from __future__ import annotations

from .models import AirspaceZone, MissionSpec, Position, UavSpec


def validate_mission_airspace(
    *,
    asset: UavSpec,
    mission: MissionSpec,
    zones: list[AirspaceZone],
) -> list[str]:
    reasons: list[str] = []
    if len(mission.route) < 2:
        reasons.append("mission route must include at least two waypoints")
        return reasons

    for index, point in enumerate(mission.route):
        altitude = point[2]
        if altitude < asset.min_altitude_m or altitude > asset.max_altitude_m:
            reasons.append(
                f"waypoint {index} altitude {altitude:.1f}m is outside asset limit "
                f"{asset.min_altitude_m:.1f}-{asset.max_altitude_m:.1f}m"
            )
        for zone in zones:
            if zone.kind == "operating_area":
                continue
            if point_inside_zone(point, zone) and _altitude_overlaps(point[2], zone):
                reasons.append(f"waypoint {index} enters {zone.kind}:{zone.id}")

    for start, end in zip(mission.route, mission.route[1:]):
        for zone in zones:
            if zone.kind == "operating_area":
                continue
            if segment_crosses_zone(start, end, zone):
                reasons.append(f"route segment crosses {zone.kind}:{zone.id}")

    operating_zones = [zone for zone in zones if zone.kind == "operating_area"]
    if operating_zones:
        for index, point in enumerate(mission.route):
            if not any(point_inside_zone(point, zone) for zone in operating_zones):
                reasons.append(f"waypoint {index} is outside operating area")

    return sorted(set(reasons))


def point_inside_zone(point: Position, zone: AirspaceZone) -> bool:
    return zone.x_min <= point[0] <= zone.x_max and zone.y_min <= point[1] <= zone.y_max


def segment_crosses_zone(start: Position, end: Position, zone: AirspaceZone) -> bool:
    sample_count = 24
    for sample_index in range(sample_count + 1):
        ratio = sample_index / sample_count
        point = (
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
            start[2] + (end[2] - start[2]) * ratio,
        )
        if point_inside_zone(point, zone) and _altitude_overlaps(point[2], zone):
            return True
    return False


def _altitude_overlaps(altitude_m: float, zone: AirspaceZone) -> bool:
    return zone.min_altitude_m <= altitude_m <= zone.max_altitude_m
