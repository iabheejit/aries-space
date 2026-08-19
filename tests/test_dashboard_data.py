import pytest

from services.api.aries_api.dashboard_data import (
    build_workload_matrix,
    economics_breakdown,
)


def _pair(*, timing_basis="modeled_from_ground_baseline", recommendation="ground"):
    return {
        "pair_id": 7,
        "completed_at": "2026-08-17T00:00:00+00:00",
        "workload": {"slug": "w1", "name": "Workload One"},
        "dataset": {"source": "satnogs", "aoi_name": None},
        "assumptions": {
            "electricity_inr_per_kwh": 8,
            "downlink_inr_per_gb": 500,
            "edge_hardware_capex_per_run_inr": 10.0,
            "edge_hardware_capex_inr": 300_000,
            "edge_hardware_lifetime_hours": 2_400,
        },
        "recommendation": recommendation,
        "break_even_downlink_inr_per_gb": 12.5,
        "runs": [
            {
                "target_slug": "ground-cpu",
                "target_name": "Ground CPU",
                "energy_joules": 3_600,
                "cost_per_run_inr": 0.108,
                "input_bytes": 1_000_000_000,
                "output_bytes": 1_000_000_000,
                "data_reduction_factor": 1.0,
                "result": {"execution": {"timing_basis": "measured"}},
            },
            {
                "target_slug": "edge-sim",
                "target_name": "Edge Sim",
                "energy_joules": 7_200,
                "cost_per_run_inr": 10.016,
                "input_bytes": 1_000_000_000,
                "output_bytes": 100_000_000,
                "data_reduction_factor": 10.0,
                "result": {"execution": {"timing_basis": timing_basis}},
            },
        ],
    }


def test_economics_breakdown_matches_hand_computed_fixture():
    breakdown = economics_breakdown(_pair())

    assert breakdown["ground_energy_inr"] == pytest.approx(3_600 / 3_600_000 * 8)
    assert breakdown["ground_compute_inr"] == pytest.approx(0.1)
    assert breakdown["edge_energy_inr"] == pytest.approx(7_200 / 3_600_000 * 8)
    assert breakdown["edge_hardware_inr"] == pytest.approx(10.0)
    assert breakdown["downlink_saved_inr"] == pytest.approx(500 - 50)
    assert breakdown["downlink_saved_bytes"] == 900_000_000
    assert breakdown["ground_total_inr"] == pytest.approx(0.108 + 500)
    assert breakdown["edge_total_inr"] == pytest.approx(10.016 + 50)
    # capex_headroom = ground_total - edge_downlink - edge_energy
    capex_headroom = (0.108 + 500) - 50 - (7_200 / 3_600_000 * 8)
    expected_breakeven = 300_000 / capex_headroom / (2_400 / 24)
    assert breakdown["breakeven_runs_per_day"] == pytest.approx(expected_breakeven)
    assert breakdown["drf"] == 10.0
    assert breakdown["workload_slug"] == "w1"
    assert breakdown["pair_id"] == 7


def test_economics_breakdown_timing_measured_flag():
    assert economics_breakdown(_pair(timing_basis="measured_apple_silicon"))["timing_measured"] is True
    assert economics_breakdown(_pair(timing_basis="modeled_from_ground_baseline"))["timing_measured"] is False


def test_economics_breakdown_returns_none_without_both_targets():
    pair = _pair()
    pair["runs"] = [pair["runs"][0]]  # only ground, no edge
    assert economics_breakdown(pair) is None


def test_economics_breakdown_no_breakeven_when_headroom_is_negative():
    pair = _pair()
    # capex_headroom = ground_total - edge_downlink - edge_energy; blow up
    # edge's energy draw so it swamps ground's total cost and headroom goes
    # non-positive -- no utilization makes edge affordable here.
    pair["runs"][1]["energy_joules"] = 1_000_000_000
    breakdown = economics_breakdown(pair)
    assert breakdown["breakeven_runs_per_day"] is None


class _NotFound(Exception):
    pass


class _Unavailable(Exception):
    pass


def test_build_workload_matrix_skips_workloads_with_no_completed_pair():
    def fake_latest(session, slug):
        if slug == "missing":
            raise _NotFound()
        if slug == "broken":
            raise _Unavailable()
        return slug  # stand-in "pair id" passed through to serialize_pair

    def fake_serialize(session, pair_stub):
        return _pair()

    matrix = build_workload_matrix(
        session=None,
        workload_slugs=["present", "missing", "broken"],
        latest_completed_pair=fake_latest,
        serialize_pair=fake_serialize,
        not_found_error=_NotFound,
        unavailable_error=_Unavailable,
    )

    assert len(matrix) == 1
    assert matrix[0]["workload_slug"] == "w1"
