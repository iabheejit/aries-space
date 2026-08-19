"""Derived-economics helpers shared by dashboard panels that show more than
one workload's numbers (the workload matrix, run log, run detail cards).

The ground-vs-edge cost breakdown was previously re-derived independently in
three separate Jinja templates for the single headline benchmark pair. This
module computes it once, in Python, from the same real `serialize_pair()`
output, so it can be reused for every workload in the registry, not just one.
"""

from __future__ import annotations

from typing import Any


def economics_breakdown(pair: dict[str, Any]) -> dict[str, Any] | None:
    """Real per-run cost breakdown for one completed, serialized benchmark pair.

    Returns None only if the pair is missing one of its two runs (should not
    happen for a `status == "completed"` pair, but this stays defensive since
    the input crosses a serialization boundary).
    """
    edge = next((r for r in pair["runs"] if r["target_slug"] != "ground-cpu"), None)
    ground = next((r for r in pair["runs"] if r["target_slug"] == "ground-cpu"), None)
    if edge is None or ground is None:
        return None

    assumptions = pair["assumptions"]
    electricity = assumptions["electricity_inr_per_kwh"]
    downlink_price = assumptions["downlink_inr_per_gb"]

    ground_energy_inr = ground["energy_joules"] / 3_600_000 * electricity
    ground_compute_inr = ground["cost_per_run_inr"] - ground_energy_inr
    edge_energy_inr = edge["energy_joules"] / 3_600_000 * electricity
    edge_hardware_inr = edge["cost_per_run_inr"] - edge_energy_inr

    ground_downlink_inr = ground["input_bytes"] / 1_000_000_000 * downlink_price
    edge_downlink_inr = edge["output_bytes"] / 1_000_000_000 * downlink_price
    downlink_saved_inr = ground_downlink_inr - edge_downlink_inr

    ground_total_inr = ground["cost_per_run_inr"] + ground_downlink_inr
    edge_total_inr = edge["cost_per_run_inr"] + edge_downlink_inr

    edge_capex_per_run = assumptions["edge_hardware_capex_per_run_inr"]
    edge_lifetime_days = assumptions["edge_hardware_lifetime_hours"] / 24
    capex_headroom_inr = ground_total_inr - edge_downlink_inr - edge_energy_inr
    breakeven_runs_per_day = None
    if capex_headroom_inr > 0:
        breakeven_runs_per_day = (
            assumptions["edge_hardware_capex_inr"] / capex_headroom_inr / edge_lifetime_days
        )

    return {
        "workload_slug": pair["workload"]["slug"],
        "workload_name": pair["workload"]["name"],
        "pair_id": pair["pair_id"],
        "completed_at": pair["completed_at"],
        "dataset_source": pair["dataset"]["source"],
        "dataset_aoi_name": pair["dataset"]["aoi_name"],
        "recommendation": pair["recommendation"],
        "drf": edge["data_reduction_factor"],
        "timing_measured": "measured" in edge["result"]["execution"]["timing_basis"],
        "edge_target_name": edge["target_name"],
        "ground_compute_inr": ground_compute_inr,
        "ground_energy_inr": ground_energy_inr,
        "edge_energy_inr": edge_energy_inr,
        "edge_hardware_inr": edge_hardware_inr,
        "downlink_saved_inr": downlink_saved_inr,
        "downlink_saved_bytes": ground["input_bytes"] - edge["output_bytes"],
        "ground_total_inr": ground_total_inr,
        "edge_total_inr": edge_total_inr,
        "edge_capex_per_run": edge_capex_per_run,
        "breakeven_runs_per_day": breakeven_runs_per_day,
        "break_even_downlink_inr_per_gb": pair["break_even_downlink_inr_per_gb"],
    }


def build_workload_matrix(
    session: Any,
    workload_slugs: list[str],
    latest_completed_pair: Any,
    serialize_pair: Any,
    not_found_error: type[Exception],
    unavailable_error: type[Exception],
) -> list[dict[str, Any]]:
    """Real latest-completed-pair economics for every registered workload.

    Workloads with no completed pair yet (or a transiently unavailable one)
    are skipped rather than padded with placeholder rows -- an empty slot is
    honest, a fabricated one is not.
    """
    matrix: list[dict[str, Any]] = []
    for slug in workload_slugs:
        try:
            pair = serialize_pair(session, latest_completed_pair(session, slug))
        except (not_found_error, unavailable_error):
            continue
        breakdown = economics_breakdown(pair)
        if breakdown is not None:
            matrix.append(breakdown)
    return matrix
