import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient

from backend.config import Settings, get_settings
from backend.repository import RCARepository, RawLogRepository

logger = logging.getLogger(__name__)

MONGO_CONNECT_MAX_RETRIES = 10
MONGO_CONNECT_DELAY_SECONDS = 2.0
MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000


class AppState:
    client: AsyncIOMotorClient | None = None
    repository: RawLogRepository | None = None
    rca_repository: RCARepository | None = None
    db_ready: bool = False


state = AppState()


def _build_client(settings: Settings) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
    )


async def _connect_with_retry(settings: Settings) -> AsyncIOMotorClient:
    client = _build_client(settings)
    database = client[settings.mongo_database]
    collection = database[settings.mongo_raw_logs_collection]
    repository = RawLogRepository(collection, settings.raw_logs_retention_days)
    rca_repository = _build_rca_repository(database, settings)

    for attempt in range(1, MONGO_CONNECT_MAX_RETRIES + 1):
        try:
            await client.admin.command("ping")
            await repository.ensure_indexes()
            await rca_repository.ensure_indexes()
            state.client = client
            state.repository = repository
            state.rca_repository = rca_repository
            state.db_ready = True
            return client
        except Exception:
            if attempt == MONGO_CONNECT_MAX_RETRIES:
                logger.error(
                    "MongoDB connection failed after %d attempts", attempt
                )
                client.close()
                raise
            logger.warning(
                "MongoDB connection attempt %d/%d failed, retrying in %.1fs",
                attempt,
                MONGO_CONNECT_MAX_RETRIES,
                MONGO_CONNECT_DELAY_SECONDS,
            )
            await asyncio.sleep(MONGO_CONNECT_DELAY_SECONDS)
    # Unreachable, but satisfies type checkers.
    client.close()
    raise RuntimeError("MongoDB connection retries exhausted")


@asynccontextmanager
async def lifespan(_: object) -> AsyncIterator[None]:
    settings = get_settings()
    await _connect_with_retry(settings)
    try:
        yield
    finally:
        if state.client:
            state.client.close()
        state.client = None
        state.repository = None
        state.rca_repository = None
        state.db_ready = False


async def get_repository() -> RawLogRepository:
    if state.repository is None:
        settings: Settings = get_settings()
        await _connect_with_retry(settings)
    return state.repository


async def get_rca_repository() -> RCARepository:
    if state.rca_repository is None:
        settings: Settings = get_settings()
        await _connect_with_retry(settings)
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
