from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dah_harness.tactical_emulator import TacticalEmulatorRuntime
from uas_utm_service.state import ServiceState


class TacticalEmulatorTests(unittest.TestCase):
    def test_runtime_starts_with_simulated_tactical_components(self) -> None:
        runtime = TacticalEmulatorRuntime()

        snapshot = runtime.snapshot()
        labels = [item["label"] for item in snapshot["components"]]

        self.assertEqual(snapshot["schema_version"], "dah-tactical-emulator.v1")
        self.assertIn("Virtual Tactical Router / TIPS", labels)
        self.assertIn("TMMR Emulator", labels)
        self.assertIn("TICN-like Network", labels)
        self.assertIn("Upper C2/BMS Simulator", labels)
        self.assertEqual(snapshot["overall_status"], "normal")

    def test_tmmr_queue_overflow_changes_component_metrics(self) -> None:
        runtime = TacticalEmulatorRuntime()

        event = runtime.apply_fault("tmmr_queue_overflow", requested_by="operator-a", parameters={"queue_depth": 2000})
        snapshot = runtime.snapshot()
        tmmr = next(item for item in snapshot["components"] if item["component_id"] == "tmmr")

        self.assertTrue(event.simulation_only)
        self.assertEqual(snapshot["overall_status"], "critical")
        self.assertEqual(tmmr["status"], "critical")
        self.assertEqual(tmmr["metrics"]["queue_depth"], 2000)
        self.assertTrue(tmmr["metrics"]["priority_starvation"])

    def test_ticn_route_metric_change_degrades_route_state(self) -> None:
        runtime = TacticalEmulatorRuntime()

        runtime.apply_fault("ticn_route_metric_change", parameters={"route_metric": 77})
        ticn = next(item for item in runtime.snapshot()["components"] if item["component_id"] == "ticn")

        self.assertEqual(ticn["status"], "degraded")
        self.assertEqual(ticn["metrics"]["route_metric"], 77)
        self.assertEqual(ticn["metrics"]["route_change_count"], 1)

    def test_non_allowlisted_fault_is_rejected(self) -> None:
        runtime = TacticalEmulatorRuntime()

        with self.assertRaises(ValueError):
            runtime.apply_fault("real_tactical_network_attack")

    def test_service_chain_uses_tactical_emulator_snapshot(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        state.inject_fault({"payload": {"fault_type": "upper_c2_command_mismatch"}})
        chain = state.chain_payload()
        monitor = state.protocol_monitor_payload(limit=5)

        self.assertEqual(chain["emulator"]["schema_version"], "dah-tactical-emulator.v1")
        self.assertEqual(chain["overall_status"], "degraded")
        self.assertTrue(any(item["payload"]["metrics"] for item in monitor["tactical_messages"]))
        self.assertEqual(monitor["alerts"][0]["category"], "simulated_tactical_fault")


if __name__ == "__main__":
    unittest.main()