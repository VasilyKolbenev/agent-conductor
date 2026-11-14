"""Grok's access-only relay, prepared independently of production profile activation.

One fixed OIDC scope is admitted. The attempt receives auth.json without refresh_token;
the source login and executable config.toml are never changed or copied back. Whether the
pinned vendor accepts that form remains a live gate, not a claim made by this value module.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .login_relay import RelaySpec, clock_instant
from .relay_env import (
    GROK_FORBIDDEN_ENV, GROK_ROUTE_PREFIXES, GROK_SCOPE, grok_forbidden_name,
)

# The pinned vendor AuthStore roster, also reexported by grok_build for the leak scan.
GROK_AUTH_FIELDS = (
    "key", "auth_mode", "create_time", "user_id", "email", "first_name", "last_name",
    "profile_image_asset_id", "principal_type", "principal_id", "team_id", "team_name",
    "team_role", "organization_id", "organization_name", "organization_role",
    "user_blocked_reason", "team_blocked_reasons", "coding_data_retention_opt_out",
    "has_grok_code_access", "refresh_token", "expires_at", "oidc_issuer", "oidc_client_id")
GROK_AUTH_CREDENTIALS = ("key", "refresh_token")
_FIELDS = frozenset(GROK_AUTH_FIELDS)
_ISSUER, _CLIENT = GROK_SCOPE.split("::")


@dataclass(frozen=True)
class GrokRelay(RelaySpec):
    """Grok-specific routing prefixes are data bound into its own grant digest."""

    forbidden_prefixes: tuple[str, ...] = GROK_ROUTE_PREFIXES

    def admit(self, doc: dict) -> str | None:
        if set(doc) != {GROK_SCOPE}:
            return "unknown_shape"
        body = doc[GROK_SCOPE]
        if type(body) is not dict or not set(body) <= _FIELDS:
            return "unknown_shape"
        if body.get("auth_mode") == "api_key":
            return "api_key"
        if body.get("auth_mode") != "oidc":
            return "foreign_credentials"
        if type(body.get("key")) is not str or not body["key"]:
            return "no_access_token"
        refresh = body.get("refresh_token")
        if refresh is not None and type(refresh) is not str:
            return "unknown_shape"
        if any(type(body[name]) is not str for name in
               ("expires_at", "oidc_issuer", "oidc_client_id") if name in body):
            return "unknown_shape"
        if "oidc_issuer" in body and body["oidc_issuer"].rstrip("/") != _ISSUER:
            return "unknown_shape"
        if "oidc_client_id" in body and body["oidc_client_id"] != _CLIENT:
            return "unknown_shape"
        if type(body.get("user_id")) is not str or not body["user_id"]:
            return "account_unknown"
        return None

    def bootstrap(self, real_home: Path) -> dict[str, bytes]:
        """Nothing: config.toml contains executable marketplace configuration."""
        return {}

    def account(self, doc: dict, material: dict[str, bytes]) -> str | None:
        body = doc.get(GROK_SCOPE)
        value = body.get("user_id") if type(body) is dict else None
        return value if type(value) is str and value else None

    def expires_at(self, doc):
        body = doc.get(GROK_SCOPE)
        return clock_instant(body.get("expires_at")) if type(body) is dict else None

    def forbids(self, name: str) -> bool:
        return grok_forbidden_name(
            name, names=self.forbidden_env, prefixes=self.forbidden_prefixes)


GROK_RELAY = GrokRelay(
    kind="g", credential="auth.json", files=("auth.json",),
    secret_fields=GROK_AUTH_CREDENTIALS, refresh_fields=("refresh_token",),
    section=GROK_SCOPE, form=(("refresh_token", None),), forbidden_env=GROK_FORBIDDEN_ENV)
