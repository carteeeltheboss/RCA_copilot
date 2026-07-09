#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BACKEND_URL="${RCA_BACKEND_URL:-http://127.0.0.1:8000}"
OLLAMA_URL="${MSI_OLLAMA_URL:-http://100.125.17.77:11434}"
MODEL_NAME="${MSI_OLLAMA_MODEL:-qwen2.5-coder:7b}"
HORIZON_URL="${HORIZON_URL:-http://127.0.0.1/dashboard/}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

failures=0

ok() { printf 'OK   %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; failures=$((failures + 1)); }
warn() { printf 'WARN %s\n' "$1"; }

check_container() {
  local name="$1"
  local status
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
  if [[ "$status" == "healthy" || "$status" == "running" ]]; then
    ok "container ${name} is ${status}"
  else
    fail "container ${name} is ${status:-missing}"
  fi
}

check_container rca-copilot-mongodb
check_container rca-copilot-backend
check_container rca-copilot-parser-worker
check_container rca-copilot-correlation-worker
check_container rca-copilot-incident-worker
check_container rca-copilot-enrichment-worker

if curl -fsS "${BACKEND_URL}/health" >/tmp/rca_validation_health.json; then
  ok "backend /health reachable"
else
  fail "backend /health unreachable"
fi

if curl -fsS "${BACKEND_URL}/api/v1/system/health" >/tmp/rca_validation_system_health.json; then
  ok "system health API reachable"
  python3 - <<'PY' || true
import json
data = json.load(open('/tmp/rca_validation_system_health.json'))
for item in data.get('components', data if isinstance(data, list) else []):
    name = str(item.get('component') or item.get('name') or '').lower()
    status = item.get('status')
    if 'collector' in name:
        print(f"OK   collector status reported as {status}")
        break
else:
    print("WARN collector status not present in system health response")
PY
else
  fail "system health API unreachable"
fi

if curl -fsS -L --max-time 10 "$HORIZON_URL" >/tmp/rca_validation_horizon.html; then
  ok "Horizon reachable"
else
  fail "Horizon unreachable at ${HORIZON_URL}"
fi

if curl -fsS --max-time 10 "${OLLAMA_URL}/api/tags" >/tmp/rca_validation_ollama_tags.json; then
  if python3 - "$MODEL_NAME" <<'PY'
import json, sys
model = sys.argv[1]
data = json.load(open('/tmp/rca_validation_ollama_tags.json'))
names = [item.get('name') for item in data.get('models', []) if isinstance(item, dict)]
raise SystemExit(0 if model in names else 1)
PY
  then
    ok "MSI Ollama reachable with ${MODEL_NAME}"
  else
    fail "MSI Ollama reachable but ${MODEL_NAME} not listed"
  fi
else
  fail "MSI Ollama unreachable"
fi

if [[ -z "${RCA_INTERNAL_SERVICE_TOKEN:-}" ]]; then
  fail "RCA_INTERNAL_SERVICE_TOKEN is missing from environment"
else
  if curl -fsS -H "X-RCA-Service-Token: ${RCA_INTERNAL_SERVICE_TOKEN}" "${BACKEND_URL}/api/v1/providers/active" >/tmp/rca_validation_active_provider.json; then
    if python3 - <<'PY'
import json
data = json.load(open('/tmp/rca_validation_active_provider.json'))
items = data if isinstance(data, list) else data.get('items', [])
llm = [item for item in items if item.get('provider_type') == 'llm']
raise SystemExit(0 if llm else 1)
PY
    then
      ok "active LLM provider exists"
    else
      fail "active LLM provider missing"
    fi
  else
    fail "active provider API unavailable"
  fi
fi

if curl -fsS "${BACKEND_URL}/api/v1/incidents?page_size=1&status=enriched" >/tmp/rca_validation_one_incident.json; then
  incident_id="$(python3 - <<'PY'
import json
data = json.load(open('/tmp/rca_validation_one_incident.json'))
items = data.get('items', []) if isinstance(data, dict) else []
print(items[0].get('incident_id', '') if items else '')
PY
)"
  if [[ -n "$incident_id" && -n "${RCA_INTERNAL_SERVICE_TOKEN:-}" ]]; then
    if curl -fsS --max-time 120 -X POST -H "X-RCA-Service-Token: ${RCA_INTERNAL_SERVICE_TOKEN}" "${BACKEND_URL}/api/v1/incidents/${incident_id}/explain" >/tmp/rca_validation_explain_check.json; then
      ok "explain endpoint available"
    else
      fail "explain endpoint call failed"
    fi
  else
    warn "no enriched incident available for explain readiness check"
  fi
else
  fail "incident API unavailable"
fi

if (( failures > 0 )); then
  printf '\nSystem readiness failed with %d failure(s).\n' "$failures"
  exit 1
fi

printf '\nSystem readiness passed.\n'

