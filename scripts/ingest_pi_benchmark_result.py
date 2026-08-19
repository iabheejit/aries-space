"""Turn a raw timing result from scripts/pi_landcover_benchmark.py (run on
a physically separate Raspberry Pi 4B) into real cost figures, using
Aries's existing, unmodified cost formulas -- so this comparison isn't a
second copy of the cost math that can silently drift from the real one.

Run this on the dev machine (needs the full aries_api package importable),
after copying the Pi's output JSON back:

    python3 scripts/ingest_pi_benchmark_result.py pi_landcover_result.json \\
        --avg-watts 6.4

--avg-watts is required and always labeled ESTIMATED unless a real
USB power meter reading is supplied -- the Pi's own result JSON leaves
this field marked "NOT YET MEASURED" deliberately, so it isn't
silently forgotten as a follow-up. 6.4W is the Raspberry Pi Foundation's
published typical figure for a Pi 4B under sustained CPU load (no
attached peripherals); pass whatever you actually measure once a power
meter is available.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Deliberately import only metrics.py, not services.api.aries_api.config --
# config.py has real side effects (it requires DATABASE_URL, MinIO creds,
# etc. to even be imported, since it's meant to run inside the app
# container). This script has nothing to do with the running app, so the
# defaults below are copied from config.py's own defaults instead, with
# CLI overrides for anyone who has changed them via .env.
from services.api.aries_api.metrics import calculate_run_metrics

DEFAULT_DOWNLINK_MBPS = 100.0
DEFAULT_ELECTRICITY_INR_PER_KWH = 8.0
DEFAULT_EDGE_HARDWARE_CAPEX_PER_RUN_INR = 164.3835616438356  # Rs300,000 / (1 run/day * 5yr)
DEFAULT_EDGE_EXPECTED_RUNS_PER_DAY = 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_json", type=Path)
    parser.add_argument(
        "--avg-watts",
        type=float,
        required=True,
        help="Estimated or measured average power draw in watts during inference",
    )
    parser.add_argument(
        "--power-measured",
        action="store_true",
        help="Pass this only if --avg-watts came from an actual power meter reading, not a published spec figure",
    )
    parser.add_argument("--downlink-mbps", type=float, default=DEFAULT_DOWNLINK_MBPS)
    parser.add_argument("--electricity-inr-per-kwh", type=float, default=DEFAULT_ELECTRICITY_INR_PER_KWH)
    parser.add_argument(
        "--edge-hardware-capex-per-run-inr",
        type=float,
        default=DEFAULT_EDGE_HARDWARE_CAPEX_PER_RUN_INR,
        help="Must match the running app's EDGE_HARDWARE_CAPEX_PER_RUN_INR (from .env) for the comparison to be apples-to-apples",
    )
    args = parser.parse_args()

    result = json.loads(args.result_json.read_text())

    # Mirror LandcoverClassifierResult.payload() closely enough to measure
    # a realistic output size -- this is what determines the data
    # reduction factor and downlink savings, so it has to be the same
    # shape of payload the real workload would produce.
    output_payload = {
        "workload": result["workload"],
        "detector_version": "onnx-mlp-landcover-v1",
        "raster": result["raster"],
        "class_names": list(result["class_pixel_fraction"].keys()),
        "class_pixel_fraction": result["class_pixel_fraction"],
        "dominant_class": max(result["class_pixel_fraction"], key=result["class_pixel_fraction"].get),
        "input_bytes": result["input_bytes"],
    }
    output_bytes = len(json.dumps(output_payload, sort_keys=True, separators=(",", ":")).encode())

    metrics = calculate_run_metrics(
        input_bytes=result["input_bytes"],
        output_bytes=output_bytes,
        wall_ms=result["wall_ms_median"],
        avg_watts=args.avg_watts,
        downlink_mbps=args.downlink_mbps,
        electricity_inr_per_kwh=args.electricity_inr_per_kwh,
        compute_inr_per_hour=0.0,
        fixed_cost_inr_per_run=args.edge_hardware_capex_per_run_inr,
    )

    print(f"Target: {result['target_label']}")
    print(f"Host: {result['host']['platform']} / {result['host']['processor']}")
    print(f"Power basis: {'MEASURED' if args.power_measured else 'ESTIMATED (published spec figure, not a meter reading)'} -- {args.avg_watts}W")
    print(f"Median wall time: {result['wall_ms_median']:.3f} ms over {result['iterations']} iterations")
    print(f"Input bytes: {result['input_bytes']:,}  Output bytes: {output_bytes:,}  DRF: {metrics.data_reduction_factor:.2f}x")
    print(f"Energy: {metrics.energy_joules:.4f} J")
    print(f"Cost per run: Rs{metrics.cost_per_run_inr:.6f} (includes Rs{args.edge_hardware_capex_per_run_inr:.2f} amortized hardware charge)")
    print()
    print("Compare this cost_per_run against the existing ground-cpu and Mac-constrained-edge")
    print("numbers for the same fixture, from POST /api/benchmarks?workload=sentinel2-landcover-classifier")


if __name__ == "__main__":
    main()
