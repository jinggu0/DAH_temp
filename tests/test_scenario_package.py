from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm.scenario_batch import package_training_scenarios
from uas_utm.scenario_briefing import generate_briefings_for_index
from uas_utm.scenario_package import package_scenario


class ScenarioPackageTests(unittest.TestCase):
    def test_package_scenario_creates_manifest_report_and_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = package_scenario(
                scenario_path=ROOT / "scenarios" / "templates" / "uav_ugv_joint_recon.json",
                output_dir=Path(tmpdir),
                limit=8,
            )
            manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))
            package_root = Path(paths["package_root"])

            self.assertTrue((package_root / manifest["scenario"]).exists())
            self.assertTrue((package_root / manifest["report"]["markdown"]).exists())
            self.assertTrue((package_root / manifest["baseline"]["baseline"]).exists())
            self.assertTrue(manifest["valid"])



    def test_package_training_scenarios_creates_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            index = package_training_scenarios(
                scenario_dir=ROOT / "scenarios" / "dah_training",
                output_dir=Path(tmpdir),
                limit=5,
            )
            index_path = Path(index["index_json"])
            index_markdown = Path(index["index_markdown"])

            self.assertEqual(index["schema_version"], "dah-scenario-package-index.v1")
            self.assertEqual(index["count"], 3)
            self.assertTrue(index_path.exists())
            self.assertTrue(index_markdown.exists())
            self.assertTrue(all(item["valid"] for item in index["packages"]))
            self.assertTrue(any(item["fault_profile"] == "mission_count_reset_attempt" for item in index["packages"]))


    def test_generate_briefings_for_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            index = package_training_scenarios(
                scenario_dir=ROOT / "scenarios" / "dah_training",
                output_dir=Path(tmpdir),
                limit=3,
            )

            briefing_index = generate_briefings_for_index(Path(index["index_json"]))

            self.assertEqual(briefing_index["schema_version"], "dah-briefing-index.v1")
            self.assertEqual(briefing_index["count"], 3)
            self.assertTrue(Path(briefing_index["briefing_index"]).exists())
            self.assertIn("reporting templates only", briefing_index["safety_boundary"])

if __name__ == "__main__":
    unittest.main()
