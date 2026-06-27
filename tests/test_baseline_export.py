from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm_service.baseline_export import export_baseline_files


class BaselineExportTests(unittest.TestCase):
    def test_baseline_export_writes_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = export_baseline_files(
                scenario_path=ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                output_dir=Path(tmpdir),
                limit=12,
            )
            baseline = json.loads(Path(paths["baseline"]).read_text(encoding="utf-8"))
            telemetry = Path(paths["telemetry"]).read_text(encoding="utf-8").strip().splitlines()
            markdown = Path(paths["markdown"]).read_text(encoding="utf-8")

        self.assertEqual(baseline["summary"]["asset_count"], 5)
        self.assertEqual(len(telemetry), 12)
        self.assertIn("Baseline Report", markdown)
        self.assertIn("ugv-convoy-route-clearance", markdown)


if __name__ == "__main__":
    unittest.main()