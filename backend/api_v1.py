from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from backend.config import Settings, get_settings
from backend.database import get_rca_repository
from backend.providers.registry import ProviderRegistry
from backend.providers.security import SecretBox
from backend.repository import RCARepository
from backend.security import require_internal_token, require_provider_policy


router = APIRouter(prefix="/api/v1")
registry = ProviderRegistry()


class ProviderPayload(BaseModel):
    provider_type: str = Field(pattern="^(llm|embedding|reranker|vector_store)$")
    provider_kind: str
    display_name: str = Field(min_length=1)
    base_url: str | None = None
    model_name: str | None = None
    enabled: bool = False
    timeout_seconds: int = Field(default=10, ge=1, le=120)
    retry_count: int = Field(default=0, ge=0, le=5)
    verify_tls: bool = True
    api_key: str | None = None
    capabilities: list[str] | None = None
    extra_config: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(protected_namespaces=())


class ActorPayload(BaseModel):
    actor: str = "horizon"


def _actor(payload: ActorPayload | None = None) -> str:
    return (payload.actor if payload else "horizon") or "horizon"


@router.get("/system/summary")
async def system_summary(repository: RCARepository = Depends(get_rca_repository)) -> dict[str, Any]:
    return await repository.system_summary()


@router.get("/system/health")
async def system_health(repository: RCARepository = Depends(get_rca_repository)) -> dict[str, Any]:
    return await repository.system_health()


@router.get("/incidents")
async def list_incidents(
    severity: str | None = None,
    status_value: str | None = Query(default=None, alias="status"),
    service: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    request_id: str | None = None,
    resource_id: str | None = None,
    q: str | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 25,
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    filters = {
        "severity": severity,
        "status": status_value,
        "service": service,
        "start_date": start_date,
        "end_date": end_date,
        "request_id": request_id,
        "resource_id": resource_id,
        "q": q,
    }
    return await repository.list_incidents(filters, sort, page, page_size)


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str, repository: RCARepository = Depends(get_rca_repository)
) -> dict[str, Any]:
    incident = await repository.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail={"error": "incident not found"})
    return incident


@router.get("/incidents/{incident_id}/graph")
async def get_incident_graph(
    incident_id: str,
    max_nodes: int = Query(default=100, ge=1, le=250),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    graph = await repository.get_graph(incident_id, max_nodes=max_nodes)
    if not graph:
        raise HTTPException(status_code=404, detail={"error": "incident graph not found"})
    return graph


@router.get("/incidents/{incident_id}/timeline")
async def get_incident_timeline(
    incident_id: str,
    limit: int = Query(default=250, ge=1, le=500),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    timeline = await repository.get_timeline(incident_id, limit=limit)
    if not timeline:
        raise HTTPException(status_code=404, detail={"error": "incident timeline not found"})
    return timeline


@router.get("/incidents/{incident_id}/events/{event_id}")
async def get_incident_event(
    incident_id: str,
    event_id: str,
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    event = await repository.get_event(incident_id, event_id)
    if not event:
        raise HTTPException(status_code=404, detail={"error": "event not found"})
    return event


@router.post("/incidents/{incident_id}/similar")
async def ai_unavailable(
    incident_id: str, _: None = Depends(require_internal_token)
) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "unavailable",
            "reason": "No active LLM provider configured",
            "incident_id": incident_id,
        },
    )


@router.post("/incidents/{incident_id}/explain")
async def explain_incident(
    incident_id: str,
    _: None = Depends(require_internal_token),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    evidence = await repository.get_incident_evidence(incident_id)
    if not evidence:
        raise HTTPException(status_code=404, detail={"error": "incident not found"})

    provider = await repository.active_provider("llm")
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unavailable",
                "reason": "No active LLM provider configured",
                "incident_id": incident_id,
            },
        )
    adapter = registry.get(provider["provider_type"], provider["provider_kind"])
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unavailable",
                "reason": "No supported LLM provider adapter configured",
                "incident_id": incident_id,
            },
        )

    package = _build_evidence_package(evidence)
    result = await adapter.generate(provider, package)
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unavailable",
                "reason": "Active LLM provider is unreachable",
                "incident_id": incident_id,
            },
        )

    answer_text = (
        str((result.data or {}).get("answer_text") or "")
        if isinstance(result.data, dict)
        else str(result.data or "")
    )
    answer = _parse_answer(answer_text)
    return {
        "incident_id": incident_id,
        "provider": {
            "provider_id": provider.get("provider_id"),
            "provider_kind": provider.get("provider_kind"),
            "model_name": provider.get("model_name"),
        },
        "status": "ok",
        "answer": answer,
    }


@router.get("/providers")
async def list_providers(
    _: None = Depends(require_provider_policy("rca_copilot:providers:list")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    return {"items": await repository.list_providers()}


@router.post("/providers", status_code=201)
async def create_provider(
    payload: ProviderPayload,
    _: None = Depends(require_provider_policy("rca_copilot:providers:create")),
    repository: RCARepository = Depends(get_rca_repository),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    provider_id = f"{payload.provider_type}-{uuid4().hex[:12]}"
    return await _save_provider(provider_id, payload, repository, settings, actor="horizon")


@router.get("/providers/active")
async def active_providers(
    _: None = Depends(require_provider_policy("rca_copilot:providers:list")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    return {"items": await repository.active_providers()}


@router.get("/providers/health")
async def provider_health(
    _: None = Depends(require_provider_policy("rca_copilot:providers:list")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    return {"providers": await repository.provider_availability()}


@router.get("/providers/{provider_id}")
async def get_provider(
    provider_id: str,
    _: None = Depends(require_provider_policy("rca_copilot:providers:show")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    provider = await repository.get_provider_latest(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail={"error": "provider not found"})
    sanitized = await repository.list_providers()
    return next(
        item
        for item in sanitized
        if item["provider_id"] == provider_id
        and item["config_version"] == provider["config_version"]
    )


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    payload: ProviderPayload,
    _: None = Depends(require_provider_policy("rca_copilot:providers:update")),
    repository: RCARepository = Depends(get_rca_repository),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not await repository.get_provider_latest(provider_id):
        raise HTTPException(status_code=404, detail={"error": "provider not found"})
    return await _save_provider(provider_id, payload, repository, settings, actor="horizon")


@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: str,
    _: None = Depends(require_provider_policy("rca_copilot:providers:update")),
    repository: RCARepository = Depends(get_rca_repository),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    provider = await _provider_or_404(repository, provider_id)
    adapter = registry.get(provider["provider_type"], provider["provider_kind"])
    if adapter is None:
        raise HTTPException(status_code=400, detail={"error": "unsupported provider"})
    api_key = SecretBox(settings.rca_provider_master_key).decrypt(provider.get("api_key_encrypted"))
    result = await adapter.test_connection(provider, settings, api_key=api_key)
    result_data = result.to_dict()
    saved = await repository.update_provider_test(provider, result_data, "horizon")
    return {"provider": saved, "result": result_data}


@router.post("/providers/{provider_id}/activate")
async def activate_provider(
    provider_id: str,
    _: None = Depends(require_provider_policy("rca_copilot:providers:activate")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    provider = await _provider_or_404(repository, provider_id)
    try:
        return {"provider": await repository.activate_provider(provider, "horizon")}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc


@router.post("/providers/{provider_id}/disable")
async def disable_provider(
    provider_id: str,
    _: None = Depends(require_provider_policy("rca_copilot:providers:update")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    provider = await _provider_or_404(repository, provider_id)
    return {"provider": await repository.disable_provider(provider, "horizon")}


@router.get("/providers/{provider_id}/history")
async def provider_history(
    provider_id: str,
    _: None = Depends(require_provider_policy("rca_copilot:providers:show")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    return {"items": await repository.history(provider_id)}


@router.post("/providers/{provider_id}/rollback/{config_version}")
async def rollback_provider(
    provider_id: str,
    config_version: int,
    _: None = Depends(require_provider_policy("rca_copilot:providers:rollback")),
    repository: RCARepository = Depends(get_rca_repository),
) -> dict[str, Any]:
    provider = await repository.get_provider_version(provider_id, config_version)
    if not provider:
        raise HTTPException(status_code=404, detail={"error": "provider version not found"})
    try:
        return {"provider": await repository.rollback_provider(provider, "horizon")}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: str,
    _: None = Depends(require_provider_policy("rca_copilot:providers:delete")),
    repository: RCARepository = Depends(get_rca_repository),
) -> Response:
    provider = await _provider_or_404(repository, provider_id)
    try:
        await repository.delete_provider_draft(provider, "horizon")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    return Response(status_code=204)


async def _save_provider(
    provider_id: str,
    payload: ProviderPayload,
    repository: RCARepository,
    settings: Settings,
    actor: str,
) -> dict[str, Any]:
    adapter = registry.get(payload.provider_type, payload.provider_kind)
    if adapter is None:
        raise HTTPException(status_code=400, detail={"error": "unsupported provider type or kind"})
    data = payload.model_dump(exclude={"api_key"})
    validation = adapter.validate_config(data, settings)
    if not validation.ok:
        raise HTTPException(status_code=400, detail={"error": validation.error})
    data = validation.normalized_config
    now = datetime.now(UTC)
    previous = await repository.get_provider_latest(provider_id)
    encrypted = previous.get("api_key_encrypted") if previous else None
    if payload.api_key:
        try:
            encrypted = SecretBox(settings.rca_provider_master_key).encrypt(payload.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    document = {
        **data,
        "provider_id": provider_id,
        "active": False,
        "status": "draft",
        "api_key_encrypted": encrypted,
        "config_version": await repository.next_provider_version(provider_id),
        "created_at": previous.get("created_at") if previous else now,
        "created_by": previous.get("created_by") if previous else actor,
        "updated_at": now,
        "updated_by": actor,
        "last_tested_at": None,
        "last_test_status": "not_tested",
        "last_test_latency_ms": None,
        "last_test_error": None,
        "activated_at": None,
    }
    return await repository.save_provider(document, actor)


async def _provider_or_404(repository: RCARepository, provider_id: str) -> dict[str, Any]:
    provider = await repository.get_provider_latest(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail={"error": "provider not found"})
    return provider


def _build_evidence_package(evidence: dict[str, Any]) -> dict[str, Any]:
    incident = evidence["incident"]
    compact = {
        "incident_id": incident.get("incident_id"),
        "severity": incident.get("severity"),
        "status": incident.get("status"),
        "seed_reason": incident.get("seed_reason")
        or incident.get("reason")
        or incident.get("title"),
        "service": incident.get("service"),
        "started_at": incident.get("started_at"),
        "duration_ms": incident.get("duration_ms"),
        "event_count": incident.get("event_count", len(incident.get("event_ids") or [])),
        "edge_count": incident.get("edge_count", len(incident.get("edge_ids") or [])),
        "involved_services": list(incident.get("services") or []),
        "request_ids": _unique_compact(
            [incident.get("request_id"), *(incident.get("request_ids") or [])], limit=20
        ),
        "resource_ids": _unique_compact(incident.get("resource_ids") or [], limit=20),
        "deterministic_summary": incident.get("summary"),
        "enrichment": {
            "root_cause_hypothesis": incident.get("root_cause_hypothesis"),
            "impact": incident.get("impact"),
            "recommended_actions": incident.get("recommended_actions"),
            "enriched_at": incident.get("enriched_at"),
        },
        "timeline_events": list(incident.get("timeline") or [])[:30],
        "event_evidence": evidence.get("events", [])[:40],
        "correlation_edges": evidence.get("edges", [])[:80],
        "truncated": {
            "events": bool(evidence.get("events_truncated")),
            "edges": bool(evidence.get("edges_truncated")),
        },
    }
    compact["timeline_events"] = [_truncate_nested(item) for item in compact["timeline_events"]]
    prompt = (
        "You are RCA Copilot for OpenStack incidents.\n\n"
        "Use only the evidence provided.\n"
        "Do not invent services, timestamps, resources, or root causes.\n"
        "If evidence is insufficient, say so.\n"
        "Edges are correlations, not proven causality.\n"
        "Separate facts from hypotheses.\n"
        "Return concise structured RCA.\n\n"
        "Return JSON with keys: summary, likely_failure_area, evidence, hypotheses, "
        "recommended_next_checks, confidence, limitations.\n\n"
        f"Evidence:\n{json.dumps(compact, default=str, separators=(',', ':'))}"
    )
    if len(prompt) > 24000:
        compact["event_evidence"] = compact["event_evidence"][:20]
        compact["correlation_edges"] = compact["correlation_edges"][:40]
        compact["timeline_events"] = compact["timeline_events"][:15]
        prompt = (
            "You are RCA Copilot for OpenStack incidents.\n\n"
            "Use only the evidence provided.\nDo not invent services, timestamps, resources, or root causes.\n"
            "If evidence is insufficient, say so.\nEdges are correlations, not proven causality.\n"
            "Separate facts from hypotheses.\nReturn concise structured RCA.\n\n"
            "Return JSON with keys: summary, likely_failure_area, evidence, hypotheses, recommended_next_checks, confidence, limitations.\n\n"
            f"Evidence:\n{json.dumps(compact, default=str, separators=(',', ':'))}"
        )
    return {"prompt": prompt, "evidence": compact}


def _parse_answer(answer_text: str) -> dict[str, Any]:
    text = answer_text.strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except ValueError:
                parsed = None
    if isinstance(parsed, dict):
        return parsed
    return {"answer_text": text}


def _unique_compact(values: list[Any], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _truncate_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _truncate_nested(val)
            for key, val in value.items()
            if str(key).lower() not in {"raw", "raw_log", "full_log", "payload"}
        }
    if isinstance(value, list):
        return [_truncate_nested(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:500]
    return value
