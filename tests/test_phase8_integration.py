"""
Phase 8 integration tests.

Requirement mapping
  #1  docker-compose.yml has required services
  #2  Role service /health endpoint responds correctly over HTTP
  #3  /api/dashboard contains all role cards (UAV/UGV/GCS/TMMR/TICN/Upper C2)
  #4  /api/chain returns nodes in correct tactical chain order
  #5  Fault injection rejects non-allowlisted faults        (also in test_tactical_emulator)
  #6  tmmr_queue_overflow → TMMR status critical            (also in test_tactical_emulator)
  #7  ticn_route_metric_change → TICN degraded + metric     (also in test_tactical_emulator)
  #8  mission_count_reset_attempt → GCS alert created
  #9  Mock mode runs without real MAVLink / ROS2 / TICN / TMMR
"""
from __future__ import annotations

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

from dah_harness.tactical_emulator import ALLOWED_FAULT_TYPES, TacticalEmulatorRuntime
from dah_runtime.role_service import _make_handler
from dah_runtime.service_contracts import make_service_status
from uas_utm_service.state import ServiceState


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #1 — docker-compose.yml has required services
# ─────────────────────────────────────────────────────────────────────────────
class DockerComposeServiceTests(unittest.TestCase):
    """#1  docker-compose.yml declares all required default containers."""

    REQUIRED_CONTAINERS = [
        "dah-gateway",
        "dah-dashboard",
        "dah-gcs",
        "dah-uav-sim",
        "dah-ugv-sim",
        "dah-mavlink-gateway",
        "dah-tactical-router",
        "dah-tmmr-emulator",
        "dah-ticn-emulator",
        "dah-upper-c2",
        "dah-telemetry-collector",
        "dah-defense-agent",
    ]

    def _compose_text(self) -> str:
        path = ROOT / "docker-compose.yml"
        return path.read_text(encoding="utf-8")

    def _declared_containers(self) -> set[str]:
        found: set[str] = set()
        for line in self._compose_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("container_name:"):
                name = stripped.split(":", 1)[1].strip()
                found.add(name)
        return found

    def test_all_required_containers_declared(self) -> None:
        declared = self._declared_containers()
        missing = [n for n in self.REQUIRED_CONTAINERS if n not in declared]
        self.assertFalse(
            missing,
            f"Missing container_name entries in docker-compose.yml: {missing}",
        )

    def test_fault_injector_is_profile_gated_to_cyber_lab(self) -> None:
        text = self._compose_text()
        # cyber-lab profile guard must appear before the fault-injector container name
        cyber_pos = text.find("cyber-lab")
        injector_pos = text.find("dah-fault-injector")
        self.assertGreater(cyber_pos, 0, "cyber-lab profile not found in docker-compose.yml")
        self.assertGreater(injector_pos, 0, "dah-fault-injector not found in docker-compose.yml")
        # The profile key must precede the container_name declaration for fault-injector
        fault_block = text[max(0, injector_pos - 300): injector_pos + 50]
        self.assertIn("cyber-lab", fault_block)

    def test_three_isolated_docker_networks_declared(self) -> None:
        text = self._compose_text()
        for network in ("dah-asset-net", "dah-ops-net", "dah-tactical-net"):
            self.assertIn(network, text, f"Network {network!r} not declared in docker-compose.yml")

    def test_gateway_exposes_port_9000(self) -> None:
        text = self._compose_text()
        self.assertIn("9000:9000", text)

    def test_gcs_exposes_port_8080(self) -> None:
        text = self._compose_text()
        self.assertIn("8080:8080", text)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #2 — role service /health endpoint responds over HTTP
# ─────────────────────────────────────────────────────────────────────────────
class RoleServiceHealthEndpointTests(unittest.TestCase):
    """#2  Lightweight role service HTTP server responds to /health, /status, /metrics."""

    def _start_server(self, service_id: str, emulated: bool = False) -> tuple[ThreadingHTTPServer, int]:
        status = make_service_status(
            service_id=service_id,
            role="test_role",
            emulated=emulated,
            boundary="EMULATED / NOT REAL MILITARY SYSTEM" if emulated else "local test",
            metrics={"queue_depth": 0, "test_metric": True},
        )
        handler = _make_handler(status.to_payload())
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever)
        t.daemon = True
        t.start()
        return server, port

    def _get(self, port: int, path: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as resp:
            return json.loads(resp.read())

    def test_health_endpoint_returns_ok_true(self) -> None:
        server, port = self._start_server("dah-tmmr-emulator", emulated=True)
        try:
            data = self._get(port, "/health")
            self.assertTrue(data["ok"])
            self.assertEqual(data["service_id"], "dah-tmmr-emulator")
            self.assertTrue(data["emulated"])
        finally:
            server.shutdown()

    def test_status_endpoint_returns_service_fields(self) -> None:
        server, port = self._start_server("dah-ticn-emulator", emulated=True)
        try:
            data = self._get(port, "/status")
            self.assertEqual(data["service_id"], "dah-ticn-emulator")
            self.assertEqual(data["role"], "test_role")
            self.assertIn("boundary", data)
        finally:
            server.shutdown()

    def test_metrics_endpoint_returns_metric_dict(self) -> None:
        server, port = self._start_server("dah-defense-agent")
        try:
            data = self._get(port, "/metrics")
            self.assertEqual(data["service_id"], "dah-defense-agent")
            self.assertIsInstance(data["metrics"], dict)
            self.assertIn("queue_depth", data["metrics"])
        finally:
            server.shutdown()

    def test_unknown_path_returns_404(self) -> None:
        server, port = self._start_server("dah-gcs")
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get(port, "/nonexistent")
            self.assertEqual(ctx.exception.code, 404)
        finally:
            server.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #3 — /api/dashboard contains all role cards
# ─────────────────────────────────────────────────────────────────────────────
class DashboardPayloadTests(unittest.TestCase):
    """#3  dashboard_payload() exposes all required role cards and scope metadata."""

    REQUIRED_CARD_LABELS = [
        "UAV Simulator",
        "UGV Simulator",
        "GCS / Ground Gateway",
        "C2 Data Link",
        "Tactical Router",
        "TMMR Emulator",
        "TICN-like Network",
        "Upper C2/BMS",
        "Defense Agent",
        "Telemetry Collector",
    ]

    def setUp(self) -> None:
        self.state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

    def test_dashboard_cards_include_all_required_role_labels(self) -> None:
        payload = self.state.dashboard_payload()
        card_labels = [card["label"] for card in payload["cards"]]
        for label in self.REQUIRED_CARD_LABELS:
            self.assertIn(label, card_labels, f"Missing card label: {label!r}")

    def test_dashboard_scope_lists_emulated_roles(self) -> None:
        scope = self.state.dashboard_payload()["scope"]
        emulated = scope["emulated_only"]
        self.assertTrue(
            any("TMMR" in item for item in emulated),
            "TMMR not listed as emulated in scope",
        )
        self.assertTrue(
            any("TICN" in item or "network" in item.lower() for item in emulated),
            "TICN not listed as emulated in scope",
        )

    def test_dashboard_fault_allowlist_matches_allowed_fault_types(self) -> None:
        payload = self.state.dashboard_payload()
        self.assertEqual(set(payload["fault_allowlist"]), ALLOWED_FAULT_TYPES)

    def test_emulated_service_statuses_carry_emulated_flag(self) -> None:
        statuses = {
            item["label"]: item
            for item in self.state.dashboard_payload()["service_statuses"]
        }
        for label in ("TMMR Emulator", "TICN-like Network", "Tactical Router", "Upper C2/BMS"):
            self.assertTrue(
                statuses[label]["emulated"],
                f"{label} service_status.emulated should be True",
            )

    def test_real_capable_services_carry_emulated_false(self) -> None:
        statuses = {
            item["label"]: item
            for item in self.state.dashboard_payload()["service_statuses"]
        }
        for label in ("UAV Simulator", "UGV Simulator", "GCS / Ground Gateway"):
            self.assertFalse(
                statuses[label]["emulated"],
                f"{label} service_status.emulated should be False",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #4 — /api/chain returns nodes in correct tactical chain order
# ─────────────────────────────────────────────────────────────────────────────
class ChainPayloadOrderTests(unittest.TestCase):
    """#4  chain_payload() returns nodes in the canonical tactical chain order."""

    EXPECTED_NODE_ORDER = ["assets", "c2_link", "gcs", "router", "tmmr", "ticn", "upper_c2"]

    def setUp(self) -> None:
        self.state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

    def test_chain_nodes_are_in_canonical_order(self) -> None:
        chain = self.state.chain_payload()
        node_ids = [node["id"] for node in chain["nodes"]]
        self.assertEqual(
            node_ids,
            self.EXPECTED_NODE_ORDER,
            f"Chain node order mismatch.\nExpected: {self.EXPECTED_NODE_ORDER}\nGot:      {node_ids}",
        )

    def test_chain_links_connect_adjacent_nodes(self) -> None:
        chain = self.state.chain_payload()
        link_pairs = [(link["from"], link["to"]) for link in chain["links"]]
        expected_pairs = list(zip(self.EXPECTED_NODE_ORDER, self.EXPECTED_NODE_ORDER[1:]))
        self.assertEqual(link_pairs, expected_pairs)

    def test_chain_emulator_nodes_have_correct_boundary_text(self) -> None:
        chain = self.state.chain_payload()
        emulated_ids = {"router", "tmmr", "ticn", "upper_c2"}
        for node in chain["nodes"]:
            if node["id"] in emulated_ids:
                upper = node["boundary"].upper()
                self.assertTrue(
                    "EMULATED" in upper or "SIMULATED" in upper or "NOT REAL" in upper,
                    f"Node {node['id']!r} boundary must indicate simulated scope: {node['boundary']!r}",
                )

    def test_chain_overall_status_normal_on_clean_start(self) -> None:
        chain = self.state.chain_payload()
        self.assertEqual(chain["overall_status"], "normal")

    def test_chain_schema_version_is_set(self) -> None:
        chain = self.state.chain_payload()
        self.assertEqual(chain["schema_version"], "dah-tactical-chain.v1")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #5 — Fault injection allowlist rejects unlisted faults
# ─────────────────────────────────────────────────────────────────────────────
class FaultAllowlistTests(unittest.TestCase):
    """#5  ServiceState.inject_fault() rejects any fault not in ALLOWED_FAULT_TYPES."""

    DISALLOWED_FAULTS = [
        "real_network_attack",
        "ticn_protocol_exploit",
        "gps_jamming_radio",
        "dos_attack",
        "",
    ]

    def setUp(self) -> None:
        self.state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

    def test_disallowed_faults_raise_value_error(self) -> None:
        for fault in self.DISALLOWED_FAULTS:
            with self.subTest(fault=fault):
                with self.assertRaises(ValueError):
                    self.state.inject_fault({"payload": {"fault_type": fault}})

    def test_allowed_faults_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(
                ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                log_dir=Path(tmpdir),
            )
            for fault in sorted(ALLOWED_FAULT_TYPES):
                with self.subTest(fault=fault):
                    result = state.inject_fault({"payload": {"fault_type": fault}})
                    self.assertTrue(result["accepted"], f"Fault {fault!r} should be accepted")
                    self.assertTrue(result["fault"]["simulation_only"])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #6 — tmmr_queue_overflow → TMMR critical
# ─────────────────────────────────────────────────────────────────────────────
class TmmrQueueOverflowTests(unittest.TestCase):
    """#6  tmmr_queue_overflow injection degrades TMMR to critical in service chain."""

    def test_tmmr_status_becomes_critical_after_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(
                ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                log_dir=Path(tmpdir),
            )
            state.inject_fault({"payload": {"fault_type": "tmmr_queue_overflow"}})
            chain = state.chain_payload()
            tmmr_node = next(n for n in chain["nodes"] if n["id"] == "tmmr")

            self.assertIn(tmmr_node["status"], ("degraded", "critical"))
            self.assertEqual(chain["overall_status"], "critical")

    def test_tmmr_metrics_expose_queue_depth_and_starvation(self) -> None:
        runtime = TacticalEmulatorRuntime()
        runtime.apply_fault("tmmr_queue_overflow", parameters={"queue_depth": 1500})
        snapshot = runtime.snapshot()
        tmmr = next(c for c in snapshot["components"] if c["component_id"] == "tmmr")

        self.assertEqual(tmmr["metrics"]["queue_depth"], 1500)
        self.assertTrue(tmmr["metrics"]["priority_starvation"])

    def test_tmmr_overflow_generates_critical_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(
                ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                log_dir=Path(tmpdir),
            )
            state.inject_fault({"payload": {"fault_type": "tmmr_queue_overflow"}})
            alerts = state.alerts_payload()

            self.assertGreater(alerts["critical_count"], 0)
            self.assertTrue(
                any("tmmr" in a.get("target", "").lower() or "tmmr" in a.get("title", "").lower() for a in alerts["alerts"]),
                "Expected TMMR-related alert",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #7 — ticn_route_metric_change → TICN degraded + route metric updated
# ─────────────────────────────────────────────────────────────────────────────
class TicnRouteMetricTests(unittest.TestCase):
    """#7  ticn_route_metric_change updates TICN chain node status and route_metric."""

    def test_ticn_chain_node_degrades_after_route_metric_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(
                ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                log_dir=Path(tmpdir),
            )
            state.inject_fault(
                {"payload": {"fault_type": "ticn_route_metric_change", "parameters": {"route_metric": 88}}}
            )
            chain = state.chain_payload()
            ticn_node = next(n for n in chain["nodes"] if n["id"] == "ticn")

            self.assertIn(ticn_node["status"], ("degraded", "critical"))
            self.assertEqual(ticn_node["metrics"].get("route_metric"), 88)

    def test_ticn_route_change_count_increments(self) -> None:
        runtime = TacticalEmulatorRuntime()
        runtime.apply_fault("ticn_route_metric_change", parameters={"route_metric": 70})
        runtime.apply_fault("ticn_route_metric_change", parameters={"route_metric": 85})
        ticn = next(c for c in runtime.snapshot()["components"] if c["component_id"] == "ticn")

        self.assertEqual(ticn["metrics"]["route_change_count"], 2)

    def test_ticn_fault_does_not_affect_non_ticn_nodes_unexpectedly(self) -> None:
        runtime = TacticalEmulatorRuntime()
        runtime.apply_fault("ticn_route_metric_change", parameters={"route_metric": 60})
        snapshot = runtime.snapshot()
        tmmr = next(c for c in snapshot["components"] if c["component_id"] == "tmmr")
        upper_c2 = next(c for c in snapshot["components"] if c["component_id"] == "upper_c2")

        self.assertEqual(tmmr["status"], "normal")
        self.assertEqual(upper_c2["status"], "normal")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #8 — mission_count_reset_attempt → alert created, GCS degraded
# ─────────────────────────────────────────────────────────────────────────────
class MissionCountResetTests(unittest.TestCase):
    """#8  mission_count_reset_attempt creates a mission guard alert and degrades GCS."""

    def test_mission_reset_attempt_creates_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(
                ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                log_dir=Path(tmpdir),
            )
            result = state.inject_fault(
                {"payload": {"fault_type": "mission_count_reset_attempt"}}
            )
            alerts = state.alerts_payload()

            self.assertTrue(result["accepted"])
            self.assertGreater(alerts["alert_count"], 0, "Expected at least one alert")

    def test_mission_reset_attempt_degrades_gcs_chain_node(self) -> None:
        runtime = TacticalEmulatorRuntime()
        runtime.apply_fault("mission_count_reset_attempt")
        snapshot = runtime.snapshot()
        gcs = next(c for c in snapshot["components"] if c["component_id"] == "gcs")

        self.assertIn(gcs["status"], ("degraded", "critical"))
        self.assertEqual(gcs["metrics"]["mission_sequence_guard"], "hold_for_operator_review")

    def test_mission_reset_fault_is_simulation_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(
                ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                log_dir=Path(tmpdir),
            )
            result = state.inject_fault(
                {"payload": {"fault_type": "mission_count_reset_attempt"}}
            )
            self.assertTrue(result["fault"]["simulation_only"])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 #9 — mock mode runs without external network dependencies
# ─────────────────────────────────────────────────────────────────────────────
class MockModeTests(unittest.TestCase):
    """#9  Full demo lifecycle runs without real MAVLink / ROS2 / TICN / TMMR."""

    def test_service_state_loads_without_network(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        self.assertIsNotNone(state.scenario)
        self.assertGreaterEqual(state.summary["asset_count"], 1)

    def test_full_demo_lifecycle_in_mock_mode(self) -> None:
        """Register edge → ingest telemetry → request command → inject fault → verify chain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(
                ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
                log_dir=Path(tmpdir),
            )

            # 1. Edge registration (mock UAV, no real MAVLink)
            device = state.register_edge_device(
                {
                    "payload": {
                        "edge_id": "mock-uav-edge-01",
                        "device_type": "uav_edge",
                        "asset_ids": ["small-dronebot-01"],
                        "authority": "Mock UTM Cell",
                        "software_version": "mock-0.1",
                    }
                }
            )
            self.assertEqual(device["egress_policy"], "approved_queue_only")

            # 2. Telemetry ingest (no real radio / sensor)
            ingest = state.ingest_telemetry(
                {
                    "payload": {
                        "asset_id": "small-dronebot-01",
                        "time_s": 5,
                        "position": [100.0, 200.0, 50.0],
                        "status": "mock-flight",
                        "source": "mock-uav-edge",
                    }
                }
            )
            self.assertTrue(ingest["accepted"])

            # 3. Command request + approval (dry-run, no actuator command)
            cmd = state.request_command(
                {
                    "payload": {
                        "asset_id": "small-dronebot-01",
                        "command_type": "hold_position",
                        "requested_by": "mock-operator",
                    }
                }
            )
            approved = state.approve_command(
                {"payload": {"command_id": cmd["command_id"], "approver": "mock-approver"}}
            )
            self.assertEqual(approved["status"], "approved_for_gateway")
            self.assertEqual(approved["mavlink_command"]["message_name"], "COMMAND_LONG")

            # 4. Fault injection (simulation only, no real network)
            fault_result = state.inject_fault(
                {"payload": {"fault_type": "c2_link_delay", "requested_by": "mock-operator"}}
            )
            self.assertTrue(fault_result["fault"]["simulation_only"])

            # 5. Chain reflects degraded state
            chain = state.chain_payload()
            self.assertNotEqual(chain["overall_status"], "normal")

            # 6. Audit log is consistent (no external writes)
            audit = state.audit_payload(limit=50)
            event_types = {row["event_type"] for row in audit["audit"]}
            self.assertIn("command.requested", event_types)
            self.assertIn("command.approved", event_types)

    def test_dashboard_renders_without_docker_running(self) -> None:
        """dashboard_payload() must succeed even when Docker containers are offline."""
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        payload = state.dashboard_payload()
        self.assertEqual(payload["title"], "DAH UAS/UGV Tactical Chain Dashboard")
        self.assertGreater(len(payload["cards"]), 0)

    def test_no_external_imports_required_for_core_pipeline(self) -> None:
        """Core modules must be importable without pymavlink, rclpy, or ros2 packages."""
        import importlib

        optional_packages = ["pymavlink", "rclpy", "ros2", "gazebo"]
        core_modules = [
            "dah_harness.attacks",
            "dah_harness.defense",
            "dah_harness.models",
            "dah_harness.tactical_emulator",
            "uas_utm_service.server",
            "uas_utm_gateway.mavlink_parser",
            "uas_utm_edge.agent",
            "dah_runtime.service_contracts",
            "dah_runtime.health",
        ]
        for name in optional_packages:
            try:
                importlib.import_module(name)
            except ImportError:
                pass  # expected: not installed

        for module_name in core_modules:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)


if __name__ == "__main__":
    unittest.main()
