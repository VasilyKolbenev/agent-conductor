"""Asynchronous execution after Confirm: bounded, owned, and never repeated.

Every relation here is driven by a deterministic FAKE provider admitted through
the session-1 provider door (``resolve_providers`` -> ``ProviderRegistry``), so
the adapter the runtime drives is the one a real operator config would produce.
The provider performs its effect in process and blocks on an Event the test owns,
so every ordering claim is held by a barrier and never by a sleep.
"""
from __future__ import annotations

import threading

import pytest

from conductor.command.adapters import (
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
    ProviderCatalogEntry,
    ProviderConfig,
)
from conductor.command.adapters.deep_adapters import DEEP_CAPABILITIES, DEEP_CONTROLS
from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.contracts import ActionResultReceipt
from conductor.command.coordinator import (
    ExecutionCoordinator,
    ExecutionOwnershipError,
    ExecutionRefused,
)
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.providers import resolve_providers
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.service import CommandService
from conductor.command.runtime import (
    Authorization,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests.test_command_http_api import (
    PORT,
    RUN_ID,
    TOKEN,
    confirm_body,
    encode,
    post_headers,
    proposal_body,
)
from tests.test_command_run_store import CONFIG, a_run


NOW = "2026-08-17T12:00:00Z"
PROTOCOL = "fake-claude-jsonl-v1"
PROVIDER_ID = "claude-code"
INSTANCE_ID = "claude-dev"
BUDGET = Budget(
    max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)


class DeterministicProvider:
    """A fake provider whose effect is a counter and a barrier, never a process.

    It satisfies the provider door's whole contract -- the catalogued adapter
    class, the exact per-capability argument schemas, and the four lifecycle
    seams -- so the factory builds and registers it exactly as it would a real
    one. It spawns nothing: the ``executions`` counter IS the effect count, and it
    records, at each seam, whether a run-store transaction was held on the thread
    calling it.
    """

    argument_schemas = {
        capability: "deep-arguments-v1" for capability in DEEP_CAPABILITIES}

    def __init__(self, config, runner, *, clock, ids) -> None:
        self.manifest = AdapterManifest(
            adapter_id=PROVIDER_ID, display_name="Deterministic fake provider",
            vendor="ALPHA-1 fixture", version="fake-protocol-v1",
            capabilities=DEEP_CONTROLS, docs_url="")
        self._config = config
        self._runner = runner
        self._clock = clock
        self._ids = ids
        self.executions = 0
        self.verifications = 0
        self.entered = threading.Event()
        self.gate = threading.Event()
        self.gate.set()
        self.held_transactions: list[tuple[str, bool]] = []
        self._lock = threading.Lock()

    def _record(self, seam: str) -> None:
        with self._lock:
            self.held_transactions.append(
                (seam, RunStore.current_thread_holds_transaction()))

    def observe(self, instance_id, run_id):
        self._record("observe")
        return AdapterObservation(
            adapter_id=PROVIDER_ID, instance_id=instance_id, run_id=run_id,
            observed_at=self._clock(), health="unknown", available_capabilities=(),
            detail="the deterministic fixture probes nothing")

    def prepare(self, request):
        self._record("prepare")
        return PreparedAction(
            adapter_id=PROVIDER_ID, request=request,
            adapter_payload={"work_item_id": request.arguments["work_item_id"]})

    def execute(self, prepared):
        self._record("execute")
        with self._lock:
            self.executions += 1
        self.entered.set()
        self.gate.wait(10)
        request = prepared.request
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome="succeeded",
            observed_at=self._clock(), detail="the fixture completed its effect",
            exit_code=0)

    def verify(self, request, result):
        self._record("verify")
        with self._lock:
            self.verifications += 1
        return AdapterVerification(
            adapter_id=PROVIDER_ID, action_id=request.action_id,
            state="unavailable", observed_at=self._clock(),
            detail="the fixture holds no independent check of its own effect",
            evidence_refs=())


def catalog():
    """One reviewed catalog entry whose adapter class is the fixture above."""
    return {PROVIDER_ID: ProviderCatalogEntry(
        provider_id=PROVIDER_ID, display_name="Deterministic fake provider",
        vendor="ALPHA-1 fixture", protocol=PROTOCOL, capabilities=DEEP_CONTROLS,
        schema_pairs=tuple(sorted(
            (capability, "deep-arguments-v1") for capability in DEEP_CAPABILITIES)),
        lifecycle=("observe", "prepare", "execute", "verify"),
        adapter_class=DeterministicProvider)}


def ids():
    """Thread-safe deterministic ids: the worker and the request thread share them."""
    counters: dict[str, int] = {}
    lock = threading.Lock()

    def mint(kind: str) -> str:
        with lock:
            counters[kind] = counters.get(kind, 0) + 1
            return f"{kind}-async-{counters[kind]}"

    return mint


def provider_registry(tmp_path, mint):
    """Resolve one AVAILABLE fake provider through the real factory door."""
    executable = tmp_path / "fake-provider.exe"
    executable.write_text("", encoding="utf-8")
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=PROVIDER_ID, executable=str(executable),
            protocol=PROTOCOL, env_allow=())],
        root=tmp_path, clock=lambda: NOW, ids=mint, catalog=catalog())
    assert resolution.contracts[0].available is True
    return resolution.registry


def a_store(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)), CONFIG)
    return store


def an_api(tmp_path, *, capacity=8, signals=None):
    """A command API with one started coordinator over its own runtime."""
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    published = [] if signals is None else signals
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=mint,
        publish_run=published.append)
    coordinator = ExecutionCoordinator(api.runtime, capacity=capacity)
    api.attach_execution(coordinator)
    coordinator.start()
    adapter = registry.resolve(PROVIDER_ID)
    return api, store, coordinator, adapter, published


def post(api, path, body):
    return api.handle("POST", path, post_headers(body), encode(body))


def confirm(api, *, work_item_id="work-001", attempt_id="attempt-001"):
    """Propose one dispatch and confirm it; return the two responses."""
    body = {**proposal_body(), "attempt_id": attempt_id}
    body["arguments"] = {**body["arguments"], "work_item_id": work_item_id}
    proposed = post(api, f"/command/runs/{RUN_ID}/proposals", body)
    assert proposed.status == 201, proposed.payload
    confirmed = post(
        api, f"/command/runs/{RUN_ID}/actions", confirm_body(proposed.payload))
    return proposed, confirmed


def kinds(store):
    return [row.kind for row in store.read(RUN_ID).records]


def results(store):
    return [row.value for row in store.read(RUN_ID).records if row.kind == "action_result"]


def a_confirmation(proposal_id, preview_digest):
    return Confirmation(
        confirmation_id="confirmation-direct", run_id=RUN_ID,
        proposal_id=proposal_id, preview_digest=preview_digest,
        capability="dispatch", scope=("src", "tests"),
        config_digest=snapshot_digest(CONFIG), confirmed_by="release-owner",
        confirmed_at=NOW)


def test_confirm_answers_with_the_recorded_request_while_the_effect_is_still_held(
        tmp_path):
    api, store, coordinator, adapter, _ = an_api(tmp_path)
    try:
        adapter.gate.clear()
        _proposed, confirmed = confirm(api)
        assert confirmed.status == 201
        # The response arrived while the effect is provably unfinished: only this
        # test can open the gate, and it has not.
        assert adapter.gate.is_set() is False
        assert results(store) == []
        assert adapter.entered.wait(10) is True
        assert kinds(store) == [
            "action_proposal", "action_request", "attempt_event"]
        adapter.gate.set()
        assert coordinator.wait_idle(10) is True
        assert kinds(store) == [
            "action_proposal", "action_request", "attempt_event", "attempt_event",
            "action_result"]
        # The fixture provider holds no independent check of its own effect, so
        # its terminal result is `verification_failed`; the relation held here is
        # that exactly one result was appended, by exactly one worker.
        assert [row.outcome for row in results(store)] == ["verification_failed"]
        assert (adapter.executions, coordinator.placements()) == (1, 1)
    finally:
        adapter.gate.set()
        coordinator.shutdown()


def test_a_duplicate_confirm_queues_once_and_performs_exactly_one_effect(tmp_path):
    api, store, coordinator, adapter, published = an_api(tmp_path)
    try:
        proposed, confirmed = confirm(api)
        retry = post(
            api, f"/command/runs/{RUN_ID}/actions", confirm_body(proposed.payload))
        assert (confirmed.status, retry.status) == (201, 200)
        assert retry.payload == confirmed.payload
        assert coordinator.wait_idle(10) is True
        assert coordinator.placements() == 1
        assert adapter.executions == 1
        assert kinds(store).count("action_request") == 1
        assert len(results(store)) == 1
        assert published == [RUN_ID] * 5
    finally:
        coordinator.shutdown()


def test_a_full_queue_refuses_the_confirm_before_any_durable_byte_or_effect(tmp_path):
    api, store, coordinator, adapter, published = an_api(tmp_path, capacity=1)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    try:
        adapter.gate.clear()
        confirm(api)
        assert adapter.entered.wait(10) is True
        second = post(api, f"/command/runs/{RUN_ID}/proposals", {
            **proposal_body(), "attempt_id": "attempt-002",
            "arguments": {**proposal_body()["arguments"], "work_item_id": "work-002"}})
        assert second.status == 201
        before, signalled = journal.read_bytes(), list(published)
        refused = post(
            api, f"/command/runs/{RUN_ID}/actions", confirm_body(second.payload))
        assert (refused.status, refused.payload["error"]["code"]) == (
            409, "service_refused")
        # Nothing durable, nothing signalled, and no second effect: the refusal
        # landed before the request was minted, let alone before an adapter seam.
        assert journal.read_bytes() == before
        assert published[len(signalled):] == []
        assert kinds(store).count("action_request") == 1
        assert adapter.executions == 1
        assert coordinator.placements() == 1
    finally:
        adapter.gate.set()
        coordinator.shutdown()


def test_no_adapter_seam_is_reached_while_a_run_store_transaction_is_held(tmp_path):
    api, _store, coordinator, adapter, _ = an_api(tmp_path)
    try:
        confirm(api)
        assert coordinator.wait_idle(10) is True
        assert [seam for seam, _held in adapter.held_transactions] == [
            "prepare", "execute", "verify"]
        assert [held for _seam, held in adapter.held_transactions] == [
            False, False, False]
    finally:
        coordinator.shutdown()


def test_every_attempt_event_and_terminal_result_announces_the_run_id_alone(tmp_path):
    announced: list[object] = []
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(
        store, registry, clock=lambda: NOW, ids=mint, notify=announced.append)
    authorization = _authorize_one(store, registry, runtime, mint)
    coordinator = ExecutionCoordinator(runtime)
    coordinator.start()
    try:
        _place(coordinator, authorization)
        assert coordinator.wait_idle(10) is True
        # lease, observation, terminal receipt -- three facts, three bare run ids.
        assert announced == [RUN_ID, RUN_ID, RUN_ID]
        assert all(type(row) is str for row in announced)
    finally:
        coordinator.shutdown()


def _authorize_one(store, registry, runtime, mint, *, attempt_id="attempt-001"):
    """Propose and authorize one dispatch directly, without any HTTP boundary."""
    service = CommandService(store, registry, clock=lambda: NOW, ids=mint)
    proposal = service.propose(
        run_id=RUN_ID, instance_id=INSTANCE_ID, attempt_id=attempt_id,
        capability="dispatch", arguments=proposal_body()["arguments"],
        scope=("src", "tests"), proposed_by="claude-dev",
        rationale="Implement the reviewed work item.", timeout_seconds=900)
    confirmation = a_confirmation(proposal.proposal_id, proposal.preview_digest)
    authorization = runtime.authorize(confirmation, budget=BUDGET)
    assert authorization.record_created is True
    return authorization


def _place(coordinator, authorization):
    slot = coordinator.claim()
    try:
        slot.place(authorization)
    finally:
        slot.release()


def _lease(store, request, *, outcome=None, exit_code=None, event_id="lease-1",
           phase="effect_lease", recovery_ref="recovery-1"):
    """Append one durable attempt fact through the store's own existing door."""
    store.append(AttemptEvent(
        event_id=event_id, run_id=request.run_id, action_id=request.action_id,
        attempt_id=request.attempt_id, instance_id=request.instance_id,
        adapter_id=PROVIDER_ID, phase=phase, recorded_at=NOW,
        request_digest=action_request_digest(request), recovery_ref=recovery_ref,
        outcome=outcome, exit_code=exit_code, schema_version=2))


def test_a_lease_only_action_closes_unknown_without_reaching_the_adapter(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=mint)
    authorization = _authorize_one(store, registry, runtime, mint)
    _lease(store, authorization.request)
    adapter = registry.resolve(PROVIDER_ID)
    coordinator = ExecutionCoordinator(runtime)
    coordinator.start()
    try:
        _place(coordinator, authorization)
        assert coordinator.wait_idle(10) is True
        assert [row.outcome for row in results(store)] == ["unknown"]
        assert adapter.executions == 0
        assert adapter.held_transactions == []
    finally:
        coordinator.shutdown()


def test_an_observed_action_is_verified_and_never_executed_again(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=mint)
    authorization = _authorize_one(store, registry, runtime, mint)
    _lease(store, authorization.request)
    _lease(
        store, authorization.request, phase="execution_observed",
        outcome="succeeded", exit_code=0, event_id="observed-1")
    adapter = registry.resolve(PROVIDER_ID)
    coordinator = ExecutionCoordinator(runtime)
    coordinator.start()
    try:
        _place(coordinator, authorization)
        assert coordinator.wait_idle(10) is True
        assert [row.outcome for row in results(store)] == ["verification_failed"]
        assert adapter.executions == 0
        assert adapter.verifications == 1
        assert [seam for seam, _held in adapter.held_transactions] == ["verify"]
    finally:
        coordinator.shutdown()


def test_a_restarted_process_enqueues_nothing_and_repeats_no_effect(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=mint)
    _authorize_one(store, registry, runtime, mint)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    before = journal.read_bytes()

    restarted_registry = provider_registry(tmp_path, ids())
    restarted = ControlRuntime(
        RunStore(tmp_path), restarted_registry, clock=lambda: NOW, ids=ids())
    coordinator = ExecutionCoordinator(restarted)
    coordinator.start()
    try:
        assert coordinator.wait_idle(10) is True
        assert coordinator.placements() == 0
        assert restarted_registry.resolve(PROVIDER_ID).executions == 0
        assert journal.read_bytes() == before
        assert kinds(store) == ["action_proposal", "action_request"]
    finally:
        coordinator.shutdown()


def test_an_authorization_without_a_live_grant_reaches_no_adapter(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=mint)
    authorization = _authorize_one(store, registry, runtime, mint)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    before = journal.read_bytes()

    restarted_registry = provider_registry(tmp_path, ids())
    restarted = ControlRuntime(
        RunStore(tmp_path), restarted_registry, clock=lambda: NOW, ids=ids())
    coordinator = ExecutionCoordinator(restarted)
    coordinator.start()
    try:
        # A durable request is evidence of authorization, never execution authority.
        _place(coordinator, Authorization(
            request=authorization.request, record_created=True))
        assert coordinator.wait_idle(10) is True
        assert coordinator.refusals() == (authorization.request.action_id,)
        assert restarted_registry.resolve(PROVIDER_ID).executions == 0
        assert journal.read_bytes() == before
    finally:
        coordinator.shutdown()


def test_placing_an_authorization_that_created_no_request_is_refused(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=mint)
    authorization = _authorize_one(store, registry, runtime, mint)
    coordinator = ExecutionCoordinator(runtime)
    coordinator.start()
    try:
        slot = coordinator.claim()
        with pytest.raises(ExecutionRefused, match="created the durable request"):
            slot.place(Authorization(request=authorization.request))
        with pytest.raises(ExecutionRefused, match="Authorization from authorize"):
            slot.place(authorization.request)
        slot.release()
        assert coordinator.placements() == 0
        assert coordinator.wait_idle(10) is True
        assert registry.resolve(PROVIDER_ID).executions == 0
    finally:
        coordinator.shutdown()


def test_a_coordinator_retires_only_the_worker_whose_token_it_minted(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=mint)
    authorization = _authorize_one(store, registry, runtime, mint)
    owner = ExecutionCoordinator(runtime)
    stranger = ExecutionCoordinator(ControlRuntime(
        RunStore(tmp_path), registry, clock=lambda: NOW, ids=ids()))
    owner_token = owner.start()
    stranger_token = stranger.start()
    try:
        assert owner.owned_tokens() == (owner_token,)
        with pytest.raises(ExecutionOwnershipError, match="did not mint"):
            stranger.stop_worker(owner_token)
        with pytest.raises(ExecutionOwnershipError, match="did not mint"):
            owner.stop_worker(stranger_token)
        stranger.shutdown()
        # The stranger's shutdown retired its own worker and left this one working.
        assert stranger.owned_tokens() == ()
        assert owner.owned_tokens() == (owner_token,)
        _place(owner, authorization)
        assert owner.wait_idle(10) is True
        assert [row.outcome for row in results(store)] == ["verification_failed"]
    finally:
        owner.shutdown()
        stranger.shutdown()


def test_a_retired_coordinator_refuses_the_next_claim(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=mint)
    coordinator = ExecutionCoordinator(runtime)
    coordinator.start()
    coordinator.shutdown()
    assert coordinator.owned_tokens() == ()
    with pytest.raises(ExecutionRefused, match="not accepting actions"):
        coordinator.claim()


def test_an_api_binds_one_coordinator_and_only_over_its_own_runtime(tmp_path):
    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=mint,
        publish_run=lambda _run_id: None)
    foreign = ExecutionCoordinator(ControlRuntime(
        store, registry, clock=lambda: NOW, ids=ids()))
    assert api.execution is None
    with pytest.raises(ValueError, match="runtime that authorizes"):
        api.attach_execution(foreign)
    own = ExecutionCoordinator(api.runtime)
    api.attach_execution(own)
    assert api.execution is own
    with pytest.raises(ValueError, match="exactly one execution coordinator"):
        api.attach_execution(ExecutionCoordinator(api.runtime))


class _RetirementAtLockRelease:
    """Stand in for the coordinator lock and retire the fleet at ONE release.

    The race being held is not a line number, it is an INSTANT: the moment
    `claim` stops holding the coordinator lock. Wrapping the lock is how a test
    names that instant without naming the statements around it. If the
    reservation is already on a worker's inbox by then, every retirement queues
    behind it and the accepted action still runs; if it is not, the sentinel
    wins an empty queue, the worker leaves, and the reservation lands on an
    inbox no thread will drain again.

    The retirement runs on the claiming thread, so nothing here depends on
    scheduling. It fires once: `armed` is cleared before the retirement, which
    is what lets that retirement take the same lock without recursion.
    """

    def __init__(self, coordinator, retire):
        self._lock = coordinator._lock
        self._retire = retire
        self._coordinator = coordinator
        self.armed = False

    def __enter__(self):
        return self._lock.__enter__()

    def __exit__(self, *exc_info):
        released = self._lock.__exit__(*exc_info)
        if self.armed:
            self.armed = False
            self._retire(self._coordinator)
        return released


@pytest.mark.parametrize("retire", [
    lambda coordinator: coordinator.shutdown(timeout=0.0),
    lambda coordinator: coordinator.stop_worker(
        coordinator.owned_tokens()[0], timeout=0.0),
], ids=["shutdown", "stop_worker"])
def test_a_retirement_at_claims_lock_release_cannot_strand_an_accepted_action(
        tmp_path, retire):
    """A Confirm that was ANSWERED 201 is performed, whoever retires meanwhile.

    Both retirements remove a worker from the roster under the coordinator lock
    and place their sentinel only afterwards, so the whole question is whether
    the reservation reached the inbox before the lock went. Here it must have:
    the request is durable by the time anything could be retried, and an
    accepted action that no worker will ever drain is one this product can
    neither perform nor honestly report.

    The retirement is real -- the same public `shutdown`/`stop_worker` a server
    calls -- and it takes effect: what is asserted is not that retirement was
    prevented, but that it queued behind the action already admitted.
    """
    api, store, coordinator, adapter, _ = an_api(tmp_path)
    proposed = post(api, f"/command/runs/{RUN_ID}/proposals", proposal_body())
    assert proposed.status == 201, proposed.payload
    barrier = _RetirementAtLockRelease(coordinator, retire)
    coordinator._lock = barrier
    barrier.armed = True

    confirmed = post(
        api, f"/command/runs/{RUN_ID}/actions", confirm_body(proposed.payload))

    assert barrier.armed is False, "claim never released the lock under test"
    assert confirmed.status == 201, confirmed.payload
    assert "action_request" in kinds(store)
    assert coordinator.placements() == 1
    assert coordinator.wait_idle(10) is True
    assert adapter.executions == 1
    assert [row.outcome for row in results(store)] == ["verification_failed"]
