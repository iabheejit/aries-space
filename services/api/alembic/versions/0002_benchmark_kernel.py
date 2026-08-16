"""Add benchmark kernel tables."""

from alembic import op
import sqlalchemy as sa

revision = "0002_benchmark_kernel"
down_revision = "0001_aries_storage_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workloads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("detector_version", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "execution_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("power_source", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("avg_watts", sa.Float(), nullable=False),
        sa.Column("slowdown_factor", sa.Float(), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "power_source IN ('estimated', 'simulated', 'measured_external')",
            name="ck_execution_targets_power_source",
        ),
    )
    op.create_table(
        "benchmark_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("correlation_id", sa.String(36), nullable=False, unique=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workload_id", sa.Integer(), sa.ForeignKey("workloads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dataset_sha256", sa.String(64), nullable=False),
        sa.Column("detector_version", sa.String(64), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("recommendation", sa.String(32)),
        sa.Column("break_even_downlink_inr_per_gb", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_benchmark_pairs_status",
        ),
    )
    op.create_index("ix_benchmark_pairs_created_at", "benchmark_pairs", ["created_at"])
    op.create_index("ix_benchmark_pairs_completed_at", "benchmark_pairs", ["completed_at"])
    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pair_id", sa.Integer(), sa.ForeignKey("benchmark_pairs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("execution_targets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result_object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("input_bytes", sa.BigInteger(), nullable=False),
        sa.Column("output_bytes", sa.BigInteger(), nullable=False),
        sa.Column("wall_ms", sa.Float(), nullable=False),
        sa.Column("inference_ms", sa.Float(), nullable=False),
        sa.Column("avg_watts", sa.Float(), nullable=False),
        sa.Column("energy_joules", sa.Float(), nullable=False),
        sa.Column("power_source", sa.String(32), nullable=False),
        sa.Column("simulation_model_version", sa.String(64), nullable=False),
        sa.Column("data_reduction_factor", sa.Float(), nullable=False),
        sa.Column("downlink_saved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("downlink_saved_seconds", sa.Float(), nullable=False),
        sa.Column("cost_per_run_inr", sa.Float(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pair_id", "target_id", name="uq_benchmark_runs_pair_target"),
        sa.CheckConstraint("status IN ('completed', 'failed')", name="ck_benchmark_runs_status"),
        sa.CheckConstraint(
            "power_source IN ('estimated', 'simulated', 'measured_external')",
            name="ck_benchmark_runs_power_source",
        ),
    )
    op.create_index("ix_benchmark_runs_completed_at", "benchmark_runs", ["completed_at"])


def downgrade() -> None:
    op.drop_table("benchmark_runs")
    op.drop_table("benchmark_pairs")
    op.drop_table("execution_targets")
    op.drop_table("workloads")
