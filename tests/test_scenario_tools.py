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

if __name__ == "__main__":
    unittest.main()