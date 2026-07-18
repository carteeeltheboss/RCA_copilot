from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from incident_worker.detector import (
    build_subgraph_from_edges,
    detect_incident_seed,
)
from incident_worker.repository import IncidentRepository


BASE_TIME = datetime(2026, 7, 5, 10, 0, tzinfo=UTC)


def event(
    event_id: str,
    minute: int = 0,
    parsed_second: int = 0,
    message: str = "all good",
    level: str = "INFO",
    service: str = "nova-api",
    resource_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "_id": event_id,
        "parse_status": "success",
        "timestamp": BASE_TIME + timedelta(minutes=minute),
        "parsed_at": BASE_TIME + timedelta(seconds=parsed_second),
        "message": message,
        "level": level,
        "service": service,
        "request_id": "req-11111111-1111-4111-8111-111111111111",
        "resource_ids": resource_ids or [],
    }


def edge(edge_id: str, source: str, target: str, minute: int = 0) -> dict[str, Any]:
    timestamp = BASE_TIME + timedelta(minutes=minute)
    return {
        "_id": edge_id,
        "source_event_id": source,
        "target_event_id": target,
        "source_timestamp": timestamp,
        "target_timestamp": timestamp + timedelta(seconds=30),
        "correlation_version": "correlation-v1",
    }


def test_error_level_seed() -> None:
    detection = detect_incident_seed(event("seed", level="ERROR", message="request failed"))

    assert detection is not None
    assert detection.seed_reason == "level:ERROR"
    assert detection.severity == "ERROR"
    assert detection.service == "nova-api"


def test_traceback_seed() -> None:
    detection = detect_incident_seed(
        event("seed", message='Traceback (most recent call last):\n  File "x.py", line 1')
    )

    assert detection is not None
    assert detection.seed_reason == "message:traceback"


def test_timeout_seed() -> None:
    detection = detect_incident_seed(event("seed", message="RPC call timed out waiting for reply"))

    assert detection is not None
    assert detection.seed_reason == "message:timeout"


def test_false_positive_suppression() -> None:
    suppressed = [
        event("a", message="Health check reports 0 failures"),
        event("b", message="no error while polling service"),
        event("c", message="error rate is below threshold"),
        event("d", message='operator note quoted "Traceback and Exception" only'),
        event("e", message="DEBUG metrics failed_builds: '0'"),
        event("f", message="errors: 0"),
        event("g", message="error_count=0"),
        event("h", message="no failures"),
    ]

    assert [detect_incident_seed(item) for item in suppressed] == [None] * len(suppressed)


def test_negated_error_level_is_suppressed() -> None:
    assert detect_incident_seed(event("seed", level="ERROR", message="no error")) is None


def test_real_build_failed_creates_seed() -> None:
    detection = detect_incident_seed(
        event("seed", level="DEBUG", message="Build failed due to timeout")
    )

    assert detection is not None
    assert detection.seed_reason == "message:failed_or_failure"


def test_bounded_graph_traversal() -> None:
    events = {item["_id"]: item for item in [event("seed"), event("a"), event("b"), event("c")]}
    result = build_subgraph_from_edges(
        events["seed"],
        events,
        [edge("e1", "seed", "a"), edge("e2", "a", "b"), edge("e3", "b", "c")],
        max_depth=1,
        max_events=100,
    )

    assert result.event_ids == ["seed", "a"]
    assert result.edge_ids == ["e1"]


def test_incoming_and_outgoing_edge_traversal() -> None:
    events = {
        item["_id"]: item
        for item in [
            event("incoming", service="keystone"),
            event("seed", service="nova-api"),
            event("outgoing", service="neutron"),
        ]
    }
    result = build_subgraph_from_edges(
        events["seed"],
        events,
        [edge("incoming-edge", "incoming", "seed"), edge("outgoing-edge", "seed", "outgoing")],
        max_depth=3,
        max_events=100,
    )

    assert result.event_ids == ["seed", "incoming", "outgoing"]
    assert result.edge_ids == ["incoming-edge", "outgoing-edge"]
    assert result.services == ["keystone", "neutron", "nova-api"]


def test_graph_traversal_respects_max_events_and_time_window() -> None:
    events = {
        item["_id"]: item
        for item in [
            event("seed", minute=0),
            event("inside", minute=1),
            event("outside", minute=20),
        ]
    }
    result = build_subgraph_from_edges(
        events["seed"],
        events,
        [edge("inside-edge", "seed", "inside"), edge("outside-edge", "seed", "outside")],
        max_depth=3,
        max_events=2,
        window_before=timedelta(minutes=10),
        window_after=timedelta(minutes=2),
    )

    assert result.event_ids == ["seed", "inside"]
    assert result.edge_ids == ["inside-edge"]


def test_idempotent_incident_upsert() -> None:
    async def run() -> tuple[int, int]:
        incident_collection = FakeIncidentCollection()
        repository = StubIncidentRepository(incident_collection)
        first = await repository.process_batch(10)
        second = await repository.process_batch(10)
        return first.incidents_inserted, second.incidents_skipped

    assert asyncio.run(run()) == (1, 1)


def test_process_available_batches_reaches_second_batch_and_detects_error() -> None:
    async def run() -> tuple[list[int], list[Any], dict[str, Any]]:
        parsed = FakeParsedCollection(
            [
                event("a", parsed_second=1),
                event("b", parsed_second=2),
                event("c", parsed_second=3, level="ERROR", message="new failure"),
            ]
        )
        incidents = FakeIncidentCollection()
        repository = incident_repository(parsed, incidents=incidents)

        metrics = await repository.process_available_batches(2)
        state = await repository.state_collection.find_one({"_id": "incident_worker_v1"})
        return [metric.events_scanned for metric in metrics], list(incidents.keys), state

    events_scanned, incident_keys, state = asyncio.run(run())

    assert events_scanned == [2, 1]
    assert incident_keys == [("c", "incident-v1")]
    assert state["last_id"] == "c"


def test_newly_inserted_error_after_checkpoint_is_detected() -> None:
    async def run() -> tuple[int, list[Any]]:
        parsed = FakeParsedCollection([event("a", parsed_second=1)])
        incidents = FakeIncidentCollection()
        repository = incident_repository(parsed, incidents=incidents)
        await repository.process_available_batches(10)

        parsed.documents.append(event("new-error", parsed_second=2, level="ERROR", message="boom"))
        metrics = await repository.process_available_batches(10)
        return metrics[0].events_scanned, list(incidents.keys)

    events_scanned, incident_keys = asyncio.run(run())

    assert events_scanned == 1
    assert incident_keys == [("new-error", "incident-v1")]


def test_checkpoint_resumes_after_restart() -> None:
    async def run() -> tuple[list[str], dict[str, Any]]:
        parsed = FakeParsedCollection(
            [
                event("a", parsed_second=1),
                event("b", parsed_second=2),
                event("c", parsed_second=3),
            ]
        )
        state = FakeStateCollection()
        first = incident_repository(parsed, state=state)
        await first.process_batch(2)

        second = incident_repository(parsed, state=state)
        events = await second.fetch_batch(10)
        state_doc = await state.find_one({"_id": "incident_worker_v1"})
        return [event["_id"] for event in events], state_doc

    fetched_ids, state_doc = asyncio.run(run())

    assert fetched_ids == ["c"]
    assert state_doc["last_id"] == "b"


def test_checkpoint_does_not_advance_after_processing_failure() -> None:
    async def run() -> tuple[dict[str, Any] | None, list[str]]:
        parsed = FakeParsedCollection(
            [
                event("a", parsed_second=1),
                event("b", parsed_second=2, level="ERROR", message="boom"),
            ]
        )
        repository = incident_repository(parsed, incidents=FailingIncidentCollection())
        try:
            await repository.process_batch(10)
        except RuntimeError:
            pass
        state_doc = await repository.state_collection.find_one({"_id": "incident_worker_v1"})
        retry_events = await repository.fetch_batch(10)
        return state_doc, [event["_id"] for event in retry_events]

    state_doc, retry_ids = asyncio.run(run())

    assert state_doc is None
    assert retry_ids == ["a", "b"]


class FakeBulkResult:
    def __init__(self, upserted_count: int) -> None:
        self.upserted_count = upserted_count


class FakeIncidentCollection:
    def __init__(self) -> None:
        self.keys: set[tuple[Any, str]] = set()

    async def bulk_write(self, operations: list[Any], ordered: bool = False) -> FakeBulkResult:
        del ordered
        inserted = 0
        for operation in operations:
            key = (
                operation._filter["seed_event_id"],
                operation._filter["incident_version"],
            )
            if key in self.keys:
                continue
            self.keys.add(key)
            inserted += 1
        return FakeBulkResult(inserted)


class FailingIncidentCollection(FakeIncidentCollection):
    async def bulk_write(self, operations: list[Any], ordered: bool = False) -> FakeBulkResult:
        del operations, ordered
        raise RuntimeError("bulk write failed")


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self._limit: int | None = None

    def sort(self, spec: Any, direction: Any | None = None) -> FakeCursor:
        del direction
        if isinstance(spec, str):
            fields = [(spec, 1)]
        else:
            fields = list(spec)
        for field, order in reversed(fields):
            self.documents.sort(key=lambda document: document.get(field), reverse=order < 0)
        return self

    def limit(self, value: int) -> FakeCursor:
        self._limit = value
        return self

    async def to_list(self, length: int) -> list[dict[str, Any]]:
        limit = self._limit if self._limit is not None else length
        return self.documents[:limit]


class FakeParsedCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents

    async def create_indexes(self, indexes: list[Any]) -> None:
        del indexes

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor(
            [document for document in self.documents if matches_query(document, query)]
        )


class FakeEdgeCollection:
    async def create_indexes(self, indexes: list[Any]) -> None:
        del indexes

    def find(self, query: dict[str, Any]) -> FakeCursor:
        del query
        return FakeCursor([])


class FakeStateCollection:
    def __init__(self) -> None:
        self.documents: dict[Any, dict[str, Any]] = {}

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        document = self.documents.get(query["_id"])
        return dict(document) if document else None

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> None:
        del upsert
        key = query["_id"]
        document = dict(self.documents.get(key, {"_id": key}))
        document.update(update.get("$setOnInsert", {}))
        document.update(update.get("$set", {}))
        self.documents[key] = document


def matches_query(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for field, expected in query.items():
        if field == "$or":
            if not any(matches_query(document, option) for option in expected):
                return False
            continue
        actual = document.get(field)
        if isinstance(expected, dict):
            if "$exists" in expected and (field in document) != expected["$exists"]:
                return False
            if "$gt" in expected and not actual > expected["$gt"]:
                return False
            if "$gte" in expected and not actual >= expected["$gte"]:
                return False
            if "$lte" in expected and not actual <= expected["$lte"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if actual != expected:
            return False
    return True


def incident_repository(
    parsed: FakeParsedCollection,
    incidents: FakeIncidentCollection | None = None,
    state: FakeStateCollection | None = None,
) -> IncidentRepository:
    return IncidentRepository(
        parsed_collection=parsed,
        edge_collection=FakeEdgeCollection(),
        incident_collection=incidents or FakeIncidentCollection(),
        state_collection=state or FakeStateCollection(),
        worker_state_key="incident_worker_v1",
        correlation_version="correlation-v1",
        incident_version="incident-v1",
    )


class StubIncidentRepository(IncidentRepository):
    def __init__(self, incident_collection: FakeIncidentCollection) -> None:
        super().__init__(
            parsed_collection=None,
            edge_collection=None,
            incident_collection=incident_collection,
            state_collection=FakeStateCollection(),
            worker_state_key="incident_worker_v1",
            correlation_version="correlation-v1",
            incident_version="incident-v1",
        )
        self.seed = event("seed", message="request failed", level="ERROR")

    async def fetch_batch(self, batch_size: int) -> list[dict[str, Any]]:
        del batch_size
        return [self.seed]

    async def build_subgraph(self, seed_event: dict[str, Any]) -> object:
        del seed_event
        return build_subgraph_from_edges(
            self.seed,
            events_by_id={"seed": self.seed},
            edges=[],
        )

    async def save_checkpoint(self, event: dict[str, Any]) -> None:
        del event
