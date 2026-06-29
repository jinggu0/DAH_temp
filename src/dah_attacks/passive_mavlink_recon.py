# -*- coding: utf-8 -*-
"""Passive MAVLink Recon: Low-Privilege Sentinel.

This scenario is a controlled DAH adversary-emulation module. It does not use
raw sockets, CAP_NET_RAW, packet injection, ARP manipulation, or exploit code.
It demonstrates what a low-privilege observer can infer from plaintext
broadcast MAVLink telemetry, then maps the observations to blue-team controls.
"""
from __future__ import annotations

import argparse
import json
import math
import socket
import time
from typing import Any

from uas_utm_gateway.mavlink_parser import ParsedMavlinkFrame, parse_datagram

LISTEN_PORT = 14549
LISTEN_HOST = "0.0.0.0"

CONF_HIGH = 0.80
CONF_MEDIUM = 0.50

MAV_TYPE = {
    0: "GENERIC",
    2: "QUADROTOR",
    10: "GROUND_ROVER",
    14: "ONBOARD_CONTROLLER",
    27: "ADSB",
}
MAV_STATE = {
    0: "UNINIT",
    1: "BOOT",
    2: "CALIBRATING",
    3: "STANDBY",
    4: "ACTIVE",
    5: "CRITICAL",
    6: "EMERGENCY",
    7: "POWEROFF",
}
COMMAND_ACK_RESULT = {
    0: "ACCEPTED",
    1: "TEMP_REJECTED",
    2: "DENIED",
    3: "UNSUPPORTED",
    4: "FAILED",
    5: "IN_PROGRESS",
}
MISSION_ACK_TYPE = {
    0: "ACCEPTED",
    1: "ERROR",
    2: "UNSUPPORTED_FRAME",
    3: "UNSUPPORTED",
    4: "NO_SPACE",
    5: "INVALID",
    6: "INVALID_PARAM1",
    13: "OPERATION_CANCELLED",
}
COMMAND_NAMES = {
    16: "MAV_CMD_NAV_WAYPOINT",
    20: "MAV_CMD_NAV_RETURN_TO_LAUNCH",
    21: "MAV_CMD_NAV_LAND",
    176: "MAV_CMD_DO_SET_MODE",
    193: "MAV_CMD_DO_PAUSE_CONTINUE",
}


def _add_unique(values: list[Any], value: Any, limit: int = 20) -> None:
    if value is None or value in values:
        return
    values.append(value)
    if len(values) > limit:
        del values[0]


def _meters_per_lon_degree(lat_deg: float) -> float:
    return max(1.0, 111_320.0 * math.cos(math.radians(lat_deg)))


def _speed_from_positions(prev: dict[str, Any], cur: dict[str, Any]) -> float | None:
    dt = float(cur.get("received_s", 0.0)) - float(prev.get("received_s", 0.0))
    if dt <= 0.05:
        return None
    lat = float(prev["lat_deg"])
    north_m = (float(cur["lat_deg"]) - lat) * 111_320.0
    east_m = (float(cur["lon_deg"]) - float(prev["lon_deg"])) * _meters_per_lon_degree(lat)
    return math.sqrt(north_m * north_m + east_m * east_m) / dt


def _physical_consistency_check(rec: dict[str, Any]) -> bool:
    samples = rec.get("position_history", [])
    if len(samples) < 2:
        return False
    calculated = _speed_from_positions(samples[-2], samples[-1])
    reported = rec.get("ground_speed_mps")
    if calculated is None or reported is None:
        return False
    if calculated < 0.3 and float(reported) < 0.8:
        return True
    if calculated <= 0 or float(reported) <= 0:
        return False
    ratio = max(calculated, float(reported)) / max(0.01, min(calculated, float(reported)))
    return ratio < 3.0


def _cross_message_validation(rec: dict[str, Any]) -> bool:
    if rec.get("is_armed") and rec.get("alt_m", 0) < -10:
        return False
    if rec.get("system_status") == "ACTIVE" and rec.get("position_samples", 0) == 0:
        return False
    if rec.get("battery_pct", 50) is not None and rec.get("battery_pct", 50) < -1:
        return False
    return bool(rec.get("last_heartbeat") or rec.get("position_samples", 0) > 0)


def _frame_integrity_factor(rec: dict[str, Any]) -> tuple[float, str]:
    invalid = int(rec.get("crc_invalid_frames", 0))
    valid = int(rec.get("crc_valid_frames", 0))
    unknown = int(rec.get("crc_unknown_frames", 0))
    if invalid > 0:
        return 0.0, f"crc_invalid={invalid}"
    if valid > 0:
        return 0.15, f"crc_valid={valid}"
    if unknown > 0:
        return 0.08, f"crc_unknown={unknown}"
    return 0.0, "no_crc_metadata"


def confidence_details(rec: dict[str, Any], now_s: float | None = None) -> dict[str, Any]:
    now = time.time() if now_s is None else now_s
    factors: dict[str, dict[str, Any]] = {}

    repeated = rec.get("packet_count", 0) >= 3
    factors["message_repetition"] = {"ok": repeated, "weight": 0.20 if repeated else 0.0}

    position_ok = rec.get("position_samples", 0) >= 2
    factors["position_repetition"] = {"ok": position_ok, "weight": 0.15 if position_ok else 0.0}

    physical_ok = _physical_consistency_check(rec)
    factors["physical_consistency"] = {"ok": physical_ok, "weight": 0.25 if physical_ok else 0.0}

    cross_ok = _cross_message_validation(rec)
    factors["cross_message_validation"] = {"ok": cross_ok, "weight": 0.15 if cross_ok else 0.0}

    integrity_weight, integrity_note = _frame_integrity_factor(rec)
    factors["frame_integrity"] = {"ok": integrity_weight > 0, "weight": integrity_weight, "note": integrity_note}

    last_seen = rec.get("last_seen")
    fresh = bool(last_seen and now - float(last_seen) <= 90.0)
    factors["freshness"] = {"ok": fresh, "weight": 0.10 if fresh else 0.0}

    score = round(sum(item["weight"] for item in factors.values()), 2)
    return {"score": min(1.0, score), "label": confidence_label(score), "factors": factors}


def confidence_score(rec: dict[str, Any]) -> float:
    return float(confidence_details(rec)["score"])


def confidence_label(score: float) -> str:
    if score >= CONF_HIGH:
        return "HIGH - usable as a follow-on scenario candidate"
    if score >= CONF_MEDIUM:
        return "MEDIUM - revalidation recommended"
    return "LOW - possible delay/spoofing/incomplete observation"


class IntelligenceReport:
    def __init__(self) -> None:
        self.assets: dict[int, dict[str, Any]] = {}
        self.packet_count = 0
        self.parse_errors = 0
        self.unknown_msg_count = 0
        self.msg_type_counts: dict[str, int] = {}
        self.signed_frames = 0
        self.unsigned_frames = 0
        self.crc_valid_frames = 0
        self.crc_invalid_frames = 0
        self.crc_unknown_frames = 0
        self.start_time = time.time()
        self.last_packet_time: float | None = None

    def _get(self, sys_id: int) -> dict[str, Any]:
        if sys_id not in self.assets:
            self.assets[sys_id] = {
                "sys_id": sys_id,
                "first_seen": time.time(),
                "last_seen": None,
                "packet_count": 0,
                "source_ips": [],
                "message_counts": {},
                "position_history": [],
                "command_acks": [],
                "mission_items": [],
            }
        return self.assets[sys_id]

    def record_frame(self, frame: ParsedMavlinkFrame, source_ip: str) -> dict[str, Any]:
        rec = self._get(frame.system_id)
        rec["packet_count"] += 1
        rec["last_seen"] = time.time()
        rec["component_id"] = frame.component_id
        rec["last_sequence"] = frame.sequence
        rec["last_message"] = frame.message_name
        rec["signed_frames"] = rec.get("signed_frames", 0) + (1 if frame.signed else 0)
        rec["unsigned_frames"] = rec.get("unsigned_frames", 0) + (0 if frame.signed else 1)
        if frame.crc_valid is True:
            rec["crc_valid_frames"] = rec.get("crc_valid_frames", 0) + 1
        elif frame.crc_valid is False:
            rec["crc_invalid_frames"] = rec.get("crc_invalid_frames", 0) + 1
        else:
            rec["crc_unknown_frames"] = rec.get("crc_unknown_frames", 0) + 1
        _add_unique(rec["source_ips"], source_ip)
        counts = rec["message_counts"]
        counts[frame.message_name] = counts.get(frame.message_name, 0) + 1
        return rec

    def record_msg_type(self, name: str) -> None:
        self.msg_type_counts[name] = self.msg_type_counts.get(name, 0) + 1

    def record_frame_security(self, frame: ParsedMavlinkFrame) -> None:
        if frame.signed:
            self.signed_frames += 1
        else:
            self.unsigned_frames += 1
        if frame.crc_valid is True:
            self.crc_valid_frames += 1
        elif frame.crc_valid is False:
            self.crc_invalid_frames += 1
        else:
            self.crc_unknown_frames += 1

    def update_heartbeat(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["mav_type"] = MAV_TYPE.get(fields.get("type", -1), f"TYPE_{fields.get('type')}")
        rec["system_status"] = MAV_STATE.get(fields.get("system_status", -1), "UNKNOWN")
        rec["base_mode"] = fields.get("base_mode", 0)
        rec["is_armed"] = bool(fields.get("base_mode", 0) & 0x80)
        rec["is_guided"] = bool(fields.get("base_mode", 0) & 0x08)
        rec["last_heartbeat"] = time.time()

    def update_position(self, sys_id: int, fields: dict[str, Any], *, message_name: str) -> None:
        rec = self._get(sys_id)
        lat = fields.get("lat", 0) / 1e7
        lon = fields.get("lon", 0) / 1e7
        alt = fields.get("alt", 0) / 1000.0
        rel_alt = fields.get("relative_alt", fields.get("alt", 0)) / 1000.0
        vx = fields.get("vx", 0) / 100.0
        vy = fields.get("vy", 0) / 100.0
        vz = fields.get("vz", 0) / 100.0
        hdg = fields.get("hdg", 0) / 100.0
        sample = {
            "received_s": time.time(),
            "message": message_name,
            "time_boot_ms": fields.get("time_boot_ms"),
            "time_usec": fields.get("time"),
            "lat_deg": round(lat, 7),
            "lon_deg": round(lon, 7),
            "alt_m": round(alt, 1),
            "rel_alt_m": round(rel_alt, 1),
            "vx_mps": round(vx, 2),
            "vy_mps": round(vy, 2),
            "vz_mps": round(vz, 2),
            "heading_deg": round(hdg, 1),
        }
        rec.update({
            "lat_deg": sample["lat_deg"],
            "lon_deg": sample["lon_deg"],
            "alt_m": sample["alt_m"],
            "rel_alt_m": sample["rel_alt_m"],
            "velocity_mps": [sample["vx_mps"], sample["vy_mps"], sample["vz_mps"]],
            "ground_speed_mps": round(math.sqrt(vx ** 2 + vy ** 2), 2),
            "heading_deg": sample["heading_deg"],
            "position_samples": rec.get("position_samples", 0) + 1,
        })
        history = rec.setdefault("position_history", [])
        history.append(sample)
        if len(history) > 30:
            del history[0]
        rec["trail"] = [[p["lat_deg"], p["lon_deg"], p["alt_m"]] for p in history[-20:]]

    def update_sys_status(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["battery_pct"] = fields.get("battery_remaining", -1)
        rec["drop_rate_comm"] = fields.get("drop_rate_comm", 0)
        rec["errors_comm"] = fields.get("errors_comm", 0)

    def note_command_ack(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        acks = rec.setdefault("command_acks", [])
        command = fields.get("command")
        acks.append({
            "command": command,
            "command_name": COMMAND_NAMES.get(command, f"COMMAND_{command}"),
            "result": COMMAND_ACK_RESULT.get(fields.get("result", -1), f"RESULT_{fields.get('result')}"),
            "seen_s": time.time(),
        })
        if len(acks) > 10:
            del acks[0]

    def note_command_long(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        commands = rec.setdefault("command_long_seen", [])
        command = fields.get("command")
        commands.append({
            "command": command,
            "command_name": COMMAND_NAMES.get(command, f"COMMAND_{command}"),
            "target_system": fields.get("target_system"),
            "target_component": fields.get("target_component"),
            "seen_s": time.time(),
        })
        if len(commands) > 10:
            del commands[0]

    def note_mission_current(self, sys_id: int, fields: dict[str, Any]) -> None:
        self._get(sys_id)["mission_seq"] = fields.get("seq")

    def note_mission_count(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["mission_count"] = fields.get("count")
        rec["mission_upload_in_progress"] = True

    def note_mission_ack(self, sys_id: int, fields: dict[str, Any]) -> None:
        self._get(sys_id)["last_mission_ack"] = MISSION_ACK_TYPE.get(fields.get("type", -1), f"ACK_{fields.get('type')}")

    def note_mission_request(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["mission_upload_in_progress"] = True
        rec["mission_upload_seq"] = fields.get("seq")

    def note_mission_item(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        items = rec.setdefault("mission_items", [])
        items.append({
            "seq": fields.get("seq"),
            "command": fields.get("command"),
            "x": fields.get("x"),
            "y": fields.get("y"),
            "z": fields.get("z"),
        })
        if len(items) > 10:
            del items[0]

    def sanitized_assets(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for sid, rec in self.assets.items():
            clean = dict(rec)
            result[str(sid)] = clean
        return result

    def attack_value_map(self, prediction_horizon_s: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for sid, rec in sorted(self.assets.items()):
            confidence = confidence_details(rec)
            result[f"sys_{sid}"] = {
                "platform": rec.get("mav_type", "UNKNOWN"),
                "armed": rec.get("is_armed"),
                "position": {
                    "lat": rec.get("lat_deg"),
                    "lon": rec.get("lon_deg"),
                    "alt_m": rec.get("alt_m"),
                },
                "speed_mps": rec.get("ground_speed_mps"),
                "heading": rec.get("heading_deg"),
                "battery_pct": rec.get("battery_pct"),
                "mission_seq": rec.get("mission_seq"),
                "confidence": confidence,
                "movement_pattern": classify_pattern(rec),
                "prediction": predict_position(rec, prediction_horizon_s),
                "follow_on_candidates": follow_on_candidates(rec, float(confidence["score"])),
                "timing_recommendations": timing_recommendations(rec, float(confidence["score"])),
            }
        return result

    def summary(self) -> dict[str, Any]:
        return {
            "packet_count": self.packet_count,
            "parse_errors": self.parse_errors,
            "unknown_msgs": self.unknown_msg_count,
            "asset_count": len(self.assets),
            "msg_type_counts": dict(sorted(self.msg_type_counts.items())),
            "signed_frames": self.signed_frames,
            "unsigned_frames": self.unsigned_frames,
            "crc_valid_frames": self.crc_valid_frames,
            "crc_invalid_frames": self.crc_invalid_frames,
            "crc_unknown_frames": self.crc_unknown_frames,
        }

    def print_summary(self, phase: str) -> None:
        elapsed = time.time() - self.start_time
        print(f"\n{'=' * 72}")
        print(f"[PASSIVE-MAVLINK-RECON] {phase} complete")
        print(f"  elapsed_s:       {elapsed:.1f}")
        print(f"  packets:         {self.packet_count}")
        print(f"  parse_errors:    {self.parse_errors}")
        print(f"  assets:          {len(self.assets)}")
        print(f"  http_requests:   0")
        print(f"  msg_types:       {dict(sorted(self.msg_type_counts.items()))}")
        print(f"  frame_security:  signed={self.signed_frames} unsigned={self.unsigned_frames} crc_invalid={self.crc_invalid_frames}")
        print(f"{'=' * 72}")
        for sid, rec in sorted(self.assets.items()):
            confidence = confidence_details(rec)
            print(
                f"  [SYS_ID={sid}] {rec.get('mav_type', 'UNKNOWN')} "
                f"state={rec.get('system_status', 'UNKNOWN')} "
                f"armed={'Y' if rec.get('is_armed') else 'N'} "
                f"confidence={confidence['score']:.2f}"
            )
            if "lat_deg" in rec:
                print(
                    f"    pos={rec['lat_deg']},{rec['lon_deg']} alt={rec.get('alt_m')}m "
                    f"speed={rec.get('ground_speed_mps')}m/s heading={rec.get('heading_deg')}deg"
                )
            if rec.get("battery_pct", -1) >= 0:
                print(f"    battery={rec['battery_pct']}% link_loss={rec.get('drop_rate_comm', 0) / 100:.1f}%")
            print(f"    pattern={classify_pattern(rec)} candidates={follow_on_candidates(rec, float(confidence['score']))}")


def classify_pattern(rec: dict[str, Any]) -> str:
    samples = rec.get("position_history", [])
    speed = float(rec.get("ground_speed_mps") or 0.0)
    if rec.get("mission_upload_in_progress"):
        return "MISSION_UPLOAD_ACTIVITY"
    if rec.get("command_acks") or rec.get("command_long_seen"):
        return "COMMAND_ACTIVITY"
    if len(samples) >= 3:
        alt_delta = samples[-1]["alt_m"] - samples[0]["alt_m"]
        heading_values = [float(s.get("heading_deg") or 0.0) for s in samples[-5:]]
        heading_span = max(heading_values) - min(heading_values) if heading_values else 0.0
        if alt_delta < -8 and speed < 8:
            return "DESCENT_OR_RTL"
        if heading_span > 35:
            return "PATROL_TURNING"
    if speed < 0.7 and rec.get("position_samples", 0) >= 2:
        return "HOLDING"
    if rec.get("mission_seq") is not None:
        return "MISSION_PROGRESS"
    if rec.get("position_samples", 0):
        return "TRANSIT"
    return "INSUFFICIENT_DATA"


def predict_position(rec: dict[str, Any], horizon_s: int) -> dict[str, Any] | None:
    if rec.get("lat_deg") is None or rec.get("lon_deg") is None or not rec.get("velocity_mps"):
        return None
    lat = float(rec["lat_deg"])
    lon = float(rec["lon_deg"])
    alt = float(rec.get("alt_m") or 0.0)
    vx_north, vy_east, vz_down = [float(v) for v in rec.get("velocity_mps", [0.0, 0.0, 0.0])]
    pred_lat = lat + (vx_north * horizon_s) / 111_320.0
    pred_lon = lon + (vy_east * horizon_s) / _meters_per_lon_degree(lat)
    pred_alt = alt - vz_down * horizon_s
    pattern = classify_pattern(rec)
    maneuver_penalty = 30.0 if pattern in {"PATROL_TURNING", "DESCENT_OR_RTL", "COMMAND_ACTIVITY"} else 0.0
    base_error = 15.0 + 0.35 * horizon_s + maneuver_penalty
    return {
        "model": "constant_velocity_short_horizon",
        "horizon_s": horizon_s,
        "lat": round(pred_lat, 7),
        "lon": round(pred_lon, 7),
        "alt_m": round(pred_alt, 1),
        "expected_error_m": round(base_error, 1),
        "limits": "Use for short-window scenario selection only; revalidate before follow-on actions.",
    }


def follow_on_candidates(rec: dict[str, Any], score: float) -> list[str]:
    if score < CONF_MEDIUM:
        return []
    candidates: list[str] = []
    if rec.get("lat_deg") is not None:
        candidates.extend(["GNSS-DRIFT(S01)", "DYNAMIC-SPOOF(S03)", "GEOFENCE-INJECT(S17)"])
    if rec.get("battery_pct", -1) >= 0:
        candidates.append("BATTERY-CRISIS(S10)")
    if rec.get("is_armed"):
        candidates.append("COMMAND-STATE-REVIEW(S05)")
    if rec.get("drop_rate_comm", 0) > 100:
        candidates.append("LINK-DEGRADE-ASSESSMENT(S02)")
    if rec.get("mission_seq") is not None or rec.get("mission_upload_in_progress"):
        candidates.append("MISSION-FLOW-ANALYSIS")
    return candidates


def timing_recommendations(rec: dict[str, Any], score: float) -> list[dict[str, str]]:
    if score < CONF_MEDIUM:
        return [{"status": "hold", "reason": "confidence below medium threshold; revalidation required"}]
    pattern = classify_pattern(rec)
    if pattern == "HOLDING":
        return [{"candidate": "FDI/GEOFENCE analysis", "reason": "low motion reduces immediate kinematic inconsistency"}]
    if pattern == "PATROL_TURNING":
        return [{"candidate": "GNSS drift analysis", "reason": "turning behavior can mask small trajectory changes in evaluation"}]
    if pattern == "DESCENT_OR_RTL":
        return [{"candidate": "battery/link-state analysis", "reason": "operator workload is likely elevated during recovery or descent"}]
    if pattern == "MISSION_UPLOAD_ACTIVITY":
        return [{"candidate": "mission-flow monitoring", "reason": "mission transfer messages are visible and time-correlated"}]
    return [{"candidate": "short-window revalidation", "reason": "movement pattern is not distinctive enough for a strong timing claim"}]


def blue_team_mapping() -> list[dict[str, Any]]:
    return [
        {
            "layer": "GCS application audit log",
            "expected_visibility": "low",
            "reason": "the scenario sends no HTTP request and does not traverse GCS route handlers",
            "recommended_control": "correlate API audit gaps with network telemetry sensors",
        },
        {
            "layer": "Network IDS/firewall",
            "expected_visibility": "medium",
            "reason": "broadcast MAVLink packets on UDP 14549 can be observed; passive receivers are harder to attribute",
            "recommended_control": "alert on plaintext MAVLink broadcast domains and reduce broadcast scope",
        },
        {
            "layer": "Host EDR/eBPF",
            "expected_visibility": "medium-high",
            "reason": "low-privilege mode uses UDP bind/listen on 14549",
            "recommended_control": "monitor UDP bind events, process lineage, and socket lifetime",
        },
        {
            "layer": "Container runtime",
            "expected_visibility": "medium",
            "reason": "container start, command line, stdout, and volume writes are observable in the lab",
            "recommended_control": "restrict attack-profile containers and collect runtime metadata",
        },
        {
            "layer": "Protocol monitor",
            "expected_visibility": "high for exposure, low for receiver identity",
            "reason": "message type counts and unsigned/plaintext telemetry exposure are measurable",
            "recommended_control": "track MAVLink signing, CRC validity, and message exposure by segment",
        },
    ]


def ghost_sentinel_assessment() -> dict[str, Any]:
    return {
        "implemented": False,
        "purpose": "threat-model comparison only; no raw socket or CAP_NET_RAW behavior is executed by this module",
        "threat_actor": "insider/supply-chain/operator of a privileged sensor container",
        "would_reduce": ["UDP port 14549 bind table visibility"],
        "would_introduce": ["CAP_NET_RAW policy event", "AF_PACKET/packet socket telemetry", "/proc/net/packet visibility"],
        "defensive_question": "Can the environment detect privileged packet capture behavior, not just UDP port listeners?",
    }


def _handle_frame(report: IntelligenceReport, frame: ParsedMavlinkFrame, source_ip: str) -> None:
    report.record_frame_security(frame)
    report.record_msg_type(frame.message_name)
    report.record_frame(frame, source_ip)
    fields = frame.fields
    sid = frame.system_id
    name = frame.message_name
    if name == "HEARTBEAT":
        report.update_heartbeat(sid, fields)
    elif name in {"GLOBAL_POSITION_INT", "UTM_GLOBAL_POSITION"}:
        report.update_position(sid, fields, message_name=name)
    elif name == "SYS_STATUS":
        report.update_sys_status(sid, fields)
    elif name == "COMMAND_ACK":
        report.note_command_ack(sid, fields)
    elif name == "COMMAND_LONG":
        report.note_command_long(sid, fields)
    elif name == "MISSION_CURRENT":
        report.note_mission_current(sid, fields)
    elif name == "MISSION_COUNT":
        report.note_mission_count(sid, fields)
    elif name == "MISSION_ACK":
        report.note_mission_ack(sid, fields)
    elif name == "MISSION_REQUEST_INT":
        report.note_mission_request(sid, fields)
    elif name == "MISSION_ITEM_INT":
        report.note_mission_item(sid, fields)
    else:
        report.unknown_msg_count += 1


def _collect(sock: socket.socket, report: IntelligenceReport, deadline: float, phase_label: str) -> None:
    while time.time() < deadline:
        try:
            datagram, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError as exc:
            print(f"  [{phase_label}] socket error: {exc}", flush=True)
            break
        report.packet_count += 1
        report.last_packet_time = time.time()
        try:
            frames = parse_datagram(datagram)
        except Exception as exc:
            report.parse_errors += 1
            print(f"  [{phase_label}] parse error from {addr[0]} len={len(datagram)} err={exc}", flush=True)
            continue
        for item in frames:
            if not isinstance(item, ParsedMavlinkFrame):
                continue
            _handle_frame(report, item, addr[0])
            print(
                f"  [{phase_label}] {addr[0]} sys={item.system_id} msg={item.message_name} "
                f"signed={'Y' if item.signed else 'N'} crc={item.crc_valid}",
                flush=True,
            )


def _open_socket(listen_host: str, listen_port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
    sock.bind((listen_host, listen_port))
    sock.settimeout(1.0)
    return sock


def _merge_better_observations(primary: IntelligenceReport, secondary: IntelligenceReport) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for sid, new_rec in secondary.assets.items():
        old_rec = primary.assets.get(sid)
        if old_rec is None:
            primary.assets[sid] = new_rec
            changes.append({"sys_id": sid, "action": "added", "new_score": confidence_score(new_rec)})
            continue
        old_score = confidence_score(old_rec)
        new_score = confidence_score(new_rec)
        if new_score > old_score:
            old_rec.update(new_rec)
            changes.append({"sys_id": sid, "action": "improved", "old_score": old_score, "new_score": new_score})
        else:
            changes.append({"sys_id": sid, "action": "kept", "old_score": old_score, "new_score": new_score})
    return changes


def run(
    listen_host: str,
    listen_port: int,
    duration_s: int,
    revalidate_s: int,
    prediction_horizon_s: int,
    output_path: str | None,
) -> dict[str, Any]:
    report = IntelligenceReport()
    print("[passive-mavlink-recon] Low-Privilege Sentinel starting", flush=True)
    print(f"  listen={listen_host}:{listen_port} duration_s={duration_s} http_requests=0", flush=True)
    print("  scope=controlled DAH adversary emulation; no raw socket and no packet injection", flush=True)

    sock = _open_socket(listen_host, listen_port)
    _collect(sock, report, time.time() + duration_s, "phase1")
    sock.close()
    report.print_summary("phase1")

    revalidation_changes: list[dict[str, Any]] = []
    needs_revalidation = [sid for sid, rec in report.assets.items() if confidence_score(rec) < CONF_HIGH]
    if revalidate_s > 0 and needs_revalidation:
        print(f"\n[passive-mavlink-recon] short-window revalidation for sys_ids={needs_revalidation}", flush=True)
        second = IntelligenceReport()
        sock2 = _open_socket(listen_host, listen_port)
        _collect(sock2, second, time.time() + revalidate_s, "revalidate")
        sock2.close()
        revalidation_changes = _merge_better_observations(report, second)
        for change in revalidation_changes:
            print(f"  revalidation {change}", flush=True)
    elif revalidate_s > 0:
        print("\n[passive-mavlink-recon] revalidation skipped: all observed assets are high confidence", flush=True)

    intel = {
        "meta": {
            "attack": "passive_mavlink_recon",
            "scenario": "Low-Privilege Sentinel (strong recon emulation)",
            "threat_model": "low-privilege observer on a plaintext MAVLink broadcast segment",
            "duration_s": duration_s,
            "revalidate_s": revalidate_s,
            "prediction_horizon_s": prediction_horizon_s,
            "http_requests": 0,
            "gcs_audit_trace": False,
            "network_ids_visible": True,
            "raw_socket_used": False,
            "cap_net_raw_required": False,
        },
        "collection_summary": report.summary(),
        "assets": report.sanitized_assets(),
        "confidence": {
            str(sid): confidence_details(rec)
            for sid, rec in sorted(report.assets.items())
        },
        "attack_value": report.attack_value_map(prediction_horizon_s),
        "revalidation": revalidation_changes,
        "blue_team_mapping": blue_team_mapping(),
        "ghost_sentinel_comparison": ghost_sentinel_assessment(),
    }

    print("\n[passive-mavlink-recon] follow-on candidate summary", flush=True)
    for key, value in intel["attack_value"].items():
        print(
            f"  {key}: confidence={value['confidence']['score']:.2f} "
            f"pattern={value['movement_pattern']} candidates={value['follow_on_candidates']}",
            flush=True,
        )

    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(intel, handle, ensure_ascii=False, indent=2, default=str)
        print(f"\n[passive-mavlink-recon] result saved: {output_path}", flush=True)
    else:
        print("\n[passive-mavlink-recon] result JSON")
        print(json.dumps(intel, ensure_ascii=False, indent=2, default=str))
    return intel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Passive MAVLink Recon - Low-Privilege Sentinel strong recon emulation"
    )
    parser.add_argument("--listen-host", default=LISTEN_HOST)
    parser.add_argument("--listen-port", type=int, default=LISTEN_PORT)
    parser.add_argument("--duration-s", type=int, default=120)
    parser.add_argument("--revalidate-s", type=int, default=20)
    parser.add_argument("--prediction-horizon-s", type=int, default=60)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    run(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        duration_s=args.duration_s,
        revalidate_s=args.revalidate_s,
        prediction_horizon_s=args.prediction_horizon_s,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())