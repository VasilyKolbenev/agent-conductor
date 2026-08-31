"""What a plan and an attempt ledger permit, asked before anything durable.

Split out of ``runtime`` when that module reached its line cap, along a seam it
already had rather than one invented for the split: everything here is a pure
refusal over a replayed run and a standing proposal. No store is written, no
clock is read, no adapter is prepared, no lock is taken, and nothing here
decides anything -- each function either raises or returns None.

That is also WHERE they belong in the road. ``ControlRuntime._authorize_locked``
calls them after the exact-retry answer and before ``admit``, so a run that
would break one of these relations never reaches a durable byte, an effect
lease, or an adapter. The run store asks the identity relation again as a causal
rule, which is what makes it true of bytes this process did not write; asking it
here is what makes it true early.
"""
from __future__ import annotations

from .contracts import ActionProposal, ActionRequest
from .graph_schedule import authorized_attempts
from .run_store import RecoveredRun
from .runtime_values import AuthorizationError


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
