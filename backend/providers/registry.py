from __future__ import annotations

from backend.providers.adapters import (
    AnthropicAdapter,
    ChromaAdapter,
    CustomHTTPAdapter,
    GeminiAdapter,
    OllamaAdapter,
    OpenAICompatibleAdapter,
)
from backend.providers.base import BaseProviderAdapter


class ProviderRegistry:
    def __init__(self) -> None:
        adapters = [
            OllamaAdapter(),
            OpenAICompatibleAdapter(),
            GeminiAdapter(),
            AnthropicAdapter(),
            CustomHTTPAdapter(),
            ChromaAdapter(),
        ]
        self.adapters: dict[tuple[str, str], BaseProviderAdapter] = {}
        for adapter in adapters:
            for provider_type in adapter.supported_provider_types:
                self.adapters[(provider_type, adapter.provider_kind)] = adapter

    def get(self, provider_type: str, provider_kind: str) -> BaseProviderAdapter | None:
        return self.adapters.get((provider_type, provider_kind))

    def supported(self) -> list[dict[str, object]]:
        return [
            {
                "provider_type": provider_type,
                "provider_kind": provider_kind,
                "capabilities": sorted(adapter.capabilities),
            }
            for (provider_type, provider_kind), adapter in sorted(self.adapters.items())
        ]
