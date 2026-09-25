"""One server-owned, serial quota poller; HTTP handlers only see its cache.

Plans come from the same provider resolution as dispatch, not request bodies.
Stopping invalidates outstanding tickets before joining the worker. Join waits
for an in-flight fetch to return; socket timeout is not an absolute DNS deadline.
No background thread is claimed retired until it has actually exited.
An interrupted start may leave bootstrap unconfirmed. Retain that candidate;
stop reports uncertainty if the public Thread API cannot yet join it.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event, Lock, Thread, current_thread

from .command.quota import (QuotaError, failed_balance_observation, failed_observation, instant, parse_observation)
from .command.adapters.quota_connection import (NativeQuotaDeferred, NativeQuotaReader, NativeQuotaReadError,
                                                NativeQuotaSample, NativeQuotaUnconfirmed)
from .command.quota_plans import ProviderQuotaPlan
from .command.quota_service import QuotaService
from .quota_transport import QuotaFetchError, read_quota_json
from .quota_loopback import fetch_loopback_json, wait_quota_loopback, choose_loopback_port


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QuotaStartupUncertain(RuntimeError):
    """The retained candidate cannot yet be proved absent or joined."""


def _plans(values) -> tuple[ProviderQuotaPlan, ...]:
    if type(values) is not tuple or len(values) > 1024:
        raise ValueError('quota collector needs a bounded tuple of plans')
    copied = []
    for value in values:
        if type(value) is not ProviderQuotaPlan:
            raise ValueError('invalid quota collector plan')
        copied.append(ProviderQuotaPlan(value.provider_id, value.request, value.source,
                                        value.connection, value.reason))
    if len({plan.provider_id for plan in copied}) != len(copied):
        raise ValueError('duplicate quota collector binding')
    return tuple(copied)


def _failed(plan, at, error):
    reason = 'source_error'
    if isinstance(error, QuotaFetchError):
        reason = {'unauthorized': 'not_authenticated', 'invalid_payload': 'malformed_payload',
                  'unsupported_endpoint': 'not_supported'}.get(error.reason, 'source_error')
    elif isinstance(error, NativeQuotaReadError):
        reason = error.reason
    elif isinstance(error, QuotaError):
        reason = 'malformed_payload'
    failure = failed_observation if plan.source.observation_kind == 'quota' else failed_balance_observation
    return failure(None, plan.source, at, reason, connection=plan.connection)


class QuotaCollector:
    """Mint one polling lifetime, never restart or transfer its credentials."""

    def __init__(self, service: QuotaService, plans: tuple[ProviderQuotaPlan, ...], *,
                 fetch: Callable[[str, str], dict] = read_quota_json,
                 clock: Callable[[], datetime] = _now, interval_seconds: float = 60,
                 loopback_wait=wait_quota_loopback, loopback_fetch=fetch_loopback_json,
                 loopback_port=choose_loopback_port) -> None:
        if type(service) is not QuotaService or not callable(fetch) or not callable(clock):
            raise TypeError('quota collector requires a cache and callables')
        if type(interval_seconds) not in (int, float) or not 1 <= interval_seconds <= 3600:
            raise ValueError('invalid quota polling interval')
        if not callable(loopback_wait) or not callable(loopback_fetch) or not callable(loopback_port):
            raise TypeError('quota loopback services must be callable')
        self._loopback = (loopback_wait, loopback_fetch, loopback_port)
        plans = _plans(plans)  # Validate all plans before mutating any cache binding.
        self._service, self._fetch, self._clock = service, fetch, clock
        self._interval = interval_seconds
        self._stop, self._guard = Event(), Lock()
        self._thread: Thread | None = None
        self._started = False
        self._work = []
        for plan in plans:
            service.unbind(plan.provider_id)
            if plan.reason is None:
                ticket = service.bind(plan.provider_id, None, plan.source, connection=plan.connection)
                self._work.append((plan, ticket))

    def start(self) -> None:
        with self._guard:
            if self._started or self._stop.is_set():
                raise RuntimeError('quota collector can start once')
            self._started = True
            if self._work:
                worker = Thread(target=self._run, name='conduct-quota-collector', daemon=False)
                self._thread = worker
                try:
                    worker.start()
                except BaseException:
                    # Cancel before inspecting bootstrap. A native thread may
                    # exist before ident is set; if it enters later it must not
                    # begin a fetch. Keep its reference for actual retirement.
                    self._stop.set()
                    raise

    @property
    def running(self) -> bool:
        with self._guard:
            return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        with self._guard:
            worker = self._thread
            if worker is current_thread():
                raise RuntimeError('a quota worker cannot join itself')
            self._stop.set()
            for _plan, ticket in self._work:
                self._service.retire(ticket)
        if worker is not None:
            try:
                worker.join()
            except RuntimeError:
                # is_alive/ident cannot prove that start created no native
                # thread. A subsequent stop may join a confirmed bootstrap.
                raise QuotaStartupUncertain('quota worker retirement is unconfirmed') from None

    def _run(self) -> None:
        while not self._stop.is_set():
            for plan, ticket in self._work:
                if self._stop.is_set():
                    return
                self._collect(plan, ticket)
            if self._stop.wait(self._interval):
                return

    def _collect(self, plan, ticket) -> None:
        try:
            if type(plan.request) is NativeQuotaReader:
                payload = (plan.request.read(*self._loopback) if plan.request.transport == "loopback"
                           else plan.request.read())
            else:
                payload = self._fetch(plan.request.endpoint, plan.request.bearer)
            at = instant(self._clock())
            if type(payload) is NativeQuotaSample:
                sample = NativeQuotaSample(payload.payload, payload.observed_at_ms)
                at = instant(datetime.fromtimestamp(sample.observed_at_ms / 1000, timezone.utc))
                payload = sample.payload
            observation = parse_observation(payload, policy=plan.source.policy,
                version=plan.source.version, observed_at=at, connection=plan.connection)
        except NativeQuotaUnconfirmed:
            # The source answered but nothing is confirmed with its own age yet: publish nothing, so
            # the last confirmed observation keeps its time; the read did run, so no step is waiting.
            if not self._stop.is_set():
                self._service.clear_deferral(ticket)
            return
        except NativeQuotaDeferred:
            # A step holds the harness root: no reading happened, so nothing is published and the
            # last observation keeps its own time; only the deferral itself is recorded.
            if not self._stop.is_set():
                self._service.defer(ticket, now=instant(self._clock()))
            return
        except Exception as error:
            at = instant(self._clock())
            observation = _failed(plan, at, error)
        if not self._stop.is_set():
            try:
                self._service.publish(ticket, observation, now=instant(self._clock()))
            except QuotaError:
                # A clock rollback cannot make a future sample current or kill
                # collection for other bindings. Cache freshness remains explicit.
                pass
