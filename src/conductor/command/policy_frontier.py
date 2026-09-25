"""A failed routine admits only the first actions on its explicit failure road."""
from .contracts import ABSENT, ActionProposal, ActionRequest, ActionResultReceipt, ContractError
from .correction_feedback import CorrectionFeedback
from .attempt_replay import proposal_named_by
from .graph_schedule import lap_is_current


def failure_sources(values, grant):
    if grant is None:
        return ()
    requests = {v.action_id: v for v in values if type(v) is ActionRequest
                and v.run_authorization_id == grant.authorization_id}
    results = {v.action_id: v for v in values if type(v) is ActionResultReceipt}
    if any(result.outcome == "unknown" for key, result in results.items() if key in requests):
        raise ContractError("an unknown action requires human reconciliation")
    proposals = {v.proposal_id: v for v in values if type(v) is ActionProposal}
    feedback = {v.feedback_id: v for v in values if type(v) is CorrectionFeedback}
    consumed = set()
    for key, request in requests.items():
        proposal = proposals.get(proposal_named_by(request))
        if key not in results or proposal is None or proposal.feedback_ids is ABSENT:
            continue
        consumed.update(feedback[ref].source_action_id for ref in proposal.feedback_ids if ref in feedback)
    return tuple(request for key, request in requests.items() if key in results
                 and results[key].outcome != "succeeded" and key not in consumed)


def correction_frontier(definition, source_node):
    """Walk capability-less routing nodes, including a bounded loop's back edge.

    The normal scheduler still has to admit the destination; this walk cannot
    settle a human gate, open a closed edge or override an exhausted loop.
    """
    nodes = {node.node_id: node for node in definition.nodes}
    source = nodes[source_node]
    if source.failure_policy == "halt_run":
        return frozenset()
    pending = [edge.to_node for edge in definition.edges
               if edge.from_node == source_node and edge.condition == "on_failed"]
    found, seen = set(), set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        node = nodes[current]
        if node.capability is not None:
            found.add(current)
            continue
        pending.extend(edge.to_node for edge in definition.edges if edge.from_node == current)
        if node.loop is not None:
            pending.append(node.loop.back_to)
    return frozenset(found)


def required_feedback(definition, values, grant, node_id):
    from .feedback_history import consumable_feedback
    sources = failure_sources(values, grant)
    if not sources:
        return ()
    selected = []
    for source in sources:
        position = next(i for i, v in enumerate(values) if type(v) is ActionRequest
                        and v.action_id == source.action_id)
        if not lap_is_current(definition, values, source.node_id, position):
            raise ContractError("correction source belongs to a stale lap")
        if node_id not in correction_frontier(definition, source.node_id):
            raise ContractError("failed action permits only its explicit correction frontier")
        feedback = consumable_feedback(values, source)
        if len(feedback) != 1:
            raise ContractError("a definite rejection with actionable feedback is required")
        selected.extend(feedback)
    return tuple(selected)
