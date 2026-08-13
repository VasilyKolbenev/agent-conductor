"""The minimal Confirm state machine: authorize -> prepare -> execute -> verify -> result.

This module is the runtime seam A/CONF-1 and A/RT-1 own. It executes nothing on
import, spawns no process, and reaches no browser: it drives whatever adapter a
run's frozen configuration binds to an instance, through the CMD-3 adapter seams,
and records durable facts through the frozen CMD-2 run store. It never adds a
store record type and never edits a frozen surface -- every durable fact here is
one of the six the store already knows.

Authorization comes first, and it refuses BEFORE preparation. `authorize` takes a
fresh Human `Confirmation` for one already-proposed dispatch and holds every fact
the confirmation restates against the run's own durable state: the canonical
preview digest of the stored proposal, the scope, the capability, and the frozen
configuration digest, plus the confirmation's freshness and the run's action and
time budgets. ANY changed or stale fact is an `AuthorizationError`, raised before
the adapter is prepared and before one durable byte is written -- the refusing
paths A/CONF-1 owns. Only when every fact clears does authorize mint the
`ActionRequest` that records the confirmation and append it: that request carries
the confirming human (`requested_by`), the freshness instant (`requested_at`), and
the exact confirmed digest (`preview_digest`), so it IS the confirmation recorded
as its own store record, separate from any result receipt, and the store's
RecordConflict (CMD-2) guards its identity and its idempotency key. A second
authorization that mints a fresh action id for the same proposal reuses that key
and is refused with no second durable effect.

`execute` then drives the authorized, unchanged request through the state machine.
Its states -- accepted, started, succeeded, failed, cancelled, unknown, and
verification_failed -- stay DISTINCT: none is inferred from the absence of
another, and an attempt whose adapter crashed, returned no result, or reported a
result for another action is `unknown`, never converted into success. A process
that reports success is put to the adapter's verify seam, but Day-1 has no durable
execution-observed fact that could bind later evidence causally. Therefore a
`verified`, `mismatch`, or `error` response reaches `verification_failed`, while
`unavailable` leaves observed success standing but explicitly unverified. The
runtime owns one durable result receipt per attempt; its outcome is the reconciled
terminal state, appended beside -- never over -- the request that authorized it.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .adapters import AdapterRegistry, AdapterVerification, PreparedAction
from .containment import render_legacy_run_route_violations, run_route_violations
from .contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    ControlMode,
    EvidenceRef,
    _digest,
    _id,
    _mode,
    _scope,
    _thaw_json,
    _timestamp,
    frozen_config_bindings,
)
from .run_store import RecoveredRun, RunStore


class AuthorizationError(RuntimeError):
    """A confirmation fact is changed or stale; the action is refused before preparation."""


class ExecutionError(RuntimeError):
    """The runtime cannot drive a request the store never authorized or cannot bind."""


class AttemptState(str, Enum):
    """The seven states A/RT-1 keeps distinct; absence is never one of the others.

    ``accepted`` and ``started`` are pre-terminal machine states; the remaining
    five are the terminal outcomes the durable result receipt records. None is
    ever inferred from the absence of another, and ``unknown`` is never promoted
    to ``succeeded``.
    """

    ACCEPTED = "accepted"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    VERIFICATION_FAILED = "verification_failed"


#: A raw execute-reported outcome that is not ``succeeded`` maps here without ever
#: touching ``succeeded``: an unknown process stays unknown, a rejected one is not
#: a success, and a self-declared verification_failed is honoured as such.
_NON_SUCCESS: dict[str, AttemptState] = {
    "failed": AttemptState.FAILED,
    "cancelled": AttemptState.CANCELLED,
    "unknown": AttemptState.UNKNOWN,
    "rejected": AttemptState.FAILED,
    "verification_failed": AttemptState.VERIFICATION_FAILED,
}


def _instant(name: str, value: object) -> datetime:
    """Parse one validated RFC 3339 UTC timestamp into an aware datetime."""
    text = _timestamp(name, value)
    return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)


@dataclass(frozen=True)
class Confirmation:
    """A fresh Human confirmation authorizing one exact stored proposal to execute.

    It restates, in the human's own words, every fact authorization holds against
    the run's durable state: which proposal, the preview digest they saw, the
    scope and capability they approved, and the frozen configuration they approved
    under. ``confirmed_at`` is the freshness instant, ``mode`` is always Confirm --
    Policy authorization is a separate, later seam this class does not express.
    """

    confirmation_id: str
    run_id: str
    proposal_id: str
    preview_digest: str
    capability: str
    scope: tuple[str, ...]
    config_digest: str
    confirmed_by: str
    confirmed_at: str
    mode: ControlMode | str = ControlMode.CONFIRM

    def __post_init__(self) -> None:
        for name in ("confirmation_id", "run_id", "proposal_id", "capability",
                     "confirmed_by"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "preview_digest", _digest("preview_digest", self.preview_digest))
        object.__setattr__(self, "config_digest", _digest("config_digest", self.config_digest))
        object.__setattr__(self, "scope", _scope(self.scope))
        object.__setattr__(self, "confirmed_at", _timestamp("confirmed_at", self.confirmed_at))
        mode = _mode(self.mode)
        if mode is not ControlMode.CONFIRM:
            raise ContractError("a Human confirmation must carry mode 'confirm'")
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True)
class Budget:
    """The action and time budgets an authorization is held within.

    ``max_actions`` caps how many action requests one run may authorize;
    ``max_action_seconds`` caps a single action's declared timeout; and
    ``max_confirmation_age_seconds`` is the freshness window a confirmation must
    fall inside. All three refuse before preparation when exceeded.
    """

    max_actions: int
    max_action_seconds: int
    max_confirmation_age_seconds: int

    def __post_init__(self) -> None:
        for name in ("max_actions", "max_action_seconds", "max_confirmation_age_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError(f"{name} must be an integer >= 1, got {value!r}")


@dataclass(frozen=True)
class Authorization:
    """A cleared confirmation: the durable authorized request, held at ``accepted``."""

    request: ActionRequest
    state: AttemptState = AttemptState.ACCEPTED

    def __post_init__(self) -> None:
        if not isinstance(self.request, ActionRequest):
            raise ContractError("Authorization.request must be an ActionRequest")
        object.__setattr__(
            self, "request", ActionRequest.from_dict(self.request.as_dict()))
        if self.state is not AttemptState.ACCEPTED:
            raise ContractError("Authorization starts in accepted state")


@dataclass(frozen=True)
class Attempt:
    """One executed attempt: its terminal state, the state path it took, and receipt.

    ``history`` records only states this process observed. A live execute that
    crossed preparation includes ``accepted, started, terminal``; prepare refusal
    is ``accepted, unknown``; replay of an existing result is ``accepted,
    terminal`` because v2 durable records cannot prove a prior process entered
    started. ``receipt`` is the immutable terminal record; verification evidence
    is empty in Day-1; RT-2 must add causal attempt facts before evidence can bind.
    """

    request: ActionRequest
    state: AttemptState
    receipt: ActionResultReceipt
    history: tuple[AttemptState, ...]
    verification_evidence: tuple[EvidenceRef, ...] = ()


class ControlRuntime:
    """Drive any registered adapter through authorize -> execute -> verify -> receipt.

    The runtime is adapter-agnostic: it derives the adapter from the run's frozen
    configuration binding, never from a caller's word, so it drives whatever
    adapter a project configured. Ids and the clock arrive through injected
    deterministic providers; nothing here reads a hidden clock or invents an id.
    """

    def __init__(
            self, store: RunStore, registry: AdapterRegistry, *,
            clock: Callable[[], str], ids: Callable[[str], str]) -> None:
        self._store = store
        self._registry = registry
        self._clock = clock
        self._ids = ids
        # Memory-only execution authority. A durable request recovered by a new
        # runtime is evidence of authorization, not proof its effect never ran.
        self._grants: set[tuple[str, str]] = set()

    # -- authorize (A/CONF-1): refuse before preparation, else record the confirmation --

    def authorize(self, confirmation: Confirmation, *, budget: Budget) -> Authorization:
        """Authorize one confirmed proposal, or refuse; record the cleared request."""
        if not isinstance(confirmation, Confirmation):
            raise AuthorizationError("authorize requires a validated Confirmation")
        if not isinstance(budget, Budget):
            raise AuthorizationError("authorize requires a validated Budget")
        self._hold_route(confirmation.run_id, AuthorizationError)
        recovered = self._store.read(confirmation.run_id)
        if recovered.envelope.mode is not ControlMode.CONFIRM:
            raise AuthorizationError("Confirm runtime requires run mode 'confirm'")
        if recovered.warnings:
            raise AuthorizationError(
                "authorize refuses a run whose replay left unjudged durable bytes")
        proposal = self._stored_proposal(recovered, confirmation.proposal_id)
        self._hold_facts(confirmation, proposal, recovered.envelope.config_digest)
        self._hold_freshness(confirmation, budget)
        key = f"dispatch-{proposal.proposal_id}"
        prior = next((
            row.value for row in recovered.records
            if row.kind == "action_request" and row.value.idempotency_key == key), None)
        if prior is not None:
            expected = self._mint_request(
                confirmation, proposal, action_id=prior.action_id)
            if prior != expected:
                raise AuthorizationError(
                    f"proposal {proposal.proposal_id!r} was already confirmed with "
                    "different durable facts")
            # An identical retry is not a new budget action and writes nothing.
            return Authorization(request=prior)
        self._hold_budget(proposal, recovered, budget)
        request = self._mint_request(confirmation, proposal)
        self._hold_route(confirmation.run_id, AuthorizationError)
        # The store appends the request as its own record, refuses a fresh id that
        # reuses the idempotency key (RecordConflict), and no-ops an identical retry.
        appended = self._store.append(request)
        canonical = ActionRequest.from_dict(request.as_dict())
        if appended:
            self._grants.add((canonical.run_id, canonical.action_id))
        return Authorization(request=ActionRequest.from_dict(canonical.as_dict()))

    @staticmethod
    def _stored_proposal(recovered: RecoveredRun, proposal_id: str) -> ActionProposal:
        for row in recovered.records:
            if (row.kind == "action_proposal"
                    and row.value.proposal_id == proposal_id):
                return row.value
        raise AuthorizationError(
            f"run {recovered.envelope.run_id!r} holds no proposal {proposal_id!r} to confirm")

    @staticmethod
    def _hold_facts(
            confirmation: Confirmation, proposal: ActionProposal, frozen_digest: str) -> None:
        """Every fact the confirmation restates must equal the run's durable one."""
        if confirmation.preview_digest != proposal.preview_digest:
            raise AuthorizationError(
                "changed fact: the confirmed preview digest is not the stored proposal's; "
                f"confirmed {confirmation.preview_digest}, proposal {proposal.preview_digest}")
        if tuple(confirmation.scope) != tuple(proposal.scope):
            raise AuthorizationError(
                "changed fact: the confirmed scope is not the stored proposal's; "
                f"confirmed {list(confirmation.scope)}, proposal {list(proposal.scope)}")
        if confirmation.capability != proposal.capability:
            raise AuthorizationError(
                "changed fact: the confirmed capability is not the stored proposal's; "
                f"confirmed {confirmation.capability!r}, proposal {proposal.capability!r}")
        if confirmation.config_digest != frozen_digest or proposal.config_digest != frozen_digest:
            raise AuthorizationError(
                "changed fact: the confirmed frozen config is not the run's; "
                f"run {frozen_digest}, confirmed {confirmation.config_digest}, "
                f"proposal {proposal.config_digest}")

    def _hold_freshness(self, confirmation: Confirmation, budget: Budget) -> None:
        age = (_instant("now", self._clock())
               - _instant("confirmed_at", confirmation.confirmed_at)).total_seconds()
        if age < 0:
            raise AuthorizationError(
                "stale fact: the confirmation is dated in the future of the clock")
        if age > budget.max_confirmation_age_seconds:
            raise AuthorizationError(
                f"stale fact: the confirmation is {int(age)}s old, past the "
                f"{budget.max_confirmation_age_seconds}s freshness budget")

    @staticmethod
    def _hold_budget(
            proposal: ActionProposal, recovered: RecoveredRun, budget: Budget) -> None:
        prior = sum(1 for row in recovered.records if row.kind == "action_request")
        if prior >= budget.max_actions:
            raise AuthorizationError(
                f"budget: the run already holds {prior} authorized action(s), at the "
                f"{budget.max_actions} action budget")
        if proposal.timeout_seconds > budget.max_action_seconds:
            raise AuthorizationError(
                f"budget: the proposal asks for {proposal.timeout_seconds}s, past the "
                f"{budget.max_action_seconds}s time budget")

    def _mint_request(
            self, confirmation: Confirmation, proposal: ActionProposal, *,
            action_id: str | None = None) -> ActionRequest:
        return ActionRequest(
            action_id=action_id or self._ids("action"),
            run_id=confirmation.run_id,
            attempt_id=proposal.attempt_id,
            instance_id=proposal.instance_id,
            capability=proposal.capability,
            arguments=_thaw_json(proposal.arguments),
            scope=proposal.scope,
            requested_by=confirmation.confirmed_by,
            requested_at=confirmation.confirmed_at,
            idempotency_key=f"dispatch-{proposal.proposal_id}",
            timeout_seconds=proposal.timeout_seconds,
            preview_digest=proposal.preview_digest,
            mode=ControlMode.CONFIRM,
        )

    # -- execute (A/RT-1): prepare -> execute -> verify -> one durable result receipt --

    def execute(self, authorization: Authorization) -> Attempt:
        """Drive the authorized request; return the attempt with its terminal state."""
        if not isinstance(authorization, Authorization):
            raise ExecutionError("execute requires an Authorization from authorize")
        claimed = ActionRequest.from_dict(authorization.request.as_dict())
        self._hold_route(claimed.run_id, ExecutionError)
        recovered = self._store.read(claimed.run_id)
        if recovered.envelope.mode is not ControlMode.CONFIRM:
            raise ExecutionError("Confirm runtime requires run mode 'confirm'")
        if recovered.warnings:
            raise ExecutionError(
                "execute refuses a run whose replay left unjudged durable bytes")
        stored = next((
            row.value for row in recovered.records
            if row.kind == "action_request" and row.value.action_id == claimed.action_id), None)
        if stored is None:
            raise ExecutionError(
                f"action {claimed.action_id!r} was never authorized in run {claimed.run_id!r}")
        canonical = ActionRequest.from_dict(stored.as_dict())
        if canonical.as_dict() != claimed.as_dict():
            raise ExecutionError(
                f"action {claimed.action_id!r} differs from its durable authorization")
        replayed = self._replayed_attempt(canonical, recovered)
        if replayed is not None:
            return replayed
        grant = (canonical.run_id, canonical.action_id)
        if grant not in self._grants:
            raise ExecutionError(
                f"action {canonical.action_id!r} has no live execution grant; its durable "
                "request is ambiguous and requires reconciliation")
        # Consume before the first untrusted adapter seam. Every later retry is
        # fail-closed even if an effect happened but no terminal receipt landed.
        self._grants.remove(grant)
        _, bound = self._bound_adapter(recovered, canonical.instance_id)
        self._hold_route(canonical.run_id, ExecutionError)
        try:
            prepared = self._registry.prepare(
                bound, ActionRequest.from_dict(canonical.as_dict()))
        except Exception:  # noqa: BLE001 -- refusal becomes a durable unknown
            return self._finish(
                canonical, AttemptState.UNKNOWN, (AttemptState.ACCEPTED,),
                detail="adapter prepare failed")
        history = (AttemptState.ACCEPTED, AttemptState.STARTED)
        self._hold_route(canonical.run_id, ExecutionError)
        report, note = self._observe_execute(bound, prepared, canonical)
        if report is None:
            return self._finish(canonical, AttemptState.UNKNOWN, history, detail=note)
        return self._resolve(canonical, bound, report, history)

    @staticmethod
    def _replayed_attempt(request: ActionRequest, recovered: RecoveredRun) -> Attempt | None:
        """Return an already-durable terminal attempt; never execute it twice."""
        results = [
            row.value for row in recovered.records
            if row.kind == "action_result" and row.value.action_id == request.action_id
        ]
        if len(results) > 1:
            raise ExecutionError(
                f"action {request.action_id!r} has more than one terminal result")
        if not results:
            return None
        receipt = results[0]
        if len(receipt.evidence_refs) != len(set(receipt.evidence_refs)):
            raise ExecutionError(
                f"action {request.action_id!r} result repeats an evidence ref")
        if receipt.evidence_refs:
            raise ExecutionError(
                "verified evidence requires RT-2 causal attempt facts")
        try:
            state = AttemptState(receipt.outcome)
        except ValueError as e:
            raise ExecutionError(
                f"action {request.action_id!r} has unsupported terminal outcome "
                f"{receipt.outcome!r}") from e
        return Attempt(
            request=request, state=state, receipt=receipt,
            # Durable v2 records do not say whether preparation/execute started.
            # Replay therefore reconstructs only accepted + terminal facts.
            history=(AttemptState.ACCEPTED, state),
            verification_evidence=())

    def _hold_route(self, run_id: str, error: type[RuntimeError]) -> None:
        """Refuse a non-local/aliased store route before the next durable effect."""
        violations = run_route_violations(self._store, run_id)
        facts = render_legacy_run_route_violations(violations)
        if facts:
            raise error(
                f"run {run_id!r} is not on a contained writable route: "
                + "; ".join(facts))

    def _bound_adapter(self, recovered: RecoveredRun, instance_id: str) -> tuple[Any, str]:
        bindings = frozen_config_bindings(recovered.config)
        bound = bindings.get(instance_id)
        if bound is None:
            raise ExecutionError(
                f"frozen config declares no instance {instance_id!r} to drive")
        return self._registry.resolve(bound), bound

    def _observe_execute(
            self, bound: str, prepared: PreparedAction,
            request: ActionRequest) -> tuple[ActionResultReceipt | None, str | None]:
        """The one place a missing or foreign result becomes ``unknown``, never success.

        The adapter is arbitrary third-party code, so any raise is a lost result,
        not a crash to propagate: a caught exception, a non-receipt return, and a
        receipt naming another action all yield None with a note, and the caller
        records ``unknown``.
        """
        try:
            report = self._registry.execute(bound, prepared)
        except Exception:  # noqa: BLE001 -- a broken adapter's failure is a lost result
            return None, "adapter execute lost its result"
        if not isinstance(report, ActionResultReceipt):
            return None, "the adapter returned no observed result receipt"
        if (report.run_id != request.run_id
                or report.action_id != request.action_id
                or report.attempt_id != request.attempt_id
                or report.instance_id != request.instance_id):
            return None, "the adapter reported a result for another action"
        return report, None

    def _resolve(
            self, request: ActionRequest, bound: str, report: ActionResultReceipt,
            history: tuple[AttemptState, ...]) -> Attempt:
        if report.outcome != "succeeded":
            return self._finish(
                request, _NON_SUCCESS[report.outcome], history,
                detail=f"adapter reported {report.outcome}", exit_code=report.exit_code)
        return self._verify(request, bound, report, history)

    def _verify(
            self, request: ActionRequest, bound: str, report: ActionResultReceipt,
            history: tuple[AttemptState, ...]) -> Attempt:
        """A reported success is not the terminal word until verify confirms it."""
        try:
            verification = self._registry.verify(bound, request, report)
        except Exception:  # noqa: BLE001 -- a broken verifier cannot confirm success
            return self._finish(
                request, AttemptState.VERIFICATION_FAILED, history,
                detail="adapter verify failed",
                exit_code=report.exit_code)
        if (not isinstance(verification, AdapterVerification)
                or verification.action_id != request.action_id
                or verification.adapter_id != bound):
            return self._finish(
                request, AttemptState.VERIFICATION_FAILED, history,
                detail="the adapter returned no verification for this action",
                exit_code=report.exit_code)
        if verification.state == "unavailable":
            return self._finish(
                request, AttemptState.SUCCEEDED, history,
                detail="the process reported success; the adapter exposed no verifier",
                exit_code=report.exit_code)
        state = AttemptState.VERIFICATION_FAILED
        detail = ("verified evidence requires RT-2 causal attempt facts"
                  if verification.state == "verified"
                  else f"adapter verification was {verification.state}")
        return self._finish(
            request, state, history, detail=detail,
            exit_code=report.exit_code)

    def _finish(
            self, request: ActionRequest, state: AttemptState,
            history: tuple[AttemptState, ...], *, detail: str | None = None,
            exit_code: int | None = None) -> Attempt:
        """Append the one durable result receipt for this attempt and return it.

        Day-1 result receipts carry no evidence refs: RT-2 must first add a durable
        execution-observed fact. The receipt identity is never rewritten in place.
        """
        self._hold_route(request.run_id, ExecutionError)
        receipt = ActionResultReceipt(
            receipt_id=self._ids("result"),
            action_id=request.action_id,
            run_id=request.run_id,
            attempt_id=request.attempt_id,
            instance_id=request.instance_id,
            outcome=state.value,
            observed_at=self._clock(),
            evidence_refs=(),
            detail=detail,
            exit_code=exit_code,
        )
        self._store.append(receipt)
        return Attempt(
            request=request, state=state, receipt=receipt,
            history=(*history, state), verification_evidence=())
