#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "validation" / "results"
BACKEND_URL = os.environ.get("RCA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def request_json(path: str, token: bool = False) -> object:
    headers = {}
    if token:
        service_token = os.environ.get("RCA_INTERNAL_SERVICE_TOKEN")
        if service_token:
            headers["X-RCA-Service-Token"] = service_token
    req = urllib.request.Request(f"{BACKEND_URL}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    load_env()
    RESULTS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    summary = request_json("/api/v1/system/summary")
    health = request_json("/api/v1/system/health")
    try:
        providers = request_json("/api/v1/providers/active", token=True)
    except urllib.error.HTTPError as exc:
        providers = {"error": f"HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        providers = {"error": str(exc.reason)}

    counts = summary.get("counts", {}) if isinstance(summary, dict) else {}
    baseline = {
        "captured_at": timestamp,
        "backend_url": BACKEND_URL,
        "counts": {
            "raw_logs": counts.get("raw_logs"),
            "parsed_logs": counts.get("parsed_events"),
            "event_edges": counts.get("correlation_edges"),
            "incidents": counts.get("incidents"),
            "enriched_incidents": counts.get("enriched_incidents"),
        },
        "provider_status": providers,
        "system_summary": summary,
        "system_health": health,
    }

    output = RESULTS / f"baseline_{timestamp}.json"
    output.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

