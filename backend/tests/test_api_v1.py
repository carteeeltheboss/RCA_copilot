import asyncio
import os
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from httpx import ASGITransport, AsyncClient

from backend import main
from backend.config import get_settings
from backend.database import get_rca_repository
from backend.providers.models import ProviderResult
from backend.providers.registry import ProviderRegistry
from backend.providers.security import SecretBox, normalize_and_validate_provider_url
from backend.repository import RCARepository


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = list(documents)

    def sort(self, spec: Any, direction: int | None = None) -> "FakeCursor":
        fields = spec if isinstance(spec, list) else [(spec, direction or 1)]
        for field, order in reversed(fields):
            self.documents.sort(key=lambda item: item.get(field) or 0, reverse=order == -1)
        return self

    def limit(self, length: int) -> "FakeCursor":
        self.documents = self.documents[:length]
        return self

    def skip(self, length: int) -> "FakeCursor":
        self.documents = self.documents[length:]
        return self

    async def to_list(self, length: int) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self.documents[:length]]


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    async def create_indexes(self, indexes: list[object]) -> list[str]:
        return []

    async def count_documents(self, query: dict[str, Any]) -> int:
        return len([item for item in self.documents if _matches(item, query)])

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor([item for item in self.documents if _matches(item, query)])

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return next((deepcopy(item) for item in self.documents if _matches(item, query)), None)

    async def replace_one(self, query: dict[str, Any], document: dict[str, Any], upsert: bool = False) -> None:
        for index, item in enumerate(self.documents):
            if _matches(item, query):
                self.documents[index] = deepcopy(document)
                return
        if upsert:
            self.documents.append(deepcopy(document))

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        for item in self.documents:
            if _matches(item, query):
                item.update(deepcopy(update.get("$set", {})))
                return

    async def update_many(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        for item in self.documents:
            if _matches(item, query):
                item.update(deepcopy(update.get("$set", {})))

    async def delete_one(self, query: dict[str, Any]) -> None:
        self.documents = [item for item in self.documents if not _matches(item, query)]

    async def insert_one(self, document: dict[str, Any]) -> None:
        self.documents.append(deepcopy(document))


def _matches(item: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        if item.get(key) != expected:
            return False
    return True


def _repo() -> RCARepository:
    provider_configs = FakeCollection()
    return RCARepository(
        raw_logs=FakeCollection(),
        parsed_logs=FakeCollection(),
        event_edges=FakeCollection(),
        incidents=FakeCollection(),
        worker_state=FakeCollection(),
        provider_configs=provider_configs,
        config_audit_log=FakeCollection(),
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "provider_type": "llm",
        "provider_kind": "openai_compatible",
        "display_name": "Unit provider",
        "base_url": "https://provider.test/v1/",
        "model_name": "unit-model",
        "enabled": False,
        "timeout_seconds": 5,
        "retry_count": 0,
        "verify_tls": True,
        "extra_config": {},
    }
    payload.update(overrides)
    return payload


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _client(repo: RCARepository):
    app = main.create_app(lifespan_context=None)

    async def override_repo() -> RCARepository:
        return repo

    app.dependency_overrides[get_rca_repository] = override_repo
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _set_env(master_key: str | None = "unit-test-master-key") -> None:
    get_settings.cache_clear()
    os.environ["RCA_INTERNAL_SERVICE_TOKEN"] = "test-token"
    os.environ["RCA_PROVIDER_ALLOWED_HOSTS"] = "provider.test"
    if master_key is None:
        os.environ.pop("RCA_PROVIDER_MASTER_KEY", None)
    else:
        os.environ["RCA_PROVIDER_MASTER_KEY"] = master_key


def _clear_env() -> None:
    for key in [
        "RCA_INTERNAL_SERVICE_TOKEN",
        "RCA_PROVIDER_ALLOWED_HOSTS",
        "RCA_PROVIDER_MASTER_KEY",
        "RCA_PROVIDER_ALLOW_LOCALHOST",
    ]:
        os.environ.pop(key, None)
    get_settings.cache_clear()


def test_internal_service_token_required() -> None:
    _set_env()
    app = main.create_app(lifespan_context=None)

    async def _request():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/v1/providers")

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 401


def test_unavailable_ai_endpoint_returns_structured_503() -> None:
    _set_env()
    app = main.create_app(lifespan_context=None)

    async def _request():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/incidents/incident-1/explain", headers={"X-RCA-Service-Token": "test-token"})

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "unavailable"
    assert response.json()["detail"]["reason"] == "No active LLM provider configured"


def test_secret_box_encrypts_and_decrypts_without_plaintext() -> None:
    box = SecretBox("unit-test-master-key")
    encrypted = box.encrypt("secret-value")

    assert encrypted != "secret-value"
    assert box.decrypt(encrypted) == "secret-value"


def test_provider_url_rejects_metadata_endpoint() -> None:
    settings = get_settings()
    result = normalize_and_validate_provider_url("http://169.254.169.254/latest/meta-data", settings)

    assert not result.ok
    assert "blocked" in result.error


def test_create_provider_draft_encrypts_secret_and_get_masks_secret() -> None:
    _set_env()
    repo = _repo()

    async def _request():
        async with await _client(repo) as client:
            created = await client.post(
                "/api/v1/providers",
                json=_payload(api_key="secret-value"),
                headers={"X-RCA-Service-Token": "test-token"},
            )
            provider_id = created.json()["provider_id"]
            fetched = await client.get(f"/api/v1/providers/{provider_id}", headers={"X-RCA-Service-Token": "test-token"})
            return created, fetched

    try:
        created, fetched = _run(_request())
    finally:
        _clear_env()

    stored = repo.provider_configs.documents[0]
    assert created.status_code == 201
    assert stored["api_key_encrypted"] != "secret-value"
    assert "api_key_encrypted" not in fetched.json()
    assert fetched.json()["api_key_masked"] == "configured"


def test_missing_master_key_rejects_secret_save() -> None:
    _set_env(master_key=None)
    repo = _repo()

    async def _request():
        async with await _client(repo) as client:
            return await client.post(
                "/api/v1/providers",
                json=_payload(api_key="secret-value"),
                headers={"X-RCA-Service-Token": "test-token"},
            )

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 400
    assert "MASTER_KEY" in response.json()["detail"]["error"]


def test_validate_url_rejects_unsafe_provider_url() -> None:
    _set_env()
    repo = _repo()

    async def _request():
        async with await _client(repo) as client:
            return await client.post(
                "/api/v1/providers",
                json=_payload(base_url="http://169.254.169.254/latest"),
                headers={"X-RCA-Service-Token": "test-token"},
            )

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 400
    assert "blocked" in response.json()["detail"]["error"]


def test_connection_success_activation_and_audit_log(monkeypatch) -> None:
    _set_env()
    repo = _repo()

    async def success(*args: Any, **kwargs: Any) -> ProviderResult:
        return ProviderResult(status="success", latency_ms=12, provider_identity="mock", models=["m1"])

    monkeypatch.setattr("backend.providers.base.BaseProviderAdapter.test_connection", success)

    async def _request():
        async with await _client(repo) as client:
            created = await client.post("/api/v1/providers", json=_payload(), headers={"X-RCA-Service-Token": "test-token"})
            provider_id = created.json()["provider_id"]
            tested = await client.post(f"/api/v1/providers/{provider_id}/test", headers={"X-RCA-Service-Token": "test-token"})
            activated = await client.post(f"/api/v1/providers/{provider_id}/activate", headers={"X-RCA-Service-Token": "test-token"})
            return tested, activated

    try:
        tested, activated = _run(_request())
    finally:
        _clear_env()

    assert tested.status_code == 200
    assert tested.json()["provider"]["last_test_status"] == "success"
    assert activated.status_code == 200
    assert activated.json()["provider"]["active"] is True
    assert await_count(repo.config_audit_log.documents, "test_connection") == 1
    assert await_count(repo.config_audit_log.documents, "activate") == 1


def test_connection_failure_and_failed_activation_keeps_previous_active(monkeypatch) -> None:
    _set_env()
    repo = _repo()
    results = [
        ProviderResult(status="success", latency_ms=5, provider_identity="mock"),
        ProviderResult(status="failure", latency_ms=6, error="mock failure"),
    ]

    async def next_result(*args: Any, **kwargs: Any) -> ProviderResult:
        return results.pop(0)

    monkeypatch.setattr("backend.providers.base.BaseProviderAdapter.test_connection", next_result)

    async def _request():
        async with await _client(repo) as client:
            first = await client.post("/api/v1/providers", json=_payload(display_name="first"), headers={"X-RCA-Service-Token": "test-token"})
            first_id = first.json()["provider_id"]
            await client.post(f"/api/v1/providers/{first_id}/test", headers={"X-RCA-Service-Token": "test-token"})
            await client.post(f"/api/v1/providers/{first_id}/activate", headers={"X-RCA-Service-Token": "test-token"})
            second = await client.post("/api/v1/providers", json=_payload(display_name="second"), headers={"X-RCA-Service-Token": "test-token"})
            second_id = second.json()["provider_id"]
            tested = await client.post(f"/api/v1/providers/{second_id}/test", headers={"X-RCA-Service-Token": "test-token"})
            activated = await client.post(f"/api/v1/providers/{second_id}/activate", headers={"X-RCA-Service-Token": "test-token"})
            active = await client.get("/api/v1/providers/active", headers={"X-RCA-Service-Token": "test-token"})
            return tested, activated, active

    try:
        tested, activated, active = _run(_request())
    finally:
        _clear_env()

    assert tested.json()["provider"]["last_test_status"] == "failure"
    assert activated.status_code == 409
    assert len(active.json()["items"]) == 1
    assert active.json()["items"][0]["display_name"] == "first"


def test_rollback_restores_previous_tested_config(monkeypatch) -> None:
    _set_env()
    repo = _repo()

    async def success(*args: Any, **kwargs: Any) -> ProviderResult:
        return ProviderResult(status="success", latency_ms=1, provider_identity="mock")

    monkeypatch.setattr("backend.providers.base.BaseProviderAdapter.test_connection", success)

    async def _request():
        async with await _client(repo) as client:
            created = await client.post("/api/v1/providers", json=_payload(model_name="v1"), headers={"X-RCA-Service-Token": "test-token"})
            provider_id = created.json()["provider_id"]
            await client.post(f"/api/v1/providers/{provider_id}/test", headers={"X-RCA-Service-Token": "test-token"})
            await client.post(f"/api/v1/providers/{provider_id}/activate", headers={"X-RCA-Service-Token": "test-token"})
            await client.put(f"/api/v1/providers/{provider_id}", json=_payload(model_name="v2"), headers={"X-RCA-Service-Token": "test-token"})
            await client.post(f"/api/v1/providers/{provider_id}/test", headers={"X-RCA-Service-Token": "test-token"})
            await client.post(f"/api/v1/providers/{provider_id}/activate", headers={"X-RCA-Service-Token": "test-token"})
            rolled_back = await client.post(f"/api/v1/providers/{provider_id}/rollback/1", headers={"X-RCA-Service-Token": "test-token"})
            return rolled_back

    try:
        rolled_back = _run(_request())
    finally:
        _clear_env()

    assert rolled_back.status_code == 200
    assert rolled_back.json()["provider"]["model_name"] == "v1"
    assert await_count(repo.config_audit_log.documents, "rollback") == 1


def test_provider_capabilities_are_enforced() -> None:
    adapter = ProviderRegistry().get("llm", "anthropic")
    assert adapter is not None

    result = _run(adapter.embed({}, ["text"]))

    assert result.status == "unavailable"
    assert result.unsupported_capability == "embedding"


def await_count(rows: list[dict[str, Any]], action: str) -> int:
    return len([row for row in rows if row.get("action") == action])
