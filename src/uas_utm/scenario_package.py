from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uas_utm.scenario_tools import analyze_scenario, render_markdown_report
from uas_utm_service.baseline_export import export_baseline_files


def package_scenario(*, scenario_path: Path, output_dir: Path, limit: int = 500) -> dict[str, str]:
    report = analyze_scenario(scenario_path)
    if not report.get("valid"):
        raise ValueError("scenario is not valid; run scenario report first")

    package_root = output_dir / _package_name(str(report["scenario_name"]))
    baseline_dir = package_root / "baseline"
    report_dir = package_root / "report"
    scenario_dir = package_root / "scenario"
    report_dir.mkdir(parents=True, exist_ok=True)
    scenario_dir.mkdir(parents=True, exist_ok=True)

    scenario_copy = scenario_dir / scenario_path.name
    shutil.copy2(scenario_path, scenario_copy)

    report_json = report_dir / "scenario_report.json"
    report_md = report_dir / "scenario_report.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(render_markdown_report(report), encoding="utf-8")

    baseline_paths = export_baseline_files(scenario_path=scenario_path, output_dir=baseline_dir, limit=limit)
    manifest = _manifest(
        package_root=package_root,
        scenario_copy=scenario_copy,
        report_json=report_json,
        report_md=report_md,
        baseline_paths=baseline_paths,
        report=report,
    )
    manifest_path = package_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "package_root": str(package_root),
        "manifest": str(manifest_path),
        "scenario": str(scenario_copy),
        "report_markdown": str(report_md),
        "baseline": baseline_paths["baseline"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package a DAH scenario with report and baseline evidence files.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--output-dir", default="output/scenario-packages")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)

    paths = package_scenario(scenario_path=Path(args.scenario), output_dir=Path(args.output_dir), limit=args.limit)
    print(json.dumps(paths, ensure_ascii=False, indent=2))
    return 0


def _manifest(
    *,
    package_root: Path,
    scenario_copy: Path,
    report_json: Path,
    report_md: Path,
    baseline_paths: dict[str, str],
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "package_name": package_root.name,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scenario": _relative(scenario_copy, package_root),
        "report": {
            "json": _relative(report_json, package_root),
            "markdown": _relative(report_md, package_root),
        },
        "baseline": {key: _relative(Path(value), package_root) for key, value in baseline_paths.items()},
        "valid": bool(report["valid"]),
        "issue_counts": report["issue_counts"],
    }


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _package_name(scenario_name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in scenario_name).strip("-")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{safe}-{stamp}"


if __name__ == "__main__":
    raise SystemExit(main())
