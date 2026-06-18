from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .attacks import active_attacks, apply_attacks
from .defense import DefenseAgent
from .models import (
    AssetKind,
    AssetSpec,
    AttackEvent,
    DefenseConfig,
    Position,
    Scenario,
    SimulationResult,
    TelemetryFrame,
    distance,
    move_toward,
)


@dataclass
class RuntimeAssetState:
    spec: AssetSpec
    true_position: Position
    expected_position: Position
    waypoint_index: int = 0


def load_scenario(path: Path) -> Scenario:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assets = [_parse_asset(item) for item in raw["assets"]]
    attacks = [_parse_attack(item) for item in raw.get("attacks", [])]
    defense = DefenseConfig(**raw.get("defense", {}))
    metric = raw.get("metric", {})
    return Scenario(
        name=str(raw["name"]),
        description=str(raw.get("description", "")),
        duration_s=int(raw["duration_s"]),
        step_s=int(raw.get("step_s", 1)),
        seed=int(raw.get("seed", 0)),
        assets=assets,
        attacks=attacks,
        defense=defense,
        metric_detection_grace_s=int(metric.get("detection_grace_s", 5)),
    )


def run_scenario(scenario: Scenario) -> SimulationResult:
    rng = random.Random(scenario.seed)
    defense_agent = DefenseAgent(scenario.defense)
    states = {
        asset.id: RuntimeAssetState(
            spec=asset,
            true_position=asset.start,
            expected_position=asset.start,
        )
        for asset in scenario.assets
    }
    frames: list[TelemetryFrame] = []
    actions = []

    for time_s in range(0, scenario.duration_s + 1, scenario.step_s):
        for state in states.values():
            frame = _step_asset(
                state=state,
                scenario=scenario,
                time_s=time_s,
                rng=rng,
            )
            frames.append(frame)
            actions.extend(defense_agent.observe(frame))

    return SimulationResult(scenario=scenario, frames=frames, actions=actions)


def _step_asset(
    *,
    state: RuntimeAssetState,
    scenario: Scenario,
    time_s: int,
    rng: random.Random,
) -> TelemetryFrame:
    nominal_target = _current_nominal_target(state)
    attacks = active_attacks(scenario.attacks, state.spec.id, time_s)
    mutation = apply_attacks(
        attack_events=attacks,
        time_s=time_s,
        true_position=state.true_position,
        nominal_target=nominal_target,
        command_target=nominal_target,
        rng=rng,
    )

    # The expected position follows the clean mission plan, while true_position follows
    # the command target after command-channel mutation.
    state.expected_position = move_toward(
        state.expected_position,
        nominal_target,
        state.spec.nominal_speed_mps * scenario.step_s,
    )
    state.true_position = move_toward(
        state.true_position,
        mutation.command_target,
        state.spec.nominal_speed_mps * scenario.step_s,
    )
    if distance(state.true_position, nominal_target) <= 1.0:
        state.waypoint_index = min(state.waypoint_index + 1, len(state.spec.waypoints) - 1)

    return TelemetryFrame(
        time_s=time_s,
        asset_id=state.spec.id,
        asset_kind=state.spec.kind,
        true_position=_round_position(state.true_position),
        expected_position=_round_position(state.expected_position),
        reported_position=_round_position(mutation.reported_position) if mutation.reported_position else None,
        nominal_target=_round_position(nominal_target),
        command_target=_round_position(mutation.command_target),
        link_ok=mutation.link_ok,
        active_attack_ids=mutation.active_attack_ids,
    )


def _current_nominal_target(state: RuntimeAssetState) -> Position:
    if not state.spec.waypoints:
        return state.spec.start
    return state.spec.waypoints[min(state.waypoint_index, len(state.spec.waypoints) - 1)]


def _parse_asset(raw: dict[str, Any]) -> AssetSpec:
    return AssetSpec(
        id=str(raw["id"]),
        kind=_parse_asset_kind(raw["kind"]),
        start=_parse_position(raw["start"]),
        waypoints=[_parse_position(item) for item in raw.get("waypoints", [])],
        nominal_speed_mps=float(raw["nominal_speed_mps"]),
    )


def _parse_attack(raw: dict[str, Any]) -> AttackEvent:
    return AttackEvent(
        id=str(raw["id"]),
        asset_id=str(raw["asset_id"]),
        kind=str(raw["kind"]),
        start_s=int(raw["start_s"]),
        end_s=int(raw["end_s"]),
        params=dict(raw.get("params", {})),
    )


def _parse_asset_kind(value: Any) -> AssetKind:
    if value not in {"UAV", "UGV"}:
        raise ValueError(f"asset kind must be UAV or UGV, got {value!r}")
    return value


def _parse_position(value: Any) -> Position:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError(f"position must be [x, y, z], got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


def _round_position(position: Position) -> Position:
    return (round(position[0], 3), round(position[1], 3), round(position[2], 3))
