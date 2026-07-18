import asyncio
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient, Response
from pymongo.errors import BulkWriteError

from backend import main
from backend.models import RawJournalRecord, raw_record_to_document
from backend.repository import RawLogRepository


class InsertManyResult:
    def __init__(self, inserted_ids: list[int]) -> None:
        self.inserted_ids = inserted_ids


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str], dict] = {}

    async def create_indexes(self, indexes: list[object]) -> list[str]:
        return ["uniq_boot_id_journal_cursor"]

    async def insert_many(self, documents: list[dict], ordered: bool = False) -> InsertManyResult:
        inserted_ids: list[int] = []
        write_errors: list[dict] = []

        for index, document in enumerate(documents):
            key = (document["boot_id"], document["journal_cursor"])
            if key in self.documents:
                write_errors.append({"index": index, "code": 11000, "errmsg": "duplicate key"})
                continue
            self.documents[key] = document
            inserted_ids.append(index)

        if write_errors:
            raise BulkWriteError({"writeErrors": write_errors, "nInserted": len(inserted_ids)})

        return InsertManyResult(inserted_ids)


def run_request(method: str, url: str, json: dict | None = None) -> Response:
    collection = FakeCollection()
    repository = RawLogRepository(collection)
    app = main.create_app(lifespan_context=None)

    async def override_repository() -> RawLogRepository:
        return repository

    app.dependency_overrides[main.get_repository] = override_repository

    async def _request() -> Response:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=True),
            base_url="http://test",
        ) as client:
            return await client.request(method, url, json=json)

    try:
        return asyncio.run(_request())
    finally:
        app.dependency_overrides.clear()


def test_health() -> None:
    response = run_request("GET", "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_insert_batch_preserves_message_and_adds_received_at() -> None:
    response = run_request(
        "POST",
        "/logs/batch",
        json={
            "records": [
                {
                    "boot_id": "boot-1",
                    "journal_cursor": "cursor-1",
                    "message": "nova-api raw message: keep [brackets] and spacing",
                    "unit": "nova-api.service",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "received_count": 1,
        "inserted_count": 1,
        "duplicate_count": 0,
    }


def test_duplicate_records_are_ignored_safely() -> None:
    payload = {
        "records": [
            {
                "boot_id": "boot-1",
                "journal_cursor": "cursor-1",
                "message": "first copy",
            },
            {
                "boot_id": "boot-1",
                "journal_cursor": "cursor-1",
                "message": "duplicate copy",
            },
        ]
    }
    collection = FakeCollection()
    repository = RawLogRepository(collection)
    app = main.create_app(lifespan_context=None)

    async def override_repository() -> RawLogRepository:
        return repository

    app.dependency_overrides[main.get_repository] = override_repository

    async def _post_twice() -> tuple[Response, Response]:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=True),
            base_url="http://test",
        ) as client:
            first = await client.post("/logs/batch", json=payload)
            second = await client.post("/logs/batch", json=payload)
            return first, second

    try:
        first_response, second_response = asyncio.run(_post_twice())
    finally:
        app.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert first_response.json() == {
        "received_count": 2,
        "inserted_count": 1,
        "duplicate_count": 1,
    }
    assert second_response.status_code == 200
    assert second_response.json() == {
        "received_count": 2,
        "inserted_count": 0,
        "duplicate_count": 2,
    }


def test_authenticated_collector_has_an_independent_rate_bucket(monkeypatch) -> None:
    settings = main.get_settings()
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: settings.__class__(
            **{
                **settings.__dict__,
                "rca_internal_service_token": "collector-token",
                "batch_rate_limit_per_minute": 1,
            }
        ),
    )
    repository = RawLogRepository(FakeCollection())
    app = main.create_app(lifespan_context=None)
    app.dependency_overrides[main.get_repository] = lambda: repository
    payload = {
        "records": [{"boot_id": "boot", "journal_cursor": "one", "message": "line"}]
    }

    async def _post() -> tuple[Response, Response, Response]:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=True),
            base_url="http://test",
        ) as client:
            collector = await client.post(
                "/logs/batch",
                json=payload,
                headers={"X-RCA-Service-Token": "collector-token"},
            )
            operator = await client.post("/logs/batch", json=payload)
            limited_operator = await client.post("/logs/batch", json=payload)
            return collector, operator, limited_operator

    collector, operator, limited_operator = asyncio.run(_post())

    assert collector.status_code == 200
    assert operator.status_code == 200
    assert limited_operator.status_code == 429


def test_raw_record_to_document_keeps_message_exact() -> None:
    record = RawJournalRecord(
        boot_id="boot-1",
        journal_cursor="cursor-1",
        message="  raw ERROR line: do not parse or trim  ",
    )
    received_at = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)

    document = raw_record_to_document(record, received_at)

    assert document["message"] == record.message
    assert document["received_at"] == received_at


def test_batch_record_limit_is_enforced() -> None:
    response = run_request(
        "POST",
        "/logs/batch",
        json={
            "records": [
                {"boot_id": "boot", "journal_cursor": str(index), "message": "line"}
                for index in range(501)
            ]
        },
    )

    assert response.status_code == 413
