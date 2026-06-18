from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .simulator import load_scenario, run_environment, summarize_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the normal-operation UAS/UTM virtual environment.")
    parser.add_argument("--scenario", required=True, help="Path to a UAS/UTM scenario JSON file.")
    parser.add_argument("--output", help="Optional path for summary JSON output.")
    parser.add_argument("--telemetry-output", help="Optional path for telemetry JSONL output.")
    args = parser.parse_args(argv)

    scenario = load_scenario(Path(args.scenario))
    result = run_environment(scenario)
    summary = summarize_result(result)

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.telemetry_output:
        telemetry_path = Path(args.telemetry_output)
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [json.dumps(asdict(frame), ensure_ascii=False) for frame in result.telemetry]
        telemetry_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
