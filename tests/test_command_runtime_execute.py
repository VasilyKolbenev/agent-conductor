"""The execute state machine (A/RT-1): seven distinct states, unknown never success.

`ControlRuntime.execute` drives an authorized, unchanged request through
prepare -> execute -> verify -> one durable result receipt. The states it can
reach -- accepted, started, succeeded, failed, cancelled, unknown, and
verification_failed -- stay distinct: a crashed, empty, or foreign result is
`unknown`, never converted into success, and a process that merely reports
success must clear the verify seam before it reaches `succeeded`.

The scripted adapter here implements the four CMD-3 seams and nothing else; the
runtime derives it from the run's frozen config binding, so the same machine
drives an adapter registered under any id. The builders come from the authorize
circuit next door, which owns them.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conductor.command.adapters import (
    AdapterManifest,
    AdapterObservation,
    AdapterRegistry,
    AdapterVerification,
    PreparedAction,
)
from conductor.command.contracts import ActionRequest, ActionResultReceipt, EvidenceRef
from conductor.command.run_store import RecordConflict, RunStore
from conductor.command.runtime import (
    AttemptState,
    Authorization,
    ControlRuntime,
    ExecutionError,
)

from tests.test_command_runtime_authorize import (
    NOW,
    a_budget,
    a_confirmation,
    a_proposal,
    a_store,
    counting_ids,
    fixed_clock,
    fixed_ids,
)


class ScriptedAdapter:
    """A deterministic adapter whose execute and verify are scripted per scenario.

    It counts each seam it is asked to run, so a test can prove the runtime never
    verified a non-success, and it can be told to raise, to return a non-receipt,
    or to name another action -- the three ways a result goes missing.
    """

    def __init__(self, adapter_id="claude-code", *, execute_outcome="succeeded",
                 verify_state="unavailable", execute_raises=False, verify_raises=False,
                 foreign_result=False, non_receipt=False,
                 result_changes=None, verification_changes=None,
                 capabilities=("observe", "dispatch")):
        self.manifest = AdapterManifest(
            adapter_id=adapter_id, display_name="Scripted", vendor="Test",
            version="1", capabilities=capabilities, docs_url="")
        self._execute_outcome = execute_outcome
        self._verify_state = verify_state
        self._execute_raises = execute_raises
        self._verify_raises = verify_raises
        self._foreign_result = foreign_result
        self._non_receipt = non_receipt
        self._result_changes = dict(result_changes or {})
        self._verification_changes = dict(verification_changes or {})
        self.prepare_calls = 0
        self.execute_calls = 0
        self.verify_calls = 0

    def observe(self, instance_id, run_id):
        return AdapterObservation(
            adapter_id=self.manifest.adapter_id, instance_id=instance_id, run_id=run_id,
            observed_at=NOW, health="ready", available_capabilities=())

    def prepare(self, request):
        self.prepare_calls += 1
        return PreparedAction(
            adapter_id=self.manifest.adapter_id, request=request,
            adapter_payload={"operation": "dispatch"})

    def execute(self, prepared):
        self.execute_calls += 1
        if self._execute_raises:
            raise RuntimeError("scripted execute failure")
        if self._non_receipt:
            return "not a receipt"
        req = prepared.request
        exits = {
            "succeeded": 0, "failed": 7, "cancelled": None,
            "rejected": None, "unknown": None, "verification_failed": None,
        }
        values = {
            "receipt_id": "adapter-result",
            "action_id": "action-other" if self._foreign_result else req.action_id,
            "run_id": req.run_id, "attempt_id": req.attempt_id,
            "instance_id": req.instance_id, "outcome": self._execute_outcome,
            "observed_at": NOW, "exit_code": exits[self._execute_outcome],
        }
        values.update(self._result_changes)
        return ActionResultReceipt(**values)

    def verify(self, request, result):
        self.verify_calls += 1
        if self._verify_raises:
            raise RuntimeError("scripted verify failure")
        refs = ("scripted-evidence",) if self._verify_state == "verified" else ()
        values = {
            "adapter_id": self.manifest.adapter_id, "action_id": request.action_id,
            "state": self._verify_state, "observed_at": NOW,
            "detail": "scripted verification", "evidence_refs": refs,
        }
        values.update(self._verification_changes)
        return AdapterVerification(**values)


class VerifiedAdapter(ScriptedAdapter):
    """The only adapter here that can reach ``succeeded``, and it earns it.

    Succeeded is a three-legged relation: the process was OBSERVED to succeed,
    the bound adapter answered ``verified``, and the refs it named resolve to a
    durable ``EvidenceRef`` the store recorded AFTER that observation. This
    adapter writes that record itself -- the test-local stand-in for an
    independent evidence writer, since the adapter API returns refs and receives
    no append power of its own. Every other adapter in this module now
    terminates short of success, which is the point: no verifier is no proof.
    """

    def __init__(self, store, *, evidence_id="durable-evidence", **knobs):
        super().__init__(verify_state="verified", **knobs)
        self._store = store
        self._evidence_id = evidence_id

    def verify(self, request, result):
        self.verify_calls += 1
        self._store.append(EvidenceRef(
            evidence_id=self._evidence_id, run_id=request.run_id,
            kind="verification", uri=f"verification/{request.action_id}",
            label="durable verification fact", created_by=self.manifest.adapter_id,
            observed_at=NOW, verification="verified",
            verified_by=self.manifest.adapter_id, verified_at=NOW))
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state="verified", observed_at=NOW, detail="durable verification",
            evidence_refs=(self._evidence_id,))


def a_runtime(store, adapter, *, clock=None, ids=None):
    registry = AdapterRegistry([adapter])
    return ControlRuntime(store, registry, clock=clock or fixed_clock(), ids=ids or fixed_ids())


def authorized(store, adapter, *, proposal_changes=None, **runtime):
    """Seed a run, propose, and authorize -- the ground every execute test starts on."""
    proposal = a_proposal(store, **(proposal_changes or {}))
    runtime_obj = a_runtime(store, adapter, **runtime)
    authorization = runtime_obj.authorize(a_confirmation(proposal), budget=a_budget())
    return runtime_obj, authorization


def kinds(store, run_id="run-001"):
    return [row.kind for row in store.read(run_id).records]


def request_for(proposal):
    return ActionRequest(
        action_id="action-preexisting", run_id=proposal.run_id,
        attempt_id=proposal.attempt_id, instance_id=proposal.instance_id,
        capability=proposal.capability, arguments=proposal.arguments,
        scope=proposal.scope, requested_by="owner", requested_at=NOW,
        idempotency_key=f"dispatch-{proposal.proposal_id}",
        timeout_seconds=proposal.timeout_seconds,
        preview_digest=proposal.preview_digest, mode="confirm")



# -- non-success outcomes are themselves, and never trigger a verification --

@pytest.mark.parametrize("outcome,state", [
    ("failed", AttemptState.FAILED),
    ("cancelled", AttemptState.CANCELLED),
    ("unknown", AttemptState.UNKNOWN),
])
def test_a_non_success_process_keeps_its_outcome_and_is_never_verified(tmp_path, outcome, state):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(execute_outcome=outcome)
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is state
    assert attempt.receipt.outcome == outcome
    assert adapter.verify_calls == 0  # nothing to verify once it did not succeed
    assert "evidence" not in kinds(store)


# -- SABOTAGE (state distinctness): a crashed / empty / foreign attempt is unknown --

@pytest.mark.parametrize("adapter", [
    ScriptedAdapter(execute_raises=True),
    ScriptedAdapter(non_receipt=True),
    ScriptedAdapter(foreign_result=True),
], ids=["execute-raised", "no-receipt", "foreign-result"])
def test_a_missing_or_foreign_result_is_unknown_never_success(tmp_path, adapter):
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.UNKNOWN
    assert attempt.state is not AttemptState.SUCCEEDED
    assert attempt.receipt.outcome == "unknown"
    # A lost result is never verified as a success, and it still lands one receipt.
    assert adapter.verify_calls == 0
    assert kinds(store) == [
        "action_proposal", "action_request",
        "attempt_event", "attempt_event", "action_result"]


def test_started_is_entered_and_is_not_read_as_success(tmp_path):
    # The crash path proves `started` is a real state the machine passes through
    # and yet terminates `unknown`, so absence of a result never becomes success.
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(execute_raises=True)
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.history == (
        AttemptState.ACCEPTED, AttemptState.STARTED, AttemptState.UNKNOWN)
    assert AttemptState.STARTED in attempt.history
    assert attempt.state is not AttemptState.SUCCEEDED


def test_the_seven_attempt_states_are_seven_distinct_values():
    values = {state.value for state in AttemptState}
    assert len(values) == 7
    assert values == {
        "accepted", "started", "succeeded", "failed", "cancelled", "unknown",
        "verification_failed"}


def test_the_terminal_outcomes_reached_across_scenarios_do_not_collapse(tmp_path):
    # The succeeded scenario is the only one that earns its state: it observes a
    # success, verifies it, and leaves a causal durable record behind. The rest
    # reach four other terminals, and none of the five folds into another.
    scenarios = {
        "succeeded": VerifiedAdapter,
        "mismatch": lambda _store: ScriptedAdapter(verify_state="mismatch"),
        "failed": lambda _store: ScriptedAdapter(execute_outcome="failed"),
        "cancelled": lambda _store: ScriptedAdapter(execute_outcome="cancelled"),
        "crash": lambda _store: ScriptedAdapter(execute_raises=True),
    }
    reached = set()
    for index, build in enumerate(scenarios.values()):
        store = a_store(tmp_path / f"s{index}")
        runtime, authorization = authorized(store, build(store))
        reached.add(runtime.execute(authorization).state)
    # Five scenarios, five different terminal states -- none folded into another.
    assert reached == {
        AttemptState.SUCCEEDED, AttemptState.VERIFICATION_FAILED, AttemptState.FAILED,
        AttemptState.CANCELLED, AttemptState.UNKNOWN}


# -- adapter-agnostic: the runtime drives whatever the frozen config binds --

def test_the_runtime_drives_whatever_adapter_the_frozen_config_binds(tmp_path):
    # CONFIG binds 'codex-review' to the 'codex' adapter. The runtime resolves that
    # binding itself; it never names an adapter, so a scripted 'codex' is driven.
    store = a_store(tmp_path)
    adapter = VerifiedAdapter(store, adapter_id="codex")
    runtime, authorization = authorized(
        store, adapter, proposal_changes={"instance_id": "codex-review"})
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.request.instance_id == "codex-review"
    assert adapter.execute_calls == 1


# -- immutability: a recorded receipt is never rewritten in place --

def test_a_recorded_result_receipt_cannot_be_rewritten(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    recorded = attempt.receipt
    # A second receipt reusing the same id with a different outcome is a rewrite,
    # which the append-only store refuses; the durable outcome is unchanged.
    rewrite = ActionResultReceipt(
        receipt_id=recorded.receipt_id, action_id=recorded.action_id,
        run_id=recorded.run_id, attempt_id=recorded.attempt_id,
        instance_id=recorded.instance_id, outcome="failed", observed_at=NOW)
    with pytest.raises(RecordConflict):
        store.append(rewrite)
    results = [row.value for row in store.read("run-001").records
               if row.kind == "action_result"]
    assert len(results) == 1 and results == [recorded]


# -- execute refuses a request the store never authorized --

def test_execute_refuses_a_request_the_store_never_authorized(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    proposal = a_proposal(store)
    runtime = a_runtime(store, adapter)
    authorization = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    # A fresh store over the same tree that has the request removed cannot happen
    # through the API, so forge an Authorization for an action id nobody stored.
    forged = Authorization(request=authorization.request.__class__.from_dict(
        {**authorization.request.as_dict(), "action_id": "never-authorized",
         "idempotency_key": "dispatch-nowhere"}))
    with pytest.raises(ExecutionError, match="never authorized"):
        runtime.execute(forged)
    assert adapter.execute_calls == 0


@pytest.mark.parametrize("mode", ["observe", "propose", "policy"])
def test_direct_execute_refuses_preexisting_request_in_every_non_confirm_run(
        tmp_path, mode):
    store = a_store(tmp_path, mode=mode)
    proposal = a_proposal(store)
    request = request_for(proposal)
    store.append(request)
    journal = store.run_path("run-001") / "records.jsonl"
    before = journal.read_bytes()
    adapter = ScriptedAdapter()
    with pytest.raises(ExecutionError, match="requires run mode 'confirm'"):
        a_runtime(store, adapter).execute(Authorization(request=request))
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    assert journal.read_bytes() == before


def test_execute_refuses_same_id_with_changed_facts_before_prepare_or_append(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    forged = Authorization(request=authorization.request.__class__.from_dict({
        **authorization.request.as_dict(), "arguments": {"handoff": "forged"},
    }))
    with pytest.raises(ExecutionError, match="differs from its durable authorization"):
        runtime.execute(forged)
    assert adapter.execute_calls == 0
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before


@pytest.mark.parametrize("field,foreign", [
    ("run_id", "run-foreign"),
    ("action_id", "action-foreign"),
    ("attempt_id", "attempt-foreign"),
    ("instance_id", "instance-foreign"),
])
def test_execute_rejects_every_foreign_result_binding_field(
        tmp_path, field, foreign):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(result_changes={field: foreign})
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.UNKNOWN
    assert attempt.receipt.outcome == "unknown"
    assert adapter.verify_calls == 0


def test_direct_execute_refuses_a_hard_linked_journal_before_prepare(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    journal = store.run_path("run-001") / "records.jsonl"
    alias = tmp_path / "outside-journal.jsonl"
    try:
        import os
        os.link(journal, alias)
    except OSError as e:
        pytest.skip(f"hard links unavailable: {e}")
    before = alias.read_bytes()
    with pytest.raises(ExecutionError, match="hard links"):
        runtime.execute(authorization)
    assert adapter.prepare_calls == 0 and adapter.execute_calls == 0
    assert alias.read_bytes() == before and journal.read_bytes() == before


def test_execute_replays_a_durable_result_without_executing_twice(tmp_path):
    # A verified success is the richest thing to replay -- it carries evidence
    # refs the replay must resolve -- so the adapter here earns its state.
    store = a_store(tmp_path)
    adapter = VerifiedAdapter(store)
    runtime, authorization = authorized(store, adapter)
    first = runtime.execute(authorization)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    second = runtime.execute(authorization)
    assert second.receipt == first.receipt and second.state == first.state
    assert second.history == (
        AttemptState.ACCEPTED, AttemptState.STARTED, AttemptState.SUCCEEDED)
    assert adapter.execute_calls == 1
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before
    # A new runtime/process reconstructs from durable facts just as safely.
    fresh_adapter = ScriptedAdapter()
    replayed = a_runtime(store, fresh_adapter).execute(authorization)
    assert replayed.receipt == first.receipt
    assert fresh_adapter.execute_calls == 0


@pytest.mark.parametrize("outcome", [
    "succeeded", "failed", "cancelled", "rejected", "unknown",
    "verification_failed",
])
def test_terminal_replay_refuses_every_day1_outcome_with_evidence_refs(
        tmp_path, outcome):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    store.append(ActionResultReceipt(
        receipt_id="tampered-result", action_id=authorization.request.action_id,
        run_id="run-001", attempt_id=authorization.request.attempt_id,
        instance_id=authorization.request.instance_id, outcome=outcome,
        observed_at=NOW, evidence_refs=("tampered-evidence",)))
    fresh = ScriptedAdapter()
    with pytest.raises(ExecutionError, match="requires RT-2 causal attempt facts"):
        a_runtime(store, fresh).execute(authorization)
    assert fresh.prepare_calls == fresh.execute_calls == fresh.verify_calls == 0


def test_terminal_replay_refuses_duplicate_evidence_refs_before_any_adapter(tmp_path):
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, ScriptedAdapter())
    store.append(ActionResultReceipt(
        receipt_id="duplicate-result", action_id=authorization.request.action_id,
        run_id="run-001", attempt_id=authorization.request.attempt_id,
        instance_id=authorization.request.instance_id, outcome="failed",
        observed_at=NOW, evidence_refs=("same-evidence", "same-evidence")))
    fresh = ScriptedAdapter()
    with pytest.raises(ExecutionError, match="repeats an evidence ref"):
        a_runtime(store, fresh).execute(authorization)
    assert fresh.prepare_calls == fresh.execute_calls == fresh.verify_calls == 0


def test_an_evidence_free_terminal_result_replays_without_adapter_calls(tmp_path):
    """A terminal receipt naming no evidence is still terminal, and still replays.

    This used to be the unavailable-success case. The outcome it lands on has
    changed -- an adapter with no verifier proves nothing -- but the relation is
    the same one it always held: once a terminal result is durable, a second
    execute reproduces it out of the journal and touches no adapter seam.
    """
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, ScriptedAdapter())
    first = runtime.execute(authorization)
    assert first.state is AttemptState.VERIFICATION_FAILED
    assert first.receipt.evidence_refs == ()
    fresh = ScriptedAdapter()
    replayed = a_runtime(store, fresh).execute(authorization)
    assert replayed.receipt == first.receipt
    assert fresh.prepare_calls == fresh.execute_calls == fresh.verify_calls == 0


def test_fresh_runtime_refuses_request_only_history_without_reexecuting(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    fresh_adapter = ScriptedAdapter()
    with pytest.raises(ExecutionError, match="requires reconciliation"):
        a_runtime(store, fresh_adapter).execute(authorization)
    assert fresh_adapter.prepare_calls == fresh_adapter.execute_calls == 0
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before


def test_observed_pre_result_retry_resolves_without_a_second_effect(
        tmp_path, monkeypatch):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()

    def crash_before_result(*args, **kwargs):
        raise ExecutionError("simulated crash before result append")

    finish = runtime._finish
    monkeypatch.setattr(runtime, "_finish", crash_before_result)
    with pytest.raises(ExecutionError, match="simulated crash"):
        runtime.execute(authorization)
    assert adapter.execute_calls == 1
    monkeypatch.setattr(runtime, "_finish", finish)
    attempt = runtime.execute(authorization)
    # The retry resolves from the durable observation alone: no second effect,
    # and no verifier behind this adapter, so it resolves short of success.
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert adapter.execute_calls == 1
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() != before


@pytest.mark.parametrize("phase", ["prepare", "execute", "verify"])
def test_untrusted_in_place_identity_rewrite_cannot_steal_another_authorization(
        tmp_path, phase):
    class MutatingAdapter(ScriptedAdapter):
        target = None

        def _rewrite(self, request):
            for field in ("run_id", "action_id", "attempt_id", "instance_id"):
                object.__setattr__(request, field, getattr(self.target, field))

        def prepare(self, request):
            if phase == "prepare":
                self._rewrite(request)
            return super().prepare(request)

        def execute(self, prepared):
            if phase == "execute":
                self._rewrite(prepared.request)
            return super().execute(prepared)

        def verify(self, request, result):
            if phase == "verify":
                self._rewrite(request)
            return super().verify(request, result)

    store = a_store(tmp_path)
    adapter = MutatingAdapter()
    runtime = a_runtime(store, adapter, ids=counting_ids())
    first_proposal = a_proposal(store, proposal_id="proposal-first")
    first = runtime.authorize(a_confirmation(first_proposal), budget=a_budget())
    second_proposal = a_proposal(
        store, proposal_id="proposal-second", attempt_id="attempt-second")
    second = runtime.authorize(a_confirmation(second_proposal), budget=a_budget())
    adapter.target = second.request

    attempt = runtime.execute(first)
    assert attempt.request.action_id == first.request.action_id
    assert attempt.request.action_id != second.request.action_id
    results = [row.value for row in store.read("run-001").records
               if row.kind == "action_result"]
    assert len(results) == 1 and results[0].action_id == first.request.action_id
    assert all(result.action_id != second.request.action_id for result in results)


def test_prepare_failure_records_unknown_and_never_executes(tmp_path):
    class BrokenPrepare(ScriptedAdapter):
        def prepare(self, request):
            raise RuntimeError("prepare broke")

    store = a_store(tmp_path)
    adapter = BrokenPrepare()
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.UNKNOWN
    assert attempt.history == (AttemptState.ACCEPTED, AttemptState.UNKNOWN)
    assert attempt.receipt.outcome == "unknown"
    assert adapter.execute_calls == 0
    assert kinds(store) == ["action_proposal", "action_request", "action_result"]


@pytest.mark.parametrize("phase", ["prepare", "execute", "verify"])
def test_adapter_exception_secrets_never_reach_durable_or_returned_receipts(
        tmp_path, phase):
    class_secret = "APIKEY_SECRET_IN_CLASS_NAME"
    message_secret = "APIKEY-secret-in-exception-message"
    SecretFailure = type(class_secret, (RuntimeError,), {})

    class SecretAdapter(ScriptedAdapter):
        def prepare(self, request):
            if phase == "prepare":
                raise SecretFailure(message_secret)
            return super().prepare(request)

        def execute(self, prepared):
            if phase == "execute":
                raise SecretFailure(message_secret)
            return super().execute(prepared)

        def verify(self, request, result):
            if phase == "verify":
                raise SecretFailure(message_secret)
            return super().verify(request, result)

    store = a_store(tmp_path)
    runtime, authorization = authorized(store, SecretAdapter())
    attempt = runtime.execute(authorization)
    durable = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    for secret in (class_secret, message_secret):
        assert secret not in repr(attempt)
        assert secret not in str(attempt.receipt.as_dict())
        assert secret.encode() not in durable


@pytest.mark.parametrize("outcome", [
    "succeeded", "failed", "cancelled", "rejected", "unknown",
    "verification_failed",
])
def test_adapter_result_free_text_never_reaches_attempt_or_durable_state(
        tmp_path, outcome):
    secret = f"RESULT-SECRET-{outcome}"
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(
        execute_outcome=outcome,
        result_changes={"detail": secret})
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert secret not in repr(attempt)
    assert secret.encode() not in store.run_path("run-001").joinpath(
        "records.jsonl").read_bytes()

# -- the runtime starts no process itself; every execution goes through an adapter --

def test_the_runtime_source_opens_no_machine_or_process_door():
    """Execution is delegated to an adapter through the CMD-3 seams, so the module
    imports only value and sibling modules -- never a subprocess, os, socket, or
    shutil door of its own. An allowlist fails closed: a new stdlib import is a
    failure until it is reviewed and named here.
    """
    from conductor.command import runtime as runtime_module
    tree = ast.parse(Path(runtime_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level >= 1:
                continue  # a sibling module inside the command package
            imported.add(node.module or "")
    allowed = {
        "__future__", "collections.abc", "dataclasses", "datetime", "enum",
        "threading", "typing", "weakref",
    }
    assert imported <= allowed, sorted(imported - allowed)
