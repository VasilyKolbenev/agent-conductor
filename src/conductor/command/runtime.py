"""The Confirm state machine with durable effect boundaries and restart replay.

This module is the runtime seam A/CONF-1 and A/RT-1 own. It executes nothing on
import, spawns no process, and reaches no browser: it drives whatever adapter a
run's frozen configuration binds to an instance, through the CMD-3 adapter seams,
and records durable facts through the frozen run store. Before the first effect
seam it appends an ``effect_lease``; after execute returns it appends the exact
``execution_observed`` outcome. These facts prevent a restart from repeating an
ambiguous effect and let an observed success resume at verify without executing.

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
that reports success is put to the adapter's verify seam only after its durable
observation. There is exactly ONE road to `succeeded`, and it has three legs:
execution observed as succeeded, a bound adapter that answers `verified`, and a
causal durable EvidenceRef the store recorded after that observation. Every
other verification answer -- `mismatch`, `error`, a verifier that raised, and
`unavailable` -- is `verification_failed` with EMPTY evidence. `unavailable` in
particular is never success: an adapter that exposes no verifier has proved
nothing, and the product says execution observed and unverified rather than
letting an exit code stand in for proof.
Request-only recovery has no fresh effect authority and fails closed; the
operator closes it explicitly with `reconcile`, which records one terminal
``unknown`` and reaches no adapter seam. Lease-only recovery becomes terminal
``unknown`` without another execute; observed recovery never executes. Terminal
replay calls no adapter seam.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any
from weakref import WeakValueDictionary

from .adapters import AdapterRegistry, AdapterVerification, PreparedAction
from .attempt_replay import action_request_for, attempt_events_for, terminal_result_for
from .attempts import AttemptEvent, OBSERVED_OUTCOMES, action_request_digest
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
    frozen_config_models,
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
}

# Process-local only: concurrent operations sharing one logical key hold the
# same live lock. The weak table releases idle keys; cross-process exclusion is
# separately out of scope for both this operation gate and RunStore transactions.
_LOCKS_GUARD = Lock()
_OPERATION_LOCKS: WeakValueDictionary[tuple[Any, ...], Any] = WeakValueDictionary()


def _operation_lock(key: tuple[Any, ...]):
    with _LOCKS_GUARD:
        lock = _OPERATION_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _OPERATION_LOCKS[key] = lock
        return lock


def _no_notify(run_id: str) -> None:
    """The default listener: a runtime nobody is watching announces nothing."""


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
    """A cleared confirmation and whether this call created its durable request.

    ``record_created`` is a response disposition, not execution authority.  It is
    true only for the runtime call that appended the request; an exact immutable
    retry returns the same request with it false.
    """

    request: ActionRequest
    state: AttemptState = AttemptState.ACCEPTED
    record_created: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.request, ActionRequest):
            raise ContractError("Authorization.request must be an ActionRequest")
        object.__setattr__(
            self, "request", ActionRequest.from_dict(self.request.as_dict()))
        if self.state is not AttemptState.ACCEPTED:
            raise ContractError("Authorization starts in accepted state")
        if type(self.record_created) is not bool:
            raise ContractError("Authorization.record_created must be a boolean")


@dataclass(frozen=True)
class Attempt:
    """One executed attempt: its terminal state, the state path it took, and receipt.

    ``history`` records states supported by this process or durable attempt facts.
    A live execute and a replay carrying an effect lease include ``started``;
    prepare refusal and legacy result replay do not. ``receipt`` is the immutable
    terminal record. Verification evidence is returned only when it follows a
    durable observation and is bound to the frozen adapter by the store relation.
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

    Every attempt event and every terminal receipt this runtime appends is
    announced to ``notify`` with the run id ALONE. The listener is told a run
    changed, never what changed, so no adapter detail, output, or state ever
    leaves through that seam.
    """

    def __init__(
            self, store: RunStore, registry: AdapterRegistry, *,
            clock: Callable[[], str], ids: Callable[[str], str],
            notify: Callable[[str], None] = _no_notify) -> None:
        self._store = store
        self._registry = registry
        self._clock = clock
        self._ids = ids
        # Called with the run id ALONE after each attempt fact lands, so a
        # listener learns that a run changed and must re-read it -- never what
        # changed, what an adapter reported, or what any output held.
        self._notify = notify
        # Memory-only execution authority. A durable request recovered by a new
        # runtime is evidence of authorization, not proof its effect never ran.
        self._grants: set[tuple[str, str]] = set()

    # -- authorize (A/CONF-1): refuse before preparation, else record the confirmation --

    def authorize(
            self, confirmation: Confirmation, *, budget: Budget,
            admit: Callable[[], None] | None = None) -> Authorization:
        """Authorize one confirmed proposal, or refuse; record the cleared request.

        Args:
            confirmation: The fresh Human confirmation restating the proposal.
            budget: The server-owned action/time/age budget to hold it against.
            admit: Optional admission hook, called exactly once on the ONE path
                that is about to append a fresh request, immediately before the
                append and after every other fact has cleared. It is the caller's
                place to bind that request to somewhere that will carry it; if it
                raises, nothing durable is written and the refusal is the answer.
                It is never called for a retry that appends nothing, so a caller
                gating on admission cannot gate an exact retry.

        Returns:
            The cleared `Authorization`, carrying the recorded request.

        Raises:
            AuthorizationError: Any restated fact is changed, stale, or missing.
        """
        if not isinstance(confirmation, Confirmation):
            raise AuthorizationError("authorize requires a validated Confirmation")
        if not isinstance(budget, Budget):
            raise AuthorizationError("authorize requires a validated Budget")
        if admit is not None and not callable(admit):
            raise AuthorizationError("authorize requires a callable admission hook")
        self._hold_lock_order(AuthorizationError)
        logical = f"dispatch-{confirmation.proposal_id}"
        key = self._lock_key(
            "authorize", confirmation.run_id, confirmation.proposal_id, logical)
        with _operation_lock(key):
            with self._store.transaction():
                return self._authorize_locked(confirmation, budget, admit)

    def _authorize_locked(
            self, confirmation: Confirmation, budget: Budget,
            admit: Callable[[], None] | None = None) -> Authorization:
        """Hold one proposal transition from authoritative read through grant."""
        self._hold_route(confirmation.run_id, AuthorizationError)
        recovered = self._store.read(confirmation.run_id)
        if recovered.envelope.mode is not ControlMode.CONFIRM:
            raise AuthorizationError("Confirm runtime requires run mode 'confirm'")
        if recovered.warnings:
            raise AuthorizationError(
                "authorize refuses a run whose replay left unjudged durable bytes")
        proposal = self._stored_proposal(recovered, confirmation.proposal_id)
        self._hold_facts(confirmation, proposal, recovered.envelope.config_digest)
        key = f"dispatch-{proposal.proposal_id}"
        prior = next((
            row.value for row in recovered.records
            if row.kind == "action_request" and row.value.idempotency_key == key), None)
        if prior is not None:
            expected = self._mint_request(
                confirmation, proposal, action_id=prior.action_id,
                requested_at=prior.requested_at)
            if prior != expected:
                raise AuthorizationError(
                    f"proposal {proposal.proposal_id!r} was already confirmed with "
                    "different durable facts")
            # An identical retry is not a new budget action and writes nothing.
            return Authorization(request=prior, record_created=False)
        self._hold_freshness(confirmation, budget)
        self._hold_budget(proposal, recovered, budget)
        request = self._mint_request(confirmation, proposal)
        self._hold_route(confirmation.run_id, AuthorizationError)
        if admit is not None:
            # The last gate before the request becomes durable, and the only one
            # a retry never reaches: an admission refused here leaves the journal
            # exactly as it was.
            admit()
        # The store appends the request as its own record, refuses a fresh id that
        # reuses the idempotency key (RecordConflict), and no-ops an identical retry.
        appended = self._store.append(request)
        canonical = ActionRequest.from_dict(request.as_dict())
        if appended:
            self._grants.add((canonical.run_id, canonical.action_id))
        return Authorization(
            request=ActionRequest.from_dict(canonical.as_dict()),
            record_created=appended)

    def _lock_key(self, operation: str, *parts: str) -> tuple[Any, ...]:
        return (operation, self._store.project_root, *parts)

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
            action_id: str | None = None,
            requested_at: str | None = None) -> ActionRequest:
        return ActionRequest(
            action_id=action_id or self._ids("action"),
            run_id=confirmation.run_id,
            attempt_id=proposal.attempt_id,
            instance_id=proposal.instance_id,
            capability=proposal.capability,
            arguments=_thaw_json(proposal.arguments),
            scope=proposal.scope,
            requested_by=confirmation.confirmed_by,
            requested_at=requested_at or confirmation.confirmed_at,
            idempotency_key=f"dispatch-{proposal.proposal_id}",
            timeout_seconds=proposal.timeout_seconds,
            preview_digest=proposal.preview_digest,
            mode=ControlMode.CONFIRM,
            # Copied from the STORED proposal, never from a Confirm body: what a
            # Human confirmed is the proposal they were shown, binding included,
            # and a body that could name a node could name a different one.
            node_id=proposal.node_id,
        )

    # -- execute (A/RT-1): prepare -> execute -> verify -> one durable result receipt --

    def execute(self, authorization: Authorization) -> Attempt:
        """Drive the authorized request; return the attempt with its terminal state."""
        if not isinstance(authorization, Authorization):
            raise ExecutionError("execute requires an Authorization from authorize")
        self._hold_lock_order(ExecutionError)
        claimed = ActionRequest.from_dict(authorization.request.as_dict())
        copied = Authorization(request=claimed)
        key = self._lock_key("execute", claimed.run_id, claimed.action_id)
        with _operation_lock(key):
            return self._execute_locked(copied)

    def _execute_locked(self, authorization: Authorization) -> Attempt:
        """Hold recovery through the one terminal append for this action."""
        canonical, recovered = self._recover_authorized(authorization)
        replayed = self._replayed_attempt(canonical, recovered)
        if replayed is not None:
            return replayed
        lease, observed = self._durable_events(canonical, recovered)
        if observed is not None:
            return self._resume_observed(canonical, recovered, observed)
        if lease is not None:
            return self._finish(
                canonical, AttemptState.UNKNOWN,
                (AttemptState.ACCEPTED, AttemptState.STARTED),
                detail="effect lease has no durable observation; execution was not repeated")
        grant = (canonical.run_id, canonical.action_id)
        if grant not in self._grants:
            raise ExecutionError(
                f"action {canonical.action_id!r} has no live execution grant; its durable "
                "request is ambiguous and requires reconciliation -- close it with "
                "ControlRuntime.reconcile(run_id, action_id), which records one terminal "
                "'unknown' result, executes nothing, and never reports success")
        return self._execute_granted(canonical, recovered, grant)

    def _recover_authorized(
            self, authorization: Authorization) -> tuple[ActionRequest, RecoveredRun]:
        """Recover the canonical durable request before any adapter seam."""
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
        return canonical, recovered

    def _execute_granted(
            self, canonical: ActionRequest, recovered: RecoveredRun,
            grant: tuple[str, str]) -> Attempt:
        """Consume fresh authority, then bracket the one effect with durable events."""
        # Consume before the first untrusted adapter seam. Every later retry is
        # fail-closed even if an effect happened but no terminal receipt landed.
        self._grants.remove(grant)
        _, bound = self._bound_adapter(recovered, canonical.instance_id)
        self._hold_route(canonical.run_id, ExecutionError)
        try:
            model = frozen_config_models(recovered.config).get(canonical.instance_id)
            prepared = self._registry.prepare(
                bound, ActionRequest.from_dict(canonical.as_dict()), model=model)
        except Exception:  # noqa: BLE001 -- refusal becomes a durable unknown
            return self._finish(
                canonical, AttemptState.UNKNOWN, (AttemptState.ACCEPTED,),
                detail="adapter prepare failed")
        history = (AttemptState.ACCEPTED, AttemptState.STARTED)
        self._hold_route(canonical.run_id, ExecutionError)
        lease = self._append_event(canonical, bound, phase="effect_lease")
        report, note = self._observe_execute(bound, prepared, canonical)
        observed = self._append_event(
            canonical, bound, phase="execution_observed",
            recovery_ref=lease.recovery_ref,
            outcome=report.outcome if report is not None else "unknown",
            exit_code=report.exit_code if report is not None else None)
        if report is None:
            return self._finish(canonical, AttemptState.UNKNOWN, history, detail=note)
        canonical_report = self._observed_report(canonical, observed)
        return self._resolve(canonical, bound, canonical_report, observed, history)

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
        events = [
            row.value for row in recovered.records
            if row.kind == "attempt_event" and row.value.action_id == request.action_id
        ]
        if receipt.evidence_refs and not events:
            raise ExecutionError(
                "verified evidence requires RT-2 causal attempt facts")
        evidence = ControlRuntime._receipt_evidence(receipt, recovered)
        try:
            state = AttemptState(receipt.outcome)
        except ValueError as e:
            raise ExecutionError(
                f"action {request.action_id!r} has unsupported terminal outcome "
                f"{receipt.outcome!r}") from e
        history = ((AttemptState.ACCEPTED, AttemptState.STARTED, state)
                   if events else (AttemptState.ACCEPTED, state))
        return Attempt(
            request=request, state=state, receipt=receipt,
            history=history, verification_evidence=evidence)

    @staticmethod
    def _receipt_evidence(
            receipt: ActionResultReceipt,
            recovered: RecoveredRun) -> tuple[EvidenceRef, ...]:
        """Resolve receipt refs from the already-validated durable record order."""
        by_id = {
            row.value.evidence_id: row.value for row in recovered.records
            if row.kind == "evidence"
        }
        try:
            return tuple(EvidenceRef.from_dict(by_id[ref].as_dict())
                         for ref in receipt.evidence_refs)
        except KeyError as e:
            raise ExecutionError(
                f"result references missing evidence {e.args[0]!r}") from None

    @staticmethod
    def _durable_events(
            request: ActionRequest,
            recovered: RecoveredRun) -> tuple[AttemptEvent | None, AttemptEvent | None]:
        events = [
            row.value for row in recovered.records
            if row.kind == "attempt_event" and row.value.action_id == request.action_id
        ]
        lease = next((row for row in events if row.phase == "effect_lease"), None)
        observed = next((
            row for row in events if row.phase == "execution_observed"), None)
        return lease, observed

    def _hold_route(self, run_id: str, error: type[RuntimeError]) -> None:
        """Refuse a non-local/aliased store route before the next durable effect."""
        run_path = self._store.run_path(run_id)
        violations = run_route_violations(self._store, run_id)
        facts = render_legacy_run_route_violations(violations, run_path)
        if facts:
            raise error(
                f"run {run_id!r} is not on a contained writable route: "
                + "; ".join(facts))

    def _hold_lock_order(self, error: type[RuntimeError]) -> None:
        """Refuse public operation entry from below the operation-lock layer."""
        if self._store.current_thread_holds_transaction():
            raise error("runtime operation cannot start inside a store transaction")

    def _bound_adapter(self, recovered: RecoveredRun, instance_id: str) -> tuple[Any, str]:
        bindings = frozen_config_bindings(recovered.config)
        bound = bindings.get(instance_id)
        if bound is None:
            raise ExecutionError(
                f"frozen config declares no instance {instance_id!r} to drive")
        return self._registry.resolve(bound), bound

    def _append_event(
            self, request: ActionRequest, bound: str, *, phase: str,
            recovery_ref: str | None = None, outcome: str | None = None,
            exit_code: int | None = None) -> AttemptEvent:
        """Append one contract-derived boundary immediately around the effect seam."""
        self._hold_route(request.run_id, ExecutionError)
        event = AttemptEvent(
            event_id=self._ids(f"{phase}-event"),
            run_id=request.run_id, action_id=request.action_id,
            attempt_id=request.attempt_id, instance_id=request.instance_id,
            adapter_id=bound, phase=phase, recorded_at=self._clock(),
            request_digest=action_request_digest(request),
            recovery_ref=recovery_ref or self._ids("recovery"),
            outcome=outcome, exit_code=exit_code, schema_version=2)
        self._store.append(event)
        self._notify(request.run_id)
        return AttemptEvent.from_dict(event.as_dict())

    def _resume_observed(
            self, request: ActionRequest, recovered: RecoveredRun,
            observed: AttemptEvent) -> Attempt:
        """Resolve a durable observation without preparing or executing again."""
        _, bound = self._bound_adapter(recovered, request.instance_id)
        report = self._observed_report(request, observed)
        history = (AttemptState.ACCEPTED, AttemptState.STARTED)
        return self._resolve(request, bound, report, observed, history)

    @staticmethod
    def _observed_report(
            request: ActionRequest, observed: AttemptEvent) -> ActionResultReceipt:
        """Project the sole live/restart verify input from the durable event."""
        return ActionResultReceipt(
            receipt_id=observed.event_id,
            action_id=request.action_id, run_id=request.run_id,
            attempt_id=request.attempt_id, instance_id=request.instance_id,
            outcome=observed.outcome, observed_at=observed.recorded_at,
            evidence_refs=(), detail=None, exit_code=observed.exit_code)

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
        if not self._valid_observed_result(report):
            return None, "the adapter returned no recognized effect outcome"
        return report, None

    @staticmethod
    def _valid_observed_result(report: ActionResultReceipt) -> bool:
        """Hold the event vocabulary and exit relation before durable observation."""
        if report.outcome not in OBSERVED_OUTCOMES:
            return False
        if report.outcome == "succeeded":
            return report.exit_code in (None, 0)
        if report.outcome == "failed":
            return report.exit_code is None or report.exit_code != 0
        return report.exit_code is None

    def _resolve(
            self, request: ActionRequest, bound: str, report: ActionResultReceipt,
            observed: AttemptEvent,
            history: tuple[AttemptState, ...]) -> Attempt:
        if report.outcome != "succeeded":
            return self._finish(
                request, _NON_SUCCESS[report.outcome], history,
                detail=f"adapter reported {report.outcome}", exit_code=report.exit_code)
        return self._verify(request, bound, report, observed, history)

    def _verify(
            self, request: ActionRequest, bound: str, report: ActionResultReceipt,
            observed: AttemptEvent,
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
            # No verifier is no proof, and no proof is not a success. This is the
            # one place the whole product could be talked into believing an exit
            # code, so the refusal lives HERE rather than inside whichever
            # adapter happens to be honest today: any next harness may answer
            # `unavailable`, and none of them may be believed for it.
            return self._finish(
                request, AttemptState.VERIFICATION_FAILED, history,
                detail="execution observed; the adapter exposed no verifier, so "
                       "nothing about the work is verified",
                exit_code=report.exit_code)
        if verification.state == "verified":
            evidence = self._causal_evidence(
                request, bound, observed, verification.evidence_refs)
            if evidence is not None:
                return self._finish(
                    request, AttemptState.SUCCEEDED, history,
                    detail="post-effect evidence was verified by the bound adapter",
                    exit_code=report.exit_code, evidence=evidence)
            return self._finish(
                request, AttemptState.VERIFICATION_FAILED, history,
                detail="verified evidence did not satisfy the causal store relation",
                exit_code=report.exit_code)
        state = AttemptState.VERIFICATION_FAILED
        detail = f"adapter verification was {verification.state}"
        return self._finish(
            request, state, history, detail=detail,
            exit_code=report.exit_code)

    def _causal_evidence(
            self, request: ActionRequest, bound: str, observed: AttemptEvent,
            refs: tuple[str, ...]) -> tuple[EvidenceRef, ...] | None:
        """Resolve only bound verification evidence recorded after observation."""
        self._hold_route(request.run_id, ExecutionError)
        recovered = self._store.read(request.run_id)
        rows = list(recovered.records)
        index = next((
            position for position, row in enumerate(rows)
            if row.kind == "attempt_event" and row.value == observed), None)
        if index is None:
            return None
        eligible = {
            row.value.evidence_id: row.value for row in rows[index + 1:]
            if row.kind == "evidence"
        }
        evidence = tuple(eligible.get(ref) for ref in refs)
        if any(row is None for row in evidence):
            return None
        expected_uri = f"verification/{request.action_id}"
        if any(
                row.run_id != request.run_id or row.kind != "verification"
                or row.uri != expected_uri or row.created_by != bound
                or row.verification != "verified" or row.verified_by != bound
                for row in evidence):
            return None
        return tuple(EvidenceRef.from_dict(row.as_dict()) for row in evidence)

    def _finish(
            self, request: ActionRequest, state: AttemptState,
            history: tuple[AttemptState, ...], *, detail: str | None = None,
            exit_code: int | None = None,
            evidence: tuple[EvidenceRef, ...] = ()) -> Attempt:
        """Append the one durable result receipt for this attempt and return it.

        Evidence refs are accepted only after a durable execution observation.
        The receipt identity is never rewritten in place.
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
            evidence_refs=tuple(row.evidence_id for row in evidence),
            detail=detail,
            exit_code=exit_code,
        )
        self._store.append(receipt)
        self._notify(request.run_id)
        return Attempt(
            request=request, state=state, receipt=receipt,
            history=(*history, state), verification_evidence=evidence)

    # -- reconcile: the operator's only road out of a request-only action --

    def reconcile(self, run_id: str, action_id: str) -> Attempt:
        """Close a request-only action with one terminal ``unknown`` receipt.

        A durable request with no ``effect_lease`` proves no effect was ever
        authorized to start: `_execute_granted` appends that lease BEFORE it
        calls the adapter's execute seam, so an action that never reached a
        lease never reached a spawn. `execute` still refuses such an action --
        a restarted process holds no fresh effect authority -- and that refusal
        used to leave it neither resumable nor terminal, with no operation
        anywhere in the product able to end it. This is that operation.

        It prepares, executes and verifies nothing, resolves no adapter, and
        records ``unknown``: the only honest terminal for an effect nobody
        observed, and one this runtime never promotes. An action carrying any
        attempt event, or a terminal result already, belongs to `execute`'s own
        recovery roads and is refused here rather than given a second terminal.
        """
        self._hold_lock_order(ExecutionError)
        # The only entry here that takes bare strings rather than a contract
        # value, so the ids are held to the contract before they reach a path.
        try:
            run_id, action_id = _id("run_id", run_id), _id("action_id", action_id)
        except ContractError as e:
            raise ExecutionError(str(e)) from e
        with _operation_lock(self._lock_key("execute", run_id, action_id)):
            self._hold_route(run_id, ExecutionError)
            recovered = self._store.read(run_id)
            if recovered.envelope.mode is not ControlMode.CONFIRM:
                raise ExecutionError("Confirm runtime requires run mode 'confirm'")
            if recovered.warnings:
                raise ExecutionError(
                    "reconcile refuses a run whose replay left unjudged durable bytes")
            values = tuple(row.value for row in recovered.records)
            stored = action_request_for(values, action_id)
            if stored is None:
                raise ExecutionError(
                    f"action {action_id!r} has no durable request in run {run_id!r}")
            if attempt_events_for(values, action_id):
                raise ExecutionError(
                    f"action {action_id!r} carries a durable attempt event; that "
                    "recovery belongs to execute, which never repeats the effect")
            if terminal_result_for(values, action_id) is not None:
                raise ExecutionError(
                    f"action {action_id!r} already has a terminal result")
            return self._finish(
                ActionRequest.from_dict(stored.as_dict()), AttemptState.UNKNOWN,
                (AttemptState.ACCEPTED,),
                detail="durable request with no effect lease; no effect was ever "
                       "authorized to start, and reconcile started none")
