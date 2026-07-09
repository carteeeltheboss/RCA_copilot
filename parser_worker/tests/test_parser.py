from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from parser_worker.parser import parse_raw_log
from parser_worker.repository import ParserRepository


REQUEST_UUID = "11111111-1111-4111-8111-111111111111"
RESOURCE_UUID = "22222222-2222-4222-8222-222222222222"


def parse(message: object, **overrides: object) -> dict[str, object]:
    document = {
        "_id": "raw-1",
        "service": "devstack@n-api.service",
        "message": message,
        "priority": "3",
        "timestamp": "2026-07-05T10:00:00Z",
        "received_at": datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    }
    document.update(overrides)
    return parse_raw_log(document, "parser-v1")


def test_request_id_extraction() -> None:
    parsed = parse(f"ERROR nova.api [req-{REQUEST_UUID}] request failed")

    assert parsed["request_id"] == f"req-{REQUEST_UUID}"


def test_resource_uuid_extraction() -> None:
    parsed = parse(f"ERROR instance {RESOURCE_UUID} failed")

    assert parsed["resource_ids"] == [RESOURCE_UUID]


def test_request_uuid_excluded_from_resource_ids() -> None:
    parsed = parse(
        f"ERROR nova.api [req-{REQUEST_UUID}] instance {RESOURCE_UUID} failed "
        f"while handling {REQUEST_UUID}"
    )

    assert parsed["request_id"] == f"req-{REQUEST_UUID}"
    assert parsed["resource_ids"] == [RESOURCE_UUID]


def test_host_extraction_from_journal_field() -> None:
    parsed = parse("ERROR nova-api failed", _HOSTNAME="compute-01")

    assert parsed["host"] == "compute-01"


def test_multiline_logs_are_preserved_and_parsed() -> None:
    parsed = parse(
        "2026-07-05 10:00:00.000 1234 ERROR nova.compute.manager "
        f"[req-{REQUEST_UUID}] Build failed\n"
        'Traceback (most recent call last):\n  File "/opt/stack/nova/nova/compute.py", '
        'line 42, in spawn\nException: failed'
    )

    assert "Traceback" in str(parsed["message"])
    assert parsed["level"] == "ERROR"
    assert parsed["module"] == "nova.compute.manager"
    assert parsed["pid"] == 1234
    assert parsed["file"] == "/opt/stack/nova/nova/compute.py"
    assert parsed["line"] == 42
    assert parsed["function"] == "spawn"


def test_ansi_sequences_are_stripped() -> None:
    parsed = parse("\x1b[31mERROR\x1b[0m nova-api failed")

    assert parsed["message"] == "ERROR nova-api failed"
    assert parsed["level"] == "ERROR"


def test_parser_failures_are_recorded() -> None:
    parsed = parse(["not", "a", "string"])

    assert parsed["parse_status"] == "failure"
    assert parsed["parse_error"] == "message must be a string"
    assert parsed["resource_ids"] == []


class FakeCursor:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    async def to_list(self, length: int) -> list[dict[str, object]]:
        return self.documents[:length]


class FakeRawCollection:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    def aggregate(self, _pipeline: list[dict[str, object]]) -> FakeCursor:
        return FakeCursor(self.documents)


class FakeBulkResult:
    def __init__(self, upserted_count: int) -> None:
        self.upserted_count = upserted_count


class FakeParsedCollection:
    name = "parsed_logs"

    def __init__(self) -> None:
        self.keys: set[tuple[object, object]] = set()

    async def create_indexes(self, _indexes: list[object]) -> list[str]:
        return ["uniq_source_log_id_parser_version"]

    async def bulk_write(self, operations: list[object], ordered: bool = False) -> FakeBulkResult:
        upserted_count = 0
        for operation in operations:
            key = (
                operation._filter["source_log_id"],  # type: ignore[attr-defined]
                operation._filter["parser_version"],  # type: ignore[attr-defined]
            )
            if key in self.keys:
                continue
            self.keys.add(key)
            upserted_count += 1
        return FakeBulkResult(upserted_count)


class FakeStateCollection:
    def __init__(self) -> None:
        self.document: dict[str, object] = {}

    async def update_one(self, query: dict[str, object], update: dict[str, object], upsert: bool = False) -> None:
        self.document.update(update.get("$set", {}))  # type: ignore[arg-type]
        self.document.update(update.get("$setOnInsert", {}))  # type: ignore[arg-type]


def test_duplicate_prevention_uses_idempotent_upserts() -> None:
    raw_collection = FakeRawCollection(
        [
            {
                "_id": "raw-1",
                "message": "ERROR first",
                "received_at": datetime(2026, 7, 5, tzinfo=UTC),
            }
        ]
    )
    parsed_collection = FakeParsedCollection()
    repository = ParserRepository(raw_collection, parsed_collection, "parser-v1")

    async def process_twice() -> tuple[int, int]:
        return (
            await repository.process_batch(100),
            await repository.process_batch(100),
        )

    assert asyncio.run(process_twice()) == (1, 0)


def test_parser_repository_writes_worker_state_heartbeat() -> None:
    state_collection = FakeStateCollection()
    repository = ParserRepository(
        FakeRawCollection([]),
        FakeParsedCollection(),
        "parser-v1",
        state_collection=state_collection,
        worker_state_key="parser_worker_v1",
    )

    asyncio.run(repository.heartbeat(processed_count=3))

    assert state_collection.document["worker"] == "parser_worker_v1"
    assert state_collection.document["last_batch_count"] == 3
    assert state_collection.document["parser_version"] == "parser-v1"
    assert "updated_at" in state_collection.document
