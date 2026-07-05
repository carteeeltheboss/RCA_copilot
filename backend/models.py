from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RawJournalRecord(BaseModel):
    boot_id: str = Field(min_length=1)
    journal_cursor: str = Field(min_length=1)
    message: str

    model_config = ConfigDict(extra="allow")


class BatchIngestRequest(BaseModel):
    records: list[RawJournalRecord] = Field(default_factory=list)


class BatchIngestResponse(BaseModel):
    received_count: int
    inserted_count: int
    duplicate_count: int


class InsertResult(BaseModel):
    inserted_count: int
    duplicate_count: int


def raw_record_to_document(record: RawJournalRecord, received_at: datetime) -> dict[str, Any]:
    document = record.model_dump(mode="python")
    document["received_at"] = received_at
    return document
