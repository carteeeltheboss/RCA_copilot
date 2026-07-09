from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING, IndexModel, UpdateOne

from correlation_worker.correlator import (
    CorrelationRule,
    build_edges_for_group,
    parse_event_timestamp,
    resource_values,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorrelationBatchMetrics:
    events_scanned: int
    groups_processed: int
    periodic_groups_skipped: int
    oversized_groups_skipped: int
    edges_inserted: int
    candidate_edges: int
    inserted_edges: int
    skipped_edges: int


class CorrelationRepository:
    def __init__(
        self,
        parsed_collection: object,
        edge_collection: object,
        state_collection: object,
        worker_state_key: str,
        correlation_version: str,
        request_id_max_gap: timedelta,
        resource_id_max_gap: timedelta,
        max_events_per_group: int = 100,
        skip_periodic_groups: bool = True,
    ) -> None:
        self.parsed_collection = parsed_collection
        self.edge_collection = edge_collection
        self.state_collection = state_collection
        self.worker_state_key = worker_state_key
        self.correlation_version = correlation_version
        self.request_rule = CorrelationRule("same_request_id", 1.0, request_id_max_gap)
        self.resource_rule = CorrelationRule("shared_resource_id", 0.9, resource_id_max_gap)
        self.max_events_per_group = max_events_per_group
        self.skip_periodic_groups = skip_periodic_groups
        self._last_seen_id: Any | None = None

    async def ensure_indexes(self) -> None:
        await self.edge_collection.create_indexes(
            [
                IndexModel(
                    [
                        ("source_event_id", ASCENDING),
                        ("target_event_id", ASCENDING),
                        ("reason", ASCENDING),
                        ("shared_value", ASCENDING),
                        ("correlation_version", ASCENDING),
                    ],
                    unique=True,
                    name="uniq_event_edge_version",
                ),
                IndexModel([("source_timestamp", ASCENDING)], name="idx_source_timestamp"),
                IndexModel([("target_timestamp", ASCENDING)], name="idx_target_timestamp"),
            ]
        )
        await self.parsed_collection.create_indexes(
            [
                IndexModel(
                    [("parse_status", ASCENDING), ("_id", ASCENDING)],
                    name="idx_parse_status_id",
                ),
                IndexModel(
                    [("request_id", ASCENDING), ("timestamp", ASCENDING)],
                    name="idx_request_id_timestamp",
                ),
                IndexModel(
                    [("resource_ids", ASCENDING), ("timestamp", ASCENDING)],
                    name="idx_resource_ids_timestamp",
                ),
                IndexModel(
                    [("resource_id", ASCENDING), ("timestamp", ASCENDING)],
                    name="idx_resource_id_timestamp",
                ),
            ]
        )

    async def fetch_batch(self, batch_size: int) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"parse_status": "success"}
        if self._last_seen_id is not None:
            query["_id"] = {"$gt": self._last_seen_id}

        cursor = (
            self.parsed_collection.find(query)
            .sort("_id", ASCENDING)
            .limit(batch_size)
        )
        documents = await cursor.to_list(length=batch_size)
        if documents:
            self._last_seen_id = documents[-1]["_id"]
        return documents

    async def process_batch(self, batch_size: int) -> CorrelationBatchMetrics:
        events = await self.fetch_batch(batch_size)
        operations: list[UpdateOne] = []
        groups_processed = 0
        periodic_groups_skipped = 0
        oversized_groups_skipped = 0
        candidate_edges = 0
        skipped_edges = 0
        created_at = datetime.now(UTC)
        group_refs: dict[tuple[str, str], tuple[CorrelationRule, list[datetime], bool]] = {}

        for event in events:
            event_timestamp = parse_event_timestamp(event.get("timestamp"))
            if event_timestamp is None:
                skipped_edges += 1
                continue

            request_id = event.get("request_id")
            if request_id not in (None, ""):
                self._add_group_ref(
                    group_refs,
                    self.request_rule,
                    str(request_id),
                    event_timestamp,
                    isinstance(event.get("timestamp"), datetime),
                )

            for resource_id in resource_values(event):
                self._add_group_ref(
                    group_refs,
                    self.resource_rule,
                    resource_id,
                    event_timestamp,
                    isinstance(event.get("timestamp"), datetime),
                )

        for (_, shared_value), (rule, timestamps, use_datetime_query) in sorted(group_refs.items()):
            group_events = await self._find_group_events(
                rule,
                shared_value,
                min(timestamps),
                max(timestamps),
                use_datetime_query,
            )
            result = build_edges_for_group(
                group_events,
                rule,
                shared_value,
                self.correlation_version,
                max_events_per_group=self.max_events_per_group,
                skip_periodic_groups=self.skip_periodic_groups,
                periodic_minimum_span=self.request_rule.max_gap,
            )
            groups_processed += result.metrics.groups_processed
            periodic_groups_skipped += result.metrics.periodic_groups_skipped
            oversized_groups_skipped += result.metrics.oversized_groups_skipped
            candidate_edges += result.metrics.candidate_edges
            skipped_edges += result.metrics.skipped_edges
            for edge in result.edges:
                operations.append(self._upsert_operation(edge.to_document(created_at)))

        edges_inserted = 0
        if operations:
            result = await self.edge_collection.bulk_write(operations, ordered=False)
            edges_inserted = int(result.upserted_count)
            skipped_edges += len(operations) - edges_inserted

        metrics = CorrelationBatchMetrics(
            events_scanned=len(events),
            groups_processed=groups_processed,
            periodic_groups_skipped=periodic_groups_skipped,
            oversized_groups_skipped=oversized_groups_skipped,
            edges_inserted=edges_inserted,
            candidate_edges=candidate_edges,
            inserted_edges=edges_inserted,
            skipped_edges=skipped_edges,
        )
        if metrics.events_scanned or metrics.groups_processed or metrics.edges_inserted:
            LOGGER.info(
                "correlation batch events_scanned=%s groups_processed=%s "
                "periodic_groups_skipped=%s oversized_groups_skipped=%s "
                "edges_inserted=%s candidate_edges=%s skipped_edges=%s",
                metrics.events_scanned,
                metrics.groups_processed,
                metrics.periodic_groups_skipped,
                metrics.oversized_groups_skipped,
                metrics.edges_inserted,
                metrics.candidate_edges,
                metrics.skipped_edges,
        )
        return metrics

    async def heartbeat(self, metrics: CorrelationBatchMetrics | None = None) -> None:
        updated_at = datetime.now(UTC)
        state = {
            "worker": self.worker_state_key,
            "updated_at": updated_at,
            "correlation_version": self.correlation_version,
        }
        if metrics is not None:
            state.update(
                {
                    "last_batch_count": metrics.events_scanned,
                    "last_edges_inserted": metrics.edges_inserted,
                    "last_groups_processed": metrics.groups_processed,
                }
            )
        await self.state_collection.update_one(
            {"_id": self.worker_state_key},
            {"$set": state, "$setOnInsert": {"created_at": updated_at}},
            upsert=True,
        )

    def _add_group_ref(
        self,
        group_refs: dict[tuple[str, str], tuple[CorrelationRule, list[datetime], bool]],
        rule: CorrelationRule,
        shared_value: str,
        event_timestamp: datetime,
        use_datetime_query: bool,
    ) -> None:
        key = (rule.reason, shared_value)
        if key not in group_refs:
            group_refs[key] = (rule, [event_timestamp], use_datetime_query)
            return

        existing_rule, timestamps, existing_datetime_query = group_refs[key]
        timestamps.append(event_timestamp)
        group_refs[key] = (existing_rule, timestamps, existing_datetime_query and use_datetime_query)

    async def _find_group_events(
        self,
        rule: CorrelationRule,
        value: str,
        first_timestamp: datetime,
        last_timestamp: datetime,
        use_datetime_query: bool,
    ) -> list[dict[str, Any]]:
        timestamp_query = self._timestamp_range_query(
            first_timestamp - rule.max_gap,
            last_timestamp + rule.max_gap,
            use_datetime_query,
        )
        query: dict[str, Any] = {
            "parse_status": "success",
            "timestamp": timestamp_query,
        }
        if rule.reason == self.request_rule.reason:
            query["request_id"] = value
        else:
            query["$or"] = [{"resource_ids": value}, {"resource_id": value}]

        cursor = (
            self.parsed_collection.find(query)
            .sort("timestamp", ASCENDING)
            .limit(self.max_events_per_group + 1)
        )
        return await cursor.to_list(length=self.max_events_per_group + 1)

    def _timestamp_range_query(
        self,
        lower: datetime,
        upper: datetime,
        use_datetime_query: bool,
    ) -> dict[str, Any]:
        if use_datetime_query:
            return {"$gte": lower, "$lte": upper}
        return {"$gte": _format_utc_iso(lower), "$lte": _format_utc_iso(upper)}

    def _upsert_operation(self, document: dict[str, Any]) -> UpdateOne:
        return UpdateOne(
            {
                "source_event_id": document["source_event_id"],
                "target_event_id": document["target_event_id"],
                "reason": document["reason"],
                "shared_value": document["shared_value"],
                "correlation_version": document["correlation_version"],
            },
            {"$setOnInsert": document},
            upsert=True,
        )


def _format_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
