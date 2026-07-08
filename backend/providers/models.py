from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ProviderType = Literal["llm", "embedding", "reranker", "vector_store"]
ProviderKind = Literal["ollama", "openai_compatible", "gemini", "anthropic", "custom_http", "chroma"]
Capability = Literal["llm", "embedding", "reranker", "vision", "streaming", "model_listing"]


PROVIDER_TYPES = {"llm", "embedding", "reranker", "vector_store"}
PROVIDER_KINDS = {"ollama", "openai_compatible", "gemini", "anthropic", "custom_http", "chroma"}
CAPABILITIES = {"llm", "embedding", "reranker", "vision", "streaming", "model_listing"}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    normalized_config: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class ProviderResult:
    status: Literal["success", "failure", "unavailable"]
    latency_ms: int | None = None
    provider_identity: str | None = None
    models: list[str] = field(default_factory=list)
    data: Any = None
    error: str | None = None
    unsupported_capability: str | None = None

    @property
    def success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "provider_identity": self.provider_identity,
            "models": self.models,
            "data": self.data,
            "error": self.error,
            "unsupported_capability": self.unsupported_capability,
        }


def unsupported(capability: str) -> ProviderResult:
    return ProviderResult(
        status="unavailable",
        error=f"Provider does not support {capability}",
        unsupported_capability=capability,
    )
