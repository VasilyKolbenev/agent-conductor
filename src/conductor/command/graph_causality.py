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

from .contracts import ActionProposal, ActionRequest, DecisionReceipt, _thaw_json
from .graph_definition import GraphDefinition
from .graph_schedule import schedule
from .run_terminal import RunTerminal
from .store_errors import CorruptRun, RecordConflict, StoreError

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


def _standing_graph(recovered: "RecoveredRun") -> GraphDefinition | None:
    """The one plan this run follows, out of its own prior records."""
    return next((row.value for row in recovered.records
                 if row.kind == "graph_definition"), None)


def standing_terminal(recovered: "RecoveredRun") -> RunTerminal | None:
    """The terminal witness this run has recorded, if it has recorded one.

    ONE predicate, spent by every door that must refuse once a run has ended:
    the two HTTP boundaries, the runtime hold beneath them, and the closing road
    that must not mint a second ending. A second spelling would be a second
    answer to "has this run finished", and the doors would disagree about it on
    exactly the journals where it matters.

    `None` for every run that follows no plan, and that is not a special case:
    such a run can never hold a terminal at all, because `_hold_run_terminal`
    refuses one outright.
    """
    return next((row.value for row in recovered.records
                 if row.kind == "run_terminal"), None)


def _decision_names_a_planned_gate(
        recovered: "RecoveredRun", value: DecisionReceipt) -> None:
    """A decision on a planned run answers a gate that run's plan carries.

    A `gate_id` nobody planned is a Human answer to a question the plan never
    asked. Nothing downstream could ever read it -- no node names that gate, so
    no road it might open exists -- and it would sit in the journal looking
    exactly like an answer that mattered.

    A decision written BEFORE the plan stays legal, and that is not a
    concession: a run may be answered and then given a graph, every journal
    written before graphs existed is one such run, and judging those records
    against a plan they predate would make them unreplayable. So the rule is
    guarded by the plan's presence among the PRIOR records, which is the same
    frozen set every other relation here is a pure function of.
    """
    graph = _standing_graph(recovered)
    if graph is None:
        return
    planned = {node.gate_id for node in graph.nodes if node.gate_id is not None}
    if value.gate_id not in planned:
        raise StoreError(
            f"decision {value.receipt_id!r} names gate {value.gate_id!r}, "
            f"which graph {graph.graph_id!r} does not carry")


def gate_refuses_waiver(recovered: "RecoveredRun", gate_id: object) -> bool:
    """Whether this run's plan says that gate may not be set aside.

    The ONE reading of that question, and both doors spend it: the boundary
    asks before it appends, and the store asks again on raw replay. A second
    spelling would let the two disagree -- and the whole point of the pair is
    that bytes written around the boundary are still refused when they are
    read, which only holds if both are asking the same thing.

    A run following no plan answers False: there is no gate to protect, and a
    journal written before graphs existed must go on replaying.
    """
    graph = _standing_graph(recovered)
    if graph is None:
        return False
    return any(node.gate_id == gate_id and node.success_requires is not None
               for node in graph.nodes)


def _decision_may_settle_that_gate(
        recovered: "RecoveredRun", value: DecisionReceipt) -> None:
    """A gate demanding explicit approval carries no waiver, ever.

    The rule above asks whether the gate is one the plan CARRIES; this asks
    whether the answer is one that gate ALLOWS. Both are pure functions of the
    plan's own bytes among the PRIOR records, and both are guarded by the
    plan's presence there for the same reason: a decision written before the
    plan stays legal, and judging a record against a plan it predates would
    make a journal written before graphs existed unreplayable.

    This is the half a forged journal meets. The boundary refuses a waiver
    before it is appended; bytes written around that boundary -- by hand, by an
    older build, by anything -- are refused when they are READ, so the
    protection cannot be edited into the file.
    """
    if value.action != "waive" or not gate_refuses_waiver(
            recovered, value.gate_id):
        return
    raise StoreError(
        f"decision {value.receipt_id!r} waives gate {value.gate_id!r}, which "
        "this run's plan says requires explicit human approval")


def _hold_run_terminal(recovered: "RecoveredRun", value: RunTerminal) -> None:
    """A run records its terminal once, and only about the plan it follows.

    Rule 1 is why a plan-less journal can never hold one of these at all: the
    record names a `graph_id`, and a run with no `graph_definition` has no
    graph_id to name. Rule 2 is what makes the record an identity rather than a
    reading -- a second terminal, under any id, would be a second answer to a
    question that was already answered, and re-minting one at a later instant
    would let one identity carry different facts.

    Rule 3 is what keeps the record from being anything a writer pleases. The
    verdict is RECOMPUTED here from the plan's own bytes and the run's own prior
    records, and the recorded partitions must equal it entry for entry -- so a
    forged terminal, or one whose `settled_nodes` was altered by a single name,
    is refused on the append road and again on the raw-replay road. `schedule`
    is a pure function of a frozen plan and a frozen prefix, and
    `_validate_records` replays each record against exactly the prefix before
    it, so identical bytes reach an identical verdict every time they are read.
    """
    graph = _standing_graph(recovered)
    if graph is None:
        raise StoreError(
            f"run {recovered.envelope.run_id!r} follows no graph, so its plan "
            "has no terminal to record")
    if value.graph_id != graph.graph_id:
        raise StoreError(
            f"run terminal names graph {value.graph_id!r}, and run "
            f"{recovered.envelope.run_id!r} follows {graph.graph_id!r}")
    if standing_terminal(recovered) is not None:
        raise RecordConflict(
            f"run {recovered.envelope.run_id!r} already recorded its terminal")
    computed = schedule(graph, tuple(row.value for row in recovered.records))
    if (value.state, value.settled_nodes, value.unreachable_nodes) != (
            computed.run_state, computed.settled, computed.unreachable):
        raise StoreError(
            "run terminal does not match what this run's own records support")


def _hold_terminal_is_last(records) -> None:
    """A recorded terminal is the last record the journal carries.

    The whole-journal half of the same fact the live doors refuse: a run that
    has recorded its terminal accepts nothing further. Written over the record
    list rather than per record because that is what it says -- everything
    after the terminal is wrong, not the terminal itself.

    It cannot change the verdict on any journal that exists, because none holds
    a terminal, and it stays a REPLAY rule: a hand-written journal carrying a
    record after its terminal is corrupt whatever door wrote it.
    """
    for index, row in enumerate(records):
        if row.kind == "run_terminal" and index != len(records) - 1:
            raise CorruptRun(
                f"{records[index + 1].kind} follows the run terminal; a run "
                "that recorded its terminal accepts no further records")


def _planned_node_of(recovered: "RecoveredRun", action_id: str):
    """The node this action's request was bound to, out of the run's own plan.

    The lookup both plan-derived holds below are written on, extracted so there
    is ONE answer to "which step is this action". Two copies would be two
    chances to disagree about a run with no request, no binding, no graph or no
    such node -- and disagreeing there means one rule firing on a journal the
    other passes, which is the shape a four-layer refusal exists to prevent.

    Every value it reads is durable: the run's own `action_request` record and
    its own `graph_definition` record, both already part of the frozen set this
    validation is a pure function of, and neither of them anything a caller
    supplies. `None` means the plan says nothing about this action -- which is
    what every journal written before graphs, before bindings, and before either
    of these fields answers.
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
    return next((row for row in graph.nodes
                 if row.node_id == request.node_id), None)


def demanded_evidence(recovered: "RecoveredRun", action_id: str) -> str | None:
    """What the PLAN requires this action's verification to NAME, if anything.

    Beside `permitted_verifier` and written to the same law, because it is the
    same kind of fact: a demand the plan makes, derived from frozen bytes and
    from nothing a caller supplies, spent by the one relation that runs on the
    append road and again on the raw-replay road.

    Where `permitted_verifier` says WHO may sign, this says what the signature
    must be OVER. Together they are the whole of what a plan may say about the
    proof a step rests on, and neither can be answered from the evidence row
    itself -- which is exactly why a forged row cannot answer for it.

    `None` means the plan requires nothing beyond what the runtime already
    demands of every step. Every journal written before this field existed
    answers `None`, and so does a request naming no node, a run following no
    graph, and a node this run's graph does not carry: their verdicts are
    byte-identical to what they always were.

    Args:
        recovered: The run replayed so far, oldest record first.
        action_id: The action whose verification is being judged.

    Returns:
        The word from `graph_values.REQUIRED_EVIDENCE` the plan names for this
        step, or None.
    """
    node = _planned_node_of(recovered, action_id)
    return None if node is None else node.required_evidence


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
    node = _planned_node_of(recovered, action_id)
    if node is None or node.verifier_instance_id is None:
        return None
    from .contracts import frozen_config_bindings

    return frozen_config_bindings(recovered.config).get(node.verifier_instance_id)
