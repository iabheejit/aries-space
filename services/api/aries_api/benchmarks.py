import hashlib
import json
import logging
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.api.aries_api import config
from services.api.aries_api.metrics import (
    break_even_downlink_price,
    calculate_run_metrics,
    recommendation_for_price,
)
from services.api.aries_api.models import (
    BenchmarkPair,
    BenchmarkRun,
    Dataset,
    ExecutionTarget,
    Observation,
    Workload,
)
from services.api.aries_api.storage import ObjectStore
from services.api.aries_api.workloads import satnogs_payload_proxy, sentinel2_ndvi_summary

logger = logging.getLogger("aries.benchmarks")
RESULTS_BUCKET = "results"
EDGE_MODEL_VERSION = "edge-sim-m4-v1"
GROUND_MODEL_VERSION = "local-median-v1"


class DatasetNotFoundError(Exception):
    pass


class DatasetIneligibleError(Exception):
    pass


class BenchmarkUnavailableError(Exception):
    pass


class BenchmarkNotFoundError(Exception):
    pass


class WorkloadNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class WorkloadSpec:
    slug: str
    name: str
    detector_version: str
    description: str
    eligible_sources: frozenset[str]
    run: Callable[[bytes], Any]
    canonical_result_bytes: Callable[[Any], bytes]
    sample_iterations: int


WORKLOAD_REGISTRY: dict[str, WorkloadSpec] = {
    satnogs_payload_proxy.WORKLOAD_SLUG: WorkloadSpec(
        slug=satnogs_payload_proxy.WORKLOAD_SLUG,
        name="SatNOGS Payload Anomaly Proxy",
        detector_version=satnogs_payload_proxy.DETECTOR_VERSION,
        description=(
            "Deterministic payload/metadata completeness proxy; not decoded-frame "
            "telemetry anomaly detection."
        ),
        eligible_sources=frozenset({"satnogs"}),
        run=satnogs_payload_proxy.run,
        canonical_result_bytes=satnogs_payload_proxy.canonical_result_bytes,
        sample_iterations=config.BENCHMARK_SAMPLE_ITERATIONS,
    ),
    sentinel2_ndvi_summary.WORKLOAD_SLUG: WorkloadSpec(
        slug=sentinel2_ndvi_summary.WORKLOAD_SLUG,
        name="Sentinel-2 NDVI Summary",
        detector_version=sentinel2_ndvi_summary.DETECTOR_VERSION,
        description=(
            "Deterministic, model-free NDVI summary statistics computed from a real "
            "Sentinel-2 L2A red/NIR crop."
        ),
        eligible_sources=frozenset({"sentinel2"}),
        run=sentinel2_ndvi_summary.run,
        canonical_result_bytes=sentinel2_ndvi_summary.canonical_result_bytes,
        # Raster workloads cost orders of magnitude more per call than the
        # tiny JSON-metadata SatNOGS proxy; a much smaller sample count
        # keeps the ground-cpu median measurement inside the target timeout.
        sample_iterations=config.SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS,
    ),
}
DEFAULT_WORKLOAD_SLUG = satnogs_payload_proxy.WORKLOAD_SLUG


@dataclass(frozen=True)
class RunEvidence:
    target_slug: str
    target_name: str
    power_source: str
    model_version: str
    result_object_key: str
    result_sha256: str
    input_bytes: int
    output_bytes: int
    wall_ms: float
    inference_ms: float
    avg_watts: float
    energy_joules: float
    data_reduction_factor: float
    downlink_saved_bytes: int
    downlink_saved_seconds: float
    cost_per_run_inr: float
    result: dict


def assumptions_snapshot() -> dict:
    return {
        "downlink_mbps": config.DOWNLINK_MBPS,
        "electricity_inr_per_kwh": config.ELECTRICITY_INR_PER_KWH,
        "downlink_inr_per_gb": config.DOWNLINK_INR_PER_GB,
        "ground_compute_inr_per_hour": config.GROUND_COMPUTE_INR_PER_HOUR,
        "ground_estimated_watts": config.GROUND_ESTIMATED_WATTS,
        "edge_sim_watts": config.EDGE_SIM_WATTS,
        "edge_sim_slowdown_factor": config.EDGE_SIM_SLOWDOWN_FACTOR,
        "ground_sample_iterations": config.BENCHMARK_SAMPLE_ITERATIONS,
        "placement_model": (
            "Ground downlinks input then processes; simulated edge processes first "
            "then downlinks workload output."
        ),
    }


def _seed_catalog(
    session: Session, spec: WorkloadSpec
) -> tuple[Workload, list[ExecutionTarget]]:
    workload = session.scalar(select(Workload).where(Workload.slug == spec.slug))
    if workload is None:
        workload = Workload(
            slug=spec.slug,
            name=spec.name,
            detector_version=spec.detector_version,
            description=spec.description,
        )
        session.add(workload)
    else:
        workload.name = spec.name
        workload.detector_version = spec.detector_version
        workload.description = spec.description

    target_specs = (
        {
            "slug": "ground-cpu",
            "name": "Terrestrial CPU",
            "power_source": "estimated",
            "model_version": GROUND_MODEL_VERSION,
            "avg_watts": config.GROUND_ESTIMATED_WATTS,
            "slowdown_factor": 1.0,
            "is_simulated": False,
        },
        {
            "slug": "edge-sim",
            "name": "Simulated Edge Node",
            "power_source": "simulated",
            "model_version": EDGE_MODEL_VERSION,
            "avg_watts": config.EDGE_SIM_WATTS,
            "slowdown_factor": config.EDGE_SIM_SLOWDOWN_FACTOR,
            "is_simulated": True,
        },
    )
    targets = []
    for spec in target_specs:
        target = session.scalar(
            select(ExecutionTarget).where(ExecutionTarget.slug == spec["slug"])
        )
        if target is None:
            target = ExecutionTarget(**spec)
            session.add(target)
        else:
            for name, value in spec.items():
                setattr(target, name, value)
        targets.append(target)
    session.flush()
    return workload, targets


def _result_bytes(core: dict, execution: dict) -> tuple[bytes, dict]:
    result = {**core, "execution": execution, "output_bytes": 0}
    for _ in range(4):
        payload = json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        if result["output_bytes"] == len(payload):
            return payload, result
        result["output_bytes"] = len(payload)
    raise BenchmarkUnavailableError("Result size did not stabilize")


def _execute_target(
    target: ExecutionTarget,
    payload: bytes,
    spec: WorkloadSpec,
    ground_baseline_ms: float | None = None,
) -> tuple[bytes, dict, float, float, int]:
    if target.is_simulated:
        if ground_baseline_ms is None:
            raise BenchmarkUnavailableError("Simulated edge requires ground baseline")
        proxy = spec.run(payload)
        inference_ms = ground_baseline_ms * target.slowdown_factor
        wall_ms = inference_ms
        timing_basis = "modeled_from_ground_median"
    else:
        iterations = spec.sample_iterations
        for _ in range(min(100, iterations)):
            spec.run(payload)
        samples = []
        proxy = None
        for _ in range(iterations):
            started = time.perf_counter_ns()
            proxy = spec.run(payload)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
        inference_ms = max(statistics.median(samples), 0.001)
        wall_ms = inference_ms
        timing_basis = "measured_container_median_estimated_power"
        if proxy is None:
            raise BenchmarkUnavailableError("Ground benchmark produced no samples")
    execution = {
        "target": target.slug,
        "target_label": target.name,
        "power_source": target.power_source,
        "model_version": target.model_version,
        "timing_basis": timing_basis,
        "wall_ms": round(wall_ms, 6),
        "inference_ms": round(inference_ms, 6),
        "avg_watts": target.avg_watts,
    }
    analytical_output_bytes = len(spec.canonical_result_bytes(proxy))
    return (
        *_result_bytes(proxy.payload(), execution),
        wall_ms,
        inference_ms,
        analytical_output_bytes,
    )


def _execute_target_bounded(
    target: ExecutionTarget,
    payload: bytes,
    spec: WorkloadSpec,
    ground_baseline_ms: float | None = None,
) -> tuple[bytes, dict, float, float, int]:
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="benchmark-target") as executor:
        future = executor.submit(_execute_target, target, payload, spec, ground_baseline_ms)
        try:
            return future.result(timeout=config.BENCHMARK_TIMEOUT_SECONDS)
        except FutureTimeoutError as exc:
            future.cancel()
            raise BenchmarkUnavailableError(
                f"Target {target.slug} exceeded benchmark timeout"
            ) from exc


def run_benchmark_pair(
    session: Session,
    store: ObjectStore,
    dataset_id: int,
    workload_slug: str = DEFAULT_WORKLOAD_SLUG,
) -> BenchmarkPair:
    spec = WORKLOAD_REGISTRY.get(workload_slug)
    if spec is None:
        raise WorkloadNotFoundError(f"Unknown workload '{workload_slug}'")

    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise DatasetNotFoundError(f"Dataset {dataset_id} was not found")
    if dataset.source not in spec.eligible_sources:
        raise DatasetIneligibleError(
            f"Dataset source '{dataset.source}' is not eligible for workload "
            f"'{spec.slug}' (eligible: {sorted(spec.eligible_sources)})"
        )
    if dataset.source == "satnogs":
        observation = session.scalar(
            select(Observation).where(Observation.dataset_id == dataset.id)
        )
        if observation is None:
            raise DatasetIneligibleError("SatNOGS dataset has no linked observation")

    try:
        raw_payload = store.get(config.MINIO_RAW_BUCKET, dataset.object_key)
    except Exception as exc:
        raise BenchmarkUnavailableError("Dataset object is unavailable") from exc
    if hashlib.sha256(raw_payload).hexdigest() != dataset.sha256:
        raise DatasetIneligibleError("Dataset object checksum does not match provenance")

    correlation_id = str(uuid.uuid4())
    created_keys: list[str] = []
    try:
        workload, targets = _seed_catalog(session, spec)
        pair = BenchmarkPair(
            correlation_id=correlation_id,
            dataset_id=dataset.id,
            workload_id=workload.id,
            dataset_sha256=dataset.sha256,
            detector_version=workload.detector_version,
            assumptions=assumptions_snapshot(),
            status="running",
            recommendation=None,
            break_even_downlink_inr_per_gb=None,
            created_at=datetime.now(timezone.utc),
            completed_at=None,
        )
        session.add(pair)
        session.flush()

        evidence: list[tuple[ExecutionTarget, RunEvidence, dict]] = []
        ground_baseline_ms = None
        for target in targets:
            (
                result_bytes,
                result,
                wall_ms,
                inference_ms,
                analytical_output_bytes,
            ) = _execute_target_bounded(
                target, raw_payload, spec, ground_baseline_ms
            )
            if target.slug == "ground-cpu":
                ground_baseline_ms = wall_ms
            result_sha256 = hashlib.sha256(result_bytes).hexdigest()
            key = f"benchmarks/{correlation_id}/{target.slug}/result.json"
            store.put(RESULTS_BUCKET, key, result_bytes, result_sha256)
            created_keys.append(key)
            stored = store.get(RESULTS_BUCKET, key)
            if hashlib.sha256(stored).hexdigest() != result_sha256:
                raise BenchmarkUnavailableError("Stored result checksum mismatch")
            metrics = calculate_run_metrics(
                input_bytes=len(raw_payload),
                output_bytes=analytical_output_bytes,
                wall_ms=wall_ms,
                avg_watts=target.avg_watts,
                downlink_mbps=config.DOWNLINK_MBPS,
                electricity_inr_per_kwh=config.ELECTRICITY_INR_PER_KWH,
                compute_inr_per_hour=(
                    config.GROUND_COMPUTE_INR_PER_HOUR
                    if target.slug == "ground-cpu"
                    else 0
                ),
            )
            run_evidence = RunEvidence(
                target_slug=target.slug,
                target_name=target.name,
                power_source=target.power_source,
                model_version=target.model_version,
                result_object_key=key,
                result_sha256=result_sha256,
                input_bytes=len(raw_payload),
                output_bytes=analytical_output_bytes,
                wall_ms=wall_ms,
                inference_ms=inference_ms,
                avg_watts=target.avg_watts,
                energy_joules=metrics.energy_joules,
                data_reduction_factor=metrics.data_reduction_factor,
                downlink_saved_bytes=metrics.downlink_saved_bytes,
                downlink_saved_seconds=metrics.downlink_saved_seconds,
                cost_per_run_inr=metrics.cost_per_run_inr,
                result=result,
            )
            evidence.append((target, run_evidence, result))

        by_slug = {item.target_slug: item for _, item, _ in evidence}
        ground = by_slug["ground-cpu"]
        edge = by_slug["edge-sim"]
        break_even = break_even_downlink_price(
            ground_cost_inr=ground.cost_per_run_inr,
            edge_cost_inr=edge.cost_per_run_inr,
            downlink_saved_bytes=edge.downlink_saved_bytes,
        )
        recommendation = recommendation_for_price(
            configured_downlink_inr_per_gb=config.DOWNLINK_INR_PER_GB,
            break_even_inr_per_gb=break_even,
        )
        completed_at = datetime.now(timezone.utc)
        for target, item, result in evidence:
            session.add(
                BenchmarkRun(
                    pair_id=pair.id,
                    target_id=target.id,
                    status="completed",
                    result_object_key=item.result_object_key,
                    result_sha256=item.result_sha256,
                    input_bytes=item.input_bytes,
                    output_bytes=item.output_bytes,
                    wall_ms=item.wall_ms,
                    inference_ms=item.inference_ms,
                    avg_watts=item.avg_watts,
                    energy_joules=item.energy_joules,
                    power_source=item.power_source,
                    simulation_model_version=item.model_version,
                    data_reduction_factor=item.data_reduction_factor,
                    downlink_saved_bytes=item.downlink_saved_bytes,
                    downlink_saved_seconds=item.downlink_saved_seconds,
                    cost_per_run_inr=item.cost_per_run_inr,
                    result=result,
                    completed_at=completed_at,
                )
            )
        pair.status = "completed"
        pair.recommendation = recommendation
        pair.break_even_downlink_inr_per_gb = break_even
        pair.completed_at = completed_at
        session.commit()
        return pair
    except Exception as exc:
        session.rollback()
        for key in created_keys:
            try:
                store.delete(RESULTS_BUCKET, key)
            except Exception:
                logger.exception(
                    "benchmark_orphan_result correlation_id=%s key=%s",
                    correlation_id,
                    key,
                )
        if isinstance(exc, (DatasetNotFoundError, DatasetIneligibleError)):
            raise
        raise BenchmarkUnavailableError("Benchmark pair failed atomically") from exc


def latest_completed_pair(
    session: Session, workload_slug: str | None = None
) -> BenchmarkPair:
    """Most recent completed pair. Pass workload_slug to filter to one
    workload, or None for the most recent pair across all workloads (used
    by the dashboard's single headline benchmark slot).
    """
    query = (
        select(BenchmarkPair)
        .where(BenchmarkPair.status == "completed")
        .order_by(BenchmarkPair.completed_at.desc(), BenchmarkPair.id.desc())
        .limit(1)
    )
    if workload_slug is not None:
        query = query.join(Workload, Workload.id == BenchmarkPair.workload_id).where(
            Workload.slug == workload_slug
        )
    pair = session.scalar(query)
    if pair is None:
        raise BenchmarkNotFoundError("No completed benchmark pair found")
    return pair


def serialize_pair(session: Session, pair: BenchmarkPair) -> dict:
    workload = session.get(Workload, pair.workload_id)
    dataset = session.get(Dataset, pair.dataset_id)
    runs = session.execute(
        select(BenchmarkRun, ExecutionTarget)
        .join(ExecutionTarget, ExecutionTarget.id == BenchmarkRun.target_id)
        .where(BenchmarkRun.pair_id == pair.id, BenchmarkRun.status == "completed")
        .order_by(ExecutionTarget.slug)
    ).all()
    if workload is None or dataset is None or len(runs) != 2:
        raise BenchmarkUnavailableError("Benchmark pair is incomplete")
    return {
        "pair_id": pair.id,
        "correlation_id": pair.correlation_id,
        "status": pair.status,
        "completed_at": pair.completed_at.isoformat(),
        "workload": {
            "slug": workload.slug,
            "name": workload.name,
            "detector_version": pair.detector_version,
            "description": workload.description,
        },
        "dataset": {
            "id": dataset.id,
            "source": dataset.source,
            "external_id": dataset.external_id,
            "sha256": pair.dataset_sha256,
        },
        "assumptions": pair.assumptions,
        "recommendation": pair.recommendation,
        "break_even_downlink_inr_per_gb": pair.break_even_downlink_inr_per_gb,
        "runs": [
            {
                **asdict(
                    RunEvidence(
                        target_slug=target.slug,
                        target_name=target.name,
                        power_source=run.power_source,
                        model_version=run.simulation_model_version,
                        result_object_key=run.result_object_key,
                        result_sha256=run.result_sha256,
                        input_bytes=run.input_bytes,
                        output_bytes=run.output_bytes,
                        wall_ms=run.wall_ms,
                        inference_ms=run.inference_ms,
                        avg_watts=run.avg_watts,
                        energy_joules=run.energy_joules,
                        data_reduction_factor=run.data_reduction_factor,
                        downlink_saved_bytes=run.downlink_saved_bytes,
                        downlink_saved_seconds=run.downlink_saved_seconds,
                        cost_per_run_inr=run.cost_per_run_inr,
                        result=run.result,
                    )
                )
            }
            for run, target in runs
        ],
    }
