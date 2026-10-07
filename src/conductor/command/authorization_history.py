"""Durable bounded authorization relations shared by append and prefix replay.

History never consults the current clock, credentials or provider installation.
Provider digest is a recorded fact; fresh admission must establish its provenance
with the configured registry. These records do not create live execution rights.
"""
from __future__ import annotations

import hashlib

from .authorization_inputs import bind_inputs, executable_nodes
from .authorization_terms import AUTOMATION_CONTRACT, _time_parts
from .contracts import (ActionRequest, ActionResultReceipt, ContractError, ControlMode,
                        canonical_json, frozen_config_workflow)
from .graph_definition import GraphDefinition
from .run_authorization import RunAuthorization, RunAuthorizationControl
from .run_terminal import RunTerminal
from .store_errors import StoreError


def journal_prefix_digest(records):
    wrappers = [{"record_type": row.kind, "record": row.value.as_dict()} for row in records]
    return "sha256:" + hashlib.sha256(canonical_json(wrappers).encode("utf-8")).hexdigest()


def _instant(value):
    return _time_parts("authorization history timestamp", value)


def bounded_history_enabled(recovered):
    return (recovered.envelope.mode is ControlMode.POLICY
            and recovered.config.get("automation_contract") == AUTOMATION_CONTRACT)


def _hold_opt_in(recovered):
    if not bounded_history_enabled(recovered):
        raise ContractError("bounded authorization requires explicit frozen Policy opt-in")
    if frozen_config_workflow(recovered.config) is None:
        raise ContractError("bounded authorization requires a published workflow reference")
    if recovered.warnings:
        raise ContractError("bounded authorization refuses unresolved journal warnings")


def _latest_authorization(values):
    return next((row for row in reversed(values) if type(row) is RunAuthorization), None)


def _controls(values, authorization):
    return tuple(row for row in values if type(row) is RunAuthorizationControl
                 and row.authorization_id == authorization.authorization_id)


def _hold_quiescent(values):
    terminal = {row.action_id for row in values if type(row) is ActionResultReceipt}
    if any(type(row) is ActionRequest and row.action_id not in terminal for row in values):
        raise ContractError("authorization replacement requires all actions settled")


def _hold_predecessor(value, values, created_at):
    previous = _latest_authorization(values)
    if previous is None:
        if value.supersedes is not None:
            raise ContractError("first authorization cannot supersede an absent grant")
        earliest = created_at
    else:
        if value.supersedes != previous.authorization_id:
            raise ContractError("authorization must supersede the immediate predecessor")
        controls = _controls(values, previous)
        latest = controls[-1] if controls else None
        earliest = latest.recorded_at if latest else previous.authorized_at
        revoked = latest is not None and latest.action == "revoke"
        if not revoked and _instant(value.authorized_at) < _instant(previous.expires_at):
            raise ContractError("preceding authorization must be revoked or expired")
    if _instant(value.authorized_at) < _instant(earliest):
        raise ContractError("authorization timestamp precedes its history")
    _hold_quiescent(values)


def _hold_limits(value, definition):
    nodes = executable_nodes(definition)
    if tuple(row.node_id for row in value.node_limits) != tuple(n.node_id for n in nodes):
        raise ContractError("authorization nodes must exactly follow executable graph order")
    for node, limit in zip(nodes, value.node_limits, strict=True):
        if node.timeout_seconds is not None and limit.timeout_seconds > node.timeout_seconds:
            raise ContractError("authorization timeout exceeds graph bound")
        if node.attempt_bound is not None and limit.max_attempts > node.attempt_bound:
            raise ContractError("authorization attempts exceed graph bound")
        multiplier = 2 if node.verifier_instance_id not in (None, node.instance_id) else 1
        reserved = limit.timeout_seconds * multiplier
        if reserved > value.max_action_seconds or reserved > value.max_total_task_seconds:
            raise ContractError("authorization does not cover doer and checker reservation")


def _hold_authorization(recovered, value, values):
    definitions = tuple(row for row in values if type(row) is GraphDefinition)
    if len(definitions) != 1:
        raise ContractError("bounded authorization requires one frozen graph")
    definition, = definitions
    if value.config_digest != recovered.envelope.config_digest:
        raise ContractError("authorization config digest differs from frozen run")
    if value.graph_digest != definition.digest():
        raise ContractError("authorization graph digest differs from frozen plan")
    if value.source_prefix_digest != journal_prefix_digest(recovered.records):
        raise ContractError("authorization source prefix differs from reviewed history")
    _hold_predecessor(value, values, recovered.envelope.created_at)
    _hold_limits(value, definition)
    instructions, inputs = bind_inputs(definition, values)
    if value.instruction_bindings != instructions:
        raise ContractError("authorization instructions differ from immutable source bytes")
    if value.initial_input_bindings != inputs:
        raise ContractError("authorization inputs differ from immutable source bytes")


def _hold_control(value, values):
    authorization = _latest_authorization(values)
    if authorization is None or (value.authorization_id, value.authorization_digest) != (
            authorization.authorization_id, authorization.authorization_digest):
        raise ContractError("control must name the current authorization and digest")
    controls = _controls(values, authorization)
    previous = controls[-1] if controls else None
    if value.expected_control_id != (previous.control_id if previous else None):
        raise ContractError("control predecessor is stale")
    earliest = previous.recorded_at if previous else authorization.authorized_at
    if _instant(value.recorded_at) < _instant(earliest):
        raise ContractError("control timestamp precedes its history")
    state = previous.action if previous else "resume"
    if state == "revoke":
        raise ContractError("revocation is irreversible")
    if value.action == "resume":
        # A human Resume may also rearm an unexpired grant after a restart.
        # Exact control predecessor still prevents stale two-window writes.
        if _instant(value.recorded_at) >= _instant(authorization.expires_at):
            raise ContractError("expired authorization cannot resume")
    if value.action == "pause" and state == "pause":
        raise ContractError("authorization is already paused")


def validate_authorization_history(recovered, value):
    """Keep legacy journals unchanged; marked requests stay closed until wired."""
    from .attempts import AttemptEvent
    if type(value) is GraphDefinition:
        from .graph_execution import hold_graph_execution
        hold_graph_execution(recovered, value)
    if type(value) is AttemptEvent and bounded_history_enabled(recovered):
        from .policy_history import validate_policy_lease
        validate_policy_lease(recovered, value)
    if not isinstance(value, (RunAuthorization, RunAuthorizationControl)):
        if isinstance(value, ActionRequest) and bounded_history_enabled(recovered):
            from .policy_history import validate_policy_request
            validate_policy_request(recovered, value)
        elif isinstance(value, ActionRequest):
            from .contracts import ABSENT
            if value.run_authorization_id is not ABSENT:
                raise ContractError("legacy request cannot carry bounded authorization")
        return
    if type(value) not in (RunAuthorization, RunAuthorizationControl):
        raise ContractError("authorization history requires exact record types")
    _hold_opt_in(recovered)
    # Reconstruct nested values even if a caller mutated a frozen dataclass.
    value = type(value).from_dict(value.as_dict())
    if value.run_id != recovered.envelope.run_id:
        raise ContractError("authorization history belongs to another run")
    values = tuple(row.value for row in recovered.records)
    if any(type(row) is RunTerminal for row in values):
        raise ContractError("completed run accepts no authorization history")
    if type(value) is RunAuthorization:
        _hold_authorization(recovered, value, values)
    else:
        _hold_control(value, values)


def hold_authorization_history(recovered, value):
    try:
        validate_authorization_history(recovered, value)
    except ContractError as error:
        raise StoreError(str(error)) from error
