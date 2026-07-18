from __future__ import annotations

import hmac
from functools import lru_cache

from fastapi import Header, HTTPException, status
from oslo_config import cfg
from oslo_policy import policy

from backend.config import get_settings


async def require_internal_token(
    x_rca_service_token: str | None = Header(default=None, alias="X-RCA-Service-Token"),
) -> None:
    configured = get_settings().rca_internal_service_token
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "internal service token is not configured"},
        )
    if not x_rca_service_token or not hmac.compare_digest(x_rca_service_token, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid internal service token"},
        )


@lru_cache
def _policy_enforcer(policy_file: str) -> policy.Enforcer:
    policy_conf = cfg.ConfigOpts()
    policy_conf([])
    enforcer = policy.Enforcer(policy_conf, policy_file=policy_file, use_conf=True)
    enforcer.load_rules(force_reload=True)
    return enforcer


def require_provider_policy(rule: str):
    """Enforce provider RBAC for a user asserted by trusted Horizon.

    The service token authenticates the loopback Horizon client; roles are
    copied from Horizon's already Keystone-authenticated request context.
    """

    async def dependency(
        x_rca_service_token: str | None = Header(default=None, alias="X-RCA-Service-Token"),
        x_rca_roles: str | None = Header(default=None, alias="X-RCA-Roles"),
    ) -> None:
        await require_internal_token(x_rca_service_token)
        roles = [value.strip() for value in (x_rca_roles or "").split(",") if value.strip()]
        try:
            _policy_enforcer(get_settings().policy_file).enforce(
                rule,
                {},
                {"roles": roles},
                do_raise=True,
            )
        except policy.PolicyNotAuthorized as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "provider administration requires an authorized Keystone role"},
            ) from exc

    return dependency
