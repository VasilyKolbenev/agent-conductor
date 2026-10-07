"""Owned polling uses typed source plans; blocked fetches do not outlive stop.

Only injected local fetches are used. No network, browser or harness is involved.
The first named startup witness is intended to run before the lifecycle fix.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from threading import Event, Thread

import pytest

from conductor import quota_collectors as collectors
from conductor.command.adapters.dsh_harness import (
    BALANCE_ENDPOINT, BALANCE_SOURCE_VERSION, QUOTA_POLICY,
)
from conductor.command.adapters.quota_connection import NativeQuotaConnection
from conductor.command.quota import CredentialContext, QuotaError, QuotaSource, parse_observation
from conductor.command.quota_plans import ProviderQuotaPlan
from conductor.command.quota_service import QuotaService
from conductor.quota_transport import QuotaFetchError


AT = datetime(2026, 9, 21, 14, tzinfo=timezone.utc)
AGE = timedelta(minutes=5)
KEY = "synthetic-collector-credential"
WAIT = 5


def ready(provider_id="dsh", *, key=KEY):
    request = NativeQuotaConnection(QUOTA_POLICY, BALANCE_SOURCE_VERSION, BALANCE_ENDPOINT, key)
    source = QuotaSource(QUOTA_POLICY, BALANCE_SOURCE_VERSION)
    return ProviderQuotaPlan(provider_id, request, source, CredentialContext.create(QUOTA_POLICY))


def balance(total="12.3400"):
    return {"is_available": True, "balance_infos": [{"currency": "USD",
        "total_balance": total, "granted_balance": "0.0000", "topped_up_balance": total}]}


def observation(plan, *, total="12.3400", at=AT):
    return parse_observation(balance(total), policy=plan.source.policy,
        version=plan.source.version, observed_at=at, connection=plan.connection)


def snapshot(service, provider_id="dsh", *, at=AT):
    return service.snapshot(provider_id, now=at, max_age=AGE)


def seed(service, plan, *, total="12.3400"):
    ticket = service.bind(plan.provider_id, None, plan.source, connection=plan.connection)
    assert service.publish(ticket, observation(plan, total=total), now=AT)
    return ticket


def finish(collector, *releases):
    """Bounded fixture cleanup still runs when a stop assertion fails."""
    for release in releases:
        release.set()
    collector._stop.set()
    worker = collector._thread
    if worker is not None and worker.ident is not None:
        worker.join(WAIT)
        assert not worker.is_alive(), "quota worker survived controlled fixture release"


def watch_join(monkeypatch, worker):
    entered, timeouts = Event(), []
    actual = worker.join

    def join(timeout=None):
        timeouts.append(timeout)
        entered.set()
        return actual(timeout)

    monkeypatch.setattr(worker, "join", join)
    return entered, timeouts


class Publications:
    def __init__(self, monkeypatch, service, count=1):
        self.calls = []
        self.events = tuple(Event() for _ in range(count))
        actual = service.publish

        def publish(ticket, value, *, now):
            result = actual(ticket, value, now=now)
            self.calls.append((ticket, value, result))
            if len(self.calls) <= len(self.events):
                self.events[len(self.calls) - 1].set()
            return result

        monkeypatch.setattr(service, "publish", publish)


class BlockedFetch:
    def __init__(self, result=None):
        self.entered, self.release = Event(), Event()
        self.calls = []
        self.result = balance() if result is None else result

    def __call__(self, endpoint, bearer):
        self.calls.append((endpoint, bearer))
        self.entered.set()
        if not self.release.wait(WAIT):
            raise RuntimeError("controlled fetch was not released")
        return self.result


def test_start_failure_retains_candidate_and_refuses_to_claim_verified_retirement(monkeypatch):
    service, plan, calls = QuotaService(), ready(), []
    collector = collectors.QuotaCollector(service, (plan,),
        fetch=lambda *args: calls.append(args), clock=lambda: AT)

    def cannot_start(_worker):
        raise RuntimeError("synthetic native thread start refusal")

    monkeypatch.setattr(collectors.Thread, "start", cannot_start)
    try:
        with pytest.raises(RuntimeError, match="synthetic native thread start refusal"):
            collector.start()
        for _ in range(2):
            with pytest.raises(collectors.QuotaStartupUncertain, match='retirement is unconfirmed'):
                collector.stop()
        assert collector._thread is not None
        assert not collector.running and calls == []
        assert snapshot(service).freshness == "missing"
        with pytest.raises(RuntimeError, match="start once"):
            collector.start()
    finally:
        finish(collector)


def test_constructor_refusal_has_no_start_candidate_and_stop_is_idempotent(monkeypatch):
    service, calls = QuotaService(), []
    collector = collectors.QuotaCollector(service, (ready(),),
        fetch=lambda *args: calls.append(args), clock=lambda: AT)
    def no_thread(**kwargs):
        raise RuntimeError('thread construction refused before any start')
    monkeypatch.setattr(collectors, 'Thread', no_thread)
    with pytest.raises(RuntimeError, match='construction refused'):
        collector.start()
    collector.stop()
    collector.stop()
    assert collector._thread is None and calls == [] and not collector.running
    assert snapshot(service).freshness == 'missing'


def test_post_start_interruption_keeps_real_worker_owned_until_stop_joins(monkeypatch):
    service, plan = QuotaService(), ready()
    fetch, retired, stopped = BlockedFetch(), Event(), Event()
    collector = collectors.QuotaCollector(service, (plan,), fetch=fetch, clock=lambda: AT)
    native_start, native_retire = collectors.Thread.start, service.retire
    launched, errors = [], []
    class InterruptedStart(BaseException):
        pass
    def start(worker):
        native_start(worker)
        if worker.name == 'conduct-quota-collector':
            launched.append(worker)
            assert fetch.entered.wait(WAIT)
            raise InterruptedStart('interrupted after actual worker bootstrap')
    def retire(ticket):
        result = native_retire(ticket)
        retired.set()
        return result
    def stop():
        try:
            collector.stop()
        except BaseException as error:
            errors.append(error)
        finally:
            stopped.set()
    monkeypatch.setattr(collectors.Thread, 'start', start)
    monkeypatch.setattr(service, 'retire', retire)
    stopper = None
    try:
        with pytest.raises(InterruptedStart):
            collector.start()
        was_running = collector.running
        stopper = Thread(target=stop, name='controlled-quota-stopper')
        stopper.start()
        assert retired.wait(WAIT), 'stop never retired its cache ticket'
        assert not stopped.wait(0.1), 'stop returned while its real fetch was held'
        assert was_running, 'a live worker was reported absent after interrupted start'
        assert snapshot(service).freshness == 'missing'
    finally:
        fetch.release.set()
        collector._stop.set()
        for worker in [*launched, *([] if stopper is None else [stopper])]:
            worker.join(WAIT)
            assert not worker.is_alive(), 'controlled worker did not retire'
    assert errors == [] and stopped.is_set() and not collector.running


def test_ready_plan_publishes_real_dsh_money_with_exact_source_and_connection(monkeypatch):
    service, plan, calls = QuotaService(), ready(), []
    published = Publications(monkeypatch, service)

    def fetch(endpoint, bearer):
        calls.append((endpoint, bearer))
        return {**balance(), "private": KEY}

    collector = collectors.QuotaCollector(service, (plan,), fetch=fetch, clock=lambda: AT)
    try:
        collector.start()
        assert published.events[0].wait(WAIT), "collector did not publish"
        current = snapshot(service)
        value = current.observation
        assert current.freshness == "current" and current.account is None
        assert value.source == plan.source and value.connection == plan.connection
        assert value.state == "observed" and value.is_available is True
        assert value.balances[0].as_dict() == {"currency": "USD", "total_balance": "12.3400",
            "granted_balance": "0.0000", "topped_up_balance": "12.3400"}
        assert value.as_dict()["windows"] == [] and value.as_dict()["resets_at"] is None
        assert KEY not in json.dumps(current.as_dict()) and KEY not in repr(plan)
        assert calls == [(BALANCE_ENDPOINT, KEY)] and published.calls[0][2] is True
        collector.stop()
        collector.stop()
        assert not collector.running and snapshot(service).freshness == "missing"
    finally:
        finish(collector)


@pytest.mark.parametrize("error, reason", [
    (QuotaFetchError("unauthorized"), "not_authenticated"),
    (QuotaFetchError("invalid_payload"), "malformed_payload"),
    (QuotaFetchError("rate_limited"), "source_error"),
    (RuntimeError("private exception " + KEY), "source_error"),
])
def test_newer_error_replaces_success_without_exception_text(monkeypatch, error, reason):
    service, plan = QuotaService(), ready()
    published = Publications(monkeypatch, service, 2)
    error_entered, allow_error = Event(), Event()
    now, calls = [AT], []

    def fetch(endpoint, bearer):
        calls.append((endpoint, bearer))
        if len(calls) == 1:
            return balance()
        error_entered.set()
        if not allow_error.wait(WAIT):
            raise RuntimeError("controlled error fetch was not released")
        raise error

    collector = collectors.QuotaCollector(service, (plan,), fetch=fetch,
        clock=lambda: now[0], interval_seconds=1)
    try:
        collector.start()
        assert published.events[0].wait(WAIT)
        assert snapshot(service).observation.state == "observed"
        assert error_entered.wait(WAIT)
        now[0] = AT + timedelta(seconds=1)
        allow_error.set()
        assert published.events[1].wait(WAIT)
        current = snapshot(service, at=now[0])
        assert current.observation.state == "error" and current.observation.reason == reason
        assert current.observation.balances == () and current.observation.is_available is None
        assert current.observation.observed_at == now[0] and current.freshness == "current"
        assert KEY not in json.dumps(current.as_dict())
        assert all(call[2] is True for call in published.calls[:2])
        collector.stop()
    finally:
        finish(collector, allow_error)


def test_malformed_native_money_is_an_error_not_a_partial_balance(monkeypatch):
    service, plan = QuotaService(), ready()
    published = Publications(monkeypatch, service)
    bad = balance()
    bad["balance_infos"].append({"currency": "USD", "total_balance": KEY})
    collector = collectors.QuotaCollector(service, (plan,),
        fetch=lambda *args: bad, clock=lambda: AT)
    try:
        collector.start()
        assert published.events[0].wait(WAIT)
        value = snapshot(service).observation
        assert value.state == "error" and value.reason == "malformed_payload"
        assert value.balances == () and KEY not in json.dumps(value.as_dict())
        collector.stop()
    finally:
        finish(collector)


def test_stop_retires_blocked_fetch_ticket_then_waits_for_actual_worker_exit(monkeypatch):
    service, plan, fetch = QuotaService(), ready(), BlockedFetch()
    retired, stopped, errors = Event(), Event(), []
    actual_retire = service.retire

    def retire(ticket):
        result = actual_retire(ticket)
        retired.set()
        return result

    monkeypatch.setattr(service, "retire", retire)
    collector = collectors.QuotaCollector(service, (plan,), fetch=fetch, clock=lambda: AT)
    ticket = collector._work[0][1]

    def stop():
        try:
            collector.stop()
        except BaseException as error:
            errors.append(error)
        finally:
            stopped.set()

    stopper = Thread(target=stop, name="test-quota-stop", daemon=True)
    try:
        collector.start()
        assert fetch.entered.wait(WAIT)
        joining, timeouts = watch_join(monkeypatch, collector._thread)
        stopper.start()
        assert retired.wait(WAIT), "stop did not invalidate the ticket before joining"
        assert joining.wait(WAIT), "stop never joined its live worker"
        assert timeouts == [None], "collector retirement must wait for actual exit"
        assert snapshot(service).freshness == "missing"
        assert not service.publish(ticket, observation(plan), now=AT)
        assert collector.running and not stopped.is_set(), "stop returned while fetch was blocked"
        fetch.release.set()
        assert stopped.wait(WAIT), "stop did not finish after actual fetch exit"
        stopper.join(WAIT)
        assert not stopper.is_alive() and not errors and not collector.running
        assert snapshot(service).freshness == "missing" and len(fetch.calls) == 1
        collector.stop()
    finally:
        finish(collector, fetch.release)
        if stopper.ident is not None:
            stopper.join(WAIT)
            assert not stopper.is_alive()


def test_old_collector_stop_preserves_successor_binding_and_its_published_money():
    service, first, successor = QuotaService(), ready(key="old-key"), ready(key="new-key")
    fetch = BlockedFetch(balance("1.00"))
    collector = collectors.QuotaCollector(service, (first,), fetch=fetch, clock=lambda: AT)
    old_ticket = collector._work[0][1]
    try:
        collector.start()
        assert fetch.entered.wait(WAIT)
        next_ticket = seed(service, successor, total="99.00")
        fetch.release.set()
        collector.stop()
        collector.stop()
        current = snapshot(service)
        assert current.observation.connection == successor.connection
        assert current.observation.balances[0].total_balance == "99.00"
        assert not service.retire(old_ticket)
        assert service.publish(next_ticket, observation(successor, total="99.00"), now=AT)
        assert not collector.running and fetch.calls == [(BALANCE_ENDPOINT, "old-key")]
    finally:
        finish(collector, fetch.release)


@pytest.mark.parametrize("kind", ["wrong-type", "duplicate", "corrupt-plan", "not-tuple"])
def test_invalid_plan_batch_cannot_partially_clear_an_existing_binding(kind):
    service, existing = QuotaService(), ready()
    ticket = seed(service, existing)
    replacement = ready()
    plans = (replacement, object())
    if kind == "duplicate":
        plans = (replacement, ready())
    elif kind == "corrupt-plan":
        corrupt = ready("other")
        object.__setattr__(corrupt, "source", QuotaSource(QUOTA_POLICY, "wrong-version"))
        plans = (replacement, corrupt)
    elif kind == "not-tuple":
        plans = [replacement]
    with pytest.raises((ValueError, QuotaError)):
        collectors.QuotaCollector(service, plans,
            fetch=lambda *args: pytest.fail("unexpected fetch"))
    current = snapshot(service)
    assert current.connection == existing.connection
    assert current.observation.balances[0].total_balance == "12.3400"
    assert service.publish(ticket, observation(existing), now=AT)


@pytest.mark.parametrize("reason", [
    None, "no_data", "not_supported", "source_error", "supplier-error"])
def test_absent_or_unavailable_plans_never_fetch_or_start_a_worker(reason):
    service, calls = QuotaService(), []
    plans = ()
    if reason == "supplier-error":
        plans = (ProviderQuotaPlan("dsh", reason="source_error"),)
    elif reason is not None:
        request = replace(ready().request, bearer=None, reason=reason)
        plans = (ProviderQuotaPlan("dsh", request,
            QuotaSource(QUOTA_POLICY, BALANCE_SOURCE_VERSION), reason=reason),)
    collector = collectors.QuotaCollector(service, plans,
        fetch=lambda *args: calls.append(args), clock=lambda: AT)
    try:
        collector.start()
        assert collector._thread is None and not collector.running and calls == []
        collector.stop()
        collector.stop()
        assert snapshot(service).freshness == "missing"
    finally:
        finish(collector)
