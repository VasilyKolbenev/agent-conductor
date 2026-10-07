"""Private, provider-supplied monetary request; never a public input or receipt.

The supplier owns endpoint choice and proves the dispatch relationship. This
value carries that trusted result, not a claim accepted from a browser. The
separate HTTPS transport independently validates its endpoint before any I/O.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .quota_contracts import QuotaError, QuotaPolicy, quota_policy, quota_text

CONNECTION_REASONS = frozenset({"no_data", "not_supported", "source_error"})


class NativeQuotaReadError(QuotaError):
    """Closed observation failure; no native output or exception is retained."""
    def __init__(self, reason: str = "source_error") -> None:
        if reason not in {"source_error", "not_authenticated", "not_supported", "malformed_payload"}:
            reason = "source_error"
        self.reason = reason
        super().__init__(reason)


class NativeQuotaUnconfirmed(RuntimeError):
    """The source answered, but nothing could be confirmed with its own age yet.

    Claude 2.1.239 rewrites its usage cache at most every 300 s, so a live reply taken inside
    that window can be newer than the cache that dates it. Not a failure: the last confirmed
    observation stays, with its own time, until a reply and a cache agree again.
    """


class NativeQuotaDeferred(RuntimeError):
    """The harness root stayed busy for the bounded wait: no reading was attempted.

    Neither a failed observation nor a new one. A step holds the root for its whole
    doer -> checker -> receipt interval; the collector records only that this update was
    deferred, and the last observation keeps its own time (Codex ruling J, 23.09.2026).
    Deliberately NOT a NativeQuotaReadError (its reason folds to source_error) nor a
    QuotaError (the collector reports that as malformed_payload).
    """


@dataclass(frozen=True)
class NativeQuotaSample:
    """Native cached facts retain their native age across polling reads."""
    payload: dict = field(repr=False)
    observed_at_ms: int

    def __post_init__(self) -> None:
        if type(self.payload) is not dict:
            raise QuotaError("native sample requires an object")
        if type(self.observed_at_ms) is not int or not 0 <= self.observed_at_ms <= 253402300799999:
            raise QuotaError("invalid native sample timestamp")


@dataclass(frozen=True)
class NativeQuotaReader:
    """Provider-owned reader; private callable, never a public input or receipt."""
    policy: QuotaPolicy
    version: str
    read: Callable[..., dict | NativeQuotaSample] | None = field(default=None, repr=False)
    reason: str | None = None
    transport: str = "stdio"

    def __post_init__(self) -> None:
        if type(self.transport) is not str or self.transport not in ("stdio", "loopback"):
            raise QuotaError("invalid native reader transport")
        object.__setattr__(self, "policy", quota_policy(self.policy))
        quota_text(self.version, "source version")
        if self.policy.observation_kind != "quota":
            raise QuotaError("native reader requires a subscription source")
        if self.reason is None:
            if not callable(self.read):
                raise QuotaError("native reader requires a callable")
        elif self.reason not in CONNECTION_REASONS or self.read is not None:
            raise QuotaError("invalid native reader unavailability")


@dataclass(frozen=True)
class NativeQuotaConnection:
    policy: QuotaPolicy
    version: str
    endpoint: str
    bearer: str | None = field(default=None, repr=False)
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy", quota_policy(self.policy))
        if self.policy.observation_kind != "balance":
            raise QuotaError("private connection requires a monetary source")
        quota_text(self.version, "source version")
        # Deliberately narrower than a URL parser. The network boundary repeats
        # full URL validation; this SDK value needs no networking dependency.
        if type(self.endpoint) is not str or len(self.endpoint) > 256 or re.fullmatch(
                r"https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::443)?/[A-Za-z0-9_/-]+",
                self.endpoint) is None:
            raise QuotaError("invalid private quota endpoint")
        if self.reason is None:
            if type(self.bearer) is not str or not 1 <= len(self.bearer) <= 8192 or any(
                    ord(char) <= 32 or ord(char) >= 127 for char in self.bearer):
                raise QuotaError("invalid private quota credential")
        elif type(self.reason) is not str or self.reason not in CONNECTION_REASONS or self.bearer is not None:
            raise QuotaError("invalid private quota unavailability")


def native_quota_connection(value: object) -> NativeQuotaConnection | NativeQuotaReader:
    """Reconstruct even a nominally frozen supplier value before core use."""
    if type(value) is NativeQuotaReader:
        return NativeQuotaReader(value.policy, value.version, value.read, value.reason, value.transport)
    if type(value) is not NativeQuotaConnection:
        raise QuotaError("private quota connection is required")
    return NativeQuotaConnection(value.policy, value.version, value.endpoint,
                                 value.bearer, value.reason)
