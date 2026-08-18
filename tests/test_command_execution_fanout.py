"""Owner gate B: two provider instances execute at once, serialized and replayable.

Session 2 shipped one worker on purpose, so "concurrently" could not be observed
at all. These are the witnesses that it now can be, and that nothing session 2
proved was traded away for it: the bounded-queue overflow, the fresh-authority
refusal and the restart witness are re-run here against a WORKER POOL, because
under fan-out they are regressions rather than the original claims.

Every ordering fact is held by a barrier or a gate the test owns. The barrier is
the whole concurrency proof: neither provider's ``execute`` can return until both
have reached it, so a build with one worker breaks the barrier instead of
quietly passing.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager

import pytest

from conductor.command.contracts import ActionRequest
from conductor.command.coordinator import ExecutionCoordinator, ExecutionOwnershipError
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore
from conductor.command.runtime import Authorization, ControlRuntime

from tests.alpha1_providers import NOW, a_proposal, a_store, ids, resolve
from tests.test_command_http_api import (
    PORT,
    RUN_ID,
    TOKEN,
    confirm_body,
    encode,
    post_headers,
)


BOTH = ("claude-code", "codex")
WAIT = 20.0
#: How long the first writer parks inside its transaction watching for a second.
#: A store that excludes can never admit one in that window, however slow the
#: machine; a store that does not admits one in microseconds.
HELD_WATCH = 1.0


def a_registry(root, mint):
    """Two AVAILABLE providers, resolved through the session-1 factory door."""
    resolution = resolve(root, mint, available=BOTH, mismatched=())
    assert sorted(
        (row.provider_id, row.available) for row in resolution.contracts
        if row.available) == [("claude-code", True), ("codex", True)]
    return resolution.registry


def an_api(tmp_path, *, workers=2, capacity=8, published=None, store=None):
    """A command API whose coordinator owns `workers` independently retirable workers."""
    mint = ids()
    store = a_store(tmp_path) if store is None else store
    registry = a_registry(tmp_path, mint)
    signals = [] if published is None else published
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=mint,
        publish_run=signals.append)
    coordinator = ExecutionCoordinator(api.runtime, capacity=capacity)
    api.attach_execution(coordinator)
    tokens = tuple(sorted(coordinator.start() for _ in range(workers)))
    adapters = tuple(registry.resolve(row) for row in BOTH)
    return api, store, coordinator, adapters, tokens, signals


def post(api, path, body):
    return api.handle("POST", path, post_headers(body), encode(body))


def confirm(api, *, instance_id, attempt_id, work_item_id):
    """Propose and confirm one dispatch; return the recorded action id."""
    proposed = post(api, f"/command/runs/{RUN_ID}/proposals", a_proposal(
        instance_id=instance_id, attempt_id=attempt_id, work_item_id=work_item_id))
    assert proposed.status == 201, proposed.payload
    confirmed = post(
        api, f"/command/runs/{RUN_ID}/actions", confirm_body(proposed.payload))
    assert confirmed.status == 201, confirmed.payload
    return confirmed.payload["action_id"]


def records(store, kind):
    return [row.value for row in store.read(RUN_ID).records if row.kind == kind]


def journal_of(store):
    return store.run_path(RUN_ID) / "records.jsonl"


def barriered(adapters):
    """Bind one barrier to every adapter, so execute proves simultaneity."""
    barrier = threading.Barrier(len(adapters))
    for adapter in adapters:
        adapter.barrier = barrier
    return barrier


def test_two_different_provider_instances_are_inside_execute_at_the_same_instant(
        tmp_path):
    api, store, coordinator, adapters, _tokens, _signals = an_api(tmp_path)
    barrier = barriered(adapters)
    try:
        assert records(store, "action_result") == []
        confirm(api, instance_id="claude-dev",
                attempt_id="attempt-001", work_item_id="work-001")
        confirm(api, instance_id="codex-review",
                attempt_id="attempt-002", work_item_id="work-002")
        assert coordinator.wait_idle(WAIT) is True
        # The barrier is the proof and the only one that would survive a build
        # with a single worker: neither execute could return until BOTH adapters
        # had entered, and each was entered by a different thread.
        assert barrier.broken is False
        assert [adapter.executions for adapter in adapters] == [1, 1]
        entered = {ident for adapter in adapters
                   for _action, ident in adapter.execute_threads}
        assert len(entered) == 2
        assert sorted(row.outcome for row in records(store, "action_result")) == [
            "verification_failed", "verification_failed"]
    finally:
        barrier.abort()
        coordinator.shutdown()


def test_two_workers_appending_at_once_leave_one_replayable_journal(tmp_path):
    api, store, coordinator, adapters, _tokens, _signals = an_api(tmp_path)
    barrier = barriered(adapters)
    for adapter in adapters:
        adapter.evidence_sink = store.append
        adapter.verifies_with_evidence = True
    journal = journal_of(store)
    try:
        assert journal.read_bytes() == b""
        first = confirm(api, instance_id="claude-dev",
                        attempt_id="attempt-001", work_item_id="work-001")
        second = confirm(api, instance_id="codex-review",
                         attempt_id="attempt-002", work_item_id="work-002")
        assert coordinator.wait_idle(WAIT) is True

        # Serialized: every durable line is one whole canonical record, so no
        # append tore or interleaved with the other worker's.
        lines = journal.read_bytes().decode("utf-8").splitlines()
        assert lines and all(isinstance(json.loads(line), dict) for line in lines)
        # Replayable: a reader that never saw this process replays the same
        # history, with nothing left unjudged.
        replayed = RunStore(tmp_path).read(RUN_ID)
        assert replayed.warnings == ()
        assert len(replayed.records) == len(lines)
        assert [(row.kind, row.value.as_dict()) for row in replayed.records] == [
            (row.kind, row.value.as_dict()) for row in store.read(RUN_ID).records]

        claimed = {row["action_id"]: row
                   for adapter in adapters for row in adapter.claims}
        assert sorted(claimed) == sorted([first, second])
        for action_id, claim in claimed.items():
            assert _phases(replayed, action_id) == [
                "effect_lease", "execution_observed"]
            observed = _observed(replayed, action_id)
            assert (observed.outcome, observed.exit_code) == (
                claim["outcome"], claim["exit_code"])
            receipt = _receipt(replayed, action_id)
            assert (receipt.outcome, receipt.exit_code) == ("succeeded", 0)
            assert len(receipt.evidence_refs) == 1
    finally:
        barrier.abort()
        coordinator.shutdown()


class _TransactionWitness(RunStore):
    """A RunStore that reports whether two worker threads are ever inside at once.

    Exclusion decides the answer, not timing. The first worker thread that gets
    inside a root transaction parks there and watches for a second one; a store
    that admits one writer at a time can never let a second in while the first
    is parked, so the watch always expires. A store that lost its gate admits
    the second immediately, which is what ``admitted_while_held`` reports and
    what raises ``overlap_max`` above one.

    Only the FIRST transaction each non-request thread takes is armed, so the
    nested transactions one append opens are left alone.
    """

    def __init__(self, project_root) -> None:
        super().__init__(project_root)
        self._request_thread = threading.get_ident()
        self._witness = threading.Lock()
        self._seen: set[int] = set()
        self._armed = 0
        self._inside = 0
        self.overlap_max = 0
        self.second_inside = threading.Event()
        self.admitted_while_held: bool | None = None

    @property
    def worker_threads(self) -> int:
        """How many threads other than the request thread wrote through this store."""
        with self._witness:
            return len(self._seen)

    @contextmanager
    def transaction(self):
        with super().transaction():
            role = self._arm()
            if role == 0:
                yield
                return
            try:
                if role == 1:
                    self.admitted_while_held = self.second_inside.wait(HELD_WATCH)
                else:
                    self.second_inside.set()
                yield
            finally:
                with self._witness:
                    self._inside -= 1

    def _arm(self) -> int:
        ident = threading.get_ident()
        with self._witness:
            if ident == self._request_thread or ident in self._seen:
                return 0
            self._seen.add(ident)
            self._armed += 1
            self._inside += 1
            self.overlap_max = max(self.overlap_max, self._inside)
            return self._armed


def test_two_workers_are_never_inside_a_run_store_transaction_at_once(tmp_path):
    """Serialization by exclusion: the second writer waits outside, it never joins."""
    witness = a_store(tmp_path, store_class=_TransactionWitness)
    api, store, coordinator, adapters, _tokens, _signals = an_api(
        tmp_path, store=witness)
    barrier = barriered(adapters)
    try:
        assert (witness.worker_threads, witness.overlap_max) == (0, 0)
        confirm(api, instance_id="claude-dev",
                attempt_id="attempt-001", work_item_id="work-001")
        confirm(api, instance_id="codex-review",
                attempt_id="attempt-002", work_item_id="work-002")
        assert coordinator.wait_idle(WAIT) is True

        # Two worker threads really did write, they really were both inside
        # execute at once, and still no two of them shared a transaction.
        assert witness.worker_threads == 2
        assert barrier.broken is False
        assert witness.admitted_while_held is False
        assert witness.overlap_max == 1
        assert sorted(row.outcome for row in records(store, "action_result")) == [
            "verification_failed", "verification_failed"]
        assert store.read(RUN_ID).warnings == ()
    finally:
        barrier.abort()
        coordinator.shutdown()


def _phases(recovered, action_id):
    return [row.value.phase for row in recovered.records
            if row.kind == "attempt_event" and row.value.action_id == action_id]


def _observed(recovered, action_id):
    return next(row.value for row in recovered.records
                if row.kind == "attempt_event"
                and row.value.action_id == action_id
                and row.value.phase == "execution_observed")


def _receipt(recovered, action_id):
    return next(row.value for row in recovered.records
                if row.kind == "action_result" and row.value.action_id == action_id)


def test_no_adapter_seam_is_reached_while_a_store_transaction_is_held_under_fan_out(
        tmp_path):
    api, _store, coordinator, adapters, _tokens, _signals = an_api(tmp_path)
    barrier = barriered(adapters)
    try:
        confirm(api, instance_id="claude-dev",
                attempt_id="attempt-001", work_item_id="work-001")
        confirm(api, instance_id="codex-review",
                attempt_id="attempt-002", work_item_id="work-002")
        assert coordinator.wait_idle(WAIT) is True
        for adapter in adapters:
            assert [seam for seam, _held in adapter.held_transactions] == [
                "prepare", "execute", "verify"]
            assert [held for _seam, held in adapter.held_transactions] == [
                False, False, False]
    finally:
        barrier.abort()
        coordinator.shutdown()


def test_the_bounded_queue_caps_the_whole_pool_not_one_worker(tmp_path):
    """A second idle worker does not raise the ceiling, and the refusal is free."""
    signals: list[str] = []
    api, store, coordinator, adapters, _tokens, _ = an_api(
        tmp_path, capacity=1, published=signals)
    journal = journal_of(store)
    try:
        adapters[0].gates["execute"].clear()
        held = confirm(api, instance_id="claude-dev",
                       attempt_id="attempt-001", work_item_id="work-001")
        assert adapters[0].wait_for("execute", held) is True
        second = post(api, f"/command/runs/{RUN_ID}/proposals", a_proposal(
            instance_id="codex-review", attempt_id="attempt-002",
            work_item_id="work-002"))
        assert second.status == 201
        before, announced = journal.read_bytes(), list(signals)

        refused = post(
            api, f"/command/runs/{RUN_ID}/actions", confirm_body(second.payload))

        assert (refused.status, refused.payload["error"]["code"]) == (
            409, "service_refused")
        assert journal.read_bytes() == before
        assert signals[len(announced):] == []
        assert len(records(store, "action_request")) == 1
        assert adapters[1].executions == 0
        assert coordinator.placements() == 1
    finally:
        adapters[0].gates["execute"].set()
        coordinator.shutdown()


def test_stopping_one_token_retires_that_worker_and_leaves_its_sibling_working(
        tmp_path):
    """Exactness by observation: the retired thread is gone, the named one still runs.

    Placement gives an action to the live worker carrying the least load, ties
    broken by token order, so the first action runs on ``tokens[0]`` and the
    second -- placed while the first is provably parked inside execute -- on
    ``tokens[1]``. Retiring ``tokens[1]`` must therefore end exactly the second
    thread and leave the first both alive and still executing.
    """
    api, _store, coordinator, adapters, tokens, _signals = an_api(tmp_path)
    try:
        for adapter in adapters:
            adapter.gates["execute"].clear()
        first = confirm(api, instance_id="claude-dev",
                        attempt_id="attempt-001", work_item_id="work-001")
        assert adapters[0].wait_for("execute", first) is True
        second = confirm(api, instance_id="codex-review",
                         attempt_id="attempt-002", work_item_id="work-002")
        assert adapters[1].wait_for("execute", second) is True
        on_first = dict(adapters[0].execute_threads)[first]
        on_second = dict(adapters[1].execute_threads)[second]
        assert on_first != on_second
        for adapter in adapters:
            adapter.gates["execute"].set()
        assert coordinator.wait_idle(WAIT) is True

        coordinator.stop_worker(tokens[1])

        assert coordinator.owned_tokens() == (tokens[0],)
        alive = {thread.ident for thread in threading.enumerate()}
        assert on_first in alive
        assert on_second not in alive
        third = confirm(api, instance_id="claude-dev",
                        attempt_id="attempt-003", work_item_id="work-003")
        assert coordinator.wait_idle(WAIT) is True
        assert dict(adapters[0].execute_threads)[third] == on_first
    finally:
        for adapter in adapters:
            adapter.gates["execute"].set()
        coordinator.shutdown()


def test_stopping_a_token_this_coordinator_never_minted_retires_no_worker(tmp_path):
    api, _store, coordinator, adapters, tokens, _signals = an_api(tmp_path)
    stranger = ExecutionCoordinator(ControlRuntime(
        RunStore(tmp_path), a_registry(tmp_path, ids()),
        clock=lambda: NOW, ids=ids()))
    stranger_token = stranger.start()
    barrier = barriered(adapters)
    try:
        with pytest.raises(ExecutionOwnershipError, match="did not mint"):
            coordinator.stop_worker(stranger_token)
        with pytest.raises(ExecutionOwnershipError, match="did not mint"):
            stranger.stop_worker(tokens[0])

        assert coordinator.owned_tokens() == tokens
        assert stranger.owned_tokens() == (stranger_token,)
        # Both refused stops retired nothing: the pool still runs two adapters at
        # once, which the barrier could not survive if either worker were gone.
        confirm(api, instance_id="claude-dev",
                attempt_id="attempt-001", work_item_id="work-001")
        confirm(api, instance_id="codex-review",
                attempt_id="attempt-002", work_item_id="work-002")
        assert coordinator.wait_idle(WAIT) is True
        assert barrier.broken is False
        assert [adapter.executions for adapter in adapters] == [1, 1]
    finally:
        barrier.abort()
        coordinator.shutdown()
        stranger.shutdown()


def test_shutting_down_this_pool_ends_its_own_threads_and_no_stranger_s(tmp_path):
    """Only-mine at pool scale: every owned thread ends, a stranger's keeps consuming.

    A worker's liveness is read from the work it does, not from a name: the
    stranger's pool is handed one authorization after this pool is retired, and
    only a live worker could have recorded its refusal.
    """
    api, _store, coordinator, adapters, tokens, _signals = an_api(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _store_elsewhere, request = _authorized_without_execution(elsewhere)
    stranger, _registry, stranger_tokens = _restarted_pool(elsewhere, workers=2)
    try:
        owned = _park_one_action_on_each_worker(api, adapters)
        assert len(owned) == len(tokens) == 2
        assert owned <= {thread.ident for thread in threading.enumerate()}
        assert coordinator.wait_idle(WAIT) is True

        coordinator.shutdown()

        assert coordinator.owned_tokens() == ()
        assert owned.isdisjoint({thread.ident for thread in threading.enumerate()})
        assert stranger.owned_tokens() == stranger_tokens
        slot = stranger.claim()
        try:
            slot.place(Authorization(request=request, record_created=True))
        finally:
            slot.release()
        assert stranger.wait_idle(WAIT) is True
        assert stranger.refusals() == (request.action_id,)
    finally:
        for adapter in adapters:
            adapter.gates["execute"].set()
        coordinator.shutdown()
        stranger.shutdown()


def _park_one_action_on_each_worker(api, adapters):
    """Hold one action inside each adapter's execute; return the two thread ids."""
    for adapter in adapters:
        adapter.gates["execute"].clear()
    first = confirm(api, instance_id="claude-dev",
                    attempt_id="attempt-001", work_item_id="work-001")
    assert adapters[0].wait_for("execute", first) is True
    second = confirm(api, instance_id="codex-review",
                     attempt_id="attempt-002", work_item_id="work-002")
    assert adapters[1].wait_for("execute", second) is True
    for adapter in adapters:
        adapter.gates["execute"].set()
    return {dict(adapters[0].execute_threads)[first],
            dict(adapters[1].execute_threads)[second]}


def _authorized_without_execution(tmp_path):
    """Record one durable action request through the HTTP boundary and stop there."""
    mint = ids()
    store = a_store(tmp_path)
    registry = a_registry(tmp_path, mint)
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=mint,
        publish_run=lambda _run_id: None)
    proposed = post(api, f"/command/runs/{RUN_ID}/proposals", a_proposal(
        instance_id="claude-dev", attempt_id="attempt-001",
        work_item_id="work-001"))
    assert proposed.status == 201
    confirmed = post(
        api, f"/command/runs/{RUN_ID}/actions", confirm_body(proposed.payload))
    assert confirmed.status == 201
    assert api.execution is None
    return store, ActionRequest.from_dict(confirmed.payload)


def _restarted_pool(tmp_path, *, workers=4):
    """A pool over a runtime that never authorized anything in this process."""
    mint = ids()
    registry = a_registry(tmp_path, mint)
    runtime = ControlRuntime(
        RunStore(tmp_path), registry, clock=lambda: NOW, ids=mint)
    coordinator = ExecutionCoordinator(runtime)
    tokens = tuple(sorted(coordinator.start() for _ in range(workers)))
    return coordinator, registry, tokens


def test_a_restarted_worker_pool_enqueues_nothing_and_repeats_no_effect(tmp_path):
    store, _request = _authorized_without_execution(tmp_path)
    before = journal_of(store).read_bytes()
    coordinator, registry, tokens = _restarted_pool(tmp_path)
    try:
        assert coordinator.wait_idle(WAIT) is True
        assert coordinator.placements() == 0
        assert coordinator.owned_tokens() == tokens
        assert [registry.resolve(row).executions for row in BOTH] == [0, 0]
        assert journal_of(store).read_bytes() == before
        assert [row.kind for row in store.read(RUN_ID).records] == [
            "action_proposal", "action_request"]
    finally:
        coordinator.shutdown()


def test_an_authorization_without_a_live_grant_reaches_no_worker_s_adapter(tmp_path):
    store, request = _authorized_without_execution(tmp_path)
    before = journal_of(store).read_bytes()
    coordinator, registry, _tokens = _restarted_pool(tmp_path)
    try:
        # A durable request is evidence of authorization, never execution
        # authority -- on any worker of any size of pool.
        slot = coordinator.claim()
        try:
            slot.place(Authorization(request=request, record_created=True))
        finally:
            slot.release()
        assert coordinator.wait_idle(WAIT) is True
        assert coordinator.refusals() == (request.action_id,)
        assert [registry.resolve(row).executions for row in BOTH] == [0, 0]
        assert journal_of(store).read_bytes() == before
    finally:
        coordinator.shutdown()
