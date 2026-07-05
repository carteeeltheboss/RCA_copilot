from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from correlation_worker.correlator import parse_event_timestamp, resource_values


def build_enrichment_document(
    incident: dict[str, Any],
    events: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    enrichment_version: str,
    enriched_at: datetime,
) -> dict[str, Any]:
    ordered_events = sorted(
        events,
        key=lambda event: (
            parse_event_timestamp(event.get("timestamp")) or datetime.max.replace(tzinfo=UTC),
            str(event.get("_id")),
        ),
    )
    timeline = [_timeline_entry(event) for event in ordered_events]

    services = _sorted_unique(
        str(event.get("service"))
        for event in ordered_events
        if event.get("service") not in (None, "")
    )
    request_ids = _sorted_unique(
        str(event.get("request_id"))
        for event in ordered_events
        if event.get("request_id") not in (None, "")
    )
    resource_ids = _sorted_unique(
        resource_id
        for event in ordered_events
        for resource_id in resource_values(event)
    )
    hosts = _sorted_unique(
        str(event.get("host"))
        for event in ordered_events
        if event.get("host") not in (None, "")
    )
    levels = _sorted_unique(
        str(event.get("level")).upper()
        for event in ordered_events
        if event.get("level") not in (None, "")
    )
    timestamps = [
        entry["timestamp"]
        for entry in timeline
        if entry["timestamp"] is not None
    ]
    first_event_at = timestamps[0] if timestamps else None
    last_event_at = timestamps[-1] if timestamps else None
    duration_ms = _duration_ms(first_event_at, last_event_at)
    error_count = sum(1 for event in ordered_events if _level(event) in {"ERROR", "CRITICAL"})
    warning_count = sum(1 for event in ordered_events if _level(event) in {"WARN", "WARNING"})

    return {
        "enrichment_version": enrichment_version,
        "enriched_at": enriched_at,
        "timeline": timeline,
        "request_ids": request_ids,
        "resource_ids": resource_ids,
        "hosts": hosts,
        "levels": levels,
        "first_event_at": first_event_at,
        "last_event_at": last_event_at,
        "duration_ms": duration_ms,
        "event_count": len(timeline),
        "edge_count": len(edges),
        "error_count": error_count,
        "warning_count": warning_count,
        "summary": build_summary(incident, timeline, services),
        "impact_summary": build_impact_summary(services, resource_ids),
        "evidence_summary": build_evidence_summary(
            request_ids,
            resource_ids,
            error_count,
            warning_count,
            len(edges),
            len(timeline),
        ),
        "status": "enriched",
    }


def build_summary(
    incident: dict[str, Any],
    timeline: list[dict[str, Any]],
    services: list[str],
) -> str:
    event_count = len(timeline)
    seed_event = _find_seed_event(incident, timeline)
    if seed_event is None:
        seed_description = "Seed event details were not found in parsed_logs"
    else:
        seed_service = seed_event.get("service") or "unknown service"
        seed_message = _short_message(seed_event.get("message"))
        seed_description = f"Seed event from {seed_service}: {seed_message}"

    service_text = _join_values(services) if services else "no service values available"
    event_word = "event" if event_count == 1 else "events"
    limited = " Evidence is limited to one event." if event_count == 1 else ""
    return f"{seed_description}. Involved services: {service_text}. Timeline contains {event_count} {event_word}.{limited}"


def build_impact_summary(services: list[str], resource_ids: list[str]) -> str:
    service_text = _join_values(services) if services else "no observed services"
    resource_text = _join_values(resource_ids) if resource_ids else "no observed resources"
    return f"Observed affected services: {service_text}. Observed affected resources: {resource_text}."


def build_evidence_summary(
    request_ids: list[str],
    resource_ids: list[str],
    error_count: int,
    warning_count: int,
    edge_count: int,
    event_count: int,
) -> str:
    request_text = _join_values(request_ids) if request_ids else "none observed"
    resource_text = _join_values(resource_ids) if resource_ids else "none observed"
    limited = " Evidence is limited to one event." if event_count == 1 else ""
    return (
        f"Request IDs: {request_text}. Resource IDs: {resource_text}. "
        f"Errors: {error_count}. Warnings: {warning_count}. "
        f"Correlation edges: {edge_count}.{limited}"
    )


def _timeline_entry(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("_id"),
        "timestamp": parse_event_timestamp(event.get("timestamp")),
        "service": str(event.get("service") or "unknown-service"),
        "level": _optional_string(event.get("level")),
        "message": str(event.get("message") or ""),
        "request_id": _optional_string(event.get("request_id")),
        "resource_ids": resource_values(event),
        "host": _optional_string(event.get("host")),
    }


def _find_seed_event(
    incident: dict[str, Any],
    timeline: list[dict[str, Any]],
) -> dict[str, Any] | None:
    seed_event_id = incident.get("seed_event_id")
    for entry in timeline:
        if entry.get("event_id") == seed_event_id:
            return entry
    return timeline[0] if timeline else None


def _duration_ms(first_event_at: datetime | None, last_event_at: datetime | None) -> int:
    if first_event_at is None or last_event_at is None:
        return 0
    return max(0, int((last_event_at - first_event_at).total_seconds() * 1000))


def _level(event: dict[str, Any]) -> str:
    return str(event.get("level") or "").upper()


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _short_message(value: Any, limit: int = 160) -> str:
    message = " ".join(str(value or "").strip().split())
    if not message:
        return "no message available"
    if len(message) <= limit:
        return message
    return f"{message[: limit - 3]}..."


def _sorted_unique(values: Any) -> list[str]:
    return sorted({str(value) for value in values if value not in (None, "")})


def _join_values(values: list[str]) -> str:
    return ", ".join(values)
