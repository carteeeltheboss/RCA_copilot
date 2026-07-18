#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "validation" / "results"
from validation.scripts.common import backend_url, load_config


def post_json(base_url: str, path: str, payload: dict[str, object]) -> object:
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject a safe synthetic OpenStack-like error through /logs/batch.")
    parser.add_argument("--json-out", help="Optional path for injection metadata JSON.")
    args = parser.parse_args()
    base_url = backend_url(load_config())

    RESULTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    run_id = uuid.uuid4().hex[:12]
    request_id = f"req-{uuid.uuid4()}"
    resource_id = str(uuid.uuid4())
    boot_id = f"validation-boot-{run_id}"
    unit = "devstack@n-cpu.service"
    cursor_base = f"s=validation;i={run_id}"
    context_raw_id = f"validation-{run_id}-context"
    error_raw_id = f"validation-{run_id}-error"
    context_timestamp = now.isoformat().replace("+00:00", "Z")
    error_timestamp = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

    context_message = (
        f"{now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} 4242 INFO nova.compute.manager "
        f"[{request_id} admin validation] Starting build for instance {resource_id} "
        f"request_id={request_id}"
    )
    error_time = now + timedelta(seconds=1)
    error_message = (
        f"{error_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} 4242 ERROR nova.compute.manager "
        f"[{request_id} admin validation] Build failed due to timeout for instance {resource_id} "
        f"request_id={request_id}"
    )
    records = [
        {
            "_id": context_raw_id,
            "boot_id": boot_id,
            "journal_cursor": f"{cursor_base};n=1",
            "message": context_message,
            "timestamp": context_timestamp,
            "unit": unit,
            "_SYSTEMD_UNIT": unit,
            "PRIORITY": "6",
            "SYSLOG_IDENTIFIER": "nova-compute",
        },
        {
            "_id": error_raw_id,
            "boot_id": boot_id,
            "journal_cursor": f"{cursor_base};n=2",
            "message": error_message,
            "timestamp": error_timestamp,
            "unit": unit,
            "_SYSTEMD_UNIT": unit,
            "PRIORITY": "3",
            "SYSLOG_IDENTIFIER": "nova-compute",
        },
    ]

    response = post_json(base_url, "/logs/batch", {"records": records})
    metadata = {
        "injected_at": now.isoformat(),
        "backend_url": base_url,
        "request_id": request_id,
        "resource_id": resource_id,
        "unit": unit,
        "boot_id": boot_id,
        "message_fragment": "Build failed due to timeout",
        "records": records,
        "ingest_response": response,
    }

    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.json_out) if args.json_out else RESULTS / f"injection_{timestamp}_{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

    print(f"injection_metadata={output}")
    print(f"request_id={request_id}")
    print(f"resource_id={resource_id}")
    print(f"inserted_count={response.get('inserted_count') if isinstance(response, dict) else 'unknown'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
