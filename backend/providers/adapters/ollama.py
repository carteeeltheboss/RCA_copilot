from __future__ import annotations

from backend.providers.base import BaseProviderAdapter, parse_json
from backend.providers.models import ProviderResult


class OllamaAdapter(BaseProviderAdapter):
    provider_kind = "ollama"
    supported_provider_types = {"llm", "embedding"}
    capabilities = {"llm", "embedding", "model_listing", "streaming"}

    def health_url(self, base_url: str) -> str:
        return f"{base_url}/api/tags"

    def parse_response(self, body: bytes, latency_ms: int) -> ProviderResult:
        data = parse_json(body)
        models = [str(model.get("name")) for model in data.get("models", []) if isinstance(model, dict) and model.get("name")]
        return ProviderResult(status="success", latency_ms=latency_ms, provider_identity="ollama", models=models)
