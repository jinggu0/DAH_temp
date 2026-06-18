from __future__ import annotations

import random
from collections.abc import Iterable

from .models import AttackEvent, Position, TelemetryMutation


def active_attacks(attacks: Iterable[AttackEvent], asset_id: str, time_s: int) -> list[AttackEvent]:
    return [
        attack
        for attack in attacks
        if attack.asset_id == asset_id and attack.start_s <= time_s <= attack.end_s
    ]


def apply_attacks(
    *,
    attack_events: Iterable[AttackEvent],
    time_s: int,
    true_position: Position,
    nominal_target: Position,
    command_target: Position,
    rng: random.Random,
) -> TelemetryMutation:
    reported_position = true_position
    mutated_command_target = command_target
    link_ok = True
    active_ids: list[str] = []

    for attack in attack_events:
        active_ids.append(attack.id)
        if attack.kind == "gps_spoof":
            drift = _position_param(attack, "drift_mps", default=(0.0, 0.0, 0.0))
            elapsed_s = max(0, time_s - attack.start_s + 1)
            reported_position = (
                true_position[0] + drift[0] * elapsed_s,
                true_position[1] + drift[1] * elapsed_s,
                true_position[2] + drift[2] * elapsed_s,
            )
        elif attack.kind == "command_injection":
            mutated_command_target = _position_param(attack, "target", default=nominal_target)
        elif attack.kind == "link_jam":
            drop_probability = float(attack.params.get("drop_probability", 1.0))
            link_ok = rng.random() >= drop_probability
        else:
            raise ValueError(f"unsupported attack kind: {attack.kind}")

    return TelemetryMutation(
        reported_position=reported_position,
        command_target=mutated_command_target,
        link_ok=link_ok,
        active_attack_ids=active_ids,
    )


def _position_param(
    attack: AttackEvent,
    key: str,
    *,
    default: Position,
) -> Position:
    raw_value = attack.params.get(key, default)
    if not isinstance(raw_value, list | tuple) or len(raw_value) != 3:
        raise ValueError(f"{attack.id}.{key} must be a 3-value position")
    return (float(raw_value[0]), float(raw_value[1]), float(raw_value[2]))
