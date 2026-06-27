#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
UDP_PORT="${UDP_PORT:-14551}"

ok() { printf '[OK] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1" >&2; exit 1; }
warn() { printf '[WARN] %s\n' "$1" >&2; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "$1 is not installed or not in PATH"; }

need_cmd docker
need_cmd curl
need_cmd python3

docker version >/dev/null 2>&1 || fail "Docker daemon is not reachable"
ok "Docker daemon reachable"

docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not available"
ok "Docker Compose available"

[ -f "$COMPOSE_FILE" ] || fail "compose file not found: $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config >/dev/null
ok "Compose config is valid"

if docker compose -f "$COMPOSE_FILE" ps --services --filter status=running | grep -q '^uas-utm-service$'; then
  ok "uas-utm-service is running"
else
  warn "uas-utm-service is not running; run: docker compose up --build -d"
fi

health="$(curl -fsS "$BASE_URL/api/health" || true)"
[ -n "$health" ] || fail "health endpoint is not reachable: $BASE_URL/api/health"
printf '%s' "$health" | python3 -m json.tool >/dev/null
ok "Health endpoint returns JSON"

protocol="$(curl -fsS "$BASE_URL/api/protocol" || true)"
printf '%s' "$protocol" | python3 -m json.tool >/dev/null || fail "protocol endpoint did not return JSON"
printf '%s' "$protocol" | grep -q 'TTA-UAS-UTM-SIM' || fail "protocol profile mismatch"
ok "Protocol endpoint OK"

baseline="$(curl -fsS "$BASE_URL/api/baseline/export?limit=5" || true)"
printf '%s' "$baseline" | python3 -m json.tool >/dev/null || fail "baseline export endpoint did not return JSON"
printf '%s' "$baseline" | grep -q 'uav_ugv_joint_tracking_enabled' || fail "baseline export missing DAH baseline notes"
ok "Baseline export endpoint OK"

if command -v ss >/dev/null 2>&1; then
  if ss -lun | grep -q ":$UDP_PORT"; then
    ok "UDP $UDP_PORT appears to be listening"
  else
    warn "UDP $UDP_PORT is not visible as listening; bidirectional gateway may be stopped"
  fi
else
  warn "ss command unavailable; skipping UDP port check"
fi

printf '\nDAH Kali runtime check completed.\n'