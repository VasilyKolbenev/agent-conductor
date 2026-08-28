"""The Day-1 control-loop gate, driven through the owned-process adapter.

`conduct integration-smoke` runs the whole Day-1 A+B loop end to end on a fixed,
deterministic synthetic scenario: it opens (or creates) a run with a frozen config,
proposes one dispatch, records a labelled synthetic confirmation fixture, executes it through
the owned-process adapter against a packaged no-op executable, and prints the
canonical result receipt -- the immutable outcome record -- for inspection. It
reaches no browser and accepts
no caller command text; the fixed structured argv still crosses the real spawn,
timeout, process-group ownership and bounded-output surface.

The receipt this gate prints is ``verification_failed``, and that IS the passing
result. The owned-process adapter watches a process; it holds no independent
check of what the process did, so it answers ``unavailable`` -- and the runtime
never turns that into product success. The loop is proved end to end by the
durable record it leaves (a proposal, a request, a lease, an observation whose
own outcome is ``succeeded``, and one immutable result), not by a success token
this build cannot back with evidence.

This is not the product Confirm surface and records no Human assertion. Product
confirmation arrives through the later server-owned API boundary. The fixture is
fixed so the printed receipt is reproducible: the same frozen
config, the same deterministic ids and clock, and the same synthetic fixture confirmation
every time. Reopening the run is idempotent -- the proposal, the authorized
request and the result receipt are immutable, so a
second run appends nothing and prints the same bytes.

The same command-layer containment and identity doors used by preview run before
creation, replay, confirmation, or execution.  A foreign run or a portal/alias
on the store route is refused read-only: no proposal is first planted into state
the gate did not create. A refused road reaches no spawn; the successful road
does cross the owned-process surface described above.

Reopening also REPAIRS one thing, because this gate is the single writer the run
store reserves repair to. A crash inside an append leaves a newline-free tail on
records.jsonl; `read` reports it and leaves it in place, so without a repair the
run warns about itself forever and every later smoke refuses it. Once the route,
the frozen envelope and config, the surviving history and the run directory's
own contents have all agreed the run is this loop's, `recover` truncates that
tail and the identity door is put to the repaired history again. Nothing else is
repaired: a complete record that breaks a contract or a relation is corruption,
refused with the store's own line number and left byte-for-byte alone, and a
history this loop does not write -- including a terminal an operator recorded
through `ControlRuntime.reconcile` -- is refused as foreign. The recovery for
those is a fresh directory, which yields the identical receipt.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any

from .adapters import (
    AdapterContractError,
    AdapterRegistry,
)
from .adapters.process import ProcessAdapter, ProcessRunner
from . import _smoke_exec
from .attempts import AttemptEvent, action_request_digest
from .containment import (
    render_legacy_run_route_violations,
    run_route_violations,
    unowned_paths,
)
from .contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    ControlMode,
    RunEnvelope,
    _freeze_json,
    canonical_json,
)
from .identity import history_is_one_of, mapping_differences
from .run_store import (
    RecoveredRun,
    RunExists,
    RunStore,
    StoreError,
    StoredRecord,
    snapshot_digest,
)
from .runtime import (
    AuthorizationError,
    Budget,
    Confirmation,
    ControlRuntime,
    ExecutionError,
)
from .service import CommandService, ServiceError

#: The one frozen configuration this gate pins; its instances section binds the
#: instance the loop drives to the owned-process adapter registered below.
FROZEN_CONFIG: Mapping[str, Any] = {
    "cycle": {"id": "control-loop-orbit", "phases": ["dispatch"]},
    "instances": [{"id": "claude-dev", "adapter": "owned-process"}],
}
_REPLAYED_FROZEN_CONFIG = _freeze_json(dict(FROZEN_CONFIG))

_RUN_ID = "control-loop-run"
_ATTEMPT_ID = "control-loop-attempt"
_INSTANCE_ID = "claude-dev"
_NOW = "2026-08-11T00:00:00Z"
_ARGUMENTS: Mapping[str, Any] = {
    "argv": [sys.executable, str(Path(_smoke_exec.__file__).resolve())],
    "cwd": "conductor/runs",
    "env_allow": [],
    "output_limit": 4096,
}
_SCOPE = ("src",)
_ACTOR = "synthetic-integration-smoke"
_RATIONALE = "Synthetic integration smoke: authorize one no-op dispatch end to end."
_TIMEOUT_SECONDS = 900
_BUDGET = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)


class GateError(RuntimeError):
    """The control-loop gate cannot produce a result receipt to inspect."""


def _loop_id(purpose: str) -> str:
    """Mint every id the gate uses; deterministic, so a rerun is byte-identical."""
    return f"{purpose}-{_RUN_ID}"


def _open_run(store: RunStore) -> RunEnvelope:
    envelope = RunEnvelope(
        run_id=_RUN_ID, cycle_id="control-loop-orbit", created_at=_NOW,
        config_digest=snapshot_digest(FROZEN_CONFIG), mode="confirm")
    run_path = store.run_path(_RUN_ID)
    violations = run_route_violations(store, _RUN_ID)
    facts = render_legacy_run_route_violations(violations, run_path)
    if facts:
        raise GateError(
            f"run {_RUN_ID!r} is not on a contained writable route: "
            + "; ".join(facts))
    try:
        store.create_run(envelope, FROZEN_CONFIG)
    except RunExists:
        found = store.read(_RUN_ID)
        _hold_own_facts(envelope, found)
        try:
            foreign = unowned_paths(store.run_path(_RUN_ID))
        except OSError as e:
            raise GateError(
                f"run {_RUN_ID!r} contains state the identity gate cannot read") from e
        if foreign:
            raise GateError(
                f"run {_RUN_ID!r} holds unowned durable objects: {list(foreign)!r}")
        if found.warnings:
            _repair_own_run(store, envelope)
    return envelope


def _hold_own_facts(envelope: RunEnvelope, found: RecoveredRun) -> None:
    """Refuse a run standing at this gate's fixed id whose facts are not its own.

    A replay warning is deliberately NOT one of these refusals. It says a crash
    interrupted one of this writer's own appends, which is a different fact from
    somebody else having written the journal, and folding the two together made
    the gate answer the second question when it had only been asked the first.
    """
    differences = mapping_differences(envelope.as_dict(), found.envelope.as_dict())
    if differences or found.config != _REPLAYED_FROZEN_CONFIG:
        raise GateError(
            f"run {_RUN_ID!r} already exists with foreign envelope/config facts")
    if not history_is_one_of(found.records, _expected_histories(envelope)):
        raise GateError(
            f"run {_RUN_ID!r} already exists with history this loop did not write")


def _repair_own_run(store: RunStore, envelope: RunEnvelope) -> None:
    """Finish the append a crash cut in half, as the one writer entitled to.

    `read` never edits a durable byte, so a newline-free tail left by a killed
    or out-of-space `_append_bytes` survives every later read and warns about
    itself forever. `recover` truncates it, and the store reserves that to the
    single writer of the run -- which, for this fixed id, is this gate. It is
    called only once the route, the frozen envelope, the history and the run
    directory's own contents have all agreed the run is this loop's, and before
    a proposal is put anywhere near it.

    The gate repairs explicitly rather than let it happen underneath: every
    `append` recovers first, so the propose that follows would truncate the tail
    on its own -- but only AFTER the identity door had passed judgment on a
    prefix missing its last line, and only as a property of `CommandService`
    that this gate does not get to promise. Here the run is whole, and judged
    whole, before anything is proposed into it.

    Only an interrupted final line is repairable. A complete record that
    contradicts its contract or its neighbours is `CorruptRun`, raised out of
    the read above and reported with the store's own line number; recovery is
    never reached for it and never rewrites it.

    The verdict is then taken from a fresh `read`, not from what `recover`
    returned: recover reports the repairs it MADE as warnings of its own, so
    only a plain read can say whether any unjudged byte is still there.
    """
    store.recover(_RUN_ID)
    repaired = store.read(_RUN_ID)
    _hold_own_facts(envelope, repaired)
    if repaired.warnings:
        raise GateError(
            f"run {_RUN_ID!r} still replays with durable bytes this loop's own writer "
            "could not repair: " + "; ".join(repaired.warnings))


def _loop_event(
        request: ActionRequest, phase: str, *,
        outcome: str | None = None, exit_code: int | None = None) -> AttemptEvent:
    """Build one deterministic event for the fixed synthetic scenario."""
    return AttemptEvent(
        event_id=_loop_id(f"{phase}-event"), run_id=_RUN_ID,
        action_id=request.action_id, attempt_id=request.attempt_id,
        instance_id=request.instance_id, adapter_id="owned-process",
        phase=phase, recorded_at=_NOW,
        request_digest=action_request_digest(request),
        recovery_ref=_loop_id("recovery"), outcome=outcome,
        exit_code=exit_code, schema_version=2)


def _expected_histories(envelope: RunEnvelope) -> tuple[tuple[StoredRecord, ...], ...]:
    """Every prefix this deterministic loop may itself leave, contract-derived."""
    proposal = ActionProposal(
        proposal_id=_loop_id("proposal"), run_id=_RUN_ID, attempt_id=_ATTEMPT_ID,
        instance_id=_INSTANCE_ID, capability="dispatch", arguments=_ARGUMENTS,
        scope=_SCOPE, proposed_by="control-loop", proposed_at=_NOW,
        timeout_seconds=_TIMEOUT_SECONDS, rationale=_RATIONALE,
        config_digest=envelope.config_digest)
    request = ActionRequest(
        action_id=_loop_id("action"), run_id=_RUN_ID, attempt_id=_ATTEMPT_ID,
        instance_id=_INSTANCE_ID, capability="dispatch", arguments=_ARGUMENTS,
        scope=_SCOPE, requested_by=_ACTOR, requested_at=_NOW,
        idempotency_key=f"dispatch-{proposal.proposal_id}",
        timeout_seconds=_TIMEOUT_SECONDS, preview_digest=proposal.preview_digest,
        mode=ControlMode.CONFIRM)
    result = ActionResultReceipt(
        receipt_id=_loop_id("result"), action_id=request.action_id, run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID, instance_id=_INSTANCE_ID,
        outcome="verification_failed", observed_at=_NOW, evidence_refs=(),
        detail="execution observed; the adapter exposed no verifier, so nothing "
               "about the work is verified",
        exit_code=0)
    lease = _loop_event(request, "effect_lease")
    observed = _loop_event(
        request, "execution_observed", outcome="succeeded", exit_code=0)
    rows = (
        StoredRecord("action_proposal", proposal),
        StoredRecord("action_request", request),
        StoredRecord("attempt_event", lease),
        StoredRecord("attempt_event", observed),
        StoredRecord("action_result", result),
    )
    unknown = ActionResultReceipt.from_dict({
        **result.as_dict(), "outcome": "unknown", "exit_code": None,
        "detail": "effect lease has no durable observation; execution was not repeated",
    })
    # A durable request without a terminal result is ambiguous: execution may
    # have happened before a crash.  It must not be resumed automatically.
    # The terminal `ControlRuntime.reconcile` writes over such a request is
    # deliberately NOT listed. Every prefix here is one this gate writes itself,
    # the lease-only `unknown` below included; an operator's terminal is not,
    # and admitting it would let the gate exit 0 printing a receipt whose
    # dispatch never crossed the spawn surface this gate exists to prove.
    return ((), rows[:1], rows[:2], rows[:3], rows[:4], rows,
            (*rows[:3], StoredRecord("action_result", unknown)))


def render_integration_smoke(project_root: str) -> str:
    """Run the fixed synthetic loop and return the canonical result receipt.

    Args:
        project_root: The directory holding (or to hold) ``conductor/runs``.

    Returns:
        The canonical JSON of the immutable ActionResultReceipt the loop recorded.

    Raises:
        GateError: The run cannot be opened as this scenario's own, the confirmation
            cannot be authorized, or the attempt cannot be driven -- each wrapped
            from the service, store, or runtime that refused it.
    """
    store = RunStore(project_root)
    runner = ProcessRunner(store.project_root)
    registry = AdapterRegistry([ProcessAdapter(
        "owned-process", runner, clock=lambda: _NOW, ids=_loop_id)])
    clock, ids = (lambda: _NOW), _loop_id
    try:
        envelope = _open_run(store)
        proposal = CommandService(store, registry, clock=clock, ids=ids).propose(
            run_id=_RUN_ID, instance_id=_INSTANCE_ID, attempt_id=_ATTEMPT_ID,
            capability="dispatch", arguments=_ARGUMENTS, scope=_SCOPE,
            proposed_by="control-loop", rationale=_RATIONALE,
            timeout_seconds=_TIMEOUT_SECONDS)
        runtime = ControlRuntime(store, registry, clock=clock, ids=ids)
        confirmation = Confirmation(
            confirmation_id=_loop_id("confirmation"), run_id=_RUN_ID,
            proposal_id=proposal.proposal_id, preview_digest=proposal.preview_digest,
            capability="dispatch", scope=_SCOPE, config_digest=envelope.config_digest,
            confirmed_by=_ACTOR, confirmed_at=_NOW)
        authorization = runtime.authorize(confirmation, budget=_BUDGET)
        attempt = runtime.execute(authorization)
    except (ServiceError, StoreError, AuthorizationError, ExecutionError,
            AdapterContractError) as e:
        raise GateError(str(e)) from e
    return canonical_json(attempt.receipt)
