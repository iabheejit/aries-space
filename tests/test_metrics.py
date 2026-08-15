import pytest

from services.api.aries_api.metrics import (
    MetricError,
    break_even_downlink_price,
    calculate_run_metrics,
    recommendation_for_price,
)


def test_run_metrics_match_hand_computed_fixture():
    metrics = calculate_run_metrics(
        input_bytes=1_000_000,
        output_bytes=100_000,
        wall_ms=2_000,
        avg_watts=20,
        downlink_mbps=100,
        electricity_inr_per_kwh=8,
        compute_inr_per_hour=100,
    )

    assert metrics.data_reduction_factor == 10
    assert metrics.downlink_saved_bytes == 900_000
    assert metrics.downlink_saved_seconds == pytest.approx(0.072)
    assert metrics.energy_joules == 40
    assert metrics.cost_per_run_inr == pytest.approx(
        40 / 3_600_000 * 8 + 2_000 / 3_600_000 * 100
    )


def test_break_even_and_recommendation_boundaries():
    price = break_even_downlink_price(
        ground_cost_inr=0.1,
        edge_cost_inr=0.55,
        downlink_saved_bytes=900_000,
    )

    assert price == pytest.approx(500)
    assert recommendation_for_price(
        configured_downlink_inr_per_gb=500, break_even_inr_per_gb=price
    ) == "ground"
    assert recommendation_for_price(
        configured_downlink_inr_per_gb=500.01, break_even_inr_per_gb=price
    ) == "simulated_edge"


def test_zero_saved_bytes_refuses_recommendation():
    assert break_even_downlink_price(
        ground_cost_inr=0.1, edge_cost_inr=0.2, downlink_saved_bytes=0
    ) is None
    assert recommendation_for_price(
        configured_downlink_inr_per_gb=500, break_even_inr_per_gb=None
    ) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_bytes": 0},
        {"output_bytes": 0},
        {"wall_ms": -1},
        {"avg_watts": float("nan")},
        {"downlink_mbps": 0},
    ],
)
def test_invalid_run_metrics_are_rejected(kwargs):
    values = {
        "input_bytes": 100,
        "output_bytes": 10,
        "wall_ms": 10,
        "avg_watts": 20,
        "downlink_mbps": 100,
        "electricity_inr_per_kwh": 8,
        "compute_inr_per_hour": 100,
    }
    values.update(kwargs)

    with pytest.raises(MetricError):
        calculate_run_metrics(**values)
