"""The Day-1 control-loop gate, driven from the CLI against an in-process adapter.

`conduct confirm` runs the whole lane-A loop end to end on a fixed, deterministic
scenario: it opens (or creates) a run with a frozen config, proposes one dispatch,
authorizes a fresh Human confirmation of that exact proposal, executes it through
an in-process fake adapter, verifies, and prints the canonical result receipt --
the immutable outcome record -- for inspection. It spawns no process and reaches
no browser; the adapter is in-process and its "execution" is a deterministic
return, so the receipt proves the state machine, not a real harness.

The scenario is fixed so the printed receipt is reproducible: the same frozen
config, the same deterministic ids and clock, and the same fresh confirmation
every time. Reopening the run is idempotent -- the proposal, the authorized
request, the verification evidence, and the result receipt are all immutable, so a
second run appends nothing and prints the same bytes.

The gate does NOT carry `conduct preview`'s byte-level route containment: it opens
a run at a fixed id under whatever `--dir` names, and a foreign run standing at
that id is refused (exit 1) when its frozen config or recorded facts disagree with
this scenario, but the guarantee here is an honest refusal, not preview's proven
inertness. The whole flow is upstream of any real execution surface.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .adapters import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterRegistry,
    AdapterVerification,
    PreparedAction,
)
from .contracts import ActionResultReceipt, RunEnvelope, canonical_json
from .run_store import RunExists, RunStore, StoreError, snapshot_digest
from .runtime import (
    AuthorizationError,
    Budget,
    Confirmation,
    ControlRuntime,
    ExecutionError,
)
from .service import CommandService, ServiceError

#: The one frozen configuration this gate pins; its instances section binds the
#: instance the loop drives to the in-process adapter registered below.
FROZEN_CONFIG: Mapping[str, Any] = {
    "cycle": {"id": "control-loop-orbit", "phases": ["dispatch"]},
    "instances": [{"id": "claude-dev", "adapter": "claude-code"}],
}

_RUN_ID = "control-loop-run"
_ATTEMPT_ID = "control-loop-attempt"
_INSTANCE_ID = "claude-dev"
_NOW = "2026-08-11T00:00:00Z"
_ARGUMENTS: Mapping[str, Any] = {"handoff": "control-loop-packet"}
_SCOPE = ("src",)
_ACTOR = "release-owner"
_RATIONALE = "Day-1 control loop: confirm one dispatch and execute it end to end."
_TIMEOUT_SECONDS = 900
_BUDGET = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)


class GateError(RuntimeError):
    """The control-loop gate cannot produce a result receipt to inspect."""


def _loop_id(purpose: str) -> str:
    """Mint every id the gate uses; deterministic, so a rerun is byte-identical."""
    return f"{purpose}-{_RUN_ID}"


class _LoopAdapter:
    """A minimal in-process adapter: it dispatches deterministically and verifies.

    Unlike the preview's adapter, this one implements execute and verify, because
    the loop drives them. Both are pure returns -- no process is ever spawned.
    """

    def __init__(self) -> None:
        self.manifest = AdapterManifest(
            adapter_id="claude-code", display_name="Claude Code", vendor="Anthropic",
            version="1", capabilities=("observe", "dispatch"), docs_url="")

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation:
        return AdapterObservation(
            adapter_id="claude-code", instance_id=instance_id, run_id=run_id,
            observed_at=_NOW, health="ready", available_capabilities=("observe", "dispatch"))

    def prepare(self, request: Any) -> PreparedAction:
        return PreparedAction(
            adapter_id="claude-code", request=request,
            adapter_payload={"operation": "dispatch", "handoff": "control-loop-packet"})

    def execute(self, prepared: Any) -> ActionResultReceipt:
        req = prepared.request
        return ActionResultReceipt(
            receipt_id=_loop_id("adapter-result"), action_id=req.action_id,
            run_id=req.run_id, attempt_id=req.attempt_id, instance_id=req.instance_id,
            outcome="succeeded", observed_at=_NOW, exit_code=0,
            detail="the in-process adapter dispatched the handoff deterministically")

    def verify(self, request: Any, result: Any) -> AdapterVerification:
        return AdapterVerification(
            adapter_id="claude-code", action_id=request.action_id, state="verified",
            observed_at=_NOW, detail="handoff packet observed in the fake transport",
            evidence_refs=("adapter-evidence",))


def _open_run(store: RunStore) -> RunEnvelope:
    envelope = RunEnvelope(
        run_id=_RUN_ID, cycle_id="control-loop-orbit", created_at=_NOW,
        config_digest=snapshot_digest(FROZEN_CONFIG), mode="confirm")
    try:
        store.create_run(envelope, FROZEN_CONFIG)
    except RunExists:
        pass  # reopen: every record below is immutable, so the rerun is idempotent
    return envelope


def render_control_loop(project_root: str) -> str:
    """Run the fixed control loop and return the canonical result receipt.

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
    registry = AdapterRegistry([_LoopAdapter()])
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
