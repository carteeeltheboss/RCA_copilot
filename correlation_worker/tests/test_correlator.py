from __future__ import annotations

from datetime import UTC, datetime, timedelta

from correlation_worker.correlator import (
    CorrelationRule,
    build_edge,
    build_edges_for_group,
    build_edges_for_events,
    parse_event_timestamp,
)
from correlation_worker.repository import CorrelationBatchMetrics, CorrelationRepository


REQUEST_RULE = CorrelationRule("same_request_id", 1.0, timedelta(minutes=5))
RESOURCE_RULE = CorrelationRule("shared_resource_id", 0.9, timedelta(minutes=10))


def test_parse_journald_microsecond_timestamp() -> None:
    parsed = parse_event_timestamp(1_720_000_000_000_000)
    assert parsed is not None
    assert parsed.year == 2024


def event(
    event_id: str,
    minute: int,
    request_id: str | None = None,
    resource_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "_id": event_id,
        "parse_status": "success",
        "timestamp": datetime(2026, 7, 5, 10, 0, tzinfo=UTC) + timedelta(minutes=minute),
        "request_id": request_id,
        "resource_ids": resource_ids or [],
    }


def test_same_request_id_edge() -> None:
    edges, skipped = build_edges_for_events(
        [event("a", 0, request_id="req-1"), event("b", 1, request_id="req-1")],
        REQUEST_RULE,
        RESOURCE_RULE,
        "correlation-v1",
    )

    assert skipped == 0
    assert len(edges) == 1
    assert edges[0].reason == "same_request_id"
    assert edges[0].confidence == 1.0
    assert edges[0].shared_value == "req-1"


def test_shared_resource_id_edge() -> None:
    edges, skipped = build_edges_for_events(
        [event("a", 0, resource_ids=["server-1"]), event("b", 9, resource_ids=["server-1"])],
        REQUEST_RULE,
        RESOURCE_RULE,
        "correlation-v1",
    )

    assert skipped == 0
    assert len(edges) == 1
    assert edges[0].reason == "shared_resource_id"
    assert edges[0].confidence == 0.9
    assert edges[0].shared_value == "server-1"


def test_time_window_rejection() -> None:
    edges, skipped = build_edges_for_events(
        [event("a", 0, request_id="req-1"), event("b", 6, request_id="req-1")],
        REQUEST_RULE,
        RESOURCE_RULE,
        "correlation-v1",
    )

    assert edges == []
    assert skipped == 1


def test_self_edge_rejection() -> None:
    source = event("a", 0, request_id="req-1")

    edge = build_edge(source, source, REQUEST_RULE, "req-1", "correlation-v1")

    assert edge is None


def test_duplicate_prevention_uses_stable_edge_identity() -> None:
    first = event("a", 0, request_id="req-1")
    second = event("b", 1, request_id="req-1")

    forward = build_edge(first, second, REQUEST_RULE, "req-1", "correlation-v1")
    reverse = build_edge(second, first, REQUEST_RULE, "req-1", "correlation-v1")

    assert forward is not None
    assert reverse is not None
    assert forward.source_event_id == reverse.source_event_id == "a"
    assert forward.target_event_id == reverse.target_event_id == "b"
    assert forward.reason == reverse.reason
    assert forward.shared_value == reverse.shared_value


def test_chronological_direction() -> None:
    edges, skipped = build_edges_for_events(
        [event("later", 4, request_id="req-1"), event("earlier", 1, request_id="req-1")],
        REQUEST_RULE,
        RESOURCE_RULE,
        "correlation-v1",
    )

    assert skipped == 0
    assert len(edges) == 1
    assert edges[0].source_event_id == "earlier"
    assert edges[0].target_event_id == "later"


def test_one_hundred_matching_events_create_at_most_ninety_nine_edges() -> None:
    events = [event(f"event-{index:03}", index, request_id="req-chain") for index in range(100)]

    result = build_edges_for_group(
        events,
        REQUEST_RULE,
        "req-chain",
        "correlation-v1",
        skip_periodic_groups=False,
    )

    assert result.metrics.groups_processed == 1
    assert result.metrics.oversized_groups_skipped == 0
    assert len(result.edges) == 99
    assert result.edges[0].source_event_id == "event-000"
    assert result.edges[0].target_event_id == "event-001"
    assert result.edges[-1].source_event_id == "event-098"
    assert result.edges[-1].target_event_id == "event-099"
    assert {edge.group_classification for edge in result.edges} == {"periodic"}


def test_periodic_one_minute_events_are_skipped_by_default() -> None:
    events = [event(f"event-{index:03}", index, request_id="req-periodic") for index in range(12)]

    result = build_edges_for_group(events, REQUEST_RULE, "req-periodic", "correlation-v1")

    assert result.edges == []
    assert result.metrics.periodic_groups_skipped == 1


def test_normal_short_request_chain_remains_connected() -> None:
    events = [
        event("later", 2, request_id="req-short"),
        event("first", 0, request_id="req-short"),
        event("middle", 1, request_id="req-short"),
    ]

    result = build_edges_for_group(events, REQUEST_RULE, "req-short", "correlation-v1")

    assert result.metrics.periodic_groups_skipped == 0
    assert [edge.source_event_id for edge in result.edges] == ["first", "middle"]
    assert [edge.target_event_id for edge in result.edges] == ["middle", "later"]
    assert {edge.group_classification for edge in result.edges} == {"transactional"}


def test_shared_resource_chain_remains_connected() -> None:
    events = [
        event("first", 0, resource_ids=["server-1"]),
        event("middle", 4, resource_ids=["server-1"]),
        event("later", 9, resource_ids=["server-1"]),
    ]

    result = build_edges_for_group(events, RESOURCE_RULE, "server-1", "correlation-v1")

    assert len(result.edges) == 2
    assert [edge.reason for edge in result.edges] == ["shared_resource_id", "shared_resource_id"]
    assert [edge.source_event_id for edge in result.edges] == ["first", "middle"]
    assert [edge.target_event_id for edge in result.edges] == ["middle", "later"]


class FakeStateCollection:
    def __init__(self) -> None:
        self.document: dict[str, object] = {}

    async def update_one(
        self, query: dict[str, object], update: dict[str, object], upsert: bool = False
    ) -> None:
        self.document.update(update.get("$set", {}))  # type: ignore[arg-type]
        self.document.update(update.get("$setOnInsert", {}))  # type: ignore[arg-type]


def test_correlation_repository_writes_worker_state_heartbeat() -> None:
    state_collection = FakeStateCollection()
    repository = CorrelationRepository(
        parsed_collection=object(),
        edge_collection=object(),
        state_collection=state_collection,
        worker_state_key="correlation_worker_v1",
        correlation_version="correlation-v1",
        request_id_max_gap=timedelta(minutes=5),
        resource_id_max_gap=timedelta(minutes=10),
    )
    metrics = CorrelationBatchMetrics(
        events_scanned=4,
        groups_processed=2,
        periodic_groups_skipped=0,
        oversized_groups_skipped=0,
        edges_inserted=3,
        candidate_edges=3,
        inserted_edges=3,
        skipped_edges=0,
    )

    import asyncio

    asyncio.run(repository.heartbeat(metrics))

    assert state_collection.document["worker"] == "correlation_worker_v1"
    assert state_collection.document["last_batch_count"] == 4
    assert state_collection.document["last_edges_inserted"] == 3
    assert state_collection.document["correlation_version"] == "correlation-v1"
