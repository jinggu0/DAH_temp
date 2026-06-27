from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm.mavlink_adapter import mission_to_mavlink_items
from uas_utm.simulator import load_scenario, run_environment, summarize_result
from uas_utm.utm_service import UtmService


class KoreaDefenseUasUpgradeTests(unittest.TestCase):
    def test_korea_defense_scenario_approves_operational_missions(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        decisions = UtmService(scenario).evaluate_missions()

        approved = {decision.mission_id for decision in decisions if decision.approved}
        rejected = {decision.mission_id: decision.reasons for decision in decisions if not decision.approved}

        self.assertIn("muav-wide-area-isr", approved)
        self.assertIn("rq101-corps-route-survey", approved)
        self.assertIn("dronebot-local-recon", approved)
        self.assertIn("naval-vtol-coastal-watch", approved)
        self.assertIn("ugv-convoy-route-clearance", approved)
        self.assertIn("invalid-airport-buffer-sample", rejected)
        self.assertTrue(any("no_fly_zone:civil-airport-buffer" in reason for reason in rejected["invalid-airport-buffer-sample"]))

    def test_mavlink_telemetry_messages_are_generated(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        result = run_environment(scenario)
        summary = summarize_result(result)

        self.assertEqual(summary["asset_count"], 5)
        self.assertEqual(summary["c2_node_count"], 4)
        self.assertGreater(summary["link_coverage_rate"], 0.95)
        self.assertIn("UTM_GLOBAL_POSITION", summary["mavlink_message_counts"])
        self.assertIn("GLOBAL_POSITION_INT", summary["mavlink_message_counts"])
        self.assertIn("MISSION_CURRENT", summary["mavlink_message_counts"])
        self.assertIn("ugv_ground_rover", summary["platform_classes"])

    def test_approved_missions_can_be_rendered_as_mission_item_int(self) -> None:
        scenario = load_scenario(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        assets = {asset.id: asset for asset in scenario.assets}
        mission = next(item for item in scenario.missions if item.id == "muav-wide-area-isr")

        messages = mission_to_mavlink_items(
            scenario=scenario,
            asset=assets[mission.asset_id],
            mission=mission,
        )

        self.assertEqual(len(messages), len(mission.route))
        self.assertTrue(all(message.message_name == "MISSION_ITEM_INT" for message in messages))
        self.assertEqual(messages[0].fields["command"], "MAV_CMD_NAV_WAYPOINT")


if __name__ == "__main__":
    unittest.main()
