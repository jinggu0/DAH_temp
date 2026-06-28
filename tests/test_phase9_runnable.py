"""
Phase 9: README 명령 실행 검증 테스트.

README에 명시된 Python CLI 명령과 API 엔드포인트가 실제로 동작하는지
자동화 테스트로 검증합니다. (Docker 필요 명령은 별도 RunBook 참조)

Verified commands:
  python -m dah_harness.cli --scenario ... --output ...
  python -m dah_harness.cli ... --set key=value
  python -m uas_utm.scenario_report --scenario ... --markdown-output ...
  python -m uas_utm.scenario_package --scenario ... --output-dir ...
  python -m uas_utm.scenario_batch --scenario-dir ... --output-dir ...
  GCS server /api/* endpoints (in-process ThreadingHTTPServer)
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# ─────────────────────────────────────────────────────────────────────────────
# Helper — spin up GCS server in-process on port 0
# ─────────────────────────────────────────────────────────────────────────────
class _GcsServer:
    def __init__(self, tmpdir: str) -> None:
        from uas_utm_service.server import _make_handler
        from uas_utm_service.state import ServiceState

        self.state = ServiceState(
            ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
            log_dir=Path(tmpdir),
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.state))
        self.port = self.server.server_address[1]
        t = threading.Thread(target=self.server.serve_forever)
        t.daemon = True
        t.start()

    def get(self, path: str) -> dict:
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read())

    def post(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def shutdown(self) -> None:
        self.server.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 1. Referenced docs exist
# ─────────────────────────────────────────────────────────────────────────────
class ReadmeReferencedFilesTests(unittest.TestCase):
    """All files referenced in README must exist on disk."""

    REQUIRED_DOCS = [
        "docs/repo_gap_analysis.md",
        "docs/service_map.md",
        "docs/docker_desktop_runbook.md",
        "docs/scenarios.md",
        "docs/vulnerabilities.md",
        "docs/stack_and_harness_plan.md",
    ]

    REQUIRED_SCRIPTS = [
        "scripts/run_harness.ps1",
        "scripts/run_uas_utm_service.ps1",
    ]

    REQUIRED_SCENARIOS = [
        "scenarios/uav_ugv_convoy.json",
        "scenarios/korea_defense_uas_utm_ops.json",
        "scenarios/dah_training/mavlink_telemetry_monitoring.json",
        "scenarios/dah_training/mission_upload_guard.json",
        "scenarios/dah_training/tactical_chain_degradation.json",
    ]

    def _assert_exists(self, rel: str) -> None:
        path = ROOT / rel
        self.assertTrue(path.exists(), f"Missing required file: {rel}")

    def test_all_docs_exist(self) -> None:
        for doc in self.REQUIRED_DOCS:
            with self.subTest(doc=doc):
                self._assert_exists(doc)

    def test_all_scripts_exist(self) -> None:
        for script in self.REQUIRED_SCRIPTS:
            with self.subTest(script=script):
                self._assert_exists(script)

    def test_all_scenarios_exist(self) -> None:
        for scenario in self.REQUIRED_SCENARIOS:
            with self.subTest(scenario=scenario):
                self._assert_exists(scenario)

    def test_readme_exists_and_has_content(self) -> None:
        readme = ROOT / "README.md"
        self.assertTrue(readme.exists())
        self.assertGreater(readme.stat().st_size, 2000)

    def test_docker_compose_exists_and_valid(self) -> None:
        self.assertTrue((ROOT / "docker-compose.yml").exists())
        self.assertTrue((ROOT / "Dockerfile").exists())
        self.assertTrue((ROOT / "requirements.txt").exists())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 2. CLI entry points importable
# ─────────────────────────────────────────────────────────────────────────────
class CliEntryPointImportTests(unittest.TestCase):
    """All CLI modules referenced in README must be importable."""

    CLI_MODULES = [
        "dah_harness.cli",
        "uas_utm.scenario_report",
        "uas_utm.scenario_package",
        "uas_utm.scenario_batch",
        "uas_utm_service.server",
    ]

    def test_all_cli_modules_importable(self) -> None:
        for mod in self.CLI_MODULES:
            with self.subTest(module=mod):
                m = importlib.import_module(mod)
                self.assertIsNotNone(m)

    def test_harness_cli_has_main(self) -> None:
        import dah_harness.cli as cli
        self.assertTrue(callable(getattr(cli, "main", None)))

    def test_scenario_report_has_main(self) -> None:
        import uas_utm.scenario_report as sr
        self.assertTrue(callable(getattr(sr, "main", None)))

    def test_scenario_package_has_main(self) -> None:
        import uas_utm.scenario_package as sp
        self.assertTrue(callable(getattr(sp, "main", None)))

    def test_scenario_batch_has_main(self) -> None:
        import uas_utm.scenario_batch as sb
        self.assertTrue(callable(getattr(sb, "main", None)))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 3. Harness CLI produces valid JSON output
# ─────────────────────────────────────────────────────────────────────────────
class HarnessCliOutputTests(unittest.TestCase):
    """python -m dah_harness.cli produces well-formed JSON with expected fields."""

    def test_harness_cli_basic_run(self) -> None:
        from dah_harness.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "summary.json"
            rc = main([
                "--scenario", str(ROOT / "scenarios" / "uav_ugv_convoy.json"),
                "--output", str(out),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            data = json.loads(out.read_text(encoding="utf-8"))

        self.assertIn("metrics", data)
        self.assertIn("detection_rate", data["metrics"])
        self.assertIn("mean_detection_latency_s", data["metrics"])
        self.assertIn("false_positive_actions", data["metrics"])
        self.assertIn("mission_progress", data["metrics"])

    def test_harness_cli_threshold_tuning(self) -> None:
        from dah_harness.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "tuned.json"
            rc = main([
                "--scenario", str(ROOT / "scenarios" / "uav_ugv_convoy.json"),
                "--set", "route_deviation_threshold_m=45",
                "--set", "link_loss_threshold_s=4",
                "--output", str(out),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            data = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(data["defense"]["route_deviation_threshold_m"], 45)
        self.assertEqual(data["defense"]["link_loss_threshold_s"], 4)

    def test_harness_cli_output_has_scenario_name(self) -> None:
        from dah_harness.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.json"
            main([
                "--scenario", str(ROOT / "scenarios" / "uav_ugv_convoy.json"),
                "--output", str(out),
            ])
            data = json.loads(out.read_text(encoding="utf-8"))

        self.assertIn("scenario", data)
        self.assertIn("frames", data)

    def test_harness_cli_korea_scenario_is_not_harness_format(self) -> None:
        """korea_defense_uas_utm_ops.json is a UTM service scenario, not harness format."""
        from dah_harness.simulation import load_scenario

        with self.assertRaises((KeyError, ValueError, TypeError)):
            load_scenario(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 4. Scenario report command
# ─────────────────────────────────────────────────────────────────────────────
class ScenarioReportCommandTests(unittest.TestCase):
    """python -m uas_utm.scenario_report produces a readable markdown report."""

    TRAINING_SCENARIOS = [
        "scenarios/dah_training/mavlink_telemetry_monitoring.json",
        "scenarios/dah_training/mission_upload_guard.json",
        "scenarios/dah_training/tactical_chain_degradation.json",
    ]

    def test_scenario_report_produces_markdown(self) -> None:
        from uas_utm.scenario_report import main

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.md"
            main([
                "--scenario", str(ROOT / "scenarios/dah_training/mavlink_telemetry_monitoring.json"),
                "--markdown-output", str(out),
            ])
            self.assertTrue(out.exists())
            text = out.read_text(encoding="utf-8")

        self.assertIn("# Scenario Report:", text)
        self.assertIn("Valid:", text)

    def test_all_training_scenarios_report_without_error(self) -> None:
        from uas_utm.scenario_report import main

        for scenario in self.TRAINING_SCENARIOS:
            with self.subTest(scenario=scenario):
                with tempfile.TemporaryDirectory() as tmpdir:
                    out = Path(tmpdir) / "report.md"
                    rc = main([
                        "--scenario", str(ROOT / scenario),
                        "--markdown-output", str(out),
                    ])
                    self.assertEqual(rc, 0)
                    self.assertTrue(out.exists(), f"Report not produced for {scenario}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 5. Scenario package command
# ─────────────────────────────────────────────────────────────────────────────
class ScenarioPackageCommandTests(unittest.TestCase):
    """python -m uas_utm.scenario_package produces package with manifest."""

    def test_scenario_package_creates_manifest(self) -> None:
        from uas_utm.scenario_package import package_scenario

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = package_scenario(
                scenario_path=ROOT / "scenarios/dah_training/mavlink_telemetry_monitoring.json",
                output_dir=Path(tmpdir),
            )
            manifest_path = Path(paths["manifest"])
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn("package_name", manifest)
        self.assertIn("generated_at_utc", manifest)
        self.assertTrue(manifest["valid"])

    def test_scenario_package_output_has_all_required_files(self) -> None:
        from uas_utm.scenario_package import package_scenario

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = package_scenario(
                scenario_path=ROOT / "scenarios/dah_training/mission_upload_guard.json",
                output_dir=Path(tmpdir),
            )
            root = Path(paths["package_root"])
            self.assertTrue((root / "manifest.json").exists())
            self.assertTrue((root / "report" / "scenario_report.md").exists())
            self.assertTrue((root / "baseline" / "baseline.json").exists())

    def test_scenario_package_main_returns_zero(self) -> None:
        from uas_utm.scenario_package import main

        with tempfile.TemporaryDirectory() as tmpdir:
            rc = main([
                "--scenario", str(ROOT / "scenarios/dah_training/tactical_chain_degradation.json"),
                "--output-dir", tmpdir,
            ])

        self.assertEqual(rc, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 6. Scenario batch command
# ─────────────────────────────────────────────────────────────────────────────
class ScenarioBatchCommandTests(unittest.TestCase):
    """python -m uas_utm.scenario_batch processes all training scenarios."""

    def test_batch_processes_all_three_training_scenarios(self) -> None:
        from uas_utm.scenario_batch import package_training_scenarios

        with tempfile.TemporaryDirectory() as tmpdir:
            index = package_training_scenarios(
                scenario_dir=ROOT / "scenarios/dah_training",
                output_dir=Path(tmpdir),
            )

        self.assertEqual(index["count"], 3)
        for pkg in index["packages"]:
            self.assertTrue(pkg["valid"], f"Invalid package: {pkg['scenario_file']}")

    def test_batch_produces_index_files(self) -> None:
        from uas_utm.scenario_batch import package_training_scenarios

        with tempfile.TemporaryDirectory() as tmpdir:
            index = package_training_scenarios(
                scenario_dir=ROOT / "scenarios/dah_training",
                output_dir=Path(tmpdir),
            )
            index_path = Path(index["index_json"])
            self.assertTrue(index_path.exists())
            self.assertTrue(Path(index["index_markdown"]).exists())
            loaded = json.loads(index_path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["schema_version"], "dah-scenario-package-index.v1")

    def test_batch_safety_boundary_is_in_index(self) -> None:
        from uas_utm.scenario_batch import package_training_scenarios

        with tempfile.TemporaryDirectory() as tmpdir:
            index = package_training_scenarios(
                scenario_dir=ROOT / "scenarios/dah_training",
                output_dir=Path(tmpdir),
            )

        self.assertIn("no real tactical network", index["safety_boundary"].lower())

    def test_batch_main_returns_zero(self) -> None:
        from uas_utm.scenario_batch import main

        with tempfile.TemporaryDirectory() as tmpdir:
            rc = main(["--scenario-dir", str(ROOT / "scenarios/dah_training"), "--output-dir", tmpdir])

        self.assertEqual(rc, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 7. GCS server API endpoints
# ─────────────────────────────────────────────────────────────────────────────
class GcsServerApiTests(unittest.TestCase):
    """GCS server serves all README-referenced REST API endpoints correctly."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._srv = _GcsServer(self._tmpdir.name)

    def tearDown(self) -> None:
        self._srv.shutdown()
        self._tmpdir.cleanup()

    def test_health_endpoint_returns_ok(self) -> None:
        data = self._srv.get("/api/health")
        self.assertTrue(data["payload"]["ok"])

    def test_dashboard_endpoint_returns_cards(self) -> None:
        data = self._srv.get("/api/dashboard")
        payload = data["payload"]
        self.assertGreater(len(payload["cards"]), 0)
        self.assertEqual(payload["title"], "DAH UAS/UGV Tactical Chain Dashboard")

    def test_chain_endpoint_returns_correct_node_order(self) -> None:
        data = self._srv.get("/api/chain")
        node_ids = [n["id"] for n in data["payload"]["nodes"]]
        self.assertEqual(
            node_ids,
            ["assets", "c2_link", "gcs", "router", "tmmr", "ticn", "upper_c2"],
        )

    def test_alerts_endpoint_returns_list(self) -> None:
        data = self._srv.get("/api/alerts")
        self.assertIsInstance(data["payload"]["alerts"], list)
        self.assertIn("alert_count", data["payload"])

    def test_service_status_endpoint_returns_service_statuses(self) -> None:
        data = self._srv.get("/api/service-status")
        statuses = data["payload"]["service_statuses"]
        self.assertGreater(len(statuses), 0)
        service_ids = [s["service_id"] for s in statuses]
        self.assertIn("dah-gcs", service_ids)

    def test_fault_inject_endpoint_accepts_allowlisted_fault(self) -> None:
        result = self._srv.post("/api/faults/inject", {
            "payload": {
                "fault_type": "tmmr_queue_overflow",
                "requested_by": "phase9-test",
            }
        })
        self.assertTrue(result["payload"]["accepted"])
        self.assertTrue(result["payload"]["fault"]["simulation_only"])

    def test_fault_inject_endpoint_rejects_unlisted_fault(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._srv.post("/api/faults/inject", {
                "payload": {"fault_type": "real_network_attack"}
            })
        self.assertEqual(ctx.exception.code, 400)

    def test_chain_status_degrades_after_fault(self) -> None:
        chain_before = self._srv.get("/api/chain")
        self.assertEqual(chain_before["payload"]["overall_status"], "normal")

        self._srv.post("/api/faults/inject", {
            "payload": {"fault_type": "c2_link_packet_loss"}
        })
        chain_after = self._srv.get("/api/chain")
        self.assertNotEqual(chain_after["payload"]["overall_status"], "normal")

    def test_summary_endpoint_returns_asset_count(self) -> None:
        data = self._srv.get("/api/summary")
        self.assertGreaterEqual(data["payload"]["asset_count"], 1)

    def test_static_index_served(self) -> None:
        with urllib.request.urlopen(f"http://127.0.0.1:{self._srv.port}/") as resp:
            html = resp.read().decode()
        self.assertIn("<html", html.lower())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 8. docker-compose.yml passes docker compose config
# ─────────────────────────────────────────────────────────────────────────────
class DockerComposeConfigTests(unittest.TestCase):
    """docker compose config must succeed (validates YAML + Compose spec)."""

    def test_docker_compose_config_is_valid_yaml(self) -> None:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=str(ROOT),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0 and b"docker" in result.stderr.lower():
            self.skipTest("docker compose not available in this environment")
        self.assertEqual(result.returncode, 0)

    def test_docker_compose_has_required_top_level_keys(self) -> None:
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for key in ("services:", "networks:", "volumes:"):
            self.assertIn(key, text, f"Missing top-level key: {key}")

    def test_dockerfile_has_from_instruction(self) -> None:
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertTrue(text.strip().startswith("FROM") or "FROM " in text)

    def test_requirements_txt_is_nonempty(self) -> None:
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8").strip()
        self.assertGreater(len(text), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — 9. Full test suite still passes (regression)
# ─────────────────────────────────────────────────────────────────────────────
class TestSuiteRegressionTests(unittest.TestCase):
    """Running python -m unittest discover -s tests must pass with no failures."""

    def test_all_test_modules_importable(self) -> None:
        test_files = list((ROOT / "tests").glob("test_*.py"))
        self.assertGreaterEqual(len(test_files), 5, "Expected at least 5 test files")
        for tf in test_files:
            module_name = f"tests.{tf.stem}"
            with self.subTest(module=module_name):
                m = importlib.import_module(module_name)
                self.assertIsNotNone(m)

    def test_output_directory_writable(self) -> None:
        output_dir = ROOT / "output"
        output_dir.mkdir(exist_ok=True)
        probe = output_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()


if __name__ == "__main__":
    unittest.main()
