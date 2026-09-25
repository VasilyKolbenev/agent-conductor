"""Continuous in-process T5 over actual fake harness writes and an independent checker.

The first witness uses only pre-existing imports and real transports, so tests.patch
alone can reproduce the gap before implementation.patch is applied. No fake Human
decision is supplied by production: the fixture explicitly confirms its own runs.
"""
import threading

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.harness_workspace import HarnessWorkspace, _root_gate
from conductor.command.contracts import (
    ActionProposal, ActionResultReceipt, DecisionReceipt, RunEnvelope)
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import CorruptRun, RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, ControlRuntime, ExecutionError
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests import _fakeclaude, _fakecodex
from tests.test_command_claude_transport import a_harness, NOW, _Ids
from tests.test_command_codex_transport import a_harness as codex_harness
from tests.test_command_runtime_authorize import (
    a_budget, a_confirmation, a_store, a_proposal, counting_ids)
from tests.test_command_runtime_execute import ScriptedAdapter


WAIT = 30.0
PROBE = 0.15


def _thread(name, call, results):
    def invoke():
        try:
            results[name] = call()
        except BaseException as error:
            results[name] = error
    worker = threading.Thread(target=invoke, name=name, daemon=True)
    worker.start()
    return worker


class _WatchedLock:
    """Observe an attempted entry; delegate locking to the actual existing RLock."""
    def __init__(self, lock, waiting):
        self.lock, self.waiting = lock, waiting
        self.entered = threading.Event()

    def acquire(self, *args, **kwargs):
        if threading.current_thread().name == "scope-b":
            self.waiting.set()
        acquired = self.lock.acquire(*args, **kwargs)
        if acquired and threading.current_thread().name == "scope-b":
            self.entered.set()
        return acquired

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
        return False


def _two_runs(tmp_path, *, reject=False, authorize=True):
    doer, root, do_log = a_harness(tmp_path / "doer",
        **{_fakeclaude.WRITE_FILE: "result.txt:done"})
    verdict = "enabled-verdict-reject" if reject else "enabled-verdict-accept"
    checker, _, check_log = codex_harness(
        tmp_path / "checker", root=root, **{_fakecodex.EMIT_VERDICT: verdict})
    config = {"cycle": {"id": "t5", "phases": ["implement", "review"]},
              "instances": [{"id": "doer", "adapter": doer.manifest.adapter_id},
                            {"id": "checker", "adapter": checker.manifest.adapter_id}],
              "task": {"id": "task-shared", "work_scope": "task-shared"}}
    TaskStore(root).create_task(TaskRecord("task-shared", "One task, two runs", "task-shared", NOW))
    store = RunStore(root)
    registry = AdapterRegistry([doer, checker])
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=_Ids())
    authorizations = {}
    for suffix in ("a", "b"):
        run_id = f"run-{suffix}"
        store.create_run(RunEnvelope(run_id=run_id, cycle_id="t5", created_at=NOW,
            config_digest=snapshot_digest(config), mode="confirm"), config)
        arguments = {"work_item_id": f"item-{suffix}", "work_scope": "task-shared",
                     "instruction_ref": "instr-001", "profile": "implement",
                     "artifact_refs": [], "output_limit_profile": "small"}
        store.append(GraphDefinition(graph_id=f"graph-{suffix}", run_id=run_id, created_at=NOW,
            nodes=(GraphNode(node_id="confirm", kind="gate", title="Human", gate_id="confirm-gate"),
                   GraphNode(node_id="do", kind="task", title="Do", instance_id="doer",
                             capability="dispatch", arguments=arguments,
                             verifier_instance_id="checker")),
            edges=(GraphEdge(from_node="confirm", to_node="do"),)))
        store.append(DecisionReceipt(
            receipt_id=f"gate-{suffix}", run_id=run_id, gate_id="confirm-gate",
            action="approve", actor="owner", decided_at=NOW, reason="Run this test action",
            scope_refs=("work",), config_digest=snapshot_digest(config)))
        proposal = ActionProposal(proposal_id=f"proposal-{suffix}", run_id=run_id,
            attempt_id=f"attempt-{suffix}", instance_id="doer", capability="dispatch",
            arguments=arguments, scope=("work",), proposed_by="owner", proposed_at=NOW,
            timeout_seconds=60, rationale="Check independently",
            config_digest=snapshot_digest(config),
            node_id="do", input_binding="proposal-v1")
        store.append(proposal)
        authorizations[suffix] = (runtime.authorize(
            a_confirmation(proposal, confirmed_at=NOW), budget=a_budget())
            if authorize else proposal)
    return runtime, store, doer, checker, authorizations, root, do_log, check_log


def _checked_results(store, results, checker, reject):
    expected = AttemptState.VERIFICATION_FAILED if reject else AttemptState.SUCCEEDED
    for suffix in ("a", "b"):
        attempt = results[f"scope-{suffix}"]
        assert attempt.state is expected, attempt.receipt.detail
        records = store.read(f"run-{suffix}").records
        evidence = [row.value for row in records if row.kind == "evidence"]
        assert len(evidence) == (0 if reject else 1)
        if evidence:
            assert evidence[0].verified_by == checker.manifest.adapter_id
            assert evidence[0].verifier_instance_id == "checker"


@pytest.mark.parametrize("window", ["before-check", "before-finish"])
@pytest.mark.parametrize("reject", [False, True])
def test_two_runs_of_same_task_hold_doer_through_independent_checker_and_terminal(
        tmp_path, monkeypatch, window, reject):
    values = _two_runs(tmp_path, reject=reject)
    runtime, store, doer, checker, auth, root, do_log, check_log = values
    reached, release, waiting = threading.Event(), threading.Event(), threading.Event()
    gate = _root_gate(root.resolve())  # retain the exact gate while instrumenting it
    monkeypatch.setattr(gate, "lock", _WatchedLock(gate.lock, waiting))
    original = runtime._resolve if window == "before-check" else runtime._finish

    def held(request, *args, **kwargs):
        if request.run_id == "run-a":
            reached.set()
            assert release.wait(WAIT), "the test did not release the reached window"
        return original(request, *args, **kwargs)

    monkeypatch.setattr(runtime, "_resolve" if window == "before-check" else "_finish", held)
    results = {}
    first = _thread("scope-a", lambda: runtime.execute(auth["a"]), results)
    second = None
    before = root / "work" / "_tasks" / "task-shared" / "item-a" / "result.txt"
    neighbour = root / "work" / "_tasks" / "task-shared" / "item-b" / "result.txt"
    try:
        assert reached.wait(WAIT), results
        assert before.read_text(encoding="utf-8") == "done", "doer did not actually write"
        assert len(_fakeclaude.prompt_spawns(do_log)) == 1
        second = _thread("scope-b", lambda: runtime.execute(auth["b"]), results)
        assert waiting.wait(WAIT), "B never attempted the actual shared gate"
        assert not gate.lock.entered.wait(PROBE), "B entered L2 while A still held its attempt"
        second.join(PROBE)
        assert second.is_alive(), "B escaped the attempt gate before A finalized"
        assert not neighbour.exists(), "B wrote during A's doer/checker/finalization interval"
        assert not any(row.kind == "action_result" for row in store.read("run-a").records)
    finally:
        release.set()
        first.join(WAIT)
        if second is not None:
            second.join(WAIT)
    assert not first.is_alive() and second is not None and not second.is_alive()
    assert not any(isinstance(value, BaseException) for value in results.values()), results
    _checked_results(store, results, checker, reject)
    assert neighbour.read_text(encoding="utf-8") == "done"
    assert len(_fakeclaude.prompt_spawns(do_log)) == len(_fakecodex.task_spawns(check_log)) == 2
    assert doer._attempts == doer._check_materials == {}


def test_standing_terminal_while_waiting_is_replayed_without_prepare_or_spawn(
        tmp_path, monkeypatch):
    runtime, store, doer, _, auth, root, do_log, check_log = _two_runs(tmp_path)
    waiting = threading.Event()
    gate = _root_gate(root.resolve())
    monkeypatch.setattr(gate, "lock", _WatchedLock(gate.lock, waiting))
    preparations = []
    original = doer.prepare

    def prepare(request):
        preparations.append(request.action_id)
        return original(request)

    monkeypatch.setattr(doer, "prepare", prepare)
    results = {}
    worker = None
    gate.lock.acquire()
    try:
        worker = _thread("scope-b", lambda: runtime.execute(auth["b"]), results)
        assert waiting.wait(WAIT), "execute never reached its gate"
        request = auth["b"].request
        standing = ActionResultReceipt(receipt_id="external-unknown", run_id=request.run_id,
            action_id=request.action_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id,
            outcome="unknown", observed_at=NOW)
        assert store.append(standing), "the competing durable door did not actually append"
    finally:
        gate.lock.release()
        if worker is not None:
            worker.join(WAIT)
    assert worker is not None and not worker.is_alive()
    assert preparations == [], "prepare used the pre-wait grant snapshot"
    assert _fakeclaude.prompt_spawns(do_log) == _fakecodex.task_spawns(check_log) == []
    assert results["scope-b"].receipt == standing, results
    assert not (root / "work" / "_tasks" / "task-shared" / "item-b").exists()


def test_direct_transport_still_waits_on_the_runtime_attempts_existing_gate(tmp_path, monkeypatch):
    runtime, _, doer, _, auth, root, do_log, _ = _two_runs(tmp_path)
    reached, release, waiting = threading.Event(), threading.Event(), threading.Event()
    gate = _root_gate(root.resolve())
    monkeypatch.setattr(gate, "lock", _WatchedLock(gate.lock, waiting))
    original = runtime._resolve

    def held(request, *args, **kwargs):
        if request.run_id == "run-a":
            reached.set()
            assert release.wait(WAIT)
        return original(request, *args, **kwargs)

    monkeypatch.setattr(runtime, "_resolve", held)
    results = {}
    first = _thread("scope-a", lambda: runtime.execute(auth["a"]), results)
    direct = None
    neighbour = root / "work" / "_tasks" / "task-shared" / "item-b" / "result.txt"
    try:
        assert reached.wait(WAIT), results
        direct = _thread("scope-b", lambda: doer.execute(doer.prepare(auth["b"].request)), results)
        assert waiting.wait(WAIT)
        assert not gate.lock.entered.wait(PROBE), (
            "direct transport bypassed the shared runtime hold")
        assert not neighbour.exists()
    finally:
        release.set()
        first.join(WAIT)
        if direct is not None:
            direct.join(WAIT)
        doer.release(auth["b"].request)
    assert not first.is_alive() and direct is not None and not direct.is_alive()
    assert not any(isinstance(value, BaseException) for value in results.values()), results
    assert results["scope-a"].state is AttemptState.SUCCEEDED
    # Observed only; direct doer never claims verified.
    assert results["scope-b"].outcome == "succeeded"
    assert neighbour.read_text(encoding="utf-8") == "done"
    assert len(_fakeclaude.prompt_spawns(do_log)) == 2


def _scripted(tmp_path, *, acquire=None, release=None):
    from conductor.command.adapters.attempt_scope import AttemptScope
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    workspace = HarnessWorkspace.at(tmp_path, home_dir=".fake-home", marker_dir=".fake-markers")
    held = workspace.attempt_scope()
    adapter.attempt_scope = AttemptScope(
        held.resource, acquire or held.acquire, release or held.release)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=counting_ids())
    proposal = a_proposal(store)
    auth = runtime.authorize(a_confirmation(proposal, confirmed_at=NOW), budget=a_budget())
    return store, adapter, workspace, runtime, auth


def test_interrupted_acquire_consumes_grant_and_clears_entry_state_without_release(tmp_path):
    calls = []

    def interrupted():
        calls.append("acquire")
        raise KeyboardInterrupt("synthetic before lock acquisition")

    _, adapter, _, runtime, auth = _scripted(
        tmp_path, acquire=interrupted, release=lambda: calls.append("release"))
    with pytest.raises(KeyboardInterrupt):
        runtime.execute(auth)
    with pytest.raises(ExecutionError, match="no live execution grant"):
        runtime.execute(auth)
    assert calls == ["acquire"]
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    reconciled = runtime.reconcile(auth.request.run_id, auth.request.action_id)
    assert reconciled.state is AttemptState.UNKNOWN


@pytest.mark.parametrize("answer", [False, None, 1, "acquired"])
def test_acquire_must_explicitly_confirm_holding_before_any_adapter_seam(tmp_path, answer):
    calls = []
    _, adapter, _, runtime, auth = _scripted(
        tmp_path, acquire=lambda: answer, release=lambda: calls.append("release"))
    with pytest.raises(ExecutionError, match="did not confirm acquisition"):
        runtime.execute(auth)
    assert calls == []
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    with pytest.raises(ExecutionError, match="no live execution grant"):
        runtime.execute(auth)


def test_reentrant_notify_refuses_before_another_runtime_can_take_operation_lock(tmp_path):
    store, adapter, _, runtime, auth = _scripted(tmp_path)
    other = ControlRuntime(store, runtime._registry, clock=lambda: NOW, ids=counting_ids())
    refusals = []

    def notify(run_id):
        for target in (runtime, other):
            try:
                target.execute(auth)
            except ExecutionError as error:
                refusals.append(str(error))

    runtime._notify = notify
    results = {}
    worker = _thread("scope-a", lambda: runtime.execute(auth), results)
    worker.join(WAIT)
    assert not worker.is_alive(), "reentrant notify deadlocked on L1"
    assert not isinstance(results["scope-a"], BaseException), results
    assert len(refusals) == 6 and all("attempt scope" in value for value in refusals)
    assert adapter.execute_calls == 1


def test_changed_frozen_bytes_during_wait_refuse_before_prepare(tmp_path, monkeypatch):
    store, adapter, _, runtime, auth = _scripted(tmp_path)
    waiting = threading.Event()
    gate = _root_gate(tmp_path.resolve())
    monkeypatch.setattr(gate, "lock", _WatchedLock(gate.lock, waiting))
    results = {}
    worker = None
    journal = store.run_path(auth.request.run_id) / "records.jsonl"
    journal_before = journal.read_bytes()
    gate.lock.acquire()
    try:
        worker = _thread("scope-b", lambda: runtime.execute(auth), results)
        assert waiting.wait(WAIT)
        config = store.run_path(auth.request.run_id) / "config.json"
        original = config.read_bytes()
        config.write_bytes(original + b"corrupt")
    finally:
        gate.lock.release()
        if worker is not None:
            worker.join(WAIT)
    assert worker is not None and not worker.is_alive()
    assert isinstance(results["scope-b"], CorruptRun), results
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    assert journal.read_bytes() == journal_before, (
        "waiting execution appended after corrupt frozen state")


def test_managed_other_root_continues_while_this_root_waits(tmp_path, monkeypatch):
    _, adapter, _, runtime, auth = _scripted(tmp_path / "one")
    _, unrelated, _, other, other_auth = _scripted(tmp_path / "two")
    waiting = threading.Event()
    gate = _root_gate((tmp_path / "one").resolve())
    monkeypatch.setattr(gate, "lock", _WatchedLock(gate.lock, waiting))
    results = {}
    pending = independent = None
    gate.lock.acquire()
    try:
        pending = _thread("scope-b", lambda: runtime.execute(auth), results)
        assert waiting.wait(WAIT)
        independent = _thread("unrelated", lambda: other.execute(other_auth), results)
        independent.join(WAIT)
        assert not independent.is_alive(), "an unrelated root was serialized behind this root"
        assert unrelated.prepare_calls == unrelated.execute_calls == unrelated.verify_calls == 1
        assert results["unrelated"].state is AttemptState.VERIFICATION_FAILED
        assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    finally:
        gate.lock.release()
        if pending is not None:
            pending.join(WAIT)
        if independent is not None:
            independent.join(WAIT)
    assert pending is not None and not pending.is_alive()
    assert results["scope-b"].state is AttemptState.VERIFICATION_FAILED


def test_different_declared_resources_refuse_before_acquiring_either(tmp_path):
    from conductor.command.adapters.attempt_scope import AttemptScope
    from tests.test_command_independent_runtime import circuit
    _, doer, checker, _, runtime, proposal = circuit(tmp_path)
    calls = []

    def acquire():
        calls.append("acquire")
        return True

    doer.attempt_scope = AttemptScope(object(), acquire, lambda: calls.append("release"))
    checker.attempt_scope = AttemptScope(object(), acquire, lambda: calls.append("release"))
    runtime._registry = AdapterRegistry([doer, checker])
    auth = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    with pytest.raises(ExecutionError, match="different shared resources"):
        runtime.execute(auth)
    assert calls == []
    assert doer.prepare_calls == doer.execute_calls == doer.verify_calls == 0
    assert checker.independent_calls == []
    with pytest.raises(ExecutionError, match="no live execution grant"):
        runtime.execute(auth)


def test_execute_exception_finalizes_unknown_and_releases_for_another_thread(tmp_path):
    store, adapter, _, runtime, auth = _scripted(tmp_path)
    adapter._execute_raises = True
    failed = runtime.execute(auth)
    assert failed.state is AttemptState.UNKNOWN
    adapter._execute_raises = False
    next_proposal = a_proposal(store, proposal_id="proposal-next", attempt_id="attempt-next")
    next_auth = runtime.authorize(
        a_confirmation(next_proposal, confirmed_at=NOW), budget=a_budget())
    results = {}
    worker = _thread("scope-b", lambda: runtime.execute(next_auth), results)
    worker.join(WAIT)
    assert not worker.is_alive(), "failed attempt retained the actual RLock"
    assert results["scope-b"].state is AttemptState.VERIFICATION_FAILED, results
    assert adapter.execute_calls == 2
