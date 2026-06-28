from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dah_runtime.event_bus import EventBus
from dah_runtime.health import health_payload, status_payload
from dah_runtime.jsonl_store import JsonlStore
from dah_runtime.service_contracts import CommandEvent, TelemetryEvent, make_service_status


class DahRuntimeServiceTests(unittest.TestCase):
    def test_service_status_contract_serializes_boundary_and_metrics(self) -> None:
        status = make_service_status(
            service_id="dah-tmmr-emulator",
            role="tmmr_queue_emulator",
            emulated=True,
            boundary="EMULATED / NOT REAL MILITARY SYSTEM",
            metrics={"queue_depth": 0},
        )

        payload = status.to_payload()

        self.assertTrue(payload["emulated"])
        self.assertEqual(payload["metrics"]["queue_depth"], 0)
        self.assertEqual(health_payload(status)["ok"], True)

    def test_common_event_contracts_use_json_ready_payloads(self) -> None:
        telemetry = TelemetryEvent(
            vehicle_id="uav-01",
            vehicle_type="UAV",
            timestamp="2026-06-28T00:00:00+00:00",
            position=(1.0, 2.0, 80.0),
            velocity=(0.1, 0.0, 0.0),
            mode="mock",
            mission_id="mission-1",
            waypoint_index=1,
            link_status="normal",
            source_protocol="MAVLink-like",
        )
        command = CommandEvent(
            command_id="cmd-1",
            source="dah-gcs",
            destination="dah-uav-sim",
            command_type="hold_position",
            approved=False,
            dry_run=True,
            ack_status="queued",
        )

        self.assertEqual(telemetry.to_payload()["position"], [1.0, 2.0, 80.0])
        self.assertTrue(command.to_payload()["dry_run"])

    def test_jsonl_store_and_event_bus_persist_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            store = JsonlStore(path)
            store.append({"event_type": "unit.test", "value": 1})
            bus = EventBus(path)
            bus.publish("unit.bus", {"value": 2}, source="test")

            rows = bus.tail(limit=5)

            self.assertEqual(rows[0]["event_type"], "unit.test")
            self.assertEqual(rows[-1]["event_type"], "unit.bus")

    def test_role_wrapper_modules_are_importable(self) -> None:
        modules = [
            "dah_services.gcs_service",
            "dah_services.uav_sim_service",
            "dah_services.ugv_sim_service",
            "dah_services.dashboard_service",
            "dah_services.tactical_router_service",
            "dah_services.tmmr_emulator_service",
            "dah_services.ticn_emulator_service",
            "dah_services.upper_c2_service",
            "dah_services.telemetry_collector_service",
            "dah_services.defense_agent_service",
            "dah_services.fault_injector_service",
        ]

        for name in modules:
            module = importlib.import_module(name)
            self.assertTrue(callable(module.main), name)

    def test_status_payload_matches_phase3_service_fields(self) -> None:
        payload = status_payload(
            service_id="dah-defense-agent",
            role="rule_based_detection_and_response_recommendation",
            status="normal",
            boundary="LOCAL DEFENSE MONITOR; NO REAL COMMAND EXECUTION",
            metrics={"executor": "dry_run"},
        )

        self.assertEqual(payload["service_id"], "dah-defense-agent")
        self.assertEqual(payload["status"], "normal")
        self.assertEqual(payload["metrics"]["executor"], "dry_run")


if __name__ == "__main__":
    unittest.main()