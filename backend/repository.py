from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING, IndexModel
from pymongo.errors import BulkWriteError

from backend.models import InsertResult, RawJournalRecord, raw_record_to_document


class RawLogRepository:
    def __init__(self, collection: object) -> None:
        self.collection = collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_indexes(
            [
                IndexModel(
                    [("boot_id", ASCENDING), ("journal_cursor", ASCENDING)],
                    unique=True,
                    name="uniq_boot_id_journal_cursor",
                )
            ]
        )

    async def insert_raw_logs(self, records: list[RawJournalRecord]) -> InsertResult:
        if not records:
            return InsertResult(inserted_count=0, duplicate_count=0)

        received_at = datetime.now(UTC)
        documents = [raw_record_to_document(record, received_at) for record in records]

        try:
            result = await self.collection.insert_many(documents, ordered=False)
            return InsertResult(inserted_count=len(result.inserted_ids), duplicate_count=0)
        except BulkWriteError as exc:
            details = exc.details or {}
            write_errors = details.get("writeErrors", [])
            duplicate_count = sum(1 for error in write_errors if error.get("code") == 11000)
            non_duplicate_errors = [error for error in write_errors if error.get("code") != 11000]
            if non_duplicate_errors:
                raise

            inserted_count = int(details.get("nInserted", 0))
            return InsertResult(inserted_count=inserted_count, duplicate_count=duplicate_count)


class RCARepository:
    def __init__(
        self,
        raw_logs: object,
        parsed_logs: object,
        event_edges: object,
        incidents: object,
        worker_state: object,
        provider_configs: object,
        config_audit_log: object,
    ) -> None:
        self.raw_logs = raw_logs
        self.parsed_logs = parsed_logs
        self.event_edges = event_edges
        self.incidents = incidents
        self.worker_state = worker_state
        self.provider_configs = provider_configs
        self.config_audit_log = config_audit_log

    async def ensure_indexes(self) -> None:
        await self.incidents.create_indexes(
            [
                IndexModel([("incident_id", ASCENDING)], unique=True, name="uniq_incident_id"),
                IndexModel([("started_at", ASCENDING)], name="idx_started_at"),
                IndexModel([("status", ASCENDING)], name="idx_status"),
                IndexModel(
                    [("severity", ASCENDING), ("status", ASCENDING)],
                    name="idx_incidents_severity_status",
                ),
                IndexModel([("service", ASCENDING)], name="idx_incidents_service"),
                IndexModel([("request_id", ASCENDING)], name="idx_incidents_request_id"),
                IndexModel([("resource_ids", ASCENDING)], name="idx_incidents_resource_ids"),
            ]
        )
        await self.provider_configs.create_indexes(
            [
                IndexModel(
                    [("provider_id", ASCENDING), ("config_version", ASCENDING)],
                    unique=True,
                    name="uniq_provider_version",
                ),
                IndexModel(
                    [
                        ("provider_type", ASCENDING),
                        ("provider_kind", ASCENDING),
                        ("status", ASCENDING),
                    ],
                    name="idx_provider_type_kind_status",
                ),
            ]
        )
        await self.config_audit_log.create_indexes(
            [
                IndexModel(
                    [("provider_id", ASCENDING), ("timestamp", ASCENDING)],
                    name="idx_audit_provider_timestamp",
                ),
                IndexModel([("timestamp", ASCENDING)], name="idx_audit_timestamp"),
            ]
        )

    async def system_summary(self) -> dict[str, Any]:
        (
            raw_count,
            parsed_count,
            edge_count,
            incident_count,
            candidate_count,
            enriched_count,
            active_providers,
        ) = await _gather(
            self.raw_logs.count_documents({}),
            self.parsed_logs.count_documents({"parse_status": "success"}),
            self.event_edges.count_documents({}),
            self.incidents.count_documents({}),
            self.incidents.count_documents({"status": "candidate"}),
            self.incidents.count_documents({"status": "enriched"}),
            self.provider_configs.count_documents({"status": "active", "enabled": True}),
        )
        latest_incidents = await self.list_incidents({}, "newest", 1, 5)
        return {
            "counts": {
                "raw_logs": raw_count,
                "parsed_events": parsed_count,
                "correlation_edges": edge_count,
                "incidents": incident_count,
                "candidate_incidents": candidate_count,
                "enriched_incidents": enriched_count,
                "active_providers": active_providers,
            },
            "pipeline": await self.pipeline_state(),
            "recent_incidents": latest_incidents["items"],
            "ai_availability": await self.provider_availability(),
        }

    async def pipeline_state(self) -> list[dict[str, Any]]:
        states = await self.worker_state.find({}).to_list(length=100)
        state_by_worker = {str(item.get("worker") or item.get("_id")): item for item in states}
        stages = [
            ("journald", self.raw_logs, "received_at", "unknown"),
            ("collector", self.raw_logs, "received_at", "unknown"),
            ("ingestion API", self.raw_logs, "received_at", "healthy"),
            ("raw logs", self.raw_logs, "received_at", "healthy"),
            ("parser", self.parsed_logs, "parsed_at", "unknown"),
            ("parsed events", self.parsed_logs, "parsed_at", "healthy"),
            ("correlation", self.event_edges, "created_at", "unknown"),
            ("event graph", self.event_edges, "created_at", "healthy"),
            ("incident detection", self.incidents, "updated_at", "unknown"),
            ("enrichment", self.incidents, "enriched_at", "unknown"),
        ]
        rows = []
        for name, collection, field, default_status in stages:
            latest = (
                await collection.find({field: {"$exists": True}})
                .sort(field, -1)
                .limit(1)
                .to_list(length=1)
            )
            count = await collection.count_documents({})
            worker = next(
                (value for key, value in state_by_worker.items() if name.split()[0] in key), None
            )
            rows.append(
                {
                    "name": name,
                    "status": _worker_status(worker, default_status),
                    "latest_activity_time": _json_safe(latest[0].get(field)) if latest else None,
                    "processed_count": count,
                }
            )
        return rows

    async def provider_availability(self) -> dict[str, Any]:
        providers = await self.provider_configs.find({"active": True, "enabled": True}).to_list(
            length=100
        )
        result = {}
        for provider_type in ["llm", "embedding", "reranker", "vector_store"]:
            provider = next(
                (item for item in providers if item.get("provider_type") == provider_type), None
            )
            result[provider_type] = {
                "status": provider.get("status", "unconfigured") if provider else "unconfigured",
                "display_name": provider.get("display_name") if provider else "Not configured",
                "provider_kind": provider.get("provider_kind") if provider else None,
                "model_name": provider.get("model_name") if provider else None,
                "last_test_status": provider.get("last_test_status") if provider else None,
            }
        return result

    async def system_health(self) -> dict[str, Any]:
        health = [
            {
                "component": "RCA backend",
                "status": "healthy",
                "endpoint": "localhost",
                "enabled": True,
            }
        ]
        try:
            await self.raw_logs.database.client.admin.command("ping")
            health.append(
                {
                    "component": "MongoDB",
                    "status": "healthy",
                    "endpoint": "configured MongoDB",
                    "enabled": True,
                }
            )
        except Exception as exc:
            health.append(
                {
                    "component": "MongoDB",
                    "status": "unavailable",
                    "endpoint": "configured MongoDB",
                    "enabled": True,
                    "last_error": str(exc)[:160],
                }
            )
        state_rows = await self.worker_state.find({}).to_list(length=100)
        state_by_worker = {str(item.get("worker") or item.get("_id")): item for item in state_rows}
        latest_raw = (
            await self.raw_logs.find({"received_at": {"$exists": True}})
            .sort("received_at", -1)
            .limit(1)
            .to_list(length=1)
        )
        health.append(
            {
                "component": "collector",
                "status": "healthy" if latest_raw else "unknown",
                "endpoint": "raw log ingestion",
                "latest_successful_check": (
                    _json_safe(latest_raw[0].get("received_at")) if latest_raw else None
                ),
                "enabled": True,
            }
        )
        worker_components = [
            ("parser-worker", "parser_worker_v1"),
            ("correlation-worker", "correlation_worker_v1"),
            ("incident-worker", "incident_worker_v1"),
            ("enrichment-worker", "enrichment_worker_v1"),
        ]
        for component, key in worker_components:
            health.append(_worker_health_row(component, state_by_worker.get(key)))
        providers = await self.provider_configs.find({"active": True}).to_list(length=100)
        for provider_type in ["llm", "embedding", "reranker", "vector_store"]:
            provider = next(
                (item for item in providers if item.get("provider_type") == provider_type), None
            )
            health.append(_provider_health_row(provider_type, provider))
        llm_provider = next(
            (item for item in providers if item.get("provider_type") == "llm"), None
        )
        if llm_provider and llm_provider.get("provider_kind") == "ollama":
            health.append(
                {
                    "component": "MSI Ollama reachability",
                    "status": (
                        "healthy"
                        if llm_provider.get("last_test_status") == "success"
                        else "degraded"
                    ),
                    "endpoint": llm_provider.get("base_url"),
                    "latest_successful_check": _json_safe(llm_provider.get("last_tested_at")),
                    "response_latency": llm_provider.get("last_test_latency_ms"),
                    "last_error": llm_provider.get("last_test_error"),
                    "enabled": bool(llm_provider.get("enabled")),
                }
            )
        return {"components": health}

    async def list_incidents(
        self, filters: dict[str, Any], sort: str, page: int, page_size: int
    ) -> dict[str, Any]:
        query = _incident_query(filters)
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        sort_spec = _incident_sort(sort)
        total = await self.incidents.count_documents(query)
        cursor = (
            self.incidents.find(query).sort(sort_spec).skip((page - 1) * page_size).limit(page_size)
        )
        return {
            "items": [_incident_summary(item) for item in await cursor.to_list(length=page_size)],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    async def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        item = await self.incidents.find_one({"incident_id": incident_id})
        return _json_safe(item) if item else None

    async def get_graph(self, incident_id: str, max_nodes: int = 100) -> dict[str, Any] | None:
        incident = await self.get_incident(incident_id)
        if not incident:
            return None
        event_ids = [
            _coerce_id(str(value)) for value in list(incident.get("event_ids") or [])[:max_nodes]
        ]
        events = await self.parsed_logs.find({"_id": {"$in": event_ids}}).to_list(
            length=len(event_ids)
        )
        edge_ids = [_coerce_id(str(value)) for value in list(incident.get("edge_ids") or [])]
        edges = await self.event_edges.find({"_id": {"$in": edge_ids}}).to_list(
            length=len(edge_ids) or 1
        )
        event_id_set = {item.get("_id") for item in events}
        visible_edges = [
            edge
            for edge in edges
            if edge.get("source_event_id") in event_id_set
            and edge.get("target_event_id") in event_id_set
        ]
        return {
            "incident_id": incident_id,
            "nodes": [_graph_node(event, incident.get("seed_event_id")) for event in events],
            "edges": [_graph_edge(edge) for edge in visible_edges],
            "truncated": len(incident.get("event_ids") or []) > len(event_ids),
            "max_nodes": max_nodes,
        }

    async def get_timeline(self, incident_id: str, limit: int = 250) -> dict[str, Any] | None:
        incident = await self.get_incident(incident_id)
        if not incident:
            return None
        timeline = list(incident.get("timeline") or [])[: min(limit, 500)]
        return {
            "incident_id": incident_id,
            "items": _json_safe(timeline),
            "truncated": len(incident.get("timeline") or []) > len(timeline),
        }

    async def get_event(self, incident_id: str, event_id: str) -> dict[str, Any] | None:
        incident = await self.get_incident(incident_id)
        if not incident or event_id not in {str(item) for item in incident.get("event_ids", [])}:
            return None
        event = await self.parsed_logs.find_one({"_id": _coerce_id(event_id)})
        return _json_safe(event) if event else None

    async def get_incident_evidence(
        self, incident_id: str, max_events: int = 40, max_edges: int = 80
    ) -> dict[str, Any] | None:
        incident = await self.get_incident(incident_id)
        if not incident:
            return None
        event_ids = [
            _coerce_id(str(value)) for value in list(incident.get("event_ids") or [])[:max_events]
        ]
        edge_ids = [
            _coerce_id(str(value)) for value in list(incident.get("edge_ids") or [])[:max_edges]
        ]
        events = await self.parsed_logs.find({"_id": {"$in": event_ids}}).to_list(
            length=len(event_ids) or 1
        )
        edges = await self.event_edges.find({"_id": {"$in": edge_ids}}).to_list(
            length=len(edge_ids) or 1
        )
        return {
            "incident": incident,
            "events": [_safe_event_for_evidence(event) for event in events],
            "edges": [_safe_edge_for_evidence(edge) for edge in edges],
            "events_truncated": len(incident.get("event_ids") or []) > len(event_ids),
            "edges_truncated": len(incident.get("edge_ids") or []) > len(edge_ids),
        }

    async def list_providers(self) -> list[dict[str, Any]]:
        providers = (
            await self.provider_configs.find({})
            .sort(
                [("provider_type", ASCENDING), ("provider_id", ASCENDING), ("config_version", -1)]
            )
            .to_list(length=500)
        )
        return [_sanitize_provider(item) for item in providers]

    async def active_providers(self) -> list[dict[str, Any]]:
        providers = (
            await self.provider_configs.find({"active": True, "enabled": True})
            .sort("provider_type", ASCENDING)
            .to_list(length=20)
        )
        return [_sanitize_provider(item) for item in providers]

    async def active_provider(self, provider_type: str) -> dict[str, Any] | None:
        return await self.provider_configs.find_one(
            {"provider_type": provider_type, "active": True, "enabled": True}
        )

    async def get_provider_latest(self, provider_id: str) -> dict[str, Any] | None:
        items = (
            await self.provider_configs.find({"provider_id": provider_id})
            .sort("config_version", -1)
            .limit(1)
            .to_list(length=1)
        )
        return items[0] if items else None

    async def get_provider_version(
        self, provider_id: str, config_version: int
    ) -> dict[str, Any] | None:
        return await self.provider_configs.find_one(
            {"provider_id": provider_id, "config_version": config_version}
        )

    async def save_provider(
        self, document: dict[str, Any], actor: str, action: str = "save_draft"
    ) -> dict[str, Any]:
        await self.provider_configs.replace_one(
            {"provider_id": document["provider_id"], "config_version": document["config_version"]},
            document,
            upsert=True,
        )
        await self.audit(action, document, actor)
        return _sanitize_provider(document)

    async def next_provider_version(self, provider_id: str) -> int:
        latest = await self.get_provider_latest(provider_id)
        return int(latest.get("config_version", 0)) + 1 if latest else 1

    async def update_provider_test(
        self, provider: dict[str, Any], result: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        status = "inactive" if result["success"] else "failed"
        updates = {
            "status": status,
            "last_tested_at": now,
            "last_test_status": "success" if result["success"] else "failure",
            "last_test_latency_ms": result["latency_ms"],
            "last_test_error": result.get("error"),
            "updated_at": now,
            "updated_by": actor,
        }
        await self.provider_configs.update_one(
            {"provider_id": provider["provider_id"], "config_version": provider["config_version"]},
            {"$set": updates},
        )
        saved = await self.get_provider_version(provider["provider_id"], provider["config_version"])
        await self.audit("test_connection", saved or provider, actor, test_result=result)
        return _sanitize_provider(saved or provider)

    async def activate_provider(self, provider: dict[str, Any], actor: str) -> dict[str, Any]:
        offline_placeholder = bool(provider.get("extra_config", {}).get("offline_placeholder"))
        if provider.get("last_test_status") != "success" and not offline_placeholder:
            await self.audit(
                "activate_failed",
                provider,
                actor,
                activation_result={
                    "success": False,
                    "error": "provider must pass connection test before activation",
                },
            )
            raise ValueError("provider must pass connection test before activation")
        now = datetime.now(UTC)
        await self.provider_configs.update_many(
            {"provider_type": provider["provider_type"], "active": True},
            {
                "$set": {
                    "status": "inactive",
                    "active": False,
                    "updated_at": now,
                    "updated_by": actor,
                }
            },
        )
        await self.provider_configs.update_one(
            {"provider_id": provider["provider_id"], "config_version": provider["config_version"]},
            {
                "$set": {
                    "status": "active",
                    "active": True,
                    "enabled": True,
                    "activated_at": now,
                    "updated_at": now,
                    "updated_by": actor,
                }
            },
        )
        saved = await self.get_provider_version(provider["provider_id"], provider["config_version"])
        await self.audit("activate", saved or provider, actor, activation_result={"success": True})
        return _sanitize_provider(saved or provider)

    async def rollback_provider(self, provider: dict[str, Any], actor: str) -> dict[str, Any]:
        if provider.get("last_test_status") != "success":
            await self.audit(
                "rollback_failed",
                provider,
                actor,
                rollback_result={
                    "success": False,
                    "error": "rollback target must be a tested successful version",
                },
            )
            raise ValueError("rollback target must be a tested successful version")
        saved = await self.activate_provider(provider, actor)
        await self.audit(
            "rollback",
            provider,
            actor,
            rollback_result={"success": True, "config_version": provider.get("config_version")},
        )
        return saved

    async def disable_provider(self, provider: dict[str, Any], actor: str) -> dict[str, Any]:
        await self.provider_configs.update_one(
            {"provider_id": provider["provider_id"], "config_version": provider["config_version"]},
            {
                "$set": {
                    "enabled": False,
                    "active": False,
                    "status": "inactive",
                    "updated_at": datetime.now(UTC),
                    "updated_by": actor,
                }
            },
        )
        saved = await self.get_provider_version(provider["provider_id"], provider["config_version"])
        await self.audit("disable", saved or provider, actor)
        return _sanitize_provider(saved or provider)

    async def delete_provider_draft(self, provider: dict[str, Any], actor: str) -> None:
        if provider.get("status") not in {"draft", "failed", "unconfigured"}:
            raise ValueError("only unused draft or failed provider versions can be deleted")
        await self.provider_configs.delete_one(
            {"provider_id": provider["provider_id"], "config_version": provider["config_version"]}
        )
        await self.audit("delete_unused_draft", provider, actor)

    async def history(self, provider_id: str) -> list[dict[str, Any]]:
        rows = (
            await self.config_audit_log.find({"provider_id": provider_id})
            .sort("timestamp", -1)
            .limit(100)
            .to_list(length=100)
        )
        return [_json_safe(row) for row in rows]

    async def audit(self, action: str, provider: dict[str, Any], actor: str, **extra: Any) -> None:
        record = {
            "action": action,
            "provider_id": provider.get("provider_id"),
            "provider_type": provider.get("provider_type"),
            "config_version": provider.get("config_version"),
            "actor": actor,
            "timestamp": datetime.now(UTC),
            "old_non_secret_fields": extra.pop("old_non_secret_fields", None),
            "new_non_secret_fields": _non_secret_provider_fields(provider),
            **extra,
        }
        await self.config_audit_log.insert_one(record)


async def _gather(*awaitables: Any) -> tuple[Any, ...]:
    import asyncio

    return tuple(await asyncio.gather(*awaitables))


def _incident_query(filters: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for key in ["severity", "status", "service", "request_id"]:
        if filters.get(key):
            query[key] = filters[key]
    if filters.get("resource_id"):
        query["resource_ids"] = filters["resource_id"]
    if filters.get("start_date") or filters.get("end_date"):
        query["started_at"] = {}
        if filters.get("start_date"):
            query["started_at"]["$gte"] = filters["start_date"]
        if filters.get("end_date"):
            query["started_at"]["$lte"] = filters["end_date"]
    if filters.get("q"):
        query["$or"] = [
            {"incident_id": {"$regex": filters["q"], "$options": "i"}},
            {"title": {"$regex": filters["q"], "$options": "i"}},
            {"summary": {"$regex": filters["q"], "$options": "i"}},
        ]
    return query


def _incident_sort(sort: str) -> list[tuple[str, int]]:
    return {
        "oldest": [("started_at", ASCENDING)],
        "severity": [("severity", ASCENDING), ("started_at", -1)],
        "event_count": [("event_count", -1), ("started_at", -1)],
        "duration": [("duration_ms", -1), ("started_at", -1)],
    }.get(sort, [("started_at", -1)])


def _incident_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": item.get("incident_id"),
        "severity": item.get("severity"),
        "title": item.get("title"),
        "primary_service": item.get("service"),
        "involved_services": item.get("services", []),
        "status": item.get("status"),
        "event_count": item.get("event_count", len(item.get("event_ids", []))),
        "edge_count": item.get("edge_count", len(item.get("edge_ids", []))),
        "started_at": _json_safe(item.get("started_at")),
        "duration_ms": item.get("duration_ms", 0),
        "enrichment_status": "enriched" if item.get("status") == "enriched" else "pending",
    }


def _graph_node(event: dict[str, Any], seed_event_id: Any) -> dict[str, Any]:
    return {
        "id": str(event.get("_id")),
        "label": str(event.get("service") or "event"),
        "level": event.get("level"),
        "service": event.get("service"),
        "message": event.get("message"),
        "seed": str(event.get("_id")) == str(seed_event_id),
    }


def _graph_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(edge.get("_id")),
        "source": str(edge.get("source_event_id")),
        "target": str(edge.get("target_event_id")),
        "reason": edge.get("reason"),
        "confidence": edge.get("confidence"),
    }


def _safe_event_for_evidence(event: dict[str, Any]) -> dict[str, Any]:
    message = str(event.get("message") or event.get("summary") or "")
    return _json_safe(
        {
            "id": str(event.get("_id")),
            "timestamp": event.get("timestamp")
            or event.get("parsed_at")
            or event.get("received_at"),
            "service": event.get("service"),
            "level": event.get("level"),
            "event_type": event.get("event_type"),
            "request_id": event.get("request_id"),
            "resource_id": event.get("resource_id"),
            "message": message[:500],
        }
    )


def _safe_edge_for_evidence(edge: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
            "id": str(edge.get("_id")),
            "source_event_id": str(edge.get("source_event_id")),
            "target_event_id": str(edge.get("target_event_id")),
            "reason": edge.get("reason"),
            "confidence": edge.get("confidence"),
        }
    )


def _sanitize_provider(item: dict[str, Any]) -> dict[str, Any]:
    data = _json_safe(item)
    data.pop("_id", None)
    data.pop("api_key_encrypted", None)
    data["api_key_masked"] = "configured" if item.get("api_key_encrypted") else ""
    return data


def _non_secret_provider_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe(value)
        for key, value in item.items()
        if key not in {"_id", "api_key_encrypted"}
    }


def _worker_status(worker: dict[str, Any] | None, default: str) -> str:
    if worker is None:
        return default
    return "healthy" if worker.get("updated_at") or worker.get("last_id") else "unknown"


def _worker_health_row(component: str, worker: dict[str, Any] | None) -> dict[str, Any]:
    if not worker:
        return {"component": component, "status": "unknown", "enabled": True}
    updated_at = worker.get("updated_at")
    status = "healthy"
    if isinstance(updated_at, datetime):
        comparable = updated_at if updated_at.tzinfo is not None else updated_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - comparable > timedelta(seconds=90):
            status = "degraded"
    elif updated_at is None:
        status = "unknown"
    return {
        "component": component,
        "status": status,
        "endpoint": "worker_state",
        "latest_successful_check": _json_safe(updated_at),
        "response_latency": None,
        "last_error": None,
        "enabled": True,
    }


def _provider_health_row(provider_type: str, provider: dict[str, Any] | None) -> dict[str, Any]:
    if not provider:
        return {
            "component": f"{provider_type} provider",
            "status": "unconfigured",
            "enabled": False,
        }
    health_status = "healthy" if provider.get("last_test_status") == "success" else "degraded"
    if not provider.get("enabled", False):
        health_status = "disabled"
    return {
        "component": f"{provider_type} provider",
        "status": health_status,
        "endpoint": provider.get("base_url"),
        "latest_successful_check": _json_safe(provider.get("last_tested_at")),
        "response_latency": provider.get("last_test_latency_ms"),
        "last_error": provider.get("last_test_error"),
        "enabled": provider.get("enabled", False),
    }


def _coerce_id(value: str) -> Any:
    try:
        from bson import ObjectId

        if ObjectId.is_valid(value):
            return ObjectId(value)
    except Exception:
        pass
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    return str(value) if value.__class__.__name__ == "ObjectId" else value
