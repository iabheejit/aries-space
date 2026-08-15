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


def test_second_target_failure_rolls_back_pair_and_results(
    benchmark_context, monkeypatch
):
    session, store, dataset_id = benchmark_context
    original = benchmarks._execute_target
    calls = 0

    def fail_second(target, payload, ground_baseline_ms=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("edge execution failed")
        return original(target, payload, ground_baseline_ms)

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


def test_latest_pair_orders_by_completed_pair(benchmark_context):
    session, store, dataset_id = benchmark_context
    first = run_benchmark_pair(session, store, dataset_id)
    second = run_benchmark_pair(session, store, dataset_id)

    latest = latest_completed_pair(session, "satnogs-payload-anomaly-proxy")

    assert latest.id == second.id
    assert latest.id != first.id
