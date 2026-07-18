#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "validation" / "results"
from validation.scripts.common import backend_url, load_config


def request_json(base_url: str, path: str, service_token: str | None = None) -> object:
    headers = {}
    if service_token:
        headers["X-RCA-Service-Token"] = service_token
    req = urllib.request.Request(f"{base_url}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    conf = load_config()
    base_url = backend_url(conf)
    RESULTS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    summary = request_json(base_url, "/api/v1/system/summary")
    health = request_json(base_url, "/api/v1/system/health")
    try:
        providers = request_json(base_url, "/api/v1/providers/active", conf.api.internal_service_token)
    except urllib.error.HTTPError as exc:
        providers = {"error": f"HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        providers = {"error": str(exc.reason)}

    counts = summary.get("counts", {}) if isinstance(summary, dict) else {}
    baseline = {
        "captured_at": timestamp,
        "backend_url": base_url,
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
