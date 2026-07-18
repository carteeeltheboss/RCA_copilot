from __future__ import annotations

import json
import time
from typing import Any

import httpx

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
        models = [
            str(model.get("name"))
            for model in data.get("models", [])
            if isinstance(model, dict) and model.get("name")
        ]
        return ProviderResult(
            status="success", latency_ms=latency_ms, provider_identity="ollama", models=models
        )

    async def generate(
        self, config: dict[str, Any], evidence_package: dict[str, Any]
    ) -> ProviderResult:
        if "llm" not in self.capabilities:
            return ProviderResult(
                status="unavailable",
                error="Provider does not support llm",
                unsupported_capability="llm",
            )
        base_url = str(config.get("base_url") or "").rstrip("/")
        model_name = str(config.get("model_name") or "").strip()
        if not base_url:
            return ProviderResult(status="unavailable", error="provider base URL is not configured")
        if not model_name:
            return ProviderResult(
                status="unavailable", error="provider model name is not configured"
            )

        prompt = str(evidence_package.get("prompt") or "")
        if not prompt:
            prompt = json.dumps(evidence_package, default=str, separators=(",", ":"))
        payload = {
            "model": model_name,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": "You are RCA Copilot. Return only JSON when possible.",
                },
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.2},
        }

        timeout = float(config.get("timeout_seconds") or 30)
        retry_count = int(config.get("retry_count") or 0)
        start = time.monotonic()
        last_error = "provider request failed"
        for attempt in range(retry_count + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=False,
                    max_redirects=0,
                    verify=bool(config.get("verify_tls", True)),
                ) as client:
                    response = await client.post(f"{base_url}/api/chat", json=payload)
                    latency_ms = int((time.monotonic() - start) * 1000)
                    if response.status_code >= 400:
                        return ProviderResult(
                            status="failure",
                            latency_ms=latency_ms,
                            error=f"provider returned HTTP {response.status_code}",
                        )
                    body = response.json()
                    message = body.get("message") if isinstance(body, dict) else None
                    content = message.get("content") if isinstance(message, dict) else None
                    if not isinstance(content, str) or not content.strip():
                        return ProviderResult(
                            status="failure",
                            latency_ms=latency_ms,
                            error="provider returned an empty response",
                        )
                    return ProviderResult(
                        status="success",
                        latency_ms=latency_ms,
                        provider_identity="ollama",
                        data={
                            "answer_text": content.strip(),
                            "model_name": str(body.get("model") or model_name),
                            "done": bool(body.get("done", True)),
                        },
                    )
            except httpx.TimeoutException:
                last_error = "provider request timed out"
            except (httpx.HTTPError, ValueError) as exc:
                last_error = _sanitize_error(str(exc))
            if attempt >= retry_count:
                break
        return ProviderResult(
            status="failure", latency_ms=int((time.monotonic() - start) * 1000), error=last_error
        )


def _sanitize_error(message: str) -> str:
    return message.splitlines()[0][:240] if message else "provider request failed"
