from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class RCAClientError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class RCAClient:
    base_url: str = os.environ.get("RCA_BACKEND_URL", "http://127.0.0.1:8000")
    token: str | None = os.environ.get("RCA_INTERNAL_SERVICE_TOKEN")
    timeout: float = float(os.environ.get("RCA_BACKEND_TIMEOUT_SECONDS", "5"))

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("POST", path, payload=payload or {})

    def put(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("PUT", path, payload=payload)

    def delete(self, path: str) -> dict[str, Any]:
        return self.request("DELETE", path)

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urllib.parse.urlencode(_compact(params or {}), doseq=True)}" if params else ""
        url = f"{self.base_url.rstrip('/')}{path}{query}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["X-RCA-Service-Token"] = self.token
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content = response.read(2 * 1024 * 1024)
                return json.loads(content.decode("utf-8")) if content else {}
        except urllib.error.HTTPError as exc:
            detail = _safe_detail(exc)
            raise RCAClientError(detail, exc.code) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RCAClientError("RCA backend unavailable") from exc


def _safe_detail(exc: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(exc.read(65536).decode("utf-8"))
        detail = data.get("detail", data)
        if isinstance(detail, dict):
            return str(detail.get("error") or detail.get("reason") or "RCA backend request failed")
        return str(detail)
    except Exception:
        return "RCA backend request failed"


def _compact(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in (None, "", [])}
