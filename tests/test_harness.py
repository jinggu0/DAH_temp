from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dah_harness.metrics import score_result
from dah_harness.simulation import load_scenario, run_scenario


class HarnessScenarioTests(unittest.TestCase):
    def test_baseline_detects_all_seeded_attacks(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "uav_ugv_convoy.json")
        result = run_scenario(scenario)
        metrics = score_result(result, detection_grace_s=scenario.metric_detection_grace_s)

        self.assertEqual(metrics["attack_count"], 3)
        self.assertEqual(metrics["detected_count"], 3)
        self.assertGreaterEqual(metrics["detection_rate"], 1.0)
        self.assertIn("atk-gps-uav-01", metrics["detections"])
        self.assertIn("atk-cmd-ugv-01", metrics["detections"])
        self.assertIn("atk-link-uav-01", metrics["detections"])
        self.assertLessEqual(metrics["false_positive_actions"], 1)

    def test_threshold_override_can_reduce_sensitivity(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "uav_ugv_convoy.json")
        scenario.defense.route_deviation_threshold_m = 500
        scenario.defense.gps_jump_threshold_m = 500

        result = run_scenario(scenario)
        metrics = score_result(result, detection_grace_s=scenario.metric_detection_grace_s)

        self.assertIsNone(metrics["detections"]["atk-gps-uav-01"])
        self.assertLess(metrics["detected_count"], metrics["attack_count"])

    def test_actions_keep_attack_context_for_report_evidence(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "uav_ugv_convoy.json")
        result = run_scenario(scenario)

        contextual_actions = [action for action in result.actions if action.active_attack_ids]

        self.assertTrue(contextual_actions)
        self.assertTrue(any("atk-cmd-ugv-01" in action.active_attack_ids for action in contextual_actions))


if __name__ == "__main__":
    unittest.main()
