from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from enrichment_worker.enricher import build_enrichment_document
from enrichment_worker.repository import EnrichmentRepository


BASE_TIME = datetime(2026, 7, 5, 10, 0, tzinfo=UTC)


def event(
    event_id: str,
    minute: int = 0,
    message: str = "all good",
    level: str = "INFO",
    service: str = "nova-api",
    request_id: str | None = "req-11111111-1111-4111-8111-111111111111",
    resource_ids: list[str] | None = None,
    host: str | None = "compute-1",
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "_id": event_id,
        "parse_status": "success",
        "timestamp": BASE_TIME + timedelta(minutes=minute),
        "message": message,
        "level": level,
        "service": service,
        "request_id": request_id,
        "resource_ids": resource_ids or [],
        "host": host,
    }
    return document


def edge(edge_id: str, source: str = "seed", target: str = "next") -> dict[str, Any]:
    return {
        "_id": edge_id,
        "source_event_id": source,
        "target_event_id": target,
        "correlation_version": "correlation-v1",
    }


def incident(
    incident_id: str = "incident-a",
    event_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    status: str = "candidate",
) -> dict[str, Any]:
    return {
        "_id": incident_id,
        "incident_id": incident_id,
        "seed_event_id": "seed",
        "seed_reason": "level:ERROR",
        "severity": "ERROR",
        "status": status,
        "title": "nova-api: request failed",
        "event_ids": event_ids or ["seed"],
        "edge_ids": edge_ids or [],
        "resource_ids": ["server-a"],
        "services": ["nova-api"],
        "incident_version": "incident-v1",
    }


def test_single_event_incident() -> None:
    result = build_enrichment_document(
        incident=incident(),
        events=[event("seed", message="request failed", level="ERROR", resource_ids=["server-a"])],
        edges=[],
        enrichment_version="enrichment-v1",
        enriched_at=BASE_TIME,
    )

    assert result["status"] == "enriched"
    assert result["event_count"] == 1
    assert result["edge_count"] == 0
    assert result["error_count"] == 1
    assert result["warning_count"] == 0
    assert result["duration_ms"] == 0
    assert "Evidence is limited to one event" in result["summary"]
    assert "Evidence is limited to one event" in result["evidence_summary"]


def test_multi_event_timeline_ordering() -> None:
    result = build_enrichment_document(
        incident=incident(event_ids=["later", "seed", "middle"]),
        events=[
            event("later", minute=3, service="neutron"),
            event("seed", minute=0, message="request failed", level="ERROR"),
            event("middle", minute=1, service="keystone"),
        ],
        edges=[edge("edge-1")],
        enrichment_version="enrichment-v1",
        enriched_at=BASE_TIME,
    )

    assert [entry["event_id"] for entry in result["timeline"]] == ["seed", "middle", "later"]
    assert result["first_event_at"] == BASE_TIME
    assert result["last_event_at"] == BASE_TIME + timedelta(minutes=3)


def test_duplicate_service_resource_removal() -> None:
    result = build_enrichment_document(
        incident=incident(),
        events=[
            event("seed", level="ERROR", service="nova-api", resource_ids=["server-a", "server-a"]),
            event("next", service="nova-api", resource_ids=["server-a", "server-b"]),
        ],
        edges=[],
        enrichment_version="enrichment-v1",
        enriched_at=BASE_TIME,
    )

    assert result["resource_ids"] == ["server-a", "server-b"]
    assert "nova-api" in result["summary"]
    assert result["hosts"] == ["compute-1"]
    assert result["levels"] == ["ERROR", "INFO"]


def test_duration_calculation() -> None:
    result = build_enrichment_document(
        incident=incident(),
        events=[event("seed", minute=0), event("next", minute=2)],
        edges=[],
        enrichment_version="enrichment-v1",
        enriched_at=BASE_TIME,
    )

    assert result["duration_ms"] == 120000


def test_missing_event_handling() -> None:
    result = build_enrichment_document(
        incident=incident(event_ids=["seed", "missing"]),
        events=[event("seed", level="ERROR")],
        edges=[],
        enrichment_version="enrichment-v1",
        enriched_at=BASE_TIME,
    )

    assert result["event_count"] == 1
    assert [entry["event_id"] for entry in result["timeline"]] == ["seed"]
    assert "Evidence is limited to one event" in result["evidence_summary"]


def test_deterministic_summaries() -> None:
    args = {
        "incident": incident(),
        "events": [event("seed", level="ERROR", message="request failed", resource_ids=["server-a"])],
        "edges": [edge("edge-1")],
        "enrichment_version": "enrichment-v1",
        "enriched_at": BASE_TIME,
    }
    first = build_enrichment_document(**args)
    second = build_enrichment_document(**args)

    assert first["summary"] == second["summary"]
    assert first["impact_summary"] == second["impact_summary"]
    assert first["evidence_summary"] == second["evidence_summary"]
    assert "Correlation edges: 1" in first["evidence_summary"]
    assert "caused" not in first["summary"].lower()


def test_idempotency() -> None:
    async def run() -> tuple[int, int, dict[str, Any]]:
        incidents = FakeIncidentCollection([incident(event_ids=["seed"])])
        repository = enrichment_repository(
            incidents=incidents,
            parsed=FakeCollection([event("seed", level="ERROR")]),
            edges=FakeCollection([]),
        )
        first = await repository.process_batch(10)
        second = await repository.process_batch(10)
        stored = incidents.documents["incident-a"]
        return first.incidents_enriched, second.incidents_scanned, stored

    first_enriched, second_scanned, stored = asyncio.run(run())

    assert first_enriched == 1
    assert second_scanned == 0
    assert stored["status"] == "enriched"
    assert stored["title"] == "nova-api: request failed"


def test_checkpoint_resume() -> None:
    async def run() -> tuple[list[str], dict[str, Any] | None]:
        incidents = FakeIncidentCollection(
            [
                incident("incident-a", event_ids=["a"]),
                incident("incident-b", event_ids=["b"]),
                incident("incident-c", event_ids=["c"]),
            ]
        )
        state = FakeStateCollection()
        parsed = FakeCollection([event("a"), event("b"), event("c")])
        first = enrichment_repository(incidents=incidents, parsed=parsed, state=state)
        await first.process_batch(2)

        second = enrichment_repository(incidents=incidents, parsed=parsed, state=state)
        fetched = await second.fetch_batch(10)
        state_doc = await state.find_one({"_id": "enrichment_worker_v1"})
        return [document["_id"] for document in fetched], state_doc

    fetched_ids, state_doc = asyncio.run(run())

    assert fetched_ids == ["incident-c"]
    assert state_doc is not None
    assert state_doc["last_id"] == "incident-b"


class FakeUpdateResult:
    def __init__(self, modified_count: int) -> None:
        self.modified_count = modified_count


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self._limit: int | None = None

    def sort(self, spec: Any, direction: Any | None = None) -> FakeCursor:
        if isinstance(spec, str):
            fields = [(spec, direction or 1)]
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


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = {document["_id"]: dict(document) for document in documents}

    async def create_indexes(self, indexes: list[Any]) -> None:
        del indexes

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor(
            [dict(document) for document in self.documents.values() if matches_query(document, query)]
        )


class FakeIncidentCollection(FakeCollection):
    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> FakeUpdateResult:
        del upsert
        document = self.documents.get(query["_id"])
        if document is None or not matches_query(document, query):
            return FakeUpdateResult(0)
        document.update(update.get("$set", {}))
        self.documents[query["_id"]] = document
        return FakeUpdateResult(1)


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
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$gt" in expected and not actual > expected["$gt"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if actual != expected:
            return False
    return True


def enrichment_repository(
    incidents: FakeIncidentCollection,
    parsed: FakeCollection,
    edges: FakeCollection | None = None,
    state: FakeStateCollection | None = None,
) -> EnrichmentRepository:
    return EnrichmentRepository(
        parsed_collection=parsed,
        edge_collection=edges or FakeCollection([]),
        incident_collection=incidents,
        state_collection=state or FakeStateCollection(),
        worker_state_key="enrichment_worker_v1",
        enrichment_version="enrichment-v1",
    )
