from __future__ import annotations

from .airspace import validate_mission_airspace
from .models import MissionSpec, UasUtmScenario, UtmDecision, distance


class UtmService:
    def __init__(self, scenario: UasUtmScenario):
        self.scenario = scenario
        self.assets = {asset.id: asset for asset in scenario.assets}

    def evaluate_missions(self) -> list[UtmDecision]:
        decisions: list[UtmDecision] = []
        approved: list[MissionSpec] = []

        for mission in sorted(self.scenario.missions, key=lambda item: item.requested_start_s):
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
        if mission.requested_end_s <= mission.requested_start_s:
            reasons.append("mission end time must be after start time")

        for approved in approved_missions:
            if _time_windows_overlap(mission, approved) and _routes_conflict(
                mission,
                approved,
                self.scenario.conflict_distance_m,
            ):
                reasons.append(f"trajectory conflicts with approved mission:{approved.id}")

        return sorted(set(reasons))


def _time_windows_overlap(left: MissionSpec, right: MissionSpec) -> bool:
    return left.requested_start_s <= right.requested_end_s and right.requested_start_s <= left.requested_end_s


def _routes_conflict(left: MissionSpec, right: MissionSpec, threshold_m: float) -> bool:
    for left_point in left.route:
        for right_point in right.route:
            if distance(left_point, right_point) <= threshold_m:
                return True
    return False
