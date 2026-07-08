from __future__ import annotations

import json
import time
from typing import Any

import httpx

from backend.config import Settings
from backend.providers.models import CAPABILITIES, PROVIDER_TYPES, ProviderResult, ValidationResult, unsupported
from backend.providers.security import normalize_and_validate_provider_url


MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024


class BaseProviderAdapter:
    provider_kind = "custom_http"
    supported_provider_types: set[str] = set()
    capabilities: set[str] = set()

    def validate_config(self, config: dict[str, Any], settings: Settings) -> ValidationResult:
        provider_type = config.get("provider_type")
        if provider_type not in PROVIDER_TYPES:
            return ValidationResult(False, error="unsupported provider type")
        if provider_type not in self.supported_provider_types:
            return ValidationResult(False, error=f"{self.provider_kind} does not support {provider_type}")
        if config.get("provider_kind") != self.provider_kind:
            return ValidationResult(False, error="unsupported provider kind")
        if not config.get("display_name"):
            return ValidationResult(False, error="display name is required")
        timeout = int(config.get("timeout_seconds") or settings.rca_provider_request_timeout_seconds)
        if timeout < 1 or timeout > 120:
            return ValidationResult(False, error="timeout must be between 1 and 120 seconds")
        retry_count = int(config.get("retry_count") or 0)
        if retry_count < 0 or retry_count > 5:
            return ValidationResult(False, error="retry count must be between 0 and 5")

        normalized = dict(config)
        normalized["timeout_seconds"] = timeout
        normalized["retry_count"] = retry_count
        requested_capabilities = set(normalized.get("capabilities") or self.default_capabilities(provider_type))
        invalid_capabilities = requested_capabilities - CAPABILITIES
        if invalid_capabilities:
            return ValidationResult(False, error=f"unsupported capabilities: {', '.join(sorted(invalid_capabilities))}")
        normalized["capabilities"] = sorted(requested_capabilities & self.capabilities)

        base_url = normalized.get("base_url")
        if base_url:
            result = normalize_and_validate_provider_url(base_url, settings)
            if not result.ok:
                return ValidationResult(False, error=result.error)
            normalized["base_url"] = result.normalized_url
        return ValidationResult(True, normalized_config=normalized)

    async def test_connection(
        self,
        config: dict[str, Any],
        settings: Settings,
        api_key: str | None = None,
    ) -> ProviderResult:
        validation = self.validate_config(config, settings)
        if not validation.ok:
            return ProviderResult(status="failure", latency_ms=0, error=validation.error)
        normalized = validation.normalized_config
        if normalized.get("extra_config", {}).get("offline_placeholder"):
            return ProviderResult(status="success", latency_ms=0, provider_identity=f"{self.provider_kind}:offline-placeholder")
        if not normalized.get("base_url"):
            return ProviderResult(status="failure", latency_ms=0, error="provider base URL is not configured")

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=float(normalized.get("timeout_seconds") or settings.rca_provider_request_timeout_seconds),
                follow_redirects=False,
                max_redirects=0,
                verify=bool(normalized.get("verify_tls", True)),
            ) as client:
                async with client.stream("GET", self.health_url(normalized["base_url"]), headers=self.headers(api_key)) as response:
                    body = await _limited_body(response)
                    latency_ms = int((time.monotonic() - start) * 1000)
                    if response.status_code >= 400:
                        return ProviderResult(
                            status="failure",
                            latency_ms=latency_ms,
                            error=f"provider returned HTTP {response.status_code}",
                        )
                    return self.parse_response(body, latency_ms)
        except httpx.TimeoutException:
            return ProviderResult(
                status="failure",
                latency_ms=int((time.monotonic() - start) * 1000),
                error="provider request timed out",
            )
        except httpx.HTTPError as exc:
            return ProviderResult(
                status="failure",
                latency_ms=int((time.monotonic() - start) * 1000),
                error=_sanitize_error(str(exc)),
            )

    async def list_models(self, config: dict[str, Any], settings: Settings, api_key: str | None = None) -> ProviderResult:
        if "model_listing" not in self.capabilities:
            return unsupported("model_listing")
        return await self.test_connection(config, settings, api_key=api_key)

    async def generate(self, config: dict[str, Any], evidence_package: dict[str, Any]) -> ProviderResult:
        if "llm" not in self.capabilities:
            return unsupported("llm")
        return ProviderResult(status="unavailable", error="generation is not implemented for this provider yet")

    async def embed(self, config: dict[str, Any], texts: list[str]) -> ProviderResult:
        if "embedding" not in self.capabilities:
            return unsupported("embedding")
        return ProviderResult(status="unavailable", error="embedding is not implemented for this provider yet")

    async def rerank(self, config: dict[str, Any], query: str, documents: list[dict[str, Any]]) -> ProviderResult:
        if "reranker" not in self.capabilities:
            return unsupported("reranker")
        return ProviderResult(status="unavailable", error="reranking is not implemented for this provider yet")

    def default_capabilities(self, provider_type: str) -> set[str]:
        return {provider_type} if provider_type in {"llm", "embedding", "reranker"} else set()

    def health_url(self, base_url: str) -> str:
        return base_url

    def headers(self, api_key: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def parse_response(self, body: bytes, latency_ms: int) -> ProviderResult:
        return ProviderResult(status="success", latency_ms=latency_ms, provider_identity=self.provider_kind)


async def _limited_body(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_PROVIDER_RESPONSE_BYTES:
            raise httpx.HTTPError("provider response exceeded size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def parse_json(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _sanitize_error(message: str) -> str:
    return message.splitlines()[0][:240] if message else "provider request failed"
