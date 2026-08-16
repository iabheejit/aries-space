from dataclasses import dataclass
from math import isfinite


class MetricError(ValueError):
    pass


@dataclass(frozen=True)
class RunMetrics:
    data_reduction_factor: float
    downlink_saved_bytes: int
    downlink_saved_seconds: float
    energy_joules: float
    cost_per_run_inr: float


def calculate_run_metrics(
    *,
    input_bytes: int,
    output_bytes: int,
    wall_ms: float,
    avg_watts: float,
    downlink_mbps: float,
    electricity_inr_per_kwh: float,
    compute_inr_per_hour: float,
) -> RunMetrics:
    values = (wall_ms, avg_watts, downlink_mbps, electricity_inr_per_kwh, compute_inr_per_hour)
    if input_bytes <= 0 or output_bytes <= 0:
        raise MetricError("input_bytes and output_bytes must be positive")
    if any(not isfinite(value) or value < 0 for value in values):
        raise MetricError("metric inputs must be finite and non-negative")
    if downlink_mbps == 0:
        raise MetricError("downlink_mbps must be positive")

    saved_bytes = max(input_bytes - output_bytes, 0)
    energy_joules = avg_watts * wall_ms / 1000
    cost_inr = (
        energy_joules / 3_600_000 * electricity_inr_per_kwh
        + wall_ms / 3_600_000 * compute_inr_per_hour
    )
    return RunMetrics(
        data_reduction_factor=input_bytes / output_bytes,
        downlink_saved_bytes=saved_bytes,
        downlink_saved_seconds=saved_bytes * 8 / (downlink_mbps * 1_000_000),
        energy_joules=energy_joules,
        cost_per_run_inr=cost_inr,
    )


def break_even_downlink_price(
    *, ground_cost_inr: float, edge_cost_inr: float, downlink_saved_bytes: int
) -> float | None:
    if any(not isfinite(value) or value < 0 for value in (ground_cost_inr, edge_cost_inr)):
        raise MetricError("costs must be finite and non-negative")
    if downlink_saved_bytes < 0:
        raise MetricError("downlink_saved_bytes must be non-negative")
    if downlink_saved_bytes == 0:
        return None
    return max(edge_cost_inr - ground_cost_inr, 0) / (
        downlink_saved_bytes / 1_000_000_000
    )


def recommendation_for_price(
    *, configured_downlink_inr_per_gb: float, break_even_inr_per_gb: float | None
) -> str | None:
    if not isfinite(configured_downlink_inr_per_gb) or configured_downlink_inr_per_gb < 0:
        raise MetricError("configured downlink price must be finite and non-negative")
    if break_even_inr_per_gb is None:
        return None
    return (
        "simulated_edge"
        if configured_downlink_inr_per_gb > break_even_inr_per_gb
        else "ground"
    )
