from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import AirspaceZone, MissionSpec, Position, UasUtmScenario, UavSpec, distance
from .simulator import load_scenario, run_environment, summarize_result
from .utm_service import UtmService


@dataclass(frozen=True)
class ScenarioIssue:
    level: str
    path: str
    message: str


def analyze_scenario(path: Path) -> dict[str, Any]:
    issues: list[ScenarioIssue] = []
    try:
        scenario = load_scenario(path)
    except Exception as exc:
        return {
            "scenario_path": str(path),
            "valid": False,
            "issues": [asdict(ScenarioIssue("error", "scenario", f"failed to load scenario: {exc}"))],
            "summary": {},
            "decisions": [],
        }

    issues.extend(validate_scenario(scenario))
    decisions = UtmService(scenario).evaluate_missions()
    try:
        result = run_environment(scenario)
        summary = summarize_result(result)
    except Exception as exc:
        issues.append(ScenarioIssue("error", "simulation", f"failed to run scenario: {exc}"))
        summary = {}

    return {
        "scenario_path": str(path),
        "scenario_name": scenario.name,
        "valid": not any(issue.level == "error" for issue in issues),
        "issue_counts": _issue_counts(issues),
        "issues": [asdict(issue) for issue in issues],
        "summary": summary,
        "decisions": [asdict(decision) for decision in decisions],
        "recommendations": _recommendations(scenario, issues, summary),
    }


def validate_scenario(scenario: UasUtmScenario) -> list[ScenarioIssue]:
    issues: list[ScenarioIssue] = []
    issues.extend(_duplicate_id_issues("assets", [asset.id for asset in scenario.assets]))
    issues.extend(_duplicate_id_issues("missions", [mission.id for mission in scenario.missions]))
    issues.extend(_duplicate_id_issues("zones", [zone.id for zone in scenario.zones]))
    issues.extend(_duplicate_id_issues("c2_nodes", [node.id for node in scenario.c2_nodes]))

    assets = {asset.id: asset for asset in scenario.assets}
    if scenario.step_s <= 0:
        issues.append(ScenarioIssue("error", "step_s", "step_s must be greater than zero"))
    if scenario.duration_s <= 0:
        issues.append(ScenarioIssue("error", "duration_s", "duration_s must be greater than zero"))
    if not scenario.assets:
        issues.append(ScenarioIssue("error", "assets", "at least one asset is required"))
    if not scenario.missions:
        issues.append(ScenarioIssue("warning", "missions", "no missions are defined"))

    for index, asset in enumerate(scenario.assets):
        issues.extend(_validate_asset(asset, index))
    for index, mission in enumerate(scenario.missions):
        asset = assets.get(mission.asset_id)
        issues.extend(_validate_mission(scenario, mission, index, asset))

    return issues


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# Scenario Report: {report.get('scenario_name', 'unknown')}",
        "",
        f"- Valid: {report.get('valid')}",
        f"- Assets: {summary.get('asset_count', 0)}",
        f"- Missions: {summary.get('mission_count', 0)}",
        f"- Approved: {len(summary.get('approved_missions', []))}",
        f"- Rejected: {len(summary.get('rejected_missions', []))}",
        f"- Link coverage: {round(float(summary.get('link_coverage_rate', 0.0)) * 100, 2)}%",
        "",
        "## Issues",
        "",
    ]
    issues = report.get("issues", [])
    if not issues:
        lines.append("- none")
    else:
        for issue in issues:
            lines.append(f"- [{issue['level']}] `{issue['path']}`: {issue['message']}")
    lines.extend(["", "## Decisions", ""])
    for decision in report.get("decisions", []):
        state = "approved" if decision.get("approved") else "rejected"
        reasons = "; ".join(decision.get("reasons", [])) or "normal"
        lines.append(f"- {state}: `{decision.get('mission_id')}` / `{decision.get('asset_id')}` / {reasons}")
    lines.extend(["", "## Recommendations", ""])
    for item in report.get("recommendations", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _validate_asset(asset: UavSpec, index: int) -> list[ScenarioIssue]:
    issues: list[ScenarioIssue] = []
    path = f"assets[{index}]:{asset.id}"
    if asset.cruise_speed_mps <= 0:
        issues.append(ScenarioIssue("error", path, "cruise_speed_mps must be greater than zero"))
    if asset.min_altitude_m > asset.max_altitude_m:
        issues.append(ScenarioIssue("error", path, "min_altitude_m must be less than or equal to max_altitude_m"))
    if asset.battery_capacity_wh <= 0:
        issues.append(ScenarioIssue("warning", path, "battery_capacity_wh should be greater than zero"))
    if not asset.datalink_profiles:
        issues.append(ScenarioIssue("error", path, "at least one datalink profile is required"))
    if asset.system_id <= 0 or asset.system_id > 255:
        issues.append(ScenarioIssue("error", path, "system_id must be in MAVLink range 1..255"))
    return issues


def _validate_mission(
    scenario: UasUtmScenario,
    mission: MissionSpec,
    index: int,
    asset: UavSpec | None,
) -> list[ScenarioIssue]:
    issues: list[ScenarioIssue] = []
    path = f"missions[{index}]:{mission.id}"
    if asset is None:
        issues.append(ScenarioIssue("error", path, f"unknown asset_id:{mission.asset_id}"))
        return issues
    if len(mission.route) < 2:
        issues.append(ScenarioIssue("error", path, "route must include at least two waypoints"))
    if mission.requested_end_s <= mission.requested_start_s:
        issues.append(ScenarioIssue("error", path, "requested_end_s must be after requested_start_s"))
    if mission.required_link not in asset.datalink_profiles:
        issues.append(ScenarioIssue("error", path, f"asset does not support required_link:{mission.required_link}"))
    missing_payloads = sorted(set(mission.required_payloads) - set(asset.sensor_payloads))
    for payload in missing_payloads:
        issues.append(ScenarioIssue("error", path, f"asset missing payload:{payload}"))
    if asset.endurance_s is not None and mission.requested_end_s - mission.requested_start_s > asset.endurance_s:
        issues.append(ScenarioIssue("error", path, "mission duration exceeds asset endurance"))
    for point_index, point in enumerate(mission.route):
        if point[2] < asset.min_altitude_m or point[2] > asset.max_altitude_m:
            issues.append(ScenarioIssue("error", f"{path}.route[{point_index}]", "waypoint altitude is outside asset operating envelope"))
    if scenario.c2_nodes and not _has_c2_path(scenario, asset, mission):
        issues.append(ScenarioIssue("error", path, f"no C2 node covers every waypoint for link:{mission.required_link}"))
    if _is_ground_asset(asset):
        issues.extend(_validate_ground_route(scenario, mission, path))
    return issues



def _validate_ground_route(scenario: UasUtmScenario, mission: MissionSpec, path: str) -> list[ScenarioIssue]:
    issues: list[ScenarioIssue] = []
    if mission.corridor_width_m > 50:
        issues.append(ScenarioIssue("warning", path, "UGV corridor_width_m should stay within a narrow ground route corridor"))
    ground_zones = _ground_corridor_zones(scenario.zones)
    if not ground_zones:
        issues.append(ScenarioIssue("error", path, "UGV mission requires an operating_area zone labelled as ground, UGV, convoy, or route corridor"))
        return issues
    for point_index, point in enumerate(mission.route):
        if abs(point[2]) > 5:
            issues.append(ScenarioIssue("error", f"{path}.route[{point_index}]", "UGV route waypoint altitude must remain near ground level"))
        if not any(_point_inside_zone_xy(point, zone) for zone in ground_zones):
            issues.append(ScenarioIssue("error", f"{path}.route[{point_index}]", "UGV route waypoint is outside declared ground corridor"))
    for left, right in zip(mission.route, mission.route[1:]):
        horizontal_distance = ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5
        if horizontal_distance > 400:
            issues.append(ScenarioIssue("warning", path, "UGV route segment exceeds 400m; add intermediate waypoints for road-constrained validation"))
    return issues


def _ground_corridor_zones(zones: list[AirspaceZone]) -> list[AirspaceZone]:
    result: list[AirspaceZone] = []
    for zone in zones:
        label = f"{zone.id} {zone.label}".lower()
        if zone.kind == "operating_area" and any(token in label for token in ("ground", "ugv", "convoy", "route")):
            result.append(zone)
    return result


def _point_inside_zone_xy(point: Position, zone: AirspaceZone) -> bool:
    return zone.x_min <= point[0] <= zone.x_max and zone.y_min <= point[1] <= zone.y_max


def _is_ground_asset(asset: UavSpec) -> bool:
    platform = asset.platform_class.lower()
    return "ugv" in platform or "ground" in platform or "rover" in platform

def _has_c2_path(scenario: UasUtmScenario, asset: UavSpec, mission: MissionSpec) -> bool:
    for point in mission.route:
        if not any(
            mission.required_link in node.supported_links
            and mission.required_link in asset.datalink_profiles
            and distance(point, node.location) <= node.coverage_radius_m
            for node in scenario.c2_nodes
        ):
            return False
    return True


def _duplicate_id_issues(kind: str, values: list[str]) -> list[ScenarioIssue]:
    issues: list[ScenarioIssue] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    for value in sorted(duplicates):
        issues.append(ScenarioIssue("error", kind, f"duplicate id:{value}"))
    return issues


def _issue_counts(issues: list[ScenarioIssue]) -> dict[str, int]:
    return {
        "error": sum(1 for issue in issues if issue.level == "error"),
        "warning": sum(1 for issue in issues if issue.level == "warning"),
    }


def _recommendations(scenario: UasUtmScenario, issues: list[ScenarioIssue], summary: dict[str, Any]) -> list[str]:
    items: list[str] = []
    if any("ugv" in asset.platform_class.lower() for asset in scenario.assets):
        items.append("UGV assets are present; include ground route and C2 evidence in DAH scenario notes.")
    if summary.get("link_coverage_rate", 0) < 0.95:
        items.append("Link coverage is below 95%; adjust C2 node radius or mission route before using as baseline.")
    if any(issue.level == "error" for issue in issues):
        items.append("Resolve error-level issues before using this scenario as a normal-operation baseline.")
    if not items:
        items.append("Scenario is ready for normal-operation baseline export.")
    return items