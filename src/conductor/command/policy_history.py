"""Pure request authority, cumulative spending and immutable input relations."""
from .artifacts import latest_artifacts, required_input_refs, settled_products
from .attempt_replay import proposal_named_by, values_the_proposal_saw
from .authorization_inputs import content_digest
from .authorization_terms import AUTOMATION_CONTRACT, _time_parts
from .contract_values import ContractError
from .contracts import ABSENT, ActionProposal, ActionRequest, ActionResultReceipt, ControlMode
from .run_authorization import RunAuthorization, RunAuthorizationControl
from .work_layout import work_route


def current_authorization(values):
    return next((v for v in reversed(values) if type(v) is RunAuthorization), None)


def current_control(values, grant):
    return next((v for v in reversed(values) if type(v) is RunAuthorizationControl
                 and v.authorization_id == grant.authorization_id), None)


def hold_active(grant, values, at):
    if grant is None:
        raise ContractError("bounded policy request requires a preceding authorization")
    current = current_authorization(values)
    if current != grant:
        raise ContractError("authorization has been superseded")
    time = _time_parts("admission time", at)
    if not _time_parts("authorized_at", grant.authorized_at) <= time < _time_parts(
            "expires_at", grant.expires_at):
        raise ContractError("authorization is not currently within its admission interval")
    control = current_control(values, grant)
    if control is not None:
        if _time_parts("admission time", at) < _time_parts("control time", control.recorded_at):
            raise ContractError("admission timestamp precedes authorization control")
        if control.action in {"pause", "revoke"}:
            raise ContractError("authorization is paused or revoked")


def request_reservation(request, definition):
    node = next((n for n in definition.nodes if n.node_id == request.node_id), None)
    if node is None:
        raise ContractError("bounded action names no frozen plan node")
    return request.timeout_seconds * (2 if node.verifier_instance_id is not None else 1)


def spent_budget(values, definition):
    requests = [v for v in values if type(v) is ActionRequest]
    return len(requests), sum(request_reservation(v, definition) for v in requests)


def hold_request_budget(request, grant, values, definition):
    actions, seconds = spent_budget(values, definition)
    reservation = request_reservation(request, definition)
    if actions >= grant.max_actions or seconds + reservation > grant.max_total_task_seconds:
        raise ContractError("run-wide authorization budget is exhausted")
    if reservation > grant.max_action_seconds:
        raise ContractError("action and checker exceed authorized time reservation")
    limit = next((row for row in grant.node_limits if row.node_id == request.node_id), None)
    if limit is None or request.timeout_seconds > limit.timeout_seconds:
        raise ContractError("action exceeds authorized node timeout")
    spent = sum(type(v) is ActionRequest and v.node_id == request.node_id for v in values)
    if spent >= limit.max_attempts:
        raise ContractError("authorized node attempts are exhausted")


def hold_selected_inputs(proposal, grant, values, definition):
    """Current sources must still equal the exact documents selected at proposal."""
    cut = values_the_proposal_saw(values, proposal.proposal_id)
    if cut is None:
        cut = values  # Used before the driver appends its new proposal.
    refs = required_input_refs(proposal.capability, proposal.arguments)
    selected = latest_artifacts(settled_products(cut), refs)
    current = latest_artifacts(settled_products(values), refs)
    if selected != current:
        raise ContractError("inputs_changed: proposal sources are no longer current")
    initial = {row.artifact_ref: row for row in grant.initial_input_bindings}
    for document in selected:
        binding = initial.get(document.artifact_ref)
        if binding is not None:
            if (document.artifact_id, content_digest(document)) != (
                    binding.artifact_id, binding.content_digest):
                raise ContractError("inputs_changed: initial source differs from authorization")
        else:
            _hold_generated(document, grant, cut, definition)
    if proposal.capability == "dispatch":
        document, = latest_artifacts(settled_products(values), (proposal.arguments["instruction_ref"],))
        binding = next((b for b in grant.instruction_bindings if b.node_id == proposal.node_id), None)
        if binding is None or (document.artifact_id, content_digest(document)) != (
                binding.artifact_id, binding.content_digest):
            raise ContractError("inputs_changed: immutable instruction differs from authorization")


def _hold_generated(document, grant, values, definition):
    source = next((v for v in values if type(v) is ActionRequest
                   and v.action_id == document.source_action_id), None)
    if source is None or (source.run_authorization_id, source.run_authorization_digest) != (
            grant.authorization_id, grant.authorization_digest):
        raise ContractError("generated input was not produced under this authorization")
    producer = next((n for n in definition.nodes if n.node_id == source.node_id), None)
    if (producer is None or producer.capability != "review"
            or producer.arguments.get("result_artifact_ref") != document.artifact_ref):
        raise ContractError("input has no declared authorized review producer")


def _hold_request_proposal(request, values, definition):
    proposal_id = proposal_named_by(request)
    proposal = next((v for v in values if type(v) is ActionProposal
                     and v.proposal_id == proposal_id), None)
    if proposal is None:
        raise ContractError("bounded action requires its stored proposal")
    for field in ("run_id", "attempt_id", "instance_id", "capability", "arguments", "scope",
                  "timeout_seconds", "preview_digest", "node_id"):
        if getattr(proposal, field) != getattr(request, field):
            raise ContractError("bounded request differs from its stored proposal")
    node = next((n for n in definition.nodes if n.node_id == request.node_id), None)
    if node is None or (node.instance_id, node.capability, node.arguments) != (
            proposal.instance_id, proposal.capability, proposal.arguments):
        raise ContractError("bounded request differs from its frozen node")
    route = work_route(node.arguments.get("work_item_id"), node.arguments.get("work_scope"))
    if tuple(request.scope) != (route,):
        raise ContractError("bounded scope differs from the planned work route")
    return proposal


def validate_policy_request(recovered, request):
    if type(request) is not ActionRequest or request.mode is not ControlMode.POLICY:
        raise ContractError("bounded request must be an exact Policy action")
    if request.run_authorization_id is ABSENT or request.requested_by != "run-policy":
        raise ContractError("bounded request requires its explicit authorization reference")
    values = tuple(row.value for row in recovered.records)
    grant = current_authorization(values)
    hold_active(grant, values, request.requested_at)
    if (request.run_authorization_id, request.run_authorization_digest) != (
            grant.authorization_id, grant.authorization_digest):
        raise ContractError("bounded request names another authorization")
    definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
    proposal = _hold_request_proposal(request, values, definition)
    hold_request_budget(request, grant, values, definition)
    terminal = {v.action_id for v in values if type(v) is ActionResultReceipt}
    if any(type(v) is ActionRequest and v.action_id not in terminal for v in values):
        raise ContractError("bounded authorization permits one unsettled action")
    hold_selected_inputs(proposal, grant, values, definition)
    cut = values_the_proposal_saw(values, proposal.proposal_id)
    if grant not in cut:
        raise ContractError("proposal predates its bounded authorization")
    from .feedback_history import hold_feedback_binding
    hold_feedback_binding(proposal, grant, values, definition)
    from .graph_schedule import schedule
    if request.node_id not in schedule(definition, values).runnable:
        raise ContractError("bounded node is not currently runnable")


def validate_policy_lease(recovered, event):
    if event.phase != "effect_lease":
        return
    values = tuple(row.value for row in recovered.records)
    request = next((v for v in values if type(v) is ActionRequest
                    and v.action_id == event.action_id), None)
    if request is None:
        raise ContractError("effect lease has no bounded request")
    grant = current_authorization(values)
    hold_active(grant, values, event.recorded_at)
    if (request.run_authorization_id, request.run_authorization_digest) != (
            grant.authorization_id, grant.authorization_digest):
        raise ContractError("effect lease lost its bounded authorization")
