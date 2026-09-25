"""Bounded Policy shares the existing request, budget and execution machinery."""
from .authorization_history import bounded_history_enabled
from .authorize_holds import _hold_attempt_identity, _hold_plan_admits, _hold_work_scope
from .contract_values import ContractError
from .contracts import ActionRequest, ControlMode, _thaw_json
from .policy_history import current_authorization, hold_active, hold_selected_inputs
from .runtime_values import Authorization, AuthorizationError, ExecutionError


def hold_execution_mode(recovered):
    if recovered.envelope.mode is ControlMode.CONFIRM or bounded_history_enabled(recovered):
        return
    raise ExecutionError("Confirm runtime requires run mode 'confirm' for unmarked runs")


def mint_request(proposal, grant, *, action_id, at):
    return ActionRequest(action_id=action_id, run_id=proposal.run_id,
        attempt_id=proposal.attempt_id, instance_id=proposal.instance_id,
        capability=proposal.capability, arguments=_thaw_json(proposal.arguments),
        scope=proposal.scope, requested_by="run-policy", requested_at=at,
        idempotency_key=f"dispatch-{proposal.proposal_id}", timeout_seconds=proposal.timeout_seconds,
        preview_digest=proposal.preview_digest, mode=ControlMode.POLICY, node_id=proposal.node_id,
        run_authorization_id=grant.authorization_id, run_authorization_digest=grant.authorization_digest)


def authorize_policy(runtime, run_id, proposal_id, authorization_id, admit):
    from .runtime import _operation_lock
    runtime._hold_lock_order(AuthorizationError)
    key = runtime._lock_key("authorize", run_id, proposal_id, f"dispatch-{proposal_id}")
    with _operation_lock(key):
        with runtime._store.transaction():
            return _authorize_locked(runtime, run_id, proposal_id, authorization_id, admit)


def _authorize_locked(runtime, run_id, proposal_id, authorization_id, admit):
    runtime._hold_route(run_id, AuthorizationError)
    recovered = runtime._store.read(run_id)
    if not bounded_history_enabled(recovered) or recovered.warnings:
        raise AuthorizationError("bounded authorization requires unambiguous frozen Policy history")
    proposal = runtime._stored_proposal(recovered, proposal_id)
    values = tuple(row.value for row in recovered.records)
    grant = next((v for v in values if getattr(v, "authorization_id", None) == authorization_id
                  and hasattr(v, "node_limits")), None)
    if grant is None:
        raise AuthorizationError("bounded authorization is absent")
    prior = next((v for v in values if type(v) is ActionRequest
                  and v.idempotency_key == f"dispatch-{proposal_id}"), None)
    if prior is not None:
        expected = mint_request(proposal, grant, action_id=prior.action_id, at=prior.requested_at)
        if expected != prior:
            raise AuthorizationError("proposal already has different durable authority")
        return Authorization(request=prior, record_created=False)
    hold_live(runtime, recovered, grant, proposal)
    runtime._hold_input_binding(proposal, recovered)
    _hold_work_scope(proposal, recovered)
    _hold_attempt_identity(proposal, recovered)
    runtime._hold_budget(proposal, recovered, runtime._policy.budget)
    _hold_plan_admits(proposal, recovered,
                      verifies_independently=runtime._registry.verifies_independently)
    request = mint_request(proposal, grant, action_id=runtime._ids("action"), at=runtime._clock())
    from .policy_history import validate_policy_request
    validate_policy_request(recovered, request)
    if admit is not None:
        admit()
    created = runtime._store.append(request)
    if created:
        runtime._grants.add((request.run_id, request.action_id))
    return Authorization(request=request, record_created=created)


def hold_live(runtime, recovered, grant, proposal):
    policy = getattr(runtime, "_policy", None)
    if policy is None:
        raise AuthorizationError("bounded policy execution is not enabled")
    policy.owner_check()
    if policy.driver is None or not policy.driver.is_active(grant.run_id, grant.authorization_id):
        raise AuthorizationError("authorization needs an explicit activation or resume")
    values = tuple(row.value for row in recovered.records)
    hold_active(grant, values, runtime._clock())
    if policy.provider_digest(recovered.config) != grant.provider_config_digest:
        raise ContractError("provider configuration changed; renewed authorization is required")
    definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
    hold_selected_inputs(proposal, grant, values, definition)


def hold_start(runtime, request):
    """Called before preparation and under the lease's store transaction."""
    if request.mode is not ControlMode.POLICY:
        return
    recovered = runtime._store.read(request.run_id)
    grant = current_authorization(tuple(row.value for row in recovered.records))
    if grant is None or (request.run_authorization_id, request.run_authorization_digest) != (
            grant.authorization_id, grant.authorization_digest):
        raise AuthorizationError("queued request lost its current authorization")
    proposal = runtime._stored_proposal(recovered, request.idempotency_key.removeprefix("dispatch-"))
    hold_live(runtime, recovered, grant, proposal)
    _hold_work_scope(proposal, recovered)
