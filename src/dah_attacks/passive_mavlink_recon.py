# -*- coding: utf-8 -*-
"""Passive MAVLink Recon — Low-Privilege Sentinel (시나리오 11).

브로드캐스트 MAVLink v2 텔레메트리를 수신 전용으로 관측하여
위치, 상태, 배터리, sys_id 등 후속 시나리오 초기화에 필요한
전술 텔레메트리를 수집한다.

[탐지 범위 정의]
  - GCS 애플리케이션 감사로그(JSONL audit trail):
      UDP 수신은 GCS route handler를 통과하지 않으므로 기록 없음.
  - 네트워크 IDS / 방화벽:
      브로드캐스트 송출은 관측되나 수신자 IP 특정 어렵다.
  - 호스트 EDR / eBPF:
      UDP bind(14549) 이벤트 포착 가능.
  - 컨테이너 런타임:
      프로세스 실행 기록 존재. 공격자가 제어하는 영역.
  탐지 책임: GCS 앱 로그 단독으로는 수신자 식별 어려움.
  완전한 탐지는 네트워크 센서 + EDR/eBPF 복합 배포 필요.
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

_MAV_TYPE = {
    0:  "GENERIC",
    2:  "QUADROTOR",
    10: "GROUND_ROVER",
    14: "ONBOARD_CONTROLLER",
    27: "ADSB",
}
_MAV_STATE = {
    0: "UNINIT", 1: "BOOT", 2: "CALIBRATING",
    3: "STANDBY", 4: "ACTIVE", 5: "CRITICAL",
    6: "EMERGENCY", 7: "POWEROFF",
}
_COMMAND_ACK_RESULT = {
    0: "ACCEPTED", 1: "TEMP_REJECTED", 2: "DENIED",
    3: "UNSUPPORTED", 4: "FAILED", 5: "IN_PROGRESS",
}
_MISSION_ACK_TYPE = {
    0: "ACCEPTED", 1: "ERROR", 2: "UNSUPPORTED_FRAME",
    3: "UNSUPPORTED", 4: "NO_SPACE", 5: "INVALID",
    6: "INVALID_PARAM1", 13: "OPERATION_CANCELLED",
}


# ── 신뢰도 점수 기준 ──────────────────────────────────────────────────────────
_CONF_HIGH   = 0.8   # 고신뢰 관측 — 후속 시나리오 후보로 사용 가능
_CONF_MEDIUM = 0.5   # 재검증 필요
# < 0.5: 지연/스푸핑/불완전 관측 의심


def _physical_consistency_check(rec: dict[str, Any]) -> bool:
    """보고된 속도와 위치 변화에서 산출한 속도가 물리적으로 일관적인지 확인."""
    trail = rec.get("trail", [])
    if len(trail) < 2:
        return False
    p1, p2 = trail[-2], trail[-1]
    dlat = (p2[0] - p1[0]) * 111_320
    dlon = (p2[1] - p1[1]) * 88_800 * math.cos(math.radians(p1[0]))
    calc_speed = math.sqrt(dlat ** 2 + dlon ** 2)   # 1초 간격 가정
    reported = rec.get("ground_speed_mps", 0.0)
    if reported > 0.5 and calc_speed > 0.1:
        ratio = max(reported, calc_speed) / min(reported, calc_speed)
        return ratio < 3.0
    return True


def _cross_message_validation(rec: dict[str, Any]) -> bool:
    """HEARTBEAT와 GLOBAL_POSITION_INT 간 상태 일관성 확인."""
    # 무장 상태인데 고도가 비정상적으로 음수
    if rec.get("is_armed") and rec.get("alt_m", 0) < -10:
        return False
    # ACTIVE 상태인데 위치 관측이 전혀 없음
    if rec.get("system_status") == "ACTIVE" and rec.get("position_samples", 0) == 0:
        return False
    return True


def confidence_score(rec: dict[str, Any]) -> float:
    """자산 관측 레코드에 대한 신뢰도 점수 산출 (0.0 ~ 1.0).

    채점 기준:
      0.25 — 메시지 반복성:    동일 sys_id 3회 이상 수신
      0.20 — 위치 샘플 충분성: GLOBAL_POSITION_INT 2회 이상
      0.30 — 물리 일관성:      속도·위치 변화 벡터 일치
      0.25 — 교차 메시지 검증: HEARTBEAT 상태와 위치 데이터 상호 일관
    """
    score = 0.0
    if rec.get("packet_count", 0) >= 3:
        score += 0.25
    if rec.get("position_samples", 0) >= 2:
        score += 0.20
    if _physical_consistency_check(rec):
        score += 0.30
    if _cross_message_validation(rec):
        score += 0.25
    return round(score, 2)


def _conf_label(score: float) -> str:
    if score >= _CONF_HIGH:
        return "HIGH   — 후속 시나리오 후보로 사용 가능"
    if score >= _CONF_MEDIUM:
        return "MEDIUM — 재검증 필요"
    return "LOW    — 지연/스푸핑/불완전 관측 의심"


# ── Intelligence Report ───────────────────────────────────────────────────────

class IntelligenceReport:
    """수집된 전술 텔레메트리 저장소."""

    def __init__(self) -> None:
        self.assets: dict[int, dict[str, Any]] = {}
        self.packet_count = 0
        self.parse_errors = 0
        self.unknown_msg_count = 0
        self.msg_type_counts: dict[str, int] = {}
        self.start_time = time.time()

    # ── 메시지 핸들러 ─────────────────────────────────────────────────────────

    def update_heartbeat(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["mav_type"] = _MAV_TYPE.get(fields.get("type", -1),
                                         f"TYPE_{fields.get('type')}")
        rec["system_status"] = _MAV_STATE.get(fields.get("system_status", -1),
                                               "UNKNOWN")
        rec["base_mode"] = fields.get("base_mode", 0)
        rec["is_armed"]  = bool(fields.get("base_mode", 0) & 0x80)
        rec["is_guided"] = bool(fields.get("base_mode", 0) & 0x08)
        rec["last_heartbeat"] = time.time()

    def update_position(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        lat = fields.get("lat", 0) / 1e7
        lon = fields.get("lon", 0) / 1e7
        alt = fields.get("alt", 0) / 1000.0
        rel_alt = fields.get("relative_alt", 0) / 1000.0
        vx  = fields.get("vx", 0) / 100.0
        vy  = fields.get("vy", 0) / 100.0
        vz  = fields.get("vz", 0) / 100.0
        hdg = fields.get("hdg", 0) / 100.0

        rec["lat_deg"]           = round(lat, 7)
        rec["lon_deg"]           = round(lon, 7)
        rec["alt_m"]             = round(alt, 1)
        rec["rel_alt_m"]         = round(rel_alt, 1)
        rec["velocity_mps"]      = [round(vx, 2), round(vy, 2), round(vz, 2)]
        rec["ground_speed_mps"]  = round(math.sqrt(vx**2 + vy**2), 2)
        rec["heading_deg"]       = round(hdg, 1)
        rec["position_samples"]  = rec.get("position_samples", 0) + 1

        trail = rec.setdefault("trail", [])
        trail.append([round(lat, 6), round(lon, 6), round(alt, 0)])
        if len(trail) > 20:
            trail.pop(0)

    def update_sys_status(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["battery_pct"]    = fields.get("battery_remaining", -1)
        rec["drop_rate_comm"] = fields.get("drop_rate_comm", 0)
        rec["errors_comm"]    = fields.get("errors_comm", 0)

    def update_utm_position(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["utm_lat_deg"] = round(fields.get("lat", 0) / 1e7, 7)
        rec["utm_lon_deg"] = round(fields.get("lon", 0) / 1e7, 7)
        rec["utm_alt_m"]   = round(fields.get("alt", 0) / 1000.0, 1)

    def note_command_ack(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        acks = rec.setdefault("command_acks", [])
        acks.append({
            "command": fields.get("command"),
            "result":  _COMMAND_ACK_RESULT.get(fields.get("result", -1),
                                                f"RESULT_{fields.get('result')}"),
        })
        if len(acks) > 10:
            acks.pop(0)

    def note_mission_current(self, sys_id: int, fields: dict[str, Any]) -> None:
        self._get(sys_id)["mission_seq"] = fields.get("seq")

    def note_mission_ack(self, sys_id: int, fields: dict[str, Any]) -> None:
        self._get(sys_id)["last_mission_ack"] = _MISSION_ACK_TYPE.get(
            fields.get("type", -1), f"ACK_{fields.get('type')}")

    def note_mission_request(self, sys_id: int, fields: dict[str, Any]) -> None:
        rec = self._get(sys_id)
        rec["mission_upload_in_progress"] = True
        rec["mission_upload_seq"] = fields.get("seq")

    def record_msg_type(self, name: str) -> None:
        self.msg_type_counts[name] = self.msg_type_counts.get(name, 0) + 1

    # ── 집계 및 출력 ──────────────────────────────────────────────────────────

    def attack_value_map(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for sid, rec in self.assets.items():
            score = confidence_score(rec)
            result[f"sys_{sid}"] = {
                "platform":        rec.get("mav_type", "UNKNOWN"),
                "armed":           rec.get("is_armed"),
                "position": {
                    "lat":   rec.get("lat_deg"),
                    "lon":   rec.get("lon_deg"),
                    "alt_m": rec.get("alt_m"),
                },
                "speed_mps":       rec.get("ground_speed_mps"),
                "heading":         rec.get("heading_deg"),
                "battery_pct":     rec.get("battery_pct"),
                "mission_seq":     rec.get("mission_seq"),
                "confidence":      score,
                "confidence_label": _conf_label(score),
                "attacks_enabled": _enabled_attacks(rec, score),
            }
        return result

    def print_summary(self, phase: str = "최종") -> None:
        elapsed = time.time() - self.start_time
        print(
            f"\n{'='*65}\n"
            f"[PASSIVE-MAVLINK-RECON] {phase} 수집 완료\n"
            f"  경과 시간:        {elapsed:.1f}s\n"
            f"  수신 패킷:        {self.packet_count}개\n"
            f"  파싱 오류:        {self.parse_errors}개\n"
            f"  식별 자산 수:     {len(self.assets)}개\n"
            f"  HTTP 요청 횟수:   0  (GCS 감사로그 무흔적)\n"
            f"  메시지 타입 분포: {dict(sorted(self.msg_type_counts.items()))}\n"
            f"{'='*65}"
        )
        for sid, rec in sorted(self.assets.items()):
            score = confidence_score(rec)
            print(f"\n  [SYS_ID={sid}] {rec.get('mav_type','?')} / "
                  f"상태={rec.get('system_status','?')} / "
                  f"무장={'Y' if rec.get('is_armed') else 'N'} / "
                  f"신뢰도={score:.2f} [{_conf_label(score).split('—')[0].strip()}]")
            if "lat_deg" in rec:
                print(f"    위치: {rec['lat_deg']}, {rec['lon_deg']} "
                      f"고도={rec.get('alt_m')}m "
                      f"속도={rec.get('ground_speed_mps')}m/s "
                      f"방위={rec.get('heading_deg')}°")
            if rec.get("battery_pct", -1) >= 0:
                print(f"    배터리: {rec['battery_pct']}%  "
                      f"패킷손실={rec.get('drop_rate_comm', 0)/100:.1f}%")
            if rec.get("mission_seq") is not None:
                print(f"    임무 웨이포인트: #{rec['mission_seq']}")
            if rec.get("command_acks"):
                print(f"    최근 명령 응답: {rec['command_acks'][-3:]}")
            attacks = _enabled_attacks(rec, score)
            if attacks:
                print(f"    후속 시나리오 후보: {', '.join(attacks)}")
            else:
                print(f"    후속 시나리오 후보: 없음 (신뢰도 부족)")

    def _get(self, sys_id: int) -> dict[str, Any]:
        if sys_id not in self.assets:
            self.assets[sys_id] = {
                "sys_id":      sys_id,
                "first_seen":  time.time(),
                "packet_count": 0,
            }
        self.assets[sys_id]["packet_count"] += 1
        return self.assets[sys_id]


# ── 후속 시나리오 활성화 조건 ─────────────────────────────────────────────────

def _enabled_attacks(rec: dict[str, Any], score: float) -> list[str]:
    """신뢰도 임계를 충족한 자산에 대해서만 후속 시나리오 후보 반환."""
    if score < _CONF_MEDIUM:
        return []   # 저신뢰 관측은 후속 시나리오 후보로 사용하지 않음
    attacks = []
    if rec.get("lat_deg") is not None:
        attacks.append("GNSS-DRIFT(S01)")
        attacks.append("DYNAMIC-SPOOF(S03)")
        attacks.append("GEOFENCE-INJECT(S17)")
    if rec.get("battery_pct", -1) >= 0:
        attacks.append("BATTERY-CRISIS(S10)")
    if rec.get("is_armed"):
        attacks.append("CMD-INJECT(S05)")
    if rec.get("drop_rate_comm", 0) > 100:
        attacks.append("LINK-DEGRADE(S02)")
    if rec.get("mission_seq") is not None:
        attacks.append("MISSION-UPLOAD-RACE")
    return attacks


# ── 수집 루프 ─────────────────────────────────────────────────────────────────

def _collect(sock: socket.socket, report: IntelligenceReport,
             deadline: float, phase_label: str) -> None:
    """단일 수집 루프. deadline까지 패킷을 수신하여 report에 누적."""
    while time.time() < deadline:
        try:
            datagram, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError as e:
            print(f"  [{phase_label}] 소켓 오류: {e}", flush=True)
            break

        report.packet_count += 1
        try:
            frames = parse_datagram(datagram)
        except Exception as e:
            report.parse_errors += 1
            print(f"  [PARSE_ERR] {addr[0]} len={len(datagram)} err={e}",
                  flush=True)
            continue

        for item in frames:
            if not isinstance(item, ParsedMavlinkFrame):
                continue
            sid    = item.system_id
            name   = item.message_name
            fields = item.fields
            report.record_msg_type(name)

            if name == "HEARTBEAT":
                report.update_heartbeat(sid, fields)
                print(
                    f"  [{addr[0]}] HEARTBEAT   sys={sid} "
                    f"type={_MAV_TYPE.get(fields.get('type',-1),'?')} "
                    f"status={_MAV_STATE.get(fields.get('system_status',-1),'?')} "
                    f"armed={'Y' if fields.get('base_mode',0)&0x80 else 'N'}",
                    flush=True,
                )
            elif name == "GLOBAL_POSITION_INT":
                report.update_position(sid, fields)
                lat = fields.get("lat", 0) / 1e7
                lon = fields.get("lon", 0) / 1e7
                alt = fields.get("alt", 0) / 1000.0
                hdg = fields.get("hdg", 0) / 100.0
                spd = math.sqrt(
                    (fields.get("vx", 0)/100)**2 + (fields.get("vy", 0)/100)**2
                )
                print(
                    f"  [{addr[0]}] GLOBAL_POS  sys={sid} "
                    f"lat={lat:.6f} lon={lon:.6f} alt={alt:.1f}m "
                    f"hdg={hdg:.1f}deg spd={spd:.1f}m/s",
                    flush=True,
                )
            elif name == "SYS_STATUS":
                report.update_sys_status(sid, fields)
                pct  = fields.get("battery_remaining", -1)
                drop = fields.get("drop_rate_comm", 0) / 100.0
                print(
                    f"  [{addr[0]}] SYS_STATUS  sys={sid} "
                    f"battery={pct}% link_loss={drop:.1f}%",
                    flush=True,
                )
            elif name == "UTM_GLOBAL_POSITION":
                report.update_utm_position(sid, fields)
                lat = fields.get("lat", 0) / 1e7
                lon = fields.get("lon", 0) / 1e7
                print(
                    f"  [{addr[0]}] UTM_POS     sys={sid} "
                    f"lat={lat:.6f} lon={lon:.6f} "
                    f"alt={fields.get('alt',0)/1000:.1f}m",
                    flush=True,
                )
            elif name == "COMMAND_ACK":
                report.note_command_ack(sid, fields)
                result_str = _COMMAND_ACK_RESULT.get(fields.get("result", -1), "?")
                print(
                    f"  [{addr[0]}] CMD_ACK     sys={sid} "
                    f"cmd={fields.get('command')} result={result_str}",
                    flush=True,
                )
            elif name == "MISSION_CURRENT":
                report.note_mission_current(sid, fields)
                print(
                    f"  [{addr[0]}] MISSION_CUR sys={sid} seq={fields.get('seq')}",
                    flush=True,
                )
            elif name == "MISSION_ACK":
                report.note_mission_ack(sid, fields)
                ack_str = _MISSION_ACK_TYPE.get(fields.get("type", -1), "?")
                print(
                    f"  [{addr[0]}] MISSION_ACK sys={sid} type={ack_str}",
                    flush=True,
                )
            elif name == "MISSION_REQUEST_INT":
                report.note_mission_request(sid, fields)
                print(
                    f"  [{addr[0]}] MISS_REQ    sys={sid} seq={fields.get('seq')} "
                    f"(임무 업로드 진행 중)",
                    flush=True,
                )
            else:
                report.unknown_msg_count += 1
                print(
                    f"  [{addr[0]}] UNKNOWN     sys={sid} "
                    f"msg={name}(id={item.message_id})",
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


def run(listen_host: str, listen_port: int, duration_s: int,
        revalidate_s: int, output_path: str | None) -> None:
    report = IntelligenceReport()

    # ── Phase 1: 초기 수집 ────────────────────────────────────────────────────
    sock = _open_socket(listen_host, listen_port)
    print(
        f"[passive-mavlink-recon] Phase 1: 초기 수집\n"
        f"  UDP {listen_host}:{listen_port}  지속: {duration_s}s\n"
        f"  HTTP 요청: 0 (GCS 감사로그 무흔적)\n"
        f"  [주의] 네트워크 IDS/방화벽에는 수신 소켓이 관측될 수 있음\n",
        flush=True,
    )
    _collect(sock, report, time.time() + duration_s, "Phase1")
    sock.close()

    report.print_summary(phase="Phase 1")

    # ── Phase 2: 신뢰도 평가 ──────────────────────────────────────────────────
    print(f"\n[passive-mavlink-recon] Phase 2: 신뢰도 점수화", flush=True)
    low_conf = []
    for sid, rec in sorted(report.assets.items()):
        score = confidence_score(rec)
        label = _conf_label(score)
        print(f"  sys={sid:>3}  score={score:.2f}  {label}", flush=True)
        if score < _CONF_MEDIUM:
            low_conf.append(sid)

    # ── Phase 3: 단기 재검증 (옵션) ───────────────────────────────────────────
    if revalidate_s > 0 and low_conf:
        print(
            f"\n[passive-mavlink-recon] Phase 3: 단기 재검증 ({revalidate_s}s)\n"
            f"  재검증 대상: {low_conf}\n",
            flush=True,
        )
        r2 = IntelligenceReport()
        sock2 = _open_socket(listen_host, listen_port)
        _collect(sock2, r2, time.time() + revalidate_s, "Phase3")
        sock2.close()

        print(f"\n[passive-mavlink-recon] Phase 3: 재검증 결과", flush=True)
        for sid in low_conf:
            if sid in r2.assets:
                new_score = confidence_score(r2.assets[sid])
                old_score = confidence_score(report.assets[sid])
                delta = new_score - old_score
                sign  = "+" if delta >= 0 else ""
                print(f"  sys={sid:>3}  초기={old_score:.2f} → "
                      f"재검증={new_score:.2f} ({sign}{delta:.2f})", flush=True)
                # 재검증 데이터로 레코드 보강
                if new_score > old_score:
                    report.assets[sid].update(r2.assets[sid])
            else:
                print(f"  sys={sid:>3}  재검증 기간 동안 수신 없음 — "
                      f"스푸핑/전파 중단 의심", flush=True)
    elif revalidate_s > 0:
        print(f"\n[passive-mavlink-recon] Phase 3: 전 자산 신뢰도 충분 — 재검증 생략",
              flush=True)

    # ── Phase 4: 후속 시나리오 권고 ───────────────────────────────────────────
    print(f"\n[passive-mavlink-recon] Phase 4: 후속 시나리오 권고", flush=True)
    any_usable = False
    for sid, rec in sorted(report.assets.items()):
        score   = confidence_score(rec)
        attacks = _enabled_attacks(rec, score)
        if attacks:
            any_usable = True
            print(f"  sys={sid:>3} ({rec.get('mav_type','?')})  "
                  f"score={score:.2f}  → {', '.join(attacks)}", flush=True)
        else:
            print(f"  sys={sid:>3} ({rec.get('mav_type','?')})  "
                  f"score={score:.2f}  → 후보 없음 (신뢰도 부족)", flush=True)
    if not any_usable:
        print("  전 자산 신뢰도 부족 — 수집 연장 또는 세그먼트 재확인 권고", flush=True)

    # ── JSON 저장 ─────────────────────────────────────────────────────────────
    intel = {
        "meta": {
            "attack":          "passive_mavlink_recon",
            "scenario":        "Low-Privilege Sentinel (S11)",
            "duration_s":      duration_s,
            "revalidate_s":    revalidate_s,
            "packet_count":    report.packet_count,
            "parse_errors":    report.parse_errors,
            "unknown_msgs":    report.unknown_msg_count,
            "msg_type_counts": report.msg_type_counts,
            "http_requests":   0,
            "gcs_audit_trace": False,
            "network_ids_visible": True,
        },
        "assets": {str(k): v for k, v in report.assets.items()},
        "confidence": {
            str(sid): {
                "score": confidence_score(rec),
                "label": _conf_label(confidence_score(rec)),
            }
            for sid, rec in report.assets.items()
        },
        "attack_value": report.attack_value_map(),
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(intel, f, ensure_ascii=False, indent=2)
        print(f"\n[passive-mavlink-recon] 결과 저장: {output_path}", flush=True)
    else:
        print("\n[정보 수집 결과 JSON]")
        print(json.dumps(intel, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Passive MAVLink Recon — Low-Privilege Sentinel (S11)\n"
                    "UDP 수신 전용, REST API 미호출, 신뢰도 점수화 포함"
    )
    parser.add_argument("--listen-host",  default=LISTEN_HOST)
    parser.add_argument("--listen-port",  type=int, default=LISTEN_PORT)
    parser.add_argument("--duration-s",   type=int, default=120,
                        help="Phase 1 수집 지속 시간 (초)")
    parser.add_argument("--revalidate-s", type=int, default=20,
                        help="Phase 3 재검증 시간 (초, 0이면 생략)")
    parser.add_argument("--output",       default=None,
                        help="수집 결과 JSON 저장 경로")
    args = parser.parse_args(argv)

    run(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        duration_s=args.duration_s,
        revalidate_s=args.revalidate_s,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
