"""Claude Code's relay: which login is admitted, and what an attempt is given of it.

Claude Code 2.1.239 keeps its subscription login in `.credentials.json` as one object,
`claudeAiOauth`, with an access token, a refresh token and their deadlines. The same file can also
carry other credentials a task must never be handed (a tool server's OAuth, plugin secrets, a
gateway's trust), so the relay admits ONE shape: the top of the file is exactly `claudeAiOauth`, its
keys are the eight the schema names with the types it names, and the plan is not the API-billing
one. Anything else is refused by name before a byte is copied (design F6).

The account of the login is not in that file but in the vendor's profile, `.claude.json`
(`oauthAccount`: `accountUuid`, `organizationUuid`...), which also holds tool servers, projects,
cached feature flags and a primary API key slot. The relay copies the account object from it into
a new profile and nothing else, and refuses a login whose account it cannot name. Of the account
object only the measured names and types are admitted. The saved dedicated profile's structural
roster was measured on 11.11.2026; this is not a new live compatibility measurement. Its observed
ccOnboardingFlags object is explicitly omitted, as nested values were before. The profile is read
ONCE, in
`bootstrap`; the account named for the evidence is read from the bytes that are written, and those
bytes are part of the digest `copy_in` holds the copy to.

The copy has no refresh token and no deadline for one: the owner's decision of 23.10.2026 is that
the attempt gets access and the real refresh stays with the real login. The form of that copy is
the one constant `CLAUDE_FORM`. Whether the pinned CLI works on it is the live measurement M2 and
is not something this module can show.

When the profile or the config says the vendor uses the Windows credential manager
(`cachedGrowthBookFeatures.tengu_windows_credman`), a refresh would move the login out of its file
and delete the file (design F7), so the login is refused. Either file saying so refuses: which
one the vendor reads first is not established, and a wrong guess would be the unsafe one.

A value module: it reads through `login_relay.read_leaf` and names no OS door of its own.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .claude_quota import API_BILLING_PLAN, plan_value
from .login_home import CREDENTIAL_LIMIT
from .login_relay import PROFILE_LIMIT, Refused, RelaySpec, from_epoch_ms, read_leaf
from .relay_env import CLAUDE_FORBIDDEN_ENV

CREDENTIAL = ".credentials.json"
PROFILE = ".claude.json"
CONFIG = ".config.json"
SECTION = "claudeAiOauth"
#: THE form of the access-only copy: the refresh token and its deadline are not in it. If the live
#: measurement finds the CLI needs the key present, this is the one value to change.
CLAUDE_FORM = (("refreshToken", None), ("refreshTokenExpiresAt", None))
_TEXT = frozenset({"accessToken", "refreshToken", "subscriptionType", "rateLimitTier", "clientId"})
_NUMBER = frozenset({"expiresAt", "refreshTokenExpiresAt"})
_KEYS = _TEXT | _NUMBER | {"scopes"}
_ACCOUNT_KEYS = ("accountUuid", "organizationUuid")
# Names/types only, from the saved 30.10 profile; no values or nested contents were recorded.
# Structural roster SHA256: 821849d871fb70d6aaeac3fc38220a23c9a2bb18b23d2da918a7d9b51f931231.
_ACCOUNT_SCHEMA = (
    ("accountCreatedAt", "str"), ("accountUuid", "str"), ("billingType", "str"),
    ("ccOnboardingFlags", "dict"), ("claudeCodeTrialDurationDays", "null"),
    ("claudeCodeTrialEndsAt", "null"), ("displayName", "str"), ("emailAddress", "str"),
    ("fullName", "str"), ("hasExtraUsageEnabled", "bool"), ("organizationName", "str"),
    ("organizationRateLimitTier", "str"), ("organizationRole", "str"),
    ("organizationType", "str"), ("organizationUuid", "str"), ("profileFetchedAt", "int"),
    ("seatTier", "null"), ("subscriptionCreatedAt", "str"), ("userRateLimitTier", "null"),
    ("workspaceRole", "null"))


def _typed(key: str, value: object) -> bool:
    """Whether a value is of the type the schema names for its key (`scopes` is the list).

    Judges the type of a key the schema names; that the key IS one of the eight is `admit`'s
    own check of the key set, and is not repeated here.
    """
    if key in _TEXT:
        return type(value) is str
    if key in _NUMBER:
        return type(value) is int
    return type(value) is list and all(type(row) is str for row in value)


def _account(home: object, schema, omitted) -> dict | None:
    """The closed measured account fields, without the explicitly omitted nested object."""
    leaf = read_leaf(Path(home) / PROFILE, limit=PROFILE_LIMIT)
    if isinstance(leaf, Refused):
        return None
    account = leaf.doc.get("oauthAccount")
    if type(account) is not dict:
        return None
    if any(type(account.get(key)) is not str or not account[key] for key in _ACCOUNT_KEYS):
        return None
    allowed = dict(schema)
    if any(key not in allowed or ("null" if value is None else type(value).__name__)
           != allowed[key] for key, value in account.items()):
        return None
    return {key: value for key, value in account.items() if key not in omitted}


@dataclass(frozen=True)
class ClaudeRelay(RelaySpec):
    """The relay of Claude Code; its facts are in `CLAUDE_RELAY`."""

    # Dataclass fields: policy_providers freezes them into the same grant digest as the profile.
    account_schema: tuple[tuple[str, str], ...] = _ACCOUNT_SCHEMA
    account_omitted: tuple[str, ...] = ("ccOnboardingFlags",)

    def admit(self, doc: dict) -> str | None:
        if set(doc) != {SECTION}:
            return "foreign_credentials"
        body = doc[SECTION]
        if (type(body) is not dict or not set(body) <= _KEYS
                or not all(_typed(key, value) for key, value in body.items())):
            return "unknown_shape"
        if not body.get("accessToken"):
            return "no_access_token"
        plan = body.get("subscriptionType")
        if plan is None or not plan.strip():
            return "plan_unknown"
        return "console_plan" if plan_value(plan) == API_BILLING_PLAN else None

    def bootstrap(self, real_home: Path) -> dict[str, bytes] | Refused:
        account = _account(real_home, self.account_schema, self.account_omitted)
        if account is None:
            return Refused("account_unknown")
        profile = json.dumps({"oauthAccount": account}, separators=(",", ":")).encode("utf-8")
        if len(profile) > CREDENTIAL_LIMIT:
            return Refused("account_unknown")
        return {PROFILE: profile}

    def account(self, doc: dict, material: dict[str, bytes]) -> str | None:
        try:
            value = json.loads(material[PROFILE])["oauthAccount"]["accountUuid"]
        except (KeyError, TypeError, ValueError):
            return None
        return value if type(value) is str and value else None

    def expires_at(self, doc):
        body = doc.get(SECTION)
        return from_epoch_ms(body.get("expiresAt")) if type(body) is dict else None

    def credman_refusal(self, real_home: Path) -> str | None:
        for name in (CONFIG, PROFILE):
            leaf = read_leaf(Path(real_home) / name, limit=PROFILE_LIMIT)
            if isinstance(leaf, Refused):
                if leaf.code == "leaf_absent":
                    continue
                return "credman_unknown"
            features = leaf.doc.get("cachedGrowthBookFeatures")
            if type(features) is dict and features.get("tengu_windows_credman") is True:
                return "credman"
        return None


CLAUDE_RELAY = ClaudeRelay(
    kind="c", credential=CREDENTIAL, files=(CREDENTIAL, PROFILE),
    secret_fields=("accessToken", "refreshToken"),
    refresh_fields=("refreshToken", "refreshTokenExpiresAt"),
    section=SECTION, form=CLAUDE_FORM, forbidden_env=CLAUDE_FORBIDDEN_ENV)
