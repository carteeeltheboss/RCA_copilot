#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND_URL = os.environ.get("RCA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def get_json(path: str) -> object:
    with urllib.request.urlopen(f"{BACKEND_URL}{path}", timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def search(query: dict[str, str]) -> list[dict[str, object]]:
    params = {"page_size": "20", "sort": "newest", **{k: v for k, v in query.items() if v}}
    path = "/api/v1/incidents?" + urllib.parse.urlencode(params)
    data = get_json(path)
    return data.get("items", []) if isinstance(data, dict) else []


def best_match(items: list[dict[str, object]], request_id: str, resource_id: str, fragment: str) -> dict[str, object] | None:
    for item in items:
        text = json.dumps(item, default=str)
        if request_id and request_id in text:
            return item
        if resource_id and resource_id in text:
            return item
        if fragment and fragment in text and (request_id in text or resource_id in text):
            return item
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll for a newly created validation incident.")
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--resource-id", required=True)
    parser.add_argument("--message-fragment", default="Build failed due to timeout")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--json-out")
    args = parser.parse_args()

    deadline = time.time() + args.timeout
    last_seen: dict[str, object] | None = None
    while time.time() < deadline:
        candidates: list[dict[str, object]] = []
        for query in (
            {"request_id": args.request_id},
            {"resource_id": args.resource_id},
            {"q": args.resource_id},
            {"q": args.request_id},
        ):
            try:
                candidates.extend(search(query))
            except Exception:
                pass
        match = best_match(candidates, args.request_id, args.resource_id, args.message_fragment)
        if match:
            last_seen = match
            if match.get("status") == "enriched":
                break
        time.sleep(args.interval)

    if not last_seen:
        print("No incident found for validation injection.", file=sys.stderr)
        return 1

    result = {
        "incident_id": last_seen.get("incident_id"),
        "status": last_seen.get("status"),
        "severity": last_seen.get("severity"),
        "service": last_seen.get("primary_service") or last_seen.get("service"),
        "event_count": last_seen.get("event_count"),
        "edge_count": last_seen.get("edge_count"),
    }
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    print(f"incident_id={result['incident_id']}")
    print(f"status={result['status']}")
    print(f"event_count={result['event_count']}")
    print(f"edge_count={result['edge_count']}")
    return 0 if result["incident_id"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
