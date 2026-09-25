"""Actual pre-bootstrap thread and hosted server cleanup under startup failure."""
from threading import Event, Thread

import pytest

from conductor import quota_collectors as collectors, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.quota_service import QuotaService
from tests.test_quota_collectors import AT, WAIT, ready, snapshot
from tests.test_store import good_lane, write_project


class InterruptedStart(BaseException):
    pass


class BeforeBootstrap:
    """Hold a real native thread before Python Thread records its ident."""
    def __init__(self, monkeypatch):
        self.entered, self.release, self.done = Event(), Event(), Event()
        self.workers = []
        self.monkeypatch = monkeypatch

    def factory(self, **kwargs):
        worker = Thread(**kwargs)
        original_bootstrap, original_wait = worker._bootstrap, worker._started.wait
        def bootstrap():
            self.entered.set()
            try:
                assert self.release.wait(WAIT), 'fixture did not release bootstrap'
                original_bootstrap()
            finally:
                self.done.set()
        def wait(timeout=None):
            assert self.entered.wait(WAIT), 'native bootstrap did not start'
            worker._started.wait = original_wait
            raise InterruptedStart('interrupted during native bootstrap acknowledgment')
        self.monkeypatch.setattr(worker, '_bootstrap', bootstrap)
        self.monkeypatch.setattr(worker._started, 'wait', wait)
        self.workers.append(worker)
        return worker

    def finish(self):
        self.release.set()
        assert self.done.wait(WAIT), 'native bootstrap did not exit'
        for worker in self.workers:
            worker.join(WAIT)
            assert not worker.is_alive()


def test_native_thread_before_ident_is_pending_then_joins_without_any_fetch(monkeypatch):
    cache, calls = QuotaService(), []
    held = BeforeBootstrap(monkeypatch)
    monkeypatch.setattr(collectors, 'Thread', held.factory)
    collector = collectors.QuotaCollector(cache, (ready(),),
        fetch=lambda *args: calls.append(args), clock=lambda: AT)
    try:
        with pytest.raises(InterruptedStart):
            collector.start()
        worker = held.workers[0]
        assert held.entered.is_set() and worker.ident is None and not held.done.is_set()
        with pytest.raises(collectors.QuotaStartupUncertain, match='retirement is unconfirmed'):
            collector.stop()
        assert collector._thread is worker and snapshot(cache).freshness == 'missing'
        assert calls == []
    finally:
        held.finish()
        collector.stop()
    assert calls == [] and not collector.running


class UncertainCollector:
    def __init__(self, *, start_fails):
        self.start_fails = start_fails
        self.stops = 0

    def start(self):
        if self.start_fails:
            raise InterruptedStart('original startup failure')

    def stop(self):
        self.stops += 1
        raise collectors.QuotaStartupUncertain('quota worker retirement is unconfirmed')


def test_failed_server_start_closes_watcher_socket_and_workers_preserving_both_errors(tmp_path, monkeypatch):
    root = write_project(tmp_path, lanes={'claude': good_lane()})
    pending, captured = UncertainCollector(start_fails=True), []
    original = server.ConductServer._start_command
    def start_command(subject, *args):
        captured.append(subject)
        return original(subject, *args)
    monkeypatch.setattr(server, 'QuotaCollector', lambda *a, **kw: pending)
    monkeypatch.setattr(server.ConductServer, '_start_command', start_command)
    with pytest.raises(collectors.QuotaStartupUncertain) as caught:
        server.build(root, 0, registry=AdapterRegistry())
    subject = captured[0]
    assert isinstance(caught.value.__context__, InterruptedStart)
    assert not subject.watcher.is_alive() and subject.socket.fileno() == -1
    assert subject.command_execution.owned_tokens() == () and pending.stops == 1


def test_shutdown_finishes_http_loop_even_when_quota_retirement_remains_pending(tmp_path, monkeypatch):
    root = write_project(tmp_path, lanes={'claude': good_lane()})
    pending = UncertainCollector(start_fails=False)
    monkeypatch.setattr(server, 'QuotaCollector', lambda *a, **kw: pending)
    subject = server.build(root, 0, registry=AdapterRegistry())
    serving = Thread(target=subject.serve_forever, daemon=True)
    serving.start()
    try:
        with pytest.raises(collectors.QuotaStartupUncertain):
            subject.shutdown()
        serving.join(WAIT)
        assert not serving.is_alive()
    finally:
        with pytest.raises(collectors.QuotaStartupUncertain):
            subject.server_close()
    assert not subject.watcher.is_alive() and subject.socket.fileno() == -1
    assert subject.command_execution.owned_tokens() == ()
