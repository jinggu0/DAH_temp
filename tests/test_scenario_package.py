from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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


if __name__ == "__main__":
    unittest.main()
