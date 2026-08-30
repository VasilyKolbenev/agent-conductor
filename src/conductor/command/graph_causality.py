"""Whether a run's records agree with the graph the run says it follows.

These are relations, not shapes: every value here is already a validated
contract, and what is decided is whether the run's OWN records can hold them
together. They live beside the graph rather than inside the store because they
are facts about a plan, and because the store was at its line cap.

The store calls them from one place -- the relation pass that runs on every
append AND on every replay -- so a record that reaches the journal by any road
has met the same rules.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .contracts import ActionProposal, ActionRequest, _thaw_json
from .graph_definition import GraphDefinition
from .store_errors import RecordConflict, StoreError

if TYPE_CHECKING:  # pragma: no cover -- import cycle avoided at runtime
    from .run_store import RecoveredRun


def _one_graph_per_run(recovered: "RecoveredRun", value: GraphDefinition) -> None:
    """A run follows ONE graph, which identity alone would never have said.

    Two graphs with different ids are two different identities, so the store
    would take both and leave every reader to guess which plan the run is
    actually following. Editing, versioning and templates are a later slice;
    until they land, a second graph is a question this product cannot answer,
    and the refusal NAMES the plan already standing so an operator knows which.
    """
    standing = next((row.value for row in recovered.records
                     if row.kind == "graph_definition"), None)
    if standing is not None and standing.graph_id != value.graph_id:
        raise RecordConflict(
            f"run {recovered.envelope.run_id!r} already follows graph "
            f"{standing.graph_id!r}; one run carries one graph")


#: The one relation that names which proposal a request was minted from. The
#: runtime spells the key this way and the frozen ALPHA-1 artifacts read it back
#: the same way, so it is the link the journal already carries -- not a guess.
DISPATCH_KEY_PREFIX = "dispatch-"


def _matches_its_node(
        recovered: "RecoveredRun", subject: str, node_id: str | None,
        instance_id: str, capability: str, arguments: object,
        timeout_seconds: int | None = None) -> None:
    """A document that names a node must be the work that node describes.

    An unbound document is left alone: runs without a graph existed before
    graphs did, and they still do. But a binding that nobody checks is worse
    than none at all -- it reads as authority the plan never gave. So the node
    must exist in THIS run's graph, it must be a node that does work, and the
    three facts that decide what runs -- the instance, the capability and the
    arguments -- must be the node's own.

    Both documents that may carry a binding come through here, because a rule
    the proposal obeys and the request does not is not a rule about the run.
    """
    if node_id is None:
        return
    graph = next((row.value for row in recovered.records
                  if row.kind == "graph_definition"), None)
    if graph is None:
        raise StoreError(
            f"{subject} names node {node_id!r} but run "
            f"{recovered.envelope.run_id!r} follows no graph")
    node = next((row for row in graph.nodes if row.node_id == node_id), None)
    if node is None:
        raise StoreError(
            f"{subject} names node {node_id!r}, which graph "
            f"{graph.graph_id!r} does not carry")
    if node.capability is None:
        raise StoreError(
            f"node {node.node_id!r} declares no capability, so no {subject} "
            "carries it out")
    for field_name, mine, planned in (
            ("instance_id", instance_id, node.instance_id),
            ("capability", capability, node.capability)):
        if mine != planned:
            raise StoreError(
                f"{subject} {field_name} does not match node {node.node_id!r}")
    if _thaw_json(arguments) != node.payload():
        raise StoreError(
            f"{subject} arguments do not match node {node.node_id!r}")
    _within_the_planned_ceiling(subject, node, timeout_seconds)


def _within_the_planned_ceiling(subject: str, node, timeout_seconds) -> None:
    """A document may ask for less time than the plan allows, and never more.

    Held HERE and not only where the runtime authorizes, because this relation
    is the one rule that runs on the honest road AND again on a journal
    replayed from disk. A record written straight into the journal cannot buy
    itself more time than the plan gave the step.

    A node naming no ceiling constrains nothing -- which is what every plan
    written before ceilings existed says, and why no stored run changes meaning.
    """
    if (node.timeout_seconds is not None and timeout_seconds is not None
            and timeout_seconds > node.timeout_seconds):
        raise StoreError(
            f"{subject} asks for {timeout_seconds}s, past the "
            f"{node.timeout_seconds}s ceiling node {node.node_id!r} names")


def _proposal_matches_its_node(
        recovered: "RecoveredRun", value: ActionProposal) -> None:
    _matches_its_node(recovered, "proposal", value.node_id, value.instance_id,
                      value.capability, value.arguments,
                      value.timeout_seconds)


def _proposal_named_by(
        recovered: "RecoveredRun", value: ActionRequest) -> ActionProposal | None:
    """The proposal this request's idempotency key NAMES, if the run holds it."""
    if not value.idempotency_key.startswith(DISPATCH_KEY_PREFIX):
        return None
    named = value.idempotency_key[len(DISPATCH_KEY_PREFIX):]
    return next((row.value for row in recovered.records
                 if row.kind == "action_proposal"
                 and row.value.proposal_id == named), None)


def _request_repeats_its_proposal(
        recovered: "RecoveredRun", value: ActionRequest) -> None:
    """A request is a confirmed proposal restated; the journal must show it.

    The runtime copies the proposal's facts on the honest road, and that was
    taken for enough. It is not: a record appended directly, or a journal
    replayed from disk, reaches the store without passing the runtime at all --
    and a request could then run different work, or tie an effect to a gate, to
    a node no graph carries, or to nothing, while the proposal a Human confirmed
    said otherwise.

    So the store holds the same causality the runtime does. The proposal is
    found by the key that NAMES it, and then the facts a Confirm may not change
    are required to be the proposal's own -- the binding first among them, in
    both directions: a bound proposal cannot yield an unbound request, and an
    unbound one cannot yield a bound request.

    The arguments are compared HERE rather than left to the node re-check below,
    which only speaks when a node is named: an unbound proposal reached no check
    at all, and the relation the spec freezes is between the two documents.

    A request that names no proposal and no node is left alone. Actions like
    that were written before proposals carried graphs, and they are still legal.
    """
    proposal = _proposal_named_by(recovered, value)
    if proposal is None:
        if value.node_id is not None:
            raise StoreError(
                f"request names node {value.node_id!r} but repeats no proposal "
                "this run holds")
        return
    if value.node_id != proposal.node_id:
        raise StoreError(
            f"request node binding {value.node_id!r} does not match proposal "
            f"{proposal.proposal_id!r} binding {proposal.node_id!r}")
    for field_name in ("attempt_id", "timeout_seconds", "preview_digest",
                       "instance_id", "capability"):
        if getattr(value, field_name) != getattr(proposal, field_name):
            raise StoreError(
                f"request {field_name} does not match proposal "
                f"{proposal.proposal_id!r}")
    if tuple(value.scope) != tuple(proposal.scope):
        raise StoreError(
            f"request scope does not match proposal {proposal.proposal_id!r}")
    if _thaw_json(value.arguments) != _thaw_json(proposal.arguments):
        raise StoreError(
            f"request arguments do not match proposal {proposal.proposal_id!r}")
    _matches_its_node(recovered, "request", value.node_id, value.instance_id,
                      value.capability, value.arguments,
                      value.timeout_seconds)


def permitted_verifier(recovered: "RecoveredRun", action_id: str) -> str | None:
    """The adapter the PLAN says may sign this action's verification, if any.

    `attempt_replay` requires a terminal success to carry verification evidence
    signed by exactly ONE adapter identity, and until a plan could name a
    verifier that identity could only be the one observed executing. A plan that
    names a `verifier_instance_id` says somebody else checks, and evidence
    signed by the doer is then precisely what must NOT be accepted -- so the
    rule has to learn which identity the plan meant.

    What does not change is the shape of the rule. Exactly one adapter may sign,
    it is derived from FROZEN bytes and from nothing a caller supplies -- the
    run's own graph record and its own frozen configuration, both already part
    of the durable set this validation is a pure function of -- and an instance
    the configuration does not declare resolves to nothing, which refuses.

    `None` means the plan named no verifier, and every journal written before
    this field existed answers `None`: their verdicts are byte-identical to
    what they always were.
    """
    request = next(
        (row.value for row in recovered.records
         if row.kind == "action_request" and row.value.action_id == action_id),
        None)
    if request is None or request.node_id is None:
        return None
    graph = next((row.value for row in recovered.records
                  if row.kind == "graph_definition"), None)
    if graph is None:
        return None
    node = next((row for row in graph.nodes
                 if row.node_id == request.node_id), None)
    if node is None or node.verifier_instance_id is None:
        return None
    from .contracts import frozen_config_bindings

    return frozen_config_bindings(recovered.config).get(node.verifier_instance_id)
