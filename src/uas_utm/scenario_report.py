from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scenario_tools import analyze_scenario, render_markdown_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a DAH UAS/UTM scenario and generate a report.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    parser.add_argument("--fail-on", choices=["none", "error", "warning"], default="error")
    args = parser.parse_args(argv)

    report = analyze_scenario(Path(args.scenario))
    markdown = render_markdown_report(report)
    print(markdown)

    if args.json_output:
        path = Path(args.json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_output:
        path = Path(args.markdown_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")

    counts = report.get("issue_counts", {})
    if args.fail_on == "warning" and (counts.get("warning", 0) or counts.get("error", 0)):
        return 1
    if args.fail_on == "error" and counts.get("error", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())