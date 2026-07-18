from __future__ import annotations

from typing import Any

from backend.config import Settings
from backend.providers.base import BaseProviderAdapter
from backend.providers.models import ValidationResult


class CustomHTTPAdapter(BaseProviderAdapter):
    provider_kind = "custom_http"
    supported_provider_types = {"llm", "embedding", "reranker"}
    capabilities = {"llm", "embedding", "reranker", "model_listing"}

    def validate_config(self, config: dict[str, Any], settings: Settings) -> ValidationResult:
        result = super().validate_config(config, settings)
        if not result.ok:
            return result
        normalized = dict(result.normalized_config)
        capabilities = set(normalized.get("capabilities") or [])
        if not capabilities:
            normalized["capabilities"] = sorted(
                self.default_capabilities(normalized["provider_type"])
            )
        return ValidationResult(True, normalized_config=normalized)

    def health_url(self, base_url: str) -> str:
        return base_url


class ChromaAdapter(BaseProviderAdapter):
    provider_kind = "chroma"
    supported_provider_types = {"vector_store"}
    capabilities: set[str] = set()

    def health_url(self, base_url: str) -> str:
        return f"{base_url}/api/v1/heartbeat"
