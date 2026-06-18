from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .metrics import score_result
from .simulation import load_scenario, run_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the DAH UAV/UGV cyber test harness.")
    parser.add_argument("--scenario", required=True, help="Path to a scenario JSON file.")
    parser.add_argument("--output", help="Optional path to write a summary JSON file.")
    parser.add_argument("--trace-output", help="Optional path to write full telemetry/action trace JSON.")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a defense threshold, for example --set route_deviation_threshold_m=45.",
    )
    args = parser.parse_args(argv)

    scenario = load_scenario(Path(args.scenario))
    _apply_overrides(scenario.defense, args.set)

    result = run_scenario(scenario)
    metrics = score_result(result, detection_grace_s=scenario.metric_detection_grace_s)
    summary = {
        "scenario": scenario.name,
        "description": scenario.description,
        "frames": len(result.frames),
        "actions": [asdict(action) for action in result.actions],
        "metrics": metrics,
        "defense": asdict(scenario.defense),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.trace_output:
        trace_path = Path(args.trace_output)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace = {
            "frames": [asdict(frame) for frame in result.frames],
            "actions": [asdict(action) for action in result.actions],
        }
        trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0


def _apply_overrides(defense: Any, overrides: list[str]) -> None:
    for override in overrides:
        if "=" not in override:
            raise SystemExit(f"invalid --set value, expected KEY=VALUE: {override}")
        key, raw_value = override.split("=", 1)
        if not hasattr(defense, key):
            raise SystemExit(f"unknown defense setting: {key}")
        current_value = getattr(defense, key)
        if isinstance(current_value, int) and not isinstance(current_value, bool):
            value: float | int = int(float(raw_value))
        else:
            value = float(raw_value)
        setattr(defense, key, value)


if __name__ == "__main__":
    raise SystemExit(main())
