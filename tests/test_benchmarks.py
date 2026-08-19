import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from services.api.aries_api import benchmarks, config
from services.api.aries_api.benchmarks import (
    BenchmarkUnavailableError,
    DatasetIneligibleError,
    DatasetNotFoundError,
    latest_completed_pair,
    run_benchmark_pair,
    serialize_pair,
)
from services.api.aries_api.ingest import ingest_satnogs_observation
from services.api.aries_api.models import Base, BenchmarkPair, BenchmarkRun, Dataset
from services.api.aries_api.sentinel2_ingest import (
    AOI_COASTAL_PORT,
    AOI_GHRCE_AGRICULTURAL,
    ingest_sentinel2_crop,
)
from services.api.aries_api.storage import ObjectInfo, ObjectNotFoundError


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.put_calls = 0
        self.fail_put_on_call = None
        self.corrupt_results = False

    def put(self, bucket, key, payload, checksum):
        self.put_calls += 1
        if self.put_calls == self.fail_put_on_call:
            raise RuntimeError("result upload failed")
        self.objects[(bucket, key)] = (payload, checksum)

    def get(self, bucket, key):
        try:
            payload = self.objects[(bucket, key)][0]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc
        if bucket == "results" and self.corrupt_results:
            return payload + b"corrupt"
        return payload

    def stat(self, bucket, key):
        try:
            payload, checksum = self.objects[(bucket, key)]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc
        return ObjectInfo(len(payload), checksum)

    def delete(self, bucket, key):
        self.objects.pop((bucket, key), None)


@pytest.fixture
def benchmark_context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "satnogs_observation_14790266.json").read_text()
    )
    store = MemoryStore()
    with Session(engine, expire_on_commit=False) as session:
        dataset_id = ingest_satnogs_observation(session, store, raw, 68635).dataset_id
        yield session, store, dataset_id


def test_benchmark_pair_has_two_honestly_labeled_runs(benchmark_context):
    session, store, dataset_id = benchmark_context

    pair = run_benchmark_pair(session, store, dataset_id)
    payload = serialize_pair(session, pair)

    assert pair.status == "completed"
    assert len(payload["runs"]) == 2
    assert {run["target_slug"] for run in payload["runs"]} == {
        "ground-cpu",
        "edge-sim",
    }
    assert {run["power_source"] for run in payload["runs"]} == {
        "estimated",
        "simulated",
    }
    assert len({run["output_bytes"] for run in payload["runs"]}) == 1
    edge = next(run for run in payload["runs"] if run["target_slug"] == "edge-sim")
    assert edge["model_version"] == "edge-sim-m4-v1"
    assert "not decoded-frame telemetry anomaly detection" in edge["result"]["limitations"]
    assert session.scalar(select(func.count()).select_from(BenchmarkRun)) == 2
    assert len([key for key in store.objects if key[0] == "results"]) == 2


def test_edge_is_charged_amortized_hardware_cost_not_just_electricity(
    benchmark_context,
):
    # TCO fix regression guard: edge must not be modeled as free compute.
    # Before this fix, edge's cost_per_run_inr was electricity only, which
    # structurally guaranteed a 0-cost-basis break-even regardless of the
    # workload. The disclosed CAPEX assumption must be visible and must
    # actually be reflected in the persisted cost.
    session, store, dataset_id = benchmark_context

    pair = run_benchmark_pair(session, store, dataset_id)
    payload = serialize_pair(session, pair)

    assert payload["assumptions"]["edge_hardware_capex_per_run_inr"] == pytest.approx(
        config.EDGE_HARDWARE_CAPEX_INR / config.EDGE_EXPECTED_TOTAL_RUNS
    )
    edge = next(run for run in payload["runs"] if run["target_slug"] == "edge-sim")
    electricity_only_cost = (
        edge["energy_joules"] / 3_600_000 * config.ELECTRICITY_INR_PER_KWH
    )
    assert edge["cost_per_run_inr"] > electricity_only_cost


def test_second_target_failure_rolls_back_pair_and_results(
    benchmark_context, monkeypatch
):
    session, store, dataset_id = benchmark_context
    original = benchmarks._execute_target
    calls = 0

    def fail_second(target, payload, spec, ground_baseline_ms=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("edge execution failed")
        return original(target, payload, spec, ground_baseline_ms)

    monkeypatch.setattr(benchmarks, "_execute_target", fail_second)

    with pytest.raises(BenchmarkUnavailableError, match="failed atomically"):
        run_benchmark_pair(session, store, dataset_id)

    assert session.scalar(select(func.count()).select_from(BenchmarkPair)) == 0
    assert session.scalar(select(func.count()).select_from(BenchmarkRun)) == 0
    assert [key for key in store.objects if key[0] == "results"] == []


def test_result_upload_failure_rolls_back_pair_and_first_object(benchmark_context):
    session, store, dataset_id = benchmark_context
    store.fail_put_on_call = store.put_calls + 2

    with pytest.raises(BenchmarkUnavailableError, match="failed atomically"):
        run_benchmark_pair(session, store, dataset_id)

    assert session.scalar(select(func.count()).select_from(BenchmarkPair)) == 0
    assert [key for key in store.objects if key[0] == "results"] == []


def test_result_checksum_failure_rolls_back_pair_and_object(benchmark_context):
    session, store, dataset_id = benchmark_context
    store.corrupt_results = True

    with pytest.raises(BenchmarkUnavailableError, match="failed atomically"):
        run_benchmark_pair(session, store, dataset_id)

    assert session.scalar(select(func.count()).select_from(BenchmarkPair)) == 0
    assert [key for key in store.objects if key[0] == "results"] == []


def test_database_commit_failure_rolls_back_pair_and_results(
    benchmark_context, monkeypatch
):
    session, store, dataset_id = benchmark_context
    monkeypatch.setattr(
        session,
        "commit",
        lambda: (_ for _ in ()).throw(__import__("sqlalchemy").exc.SQLAlchemyError()),
    )

    with pytest.raises(BenchmarkUnavailableError, match="failed atomically"):
        run_benchmark_pair(session, store, dataset_id)

    assert session.scalar(select(func.count()).select_from(BenchmarkPair)) == 0
    assert session.scalar(select(func.count()).select_from(BenchmarkRun)) == 0
    assert [key for key in store.objects if key[0] == "results"] == []


def test_dataset_eligibility_errors_are_distinct(benchmark_context):
    session, store, _ = benchmark_context

    with pytest.raises(DatasetNotFoundError):
        run_benchmark_pair(session, store, 9999)

    ineligible = Dataset(
        source="sentinel2",
        external_id="scene-1",
        observed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        size_bytes=10,
        object_key="sentinel/scene-1.json",
        sha256="0" * 64,
        ingested_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        satellite_norad_id=None,
        aoi_id=1,
    )
    session.add(ineligible)
    session.commit()

    with pytest.raises(DatasetIneligibleError):
        run_benchmark_pair(session, store, ineligible.id)


@pytest.fixture
def sentinel2_benchmark_context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    crop = (
        Path(__file__).parent / "fixtures" / "sentinel2_crop_43QHD_128.tif"
    ).read_bytes()
    store = MemoryStore()
    with Session(engine, expire_on_commit=False) as session:
        dataset_id = ingest_sentinel2_crop(
            session, store, crop, AOI_GHRCE_AGRICULTURAL
        ).dataset_id
        yield session, store, dataset_id


@pytest.fixture
def multi_aoi_benchmark_context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    agricultural_crop = (
        Path(__file__).parent / "fixtures" / "sentinel2_crop_43QHD_128.tif"
    ).read_bytes()
    coastal_crop = (
        Path(__file__).parent / "fixtures" / "sentinel2_crop_43QBA_coastal_128.tif"
    ).read_bytes()
    store = MemoryStore()
    with Session(engine, expire_on_commit=False) as session:
        agricultural_id = ingest_sentinel2_crop(
            session, store, agricultural_crop, AOI_GHRCE_AGRICULTURAL
        ).dataset_id
        coastal_id = ingest_sentinel2_crop(
            session, store, coastal_crop, AOI_COASTAL_PORT
        ).dataset_id
        yield session, store, agricultural_id, coastal_id


def test_sentinel2_benchmark_pair_produces_real_recommendation(
    sentinel2_benchmark_context,
):
    session, store, dataset_id = sentinel2_benchmark_context

    pair = run_benchmark_pair(
        session, store, dataset_id, workload_slug="sentinel2-ndvi-summary"
    )
    payload = serialize_pair(session, pair)

    assert pair.status == "completed"
    # Real Sentinel-2 pixel crop in, tiny NDVI summary JSON out -- unlike the
    # SatNOGS metadata proxy, this workload has a genuine data-reduction
    # story, so a recommendation and break-even price must be computable.
    assert payload["recommendation"] in {"ground", "edge"}
    assert payload["break_even_downlink_inr_per_gb"] is not None
    assert payload["break_even_downlink_inr_per_gb"] >= 0
    for run in payload["runs"]:
        assert run["data_reduction_factor"] > 10
        assert run["downlink_saved_bytes"] > 0


def test_placement_frontier_workloads_land_near_the_boundary(
    multi_aoi_benchmark_context,
):
    # Placement-frontier workloads are deliberately NOT detection/summary
    # tasks -- their real output is the (compressed) data itself. This test
    # locks in that they land where the analysis predicted, not collapsed
    # to either extreme (a regression here would mean the workload silently
    # started behaving like a detection workload, defeating its purpose).
    session, store, agricultural_id, _coastal_id = multi_aoi_benchmark_context

    recompress_pair = run_benchmark_pair(
        session, store, agricultural_id, workload_slug="sentinel2-lossless-recompress"
    )
    quicklook_pair = run_benchmark_pair(
        session, store, agricultural_id, workload_slug="sentinel2-quicklook-thumbnail"
    )

    recompress_payload = serialize_pair(session, recompress_pair)
    quicklook_payload = serialize_pair(session, quicklook_pair)

    for run in recompress_payload["runs"]:
        assert 1.0 < run["data_reduction_factor"] < 3.0
        assert "compressed_bytes" not in run["result"]
        assert run["result"]["compressed_bytes_size"] == run["output_bytes"]

    for run in quicklook_payload["runs"]:
        assert 5.0 < run["data_reduction_factor"] < 40.0
        assert run["result"]["thumbnail_raster"]["width"] == 32

    # Both are real, unforced numbers -- confirm they're genuinely different
    # from each other and from the existing detection-workload cluster.
    recompress_drf = recompress_payload["runs"][0]["data_reduction_factor"]
    quicklook_drf = quicklook_payload["runs"][0]["data_reduction_factor"]
    assert quicklook_drf > recompress_drf * 5


def test_satnogs_dataset_is_ineligible_for_sentinel2_workload(benchmark_context):
    session, store, dataset_id = benchmark_context

    with pytest.raises(DatasetIneligibleError):
        run_benchmark_pair(
            session, store, dataset_id, workload_slug="sentinel2-ndvi-summary"
        )


def test_cloud_mask_and_ship_detect_run_against_the_right_aoi(
    multi_aoi_benchmark_context,
):
    session, store, agricultural_id, coastal_id = multi_aoi_benchmark_context

    cloud_pair = run_benchmark_pair(
        session, store, agricultural_id, workload_slug="cloud-mask"
    )
    ship_pair = run_benchmark_pair(
        session, store, coastal_id, workload_slug="ship-detect"
    )

    assert cloud_pair.status == "completed"
    assert ship_pair.status == "completed"
    cloud_payload = serialize_pair(session, cloud_pair)
    ship_payload = serialize_pair(session, ship_pair)
    for run in cloud_payload["runs"]:
        assert "cloud_fraction" in run["result"]
    for run in ship_payload["runs"]:
        assert "bright_pixel_count" in run["result"]


def test_landcover_classifier_produces_two_genuinely_measured_runs(
    multi_aoi_benchmark_context,
):
    session, store, agricultural_id, _coastal_id = multi_aoi_benchmark_context

    pair = run_benchmark_pair(
        session, store, agricultural_id, workload_slug="sentinel2-landcover-classifier"
    )
    payload = serialize_pair(session, pair)

    assert pair.status == "completed"
    assert {run["target_slug"] for run in payload["runs"]} == {
        "ground-cpu",
        "edge-measured-mac",
    }
    # Neither target is a formula-derived slowdown: both genuinely executed
    # the ONNX model and were timed independently.
    for run in payload["runs"]:
        assert run["power_source"] == "estimated"
        assert "class_pixel_fraction" in run["result"]
        assert run["result"]["dominant_class"] in {"vegetation", "bare_soil", "cloud"}
    edge = next(run for run in payload["runs"] if run["target_slug"] == "edge-measured-mac")
    assert edge["model_version"] == "onnx-edge-constrained-v1"
    assert payload["assumptions"]["edge_measured_watts"] == pytest.approx(config.EDGE_MEASURED_WATTS)
    assert "edge_sim_watts" not in payload["assumptions"]
    assert payload["recommendation"] in {"ground", "edge", None}


def test_existing_workloads_still_use_formula_derived_edge_sim(
    multi_aoi_benchmark_context,
):
    # Regression guard for the WorkloadSpec edge-override mechanism added
    # alongside the landcover classifier: pre-existing workloads must be
    # byte-for-byte unaffected -- still the simulated slowdown-factor edge,
    # not accidentally routed through an edge_run path.
    session, store, agricultural_id, _coastal_id = multi_aoi_benchmark_context

    pair = run_benchmark_pair(session, store, agricultural_id, workload_slug="cloud-mask")
    payload = serialize_pair(session, pair)

    assert {run["target_slug"] for run in payload["runs"]} == {"ground-cpu", "edge-sim"}
    edge = next(run for run in payload["runs"] if run["target_slug"] == "edge-sim")
    assert edge["power_source"] == "simulated"
    assert edge["model_version"] == "edge-sim-m4-v1"
    assert payload["assumptions"]["edge_sim_watts"] == pytest.approx(config.EDGE_SIM_WATTS)
    assert "edge_measured_watts" not in payload["assumptions"]


def test_ship_detect_rejects_agricultural_aoi(multi_aoi_benchmark_context):
    session, store, agricultural_id, _coastal_id = multi_aoi_benchmark_context

    with pytest.raises(DatasetIneligibleError):
        run_benchmark_pair(
            session, store, agricultural_id, workload_slug="ship-detect"
        )


def test_cloud_mask_rejects_coastal_aoi(multi_aoi_benchmark_context):
    session, store, _agricultural_id, coastal_id = multi_aoi_benchmark_context

    with pytest.raises(DatasetIneligibleError):
        run_benchmark_pair(session, store, coastal_id, workload_slug="cloud-mask")


def test_ndvi_summary_rejects_coastal_aoi(multi_aoi_benchmark_context):
    session, store, _agricultural_id, coastal_id = multi_aoi_benchmark_context

    with pytest.raises(DatasetIneligibleError):
        run_benchmark_pair(
            session, store, coastal_id, workload_slug="sentinel2-ndvi-summary"
        )


def test_aoi_check_fails_closed_when_dataset_aoi_id_is_none(
    multi_aoi_benchmark_context,
):
    # Rajan's M5 audit: the source check alone can mask the AOI check, since
    # every ingested dataset has a real aoi_id. Exercise the AOI guard
    # directly with a dataset whose source matches but aoi_id is None --
    # this must still be rejected, not silently treated as eligible.
    session, store, agricultural_id, _coastal_id = multi_aoi_benchmark_context
    agricultural = session.get(Dataset, agricultural_id)

    orphaned = Dataset(
        source="sentinel2",
        external_id="no-aoi-scene",
        observed_at=agricultural.observed_at,
        size_bytes=agricultural.size_bytes,
        object_key="sentinel2/no-aoi-scene.tif",
        sha256=agricultural.sha256,
        ingested_at=agricultural.ingested_at,
        aoi_id=None,
        # The Dataset schema requires satellite_norad_id OR aoi_id to be
        # set; a dummy NORAD id satisfies that constraint for this
        # synthetic row without giving it a real (and thus AOI-eligible)
        # aoi_id -- the whole point of this test.
        satellite_norad_id=0,
    )
    session.add(orphaned)
    session.commit()
    store.objects[("raw", orphaned.object_key)] = store.objects[
        ("raw", agricultural.object_key)
    ]

    with pytest.raises(DatasetIneligibleError):
        run_benchmark_pair(
            session, store, orphaned.id, workload_slug="sentinel2-ndvi-summary"
        )


def test_latest_pair_orders_by_completed_pair(benchmark_context):
    session, store, dataset_id = benchmark_context
    first = run_benchmark_pair(session, store, dataset_id)
    second = run_benchmark_pair(session, store, dataset_id)

    latest = latest_completed_pair(session, "satnogs-payload-anomaly-proxy")

    assert latest.id == second.id
    assert latest.id != first.id
