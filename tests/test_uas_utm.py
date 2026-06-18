from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm.simulator import load_scenario, run_environment, summarize_result
from uas_utm.utm_service import UtmService


class UasUtmEnvironmentTests(unittest.TestCase):
    def test_utm_approves_valid_missions_and_rejects_airspace_violation(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "normal_utm_ops.json")
        decisions = UtmService(scenario).evaluate_missions()

        approved = {decision.mission_id for decision in decisions if decision.approved}
        rejected = {decision.mission_id: decision.reasons for decision in decisions if not decision.approved}

        self.assertIn("mission-alpha-survey", approved)
        self.assertIn("mission-bravo-logistics", approved)
        self.assertIn("mission-charlie-invalid-nfz", rejected)
        self.assertTrue(any("no_fly_zone:nfz-hospital" in reason for reason in rejected["mission-charlie-invalid-nfz"]))

    def test_environment_generates_telemetry_for_every_asset(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "normal_utm_ops.json")
        result = run_environment(scenario)

        expected_frames = (scenario.duration_s // scenario.step_s + 1) * len(scenario.assets)

        self.assertEqual(len(result.telemetry), expected_frames)
        self.assertEqual({frame.asset_id for frame in result.telemetry}, {asset.id for asset in scenario.assets})

    def test_summary_is_report_ready(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "normal_utm_ops.json")
        result = run_environment(scenario)
        summary = summarize_result(result)

        self.assertEqual(summary["scenario"], "normal_uas_utm_ops_stage_1")
        self.assertEqual(summary["asset_count"], 3)
        self.assertEqual(summary["mission_count"], 3)
        self.assertIn("mission-alpha-survey", summary["approved_missions"])
        self.assertIn("mission-bravo-logistics", summary["approved_missions"])
        self.assertEqual(summary["telemetry_frames"], 543)


if __name__ == "__main__":
    unittest.main()
