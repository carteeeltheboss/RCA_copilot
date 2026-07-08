from __future__ import annotations

from backend.providers.base import BaseProviderAdapter, parse_json
from backend.providers.models import ProviderResult


class GeminiAdapter(BaseProviderAdapter):
    provider_kind = "gemini"
    supported_provider_types = {"llm", "embedding"}
    capabilities = {"llm", "embedding", "vision", "streaming", "model_listing"}

    def health_url(self, base_url: str) -> str:
        return f"{base_url}/v1beta/models"

    def headers(self, api_key: str | None) -> dict[str, str]:
        return {"x-goog-api-key": api_key} if api_key else {}

    def parse_response(self, body: bytes, latency_ms: int) -> ProviderResult:
        data = parse_json(body)
        models = [str(item.get("name")) for item in data.get("models", []) if isinstance(item, dict) and item.get("name")]
        return ProviderResult(status="success", latency_ms=latency_ms, provider_identity="gemini", models=models)
