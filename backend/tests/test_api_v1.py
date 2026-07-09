import asyncio
import os
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from httpx import ASGITransport, AsyncClient

from backend import main
from backend.config import get_settings
from backend.database import get_rca_repository
from backend.providers.adapters.ollama import OllamaAdapter
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
        actual = item.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in expected["$in"]:
                return False
            continue
        if isinstance(expected, dict) and "$exists" in expected:
            if (actual is not None) != bool(expected["$exists"]):
                return False
            continue
        if actual != expected:
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


def _incident(**overrides: Any) -> dict[str, Any]:
    item = {
        "incident_id": "incident-1",
        "severity": "critical",
        "status": "enriched",
        "title": "nova compute error",
        "service": "nova-compute",
        "started_at": datetime(2026, 7, 9, tzinfo=UTC),
        "duration_ms": 120000,
        "event_ids": ["event-1"],
        "edge_ids": ["edge-1"],
        "event_count": 1,
        "edge_count": 1,
        "services": ["nova-compute", "neutron-server"],
        "request_ids": ["req-1"],
        "resource_ids": ["server-1"],
        "summary": "Deterministic summary",
        "timeline": [{"timestamp": "2026-07-09T10:00:00Z", "message": "short event", "raw_log": "x" * 2000}],
    }
    item.update(overrides)
    return item


def _active_provider(**overrides: Any) -> dict[str, Any]:
    item = {
        "provider_id": "llm-unit",
        "provider_type": "llm",
        "provider_kind": "ollama",
        "display_name": "Unit Ollama",
        "base_url": "http://provider.test",
        "model_name": "qwen2.5-coder:7b",
        "enabled": True,
        "active": True,
        "status": "active",
        "timeout_seconds": 5,
        "retry_count": 0,
        "verify_tls": False,
        "capabilities": ["llm", "model_listing"],
        "config_version": 1,
        "last_test_status": "success",
    }
    item.update(overrides)
    return item


def test_system_health_uses_fresh_worker_state_for_parser_and_correlation() -> None:
    repo = _repo()
    now = datetime.now(UTC)
    repo.worker_state.documents.extend(
        [
            {"_id": "parser_worker_v1", "worker": "parser_worker_v1", "updated_at": now},
            {"_id": "correlation_worker_v1", "worker": "correlation_worker_v1", "updated_at": now},
            {"_id": "incident_worker_v1", "worker": "incident_worker_v1", "updated_at": now},
            {"_id": "enrichment_worker_v1", "worker": "enrichment_worker_v1", "updated_at": now},
        ]
    )

    health = _run(repo.system_health())
    statuses = {item["component"]: item["status"] for item in health["components"]}

    assert statuses["parser-worker"] == "healthy"
    assert statuses["correlation-worker"] == "healthy"
    assert statuses["incident-worker"] == "healthy"
    assert statuses["enrichment-worker"] == "healthy"


def test_graph_and_timeline_endpoints_return_incident_evidence() -> None:
    repo = _repo()
    repo.incidents.documents.append(
        _incident(
            seed_event_id="event-1",
            timeline=[
                {
                    "event_id": "event-1",
                    "timestamp": "2026-07-09T10:00:00Z",
                    "level": "ERROR",
                    "service": "nova-compute",
                    "message": "build failed",
                    "request_id": "req-1",
                    "resource_ids": ["server-1"],
                }
            ],
        )
    )
    repo.parsed_logs.documents.append({"_id": "event-1", "service": "nova-compute", "level": "ERROR", "message": "build failed"})
    repo.event_edges.documents.append({"_id": "edge-1", "source_event_id": "event-1", "target_event_id": "event-1", "reason": "same_request_id", "confidence": 1.0})

    async def _request():
        async with await _client(repo) as client:
            graph = await client.get("/api/v1/incidents/incident-1/graph")
            timeline = await client.get("/api/v1/incidents/incident-1/timeline")
            return graph, timeline

    graph_response, timeline_response = _run(_request())

    assert graph_response.status_code == 200
    assert timeline_response.status_code == 200
    assert graph_response.json()["nodes"][0]["seed"] is True
    assert graph_response.json()["edges"][0]["reason"] == "same_request_id"
    assert timeline_response.json()["items"][0]["event_id"] == "event-1"


def test_no_provider_explain_returns_structured_503() -> None:
    _set_env()
    repo = _repo()
    repo.incidents.documents.append(_incident())

    async def _request():
        async with await _client(repo) as client:
            return await client.post("/api/v1/incidents/incident-1/explain", headers={"X-RCA-Service-Token": "test-token"})

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "unavailable"
    assert response.json()["detail"]["reason"] == "No active LLM provider configured"


def test_incident_not_found_returns_404() -> None:
    _set_env()
    repo = _repo()
    repo.provider_configs.documents.append(_active_provider())

    async def _request():
        async with await _client(repo) as client:
            return await client.post("/api/v1/incidents/missing/explain", headers={"X-RCA-Service-Token": "test-token"})

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 404


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


def test_active_llm_provider_selected_and_structured_response(monkeypatch) -> None:
    _set_env()
    repo = _repo()
    repo.incidents.documents.append(_incident())
    repo.parsed_logs.documents.append({"_id": "event-1", "service": "nova-compute", "level": "ERROR", "message": "build failed"})
    repo.event_edges.documents.append({"_id": "edge-1", "source_event_id": "event-1", "target_event_id": "event-1", "reason": "same request"})
    repo.provider_configs.documents.append(_active_provider(provider_id="llm-active"))
    seen: dict[str, Any] = {}

    async def generate(self: Any, config: dict[str, Any], evidence_package: dict[str, Any]) -> ProviderResult:
        seen["provider_id"] = config["provider_id"]
        seen["evidence"] = evidence_package["evidence"]
        return ProviderResult(
            status="success",
            latency_ms=10,
            provider_identity="ollama",
            data={"answer_text": '{"summary":"grounded","likely_failure_area":"nova-compute","evidence":["build failed"],"hypotheses":[],"recommended_next_checks":[],"confidence":"medium","limitations":"unit"}'},
        )

    monkeypatch.setattr("backend.providers.adapters.ollama.OllamaAdapter.generate", generate)

    async def _request():
        async with await _client(repo) as client:
            return await client.post("/api/v1/incidents/incident-1/explain", headers={"X-RCA-Service-Token": "test-token"})

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 200
    assert seen["provider_id"] == "llm-active"
    body = response.json()
    assert body["provider"]["model_name"] == "qwen2.5-coder:7b"
    assert body["answer"]["summary"] == "grounded"


def test_provider_unreachable_returns_503(monkeypatch) -> None:
    _set_env()
    repo = _repo()
    repo.incidents.documents.append(_incident())
    repo.provider_configs.documents.append(_active_provider())

    async def generate(self: Any, config: dict[str, Any], evidence_package: dict[str, Any]) -> ProviderResult:
        return ProviderResult(status="failure", latency_ms=1, error="provider request timed out")

    monkeypatch.setattr("backend.providers.adapters.ollama.OllamaAdapter.generate", generate)

    async def _request():
        async with await _client(repo) as client:
            return await client.post("/api/v1/incidents/incident-1/explain", headers={"X-RCA-Service-Token": "test-token"})

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "Active LLM provider is unreachable"


def test_evidence_package_excludes_raw_full_log_dump(monkeypatch) -> None:
    _set_env()
    repo = _repo()
    repo.incidents.documents.append(_incident(timeline=[{"message": "kept", "raw": "x" * 169000, "payload": "hidden"}]))
    repo.parsed_logs.documents.append({"_id": "event-1", "service": "nova-compute", "message": "y" * 2000, "raw_log": "x" * 169000})
    repo.provider_configs.documents.append(_active_provider())
    seen: dict[str, Any] = {}

    async def generate(self: Any, config: dict[str, Any], evidence_package: dict[str, Any]) -> ProviderResult:
        seen["package"] = evidence_package
        return ProviderResult(status="success", latency_ms=1, data={"answer_text": "plain explanation"})

    monkeypatch.setattr("backend.providers.adapters.ollama.OllamaAdapter.generate", generate)

    async def _request():
        async with await _client(repo) as client:
            return await client.post("/api/v1/incidents/incident-1/explain", headers={"X-RCA-Service-Token": "test-token"})

    try:
        response = _run(_request())
    finally:
        _clear_env()

    assert response.status_code == 200
    package_text = str(seen["package"])
    assert "raw_log" not in package_text
    assert "payload" not in package_text
    assert "x" * 1000 not in package_text
    assert len(seen["package"]["evidence"]["event_evidence"][0]["message"]) == 500
    assert response.json()["answer"]["answer_text"] == "plain explanation"


def test_ollama_adapter_calls_chat_endpoint_and_handles_success(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"model": "qwen2.5-coder:7b", "message": {"content": '{"summary":"ok"}'}, "done": True}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            calls.append({"kwargs": kwargs})

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
            calls.append({"url": url, "json": json})
            return FakeResponse()

    monkeypatch.setattr("backend.providers.adapters.ollama.httpx.AsyncClient", FakeClient)
    result = _run(
        OllamaAdapter().generate(
            _active_provider(base_url="http://ollama.test", timeout_seconds=12),
            {"prompt": "Explain from evidence."},
        )
    )

    assert result.success
    assert calls[0]["kwargs"]["timeout"] == 12.0
    assert calls[1]["url"] == "http://ollama.test/api/chat"
    assert calls[1]["json"]["model"] == "qwen2.5-coder:7b"
    assert result.data["answer_text"] == '{"summary":"ok"}'


def test_ollama_adapter_handles_timeout_failure(monkeypatch) -> None:
    import httpx

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any]) -> object:
            raise httpx.TimeoutException("too slow")

    monkeypatch.setattr("backend.providers.adapters.ollama.httpx.AsyncClient", FakeClient)
    result = _run(OllamaAdapter().generate(_active_provider(), {"prompt": "test"}))

    assert result.status == "failure"
    assert result.error == "provider request timed out"


def await_count(rows: list[dict[str, Any]], action: str) -> int:
    return len([row for row in rows if row.get("action") == action])
