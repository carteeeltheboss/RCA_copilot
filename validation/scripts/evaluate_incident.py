#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "validation" / "results"
from validation.scripts.common import backend_url, load_config


def request_json(base_url: str, path: str, method: str = "GET", service_token: str | None = None) -> tuple[int, object]:
    headers = {}
    data = None
    if service_token:
        headers["X-RCA-Service-Token"] = service_token
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=150) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: object = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": body}
        return exc.code, parsed


def text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def quality_label(condition: bool, detail: str) -> str:
    return f"{'PASS' if condition else 'FAIL'} - {detail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a validation incident.")
    parser.add_argument("incident_id")
    parser.add_argument("--expected-service", default="devstack@n-cpu.service")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    conf = load_config()
    base_url = backend_url(conf)
    RESULTS.mkdir(parents=True, exist_ok=True)

    detail_status, detail = request_json(base_url, f"/api/v1/incidents/{args.incident_id}")
    graph_status, graph = request_json(base_url, f"/api/v1/incidents/{args.incident_id}/graph")
    timeline_status, timeline = request_json(base_url, f"/api/v1/incidents/{args.incident_id}/timeline")
    explain_status, explain = request_json(base_url, f"/api/v1/incidents/{args.incident_id}/explain", method="POST", service_token=conf.api.internal_service_token)

    if detail_status == 404:
        print(f"Incident not found: {args.incident_id}", file=sys.stderr)
        return 1

    detail_dict = detail if isinstance(detail, dict) else {}
    graph_dict = graph if isinstance(graph, dict) else {}
    timeline_dict = timeline if isinstance(timeline, dict) else {}
    explain_dict = explain if isinstance(explain, dict) else {}
    answer = explain_dict.get("answer") if isinstance(explain_dict.get("answer"), dict) else {}
    answer_text = explain_dict.get("answer_text") or answer.get("summary") or ""

    nodes = graph_dict.get("nodes", []) if isinstance(graph_dict.get("nodes"), list) else []
    edges = graph_dict.get("edges", []) if isinstance(graph_dict.get("edges"), list) else []
    timeline_items = timeline_dict.get("items", []) if isinstance(timeline_dict.get("items"), list) else []
    detected_service = detail_dict.get("service") or detail_dict.get("primary_service") or ""
    incident_status = detail_dict.get("status")
    event_count = detail_dict.get("event_count") or len(detail_dict.get("event_ids") or [])
    edge_count = detail_dict.get("edge_count") or len(detail_dict.get("edge_ids") or [])

    service_ok = bool(detected_service) and (
        args.expected_service in str(detected_service)
        or str(detected_service) in args.expected_service
        or "nova" in str(detected_service).lower()
    )
    checks = [
        quality_label(detail_status == 200, "incident detail endpoint returned data"),
        quality_label(incident_status == "enriched", "incident is enriched"),
        quality_label(service_ok, f"detected service is plausible: {detected_service}"),
        quality_label(bool(event_count and int(event_count) > 0), f"event count is {event_count}"),
        quality_label(graph_status == 200 and len(nodes) > 0, f"graph has {len(nodes)} node(s)"),
        quality_label(graph_status == 200, f"graph endpoint status {graph_status}"),
        quality_label(timeline_status == 200 and len(timeline_items) > 0, f"timeline has {len(timeline_items)} item(s)"),
        quality_label(explain_status == 200 and explain_dict.get("status") == "ok", f"AI explain status is {explain_dict.get('status')}"),
        quality_label(bool(answer_text), "AI explanation returned content"),
    ]

    report_path = RESULTS / f"incident_{args.incident_id}_report.md"
    limitations = answer.get("limitations") or explain_dict.get("reason") or ""
    evidence = text_list(answer.get("evidence"))
    hypotheses = text_list(answer.get("hypotheses"))
    next_checks = text_list(answer.get("recommended_next_checks"))

    report = [
        f"# Validation Report: {args.incident_id}",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Incident",
        "",
        f"- Incident ID: `{args.incident_id}`",
        f"- Expected service: `{args.expected_service}`",
        f"- Detected service: `{detected_service}`",
        f"- Severity: `{detail_dict.get('severity')}`",
        f"- Status: `{incident_status}`",
        f"- Event count: `{event_count}`",
        f"- Edge count: `{edge_count}`",
        "",
        "## Timeline Quality",
        "",
        f"- Endpoint status: `{timeline_status}`",
        f"- Timeline events: `{len(timeline_items)}`",
        f"- Assessment: {'PASS' if timeline_status == 200 and timeline_items else 'FAIL'}",
        "",
        "## Graph Quality",
        "",
        f"- Endpoint status: `{graph_status}`",
        f"- Graph nodes: `{len(nodes)}`",
        f"- Graph edges: `{len(edges)}`",
        f"- Assessment: {'PASS' if graph_status == 200 and nodes else 'FAIL'}",
        "",
        "## AI Explanation",
        "",
        f"- Endpoint status: `{explain_status}`",
        f"- Provider kind: `{(explain_dict.get('provider') or {}).get('provider_kind')}`",
        f"- Model: `{(explain_dict.get('provider') or {}).get('model_name')}`",
        f"- Status: `{explain_dict.get('status')}`",
        f"- Summary: {answer.get('summary') or answer_text}",
        f"- Likely failure area: {answer.get('likely_failure_area') or ''}",
        f"- Confidence: `{answer.get('confidence') or ''}`",
        f"- Limitations: {limitations}",
        "",
        "## Evidence",
        "",
        *(f"- {item}" for item in evidence),
        "",
        "## Hypotheses",
        "",
        *(f"- {item}" for item in hypotheses),
        "",
        "## Recommended Next Checks",
        "",
        *(f"- {item}" for item in next_checks),
        "",
        "## Pass/Fail Checklist",
        "",
        *(f"- {item}" for item in checks),
        "",
    ]
    report_path.write_text("\n".join(report))

    result = {
        "incident_id": args.incident_id,
        "report_path": str(report_path),
        "detected_service": detected_service,
        "severity": detail_dict.get("severity"),
        "status": incident_status,
        "event_count": event_count,
        "edge_count": edge_count,
        "graph_node_count": len(nodes),
        "graph_edge_count": len(edges),
        "timeline_event_count": len(timeline_items),
        "ai_explain_http_status": explain_status,
        "ai_explain_status": explain_dict.get("status"),
        "checks": checks,
    }
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    print(f"report_path={report_path}")
    print(f"graph_node_count={len(nodes)}")
    print(f"graph_edge_count={len(edges)}")
    print(f"timeline_event_count={len(timeline_items)}")
    print(f"ai_explain_status={explain_dict.get('status')}")
    return 0 if all(item.startswith("PASS") for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
