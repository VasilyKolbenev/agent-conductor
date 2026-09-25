"""Private provider quota plans, separate from the public provider catalog.

No network or persistence. A ready plan mints an independent, account-unknown
context. Neither equal keys nor operator aliases merge monetary observations.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .adapters.quota_connection import NativeQuotaConnection, NativeQuotaReader, native_quota_connection
from .adapters.quota_contracts import QuotaError, quota_text
from .quota import CredentialContext, SessionContext, QuotaSource


@dataclass(frozen=True)
class ProviderQuotaPlan:
    provider_id: str
    request: NativeQuotaConnection | NativeQuotaReader | None = field(default=None, repr=False)
    source: QuotaSource | None = None
    connection: CredentialContext | SessionContext | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        quota_text(self.provider_id, "provider id")
        if self.request is None:
            if self.reason != "source_error" or self.source is not None or self.connection is not None:
                raise QuotaError("invalid unavailable quota plan")
            return
        request = native_quota_connection(self.request)
        object.__setattr__(self, "request", request)
        source = QuotaSource(request.policy, request.version)
        if type(self.source) is not QuotaSource or self.source != source:
            raise QuotaError("quota plan source mismatch")
        object.__setattr__(self, "source", source)
        if self.reason != request.reason:
            raise QuotaError("quota plan reason mismatch")
        if self.reason is not None:
            if self.connection is not None:
                raise QuotaError("unavailable quota plan has no credential context")
        else:
            kind = SessionContext if type(request) is NativeQuotaReader else CredentialContext
            if type(self.connection) is not kind:
                raise QuotaError("ready quota plan requires a credential context")
            connection = kind(self.connection.policy, self.connection.context_id)
            if connection.policy != request.policy:
                raise QuotaError("quota plan connection policy mismatch")
            object.__setattr__(self, "connection", connection)


def quota_plan_for(provider_id: str, adapter: object) -> ProviderQuotaPlan | None:
    """Call an optional trusted supplier; never expose its exception text."""
    quota_text(provider_id, "provider id")
    if adapter is None:
        return None
    try:
        supplier = getattr(adapter, "quota_connection", None)
        if supplier is None:
            return None
        request = native_quota_connection(supplier())
        source = QuotaSource(request.policy, request.version)
        kind = SessionContext if type(request) is NativeQuotaReader else CredentialContext
        connection = kind.create(request.policy) if request.reason is None else None
        return ProviderQuotaPlan(provider_id, request, source, connection, request.reason)
    except Exception:
        return ProviderQuotaPlan(provider_id, reason="source_error")
