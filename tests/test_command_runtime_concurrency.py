"""Process-local RT-2 serialization holds one logical durable transition."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gc
import threading
import weakref

import pytest

import conductor.command.run_store as run_store_module
import conductor.command.runtime as runtime_module
from conductor.command.run_store import RunStore
from conductor.command.runtime import AttemptState, AuthorizationError, ExecutionError

from tests.test_command_runtime_authorize import (
    a_budget,
    a_confirmation,
    a_proposal,
    a_runtime as confirmation_runtime,
    a_store,
    action_requests,
    counting_ids,
)
from tests.test_command_runtime_execute import ScriptedAdapter, a_runtime, authorized
from tests.test_command_runtime_restart import an_event


def test_operation_gate_identity_survives_waiters_then_idle_key_is_released():
    key = ("execute", "root-test", "run-001", "action-001")
    first = runtime_module._operation_lock(key)
    first_ref = weakref.ref(first)
    entered = threading.Event()
    same_identity = []

    def waiter():
        second = runtime_module._operation_lock(key)
        same_identity.append(second is first)
        with second:
            entered.set()

    with first:
        worker = threading.Thread(target=waiter)
        worker.start()
        worker.join(timeout=0.05)
        assert not entered.is_set()
    worker.join(timeout=3)
    assert same_identity == [True] and entered.is_set()
    del first
    gc.collect()
    assert first_ref() is None
    assert key not in runtime_module._OPERATION_LOCKS


def _race_journal_kind(monkeypatch, kind):
    """Pause two appends at the old check/write gap and report true overlap."""
    original = run_store_module._append_bytes
    barrier = threading.Barrier(2)
    witness: list[bool] = []
    guard = threading.Lock()
    token = f'"record_type":"{kind}"'.encode()

    def racing_append(path, payload):
        if token in payload:
            try:
                barrier.wait(timeout=0.1)
            except threading.BrokenBarrierError:
                overlapped = False
            else:
                overlapped = True
            with guard:
                witness.append(overlapped)
        return original(path, payload)

    monkeypatch.setattr(run_store_module, "_append_bytes", racing_append)
    return witness


@pytest.mark.parametrize("separate_runtimes", [False, True])
def test_duplicate_confirmation_is_one_request_across_process_local_runtimes(
        tmp_path, monkeypatch, separate_runtimes):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    confirmation = a_confirmation(proposal)
    if separate_runtimes:
        runtimes = (
            confirmation_runtime(
                RunStore(tmp_path), ids=lambda purpose: f"{purpose}-one"),
            confirmation_runtime(
                RunStore(tmp_path), ids=lambda purpose: f"{purpose}-two"),
        )
    else:
        runtime = confirmation_runtime(store, ids=counting_ids())
        runtimes = (runtime, runtime)
    witness = _race_journal_kind(monkeypatch, "action_request")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(runtime.authorize, confirmation, budget=a_budget())
            for runtime in runtimes]
        authorizations = [future.result(timeout=3) for future in futures]

    assert authorizations[0].request == authorizations[1].request
    assert len(action_requests(RunStore(tmp_path))) == 1
    assert witness == [False]
    assert RunStore(tmp_path).read("run-001").warnings == ()
    if separate_runtimes:
        class GrantWitness(RuntimeError):
            pass

        reached = []

        def witness_grant(canonical, recovered, grant):
            reached.append(grant)
            raise GrantWitness

        for runtime in runtimes:
            monkeypatch.setattr(runtime, "_execute_granted", witness_grant)
        outcomes = []
        for runtime, authorization in zip(runtimes, authorizations):
            try:
                runtime.execute(authorization)
            except GrantWitness:
                outcomes.append("grant")
            except ExecutionError:
                outcomes.append("refused")
        assert outcomes == ["grant", "refused"] or outcomes == ["refused", "grant"]
        assert reached == [("run-001", authorizations[0].request.action_id)]


def _seed_observed(store, authorization, suffix):
    request = authorization.request
    lease = an_event(
        request, event_id=f"event-lease-{suffix}",
        recovery_ref=f"recovery-{suffix}")
    store.append(lease)
    store.append(an_event(
        request, "execution_observed", event_id=f"event-observed-{suffix}",
        recovery_ref=lease.recovery_ref))


@pytest.mark.parametrize("separate_runtimes", [False, True])
def test_concurrent_observed_recovery_appends_one_terminal_result(
        tmp_path, monkeypatch, separate_runtimes):
    store = a_store(tmp_path)
    _, authorization = authorized(store, ScriptedAdapter())
    _seed_observed(store, authorization, "one")
    if separate_runtimes:
        adapters = (ScriptedAdapter(), ScriptedAdapter())
        runtimes = tuple(
            a_runtime(
                RunStore(tmp_path), adapter,
                ids=lambda purpose, i=index: f"{purpose}-{i}")
            for index, adapter in enumerate(adapters, 1))
    else:
        adapter = ScriptedAdapter()
        runtime = a_runtime(RunStore(tmp_path), adapter, ids=counting_ids())
        adapters = (adapter,)
        runtimes = (runtime, runtime)
    witness = _race_journal_kind(monkeypatch, "action_result")

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(
            lambda runtime: runtime.execute(authorization), runtimes))

    assert attempts[0].receipt == attempts[1].receipt
    assert sum(adapter.verify_calls for adapter in adapters) == 1
    assert sum(adapter.execute_calls for adapter in adapters) == 0
    recovered = RunStore(tmp_path).read("run-001")
    assert sum(row.kind == "action_result" for row in recovered.records) == 1
    assert witness == [False]


@pytest.mark.parametrize("stress_round", range(20))
def test_different_actions_overlap_but_journal_writes_serialize(
        tmp_path, monkeypatch, stress_round):
    assert 0 <= stress_round < 20
    store = a_store(tmp_path)
    runtime = confirmation_runtime(store, ids=counting_ids())
    first = a_proposal(store)
    second = a_proposal(
        store, proposal_id="proposal-002", attempt_id="attempt-002",
        arguments={"handoff": "packet-002"})
    authorizations = (
        runtime.authorize(a_confirmation(first), budget=a_budget()),
        runtime.authorize(a_confirmation(second), budget=a_budget()),
    )
    for index, authorization in enumerate(authorizations, 1):
        _seed_observed(store, authorization, str(index))
    seam = threading.Barrier(2)
    seam_overlap = []

    class OverlapAdapter(ScriptedAdapter):
        def verify(self, request, result):
            try:
                seam.wait(timeout=1)
            except threading.BrokenBarrierError:
                seam_overlap.append(False)
            else:
                seam_overlap.append(True)
            return super().verify(request, result)

    adapters = (OverlapAdapter(), OverlapAdapter())
    runtimes = tuple(
        a_runtime(
            RunStore(tmp_path), adapter,
            ids=lambda purpose, i=index: f"{purpose}-{i}")
        for index, adapter in enumerate(adapters, 1))
    witness = _race_journal_kind(monkeypatch, "action_result")

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [
            future.result(timeout=3) for future in (
                pool.submit(runtimes[0].execute, authorizations[0]),
                pool.submit(runtimes[1].execute, authorizations[1]),
            )]

    assert [attempt.state for attempt in attempts] == [
        AttemptState.SUCCEEDED, AttemptState.SUCCEEDED]
    assert seam_overlap == [True, True]
    assert witness == [False, False]
    recovered = RunStore(tmp_path).read("run-001")
    assert sum(row.kind == "action_result" for row in recovered.records) == 2


def test_concurrent_distinct_proposals_share_one_action_budget_transaction(
        tmp_path, monkeypatch):
    store = a_store(tmp_path)
    proposals = (
        a_proposal(store),
        a_proposal(
            store, proposal_id="proposal-002", attempt_id="attempt-002",
            arguments={"handoff": "packet-002"}),
    )
    runtimes = (
        confirmation_runtime(
            RunStore(tmp_path), ids=lambda purpose: f"{purpose}-one"),
        confirmation_runtime(
            RunStore(tmp_path), ids=lambda purpose: f"{purpose}-two"),
    )
    witness = _race_journal_kind(monkeypatch, "action_request")

    def authorize_one(index):
        return runtimes[index].authorize(
            a_confirmation(proposals[index]), budget=a_budget(max_actions=1))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(authorize_one, index) for index in range(2)]
    results = []
    for future in futures:
        try:
            results.append(future.result(timeout=3))
        except AuthorizationError:
            results.append("refused")

    assert sum(result == "refused" for result in results) == 1
    assert len(action_requests(RunStore(tmp_path))) == 1
    assert witness == [False]
    assert RunStore(tmp_path).read("run-001").warnings == ()


def test_authorize_and_terminal_append_are_both_durable_and_replayable(
        tmp_path, monkeypatch):
    store = a_store(tmp_path)
    first = a_proposal(store)
    first_runtime = confirmation_runtime(store, ids=counting_ids())
    first_authorization = first_runtime.authorize(
        a_confirmation(first), budget=a_budget())
    _seed_observed(store, first_authorization, "one")
    second = a_proposal(
        store, proposal_id="proposal-002", attempt_id="attempt-002",
        arguments={"handoff": "packet-002"})
    second_runtime = confirmation_runtime(
        RunStore(tmp_path), ids=lambda purpose: f"{purpose}-second")
    execution = a_runtime(RunStore(tmp_path), ScriptedAdapter())

    original = run_store_module._append_bytes
    barrier = threading.Barrier(2)
    witness = []

    def racing_writes(path, payload):
        if (b'"record_type":"action_request"' in payload
                or b'"record_type":"action_result"' in payload):
            try:
                barrier.wait(timeout=0.1)
            except threading.BrokenBarrierError:
                witness.append(False)
            else:
                witness.append(True)
        return original(path, payload)

    monkeypatch.setattr(run_store_module, "_append_bytes", racing_writes)
    with ThreadPoolExecutor(max_workers=2) as pool:
        executed = pool.submit(execution.execute, first_authorization)
        authorized = pool.submit(
            second_runtime.authorize, a_confirmation(second), budget=a_budget())
        assert executed.result(timeout=3).state is AttemptState.SUCCEEDED
        second_authorization = authorized.result(timeout=3)

    recovered = RunStore(tmp_path).read("run-001")
    assert any(row.value == second_authorization.request for row in recovered.records)
    assert sum(row.kind == "action_result" for row in recovered.records) == 1
    assert recovered.warnings == ()
    assert witness == [False, False]


def test_separate_project_roots_do_not_share_a_writer_or_action_lock(
        tmp_path, monkeypatch):
    roots = (tmp_path / "one", tmp_path / "two")
    stores = tuple(a_store(root) for root in roots)
    adapters = (ScriptedAdapter(), ScriptedAdapter())
    pairs = tuple(
        authorized(store, adapter) for store, adapter in zip(stores, adapters))
    for index, (store, pair) in enumerate(zip(stores, pairs), 1):
        _seed_observed(store, pair[1], str(index))
    seam = threading.Barrier(2)
    seam_overlap = []

    class RootOverlapAdapter(ScriptedAdapter):
        def verify(self, request, result):
            try:
                seam.wait(timeout=1)
            except threading.BrokenBarrierError:
                seam_overlap.append(False)
            else:
                seam_overlap.append(True)
            return super().verify(request, result)

    runtimes = tuple(
        a_runtime(RunStore(root), RootOverlapAdapter()) for root in roots)
    witness = _race_journal_kind(monkeypatch, "action_result")

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [
            future.result(timeout=3) for future in (
                pool.submit(runtimes[0].execute, pairs[0][1]),
                pool.submit(runtimes[1].execute, pairs[1][1]),
            )]

    assert all(attempt.state is AttemptState.SUCCEEDED for attempt in attempts)
    assert seam_overlap == [True, True]
    assert witness == [True, True]
    for root in roots:
        recovered = RunStore(root).read("run-001")
        assert sum(row.kind == "action_result" for row in recovered.records) == 1
        assert recovered.warnings == ()
