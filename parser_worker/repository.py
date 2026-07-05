from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, IndexModel, UpdateOne

from parser_worker.parser import parse_raw_log


class ParserRepository:
    def __init__(
        self,
        raw_collection: object,
        parsed_collection: object,
        parser_version: str,
    ) -> None:
        self.raw_collection = raw_collection
        self.parsed_collection = parsed_collection
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
