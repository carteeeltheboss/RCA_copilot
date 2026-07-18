from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient

from backend.config import Settings, get_settings
from backend.repository import RCARepository, RawLogRepository


class AppState:
    client: AsyncIOMotorClient | None = None
    repository: RawLogRepository | None = None
    rca_repository: RCARepository | None = None


state = AppState()


@asynccontextmanager
async def lifespan(_: object) -> AsyncIterator[None]:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    database = client[settings.mongo_database]
    collection = database[settings.mongo_raw_logs_collection]
    repository = RawLogRepository(collection, settings.raw_logs_retention_days)
    rca_repository = _build_rca_repository(database, settings)

    await repository.ensure_indexes()
    await rca_repository.ensure_indexes()
    await client.admin.command("ping")

    state.client = client
    state.repository = repository
    state.rca_repository = rca_repository
    try:
        yield
    finally:
        client.close()
        state.client = None
        state.repository = None
        state.rca_repository = None


async def get_repository() -> RawLogRepository:
    if state.repository is None:
        settings: Settings = get_settings()
        client = AsyncIOMotorClient(settings.mongo_uri)
        collection = client[settings.mongo_database][settings.mongo_raw_logs_collection]
        state.client = client
        state.repository = RawLogRepository(collection, settings.raw_logs_retention_days)
    return state.repository


async def get_rca_repository() -> RCARepository:
    if state.rca_repository is None:
        settings: Settings = get_settings()
        client = state.client or AsyncIOMotorClient(settings.mongo_uri)
        database = client[settings.mongo_database]
        state.client = client
        state.rca_repository = _build_rca_repository(database, settings)
    return state.rca_repository


def _build_rca_repository(database: object, settings: Settings) -> RCARepository:
    return RCARepository(
        raw_logs=database[settings.mongo_raw_logs_collection],
        parsed_logs=database[settings.mongo_parsed_logs_collection],
        event_edges=database[settings.mongo_event_edges_collection],
        incidents=database[settings.mongo_incidents_collection],
        worker_state=database[settings.mongo_worker_state_collection],
        provider_configs=database[settings.mongo_provider_configs_collection],
        config_audit_log=database[settings.mongo_config_audit_log_collection],
        parsed_retention_days=settings.parsed_logs_retention_days,
        edge_retention_days=settings.event_edges_retention_days,
    )
