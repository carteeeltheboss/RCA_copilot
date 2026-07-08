from __future__ import annotations

from backend.providers.base import BaseProviderAdapter, parse_json
from backend.providers.models import ProviderResult


class OpenAICompatibleAdapter(BaseProviderAdapter):
    provider_kind = "openai_compatible"
    supported_provider_types = {"llm", "embedding", "reranker"}
    capabilities = {"llm", "embedding", "reranker", "vision", "streaming", "model_listing"}

    def health_url(self, base_url: str) -> str:
        return f"{base_url}/models"

    def parse_response(self, body: bytes, latency_ms: int) -> ProviderResult:
        data = parse_json(body)
        models = []
        for item in data.get("data", []):
            if isinstance(item, dict) and item.get("id"):
                models.append(str(item["id"]))
        return ProviderResult(status="success", latency_ms=latency_ms, provider_identity="openai_compatible", models=models)
