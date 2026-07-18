from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, IndexModel

from enrichment_worker.enricher import build_enrichment_document


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrichmentBatchMetrics:
    incidents_scanned: int
    incidents_enriched: int
    incidents_skipped: int
    incidents_failed: int


@dataclass(frozen=True)
class ScanCheckpoint:
    document_id: Any


class EnrichmentRepository:
    def __init__(
        self,
        parsed_collection: object,
        edge_collection: object,
        incident_collection: object,
        state_collection: object,
        worker_state_key: str,
        enrichment_version: str,
    ) -> None:
        self.parsed_collection = parsed_collection
        self.edge_collection = edge_collection
        self.incident_collection = incident_collection
        self.state_collection = state_collection
        self.worker_state_key = worker_state_key
        self.enrichment_version = enrichment_version

    async def ensure_indexes(self) -> None:
        await self.incident_collection.create_indexes(
            [
                IndexModel([("status", ASCENDING), ("_id", ASCENDING)], name="idx_status_id"),
                IndexModel(
                    [("enrichment_version", ASCENDING), ("_id", ASCENDING)],
                    name="idx_enrichment_version_id",
                ),
            ]
        )

    async def fetch_batch(self, batch_size: int) -> list[dict[str, Any]]:
        checkpoint = await self.load_checkpoint()
        query = self._batch_query(checkpoint)
        cursor = self.incident_collection.find(query).sort("_id", ASCENDING).limit(batch_size)
        return await cursor.to_list(length=batch_size)

    async def process_batch(self, batch_size: int) -> EnrichmentBatchMetrics:
        incidents = await self.fetch_batch(batch_size)
        enriched = 0
        skipped = 0
        failed = 0

        for incident in incidents:
            try:
                did_enrich = await self.enrich_incident(incident)
            except Exception:
                failed += 1
                LOGGER.exception("failed to enrich incident_id=%s", incident.get("_id"))
                break

            if did_enrich:
                enriched += 1
            else:
                skipped += 1
            await self.save_checkpoint(incident)

        metrics = EnrichmentBatchMetrics(
            incidents_scanned=len(incidents),
            incidents_enriched=enriched,
            incidents_skipped=skipped,
            incidents_failed=failed,
        )
        if (
            metrics.incidents_scanned
            or metrics.incidents_enriched
            or metrics.incidents_skipped
            or metrics.incidents_failed
        ):
            LOGGER.info(
                "enrichment batch incidents_scanned=%s incidents_enriched=%s "
                "incidents_skipped=%s incidents_failed=%s",
                metrics.incidents_scanned,
                metrics.incidents_enriched,
                metrics.incidents_skipped,
                metrics.incidents_failed,
            )
        return metrics

    async def process_available_batches(self, batch_size: int) -> list[EnrichmentBatchMetrics]:
        metrics: list[EnrichmentBatchMetrics] = []
        while True:
            batch_metrics = await self.process_batch(batch_size)
            metrics.append(batch_metrics)
            if batch_metrics.incidents_scanned < batch_size or batch_metrics.incidents_failed > 0:
                return metrics

    async def enrich_incident(self, incident: dict[str, Any]) -> bool:
        events = await self._fetch_by_ids(self.parsed_collection, incident.get("event_ids", []))
        edges = await self._fetch_by_ids(self.edge_collection, incident.get("edge_ids", []))
        enrichment = build_enrichment_document(
            incident=incident,
            events=events,
            edges=edges,
            enrichment_version=self.enrichment_version,
            enriched_at=datetime.now(UTC),
        )
        result = await self.incident_collection.update_one(
            {
                "_id": incident["_id"],
                "status": "candidate",
                "$or": [
                    {"enrichment_version": {"$exists": False}},
                    {"enrichment_version": {"$ne": self.enrichment_version}},
                ],
            },
            {"$set": enrichment},
            upsert=False,
        )
        return int(getattr(result, "modified_count", 0)) > 0

    async def _fetch_by_ids(self, collection: object, ids: list[Any]) -> list[dict[str, Any]]:
        normalized_ids = _stable_unique(ids)
        if not normalized_ids:
            return []
        cursor = collection.find({"_id": {"$in": normalized_ids}}).limit(len(normalized_ids))
        return await cursor.to_list(length=len(normalized_ids))

    async def load_checkpoint(self) -> ScanCheckpoint | None:
        document = await self.state_collection.find_one({"_id": self.worker_state_key})
        if not document or document.get("last_id") is None:
            return None
        return ScanCheckpoint(document_id=document["last_id"])

    async def save_checkpoint(self, incident: dict[str, Any]) -> None:
        await self.state_collection.update_one(
            {"_id": self.worker_state_key},
            {
                "$set": {
                    "last_id": incident["_id"],
                    "last_processed_timestamp": incident.get("updated_at")
                    or incident.get("started_at"),
                    "updated_at": datetime.now(UTC),
                },
                "$setOnInsert": {"worker": self.worker_state_key},
            },
            upsert=True,
        )

    async def heartbeat(self, metrics: EnrichmentBatchMetrics | None = None) -> None:
        updated_at = datetime.now(UTC)
        state = {
            "worker": self.worker_state_key,
            "updated_at": updated_at,
            "enrichment_version": self.enrichment_version,
        }
        if metrics is not None:
            state.update(
                {
                    "last_batch_count": metrics.incidents_scanned,
                    "last_incidents_enriched": metrics.incidents_enriched,
                    "last_incidents_failed": metrics.incidents_failed,
                }
            )
        await self.state_collection.update_one(
            {"_id": self.worker_state_key},
            {"$set": state, "$setOnInsert": {"created_at": updated_at}},
            upsert=True,
        )

    def _batch_query(self, checkpoint: ScanCheckpoint | None) -> dict[str, Any]:
        query: dict[str, Any] = {
            "status": "candidate",
            "$or": [
                {"enrichment_version": {"$exists": False}},
                {"enrichment_version": {"$ne": self.enrichment_version}},
            ],
        }
        if checkpoint is not None:
            query["_id"] = {"$gt": checkpoint.document_id}
        return query


def _stable_unique(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    unique: list[Any] = []
    for value in values:
        if value in (None, "") or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
