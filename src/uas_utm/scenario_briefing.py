from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def generate_briefing_files(package_root: Path) -> dict[str, str]:
    manifest_path = package_root / "manifest.json"
    manifest = _read_json(manifest_path)
    if not manifest:
        raise ValueError(f"manifest not found or invalid:{manifest_path}")
    report_path = package_root / str(manifest.get("report", {}).get("json", "report/scenario_report.json"))
    report = _read_json(report_path)
    briefing_dir = package_root / "briefing"
    briefing_dir.mkdir(parents=True, exist_ok=True)

    checklist_path = briefing_dir / "operator_checklist.md"
    aar_path = briefing_dir / "after_action_report.md"
    checklist_path.write_text(_operator_checklist(manifest, report), encoding="utf-8")
    aar_path.write_text(_after_action_report(manifest, report), encoding="utf-8")
    return {
        "operator_checklist": str(checklist_path),
        "after_action_report": str(aar_path),
    }


def generate_briefings_for_index(index_path: Path) -> dict[str, Any]:
    index = _read_json(index_path)
    if not index:
        raise ValueError(f"index not found or invalid:{index_path}")
    generated = []
    for item in index.get("packages", []):
        package_root = Path(str(item.get("package_root", "")))
        if not package_root.exists():
            continue
        paths = generate_briefing_files(package_root)
        generated.append({"package_root": str(package_root), **paths})
    result = {
        "schema_version": "dah-briefing-index.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_index": str(index_path),
        "count": len(generated),
        "briefings": generated,
        "safety_boundary": "Briefing files are reporting templates only; they do not execute faults, network actions, or vehicle commands.",
    }
    output_path = index_path.parent / "briefing_index.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["briefing_index"] = str(output_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate DAH operator checklist and after-action report templates from scenario package evidence.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package-root")
    group.add_argument("--index")
    args = parser.parse_args(argv)

    if args.package_root:
        result: dict[str, Any] = generate_briefing_files(Path(args.package_root))
    else:
        result = generate_briefings_for_index(Path(args.index))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _operator_checklist(manifest: dict[str, Any], report: dict[str, Any]) -> str:
    scenario_name = report.get("scenario_name", manifest.get("package_name", "unknown"))
    intent = manifest.get("scenario_intent", {})
    baseline = manifest.get("baseline", {})
    lines = [
        f"# Operator Checklist: {scenario_name}",
        "",
        f"- Package: `{manifest.get('package_name', 'unknown')}`",
        f"- Generated: {manifest.get('generated_at_utc', '-')}",
        f"- Training goal: {intent.get('training_goal', 'local DAH scenario rehearsal')}",
        f"- Fault profile: `{intent.get('fault_profile', 'baseline')}`",
        "- Safety boundary: local simulation only; no real tactical network, wireless, or actuator command is executed.",
        "",
        "## Pre-Run",
        "",
        "- [ ] Confirm Docker Desktop or local runtime is running.",
        "- [ ] Confirm the dashboard opens at `http://localhost:9000`.",
        "- [ ] Confirm `GET /api/health` returns OK.",
        "- [ ] Confirm `GET /api/service-status` separates real/local-capable roles from emulator-only roles.",
        "- [ ] Confirm audit verification is clean with `GET /api/logs/verify`.",
        "",
        "## Scenario Evidence",
        "",
        f"- [ ] Scenario report reviewed: `{manifest.get('report', {}).get('markdown', 'report/scenario_report.md')}`",
        f"- [ ] Baseline reviewed: `{baseline.get('baseline', 'baseline/baseline.json')}`",
        f"- [ ] Telemetry JSONL reviewed: `{baseline.get('telemetry', 'baseline/telemetry.jsonl')}`",
        f"- [ ] Audit JSONL reviewed: `{baseline.get('audit', 'baseline/audit.jsonl')}`",
        "- [ ] Protocol logs exported or captured from the dashboard.",
        "- [ ] Chain state captured before and after any allowlisted local fault.",
        "",
        "## Operator Actions",
        "",
        "- [ ] Run only the documented local scenario flow.",
        "- [ ] Use only allowlisted local fault profiles shown in the dashboard.",
        "- [ ] Keep command and mission upload execution dry-run unless a separate safe test plan approves it.",
        "- [ ] Record timestamps for request, approval, fault marker, alert, and ACK events.",
        "- [ ] Save final `/api/scenario-packages`, `/api/chain`, `/api/protocol-monitor`, and `/api/logs/verify` outputs.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _after_action_report(manifest: dict[str, Any], report: dict[str, Any]) -> str:
    scenario_name = report.get("scenario_name", manifest.get("package_name", "unknown"))
    intent = manifest.get("scenario_intent", {})
    summary = report.get("summary", {})
    expected_logs = intent.get("expected_logs", [])
    lines = [
        f"# After-Action Report: {scenario_name}",
        "",
        "## Run Metadata",
        "",
        f"- Package: `{manifest.get('package_name', 'unknown')}`",
        "- Operator:",
        "- Team:",
        "- Run start time:",
        "- Run end time:",
        "- Git commit:",
        "- Docker compose profile:",
        "",
        "## Scenario Intent",
        "",
        f"- Training goal: {intent.get('training_goal', 'local DAH scenario rehearsal')}",
        f"- Fault profile: `{intent.get('fault_profile', 'baseline')}`",
        f"- Expected logs: {', '.join(expected_logs) if expected_logs else 'baseline logs only'}",
        "- Safety boundary: local simulation only; no real tactical network, wireless, or actuator command was executed.",
        "",
        "## Baseline Summary",
        "",
        f"- Assets: {summary.get('asset_count', 0)}",
        f"- Missions: {summary.get('mission_count', 0)}",
        f"- Approved missions: {len(summary.get('approved_missions', []))}",
        f"- Rejected missions: {len(summary.get('rejected_missions', []))}",
        f"- Link coverage: {round(float(summary.get('link_coverage_rate', 0.0)) * 100, 2)}%",
        "",
        "## Evidence Collected",
        "",
        "| Evidence | Path or API | Notes |",
        "| --- | --- | --- |",
        f"| Scenario report | `{manifest.get('report', {}).get('markdown', 'report/scenario_report.md')}` | |",
        f"| Baseline | `{manifest.get('baseline', {}).get('baseline', 'baseline/baseline.json')}` | |",
        f"| Telemetry | `{manifest.get('baseline', {}).get('telemetry', 'baseline/telemetry.jsonl')}` | |",
        f"| Audit | `{manifest.get('baseline', {}).get('audit', 'baseline/audit.jsonl')}` | |",
        "| Service status | `/api/service-status` | |",
        "| Chain state | `/api/chain` | |",
        "| Protocol monitor | `/api/protocol-monitor?limit=80` | |",
        "| Log verification | `/api/logs/verify` | |",
        "",
        "## Timeline",
        "",
        "| Time | Event | Evidence ID | Operator Note |",
        "| --- | --- | --- | --- |",
        "| | Scenario start | | |",
        "| | Baseline captured | | |",
        "| | Local fault marker, if used | | |",
        "| | Alert reviewed | | |",
        "| | Response recommendation recorded | | |",
        "| | Scenario end | | |",
        "",
        "## Assessment",
        "",
        "- Detection result:",
        "- Response result:",
        "- AI-agent feature quality:",
        "- False positives or blind spots:",
        "- Residual risk:",
        "- Next tuning item:",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
