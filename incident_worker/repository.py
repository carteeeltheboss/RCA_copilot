from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING, IndexModel, UpdateOne

from correlation_worker.correlator import parse_event_timestamp
from incident_worker.detector import (
    build_incident_document,
    build_subgraph_from_edges,
    detect_incident_seed,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncidentBatchMetrics:
    events_scanned: int
    seeds_detected: int
    incidents_inserted: int
    incidents_skipped: int


@dataclass(frozen=True)
class ScanCheckpoint:
    parsed_at: Any
    document_id: Any


class IncidentRepository:
    def __init__(
        self,
        parsed_collection: object,
        edge_collection: object,
        incident_collection: object,
        state_collection: object,
        worker_state_key: str,
        correlation_version: str,
        incident_version: str,
        max_depth: int = 3,
        max_events: int = 100,
        window_before: timedelta = timedelta(minutes=10),
        window_after: timedelta = timedelta(minutes=2),
    ) -> None:
        self.parsed_collection = parsed_collection
        self.edge_collection = edge_collection
        self.incident_collection = incident_collection
        self.state_collection = state_collection
        self.worker_state_key = worker_state_key
        self.correlation_version = correlation_version
        self.incident_version = incident_version
        self.max_depth = max_depth
        self.max_events = max_events
        self.window_before = window_before
        self.window_after = window_after

    async def ensure_indexes(self) -> None:
        await self.incident_collection.create_indexes(
            [
                IndexModel(
                    [("seed_event_id", ASCENDING), ("incident_version", ASCENDING)],
                    unique=True,
                    name="uniq_seed_event_incident_version",
                ),
                IndexModel([("started_at", ASCENDING)], name="idx_started_at"),
                IndexModel([("status", ASCENDING)], name="idx_status"),
            ]
        )
        await self.parsed_collection.create_indexes(
            [
                IndexModel(
                    [("parse_status", ASCENDING), ("parsed_at", ASCENDING), ("_id", ASCENDING)],
                    name="idx_parse_status_parsed_at_id",
                ),
                IndexModel([("timestamp", ASCENDING)], name="idx_timestamp"),
            ]
        )
        await self.edge_collection.create_indexes(
            [
                IndexModel([("source_event_id", ASCENDING)], name="idx_source_event_id"),
                IndexModel([("target_event_id", ASCENDING)], name="idx_target_event_id"),
                IndexModel([("correlation_version", ASCENDING)], name="idx_correlation_version"),
            ]
        )

    async def fetch_batch(self, batch_size: int) -> list[dict[str, Any]]:
        checkpoint = await self.load_checkpoint()
        query = self._batch_query(checkpoint)
        cursor = (
            self.parsed_collection.find(query)
            .sort([("parsed_at", ASCENDING), ("_id", ASCENDING)])
            .limit(batch_size)
        )
        return await cursor.to_list(length=batch_size)

    async def process_batch(self, batch_size: int) -> IncidentBatchMetrics:
        events = await self.fetch_batch(batch_size)
        seeds = [
            (event, detection)
            for event in events
            if (detection := detect_incident_seed(event)) is not None
        ]

        operations: list[UpdateOne] = []
        updated_at = datetime.now(UTC)
        for seed_event, detection in seeds:
            subgraph = await self.build_subgraph(seed_event)
            document = build_incident_document(
                seed_event,
                detection,
                subgraph,
                self.correlation_version,
                self.incident_version,
                updated_at,
            )
            operations.append(self._upsert_operation(document))

        inserted = 0
        if operations:
            result = await self.incident_collection.bulk_write(operations, ordered=False)
            inserted = int(result.upserted_count)

        if events:
            await self.save_checkpoint(events[-1])

        metrics = IncidentBatchMetrics(
            events_scanned=len(events),
            seeds_detected=len(seeds),
            incidents_inserted=inserted,
            incidents_skipped=len(seeds) - inserted,
        )
        if metrics.events_scanned or metrics.seeds_detected or metrics.incidents_inserted:
            LOGGER.info(
                "incident batch events_scanned=%s seeds_detected=%s "
                "incidents_inserted=%s incidents_skipped=%s",
                metrics.events_scanned,
                metrics.seeds_detected,
                metrics.incidents_inserted,
                metrics.incidents_skipped,
            )
        return metrics

    async def process_available_batches(self, batch_size: int) -> list[IncidentBatchMetrics]:
        metrics: list[IncidentBatchMetrics] = []
        while True:
            batch_metrics = await self.process_batch(batch_size)
            metrics.append(batch_metrics)
            if batch_metrics.events_scanned < batch_size:
                return metrics

    async def load_checkpoint(self) -> ScanCheckpoint | None:
        document = await self.state_collection.find_one({"_id": self.worker_state_key})
        if not document:
            return None
        parsed_at = document.get("last_parsed_at")
        document_id = document.get("last_id")
        if parsed_at is None or document_id is None:
            return None
        return ScanCheckpoint(parsed_at=parsed_at, document_id=document_id)

    async def save_checkpoint(self, event: dict[str, Any]) -> None:
        await self.state_collection.update_one(
            {"_id": self.worker_state_key},
            {
                "$set": {
                    "last_parsed_at": event["parsed_at"],
                    "last_id": event["_id"],
                    "updated_at": datetime.now(UTC),
                },
                "$setOnInsert": {"worker": self.worker_state_key},
            },
            upsert=True,
        )

    async def heartbeat(self, metrics: IncidentBatchMetrics | None = None) -> None:
        updated_at = datetime.now(UTC)
        state = {
            "worker": self.worker_state_key,
            "updated_at": updated_at,
            "incident_version": self.incident_version,
            "correlation_version": self.correlation_version,
        }
        if metrics is not None:
            state.update(
                {
                    "last_batch_count": metrics.events_scanned,
                    "last_seeds_detected": metrics.seeds_detected,
                    "last_incidents_inserted": metrics.incidents_inserted,
                }
            )
        await self.state_collection.update_one(
            {"_id": self.worker_state_key},
            {"$set": state, "$setOnInsert": {"created_at": updated_at}},
            upsert=True,
        )

    def _batch_query(self, checkpoint: ScanCheckpoint | None) -> dict[str, Any]:
        query: dict[str, Any] = {
            "parse_status": "success",
            "parsed_at": {"$exists": True},
        }
        if checkpoint is None:
            return query

        query["$or"] = [
            {"parsed_at": {"$gt": checkpoint.parsed_at}},
            {
                "parsed_at": checkpoint.parsed_at,
                "_id": {"$gt": checkpoint.document_id},
            },
        ]
        return query

    async def build_subgraph(self, seed_event: dict[str, Any]) -> object:
        seed_timestamp = parse_event_timestamp(seed_event.get("timestamp"))
        if seed_timestamp is None:
            return build_subgraph_from_edges(
                seed_event,
                events_by_id={seed_event.get("_id"): seed_event},
                edges=[],
                max_depth=self.max_depth,
                max_events=self.max_events,
                window_before=self.window_before,
                window_after=self.window_after,
            )

        lower = seed_timestamp - self.window_before
        upper = seed_timestamp + self.window_after
        edges = await self._fetch_window_edges(lower, upper)
        event_ids = {seed_event.get("_id")}
        for edge in edges:
            event_ids.add(edge.get("source_event_id"))
            event_ids.add(edge.get("target_event_id"))
        event_ids.discard(None)
        events_by_id = await self._fetch_events_by_id(event_ids, lower, upper)
        events_by_id[seed_event.get("_id")] = seed_event

        return build_subgraph_from_edges(
            seed_event,
            events_by_id=events_by_id,
            edges=edges,
            max_depth=self.max_depth,
            max_events=self.max_events,
            window_before=self.window_before,
            window_after=self.window_after,
        )

    async def _fetch_window_edges(
        self,
        lower: datetime,
        upper: datetime,
    ) -> list[dict[str, Any]]:
        query = {
            "correlation_version": self.correlation_version,
            "$or": [
                {"source_timestamp": {"$gte": lower, "$lte": upper}},
                {"target_timestamp": {"$gte": lower, "$lte": upper}},
                {
                    "source_timestamp": {
                        "$gte": _format_utc_iso(lower),
                        "$lte": _format_utc_iso(upper),
                    }
                },
                {
                    "target_timestamp": {
                        "$gte": _format_utc_iso(lower),
                        "$lte": _format_utc_iso(upper),
                    }
                },
            ],
        }
        cursor = self.edge_collection.find(query).limit(max(self.max_events * 4, 100))
        return await cursor.to_list(length=max(self.max_events * 4, 100))

    async def _fetch_events_by_id(
        self,
        event_ids: set[Any],
        lower: datetime,
        upper: datetime,
    ) -> dict[Any, dict[str, Any]]:
        if not event_ids:
            return {}
        query = {
            "_id": {"$in": list(event_ids)},
            "parse_status": "success",
            "$or": [
                {"timestamp": {"$gte": lower, "$lte": upper}},
                {"timestamp": {"$gte": _format_utc_iso(lower), "$lte": _format_utc_iso(upper)}},
            ],
        }
        cursor = self.parsed_collection.find(query).limit(max(self.max_events * 2, 100))
        events = await cursor.to_list(length=max(self.max_events * 2, 100))
        return {event["_id"]: event for event in events}

    def _upsert_operation(self, document: dict[str, Any]) -> UpdateOne:
        return UpdateOne(
            {
                "seed_event_id": document["seed_event_id"],
                "incident_version": document["incident_version"],
            },
            {"$setOnInsert": document},
            upsert=True,
        )


def _format_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
