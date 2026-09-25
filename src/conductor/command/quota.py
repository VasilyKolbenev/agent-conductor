"""Account quota facts, independent of execution authority and provider bindings.

Only trusted collectors may construct AccountIdentity, after establishing the
native account identity. An operator alias or a harness name is not that proof.
Provider-owned parsers accept decoded native replies, never credentials or logs.
No collector, network request, process, clock or persistence is implemented here.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from .adapters.quota_contracts import (
    NativeBalanceAmount, NativeQuotaReading, NativeQuotaWindow, QuotaError,
    QuotaPolicy, quota_policy,
)
_REASONS = {"no_data", "source_error", "not_authenticated", "not_supported",
            "malformed_payload"}


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value) > 256:
        raise QuotaError(f"invalid {field}")
    if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise QuotaError(f"invalid {field}")
    return value


def instant(value: object) -> datetime:
    """Require an aware datetime and retain only its UTC instant."""
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise QuotaError("quota timestamp must be an aware datetime")
    try:
        result = value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise QuotaError("invalid quota timestamp") from exc
    if result.year < 1970:
        raise QuotaError("quota timestamp predates the Unix epoch")
    return result


def _percentage(value: object) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        raise QuotaError("invalid quota percentage")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise QuotaError("invalid quota percentage") from exc
    if not math.isfinite(result) or not 0 <= result <= 100:
        raise QuotaError("invalid quota percentage")
    return result


def _optional_minutes(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise QuotaError("invalid quota window duration")
    return value


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise QuotaError("quota payload must contain plain objects")
    return value


def _unix(value: object) -> datetime | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise QuotaError("invalid quota reset timestamp")
    try:
        return instant(datetime.fromtimestamp(value, timezone.utc))
    except (ValueError, OverflowError, OSError) as exc:
        raise QuotaError("invalid quota reset timestamp") from exc


def _rfc3339(value: object) -> datetime | None:
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise QuotaError("invalid quota reset timestamp")
    try:
        return instant(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (ValueError, OverflowError) as exc:
        raise QuotaError("invalid quota reset timestamp") from exc


@dataclass(frozen=True)
class AccountIdentity:
    """A digest of a verified native account id, never a user-entered alias.

    The trust boundary is the collector, not a browser-supplied claim that an id
    was verified. None of this module's constructors is an HTTP input door.
    """
    policy: QuotaPolicy
    account_digest: str
    verified_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy", quota_policy(self.policy))
        if type(self.verified_by) is not str or self.verified_by != self.policy.identity_source:
            raise QuotaError("unconfirmed quota account identity")
        if type(self.account_digest) is not str or not re.fullmatch("[0-9a-f]{64}", self.account_digest):
            raise QuotaError("invalid quota account digest")

    @classmethod
    def from_verified_native_id(cls, policy: QuotaPolicy, native_id: str, *, verified_by: str) -> AccountIdentity:
        native_id = _text(native_id, "native account id")
        policy = quota_policy(policy)
        digest = hashlib.sha256((policy.vendor + "\0" + native_id).encode("utf-8")).hexdigest()
        return cls(policy, digest, verified_by)

    @property
    def vendor(self) -> str:
        return self.policy.vendor


@dataclass(frozen=True)
class CredentialContext:
    """Opaque collector connection handle; the billing account is unknown.

    The trusted collector must bind this handle to the credential/origin
    snapshot used by dispatch. Neither its UUID nor this constructor proves
    that relationship. Never derive the handle from credentials or an alias.
    """
    policy: QuotaPolicy
    context_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy", quota_policy(self.policy))
        if self.policy.observation_kind != "balance":
            raise QuotaError("credential context requires a monetary source")
        if type(self.context_id) is not str or re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                self.context_id) is None:
            raise QuotaError("invalid credential context handle")

    @classmethod
    def create(cls, policy: QuotaPolicy) -> CredentialContext:
        return cls(policy, str(uuid4()))

    def as_dict(self) -> dict[str, str]:
        return {"kind": "credential_context", "context_id": self.context_id,
                "vendor": self.policy.vendor, "account_status": "unknown"}


@dataclass(frozen=True)
class SessionContext:
    """Opaque native subscription reader lifetime; the account is unknown.

    The trusted collector must bind this handle to the credential/origin
    snapshot used by dispatch. Neither its UUID nor this constructor proves
    that relationship. Never derive the handle from credentials or an alias.
    """
    policy: QuotaPolicy
    context_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy", quota_policy(self.policy))
        if self.policy.observation_kind != "quota":
            raise QuotaError("session context requires a subscription source")
        if type(self.context_id) is not str or re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                self.context_id) is None:
            raise QuotaError("invalid session context handle")

    @classmethod
    def create(cls, policy: QuotaPolicy) -> SessionContext:
        return cls(policy, str(uuid4()))

    def as_dict(self) -> dict[str, str]:
        return {"kind": "session_context", "context_id": self.context_id,
                "vendor": self.policy.vendor, "account_status": "unknown"}


@dataclass(frozen=True)
class QuotaSource:
    policy: QuotaPolicy
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy", quota_policy(self.policy))
        _text(self.version, "source version")

    @property
    def kind(self) -> str:
        return self.policy.source_kind

    @property
    def observation_kind(self) -> str:
        return self.policy.observation_kind


@dataclass(frozen=True)
class QuotaWindow:
    limit_id: str
    window_id: str
    used_percent: float | None
    resets_at: datetime | None
    duration_minutes: int | None = None
    starts_at: datetime | None = None

    def __post_init__(self) -> None:
        _text(self.limit_id, "limit id")
        _text(self.window_id, "window id")
        object.__setattr__(self, "used_percent", _percentage(self.used_percent))
        _optional_minutes(self.duration_minutes)
        for key in ("starts_at", "resets_at"):
            value = getattr(self, key)
            if value is not None:
                object.__setattr__(self, key, instant(value))
        if self.starts_at is not None and self.resets_at is not None and self.starts_at >= self.resets_at:
            raise QuotaError("quota window ends before it starts")
        if self.used_percent is None and self.resets_at is None:
            raise QuotaError("quota window contains no usage or reset observation")

    @property
    def remaining_percent(self) -> float | None:
        return None if self.used_percent is None else 100.0 - self.used_percent

    def as_dict(self) -> dict[str, Any]:
        return {"limit_id": self.limit_id, "window_id": self.window_id,
                "used_percent": self.used_percent, "remaining_percent": self.remaining_percent,
                "resets_at": _iso(self.resets_at), "starts_at": _iso(self.starts_at),
                "duration_minutes": self.duration_minutes}


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def _account(value: object) -> AccountIdentity:
    if type(value) is not AccountIdentity:
        raise QuotaError("quota account identity is required")
    return AccountIdentity(value.policy, value.account_digest, value.verified_by)


def _source(value: object) -> QuotaSource:
    if type(value) is not QuotaSource:
        raise QuotaError("quota source is required")
    return QuotaSource(value.policy, value.version)


def validate_account_source(account: AccountIdentity, source: QuotaSource) -> None:
    account, source = _account(account), _source(source)
    if account.vendor != source.policy.vendor or account.verified_by != source.policy.identity_source:
        raise QuotaError("quota source and account vendor differ")


def _subject(account: AccountIdentity | None, connection: CredentialContext | SessionContext | None,
             source: QuotaSource) -> tuple[AccountIdentity | None, CredentialContext | SessionContext | None]:
    """Reconstruct exactly one trusted subject; each context has its own source kind."""
    source = _source(source)
    if connection is None:
        account = _account(account)
        validate_account_source(account, source)
        return account, None
    if account is not None or type(connection) not in (CredentialContext, SessionContext):
        raise QuotaError("exactly one quota subject is required")
    connection = type(connection)(connection.policy, connection.context_id)
    if connection.policy != source.policy:
        raise QuotaError("credential context and source policy differ")
    return None, connection


def _subject_dict(account: AccountIdentity | None,
                  connection: CredentialContext | SessionContext | None) -> dict[str, Any]:
    body = {"account": (None if account is None else {
        "vendor": account.vendor, "account_digest": account.account_digest,
        "verified_by": account.verified_by})}
    if connection is not None:
        body["connection"] = connection.as_dict()
    return body


@dataclass(frozen=True)
class QuotaObservation:
    account: AccountIdentity | None
    source: QuotaSource
    observed_at: datetime
    state: str
    windows: tuple[QuotaWindow, ...] = ()
    reason: str | None = None
    connection: SessionContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _source(self.source))
        account, connection = _subject(self.account, self.connection, self.source)
        object.__setattr__(self, "account", account)
        object.__setattr__(self, "connection", connection)
        object.__setattr__(self, "observed_at", instant(self.observed_at))
        if self.source.observation_kind != "quota":
            raise QuotaError("quota observation requires a subscription source")
        if type(self.windows) is not tuple or len(self.windows) > 128:
            raise QuotaError("quota windows must be a bounded tuple")
        rebuilt = []
        for window in self.windows:
            if type(window) is not QuotaWindow:
                raise QuotaError("invalid quota window")
            rebuilt.append(QuotaWindow(window.limit_id, window.window_id, window.used_percent,
                                       window.resets_at, window.duration_minutes, window.starts_at))
        object.__setattr__(self, "windows", tuple(rebuilt))
        keys = {(w.limit_id, w.window_id) for w in rebuilt}
        if len(keys) != len(rebuilt):
            raise QuotaError("duplicate quota window identity")
        if type(self.state) is not str:
            raise QuotaError("invalid quota observation state")
        if self.state == "observed":
            if not rebuilt or self.reason is not None:
                raise QuotaError("observed quotas require windows and no failure reason")
        elif self.state in ("unavailable", "error"):
            if rebuilt or type(self.reason) is not str or self.reason not in _REASONS:
                raise QuotaError("unavailable quotas require a bounded reason and no windows")
        else:
            raise QuotaError("unknown quota observation state")

    def as_dict(self) -> dict[str, Any]:
        return {**_subject_dict(self.account, self.connection),
                "source": {"kind": self.source.kind, "version": self.source.version},
                "observed_at": _iso(self.observed_at), "state": self.state,
                "reason": self.reason, "windows": [w.as_dict() for w in self.windows]}


def reconstruct_observation(value: object) -> QuotaObservation | BalanceObservation:
    if type(value) is QuotaObservation:
        return QuotaObservation(value.account, value.source, value.observed_at,
                                value.state, value.windows, value.reason, value.connection)
    if type(value) is BalanceObservation:
        return BalanceObservation(value.account, value.source, value.observed_at,
                                  value.state, value.balances, value.is_available, value.reason,
                                  value.connection)
    raise QuotaError("invalid quota or balance observation")


def failed_observation(account: AccountIdentity | None, source: QuotaSource, observed_at: datetime,
                       reason: str = "source_error", *, connection: SessionContext | None = None) -> QuotaObservation:
    """A collector failure with a closed reason, never an upstream error body."""
    return QuotaObservation(account, source, observed_at, "error", reason=reason, connection=connection)


def _native_time(value: object, encoding: str) -> datetime | None:
    if encoding == "unix":
        return _unix(value)
    if encoding == "rfc3339":
        return _rfc3339(value)
    if value is not None:
        raise QuotaError("source does not report reset timestamps")
    return None


def parse_observation(payload: object, *, policy: QuotaPolicy,
                      account: AccountIdentity | None = None, version: str,
                      observed_at: datetime,
                      connection: CredentialContext | SessionContext | None = None) -> QuotaObservation | BalanceObservation:
    """Decode through a provider-owned policy, then validate every native value.

    Policies are trusted code, never parsed from an HTTP request. Even their
    frozen results are reconstructed rather than trusted as canonical values.
    """
    policy = quota_policy(policy)
    source = QuotaSource(policy, version)
    account, connection = _subject(account, connection, source)
    observed_at = instant(observed_at)
    reading = policy.parse(payload)
    if type(reading) is not NativeQuotaReading or type(reading.error) is not bool:
        raise QuotaError("invalid native quota reading")
    if quota_policy(reading.policy) != policy:
        raise QuotaError("native parser and declared source policy differ")
    if type(reading.windows) is not tuple or len(reading.windows) > 128:
        raise QuotaError("native quota windows must be a bounded tuple")
    if type(reading.balances) is not tuple or len(reading.balances) > 64:
        raise QuotaError("native balance amounts must be a bounded tuple")
    if reading.error:
        if reading.windows or reading.balances or reading.is_available is not None:
            raise QuotaError("native failure must contain no usage facts")
        if source.observation_kind == "quota":
            return failed_observation(account, source, observed_at, connection=connection)
        return failed_balance_observation(account, source, observed_at, connection=connection)
    if source.observation_kind == "balance":
        if reading.windows:
            raise QuotaError("balance source cannot report quota windows")
        amounts = []
        for row in reading.balances:
            if type(row) is not NativeBalanceAmount:
                raise QuotaError("invalid native balance amount")
            amounts.append(BalanceAmount(row.currency, row.total_balance,
                                         row.granted_balance, row.topped_up_balance))
        return BalanceObservation(account, source, observed_at, "observed",
                                  tuple(amounts), reading.is_available, connection=connection)
    if reading.balances or reading.is_available is not None:
        raise QuotaError("subscription source cannot report a monetary balance")
    windows = _reading_windows(reading, policy)
    return QuotaObservation(account, source, observed_at,
                            "observed" if windows else "unavailable", windows,
                            None if windows else "no_data", connection)


def _reading_windows(reading: NativeQuotaReading, policy: QuotaPolicy) -> tuple[QuotaWindow, ...]:
    """Validate each native subscription window before publishing any of them."""
    windows = []
    for row in reading.windows:
        if type(row) is not NativeQuotaWindow:
            raise QuotaError("invalid native quota window")
        _text(row.limit_id, "limit id")
        _text(row.window_id, "window id")
        percent = _percentage(row.used_percent)
        minutes = _optional_minutes(row.duration_minutes)
        reset = _native_time(row.resets_at, policy.timestamp_format)
        start = _native_time(row.starts_at, policy.timestamp_format)
        if start is not None and reset is not None and start >= reset:
            raise QuotaError("quota window ends before it starts")
        if percent is not None or reset is not None:
            windows.append(QuotaWindow(row.limit_id, row.window_id, percent, reset, minutes, start))
    return tuple(windows)


def _money(value: object) -> str:
    # The native schema uses decimal strings. Retain their exact decimal value;
    # no float conversion, exponent, sign, locale separator or NaN is admitted.
    if type(value) is not str or len(value) > 128 or not re.fullmatch(r"\d+(?:\.\d+)?", value, re.ASCII):
        raise QuotaError("invalid balance decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise QuotaError("invalid balance decimal string") from exc
    if not amount.is_finite() or amount < 0:
        raise QuotaError("invalid balance decimal string")
    return format(amount, "f")


@dataclass(frozen=True)
class BalanceAmount:
    currency: str
    total_balance: str
    granted_balance: str
    topped_up_balance: str

    def __post_init__(self) -> None:
        if type(self.currency) is not str or re.fullmatch("[A-Z]{3}", self.currency) is None:
            raise QuotaError("invalid balance currency")
        for name in ("total_balance", "granted_balance", "topped_up_balance"):
            object.__setattr__(self, name, _money(getattr(self, name)))

    def as_dict(self) -> dict[str, str]:
        return {"currency": self.currency, "total_balance": self.total_balance,
                "granted_balance": self.granted_balance, "topped_up_balance": self.topped_up_balance}


@dataclass(frozen=True)
class BalanceObservation:
    """Native monetary balance, independent of periodic subscription windows."""
    account: AccountIdentity | None
    source: QuotaSource
    observed_at: datetime
    state: str
    balances: tuple[BalanceAmount, ...] = ()
    is_available: bool | None = None
    reason: str | None = None
    connection: CredentialContext | SessionContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _source(self.source))
        account, connection = _subject(self.account, self.connection, self.source)
        object.__setattr__(self, "account", account)
        object.__setattr__(self, "connection", connection)
        if self.source.observation_kind != "balance":
            raise QuotaError("balance observation requires a monetary source")
        object.__setattr__(self, "observed_at", instant(self.observed_at))
        if type(self.balances) is not tuple or len(self.balances) > len(self.source.policy.currencies):
            raise QuotaError("balance amounts must be a bounded tuple")
        rebuilt = []
        for amount in self.balances:
            if type(amount) is not BalanceAmount:
                raise QuotaError("invalid balance amount")
            if type(amount.currency) is not str or amount.currency not in self.source.policy.currencies:
                raise QuotaError("unsupported balance currency")
            rebuilt.append(BalanceAmount(amount.currency, amount.total_balance,
                                         amount.granted_balance, amount.topped_up_balance))
        if len({amount.currency for amount in rebuilt}) != len(rebuilt):
            raise QuotaError("duplicate balance currency")
        object.__setattr__(self, "balances", tuple(rebuilt))
        if type(self.state) is not str:
            raise QuotaError("invalid balance observation state")
        if self.state == "observed":
            if not rebuilt or type(self.is_available) is not bool or self.reason is not None:
                raise QuotaError("observed balance requires amounts and native availability")
        elif self.state in ("error", "unavailable"):
            if rebuilt or self.is_available is not None or type(self.reason) is not str or self.reason not in _REASONS:
                raise QuotaError("unavailable balance requires a bounded reason and no amounts")
        else:
            raise QuotaError("unknown balance observation state")

    def as_dict(self) -> dict[str, Any]:
        return {**_subject_dict(self.account, self.connection),
                "source": {"kind": self.source.kind, "version": self.source.version},
                "observed_at": _iso(self.observed_at), "state": self.state, "reason": self.reason,
                "balances": [amount.as_dict() for amount in self.balances],
                "is_available": self.is_available, "reset_applicability": "not_applicable",
                "resets_at": None, "windows": []}


def failed_balance_observation(account: AccountIdentity | None, source: QuotaSource, observed_at: datetime,
                               reason: str = "source_error", *,
                               connection: CredentialContext | SessionContext | None = None) -> BalanceObservation:
    return BalanceObservation(account, source, observed_at, "error", reason=reason, connection=connection)
