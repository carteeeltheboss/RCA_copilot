#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
OLLAMA_URL="${OLLAMA_URL:-http://100.125.17.77:11434}"
MODEL_NAME="${MODEL_NAME:-qwen2.5-coder:7b}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if [[ -z "${RCA_INTERNAL_SERVICE_TOKEN:-}" && -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${RCA_INTERNAL_SERVICE_TOKEN:-}" ]]; then
  echo "RCA_INTERNAL_SERVICE_TOKEN is not set"
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

echo "Checking backend health..."
curl -fsS "$BACKEND_URL/health" > "$tmp_dir/health.json"
"$PYTHON_BIN" - "$tmp_dir/health.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data.get("status") == "ok", data
print("backend health: ok")
PY

echo "Checking MSI Ollama tags..."
curl -fsS "$OLLAMA_URL/api/tags" > "$tmp_dir/tags.json"
"$PYTHON_BIN" - "$tmp_dir/tags.json" "$MODEL_NAME" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
model = sys.argv[2]
models = [item.get("name") for item in data.get("models", [])]
if model not in models:
    raise SystemExit(f"model not found: {model}")
print(f"ollama model: {model}")
PY

echo "Checking active LLM provider..."
curl -fsS -H "X-RCA-Service-Token: ${RCA_INTERNAL_SERVICE_TOKEN}" "$BACKEND_URL/api/v1/providers/active" > "$tmp_dir/providers.json"
"$PYTHON_BIN" - "$tmp_dir/providers.json" "$MODEL_NAME" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
model = sys.argv[2]
providers = [item for item in data.get("items", []) if item.get("provider_type") == "llm" and item.get("active") and item.get("enabled")]
if not providers:
    raise SystemExit("no active LLM provider")
provider = providers[0]
print(f"active provider: {provider.get('provider_id')} ({provider.get('provider_kind')} {provider.get('model_name')})")
if provider.get("model_name") != model:
    raise SystemExit(f"active LLM provider uses unexpected model: {provider.get('model_name')}")
PY

echo "Finding enriched incident..."
curl -fsS "$BACKEND_URL/api/v1/incidents?status=enriched&page_size=1&sort=newest" > "$tmp_dir/incidents.json"
incident_id="$("$PYTHON_BIN" - "$tmp_dir/incidents.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("items", [])
if not items:
    raise SystemExit("no enriched incidents found")
print(items[0]["incident_id"])
PY
)"
echo "incident: ${incident_id}"

echo "Requesting explanation..."
curl -fsS \
  -H "X-RCA-Service-Token: ${RCA_INTERNAL_SERVICE_TOKEN}" \
  -X POST \
  "$BACKEND_URL/api/v1/incidents/${incident_id}/explain" > "$tmp_dir/explain.json"

"$PYTHON_BIN" - "$tmp_dir/explain.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps({
    "incident_id": data.get("incident_id"),
    "status": data.get("status"),
    "provider": data.get("provider"),
    "answer": data.get("answer"),
}, indent=2))
PY
