"""Pure replay relations for durable RT-2 attempt facts."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .attempts import AttemptEvent, action_request_digest
from .contracts import (
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    EvidenceRef,
    frozen_config_bindings,
)


class AttemptRelationError(ValueError):
    """A sequence of individually valid attempt facts contradicts itself."""


def action_request_for(values: Sequence[object], action_id: str) -> ActionRequest | None:
    return next((
        value for value in values
        if isinstance(value, ActionRequest) and value.action_id == action_id
    ), None)


def attempt_events_for(values: Sequence[object], action_id: str) -> list[AttemptEvent]:
    return [
        value for value in values
        if isinstance(value, AttemptEvent) and value.action_id == action_id
    ]


def terminal_result_for(
        values: Sequence[object], action_id: str) -> ActionResultReceipt | None:
    """The one terminal receipt an action may already hold, if it holds one.

    An action carries at most one terminal result, and that is true of the
    action alone -- not of the attempt events it happens to have collected. The
    predicate lives here so the store and `validate_event_result` ask the same
    question of the same values rather than each spelling it for itself; asking
    it in only one of the two places is how a journal with no attempt event came
    to accept a second, contradicting receipt.
    """
    return next((
        value for value in values
        if isinstance(value, ActionResultReceipt) and value.action_id == action_id
    ), None)


def _bound_adapter(config: Mapping[str, Any], instance_id: str) -> str:
    try:
        bound = frozen_config_bindings(config).get(instance_id)
    except ContractError as e:
        raise AttemptRelationError(f"frozen config cannot bind attempt events: {e}") from e
    if bound is None:
        raise AttemptRelationError(f"frozen config declares no instance {instance_id!r}")
    return bound


def _hold_event_identity(action: ActionRequest, event: AttemptEvent) -> None:
    for field in ("run_id", "attempt_id", "instance_id"):
        if getattr(event, field) != getattr(action, field):
            raise AttemptRelationError(
                f"attempt event {field} does not match action {event.action_id!r}")
    if event.request_digest != action_request_digest(action):
        raise AttemptRelationError(
            f"attempt event request_digest does not match action {event.action_id!r}")


def validate_action_request(values: Sequence[object], request: ActionRequest) -> None:
    """One attempt id names one action, held over the requests themselves.

    ``validate_attempt_event`` below has said "attempt_id already belongs to
    another action" since attempt events existed, and it said it only of the
    EVENTS. The requests those events describe were never held to the same
    relation, so a journal could record two authorized actions under one attempt
    identity and remain, by every rule that existed, valid.

    It did not stay quiet. The first of those actions to record an event claimed
    the id, and from then on every other action holding it was refused an event
    of its own -- work that had been authorized, could not proceed, and had no
    explanation anywhere in the run. The contradiction was reachable through the
    honest road: the attempt bound counted DISTINCT attempt ids, so repeating
    one was also how a caller bought itself extra authorizations.

    Asked of the request rather than only at authorize time because a record
    appended directly, or a journal replayed from disk, reaches the store
    without passing the runtime -- the same argument
    ``_request_repeats_its_proposal`` is written under, one identity down.

    Args:
        values: The records already replayed, oldest first.
        request: The request about to join them.

    Raises:
        AttemptRelationError: A different action already holds this attempt id.
    """
    for prior in values:
        if (isinstance(prior, ActionRequest)
                and prior.attempt_id == request.attempt_id
                and prior.action_id != request.action_id):
            raise AttemptRelationError(
                f"attempt_id {request.attempt_id!r} already belongs to another "
                f"action, {prior.action_id!r}")


def validate_attempt_event(
        config: Mapping[str, Any], values: Sequence[object], event: AttemptEvent) -> None:
    action = action_request_for(values, event.action_id)
    if action is None:
        raise AttemptRelationError(f"attempt event names unknown action {event.action_id!r}")
    _hold_event_identity(action, event)
    if event.adapter_id != _bound_adapter(config, action.instance_id):
        raise AttemptRelationError(
            f"attempt event adapter does not match frozen binding for {action.instance_id!r}")
    events = attempt_events_for(values, event.action_id)
    if any(prior.phase == event.phase for prior in events):
        raise AttemptRelationError(
            f"action {event.action_id!r} already has an {event.phase!r} attempt event")
    for prior in (value for value in values if isinstance(value, AttemptEvent)):
        if prior.attempt_id == event.attempt_id and prior.action_id != event.action_id:
            raise AttemptRelationError(
                f"attempt_id {event.attempt_id!r} already belongs to another action")
        if prior.recovery_ref == event.recovery_ref and prior.action_id != event.action_id:
            raise AttemptRelationError(
                f"recovery_ref {event.recovery_ref!r} already belongs to another action")
    if any(isinstance(value, ActionResultReceipt) and value.action_id == event.action_id
           for value in values):
        raise AttemptRelationError(
            f"attempt event cannot follow terminal result for {event.action_id!r}")
    if event.phase == "execution_observed":
        _validate_observed(events, event)


def _validate_observed(events: Sequence[AttemptEvent], observed: AttemptEvent) -> None:
    lease = next((event for event in events if event.phase == "effect_lease"), None)
    if lease is None:
        raise AttemptRelationError(
            f"observed attempt event has no lease for {observed.action_id!r}")
    for field in ("request_digest", "adapter_id", "recovery_ref"):
        if getattr(observed, field) != getattr(lease, field):
            raise AttemptRelationError(f"observed attempt event {field} does not match its lease")


_OBSERVED_FINALS = {
    "succeeded": frozenset({"succeeded", "verification_failed"}),
    "failed": frozenset({"failed"}),
    "cancelled": frozenset({"cancelled"}),
    "rejected": frozenset({"failed"}),
    "unknown": frozenset({"unknown"}),
}


def _validate_result_evidence(
        values: Sequence[object], result: ActionResultReceipt,
        observed: AttemptEvent, signer: str | None = None) -> None:
    if len(set(result.evidence_refs)) != len(result.evidence_refs):
        raise AttemptRelationError("event-bearing result evidence_refs must be unique")
    if result.evidence_refs and result.outcome != "succeeded":
        raise AttemptRelationError("only a succeeded event-bearing result may reference evidence")
    observed_index = next(index for index, value in enumerate(values) if value is observed)
    eligible = {
        value.evidence_id: value for value in values[observed_index + 1:]
        if isinstance(value, EvidenceRef)
    }
    for evidence_id in result.evidence_refs:
        _validate_evidence(eligible.get(evidence_id), evidence_id, result,
                           observed, signer)


def _validate_evidence(
        evidence: EvidenceRef | None, evidence_id: str,
        result: ActionResultReceipt, observed: AttemptEvent,
        signer: str | None = None) -> None:
    """Exactly ONE adapter identity may sign this action's verification.

    `signer` is that identity when the run's own frozen plan named a verifier
    other than the doer, and `None` when it did not -- in which case the
    identity is the adapter observed executing, which is what this rule has
    always required and what every journal written before a plan could name a
    verifier still answers.

    The CARDINALITY is the invariant and it is untouched: one permitted
    signer, derived from frozen bytes, never from anything a caller supplies."""
    if evidence is None:
        raise AttemptRelationError(
            f"result evidence {evidence_id!r} must follow its observed attempt event")
    expected_uri = f"verification/{result.action_id}"
    permitted = observed.adapter_id if signer is None else signer
    if (evidence.run_id != result.run_id
            or evidence.kind != "verification" or evidence.uri != expected_uri
            or evidence.created_by != permitted
            or evidence.verified_by != permitted
            or evidence.verification != "verified"):
        raise AttemptRelationError(
            f"result evidence {evidence_id!r} is not verified by "
            f"{permitted!r}, the adapter this run's plan makes "
            "authoritative for it")


def validate_event_result(
        values: Sequence[object], result: ActionResultReceipt,
        events: Sequence[AttemptEvent], signer: str | None = None) -> None:
    if terminal_result_for(values, result.action_id) is not None:
        raise AttemptRelationError(f"action {result.action_id!r} already has a terminal result")
    lease = next((event for event in events if event.phase == "effect_lease"), None)
    if lease is None:
        raise AttemptRelationError(f"event-bearing result has no lease for {result.action_id!r}")
    observed = next((
        event for event in events if event.phase == "execution_observed"), None)
    if observed is None:
        _validate_lease_only_result(result)
        return
    if result.outcome not in _OBSERVED_FINALS[observed.outcome]:
        raise AttemptRelationError(
            f"result outcome {result.outcome!r} contradicts observed {observed.outcome!r}")
    if result.exit_code != observed.exit_code:
        raise AttemptRelationError("result exit_code does not match the observed attempt event")
    _validate_result_evidence(values, result, observed, signer)


def _validate_lease_only_result(result: ActionResultReceipt) -> None:
    if result.outcome != "unknown" or result.exit_code is not None or result.evidence_refs:
        raise AttemptRelationError(
            "a lease-only result must be unknown with null exit_code and empty evidence")
