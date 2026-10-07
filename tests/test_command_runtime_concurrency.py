"""Process-local RT-2 serialization holds one logical durable transition.

What is held here is the SHAPE of concurrent durable work: which seams overlap,
which journal writes serialize, and that one logical action leaves exactly one
terminal result. The terminal state itself is incidental to that -- these
scripted adapters expose no verifier, so every attempt below terminates
`verification_failed`, and the runtime never spends `succeeded` on a process
that nothing verified. The counts, the overlaps and the one-result relations are
what these tests are about, and none of them moved.
"""
from __future__ import annotations

from functools import partial
import gc
import inspect
import itertools
from pathlib import Path
import threading
import time
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
from tests import _threadbounds
from tests._threadbounds import (
    _A_SLOW_DURABLE_WRITE,
    _NAMED_BOUNDS,
    _PROBE_WINDOW,
    _RENDEZVOUS_BOUND,
    _RENDEZVOUS_PER_THREAD,
    _RESULT_BOUND,
    _rendezvous_call_sites,
    _run_together,
    _unbounded_lifecycles,
    _unnamed_waits,
    _values,
)

#: Both files the guards below judge. The machinery that supplies them
#: is held to its own rule rather than being the one place exempt.
_GUARDED = (Path(__file__), Path(_threadbounds.__file__))


def test_no_circuit_here_hands_its_threads_to_something_that_waits_unbounded():
    """The lifecycle claim, made structural because the last one was not true.

    `future.result(timeout=...)` inside `with ThreadPoolExecutor(...)` reads
    like a watchdog and is not one. Measured on this machine: a worker sleeping
    1.2 seconds under `result(timeout=0.05)` handed back its TimeoutError in
    0.06s, and the `with` block returned in 1.20s. The executor's exit had
    waited the whole time, and an interpreter-exit hook would have waited again.
    On a real deadlock the remote job hangs, which is precisely what the bound
    was written to prevent.

    So the executor is gone from this module and the threads are daemons, and
    both are asserted about the SOURCE rather than promised in prose. What is
    still not claimed: that abandoned work stops. Python cannot kill a thread.
    A named report is what a reader gets instead of a silent job timeout, and
    that is the whole of it.
    """
    assert _unbounded_lifecycles(*_GUARDED) == []


def test_the_rendezvous_count_is_read_from_the_adapter_that_does_the_waiting():
    """The pool's bound is derived from this number, so it may not be a guess.

    `_RESULT_BOUND` is `_RENDEZVOUS_BOUND` times one more than this count,
    because a mutually excluded runtime reaches every rendezvous on one thread's
    path in turn before any assertion runs. If the count understates the adapter
    the pool becomes the shorter fuse again and reports a TimeoutError instead
    of the relation -- the exact failure the derivation exists to prevent.

    So the declared number is proved against the adapter's own body. A seam
    added there reds this until somebody writes the new count down, and writing
    it down is what makes them look at the bound it feeds.
    """
    assert _rendezvous_call_sites(EffectOverlapAdapter) == _RENDEZVOUS_PER_THREAD

    class _WaitsOnSomebodyElse:
        def prepare(self, other):
            other._wait(None, None)

    # The receiver, which the count's docstring claimed and its first version
    # did not read. A wait somebody ELSE performs is not a rendezvous on this
    # adapter's path, and counting it would inflate a bound derived from the
    # number -- the same failure as understating it, from the other side.
    assert _rendezvous_call_sites(_WaitsOnSomebodyElse) == 0


def test_a_thread_that_never_returns_is_reported_rather_than_waited_on():
    """The behavioural half: the bound has to end the WAIT, not just be passed.

    The work here cannot finish inside the bound it is given, and the point is
    what the caller does about that. It must come back with the relation named
    and must not have spent the worker's own time getting there -- which is the
    single measurement that separates this lifecycle from the executor it
    replaced, and the one the shipped version would have failed.
    """
    never_finishes = threading.Event()
    started = time.monotonic()

    with pytest.raises(TimeoutError, match="WORK_NEVER_FINISHED"):
        _run_together(
            lambda: never_finishes.wait(timeout=_RENDEZVOUS_BOUND),
            bound=_PROBE_WINDOW)

    spent = time.monotonic() - started
    assert spent < _RENDEZVOUS_BOUND, f"THE_CALLER_WAITED_FOR_THE_WORKER={spent:.2f}s"
    never_finishes.set()  # let the abandoned thread go rather than leave it parked


# A spelled bound is how a disk budget got in, so these files refuse one.
#
# `barrier.wait(timeout=1)` inside the effect-overlap adapter was one fsync
# wide. Nothing said so, because a number at a call site carries no claim about
# what it is for -- there is no way to tell a DEADLOCK bound from a speed budget
# by looking at `1`. The two are opposite instruments: one must never be
# reached, the other must always expire, and mixing them up is what turned a
# concurrency relation into a benchmark of the machine. So each is named once,
# where the reason can be written beside it.
#
# The guard covers the four ways these files block on another thread -- `wait`,
# `result`, `join`, `map` -- and says four rather than "every wait", which would
# be a promise about syntax it does not read. An ABSENT bound is refused in the
# same breath, and that is not symmetry: a missing watchdog is not more
# permissive than a tight one, it is the same failure with no report attached.
#
# What it does NOT settle, and a review had to say so: whether the thread on the
# other side is bounded at all. A named `timeout=` binds the CALLER.
# `future.result(timeout=...)` inside `with ThreadPoolExecutor(...)` satisfies
# every line of this test and still hangs a job, so the lifecycle is a separate
# claim with its own guard above.
def test_every_blocking_call_here_names_its_bound_and_none_waits_unbounded():
    """Every `timeout=` in both files is one of the named bounds, and none is absent.

    The second half stops it guarding an empty set: a named bound that bounds
    nothing would let this pass while the files went back to literals.
    """
    offenders, used = _unnamed_waits(*_GUARDED)

    assert offenders == [], (
        f"a blocking call does not name its bound: {offenders}. Use one of "
        f"{sorted(_NAMED_BOUNDS)} so the reason travels with the number, and "
        "never leave one unbounded -- a hang has to be reported, not waited on")
    assert used == _NAMED_BOUNDS, (
        f"NAMED_BUT_UNUSED={sorted(_NAMED_BOUNDS - used)}")
    # The watchdog and the group bound have to agree, and agreeing is not "the
    # group is bigger": one thread reaches every rendezvous on its path IN TURN
    # when a runtime is mutually excluded, so the group must outlive all of them
    # or it gives up first and reports a bare TimeoutError instead of the
    # relation. What this catches is a BROKEN derivation. What it cannot catch
    # is an understated COUNT -- both sides are built from that number, so
    # halving it moves both and the comparison satisfies itself. A mutation
    # proved that by going green here; the count is answered next door, against
    # the adapter's own body, which is the only thing that knows it.
    assert _RESULT_BOUND > _RENDEZVOUS_BOUND * _RENDEZVOUS_PER_THREAD
    assert _RENDEZVOUS_BOUND > _PROBE_WINDOW
    # `bound` is admitted as a name only because it FORWARDS a named one. Pinned
    # by symbol rather than by module or by line: a forwarder that defaulted to
    # a number would fail here instead of passing by being spelled `bound`.
    assert inspect.signature(_run_together).parameters["bound"].default == (
        _RESULT_BOUND)


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
        worker = threading.Thread(target=waiter, daemon=True)
        worker.start()
        worker.join(timeout=_PROBE_WINDOW)
        assert not entered.is_set()
    worker.join(timeout=_RENDEZVOUS_BOUND)
    assert same_identity == [True] and entered.is_set()
    del first
    gc.collect()
    assert first_ref() is None
    assert key not in runtime_module._OPERATION_LOCKS


def _race_journal_kind(monkeypatch, kind):
    """Pause two appends at the old check/write gap and report true overlap."""
    return _race_journal_kinds(monkeypatch, (kind,))


def _race_journal_kinds(monkeypatch, kinds):
    """Witness whether any selected durable writes overlap another writer."""
    original = run_store_module._append_bytes
    barrier = threading.Barrier(2)
    witness: list[bool] = []
    guard = threading.Lock()
    tokens = tuple(f'"record_type":"{kind}"'.encode() for kind in kinds)

    def racing_append(path, payload):
        if any(token in payload for token in tokens):
            try:
                barrier.wait(timeout=_PROBE_WINDOW)
            except threading.BrokenBarrierError:
                overlapped = False
            else:
                overlapped = True
            with guard:
                witness.append(overlapped)
        return original(path, payload)

    monkeypatch.setattr(run_store_module, "_append_bytes", racing_append)
    return witness


class EffectOverlapAdapter(ScriptedAdapter):
    """Prove both fresh untrusted seams run outside the root transaction."""

    def __init__(self, store, prepare_barrier, execute_barrier):
        super().__init__()
        self._store = store
        self._prepare_barrier = prepare_barrier
        self._execute_barrier = execute_barrier
        self.prepare_overlap = []
        self.execute_overlap = []
        #: How many times each thread really waited. The bounds are derived from
        #: this count, so it is recorded rather than assumed: a seam added here
        #: raises what one thread can spend before any assertion runs.
        self.rendezvous = {}
        self._counting = threading.Lock()

    def deepest_thread(self) -> int:
        """The most rendezvous any ONE thread reached in this run."""
        return max(self.rendezvous.values(), default=0)

    def _wait(self, barrier, witness):
        assert not self._store.current_thread_holds_transaction()
        with self._counting:
            here = threading.get_ident()
            self.rendezvous[here] = self.rendezvous.get(here, 0) + 1
        try:
            barrier.wait(timeout=_RENDEZVOUS_BOUND)
        except threading.BrokenBarrierError:
            witness.append(False)
        else:
            witness.append(True)

    def prepare(self, request):
        self._wait(self._prepare_barrier, self.prepare_overlap)
        return super().prepare(request)

    def execute(self, prepared):
        self._wait(self._execute_barrier, self.execute_overlap)
        return super().execute(prepared)


def _slow_lease_write(monkeypatch, ordinal, seconds):
    """Make the `ordinal`-th effect-lease write take `seconds`, and nothing else.

    Installed BEFORE the race witness, so the function that witness captures as
    its own original is already the slow one. That order is the whole point: it
    is how a slow disk really presents itself to this circuit, underneath every
    instrument rather than beside them.

    The lease is the write worth slowing. It is the ONE durable write standing
    between the prepare rendezvous and the execute rendezvous, so its cost is
    exactly what a rendezvous bound was accidentally budgeting.
    """
    original = run_store_module._append_bytes
    seen = itertools.count(1)
    guard = threading.Lock()

    def slow_append(path, payload):
        if b'"phase":"effect_lease"' in payload:
            with guard:
                nth = next(seen)
            if nth == ordinal:
                time.sleep(seconds)
        return original(path, payload)

    monkeypatch.setattr(run_store_module, "_append_bytes", slow_append)


def _overlap_circuit(tmp_path, monkeypatch, *, slow_lease_write=0.0):
    """Drive two fresh distinct effects concurrently through one runtime."""
    store = a_store(tmp_path)
    prepare_barrier = threading.Barrier(2)
    execute_barrier = threading.Barrier(2)
    adapter = EffectOverlapAdapter(store, prepare_barrier, execute_barrier)
    runtime = a_runtime(store, adapter, ids=counting_ids())
    first = a_proposal(store)
    second = a_proposal(
        store, proposal_id="proposal-002", attempt_id="attempt-002",
        arguments={"handoff": "packet-002"})
    authorizations = (
        runtime.authorize(a_confirmation(first), budget=a_budget()),
        runtime.authorize(a_confirmation(second), budget=a_budget()),
    )
    if slow_lease_write:
        _slow_lease_write(monkeypatch, 2, slow_lease_write)
    writes = _race_journal_kinds(monkeypatch, ("attempt_event", "action_result"))

    attempts = _values(_run_together(
        partial(runtime.execute, authorizations[0]),
        partial(runtime.execute, authorizations[1])))
    return adapter, writes, attempts, store, authorizations


def test_fresh_distinct_effects_overlap_while_every_durable_write_serializes(
        tmp_path, monkeypatch):
    adapter, writes, attempts, store, authorizations = _overlap_circuit(
        tmp_path, monkeypatch)

    assert adapter.prepare_overlap == [True, True]
    assert adapter.execute_overlap == [True, True]
    # What one thread really spent, beside what the bounds were derived from.
    # The static count knows every seam that EXISTS; this knows how many ran,
    # so a seam reached twice through a loop cannot hide behind one call site.
    assert adapter.deepest_thread() == _RENDEZVOUS_PER_THREAD
    assert writes == [False] * 6
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 2
    assert all(attempt.history == (
        AttemptState.ACCEPTED, AttemptState.STARTED,
        AttemptState.VERIFICATION_FAILED)
        for attempt in attempts)
    recovered = store.read("run-001")
    for authorization in authorizations:
        action_id = authorization.request.action_id
        action_rows = [
            row for row in recovered.records
            if getattr(row.value, "action_id", None) == action_id]
        assert [row.kind for row in action_rows] == [
            "action_request", "attempt_event", "attempt_event", "action_result"]
    assert recovered.warnings == ()


def test_a_durable_write_slower_than_the_old_budget_leaves_the_overlap_intact(
        tmp_path, monkeypatch):
    """The regression for the budget this circuit used to hide inside a barrier.

    The rendezvous that proves two seams overlap used to wait one second, and
    one second is about one fsync. The effect lease is the single durable write
    between the two rendezvous, so a thread that took longer than that to write
    it left the other thread's barrier broken -- and the circuit reported that
    the seams had not overlapped. They had. The disk was slow.

    So the disk is made slow ON PURPOSE here, by more than the bound that used
    to be in force, and every relation the fast circuit holds must still hold.
    A machine cannot be relied on to be slow, but it can be MADE slow, and that
    turns a flake nobody could reproduce into a test that fails the same way
    every time the budget comes back.

    It does not pin the bound's value, and could not: it pins that the bound is
    not one durable write wide. The value is named rather than spelled, and
    `test_every_blocking_call_here_names_its_bound_and_none_waits_unbounded` is what
    keeps it that way.
    """
    adapter, writes, attempts, _store, _authorizations = _overlap_circuit(
        tmp_path, monkeypatch, slow_lease_write=_A_SLOW_DURABLE_WRITE)

    assert adapter.prepare_overlap == [True, True]
    assert adapter.execute_overlap == [True, True], (
        "a rendezvous gave up while the other thread was still writing, so "
        "this circuit is budgeting disk speed again")
    assert writes == [False] * 6
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 2
    assert all(attempt.history == (
        AttemptState.ACCEPTED, AttemptState.STARTED,
        AttemptState.VERIFICATION_FAILED)
        for attempt in attempts)


@pytest.mark.parametrize("held_root", ["same", "other"])
def test_authorize_refuses_before_operation_lock_when_a_root_transaction_is_held(
        tmp_path, monkeypatch, held_root):
    store = a_store(tmp_path / "subject")
    proposal = a_proposal(store)
    runtime = confirmation_runtime(store)
    held = store if held_root == "same" else RunStore(tmp_path / "other")
    journal = store.run_path("run-001") / "records.jsonl"
    before = journal.read_bytes()
    operation_calls = []

    def touched_operation_lock(key):
        operation_calls.append(key)
        raise AssertionError("operation lock was touched below a root transaction")

    monkeypatch.setattr(runtime_module, "_operation_lock", touched_operation_lock)

    with held.transaction():
        with pytest.raises(
                AuthorizationError,
                match="runtime operation cannot start inside a store transaction"):
            runtime.authorize(a_confirmation(proposal), budget=a_budget())

    assert journal.read_bytes() == before
    assert operation_calls == []


def test_execute_refuses_before_operation_lock_when_a_root_transaction_is_held(
        tmp_path, monkeypatch):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    journal = store.run_path("run-001") / "records.jsonl"
    before = journal.read_bytes()
    operation_calls = []

    def touched_operation_lock(key):
        operation_calls.append(key)
        raise AssertionError("operation lock was touched below a root transaction")

    monkeypatch.setattr(runtime_module, "_operation_lock", touched_operation_lock)

    with store.transaction():
        with pytest.raises(
                ExecutionError,
                match="runtime operation cannot start inside a store transaction"):
            runtime.execute(authorization)

    assert journal.read_bytes() == before
    assert operation_calls == []
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    monkeypatch.undo()
    assert runtime.execute(authorization).state is (
        AttemptState.VERIFICATION_FAILED)


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

    authorizations = _values(_run_together(*[
        partial(runtime.authorize, confirmation, budget=a_budget())
        for runtime in runtimes]))

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

    attempts = _values(_run_together(*[
        partial(runtime.execute, authorization) for runtime in runtimes]))

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
                seam.wait(timeout=_RENDEZVOUS_BOUND)
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

    attempts = _values(_run_together(
        partial(runtimes[0].execute, authorizations[0]),
        partial(runtimes[1].execute, authorizations[1])))

    assert [attempt.state for attempt in attempts] == [
        AttemptState.VERIFICATION_FAILED, AttemptState.VERIFICATION_FAILED]
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

    results = []
    for kind, value in _run_together(
            partial(authorize_one, 0), partial(authorize_one, 1)):
        if kind == "error" and not isinstance(value, AuthorizationError):
            raise value
        results.append("refused" if kind == "error" else value)

    assert sum(result == "refused" for result in results) == 1
    assert len(action_requests(RunStore(tmp_path))) == 1
    assert witness == [False]
    assert RunStore(tmp_path).read("run-001").warnings == ()


def test_concurrent_exact_confirmation_has_one_created_disposition_and_one_retry(
        tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    server_clock = lambda: "2026-08-11T12:00:02Z"
    runtimes = (
        confirmation_runtime(
            RunStore(tmp_path), clock=server_clock, ids=counting_ids()),
        confirmation_runtime(
            RunStore(tmp_path), clock=server_clock, ids=counting_ids()),
    )
    confirmations = (
        a_confirmation(proposal),
        a_confirmation(
            proposal, confirmation_id="confirmation-002",
            confirmed_at="2026-08-11T12:00:01Z"),
    )
    start = threading.Barrier(2)

    def authorize_one(index):
        start.wait(timeout=_RENDEZVOUS_BOUND)
        return runtimes[index].authorize(confirmations[index], budget=a_budget())

    results = _values(_run_together(
        partial(authorize_one, 0), partial(authorize_one, 1)))

    assert {result.record_created for result in results} == {True, False}
    assert results[0].request == results[1].request
    assert len(action_requests(RunStore(tmp_path))) == 1


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
                barrier.wait(timeout=_PROBE_WINDOW)
            except threading.BrokenBarrierError:
                witness.append(False)
            else:
                witness.append(True)
        return original(path, payload)

    monkeypatch.setattr(run_store_module, "_append_bytes", racing_writes)
    executed, second_authorization = _values(_run_together(
        partial(execution.execute, first_authorization),
        partial(second_runtime.authorize, a_confirmation(second),
                budget=a_budget())))
    assert executed.state is AttemptState.VERIFICATION_FAILED

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
                seam.wait(timeout=_RENDEZVOUS_BOUND)
            except threading.BrokenBarrierError:
                seam_overlap.append(False)
            else:
                seam_overlap.append(True)
            return super().verify(request, result)

    runtimes = tuple(
        a_runtime(RunStore(root), RootOverlapAdapter()) for root in roots)
    witness = _race_journal_kind(monkeypatch, "action_result")

    attempts = _values(_run_together(
        partial(runtimes[0].execute, pairs[0][1]),
        partial(runtimes[1].execute, pairs[1][1])))

    assert all(
        attempt.state is AttemptState.VERIFICATION_FAILED for attempt in attempts)
    assert seam_overlap == [True, True]
    assert witness == [True, True]
    for root in roots:
        recovered = RunStore(root).read("run-001")
        assert sum(row.kind == "action_result" for row in recovered.records) == 1
        assert recovered.warnings == ()
