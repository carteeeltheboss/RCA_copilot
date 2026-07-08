from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import Depends, FastAPI

from backend.database import get_repository, lifespan
from backend.models import BatchIngestRequest, BatchIngestResponse
from backend.repository import RawLogRepository
from backend.api_v1 import router as api_v1_router


def create_app(
    lifespan_context: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = lifespan,
) -> FastAPI:
    app = FastAPI(
        title="RCA Copilot Ingestion Backend",
        version="0.2.0",
        lifespan=lifespan_context,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/logs/batch", response_model=BatchIngestResponse)
    async def ingest_logs_batch(
        payload: BatchIngestRequest,
        repository: RawLogRepository = Depends(get_repository),
    ) -> BatchIngestResponse:
        result = await repository.insert_raw_logs(payload.records)
        return BatchIngestResponse(
            received_count=len(payload.records),
            inserted_count=result.inserted_count,
            duplicate_count=result.duplicate_count,
        )

    app.include_router(api_v1_router)

    return app


app = create_app()
