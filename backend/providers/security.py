from __future__ import annotations

import base64
import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from cryptography.fernet import Fernet, InvalidToken

from backend.config import Settings


BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
]


@dataclass(frozen=True)
class UrlValidationResult:
    ok: bool
    normalized_url: str | None = None
    error: str | None = None


def normalize_and_validate_provider_url(url: str, settings: Settings) -> UrlValidationResult:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return UrlValidationResult(False, error="provider URL must use http or https")
    if parsed.username or parsed.password:
        return UrlValidationResult(False, error="provider URL must not include embedded credentials")
    if not parsed.hostname:
        return UrlValidationResult(False, error="provider URL must include a host")

    host = parsed.hostname.lower()
    allowed_hosts = _csv(settings.rca_provider_allowed_hosts)
    if host in allowed_hosts:
        return UrlValidationResult(True, normalized_url=_normalize_url(parsed))

    allowed_cidrs = [ipaddress.ip_network(item, strict=False) for item in _csv(settings.rca_provider_allowed_cidrs)]
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(host, parsed.port or _default_port(parsed.scheme), type=socket.SOCK_STREAM)
        }
    except socket.gaierror:
        return UrlValidationResult(False, error="provider host could not be resolved")

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_loopback and settings.rca_provider_allow_localhost:
            continue
        if any(ip in cidr for cidr in allowed_cidrs):
            continue
        if ip.is_loopback or ip.is_link_local or any(ip in network for network in BLOCKED_NETWORKS):
            return UrlValidationResult(False, error="provider URL resolves to a blocked local or metadata address")
        if (ip.is_private or ip.is_reserved) and not any(ip in cidr for cidr in allowed_cidrs):
            return UrlValidationResult(False, error="provider URL resolves to a private address outside allowed CIDRs")

    return UrlValidationResult(True, normalized_url=_normalize_url(parsed))


def mask_secret(encrypted_value: str | None) -> str:
    return "configured" if encrypted_value else ""


class SecretBox:
    def __init__(self, master_key: str | None) -> None:
        self.fernet = _build_fernet(master_key) if master_key else None

    def encrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        if self.fernet is None:
            raise ValueError("RCA_PROVIDER_MASTER_KEY is required to save provider secrets")
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str | None) -> str | None:
        if not value or self.fernet is None:
            return None
        try:
            return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None


def _csv(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _normalize_url(parsed: Any) -> str:
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _build_fernet(master_key: str) -> Fernet:
    raw = master_key.encode("utf-8")
    if len(raw) == 44:
        return Fernet(raw)
    return Fernet(base64.urlsafe_b64encode(raw[:32].ljust(32, b"0")))
