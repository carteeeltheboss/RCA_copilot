from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from correlation_worker.correlator import parse_event_timestamp, resource_values


FALSE_POSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:0|zero|no)\s+failures?\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:errors?|exceptions?|tracebacks?|timeouts?)\b", re.IGNORECASE),
    re.compile(
        r"\b[\w.-]*(?:errors?|error_count|failures?|failure_count|failed_[\w.-]*)"
        r"[\w.-]*\s*[:=]\s*['\"]?(?:0|zero)['\"]?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnot\s+an?\s+errors?\b", re.IGNORECASE),
    re.compile(r"\berror\s+rate\b", re.IGNORECASE),
)
TRACEBACK_PATTERN = re.compile(r"\bTraceback\b")
EXCEPTION_PATTERN = re.compile(r"\bException\b", re.IGNORECASE)
FAILED_PATTERN = re.compile(r"\b(?:failed|failure|failures)\b", re.IGNORECASE)
TIMEOUT_PATTERN = re.compile(r"\b(?:timeout|timeouts|timed\s+out)\b", re.IGNORECASE)
RESOURCE_ERROR_STATE_PATTERN = re.compile(
    r"\b(?:resource|instance|server|volume|port|network|router|stack|node)\b.*"
    r"\b(?:entered|entering|went\s+into|transitioned\s+to|changed\s+to|is\s+in)\b.*"
    r"\bERROR\b.*\bstate\b|\bstate\b.*\b(?:ERROR|error)\b",
    re.IGNORECASE,
)
SERVICE_PROCESS_FAILURE_PATTERN = re.compile(
    r"\b(?:service|process|daemon|unit)\b.*"
    r"\b(?:failed|failure|crashed|exited|terminated|died)\b",
    re.IGNORECASE,
)
QUOTED_TEXT_PATTERN = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`")
HISTORICAL_LINE_PATTERN = re.compile(
    r"^\s*(?:previous|prior|historical|history|example|quoted)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class SeedDetection:
    seed_event_id: Any
    seed_reason: str
    severity: str
    title: str
    service: str | None
    request_id: str | None
    resource_ids: list[str]
    detected_reasons: list[str]
    suppressed_false_positive_patterns: list[str]


@dataclass(frozen=True)
class IncidentSubgraph:
    event_ids: list[Any]
    edge_ids: list[Any]
    services: list[str]
    resource_ids: list[str]


def detect_incident_seed(event: dict[str, Any]) -> SeedDetection | None:
    if event.get("parse_status") != "success":
        return None

    message = str(event.get("message") or "")
    active_message = _active_message_text(message)
    exclusions = _false_positive_matches(message)
    detected_reasons: list[str] = []
    level = str(event.get("level") or "").upper()

    if exclusions:
        return None

    if level in {"ERROR", "CRITICAL"}:
        detected_reasons.append(f"level:{level}")

    detected_reasons.extend(_message_detection_reasons(active_message))

    if not detected_reasons:
        return None

    event_id = event.get("_id")
    return SeedDetection(
        seed_event_id=event_id,
        seed_reason=detected_reasons[0],
        severity="CRITICAL" if level == "CRITICAL" else "ERROR",
        title=_build_title(event),
        service=_optional_string(event.get("service")),
        request_id=_optional_string(event.get("request_id")),
        resource_ids=resource_values(event),
        detected_reasons=detected_reasons,
        suppressed_false_positive_patterns=exclusions,
    )


def build_incident_document(
    seed_event: dict[str, Any],
    detection: SeedDetection,
    subgraph: IncidentSubgraph,
    correlation_version: str,
    incident_version: str,
    updated_at: datetime,
) -> dict[str, Any]:
    seed_timestamp = parse_event_timestamp(seed_event.get("timestamp")) or updated_at
    incident_id = build_incident_id(detection.seed_event_id, incident_version)
    resource_ids = _sorted_unique([*detection.resource_ids, *subgraph.resource_ids])
    event_ids = _stable_unique([detection.seed_event_id, *subgraph.event_ids])
    services = _sorted_unique(
        [
            service
            for service in [detection.service, *subgraph.services]
            if service not in (None, "")
        ]
    )

    return {
        "incident_id": incident_id,
        "seed_event_id": detection.seed_event_id,
        "seed_reason": detection.seed_reason,
        "seed_detection_reasons": detection.detected_reasons,
        "seed_detection_exclusions": detection.suppressed_false_positive_patterns,
        "severity": detection.severity,
        "status": "candidate",
        "title": detection.title,
        "started_at": seed_timestamp,
        "updated_at": updated_at,
        "service": detection.service,
        "request_id": detection.request_id,
        "resource_ids": resource_ids,
        "event_ids": event_ids,
        "edge_ids": subgraph.edge_ids,
        "services": services,
        "correlation_version": correlation_version,
        "incident_version": incident_version,
    }


def build_incident_id(seed_event_id: Any, incident_version: str) -> str:
    value = f"{incident_version}:{seed_event_id}".encode("utf-8")
    return f"incident-{hashlib.sha256(value).hexdigest()[:24]}"


def build_subgraph_from_edges(
    seed_event: dict[str, Any],
    events_by_id: dict[Any, dict[str, Any]],
    edges: list[dict[str, Any]],
    max_depth: int = 3,
    max_events: int = 100,
    window_before: timedelta = timedelta(minutes=10),
    window_after: timedelta = timedelta(minutes=2),
) -> IncidentSubgraph:
    seed_id = seed_event.get("_id")
    seed_timestamp = parse_event_timestamp(seed_event.get("timestamp"))
    if seed_id is None or seed_timestamp is None or max_events < 1:
        return IncidentSubgraph(event_ids=[], edge_ids=[], services=[], resource_ids=[])

    lower = seed_timestamp - window_before
    upper = seed_timestamp + window_after
    adjacency: dict[Any, list[tuple[Any, dict[str, Any]]]] = {}
    for edge in edges:
        source_id = edge.get("source_event_id")
        target_id = edge.get("target_event_id")
        if source_id is None or target_id is None:
            continue
        adjacency.setdefault(source_id, []).append((target_id, edge))
        adjacency.setdefault(target_id, []).append((source_id, edge))

    visited: set[Any] = {seed_id}
    event_ids: list[Any] = [seed_id]
    edge_ids: list[Any] = []
    seen_edge_ids: set[Any] = set()
    queue: list[tuple[Any, int]] = [(seed_id, 0)]

    while queue and len(event_ids) < max_events:
        current_id, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        for next_id, edge in adjacency.get(current_id, []):
            if next_id in visited:
                continue
            next_event = events_by_id.get(next_id)
            if next_event is None or not _event_in_window(next_event, lower, upper):
                continue

            visited.add(next_id)
            event_ids.append(next_id)
            edge_id = edge.get("_id")
            if edge_id is not None and edge_id not in seen_edge_ids:
                seen_edge_ids.add(edge_id)
                edge_ids.append(edge_id)
            queue.append((next_id, depth + 1))

            if len(event_ids) >= max_events:
                break

    included = [events_by_id[event_id] for event_id in event_ids if event_id in events_by_id]
    return IncidentSubgraph(
        event_ids=event_ids,
        edge_ids=edge_ids,
        services=_sorted_unique(
            str(event.get("service"))
            for event in included
            if event.get("service") not in (None, "")
        ),
        resource_ids=_sorted_unique(
            resource_id for event in included for resource_id in resource_values(event)
        ),
    )


def _message_detection_reasons(message: str) -> list[str]:
    reasons: list[str] = []
    if TRACEBACK_PATTERN.search(message):
        reasons.append("message:traceback")
    if EXCEPTION_PATTERN.search(message):
        reasons.append("message:exception")
    if FAILED_PATTERN.search(message):
        reasons.append("message:failed_or_failure")
    if TIMEOUT_PATTERN.search(message):
        reasons.append("message:timeout")
    if RESOURCE_ERROR_STATE_PATTERN.search(message):
        reasons.append("message:resource_error_state")
    if SERVICE_PROCESS_FAILURE_PATTERN.search(message):
        reasons.append("message:service_process_failure")
    return reasons


def _false_positive_matches(message: str) -> list[str]:
    return [pattern.pattern for pattern in FALSE_POSITIVE_PATTERNS if pattern.search(message)]


def _active_message_text(message: str) -> str:
    without_quoted = QUOTED_TEXT_PATTERN.sub(" ", message)
    return HISTORICAL_LINE_PATTERN.sub(" ", without_quoted)


def _event_in_window(event: dict[str, Any], lower: datetime, upper: datetime) -> bool:
    timestamp = parse_event_timestamp(event.get("timestamp"))
    return timestamp is not None and lower <= timestamp <= upper


def _build_title(event: dict[str, Any]) -> str:
    service = str(event.get("service") or "unknown-service")
    first_line = str(event.get("message") or "").strip().splitlines()
    summary = first_line[0] if first_line else "incident candidate"
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > 120:
        summary = f"{summary[:117]}..."
    return f"{service}: {summary}"


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _stable_unique(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _sorted_unique(values: Any) -> list[str]:
    return sorted({str(value) for value in values if value not in (None, "")})
