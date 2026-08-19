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
from services.api.aries_api.sentinel2_ingest import (
    AOI_COASTAL_PORT,
    AOI_GHRCE_AGRICULTURAL,
    AOI_NAMES,
)
from services.api.aries_api.storage import ObjectStore
from services.api.aries_api.workloads import (
    cloud_mask,
    satnogs_payload_proxy,
    sentinel2_landcover_classifier,
    sentinel2_lossless_recompress,
    sentinel2_ndvi_summary,
    sentinel2_quicklook_thumbnail,
    ship_detect,
)

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
    # None = any AOI is eligible for this source (the default). When set,
    # a dataset's aoi_id must be a member -- and a dataset with aoi_id=None
    # is never eligible against a non-None set (fails closed).
    eligible_aoi_ids: frozenset[int] | None = None
    # Edge-target override. Defaults reproduce today's formula-derived
    # "Simulated Edge Node" behaviour exactly, so the four pre-existing
    # workloads are byte-for-byte unaffected. A workload that sets
    # edge_is_simulated=False MUST also set edge_run -- that function is
    # then genuinely executed and timed (not modeled from the ground
    # baseline via a slowdown factor). See run_benchmark_pair/_execute_target.
    edge_run: Callable[[bytes], Any] | None = None
    edge_target_slug: str = "edge-sim"
    edge_target_name: str = "Simulated Edge Node"
    edge_power_source: str = "simulated"
    edge_model_version: str = EDGE_MODEL_VERSION
    edge_avg_watts: float = config.EDGE_SIM_WATTS
    edge_is_simulated: bool = True


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
        eligible_aoi_ids=frozenset({AOI_GHRCE_AGRICULTURAL}),
        run=sentinel2_ndvi_summary.run,
        canonical_result_bytes=sentinel2_ndvi_summary.canonical_result_bytes,
        # Raster workloads cost orders of magnitude more per call than the
        # tiny JSON-metadata SatNOGS proxy; a much smaller sample count
        # keeps the ground-cpu median measurement inside the target timeout.
        sample_iterations=config.SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS,
    ),
    cloud_mask.WORKLOAD_SLUG: WorkloadSpec(
        slug=cloud_mask.WORKLOAD_SLUG,
        name="Cloud Mask",
        detector_version=cloud_mask.DETECTOR_VERSION,
        description=(
            "Deterministic red+NIR joint-brightness cloud-fraction proxy, computed "
            "from raw Sentinel-2 bands (not the SCL shortcut)."
        ),
        eligible_sources=frozenset({"sentinel2"}),
        eligible_aoi_ids=frozenset({AOI_GHRCE_AGRICULTURAL}),
        run=cloud_mask.run,
        canonical_result_bytes=cloud_mask.canonical_result_bytes,
        sample_iterations=config.SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS,
    ),
    ship_detect.WORKLOAD_SLUG: WorkloadSpec(
        slug=ship_detect.WORKLOAD_SLUG,
        name="Ship Detect",
        detector_version=ship_detect.DETECTOR_VERSION,
        description=(
            "Deterministic bright-pixel-cluster count against a water background in "
            "a single Sentinel-2 NIR band; a statistical proxy, not a validated "
            "vessel-detection model."
        ),
        eligible_sources=frozenset({"sentinel2"}),
        eligible_aoi_ids=frozenset({AOI_COASTAL_PORT}),
        run=ship_detect.run,
        canonical_result_bytes=ship_detect.canonical_result_bytes,
        sample_iterations=config.SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS,
    ),
    sentinel2_landcover_classifier.WORKLOAD_SLUG: WorkloadSpec(
        slug=sentinel2_landcover_classifier.WORKLOAD_SLUG,
        name="Sentinel-2 Land-cover Classifier",
        detector_version=sentinel2_landcover_classifier.DETECTOR_VERSION,
        description=(
            "Real trained multi-class MLP (vegetation/bare-soil/cloud), executed via "
            "ONNX Runtime -- not a hand-written band-math threshold. Both the ground "
            "and edge targets genuinely execute and are timed; the edge target is not "
            "modeled from a ground-baseline slowdown factor."
        ),
        eligible_sources=frozenset({"sentinel2"}),
        eligible_aoi_ids=frozenset({AOI_GHRCE_AGRICULTURAL}),
        run=sentinel2_landcover_classifier.run,
        canonical_result_bytes=sentinel2_landcover_classifier.canonical_result_bytes,
        sample_iterations=config.SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS,
        edge_run=sentinel2_landcover_classifier.run_edge_constrained,
        edge_target_slug="edge-measured-mac",
        # Full caveat ("Apple Silicon stand-in, not space-qualified hardware")
        # lives in the workload's own limitations text and run_edge_constrained's
        # docstring -- kept short here so it renders cleanly in the dashboard card.
        edge_target_name="Measured Edge (single-core stand-in)",
        edge_power_source="estimated",
        edge_model_version="onnx-edge-constrained-v1",
        edge_avg_watts=config.EDGE_MEASURED_WATTS,
        edge_is_simulated=False,
    ),
    # Placement-frontier workloads (roadmap: find where the ground/edge
    # decision actually changes, not just re-confirm the same answer).
    # Deliberately NOT detection/summary tasks -- their real output is the
    # (compressed) data itself, so they land near the 1x-20x boundary
    # instead of alongside the ~60-100x detection cluster above.
    sentinel2_lossless_recompress.WORKLOAD_SLUG: WorkloadSpec(
        slug=sentinel2_lossless_recompress.WORKLOAD_SLUG,
        name="Sentinel-2 Lossless Recompress",
        detector_version=sentinel2_lossless_recompress.DETECTOR_VERSION,
        description=(
            "Real DEFLATE (zlib level 9) lossless recompression of the raw pixel "
            "bytes -- no semantic analysis. Deliberately a near-1x placement-"
            "frontier workload: its output is the compressed data itself, not an "
            "extracted insight."
        ),
        eligible_sources=frozenset({"sentinel2"}),
        eligible_aoi_ids=frozenset({AOI_GHRCE_AGRICULTURAL}),
        run=sentinel2_lossless_recompress.run,
        canonical_result_bytes=sentinel2_lossless_recompress.canonical_result_bytes,
        sample_iterations=config.SENTINEL2_BENCHMARK_SAMPLE_ITERATIONS,
    ),
    sentinel2_quicklook_thumbnail.WORKLOAD_SLUG: WorkloadSpec(
        slug=sentinel2_quicklook_thumbnail.WORKLOAD_SLUG,
        name="Sentinel-2 Quicklook Thumbnail",
        detector_version=sentinel2_quicklook_thumbnail.DETECTOR_VERSION,
        description=(
            "Real block-mean spatial decimation (4x per axis) plus zlib-6 "
            "compression -- a real EO-operations quicklook preview, not a "
            "semantic summary. Deliberately a mid-range placement-frontier "
            "workload, between the near-1x recompression workload and the "
            "~60-100x detection/summary cluster."
        ),
        eligible_sources=frozenset({"sentinel2"}),
        eligible_aoi_ids=frozenset({AOI_GHRCE_AGRICULTURAL}),
        run=sentinel2_quicklook_thumbnail.run,
        canonical_result_bytes=sentinel2_quicklook_thumbnail.canonical_result_bytes,
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


def assumptions_snapshot(spec: WorkloadSpec) -> dict:
    base = {
        "downlink_mbps": config.DOWNLINK_MBPS,
        "electricity_inr_per_kwh": config.ELECTRICITY_INR_PER_KWH,
        "downlink_inr_per_gb": config.DOWNLINK_INR_PER_GB,
        "ground_compute_inr_per_hour": config.GROUND_COMPUTE_INR_PER_HOUR,
        "ground_estimated_watts": config.GROUND_ESTIMATED_WATTS,
        "ground_sample_iterations": config.BENCHMARK_SAMPLE_ITERATIONS,
        # TCO fix: edge hardware is not a free sunk cost, and its CAPEX is
        # amortized against expected *uses*, not active compute-time -- a
        # low-duty-cycle payload (the realistic case) still pays for
        # hardware it owns whether or not it's currently running. Charged
        # to every edge target (simulated or measured) alongside electricity.
        "edge_hardware_capex_inr": config.EDGE_HARDWARE_CAPEX_INR,
        "edge_hardware_lifetime_hours": config.EDGE_HARDWARE_LIFETIME_HOURS,
        "edge_expected_runs_per_day": config.EDGE_EXPECTED_RUNS_PER_DAY,
        "edge_expected_total_runs": config.EDGE_EXPECTED_TOTAL_RUNS,
        "edge_hardware_capex_per_run_inr": config.EDGE_HARDWARE_CAPEX_PER_RUN_INR,
    }
    if spec.edge_is_simulated:
        base["edge_sim_watts"] = config.EDGE_SIM_WATTS
        base["edge_sim_slowdown_factor"] = config.EDGE_SIM_SLOWDOWN_FACTOR
        base["placement_model"] = (
            "Ground downlinks input then processes; simulated edge processes first "
            "then downlinks workload output."
        )
    else:
        base["edge_measured_watts"] = spec.edge_avg_watts
        base["placement_model"] = (
            "Ground downlinks input then processes; measured edge processes first "
            "then downlinks workload output. Edge timing here is genuinely executed "
            "and measured under a real resource constraint, not modeled from the "
            "ground baseline via a slowdown factor -- power draw remains an estimate."
        )
    return base


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
            "slug": spec.edge_target_slug,
            "name": spec.edge_target_name,
            "power_source": spec.edge_power_source,
            "model_version": spec.edge_model_version,
            "avg_watts": spec.edge_avg_watts,
            # Ignored by _execute_target when is_simulated is False -- the
            # DB column is non-nullable, so measured-edge workloads still
            # populate it with the global default rather than a meaningful
            # slowdown model.
            "slowdown_factor": config.EDGE_SIM_SLOWDOWN_FACTOR,
            "is_simulated": spec.edge_is_simulated,
        },
    )
    targets = []
    for target_spec in target_specs:
        target = session.scalar(
            select(ExecutionTarget).where(ExecutionTarget.slug == target_spec["slug"])
        )
        if target is None:
            target = ExecutionTarget(**target_spec)
            session.add(target)
        else:
            for name, value in target_spec.items():
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
        # Explicit dispatch: ground-cpu always runs spec.run. Any other
        # non-simulated target (a genuinely-measured edge stand-in) must
        # supply spec.edge_run -- falling back to spec.run here would
        # silently make both targets run identical code, producing
        # identical timings under a false "measured" label.
        if target.slug == "ground-cpu":
            run_fn = spec.run
            timing_basis = "measured_container_median_estimated_power"
        else:
            if spec.edge_run is None:
                raise BenchmarkUnavailableError(
                    f"Target {target.slug} is not simulated but workload "
                    f"'{spec.slug}' has no edge_run"
                )
            run_fn = spec.edge_run
            timing_basis = "measured_native_constrained_median_estimated_power"
        iterations = spec.sample_iterations
        for _ in range(min(100, iterations)):
            run_fn(payload)
        samples = []
        proxy = None
        for _ in range(iterations):
            started = time.perf_counter_ns()
            proxy = run_fn(payload)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
        inference_ms = max(statistics.median(samples), 0.001)
        wall_ms = inference_ms
        if proxy is None:
            raise BenchmarkUnavailableError(f"{target.slug} benchmark produced no samples")
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
    if spec.eligible_aoi_ids is not None and dataset.aoi_id not in spec.eligible_aoi_ids:
        # Fails closed: dataset.aoi_id is None (or simply not in the set)
        # is always ineligible when the workload restricts to specific AOIs.
        raise DatasetIneligibleError(
            f"Dataset AOI '{dataset.aoi_id}' is not eligible for workload "
            f"'{spec.slug}' (eligible: {sorted(spec.eligible_aoi_ids)})"
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
            assumptions=assumptions_snapshot(spec),
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
                # TCO fix: edge is not free compute. ground-cpu carries a
                # genuinely time-proportional cloud rental rate (real
                # pay-per-active-use billing). Edge carries a flat per-run
                # hardware amortization charge instead of an hourly rate --
                # CAPEX is incurred whether or not the hardware is currently
                # running, so amortizing against active compute-time (as an
                # earlier version of this fix did) understates true cost for
                # a low-duty-cycle payload; amortizing against expected uses
                # over the mission is the honest model.
                compute_inr_per_hour=(
                    config.GROUND_COMPUTE_INR_PER_HOUR
                    if target.slug == "ground-cpu"
                    else 0.0
                ),
                fixed_cost_inr_per_run=(
                    0.0
                    if target.slug == "ground-cpu"
                    else config.EDGE_HARDWARE_CAPEX_PER_RUN_INR
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
        edge = by_slug[spec.edge_target_slug]
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
            "aoi_name": AOI_NAMES.get(dataset.aoi_id) if dataset.aoi_id else None,
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
