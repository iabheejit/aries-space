from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
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