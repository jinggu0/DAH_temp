from __future__ import annotations

import socket
import struct
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import ServiceState

BROADCAST_ADDR = "255.255.255.255"
BROADCAST_PORT = 14549   # 전용 텔레메트리 브로드캐스트 포트 (게이트웨이 14550과 분리)
INTERVAL_S = 1.0

# MAVLink v2 상수
_STX = 0xFD
_MAV_TYPE_QUADROTOR    = 2
_MAV_TYPE_GROUND_ROVER = 10
_MAV_AUTOPILOT_APM     = 3
_MAV_STATE_ACTIVE      = 4
_BASE_MODE_ARMED_GUIDED = 0x88   # SAFETY_ARMED | GUIDED_ENABLED

# 메시지별 CRC_EXTRA (MAVLink common.xml 기준)
_CRC_EXTRA: dict[int, int] = {
    0:  50,   # HEARTBEAT
    1:  124,  # SYS_STATUS
    33: 104,  # GLOBAL_POSITION_INT
}


def _x25(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def _frame(seq: int, sys_id: int, msg_id: int, payload: bytes) -> bytes:
    header = bytes([
        _STX,
        len(payload),
        0,           # incompat_flags (서명 없음)
        0,           # compat_flags
        seq & 0xFF,
        sys_id,
        1,           # component_id = autopilot
        msg_id & 0xFF,
        (msg_id >> 8) & 0xFF,
        (msg_id >> 16) & 0xFF,
    ])
    crc = _x25(header[1:] + payload + bytes([_CRC_EXTRA.get(msg_id, 0)]))
    return header + payload + struct.pack("<H", crc)


def _heartbeat(seq: int, sys_id: int, mav_type: int) -> bytes:
    payload = struct.pack("<IBBBBB",
        0,                    # custom_mode
        mav_type,
        _MAV_AUTOPILOT_APM,
        _BASE_MODE_ARMED_GUIDED,
        _MAV_STATE_ACTIVE,
        3,                    # mavlink_version
    )
    return _frame(seq, sys_id, 0, payload)


def _global_position_int(seq: int, sys_id: int,
                          lat_e7: int, lon_e7: int, alt_mm: int,
                          vx_cms: int, vy_cms: int, hdg_cdeg: int,
                          boot_ms: int) -> bytes:
    payload = struct.pack("<IiiiihhhH",
        boot_ms,
        lat_e7,
        lon_e7,
        alt_mm,
        alt_mm,    # relative_alt = alt (시뮬레이션에서 동일)
        vx_cms,
        vy_cms,
        0,         # vz
        hdg_cdeg,
    )
    return _frame(seq, sys_id, 33, payload)


def _sys_status(seq: int, sys_id: int, battery_pct: int, drop_rate_permille: int) -> bytes:
    # 31바이트: sensors_present, sensors_enabled, sensors_health, load,
    #           voltage_mv, current_ca, battery_pct, drop_rate, errors, counts*4
    payload = struct.pack("<IIIHHhbHHHHHH",
        0xFFFFFFFF,          # sensors_present
        0xFFFFFFFF,          # sensors_enabled
        0xFFFFFFFF,          # sensors_health
        0,                   # load (permille)
        22_200,              # voltage_battery mV (6S LiPo 3.7V/cell)
        -1,                  # current_battery cA (unknown = -1)
        max(-1, min(100, battery_pct)),
        drop_rate_permille,
        0,                   # errors_comm
        0, 0, 0, 0,          # error counts 1-4
    )
    return _frame(seq, sys_id, 1, payload)


def _enu_to_wgs84(x_m: float, y_m: float, z_m: float,
                  origin_lat_e7: int, origin_lon_e7: int) -> tuple[int, int, int]:
    lat_e7 = origin_lat_e7 + int(y_m / 111_320.0 * 10_000_000)
    lon_e7 = origin_lon_e7 + int(x_m / 88_800.0 * 10_000_000)
    alt_mm  = int(z_m * 1_000)
    return lat_e7, lon_e7, alt_mm


class MavlinkBroadcaster:
    """GCS 상태를 MAVLink v2 UDP 브로드캐스트로 주기적 방출.

    실제 전술 환경에서 GCS는 전술링크(TMMR/TICN) 또는 지상 이더넷을
    통해 자산 텔레메트리를 브로드캐스트한다. 이 모듈은 그 동작을
    UDP 14549 포트로 시뮬레이션한다.

    공격자는 네트워크에서 이 패킷을 수신함으로써 REST API 호출 없이
    동일한 정보를 획득할 수 있다 (Passive MAVLink Recon, 시나리오 11).
    """

    def __init__(self, state: "ServiceState") -> None:
        self._state = state
        self._seq: dict[int, int] = {}
        self._tick = 0
        self._sock: socket.socket | None = None
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="mavlink-broadcaster"
        )

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock = sock
        self._thread.start()
        print(
            f"[mavlink-broadcaster] UDP broadcast {BROADCAST_ADDR}:{BROADCAST_PORT} "
            f"interval={INTERVAL_S}s",
            flush=True,
        )

    def _loop(self) -> None:
        while True:
            try:
                self._emit_tick()
            except Exception as exc:
                print(f"[mavlink-broadcaster] tick error: {exc}", flush=True)
            time.sleep(INTERVAL_S)
            self._tick += 1

    def _emit_tick(self) -> None:
        state = self._state
        scenario = state.scenario
        origin_lat = scenario.origin_lat_e7
        origin_lon = scenario.origin_lon_e7
        boot_ms = int(time.monotonic() * 1_000) & 0xFFFF_FFFF

        # asset_id → system_id 매핑 (시나리오 정의 기준)
        sys_id_map: dict[str, int] = {a.id: a.system_id for a in scenario.assets}
        # asset_id → 플랫폼 타입 매핑
        type_map: dict[str, str] = {a.id: getattr(a, "asset_type", "uav") for a in scenario.assets}

        payload = state.tracks_payload(None)
        tracks: list[dict[str, Any]] = payload.get("tracks", []) if isinstance(payload, dict) else []

        for track in tracks:
            asset_id: str = track.get("asset_id", "")
            sys_id = sys_id_map.get(asset_id, 1)
            atype = type_map.get(asset_id, "uav")
            mav_type = (
                _MAV_TYPE_GROUND_ROVER
                if ("ugv" in atype.lower() or "convoy" in asset_id.lower())
                else _MAV_TYPE_QUADROTOR
            )

            # 1. HEARTBEAT
            self._send(_heartbeat(self._next_seq(sys_id), sys_id, mav_type))

            # 2. GLOBAL_POSITION_INT
            pos = track.get("fused_position", [0.0, 0.0, 0.0])
            vel = track.get("fused_velocity_mps", [0.0, 0.0, 0.0])
            hdg = float(track.get("heading_deg", 0.0))
            lat_e7, lon_e7, alt_mm = _enu_to_wgs84(
                float(pos[0]), float(pos[1]), float(pos[2]),
                origin_lat, origin_lon,
            )
            self._send(_global_position_int(
                self._next_seq(sys_id), sys_id,
                lat_e7, lon_e7, alt_mm,
                int(float(vel[0]) * 100),
                int(float(vel[1]) * 100),
                int((hdg % 360) * 100),
                boot_ms,
            ))

            # 3. SYS_STATUS — 5틱(5초)마다
            if self._tick % 5 == 0:
                batt_wh = float(track.get("battery_wh", 0))
                # 690 Wh (UAV 정격) / 3725 Wh (UGV 정격) 기준 백분율
                rated = 3_725 if mav_type == _MAV_TYPE_GROUND_ROVER else 690
                batt_pct = min(100, int(batt_wh / rated * 100))
                lq = float(track.get("link_quality", 1.0))
                drop_permille = int((1.0 - max(0.0, min(1.0, lq))) * 10_000)
                self._send(_sys_status(self._next_seq(sys_id), sys_id, batt_pct, drop_permille))

    def _next_seq(self, sys_id: int) -> int:
        n = self._seq.get(sys_id, 0)
        self._seq[sys_id] = (n + 1) & 0xFF
        return n

    def _send(self, frame: bytes) -> None:
        if self._sock is not None:
            try:
                self._sock.sendto(frame, (BROADCAST_ADDR, BROADCAST_PORT))
            except OSError:
                pass
