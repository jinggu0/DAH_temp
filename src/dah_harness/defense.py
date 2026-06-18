from __future__ import annotations

from dataclasses import dataclass, field

from .models import DefenseAction, DefenseConfig, Position, TelemetryFrame, distance


@dataclass
class AssetDefenseState:
    last_reported_position: Position | None = None
    link_loss_started_s: int | None = None
    anomaly_score: int = 0
    open_conditions: set[str] = field(default_factory=set)


class DefenseAgent:
    def __init__(self, config: DefenseConfig):
        self.config = config
        self._states: dict[str, AssetDefenseState] = {}

    def observe(self, frame: TelemetryFrame) -> list[DefenseAction]:
        state = self._states.setdefault(frame.asset_id, AssetDefenseState())
        reasons: list[str] = []

        if frame.reported_position is not None:
            if state.last_reported_position is not None:
                jump_m = distance(state.last_reported_position, frame.reported_position)
                if jump_m >= self.config.gps_jump_threshold_m:
                    reasons.append(f"gps_jump:{jump_m:.1f}m")
            deviation_m = distance(frame.expected_position, frame.reported_position)
            if deviation_m >= self.config.route_deviation_threshold_m:
                reasons.append(f"route_deviation:{deviation_m:.1f}m")
            state.last_reported_position = frame.reported_position

        command_deviation_m = distance(frame.nominal_target, frame.command_target)
        if command_deviation_m >= self.config.command_deviation_threshold_m:
            reasons.append(f"command_deviation:{command_deviation_m:.1f}m")

        if frame.link_ok:
            state.link_loss_started_s = None
        else:
            if state.link_loss_started_s is None:
                state.link_loss_started_s = frame.time_s
            link_loss_s = frame.time_s - state.link_loss_started_s + 1
            if link_loss_s >= self.config.link_loss_threshold_s:
                reasons.append(f"link_loss:{link_loss_s}s")

        if not reasons:
            state.open_conditions.clear()
            return []

        state.anomaly_score += len(reasons)
        actions: list[DefenseAction] = []
        current_conditions: set[str] = set()
        for reason in reasons:
            action_type = _action_for_reason(reason, state.anomaly_score, self.config)
            reason_key = reason.split(":", 1)[0]
            condition_key = f"{action_type}:{reason_key}"
            current_conditions.add(condition_key)
            if condition_key in state.open_conditions:
                continue
            actions.append(
                DefenseAction(
                    time_s=frame.time_s,
                    asset_id=frame.asset_id,
                    action_type=action_type,
                    reason=reason,
                    active_attack_ids=frame.active_attack_ids,
                )
            )
        state.open_conditions = current_conditions
        return actions


def _action_for_reason(reason: str, score: int, config: DefenseConfig) -> str:
    if score >= config.quarantine_score_threshold:
        return "quarantine_asset_channel"
    if reason.startswith("command_deviation"):
        return "reject_command"
    if reason.startswith("link_loss"):
        return "enter_failsafe"
    if reason.startswith("gps") or reason.startswith("route"):
        return "hold_position"
    return "raise_alert"
