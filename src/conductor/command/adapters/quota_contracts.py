"""Value-only native usage seam; provider modules own the schema and policy.

These decoded inputs carry no clock, credential, filesystem or execution door.
The observation boundary validates their numbers and timestamps independently.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable


class QuotaError(ValueError):
    """A usage input cannot be represented without inventing a fact."""


def quota_text(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value) > 256:
        raise QuotaError(f"invalid {field}")
    if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise QuotaError(f"invalid {field}")
    return value


def quota_object(value: object) -> dict[str, Any]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise QuotaError("quota payload must contain plain objects")
    return value


def quota_percentage(value: object) -> float | None:
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


@dataclass(frozen=True)
class NativeQuotaWindow:
    limit_id: str
    window_id: str
    used_percent: object
    resets_at: object
    duration_minutes: object = None
    starts_at: object = None


@dataclass(frozen=True)
class NativeBalanceAmount:
    currency: object
    total_balance: object
    granted_balance: object
    topped_up_balance: object


@dataclass(frozen=True)
class NativeQuotaReading:
    windows: tuple[NativeQuotaWindow, ...] = ()
    balances: tuple[NativeBalanceAmount, ...] = ()
    is_available: object = None
    error: bool = False
    policy: QuotaPolicy | None = None

    def bound_to(self, policy: QuotaPolicy) -> NativeQuotaReading:
        """Stamp the native parser's own source, before the core compares it."""
        return NativeQuotaReading(self.windows, self.balances, self.is_available,
                                  self.error, quota_policy(policy))


@dataclass(frozen=True)
class QuotaPolicy:
    """Provider-owned schema metadata, not an identity claim from an HTTP client."""
    vendor: str
    identity_source: str
    source_kind: str
    observation_kind: str
    timestamp_format: str
    parse: Callable[[object], NativeQuotaReading]
    currencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in ("vendor", "identity_source", "source_kind"):
            quota_text(getattr(self, field), field)
        if type(self.observation_kind) is not str or self.observation_kind not in ("quota", "balance"):
            raise QuotaError("unknown observation kind")
        if type(self.timestamp_format) is not str or self.timestamp_format not in ("unix", "rfc3339", "none"):
            raise QuotaError("unknown timestamp format")
        if not callable(self.parse):
            raise QuotaError("native quota parser is required")
        if type(self.currencies) is not tuple or len(self.currencies) > 64:
            raise QuotaError("invalid supported currencies")
        if any(type(item) is not str or re.fullmatch("[A-Z]{3}", item) is None for item in self.currencies):
            raise QuotaError("invalid supported currency")
        if len(set(self.currencies)) != len(self.currencies):
            raise QuotaError("duplicate supported currency")
        if self.observation_kind == "quota":
            if self.currencies or self.timestamp_format == "none":
                raise QuotaError("invalid quota policy")
        elif not self.currencies or self.timestamp_format != "none":
            raise QuotaError("invalid balance policy")


def quota_policy(value: object) -> QuotaPolicy:
    if type(value) is not QuotaPolicy:
        raise QuotaError("quota policy is required")
    return QuotaPolicy(value.vendor, value.identity_source, value.source_kind,
                       value.observation_kind, value.timestamp_format, value.parse,
                       value.currencies)


def bucket_windows(payload: object, *, map_field: str, legacy_field: str,
                   default_limit: str, limit_field: str, window_fields: tuple[str, ...],
                   used_field: str, reset_field: str, duration_field: str) -> NativeQuotaReading:
    """Decode a keyed-window schema using fields supplied by its provider owner."""
    body = quota_object(payload)
    buckets = body.get(map_field)
    if buckets is None:
        legacy = body.get(legacy_field)
        if legacy is None:
            buckets = {}
        else:
            legacy = quota_object(legacy)
            limit = legacy.get(limit_field)
            if limit is None:
                limit = default_limit
            buckets = {quota_text(limit, "limit id"): legacy}
    buckets = quota_object(buckets)
    if len(buckets) > 64:
        raise QuotaError("too many quota buckets")
    windows = []
    for limit, raw in buckets.items():
        quota_text(limit, "limit id")
        if raw is None:
            continue
        bucket = quota_object(raw)
        declared = bucket.get(limit_field)
        if declared is not None and declared != limit:
            raise QuotaError("quota bucket identity mismatch")
        for name in window_fields:
            raw_window = bucket.get(name)
            if raw_window is not None:
                row = quota_object(raw_window)
                windows.append(NativeQuotaWindow(limit, name, row.get(used_field),
                                                  row.get(reset_field), row.get(duration_field)))
    return NativeQuotaReading(tuple(windows))
