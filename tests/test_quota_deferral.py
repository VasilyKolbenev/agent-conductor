"""Codex ruling J (23.09.2026): a busy harness root defers a quota update.

The deferral is not an error and not a new reading: the last observation keeps its own time, age
and resets; a newer error is never covered by an older success; a rebinding shows nothing of
another generation; a window past its own reset is not a current remainder.
"""
from datetime import timedelta
from threading import Thread

import pytest

from conductor.command.adapters import subscription_quota as native
from conductor.command.quota import QuotaError
from conductor.command.quota_plans import quota_plan_for
from conductor.command.quota_service import QuotaService
from conductor.quota_collectors import QuotaCollector
from tests.test_subscription_quota import AT, adapter

AGE = timedelta(minutes=5)


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(native, "ROOT_WAIT_SECONDS", 0.3)
    value, runner, _ = adapter(tmp_path)
    service, clock = QuotaService(), [AT]
    collector = QuotaCollector(service, (quota_plan_for("codex-cli", value),), clock=lambda: clock[0])
    plan, ticket = collector._work[0]
    return value, runner, service, clock, collector, plan, ticket


def _busy(value, collector, plan, ticket, times=1):
    """Collect on another thread while this one holds the root, as a running step does."""
    with value._workspace.owned():
        for _ in range(times):
            worker = Thread(target=collector._collect, args=(plan, ticket), daemon=True)
            worker.start()
            worker.join(10)
            assert not worker.is_alive()


def _snap(service, at):
    return service.snapshot("codex-cli", now=at, max_age=AGE)


def test_a_busy_root_defers_the_update_and_keeps_the_last_reading_with_its_own_time(tmp_path, monkeypatch):
    value, runner, service, clock, collector, plan, ticket = _setup(tmp_path, monkeypatch)
    collector._collect(plan, ticket)
    first = _snap(service, AT)
    assert first.observation.state == "observed" and first.deferred_at is None
    spawned, published, real = len(runner.specs), [], service.publish
    monkeypatch.setattr(service, "publish", lambda *a, **k: published.append(a) or real(*a, **k))
    clock[0] = AT + timedelta(minutes=1)
    _busy(value, collector, plan, ticket, times=2)
    busy = _snap(service, clock[0])
    assert published == [] and len(runner.specs) == spawned, "nothing read, nothing re-recorded"
    assert busy.observation == first.observation and busy.deferred_at == clock[0]
    body, before = busy.as_dict(), first.as_dict()
    assert body["state"] == "observed" and body["observed_at"] == before["observed_at"]
    assert body["deferred_at"] == "2026-09-21T16:01:00Z" and body["windows"] == [
        {**window, "freshness": "current"} for window in before["windows"]]
    clock[0] = AT + timedelta(minutes=2)
    collector._collect(plan, ticket)
    assert _snap(service, clock[0]).deferred_at is None, "a completed read ends the deferral"


def test_a_deferral_never_brings_back_an_older_success_over_a_newer_error(tmp_path, monkeypatch):
    value, runner, service, clock, collector, plan, ticket = _setup(tmp_path, monkeypatch)
    collector._collect(plan, ticket)
    success = _snap(service, AT).observation
    runner.payload = b"not a native transcript"
    clock[0] = AT + timedelta(minutes=1)
    collector._collect(plan, ticket)
    clock[0] = AT + timedelta(minutes=2)
    _busy(value, collector, plan, ticket)
    row = _snap(service, clock[0])
    assert row.observation.state == "error" and row.observation.windows == ()
    assert row.deferred_at == clock[0]
    assert service.publish(ticket, success, now=clock[0]) is False


def test_a_rebinding_shows_nothing_of_the_old_generation_and_an_invalid_rebind_changes_nothing(tmp_path, monkeypatch):
    value, runner, service, clock, collector, plan, ticket = _setup(tmp_path, monkeypatch)
    collector._collect(plan, ticket)
    old = _snap(service, AT).observation
    clock[0] = AT + timedelta(minutes=1)
    _busy(value, collector, plan, ticket)
    assert _snap(service, clock[0]).deferred_at == clock[0]
    with pytest.raises(QuotaError):
        service.bind("codex-cli", None, plan.source)
    kept = _snap(service, clock[0])
    assert kept.observation == old and kept.deferred_at == clock[0], "an invalid rebind has no side effect"
    fresh = service.bind("codex-cli", None, plan.source, connection=plan.connection)
    moved = _snap(service, clock[0])
    assert moved.observation is None and moved.deferred_at is None
    assert service.defer(ticket, now=clock[0]) is False and service.publish(ticket, old, now=clock[0]) is False
    assert _snap(service, clock[0]).deferred_at is None
    assert service.defer(fresh, now=clock[0]) is True
    service.unbind("codex-cli")
    assert _snap(service, clock[0]).deferred_at is None


def test_an_aging_deferred_reading_turns_stale_and_a_passed_reset_is_never_a_remainder(tmp_path, monkeypatch):
    value, runner, service, clock, collector, plan, ticket = _setup(tmp_path, monkeypatch)
    collector._collect(plan, ticket)
    clock[0] = AT + timedelta(minutes=1)
    _busy(value, collector, plan, ticket)
    young = _snap(service, AT + timedelta(minutes=4)).as_dict()
    assert young["freshness"] == "current" and young["windows"][0]["freshness"] == "current"
    old = _snap(service, AT + AGE).as_dict()
    assert old["freshness"] == "stale" and old["windows"][0]["freshness"] == "stale"
    assert old["windows"][0]["used_percent"] == 27 and old["observed_at"] == "2026-09-21T16:00:00Z"
    assert old["deferred_at"] == "2026-09-21T16:01:00Z"
    past = _snap(service, AT + timedelta(hours=1)).as_dict()
    assert past["freshness"] == "stale" and past["windows"][0]["freshness"] == "reset_passed"
    assert past["windows"][0]["used_percent"] == 27, "the fact is kept; only its reading changes"


def test_an_equal_native_re_read_after_a_deferral_ends_it_without_restamping(tmp_path, monkeypatch):
    value, runner, service, clock, collector, plan, ticket = _setup(tmp_path, monkeypatch)
    collector._collect(plan, ticket)
    same = _snap(service, AT).observation
    assert service.defer(ticket, now=AT + timedelta(minutes=1)) is True
    assert service.publish(ticket, same, now=AT + timedelta(minutes=2)) is True
    row = _snap(service, AT + timedelta(minutes=2))
    assert row.deferred_at is None and row.observation.observed_at == AT



def test_a_completed_read_after_a_clock_rollback_still_ends_the_deferral(tmp_path, monkeypatch):
    value, runner, service, clock, collector, plan, ticket = _setup(tmp_path, monkeypatch)
    assert service.defer(ticket, now=AT)
    clock[0] = AT - timedelta(minutes=1)
    real = service.publish
    monkeypatch.setattr(service, "publish", lambda t, o, now: real(t, o, now=AT - timedelta(minutes=2)))
    collector._collect(plan, ticket)
    assert _snap(service, AT).deferred_at is None
