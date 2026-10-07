"""Cache-only HTTP quota projection; no collector or credential reaches this door."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from .adapters.provider import ProviderContract, provider_projection
from .api_contracts import ApiRefusal
from .http_transport import announces_a_body, command_content_length
from .quota import QuotaError, _rfc3339
from .quota_service import QuotaService


DEFAULT_QUOTA_MAX_AGE = timedelta(minutes=5)


def validate_get(target: str, headers: tuple[tuple[str, str], ...], body: bytes) -> None:
    """An exact, bodyless cache read has no refresh or selection inputs."""
    if target != "/command/quotas":
        raise ApiRefusal.fixed("route_not_found")
    if type(body) is not bytes or body:
        raise ApiRefusal.fixed("malformed_request")
    if announces_a_body(headers) and command_content_length(headers) != 0:
        raise ApiRefusal.fixed("malformed_request")


class QuotaView:
    """Hold only an observation cache and a freshness interval, never a supplier."""

    def __init__(self, service: QuotaService | None, max_age: timedelta) -> None:
        if service is not None and type(service) is not QuotaService:
            raise TypeError("CommandApi quota_service must be an exact QuotaService")
        if type(max_age) is not timedelta or max_age <= timedelta(0):
            raise TypeError("CommandApi quota_max_age must be a positive timedelta")
        self._service = QuotaService() if service is None else service
        self._max_age = max_age

    def payload(self, contracts: Iterable[ProviderContract], now: str) -> dict[str, Any]:
        """Reconstruct cached facts for every provided catalog row, including missing."""
        providers = provider_projection(contracts)
        binding_ids = tuple(row["provider_id"] for row in providers)
        try:
            at = _rfc3339(now)
            if at is None:
                raise QuotaError("quota view needs the server clock")
            snapshots = self._service.snapshots(binding_ids, now=at, max_age=self._max_age)
            rows = []
            for snapshot in snapshots:
                row = snapshot.as_dict()
                # Cache connection identities keep unknown accounts isolated.
                # Binding ids preserve that separation on HTTP without exposing
                # the UUID or turning it into a billing-account identity.
                row.pop("connection", None)
                row["account_status"] = "unknown" if row["account"] is None else "verified"
                rows.append(row)
        except QuotaError as error:
            raise ApiRefusal.fixed("service_refused") from error
        return {"as_of": at.isoformat().replace("+00:00", "Z"),
                "max_age_seconds": self._max_age.total_seconds(),
                "providers": providers, "snapshots": rows}
