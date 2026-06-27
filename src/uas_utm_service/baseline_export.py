from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .state import ServiceState


def export_baseline_files(*, scenario_path: Path, output_dir: Path, limit: int = 500) -> dict[str, str]:
    state = ServiceState(scenario_path)
    payload = state.baseline_export_payload(limit=limit)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "baseline": output_dir / "baseline.json",
        "summary": output_dir / "summary.json",
        "telemetry": output_dir / "telemetry.jsonl",
        "audit": output_dir / "audit.jsonl",
        "markdown": output_dir / "baseline_report.md",
    }
    paths["baseline"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["summary"].write_text(json.dumps(payload["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["telemetry"].write_text(_jsonl(payload.get("telemetry_jsonl", [])), encoding="utf-8")
    paths["audit"].write_text(_jsonl(payload.get("audit", [])), encoding="utf-8")
    paths["markdown"].write_text(_markdown(payload), encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export DAH UAS/UTM normal-operation baseline evidence files.")
    parser.add_argument("--scenario", default="scenarios/korea_defense_uas_utm_ops.json")
    parser.add_argument("--output-dir", default="output/baseline")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)

    paths = export_baseline_files(scenario_path=Path(args.scenario), output_dir=Path(args.output_dir), limit=args.limit)
    print(json.dumps(paths, ensure_ascii=False, indent=2))
    return 0


def _jsonl(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        f"# Baseline Report: {summary.get('scenario', payload.get('scenario', {}).get('name', 'unknown'))}",
        "",
        f"- Assets: {summary.get('asset_count', 0)}",
        f"- Missions: {summary.get('mission_count', 0)}",
        f"- Approved missions: {len(summary.get('approved_missions', []))}",
        f"- Rejected missions: {len(summary.get('rejected_missions', []))}",
        f"- Telemetry rows exported: {len(payload.get('telemetry_jsonl', []))}",
        f"- Baseline notes: {', '.join(payload.get('baseline_notes', []))}",
        "",
        "## Approved Missions",
    ]
    for mission_id in summary.get("approved_missions", []):
        lines.append(f"- `{mission_id}`")
    lines.extend(["", "## Rejected Missions"])
    for item in summary.get("rejected_missions", []):
        lines.append(f"- `{item.get('mission_id')}`: {'; '.join(item.get('reasons', []))}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())