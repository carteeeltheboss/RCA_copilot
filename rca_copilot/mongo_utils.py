from __future__ import annotations

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_CONNECT_MAX_RETRIES = 10
MONGO_CONNECT_DELAY_SECONDS = 2.0
MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000


def create_mongo_client(uri: str) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        uri,
        serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
    )


async def connect_with_retry(uri: str) -> AsyncIOMotorClient:
    client = create_mongo_client(uri)
    for attempt in range(1, MONGO_CONNECT_MAX_RETRIES + 1):
        try:
            await client.admin.command("ping")
            return client
        except Exception:
            if attempt == MONGO_CONNECT_MAX_RETRIES:
                logger.error("MongoDB connection failed after %d attempts", attempt)
                client.close()
                raise
            logger.warning(
                "MongoDB connection attempt %d/%d failed, retrying in %.1fs",
                attempt,
                MONGO_CONNECT_MAX_RETRIES,
                MONGO_CONNECT_DELAY_SECONDS,
            )
            await asyncio.sleep(MONGO_CONNECT_DELAY_SECONDS)
    client.close()
    raise RuntimeError("MongoDB connection retries exhausted")
