"""Create MissionOps and Aries storage tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_aries_storage_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("satellite_norad_id", sa.BigInteger(), nullable=True),
        sa.Column("aoi_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "satellite_norad_id IS NOT NULL OR aoi_id IS NOT NULL",
            name="ck_datasets_subject",
        ),
        sa.UniqueConstraint("source", "external_id", name="uq_datasets_source_external_id"),
        sa.UniqueConstraint("object_key", name="uq_datasets_object_key"),
    )
    op.create_index("ix_datasets_observed_at", "datasets", ["observed_at"])
    op.create_index("ix_datasets_ingested_at", "datasets", ["ingested_at"])
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("satnogs_observation_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("satellite_id", sa.BigInteger(), nullable=False),
        sa.Column("station_id", sa.BigInteger()),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frequency", sa.BigInteger()),
        sa.Column("signal_quality", sa.String(64)),
        sa.Column("waterfall_url", sa.Text()),
        sa.Column("audio_url", sa.Text()),
        sa.Column("decoded_data", sa.Text()),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observations_satnogs_observation_id", "observations", ["satnogs_observation_id"])
    op.create_index("ix_observations_satellite_id", "observations", ["satellite_id"])
    op.create_index("ix_observations_timestamp", "observations", ["timestamp"])
    op.create_index("ix_observations_ingested_at", "observations", ["ingested_at"])
    op.create_table(
        "passes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("norad_id", sa.BigInteger(), nullable=False),
        sa.Column("aos", sa.DateTime(timezone=True), nullable=False),
        sa.Column("los", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_elevation_deg", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tle_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_passes_norad_id", "passes", ["norad_id"])
    op.create_index("ix_passes_aos", "passes", ["aos"])


def downgrade() -> None:
    op.drop_table("passes")
    op.drop_table("observations")
    op.drop_table("datasets")