"""In-memory latest quota observations; no polling, endpoints or execution rights.

Collectors take a generation ticket from bind(), obtain native facts, then
publish(). Rebinding invalidates in-flight tickets, including A -> B -> A.
Snapshots are detached immutable values, grouped by confirmed account/source.
Account-unknown connection balances stay separate per binding generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Any

from .quota import (AccountIdentity, BalanceObservation, CredentialContext, SessionContext, QuotaError, QuotaObservation,
                    QuotaSource, _iso, _source, _subject, _subject_dict, _text, instant, reconstruct_observation)


@dataclass(frozen=True)
class CollectionTicket:
    binding_id: str
    generation: int
    account: AccountIdentity | None
    source: QuotaSource
    connection: CredentialContext | SessionContext | None = None

    def __post_init__(self) -> None:
        _text(self.binding_id, "quota binding id")
        if type(self.generation) is not int or self.generation < 1:
            raise QuotaError("invalid quota collection generation")
        object.__setattr__(self, "source", _source(self.source))
        account, connection = _subject(self.account, self.connection, self.source)
        object.__setattr__(self, "account", account)
        object.__setattr__(self, "connection", connection)


@dataclass(frozen=True)
class QuotaSnapshot:
    binding_ids: tuple[str, ...]
    account: AccountIdentity | None
    source: QuotaSource | None
    observation: QuotaObservation | BalanceObservation | None
    freshness: str
    stale_windows: tuple[tuple[str, str], ...] = ()
    connection: CredentialContext | SessionContext | None = None
    #: Windows whose own reset has passed since the reading: their figures are not a current
    #: remainder (Codex ruling J). Kept apart from TTL ageing, which only makes them stale.
    reset_windows: tuple[tuple[str, str], ...] = ()
    #: When the collector last found the harness root busy for this binding generation; the
    #: observation above keeps its own time, age and resets.
    deferred_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        body = self.observation.as_dict() if self.observation else {
            **_subject_dict(self.account, self.connection),
            "source": (None if self.source is None else {
                "kind": self.source.kind, "version": self.source.version}),
            "observed_at": None, "state": "missing", "reason": "no_data", "windows": []}
        if self.observation is None and self.source is not None and self.source.observation_kind == "balance":
            body.update(balances=[], is_available=None, resets_at=None, reset_applicability="not_applicable")
        body.update(binding_ids=list(self.binding_ids), freshness=self.freshness,
                    deferred_at=_iso(self.deferred_at))
        expired, reset = set(self.stale_windows), set(self.reset_windows)
        for window in body["windows"]:
            key = (window["limit_id"], window["window_id"])
            window["freshness"] = "reset_passed" if key in reset else "stale" if key in expired else "current"
        return body


def _key(ticket: CollectionTicket) -> tuple[str, ...]:
    if ticket.connection is not None:
        return "connection", ticket.binding_id, str(ticket.generation)
    return "account", ticket.account.vendor, ticket.account.account_digest, ticket.source.kind


def _ticket(value: object) -> CollectionTicket:
    if type(value) is not CollectionTicket:
        raise QuotaError("invalid quota collection ticket")
    return CollectionTicket(value.binding_id, value.generation, value.account, value.source, value.connection)


class QuotaService:
    """Thread-safe observation cache with an explicit clock at every boundary."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._generation = 0
        self._bindings: dict[str, CollectionTicket] = {}
        self._latest: dict[tuple[str, ...], QuotaObservation | BalanceObservation] = {}
        self._deferred: dict[str, datetime] = {}

    def bind(self, binding_id: str, account: AccountIdentity | None, source: QuotaSource, *,
             connection: CredentialContext | SessionContext | None = None) -> CollectionTicket:
        """Bind one trusted verified account or account-unknown connection."""
        with self._lock:
            ticket = CollectionTicket(binding_id, self._generation + 1, account, source, connection)
            previous = self._bindings.get(binding_id)
            if previous is not None and previous.connection is not None:
                self._latest.pop(_key(previous), None)
            self._generation += 1
            self._bindings[ticket.binding_id] = ticket
            self._deferred.pop(binding_id, None)
            return _ticket(ticket)

    def unbind(self, binding_id: str) -> None:
        _text(binding_id, "quota binding id")
        with self._lock:
            previous = self._bindings.pop(binding_id, None)
            self._deferred.pop(binding_id, None)
            if previous is not None and previous.connection is not None:
                self._latest.pop(_key(previous), None)

    def publish(self, ticket: CollectionTicket, observation: QuotaObservation | BalanceObservation, *, now: datetime) -> bool:
        """False means superseded, out of order or an equal-time conflict.

        The caller must bind again if its authenticated account changes. Errors
        are observations too: an older success cannot hide a newer failure.
        """
        ticket = _ticket(ticket)
        observation = reconstruct_observation(observation)
        now = instant(now)
        if observation.observed_at > now:
            # The read did complete, so whatever was deferred is over, even though a rolled-back
            # clock cannot accept its observation.
            self.clear_deferral(ticket)
            raise QuotaError("quota observation is from the future")
        connection = observation.connection
        if (observation.account != ticket.account or connection != ticket.connection
                or observation.source != ticket.source):
            raise QuotaError("quota observation does not match the collection binding")
        with self._lock:
            if self._bindings.get(ticket.binding_id) != ticket:
                return False
            # A completed attempt ends the deferral, even one that re-reads an equal sample.
            self._deferred.pop(ticket.binding_id, None)
            key = _key(ticket)
            previous = self._latest.get(key)
            if previous is not None:
                if observation.observed_at < previous.observed_at:
                    return False
                if observation.observed_at == previous.observed_at:
                    return observation == previous
            self._latest[key] = observation
            return True

    def retire(self, ticket: CollectionTicket) -> bool:
        """Retire only this collector generation; a successor binding survives."""
        ticket = _ticket(ticket)
        with self._lock:
            if self._bindings.get(ticket.binding_id) != ticket:
                return False
            self._bindings.pop(ticket.binding_id)
            self._deferred.pop(ticket.binding_id, None)
            if ticket.connection is not None:
                self._latest.pop(_key(ticket), None)
            return True

    def clear_deferral(self, ticket: CollectionTicket) -> bool:
        """End this generation's deferral after a read that ran but published nothing new."""
        ticket = _ticket(ticket)
        with self._lock:
            if self._bindings.get(ticket.binding_id) != ticket:
                return False
            return self._deferred.pop(ticket.binding_id, None) is not None

    def defer(self, ticket: CollectionTicket, *, now: datetime) -> bool:
        """Record that this binding's update was deferred because a step held the root.

        Nothing is observed, written or re-stamped: the latest observation -- success or a
        newer error alike -- keeps its own time, age and resets. A superseded ticket defers
        nothing, so a rebinding never shows another generation's state.
        """
        ticket = _ticket(ticket)
        now = instant(now)
        with self._lock:
            if self._bindings.get(ticket.binding_id) != ticket:
                return False
            self._deferred[ticket.binding_id] = now
            return True

    def snapshots(self, binding_ids: tuple[str, ...], *, now: datetime,
                  max_age: timedelta) -> tuple[QuotaSnapshot, ...]:
        """Read-only groups: the same verified account/source appears once.

        Aliases select bindings only. An unbound alias stays individually
        missing; it cannot assert account equivalence or create a quota total.
        Account-unknown connection balances are never grouped across bindings.
        """
        if type(binding_ids) is not tuple or len(binding_ids) > 1024:
            raise QuotaError("quota binding ids must be a bounded tuple")
        for name in binding_ids:
            _text(name, "quota binding id")
        if len(set(binding_ids)) != len(binding_ids):
            raise QuotaError("duplicate quota binding id")
        now = instant(now)
        if type(max_age) is not timedelta or max_age <= timedelta(0):
            raise QuotaError("quota freshness interval must be positive")
        with self._lock:
            groups: dict[tuple[str, ...], list[str]] = {}
            for name in binding_ids:
                binding = self._bindings.get(name)
                key = ("missing", name) if binding is None else _key(binding)
                groups.setdefault(key, []).append(name)
            result = []
            for names in groups.values():
                binding = self._bindings.get(names[0])
                # bind/unbind/retire drop a binding's deferral, and defer() refuses a superseded
                # ticket, so what is stored here always belongs to the current generation.
                deferred = [self._deferred[name] for name in names if name in self._deferred]
                deferred_at = max(deferred) if deferred else None
                observation = None if binding is None else self._latest.get(_key(binding))
                if observation is None:
                    copied = None if binding is None else _ticket(binding)
                    result.append(QuotaSnapshot(tuple(names), None if copied is None else copied.account,
                                                None if copied is None else copied.source, None, "missing",
                                                connection=None if copied is None else copied.connection,
                                                deferred_at=deferred_at))
                    continue
                observation = reconstruct_observation(observation)
                expired = now < observation.observed_at or now - observation.observed_at >= max_age
                windows = observation.windows if type(observation) is QuotaObservation else ()
                reset = tuple((w.limit_id, w.window_id) for w in windows
                              if w.resets_at is not None and now >= w.resets_at)
                stale = tuple((w.limit_id, w.window_id) for w in windows
                              if expired and (w.limit_id, w.window_id) not in reset)
                result.append(QuotaSnapshot(tuple(names), observation.account, observation.source, observation,
                                            "stale" if expired or reset else "current", stale,
                                            observation.connection, reset_windows=reset,
                                            deferred_at=deferred_at))
            return tuple(result)

    def snapshot(self, binding_id: str, *, now: datetime, max_age: timedelta) -> QuotaSnapshot:
        return self.snapshots((binding_id,), now=now, max_age=max_age)[0]
