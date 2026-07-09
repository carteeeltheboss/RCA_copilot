#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RESULTS_DIR="$ROOT_DIR/validation/results"
mkdir -p "$RESULTS_DIR"

run_id="$(date -u +%Y%m%dT%H%M%SZ)"
injection_json="$RESULTS_DIR/injection_${run_id}.json"
incident_json="$RESULTS_DIR/found_incident_${run_id}.json"
evaluation_json="$RESULTS_DIR/evaluation_${run_id}.json"

echo "== Check system readiness =="
bash validation/scripts/check_system_ready.sh

echo "== Capture baseline =="
baseline_path="$(python3 validation/scripts/capture_baseline.py)"
echo "baseline=${baseline_path}"

echo "== Inject fake error =="
python3 validation/scripts/inject_fake_error.py --json-out "$injection_json"

request_id="$(python3 - "$injection_json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["request_id"])
PY
)"
resource_id="$(python3 - "$injection_json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["resource_id"])
PY
)"

echo "== Wait for new incident =="
python3 validation/scripts/find_new_incidents.py \
  --request-id "$request_id" \
  --resource-id "$resource_id" \
  --message-fragment "Build failed due to timeout" \
  --timeout "${VALIDATION_TIMEOUT_SECONDS:-240}" \
  --interval 5 \
  --json-out "$incident_json"

incident_id="$(python3 - "$incident_json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["incident_id"])
PY
)"

echo "== Evaluate incident =="
python3 validation/scripts/evaluate_incident.py "$incident_id" \
  --expected-service "devstack@n-cpu.service" \
  --json-out "$evaluation_json"

echo "== Safe validation summary =="
echo "baseline=${baseline_path}"
echo "injection_metadata=${injection_json}"
echo "incident_metadata=${incident_json}"
echo "evaluation=${evaluation_json}"
echo "request_id=${request_id}"
echo "resource_id=${resource_id}"
echo "incident_id=${incident_id}"

