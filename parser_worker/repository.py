from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, IndexModel, UpdateOne

from parser_worker.parser import parse_raw_log


class ParserRepository:
    def __init__(
        self,
        raw_collection: object,
        parsed_collection: object,
        parser_version: str,
        state_collection: object | None = None,
        worker_state_key: str = "parser_worker_v1",
    ) -> None:
        self.raw_collection = raw_collection
        self.parsed_collection = parsed_collection
        self.state_collection = state_collection
        self.worker_state_key = worker_state_key
        self.parser_version = parser_version

    async def ensure_indexes(self) -> None:
        await self.parsed_collection.create_indexes(
            [
                IndexModel(
                    [("source_log_id", ASCENDING), ("parser_version", ASCENDING)],
                    unique=True,
                    name="uniq_source_log_id_parser_version",
                )
            ]
        )

    async def fetch_unprocessed(self, batch_size: int) -> list[dict[str, Any]]:
        cursor = self.raw_collection.aggregate(
            [
                {
                    "$lookup": {
                        "from": self.parsed_collection.name,
                        "let": {"source_id": "$_id"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$source_log_id", "$$source_id"]},
                                            {"$eq": ["$parser_version", self.parser_version]},
                                        ]
                                    }
                                }
                            },
                            {"$limit": 1},
                        ],
                        "as": "parsed_match",
                    }
                },
                {"$match": {"parsed_match.0": {"$exists": False}}},
                {"$sort": {"_id": 1}},
                {"$limit": batch_size},
                {"$project": {"parsed_match": 0}},
            ]
        )
        return await cursor.to_list(length=batch_size)

    async def upsert_parsed(self, documents: list[dict[str, Any]]) -> int:
        if not documents:
            return 0

        operations = [
            UpdateOne(
                {
                    "source_log_id": document["source_log_id"],
                    "parser_version": document["parser_version"],
                },
                {"$setOnInsert": document},
                upsert=True,
            )
            for document in documents
        ]
        result = await self.parsed_collection.bulk_write(operations, ordered=False)
        return int(result.upserted_count)

    async def process_batch(self, batch_size: int) -> int:
        raw_documents = await self.fetch_unprocessed(batch_size)
        parsed_documents = [
            parse_raw_log(document, self.parser_version)
            for document in raw_documents
        ]
        return await self.upsert_parsed(parsed_documents)

    async def heartbeat(self, processed_count: int = 0) -> None:
        if self.state_collection is None:
            return
        await self.state_collection.update_one(
            {"_id": self.worker_state_key},
            {
                "$set": {
                    "worker": self.worker_state_key,
                    "updated_at": datetime.now(UTC),
                    "last_batch_count": processed_count,
                    "parser_version": self.parser_version,
                },
                "$setOnInsert": {"created_at": datetime.now(UTC)},
            },
            upsert=True,
        )
