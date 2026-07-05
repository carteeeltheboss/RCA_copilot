from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient

from backend.config import Settings, get_settings
from backend.repository import RawLogRepository


class AppState:
    client: AsyncIOMotorClient | None = None
    repository: RawLogRepository | None = None


state = AppState()


@asynccontextmanager
async def lifespan(_: object) -> AsyncIterator[None]:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    database = client[settings.mongo_database]
    collection = database[settings.mongo_raw_logs_collection]
    repository = RawLogRepository(collection)

    await repository.ensure_indexes()
    await client.admin.command("ping")

    state.client = client
    state.repository = repository
    try:
        yield
    finally:
        client.close()
        state.client = None
        state.repository = None


async def get_repository() -> RawLogRepository:
    if state.repository is None:
        settings: Settings = get_settings()
        client = AsyncIOMotorClient(settings.mongo_uri)
        collection = client[settings.mongo_database][settings.mongo_raw_logs_collection]
        state.client = client
        state.repository = RawLogRepository(collection)
    return state.repository
