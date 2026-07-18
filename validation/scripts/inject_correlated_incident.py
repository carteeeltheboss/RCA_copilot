#!/usr/bin/env python3
"""Inject and verify a realistic multi-service correlated incident."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
import time
import urllib.parse
import urllib.request
from uuid import uuid4


def request_json(url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method="POST" if body else "GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    base = args.backend.rstrip("/")
    request_id = f"req-{uuid4()}"
    resource_id = str(uuid4())
    boot_id = str(uuid4())
    started = datetime.now(UTC)
    services = ("nova-api", "neutron-server", "placement-api")
    messages = (
        "accepted server create request",
        "allocated network port for server",
        "ERROR placement allocation failed for server resource",
    )
    records = []
    for index, (service, message) in enumerate(zip(services, messages, strict=True)):
        timestamp = started + timedelta(seconds=index)
        records.append(
            {
                "boot_id": boot_id,
                "journal_cursor": f"rca-demo-{uuid4()}",
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "service": service,
                "unit": service,
                "message": f"{'ERROR' if index == 2 else 'INFO'} {service} "
                f"[None {request_id} demo project] {message} {resource_id}",
            }
        )
    request_json(f"{base}/logs/batch", {"records": records})

    deadline = time.monotonic() + args.timeout
    query = urllib.parse.urlencode({"request_id": request_id, "page_size": 10})
    while time.monotonic() < deadline:
        incidents = request_json(f"{base}/api/v1/incidents?{query}").get("items", [])
        if incidents:
            incident_id = incidents[0]["incident_id"]
            graph = request_json(f"{base}/api/v1/incidents/{incident_id}/graph")
            if len(graph.get("nodes", [])) >= 3 and len(graph.get("edges", [])) >= 2:
                print(json.dumps({"request_id": request_id, "incident_id": incident_id, **graph}))
                return 0
        time.sleep(2)
    raise SystemExit(f"timed out waiting for connected graph for {request_id}")


if __name__ == "__main__":
    raise SystemExit(main())
