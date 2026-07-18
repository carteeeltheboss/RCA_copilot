from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from collections import defaultdict, deque
import time

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from backend.database import get_repository, lifespan
from backend.config import get_settings
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
    request_times: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def protect_batch_ingest(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/logs/batch":
            settings = get_settings()
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > settings.max_request_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": {"error": "log batch request is too large"}},
                )
            client = request.client.host if request.client else "unknown"
            service_token = request.headers.get("X-RCA-Service-Token")
            if (
                settings.rca_internal_service_token
                and service_token == settings.rca_internal_service_token
            ):
                # Keep an authenticated collector from consuming the same bucket as
                # Horizon and operator-driven ingestion on the loopback interface.
                client = f"collector:{client}"
            now = time.monotonic()
            recent = request_times[client]
            while recent and recent[0] <= now - 60:
                recent.popleft()
            if len(recent) >= settings.batch_rate_limit_per_minute:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": {"error": "log batch rate limit exceeded"}},
                )
            recent.append(now)
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/logs/batch", response_model=BatchIngestResponse)
    async def ingest_logs_batch(
        payload: BatchIngestRequest,
        repository: RawLogRepository = Depends(get_repository),
    ) -> BatchIngestResponse:
        if len(payload.records) > get_settings().max_batch_records:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={"error": "too many records in log batch"},
            )
        result = await repository.insert_raw_logs(payload.records)
        return BatchIngestResponse(
            received_count=len(payload.records),
            inserted_count=result.inserted_count,
            duplicate_count=result.duplicate_count,
        )

    app.include_router(api_v1_router)

    return app


app = create_app()
