"""Process-local RT-2 serialization holds one logical durable transition."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

import conductor.command.run_store as run_store_module
from conductor.command.run_store import RunStore
from conductor.command.runtime import AttemptState, ExecutionError

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
                barrier.wait(timeout=0.5)
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


def test_different_actions_overlap_instead_of_taking_one_global_lock(
        tmp_path, monkeypatch):
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
    adapters = (ScriptedAdapter(), ScriptedAdapter())
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
    assert witness == [True, True]
    recovered = RunStore(tmp_path).read("run-001")
    assert sum(row.kind == "action_result" for row in recovered.records) == 2
