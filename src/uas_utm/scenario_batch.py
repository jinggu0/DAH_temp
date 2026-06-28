from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .scenario_briefing import generate_briefing_files
from .scenario_package import package_scenario


def discover_training_scenarios(scenario_dir: Path) -> list[Path]:
    if not scenario_dir.exists():
        return []
    return sorted(path for path in scenario_dir.glob("*.json") if path.is_file())


def package_training_scenarios(*, scenario_dir: Path, output_dir: Path, limit: int = 500) -> dict[str, Any]:
    scenario_paths = discover_training_scenarios(scenario_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    packages = []
    for scenario_path in scenario_paths:
        paths = package_scenario(scenario_path=scenario_path, output_dir=output_dir, limit=limit)
        manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))
        raw = _read_json(scenario_path)
        briefing_paths = generate_briefing_files(Path(paths["package_root"]))
        packages.append(
            {
                "scenario_file": _slash(scenario_path),
                "scenario_name": raw.get("name", manifest.get("package_name", scenario_path.stem)),
                "fault_profile": raw.get("scenario_intent", {}).get("fault_profile", "baseline"),
                "training_goal": raw.get("scenario_intent", {}).get("training_goal", "DAH local training scenario"),
                "package_root": paths["package_root"],
                "manifest": paths["manifest"],
                "report_markdown": paths["report_markdown"],
                "baseline": paths["baseline"],
                "operator_checklist": briefing_paths["operator_checklist"],
                "after_action_report": briefing_paths["after_action_report"],
                "valid": bool(manifest.get("valid")),
                "issue_counts": manifest.get("issue_counts", {}),
            }
        )
    index = {
        "schema_version": "dah-scenario-package-index.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scenario_dir": _slash(scenario_dir),
        "output_dir": _slash(output_dir),
        "count": len(packages),
        "packages": packages,
        "safety_boundary": "Scenario packages are local evidence exports only; no real tactical network, wireless, or actuator command is executed.",
    }
    index_json = output_dir / "index.json"
    index_md = output_dir / "index.md"
    index_json.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    index_md.write_text(_index_markdown(index), encoding="utf-8")
    index["index_json"] = str(index_json)
    index["index_markdown"] = str(index_md)
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package all DAH training scenarios with reports and baseline evidence.")
    parser.add_argument("--scenario-dir", default="scenarios/dah_training")
    parser.add_argument("--output-dir", default="output/scenario-packages")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)

    index = package_training_scenarios(scenario_dir=Path(args.scenario_dir), output_dir=Path(args.output_dir), limit=args.limit)
    print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _slash(path: Path) -> str:
    return str(path).replace("\\", "/")


def _index_markdown(index: dict[str, Any]) -> str:
    lines = [
        "# DAH Scenario Package Index",
        "",
        f"- Generated: {index['generated_at_utc']}",
        f"- Scenario count: {index['count']}",
        f"- Safety boundary: {index['safety_boundary']}",
        "",
        "## Packages",
        "",
    ]
    if not index["packages"]:
        lines.append("- none")
    for item in index["packages"]:
        lines.extend(
            [
                f"### {item['scenario_name']}",
                "",
                f"- Scenario: `{item['scenario_file']}`",
                f"- Fault profile: `{item['fault_profile']}`",
                f"- Valid: {item['valid']}",
                f"- Package root: `{item['package_root']}`",
                f"- Manifest: `{item['manifest']}`",
                f"- Report: `{item['report_markdown']}`",
                f"- Baseline: `{item['baseline']}`",
                f"- Operator checklist: `{item['operator_checklist']}`",
                f"- After-action report: `{item['after_action_report']}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
