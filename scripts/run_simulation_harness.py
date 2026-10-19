#!/usr/bin/env python3
"""LifeLink Priority 2.5: Operational Simulation & Telemetry Verification CLI.
Executes the isolated simulation harness against a sandbox database.
"""
import sys
import os
import json
import argparse

# Reconfigure stdout for UTF-8 on Windows consoles to support workspace emoji paths
if sys.platform == "win32":
    import io
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Add backend directory to path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from app.simulation.harness import SimulationHarness


def main():
    parser = argparse.ArgumentParser(description="Run LifeLink Operational Simulation Harness")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="simulation_results.json",
        help="Path to save machine-readable JSON results (default: simulation_results.json)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("LifeLink — Priority 2.5: Operational Simulation & Telemetry Verification")
    print("=" * 80)
    print("Initializing isolated sandbox database with Alembic migrations...")

    harness = SimulationHarness()
    summary = harness.execute_all()

    print(f"\nExecution Complete in {summary['total_duration_ms']} ms")
    print("-" * 80)
    print(f"{'#':<3} | {'Scenario Name':<42} | {'Status':<8} | {'Duration (ms)':<13}")
    print("-" * 80)

    for idx, sc in enumerate(summary["scenarios"], 1):
        status_str = "PASS" if sc["status"] == "passed" else "FAIL"
        print(f"{idx:<3} | {sc['scenario']:<42} | {status_str:<8} | {sc['duration_ms']:<13}")

    print("-" * 80)
    print(f"Total Scenarios: {summary['total_scenarios']} | Passed: {summary['passed']} | Failed: {summary['failed']}")
    print(f"Mock Notifications Dispatched: {summary['notifications_dispatched']}")
    print("=" * 80)

    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved machine-readable simulation results to: {output_path}\n")

    if summary["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
