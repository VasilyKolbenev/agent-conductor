"""Causal rejection records and proposal-bound correction data, including replay."""
from .contracts import (ABSENT, ActionProposal, ActionRequest, ActionResultReceipt,
                        ContractError, frozen_config_bindings)
from .correction_feedback import CorrectionFeedback
from .attempt_replay import proposal_named_by, values_the_proposal_saw
from .authorization_history import bounded_history_enabled
from .authorization_terms import _time_parts
from .graph_schedule import schedule
from .policy_history import current_authorization
from .verify_holds import CHECKER_REJECTED


def source_lap(definition, values, request):
    index = next(i for i, value in enumerate(values) if value is request or
                 type(value) is ActionRequest and value.action_id == request.action_id)
    return next(row.required_pass for row in schedule(definition, values[:index]).nodes
                if row.node_id == request.node_id)


def _source(recovered, feedback):
    values = tuple(row.value for row in recovered.records)
    source = next((v for v in values if type(v) is ActionRequest
                   and v.action_id == feedback.source_action_id), None)
    if source is None or (source.run_id, source.attempt_id, source.node_id,
            source.run_authorization_id, source.run_authorization_digest) != (
            feedback.run_id, feedback.source_attempt_id, feedback.source_node_id,
            feedback.authorization_id, feedback.authorization_digest):
        raise ContractError("feedback does not name its exact authorized source action")
    definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
    node = next(n for n in definition.nodes if n.node_id == source.node_id)
    bound = frozen_config_bindings(recovered.config)
    if (source.capability != "dispatch" or node.verifier_instance_id != feedback.checker_instance_id
            or bound.get(feedback.checker_instance_id) != feedback.checker_adapter_id
            or feedback.checker_instance_id == source.instance_id):
        raise ContractError("feedback does not name the declared independent checker")
    if source_lap(definition, values, source) != feedback.source_lap:
        raise ContractError("feedback names another source lap")
    if _time_parts("feedback time", feedback.recorded_at) < _time_parts("source time", source.requested_at):
        raise ContractError("feedback predates its source")
    _hold_manifest_inputs(source, feedback, values)
    return source


def _hold_manifest_inputs(source, feedback, values):
    from .artifacts import latest_artifacts, settled_products
    cut = values_the_proposal_saw(values, proposal_named_by(source))
    if cut is None:
        raise ContractError("feedback source has no stored bound proposal")
    refs = (source.arguments["instruction_ref"], *source.arguments["artifact_refs"])
    docs = tuple(latest_artifacts(settled_products(cut), (ref,))[0] for ref in refs)
    manifest = feedback.result_manifest
    if (manifest["action_id"], manifest["attempt_id"], tuple(manifest["input_artifact_ids"])) != (
            source.action_id, source.attempt_id, tuple(d.artifact_id for d in docs)):
        raise ContractError("feedback manifest belongs to another action or input cut")


def validate_feedback_history(recovered, value):
    if type(value) is CorrectionFeedback:
        if not bounded_history_enabled(recovered):
            raise ContractError("correction feedback requires explicit bounded Policy history")
        values = tuple(row.value for row in recovered.records)
        grant = current_authorization(values)
        if grant is None or (grant.authorization_id, grant.authorization_digest) != (
                value.authorization_id, value.authorization_digest):
            raise ContractError("feedback belongs to another authorization")
        _source(recovered, value)
        if any(type(v) is CorrectionFeedback and v.source_action_id == value.source_action_id for v in values):
            raise ContractError("an action already has its correction feedback")
        if any(type(v) is ActionResultReceipt and v.action_id == value.source_action_id for v in values):
            raise ContractError("feedback cannot be added after an action has settled")
        if not any(row.kind == "attempt_event" and row.value.action_id == value.source_action_id
                   and row.value.phase == "execution_observed" for row in recovered.records):
            raise ContractError("feedback requires an observed source action")
    elif type(value) is ActionProposal and value.feedback_ids is not ABSENT:
        if not bounded_history_enabled(recovered):
            raise ContractError("correction proposals require explicit bounded Policy history")
        values = tuple(row.value for row in recovered.records)
        definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
        hold_feedback_binding(value, current_authorization(values), values, definition)


def consumable_feedback(values, source):
    result = next((v for v in values if type(v) is ActionResultReceipt
                   and v.action_id == source.action_id), None)
    if result is None or (result.outcome, result.detail) != ("verification_failed", CHECKER_REJECTED):
        return ()
    return tuple(v for v in values if type(v) is CorrectionFeedback
                 and v.source_action_id == source.action_id)


def hold_feedback_binding(proposal, grant, values, definition):
    from .policy_frontier import required_feedback
    cut = values_the_proposal_saw(values, proposal.proposal_id)
    expected = required_feedback(definition, values if cut is None else cut, grant, proposal.node_id)
    actual = () if proposal.feedback_ids is ABSENT else tuple(proposal.feedback_ids)
    if actual != tuple(row.feedback_id for row in expected):
        raise ContractError("correction proposal does not pin its exact permitted feedback")
    return expected


def feedback_for_request(recovered, request):
    """Read the exact proposal cut; never replace findings at execution time."""
    values = tuple(row.value for row in recovered.records)
    proposal_id = proposal_named_by(request)
    proposal = next((v for v in values if type(v) is ActionProposal and v.proposal_id == proposal_id), None)
    if proposal is None or proposal.feedback_ids is ABSENT:
        return ()
    cut = values_the_proposal_saw(values, proposal_id)
    definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
    grant = current_authorization(cut)
    if grant is None or grant.authorization_id != request.run_authorization_id:
        raise ContractError("feedback request belongs to another authorization")
    return hold_feedback_binding(proposal, grant, cut, definition)
