"""Value-only local source/copy account provenance, never server identity."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass


_VENDORS = {
    "Anthropic": "anthropic", "OpenAI": "openai", "xAI": "xai", "Moonshot AI": "moonshot",
    "anthropic": "anthropic", "openai": "openai", "xai": "xai", "moonshot": "moonshot",
}
_FIELDS = frozenset({"version", "vendor", "source", "status", "account_sha256"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ADAPTER_VENDORS = {"claude-code": "anthropic", "codex": "openai",
                    "grok-build": "xai", "kimi-code": "moonshot"}


def normalize_vendor(value: str) -> str:
    """Normalize only the fixed shipped vendor names, without carrying arbitrary text."""
    if type(value) is not str or value not in _VENDORS:
        raise ValueError("unsupported subscription vendor")
    return _VENDORS[value]


def require_adapter_vendor(adapter_id: str, vendor: str) -> None:
    """Only a shipped adapter's known vendor can label its local account evidence."""
    if type(adapter_id) is not str or _ADAPTER_VENDORS.get(adapter_id) != vendor:
        raise ValueError("account proof vendor does not match a known adapter")


def _validate(value: Mapping) -> dict:
    if set(value) != _FIELDS:
        raise ValueError("subscription account proof fields must be exact")
    plain = dict(value)
    if type(plain["version"]) is not int or plain["version"] != 1:
        raise ValueError("unsupported subscription account proof version")
    vendor = plain["vendor"]
    if type(vendor) is not str or vendor not in {"anthropic", "openai", "xai", "moonshot"}:
        raise ValueError("unsupported subscription vendor")
    if type(plain["source"]) is not str or plain["source"] != "source_relay":
        raise ValueError("unsupported subscription account source")
    status, digest = plain["status"], plain["account_sha256"]
    if type(status) is not str or status not in {"local_match", "unknown"}:
        raise ValueError("unsupported subscription account status")
    if status == "unknown":
        if digest is not None:
            raise ValueError("unknown account proof cannot carry an account hash")
    elif type(digest) is not str or _DIGEST.fullmatch(digest) is None:
        raise ValueError("local account match requires an account hash")
    return plain


@dataclass(frozen=True)
class SubscriptionAccountProof:
    """Only a fixed safe digest can outlive the login lease."""

    version: int
    vendor: str
    source: str
    status: str
    account_sha256: str | None

    def __post_init__(self) -> None:
        _validate(self.as_dict())

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in _FIELDS}


def settled_proof(value: object) -> dict:
    """Validate a frozen proof or closed mapping, never retaining caller-owned objects."""
    if type(value) is SubscriptionAccountProof:
        value = value.as_dict()
    if not isinstance(value, Mapping):
        raise ValueError("subscription account proof must be a closed object")
    return _validate(value)


def make_proof(vendor: str, source_account: str | None,
               relay_account: str | None) -> SubscriptionAccountProof:
    """Hash matching admitted native IDs; absent/malformed IDs remain unverified."""
    if normalize_vendor(vendor) != vendor:
        raise ValueError("account proof requires a canonical vendor")
    digest = None
    if (type(source_account) is str and source_account and type(relay_account) is str
            and source_account == relay_account):
        try:
            account_bytes = source_account.encode("utf-8")
        except UnicodeEncodeError:
            pass
        else:
            digest = "sha256:" + hashlib.sha256(
                vendor.encode("ascii") + b"\x00" + account_bytes).hexdigest()
    return SubscriptionAccountProof(1, vendor, "source_relay",
                                    "unknown" if digest is None else "local_match", digest)
