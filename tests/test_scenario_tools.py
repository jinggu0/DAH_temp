from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm.scenario_tools import analyze_scenario, render_markdown_report, validate_scenario
from uas_utm.simulator import load_scenario


class ScenarioToolsTests(unittest.TestCase):
    def test_korea_defense_scenario_report_is_valid_and_mentions_ugv(self) -> None:
        report = analyze_scenario(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        markdown = render_markdown_report(report)

        self.assertTrue(report["valid"])
        self.assertEqual(report["summary"]["asset_count"], 5)
        self.assertIn("ugv-convoy-route-clearance", markdown)
        self.assertIn("Scenario Report", markdown)

    def test_template_scenario_is_reportable(self) -> None:
        report = analyze_scenario(ROOT / "scenarios" / "templates" / "uav_ugv_joint_recon.json")

        self.assertTrue(report["valid"])
        self.assertEqual(report["summary"]["asset_count"], 2)
        self.assertIn("UGV assets are present", "\n".join(report["recommendations"]))


    def test_ugv_ground_route_requires_declared_corridor(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "templates" / "uav_ugv_joint_recon.json")
        scenario = replace(scenario, zones=[zone for zone in scenario.zones if "ground" not in zone.id and "ugv" not in zone.id and "ugv" not in zone.label.lower()])

        issues = validate_scenario(scenario)

        self.assertTrue(any("UGV mission requires" in issue.message for issue in issues))


    def test_dah_training_scenarios_are_valid_and_documented(self) -> None:
        scenario_dir = ROOT / "scenarios" / "dah_training"
        scenario_paths = [
            scenario_dir / "mavlink_telemetry_monitoring.json",
            scenario_dir / "mission_upload_guard.json",
            scenario_dir / "tactical_chain_degradation.json",
        ]
        docs = (ROOT / "docs" / "scenarios.md").read_text(encoding="utf-8")

        for path in scenario_paths:
            with self.subTest(path=path.name):
                report = analyze_scenario(path)
                markdown = render_markdown_report(report)

                self.assertTrue(report["valid"], report["issues"])
                self.assertGreater(report["summary"]["asset_count"], 0)
                self.assertGreater(report["summary"]["mission_count"], 0)
                self.assertIn("Scenario Report", markdown)
                self.assertIn(path.name, docs)

    def test_defensive_vulnerability_notes_cover_allowlisted_faults(self) -> None:
        notes = (ROOT / "docs" / "vulnerabilities.md").read_text(encoding="utf-8")

        for fault_type in [
            "mavlink_plaintext_warning",
            "mission_count_reset_attempt",
            "c2_link_delay",
            "c2_link_packet_loss",
            "tmmr_queue_overflow",
            "ticn_route_metric_change",
            "upper_c2_command_mismatch",
        ]:
            with self.subTest(fault_type=fault_type):
                self.assertIn(fault_type, notes)
        self.assertIn("emulator roles only", notes.lower())

if __name__ == "__main__":
    unittest.main()
