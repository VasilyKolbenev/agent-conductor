"""Real HTTP confirmations, server workers and native fake doer/checker under T5.

Fixtures confirm their own proposals. Production never manufactures a Human
decision. Barriers hold actual doer/checker/finalization intervals, not sleep as
a substitute for proving that the second worker reached the shared resource.
"""
import threading

import pytest

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.harness_workspace import _root_gate
from tests import _fakeclaude, _fakecodex
from tests.test_command_attempt_scope_runtime import _two_runs, WAIT, PROBE
from tests.test_command_claude_transport import NOW, _Ids
from tests.test_command_http_api import TOKEN, confirm_body
from tests.test_command_runtime_authorize import a_budget
from tests.test_server_command_http import _request
from tests.test_store import good_lane, write_project


class ObservedGate:
    def __init__(self, native):
        self.native = native
        self.waiting, self.entered = threading.Event(), threading.Event()

    def acquire(self, *args, **kwargs):
        second = threading.current_thread().name == "http-run-b"
        if second:
            self.waiting.set()
        acquired = self.native.acquire(*args, **kwargs)
        if second and acquired:
            self.entered.set()
        return acquired

    def release(self):
        self.native.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
        return False


class HostedAttempt:
    def __init__(self, tmp_path, monkeypatch, *, window, reject):
        values = _two_runs(tmp_path, reject=reject, authorize=False)
        _, self.store, self.doer, self.checker, self.proposals, self.root, self.do_log, self.check_log = values
        write_project(self.root, lanes={"claude": good_lane()})
        self.subject = server.build(self.root, 0,
            registry=AdapterRegistry([self.doer, self.checker]), budget=a_budget(),
            clock=lambda: NOW, ids=_Ids(), token_factory=lambda _: TOKEN)
        self.reached, self.release = threading.Event(), threading.Event()
        self.gate = _root_gate(self.root.resolve())
        monkeypatch.setattr(self.gate, "lock", ObservedGate(self.gate.lock))
        self._instrument(monkeypatch, window)
        self.thread = threading.Thread(target=self.subject.serve_forever, daemon=True)
        self.thread.start()

    def _instrument(self, monkeypatch, window):
        runtime = self.subject.command_api.runtime
        execute = runtime.execute
        original = runtime._resolve if window == "before-check" else runtime._finish

        def named(authorization):
            worker = threading.current_thread()
            old_name = worker.name
            worker.name = "http-" + authorization.request.run_id
            try:
                return execute(authorization)
            finally:
                worker.name = old_name

        def held(request, *args, **kwargs):
            if request.run_id == "run-a":
                self.reached.set()
                assert self.release.wait(WAIT), "fixture did not release A"
            return original(request, *args, **kwargs)

        monkeypatch.setattr(runtime, "execute", named)
        monkeypatch.setattr(runtime, "_resolve" if window == "before-check" else "_finish", held)

    def confirm(self, suffix):
        proposal = self.proposals[suffix]
        return _request(self.subject, "POST", f"/command/runs/{proposal.run_id}/actions",
                        confirm_body(proposal.as_dict()))

    def path(self, suffix):
        return self.root / "work" / "_tasks" / "task-shared" / f"item-{suffix}" / "result.txt"

    def finish(self):
        self.release.set()
        idle = self.subject.command_execution.wait_idle(WAIT)
        self.subject.shutdown()
        self.subject.server_close()
        self.thread.join(WAIT)
        assert idle and not self.thread.is_alive()
        assert self.subject.command_execution.owned_tokens() == ()


def assert_checked(flight, reject):
    expected = "verification_failed" if reject else "succeeded"
    for suffix in ("a", "b"):
        status, body, _ = _request(flight.subject, "GET", f"/command/runs/run-{suffix}")
        assert status == 200
        receipts = [row["record"] for row in body["records"] if row["record_type"] == "action_result"]
        evidence = [row["record"] for row in body["records"] if row["record_type"] == "evidence"]
        assert len(receipts) == 1 and receipts[0]["outcome"] == expected
        assert len(evidence) == (0 if reject else 1)
        if evidence:
            assert evidence[0]["verified_by"] == flight.checker.manifest.adapter_id
            assert evidence[0]["verifier_instance_id"] == "checker"
        assert flight.path(suffix).read_text(encoding="utf-8") == "done"
    assert len(_fakeclaude.prompt_spawns(flight.do_log)) == 2
    assert len(_fakecodex.task_spawns(flight.check_log)) == 2
    assert flight.doer._attempts == flight.doer._check_materials == {}


@pytest.mark.parametrize("window", ["before-check", "before-finish"])
@pytest.mark.parametrize("reject", [False, True])
def test_http_workers_hold_t5_and_duplicate_confirmation_never_queues_twice(
        tmp_path, monkeypatch, window, reject):
    flight = HostedAttempt(tmp_path, monkeypatch, window=window, reject=reject)
    try:
        first = flight.confirm("a")
        assert first[0] == 201, first[1]
        assert flight.reached.wait(WAIT), "A never reached its held interval"
        assert flight.path("a").read_text(encoding="utf-8") == "done"
        second = flight.confirm("b")
        assert second[0] == 201, second[1]
        assert flight.gate.lock.waiting.wait(WAIT), "B never reached the shared gate"
        assert not flight.gate.lock.entered.wait(PROBE), "HTTP B entered before A finalized"
        assert not flight.path("b").exists(), "HTTP B wrote in A's held interval"
        assert not any(row.kind == "action_result" for row in flight.store.read("run-a").records)
        retry = flight.confirm("b")
        assert retry[:2] == (200, second[1])
        assert flight.subject.command_execution.placements() == 2
        flight.release.set()
        assert flight.subject.command_execution.wait_idle(WAIT)
        assert flight.subject.command_execution.refusals() == ()
        assert_checked(flight, reject)
    finally:
        flight.finish()
