from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class CorrelationRule:
    reason: str
    confidence: float
    max_gap: timedelta


@dataclass(frozen=True)
class CorrelationEdge:
    source_event_id: Any
    target_event_id: Any
    reason: str
    confidence: float
    shared_value: str
    source_timestamp: datetime
    target_timestamp: datetime
    correlation_version: str
    group_classification: str = "transactional"

    def to_document(self, created_at: datetime) -> dict[str, Any]:
        return {
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
            "reason": self.reason,
            "confidence": self.confidence,
            "shared_value": self.shared_value,
            "source_timestamp": self.source_timestamp,
            "target_timestamp": self.target_timestamp,
            "created_at": created_at,
            "correlation_version": self.correlation_version,
            "group_classification": self.group_classification,
        }


@dataclass(frozen=True)
class CorrelationGroupMetrics:
    groups_processed: int = 0
    periodic_groups_skipped: int = 0
    oversized_groups_skipped: int = 0
    candidate_edges: int = 0
    skipped_edges: int = 0


@dataclass(frozen=True)
class CorrelationBuildResult:
    edges: list[CorrelationEdge]
    metrics: CorrelationGroupMetrics


def parse_event_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    if isinstance(value, (int, float)):
        timestamp = float(value)
        magnitude = abs(timestamp)
        if magnitude >= 1e18:
            timestamp /= 1e9
        elif magnitude >= 1e15:
            timestamp /= 1e6
        elif magnitude >= 1e12:
            timestamp /= 1e3
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    return None


def resource_values(event: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    resource_id = event.get("resource_id")
    if resource_id not in (None, ""):
        values.append(resource_id)

    resource_ids = event.get("resource_ids")
    if isinstance(resource_ids, list):
        values.extend(resource_ids)

    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def build_edge(
    first: dict[str, Any],
    second: dict[str, Any],
    rule: CorrelationRule,
    shared_value: str,
    correlation_version: str,
    group_classification: str = "transactional",
) -> CorrelationEdge | None:
    first_id = first.get("_id")
    second_id = second.get("_id")
    if first_id == second_id:
        return None

    first_timestamp = parse_event_timestamp(first.get("timestamp"))
    second_timestamp = parse_event_timestamp(second.get("timestamp"))
    if first_timestamp is None or second_timestamp is None:
        return None

    gap = abs(first_timestamp - second_timestamp)
    if gap > rule.max_gap:
        return None

    if first_timestamp == second_timestamp:
        return None

    if first_timestamp < second_timestamp:
        source, target = first, second
        source_timestamp, target_timestamp = first_timestamp, second_timestamp
    else:
        source, target = second, first
        source_timestamp, target_timestamp = second_timestamp, first_timestamp

    source_id = source.get("_id")
    target_id = target.get("_id")
    if source_id == target_id:
        return None

    return CorrelationEdge(
        source_event_id=source_id,
        target_event_id=target_id,
        reason=rule.reason,
        confidence=rule.confidence,
        shared_value=shared_value,
        source_timestamp=source_timestamp,
        target_timestamp=target_timestamp,
        correlation_version=correlation_version,
        group_classification=group_classification,
    )


def is_periodic_group(
    events: list[dict[str, Any]],
    minimum_span: timedelta,
) -> bool:
    timestamps = sorted(
        timestamp
        for event in events
        if (timestamp := parse_event_timestamp(event.get("timestamp"))) is not None
    )
    if len(timestamps) < 3:
        return False

    span = timestamps[-1] - timestamps[0]
    if span <= minimum_span:
        return False

    deltas = [
        (current - previous).total_seconds()
        for previous, current in zip(timestamps, timestamps[1:], strict=False)
    ]
    positive_deltas = [delta for delta in deltas if delta > 0]
    if len(positive_deltas) != len(deltas):
        return False

    median_delta = sorted(positive_deltas)[len(positive_deltas) // 2]
    tolerance = max(1.0, median_delta * 0.10)
    return max(positive_deltas) - min(positive_deltas) <= tolerance


def build_edges_for_group(
    events: list[dict[str, Any]],
    rule: CorrelationRule,
    shared_value: str,
    correlation_version: str,
    max_events_per_group: int = 100,
    skip_periodic_groups: bool = True,
    periodic_minimum_span: timedelta | None = None,
) -> CorrelationBuildResult:
    metrics = CorrelationGroupMetrics(groups_processed=1)
    if len(events) > max_events_per_group:
        return CorrelationBuildResult(
            edges=[],
            metrics=CorrelationGroupMetrics(
                groups_processed=1,
                oversized_groups_skipped=1,
            ),
        )

    periodic = is_periodic_group(events, periodic_minimum_span or rule.max_gap)
    group_classification = "periodic" if periodic else "transactional"
    if periodic and skip_periodic_groups:
        return CorrelationBuildResult(
            edges=[],
            metrics=CorrelationGroupMetrics(
                groups_processed=1,
                periodic_groups_skipped=1,
            ),
        )

    timestamped_events = [
        (timestamp, str(event.get("_id")), event)
        for event in events
        if (timestamp := parse_event_timestamp(event.get("timestamp"))) is not None
    ]
    timestamped_events.sort(key=lambda item: (item[0], item[1]))

    edges: list[CorrelationEdge] = []
    skipped_edges = len(events) - len(timestamped_events)
    candidate_edges = 0
    for (_, _, source), (_, _, target) in zip(
        timestamped_events,
        timestamped_events[1:],
        strict=False,
    ):
        candidate_edges += 1
        edge = build_edge(
            source,
            target,
            rule,
            shared_value,
            correlation_version,
            group_classification,
        )
        if edge is None:
            skipped_edges += 1
        else:
            edges.append(edge)

    return CorrelationBuildResult(
        edges=edges,
        metrics=CorrelationGroupMetrics(
            groups_processed=metrics.groups_processed,
            candidate_edges=candidate_edges,
            skipped_edges=skipped_edges,
        ),
    )


def build_correlated_edges_for_events(
    events: list[dict[str, Any]],
    request_rule: CorrelationRule,
    resource_rule: CorrelationRule,
    correlation_version: str,
) -> CorrelationBuildResult:
    edges: list[CorrelationEdge] = []
    group_events: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for event in events:
        request_id = event.get("request_id")
        if request_id not in (None, ""):
            group_events.setdefault((request_rule.reason, str(request_id)), []).append(event)

        for resource_id in resource_values(event):
            group_events.setdefault((resource_rule.reason, resource_id), []).append(event)

    metrics = CorrelationGroupMetrics()
    for (reason, shared_value), grouped_events in sorted(group_events.items()):
        rule = request_rule if reason == request_rule.reason else resource_rule
        result = build_edges_for_group(grouped_events, rule, shared_value, correlation_version)
        edges.extend(result.edges)
        metrics = CorrelationGroupMetrics(
            groups_processed=metrics.groups_processed + result.metrics.groups_processed,
            periodic_groups_skipped=(
                metrics.periodic_groups_skipped + result.metrics.periodic_groups_skipped
            ),
            oversized_groups_skipped=(
                metrics.oversized_groups_skipped + result.metrics.oversized_groups_skipped
            ),
            candidate_edges=metrics.candidate_edges + result.metrics.candidate_edges,
            skipped_edges=metrics.skipped_edges + result.metrics.skipped_edges,
        )

    return CorrelationBuildResult(edges=edges, metrics=metrics)


def build_edges_for_events(
    events: list[dict[str, Any]],
    request_rule: CorrelationRule,
    resource_rule: CorrelationRule,
    correlation_version: str,
) -> tuple[list[CorrelationEdge], int]:
    result = build_correlated_edges_for_events(
        events,
        request_rule,
        resource_rule,
        correlation_version,
    )
    return result.edges, result.metrics.skipped_edges
