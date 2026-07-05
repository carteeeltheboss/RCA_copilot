from datetime import UTC, datetime

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
