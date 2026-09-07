"""What a plan and an attempt ledger permit, asked before anything durable.

Split out of ``runtime`` when that module reached its line cap, along a seam it
already had rather than one invented for the split: everything here is a pure
refusal over a replayed run and a standing proposal. No store is written, no
clock is read, no adapter is prepared, no lock is taken, and nothing here
decides anything -- each function either raises or returns None.
A registry fact may be supplied as a callable; no registry is imported here.

That is also WHERE they belong in the road. ``ControlRuntime._authorize_locked``
calls them after the exact-retry answer and before ``admit``, so a run that
would break one of these relations never reaches a durable byte, an effect
lease, or an adapter. The run store asks the identity relation again as a causal
rule, which is what makes it true of bytes this process did not write; asking it
here is what makes it true early.
"""
from __future__ import annotations

from .containment import unprovidable_sandboxes
from .contracts import ActionProposal, ActionRequest, frozen_config_bindings
from .graph_causality import _standing_graph, standing_terminal
from .graph_schedule import attempt_in_flight, authorized_attempts, schedule
from .run_store import RecoveredRun
from .runtime_values import AuthorizationError, RunAlreadyTerminal


def _planned_node(recovered: RecoveredRun, node_id: str | None):
    """The node this document names, out of the run's own frozen plan."""
    if node_id is None:
        return None
    graph = next((row.value for row in recovered.records
                  if row.kind == "graph_definition"), None)
    if graph is None:
        return None
    return next((row for row in graph.nodes if row.node_id == node_id), None)


def _hold_plan_bounds(
        proposal: ActionProposal, recovered: RecoveredRun) -> None:
    """The ceilings the PLAN placed on this step, spent before anything durable.

    Here rather than at execute, and here rather than only in the store's
    relation, because this is the last frame before a request is minted: no
    durable byte has been written, no effect authority has been granted, and no
    adapter has been touched. A bound checked after any of those is a bound
    that has already been exceeded once.

    What is counted is AUTHORIZED attempts -- durable `action_request` records
    naming this node -- and never proposals. A proposal is a request for an
    attempt and not an attempt: nothing has been spent until a Human confirms
    one. Counting proposals shipped once and was wrong in the worst direction,
    because proposals are not ordered against the confirmation being judged. Two
    proposals standing on a node with a bound of one meant authorizing EITHER of
    them found the other already "spent", so the bound refused the first attempt
    it was ever asked about. `tests/test_command_plan_bounds.py` drives
    `authorize` itself now, which is the only road that spends this bound and
    the road those first tests never touched.

    One ROW is one authorization. This counted distinct `attempt_id`s instead,
    on the stated ground that a byte-identical retry must not spend the bound
    twice -- and that ground was false twice over. An exact retry never arrives
    here at all: `_authorize_locked` finds the standing request by its
    `idempotency_key` and returns it several frames above, having written
    nothing. And a journal cannot hold one request twice in any case, because
    `_validate_records` refuses a second row under a key it has already seen.
    So the set bought no protection and sold the bound: three confirmations
    carrying one `attempt_id` measured as one attempt, and a ceiling of two
    admitted all three.

    A node naming no ceiling constrains nothing, which is what every plan
    written before ceilings existed says, and why no stored run changes meaning.
    """
    node = _planned_node(recovered, proposal.node_id)
    if node is None or node.attempt_bound is None:
        return
    spent = authorized_attempts(
        tuple(row.value for row in recovered.records), proposal.node_id)
    if spent >= node.attempt_bound:
        raise AuthorizationError(
            f"plan: node {proposal.node_id!r} allows {node.attempt_bound} "
            f"attempt(s) and has already authorized {spent}")


def _hold_node_is_eligible(
        proposal: ActionProposal, recovered: RecoveredRun) -> None:
    """A planned run authorizes the steps its PLAN makes runnable, and no others.

    This is what closes the caller-selected `node_id`. The binding was already
    held to the node's own facts -- same instance, same capability, same
    arguments -- but nothing asked whether the plan had reached that step at
    all. A caller could name any node the graph carried and have the work
    authorized out of order, and the plan would look like it was being followed.

    The rule is MEMBERSHIP in what the schedule computes, never the presence of
    a field: `runnable` never carries a node whose predecessors are unsettled,
    whose gate is unanswered, whose road was closed, which is already settled,
    which has spent its `attempt_bound`, or which has an attempt still in
    flight. So the refusals for all six arrive together and cannot drift apart
    -- and the last of them is why a bound of two never means two at once.

    A plan-less run returns at the first line, unchanged: runs without a graph
    existed before graphs did and they still do. A proposal naming NO node on a
    run that has one is refused rather than exempted -- an unbound action on a
    planned run is the very hole this closes, and it also mis-resolves the
    verifier, because both verifier doors key off the request's binding.
    """
    definition = _standing_graph(recovered)
    if definition is None:
        return
    if proposal.node_id is None:
        raise AuthorizationError(
            f"plan: run {recovered.envelope.run_id!r} follows graph "
            f"{definition.graph_id!r} and this proposal names no node")
    values = tuple(row.value for row in recovered.records)
    computed = schedule(definition, values)
    if proposal.node_id not in computed.runnable:
        raise AuthorizationError(
            f"plan: node {proposal.node_id!r} is "
            f"{computed.state_of(proposal.node_id)}"
            f"{_awaiting(computed, proposal, values)}"
            f" and this run's plan makes {list(computed.runnable)} runnable now")


def _awaiting(computed, proposal: ActionProposal, values: tuple) -> str:
    """Why a step is blocked, when the plan can say something more than the word.

    `blocked` covers four situations and a caller meeting the bare word cannot
    tell them apart. Two of them are about this plan's own shape and a reader
    can see them in it. The other two are not in the plan at all and each is
    something a person can act on, so each is named here: a DOCUMENT that does
    not exist yet, which somebody has to go and publish, and an ATTEMPT that is
    already running, which ends by itself and needs nothing but waiting.

    The document is asked first and neither arm derives anything: the schedule
    computed the row, and the in-flight fact is read through the one function
    §4 and §5.3 also spend, so the sentence and the refusal cannot disagree.
    """
    row = next((row for row in computed.nodes
                if row.node_id == proposal.node_id), None)
    if row is None:
        return ""
    if row.awaiting_artifacts:
        return (" waiting for artifact(s) "
                f"{list(row.awaiting_artifacts)} its plan requires before it runs")
    if attempt_in_flight(values, proposal.node_id):
        return " because an attempt on this step is still in flight"
    return ""


def _hold_node_sandbox_is_provided(
        proposal: ActionProposal, recovered: RecoveredRun) -> None:
    """A step may not be attempted on a route this build cannot give it.

    A `sandbox` resource is a DEMAND the plan makes of whatever machine runs the
    work, and until it had a consumer the demand was recorded and spent by
    nobody: a plan naming any route-shaped word ran exactly as if it had named
    none. That is the lie this closes, and it is closed BEFORE the spawn rather
    than at it, because the answer is knowable from the plan alone -- no attempt
    is made, no task is started, and no receipt has to explain one.

    This is the SECOND of the two doors, and it exists for the runs the first
    one cannot reach: a run opened before this rule, or a plan written onto a
    run by another road. `studio_routes.open_run` refuses at the door where a
    run is created; this refuses at the door where an attempt is authorized.
    Their sentences are deliberately different, and each is witnessed against
    its own, because two doors saying one sentence is one door with two names.

    Only `sandbox` rows are judged. The other five kinds are recorded and
    consumed by nothing, so a name outside any list is admitted and inert --
    refusing one would be inventing a promise this build does not keep.
    """
    definition = _standing_graph(recovered)
    if definition is None or proposal.node_id is None:
        return
    node = next((row for row in definition.nodes
                 if row.node_id == proposal.node_id), None)
    if node is None:
        return
    missing = unprovidable_sandboxes(node.resources)
    if missing:
        raise AuthorizationError(
            f"plan: step {proposal.node_id!r} demands sandbox route(s) "
            f"{list(missing)} that this build does not provide, so no attempt "
            "may be authorized for it")


def _hold_plan_admits(
        proposal: ActionProposal, recovered: RecoveredRun, *,
        verifies_independently=None) -> None:
    """Everything the PLAN says about this authorization, asked in one place.

    Ended first, then eligible: a run that has recorded its ending has no
    runnable steps to speak of, so asking which step is eligible would answer a
    question about a run that is over. One call site keeps the order a fact of
    this module rather than of whoever wired it in.
    """
    _hold_run_not_terminal(recovered)
    _hold_node_is_eligible(proposal, recovered)
    _hold_node_sandbox_is_provided(proposal, recovered)
    _hold_verifier_is_servable(proposal, recovered, verifies_independently)


def _hold_verifier_is_servable(proposal, recovered, verifies_independently) -> None:
    """A named checker must be a declared, independently capable participant."""
    node = _planned_node(recovered, proposal.node_id)
    if node is None or node.verifier_instance_id is None:
        return
    instance = node.verifier_instance_id
    bound = frozen_config_bindings(recovered.config).get(instance)
    if bound is None:
        raise AuthorizationError(
            f"plan: verifier instance {instance!r} is not declared by this run's configuration")
    try:
        supported = callable(verifies_independently) and verifies_independently(
            bound, node.capability) is True
    except Exception:
        supported = False
    if not supported:
        raise AuthorizationError(
            f"plan: verifier instance {instance!r} is bound to adapter {bound!r}, "
            "which cannot verify another participant's result")


def _hold_run_not_terminal(recovered: RecoveredRun) -> None:
    """A run that recorded its ending authorizes nothing further.

    The depth half of a refusal the HTTP boundary also makes, and the doubling
    is the same one `_hold_route` already has for the same reason: the boundary
    refuses early, and this refuses whatever the caller. A record appended after
    a terminal makes the journal `CorruptRun` on its very next read, so the only
    acceptable place to find out is before any byte is written.

    It raises its OWN type rather than a plain `AuthorizationError`, because the
    wire word for this is not "your confirmation did not authorize" -- it is
    "this run is over". The translation is by type and never by reading a
    message.
    """
    terminal = standing_terminal(recovered)
    if terminal is not None:
        raise RunAlreadyTerminal(
            f"run {recovered.envelope.run_id!r} recorded its terminal "
            f"{terminal.terminal_id!r} and accepts no further records")


def _hold_attempt_identity(
        proposal: ActionProposal, recovered: RecoveredRun) -> None:
    """One attempt id names one action, refused before anything is admitted.

    The relation already existed for attempt EVENTS -- `validate_attempt_event`
    refuses an event whose `attempt_id` "already belongs to another action" --
    and did not exist for the requests those events describe. So two actions
    could be authorized under one attempt identity, and the contradiction only
    surfaced later and elsewhere: the first action to record an event claimed
    the id, and every other action holding it could never record one. A journal
    `authorize` itself wrote then held work that could not proceed and that
    nothing in the journal explained.

    Asked here because here is before `admit`: no durable byte, no effect
    lease, no adapter. The store asks it again as a causal relation, which is
    what makes it true of bytes this process did not write; asking it here is
    what makes it true EARLY, so a run never reaches that state at all.

    Kept apart from `_hold_plan_bounds` deliberately. They answer different
    questions -- "how many attempts may this step have" and "is this attempt
    already somebody else's" -- and one refusal standing in for the other is
    exactly how the bound came to be counted by identity.
    """
    for row in recovered.records:
        if (isinstance(row.value, ActionRequest)
                and row.value.attempt_id == proposal.attempt_id):
            raise AuthorizationError(
                f"attempt_id {proposal.attempt_id!r} already belongs to another "
                f"action, {row.value.action_id!r}")
