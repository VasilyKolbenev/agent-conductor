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
that reports success is not itself the terminal word: its claim is put to the
adapter's verify seam, and only an explicit `verified` result reaches `succeeded`;
a `mismatch` or `error` reaches `verification_failed`, while `unavailable` leaves
the observed success standing but explicitly unverified. The runtime owns the one
durable result receipt per attempt: its outcome is the reconciled terminal state,
appended immutably beside -- never over -- the request that authorized it.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .adapters import AdapterRegistry, AdapterVerification, PreparedAction
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


@dataclass(frozen=True)
class Attempt:
    """One executed attempt: its terminal state, the state path it took, and receipt.

    ``history`` records the ordered states the attempt passed through -- always
    beginning ``accepted``, ``started`` -- so a caller can prove the machine
    entered ``started`` and yet did not read it as success. ``receipt`` is the one
    durable result receipt; ``verification_evidence`` is the durable evidence the
    verify seam produced, or None when none was recorded.
    """

    request: ActionRequest
    state: AttemptState
    receipt: ActionResultReceipt
    history: tuple[AttemptState, ...]
    verification_evidence: EvidenceRef | None = None


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

    # -- authorize (A/CONF-1): refuse before preparation, else record the confirmation --

    def authorize(self, confirmation: Confirmation, *, budget: Budget) -> Authorization:
        """Authorize one confirmed proposal, or refuse; record the cleared request."""
        if not isinstance(confirmation, Confirmation):
            raise AuthorizationError("authorize requires a validated Confirmation")
        if not isinstance(budget, Budget):
            raise AuthorizationError("authorize requires a validated Budget")
        recovered = self._store.read(confirmation.run_id)
        proposal = self._stored_proposal(recovered, confirmation.proposal_id)
        self._hold_facts(confirmation, proposal, recovered.envelope.config_digest)
        self._hold_freshness(confirmation, budget)
        self._hold_budget(proposal, recovered, budget)
        request = self._mint_request(confirmation, proposal)
        # The store appends the request as its own record, refuses a fresh id that
        # reuses the idempotency key (RecordConflict), and no-ops an identical retry.
        self._store.append(request)
        return Authorization(request=request)

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
            self, confirmation: Confirmation, proposal: ActionProposal) -> ActionRequest:
        return ActionRequest(
            action_id=self._ids("action"),
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
        request = authorization.request
        recovered = self._store.read(request.run_id)
        if not any(row.kind == "action_request" and row.value.action_id == request.action_id
                   for row in recovered.records):
            raise ExecutionError(
                f"action {request.action_id!r} was never authorized in run {request.run_id!r}")
        adapter, bound = self._bound_adapter(recovered, request.instance_id)
        prepared = self._registry.prepare(bound, request)
        history = (AttemptState.ACCEPTED, AttemptState.STARTED)
        report, note = self._observe_execute(adapter, prepared, request)
        if report is None:
            return self._finish(request, AttemptState.UNKNOWN, history, detail=note)
        return self._resolve(request, adapter, report, history)

    def _bound_adapter(self, recovered: RecoveredRun, instance_id: str) -> tuple[Any, str]:
        bindings = frozen_config_bindings(recovered.config)
        bound = bindings.get(instance_id)
        if bound is None:
            raise ExecutionError(
                f"frozen config declares no instance {instance_id!r} to drive")
        return self._registry.resolve(bound), bound

    @staticmethod
    def _observe_execute(
            adapter: Any, prepared: PreparedAction,
            request: ActionRequest) -> tuple[ActionResultReceipt | None, str | None]:
        """The one place a missing or foreign result becomes ``unknown``, never success.

        The adapter is arbitrary third-party code, so any raise is a lost result,
        not a crash to propagate: a caught exception, a non-receipt return, and a
        receipt naming another action all yield None with a note, and the caller
        records ``unknown``.
        """
        try:
            report = adapter.execute(prepared)
        except Exception as e:  # noqa: BLE001 -- a broken adapter's failure is a lost result
            return None, f"the adapter raised {type(e).__name__} during execute: {e}"
        if not isinstance(report, ActionResultReceipt):
            return None, "the adapter returned no observed result receipt"
        if (report.action_id != request.action_id
                or report.attempt_id != request.attempt_id
                or report.instance_id != request.instance_id):
            return None, "the adapter reported a result for another action"
        return report, None

    def _resolve(
            self, request: ActionRequest, adapter: Any, report: ActionResultReceipt,
            history: tuple[AttemptState, ...]) -> Attempt:
        if report.outcome != "succeeded":
            return self._finish(
                request, _NON_SUCCESS[report.outcome], history,
                detail=report.detail, exit_code=report.exit_code)
        return self._verify(request, adapter, report, history)

    def _verify(
            self, request: ActionRequest, adapter: Any, report: ActionResultReceipt,
            history: tuple[AttemptState, ...]) -> Attempt:
        """A reported success is not the terminal word until verify confirms it."""
        try:
            verification = adapter.verify(request, report)
        except Exception as e:  # noqa: BLE001 -- a broken verifier cannot confirm success
            return self._finish(
                request, AttemptState.VERIFICATION_FAILED, history,
                detail=f"the adapter raised {type(e).__name__} during verify: {e}",
                exit_code=report.exit_code)
        if (not isinstance(verification, AdapterVerification)
                or verification.action_id != request.action_id):
            return self._finish(
                request, AttemptState.VERIFICATION_FAILED, history,
                detail="the adapter returned no verification for this action",
                exit_code=report.exit_code)
        if verification.state == "unavailable":
            return self._finish(
                request, AttemptState.SUCCEEDED, history,
                detail="the process reported success; the adapter exposed no verifier",
                exit_code=report.exit_code)
        state = (AttemptState.SUCCEEDED if verification.state == "verified"
                 else AttemptState.VERIFICATION_FAILED)
        evidence = self._verification_evidence(request, verification)
        return self._finish(
            request, state, history, detail=report.detail,
            exit_code=report.exit_code, evidence=evidence)

    def _verification_evidence(
            self, request: ActionRequest, verification: AdapterVerification) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=self._ids("evidence"),
            run_id=request.run_id,
            kind="verification",
            uri=f"verification/{request.action_id}",
            label=verification.detail or "adapter verification result",
            created_by=verification.adapter_id,
            observed_at=verification.observed_at,
            verification=verification.state,
            verified_by=verification.adapter_id,
            verified_at=verification.observed_at,
        )

    def _finish(
            self, request: ActionRequest, state: AttemptState,
            history: tuple[AttemptState, ...], *, detail: str | None = None,
            exit_code: int | None = None, evidence: EvidenceRef | None = None) -> Attempt:
        """Append the one durable result receipt for this attempt and return it.

        Evidence, when the verify seam produced it, is appended first so the
        receipt's ``evidence_refs`` name a record that already exists. Both appends
        are immutable through the store: a receipt id is never rewritten in place.
        """
        if evidence is not None:
            self._store.append(evidence)
        receipt = ActionResultReceipt(
            receipt_id=self._ids("result"),
            action_id=request.action_id,
            run_id=request.run_id,
            attempt_id=request.attempt_id,
            instance_id=request.instance_id,
            outcome=state.value,
            observed_at=self._clock(),
            evidence_refs=(evidence.evidence_id,) if evidence is not None else (),
            detail=detail,
            exit_code=exit_code,
        )
        self._store.append(receipt)
        return Attempt(
            request=request, state=state, receipt=receipt,
            history=(*history, state), verification_evidence=evidence)
