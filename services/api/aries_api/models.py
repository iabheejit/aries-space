from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "satellite_norad_id IS NOT NULL OR aoi_id IS NOT NULL",
            name="ck_datasets_subject",
        ),
        UniqueConstraint("source", "external_id", name="uq_datasets_source_external_id"),
        UniqueConstraint("object_key", name="uq_datasets_object_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    satellite_norad_id: Mapped[int | None] = mapped_column(BigInteger)
    aoi_id: Mapped[int | None] = mapped_column(BigInteger)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), unique=True)
    satnogs_observation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    satellite_id: Mapped[int] = mapped_column(BigInteger, index=True)
    station_id: Mapped[int | None] = mapped_column(BigInteger)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    frequency: Mapped[int | None] = mapped_column(BigInteger)
    signal_quality: Mapped[str | None] = mapped_column(String(64))
    waterfall_url: Mapped[str | None] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(Text)
    decoded_data: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Pass(Base):
    __tablename__ = "passes"

    id: Mapped[int] = mapped_column(primary_key=True)
    norad_id: Mapped[int] = mapped_column(BigInteger, index=True)
    aos: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    los: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_elevation_deg: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tle_stale: Mapped[bool] = mapped_column(default=False)


class Workload(Base):
    __tablename__ = "workloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(256))
    detector_version: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)


class ExecutionTarget(Base):
    __tablename__ = "execution_targets"
    __table_args__ = (
        CheckConstraint(
            "power_source IN ('estimated', 'simulated', 'measured_external')",
            name="ck_execution_targets_power_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    power_source: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str] = mapped_column(String(64))
    avg_watts: Mapped[float] = mapped_column(Float)
    slowdown_factor: Mapped[float] = mapped_column(Float)
    is_simulated: Mapped[bool] = mapped_column(Boolean)


class BenchmarkPair(Base):
    __tablename__ = "benchmark_pairs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_benchmark_pairs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(36), unique=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"))
    workload_id: Mapped[int] = mapped_column(ForeignKey("workloads.id", ondelete="RESTRICT"))
    dataset_sha256: Mapped[str] = mapped_column(String(64))
    detector_version: Mapped[str] = mapped_column(String(64))
    assumptions: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    recommendation: Mapped[str | None] = mapped_column(String(32))
    break_even_downlink_inr_per_gb: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    __table_args__ = (
        UniqueConstraint("pair_id", "target_id", name="uq_benchmark_runs_pair_target"),
        CheckConstraint(
            "status IN ('completed', 'failed')", name="ck_benchmark_runs_status"
        ),
        CheckConstraint(
            "power_source IN ('estimated', 'simulated', 'measured_external')",
            name="ck_benchmark_runs_power_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pair_id: Mapped[int] = mapped_column(ForeignKey("benchmark_pairs.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("execution_targets.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16))
    result_object_key: Mapped[str] = mapped_column(String(512), unique=True)
    result_sha256: Mapped[str] = mapped_column(String(64))
    input_bytes: Mapped[int] = mapped_column(BigInteger)
    output_bytes: Mapped[int] = mapped_column(BigInteger)
    wall_ms: Mapped[float] = mapped_column(Float)
    inference_ms: Mapped[float] = mapped_column(Float)
    avg_watts: Mapped[float] = mapped_column(Float)
    energy_joules: Mapped[float] = mapped_column(Float)
    power_source: Mapped[str] = mapped_column(String(32))
    simulation_model_version: Mapped[str] = mapped_column(String(64))
    data_reduction_factor: Mapped[float] = mapped_column(Float)
    downlink_saved_bytes: Mapped[int] = mapped_column(BigInteger)
    downlink_saved_seconds: Mapped[float] = mapped_column(Float)
    cost_per_run_inr: Mapped[float] = mapped_column(Float)
    result: Mapped[dict] = mapped_column(JSON)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)