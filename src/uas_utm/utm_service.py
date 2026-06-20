from __future__ import annotations

from .airspace import validate_mission_airspace
from .models import MissionSpec, UasUtmScenario, UavSpec, UtmDecision, distance


class UtmService:
    def __init__(self, scenario: UasUtmScenario):
        self.scenario = scenario
        self.assets = {asset.id: asset for asset in scenario.assets}

    def evaluate_missions(self) -> list[UtmDecision]:
        decisions: list[UtmDecision] = []
        approved: list[MissionSpec] = []

        for mission in sorted(self.scenario.missions, key=lambda item: (item.priority, item.requested_start_s)):
            reasons = self._evaluate_single_mission(mission, approved)
            decision = UtmDecision(
                mission_id=mission.id,
                asset_id=mission.asset_id,
                approved=not reasons,
                reasons=reasons,
            )
            decisions.append(decision)
            if decision.approved:
                approved.append(mission)

        return decisions

    def _evaluate_single_mission(
        self,
        mission: MissionSpec,
        approved_missions: list[MissionSpec],
    ) -> list[str]:
        asset = self.assets.get(mission.asset_id)
        if asset is None:
            return [f"unknown asset:{mission.asset_id}"]

        reasons = validate_mission_airspace(
            asset=asset,
            mission=mission,
            zones=self.scenario.zones,
        )
        reasons.extend(_validate_asset_capabilities(asset, mission))
        if mission.requested_end_s <= mission.requested_start_s:
            reasons.append("mission end time must be after start time")
        if not _has_c2_coverage(self.scenario, asset, mission):
            reasons.append(f"no C2 node supports required link:{mission.required_link}")

        for approved in approved_missions:
            if _time_windows_overlap(mission, approved) and _routes_conflict(
                mission,
                approved,
                max(self.scenario.conflict_distance_m, mission.corridor_width_m, approved.corridor_width_m),
            ):
                reasons.append(f"trajectory conflicts with approved mission:{approved.id}")

        return sorted(set(reasons))


def _validate_asset_capabilities(asset: UavSpec, mission: MissionSpec) -> list[str]:
    reasons: list[str] = []
    if mission.required_link not in asset.datalink_profiles:
        reasons.append(f"asset does not support required link:{mission.required_link}")
    missing_payloads = sorted(set(mission.required_payloads) - set(asset.sensor_payloads))
    for payload in missing_payloads:
        reasons.append(f"asset missing payload:{payload}")
    if asset.endurance_s is not None and mission.requested_end_s - mission.requested_start_s > asset.endurance_s:
        reasons.append("mission duration exceeds platform endurance")
    return reasons


def _time_windows_overlap(left: MissionSpec, right: MissionSpec) -> bool:
    return left.requested_start_s <= right.requested_end_s and right.requested_start_s <= left.requested_end_s


def _routes_conflict(left: MissionSpec, right: MissionSpec, threshold_m: float) -> bool:
    for left_point in left.route:
        for right_point in right.route:
            if distance(left_point, right_point) <= threshold_m:
                return True
    return False


def _has_c2_coverage(scenario: UasUtmScenario, asset: UavSpec, mission: MissionSpec) -> bool:
    if not scenario.c2_nodes:
        return True
    for point in mission.route:
        if not any(
            mission.required_link in node.supported_links
            and mission.required_link in asset.datalink_profiles
            and distance(point, node.location) <= node.coverage_radius_m
            for node in scenario.c2_nodes
        ):
            return False
    return True
