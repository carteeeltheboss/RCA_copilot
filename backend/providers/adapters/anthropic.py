from __future__ import annotations

from backend.providers.base import BaseProviderAdapter


class AnthropicAdapter(BaseProviderAdapter):
    provider_kind = "anthropic"
    supported_provider_types = {"llm"}
    capabilities = {"llm", "vision", "streaming"}

    def headers(self, api_key: str | None) -> dict[str, str]:
        headers = {"anthropic-version": "2023-06-01"}
        if api_key:
            headers["x-api-key"] = api_key
        return headers
