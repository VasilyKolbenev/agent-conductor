"""What the command boundary refuses from the records alone.

These holds import no registry, clock or session. A registry's reviewed
capability fact may be supplied as a callable for independent verification.
Each is a pure question about a run's own durable records and the caller's own
body, which is why each was a `@staticmethod` on ``CommandApi`` -- a method
that never touches ``self`` is a function that has not been moved yet, and
``http_api`` reached its line cap carrying three of them.

They are the boundary's half of a doubling this build uses deliberately. Every
one of them is asked again beneath the boundary -- the store refuses a waiver on
a protected gate when it READS the journal, and refuses any record offered to a
run that has recorded its terminal when it APPENDS one, and again when it reads
-- so bytes written around this door are still refused when they come back. The
boundary refuses early and says why; the depth refuses whatever the caller.
"""
from __future__ import annotations

from collections.abc import Iterable

from .api_contracts import ApiRefusal
from .containment import unprovidable_sandboxes
from .contracts import DecisionReceipt
from .graph_causality import (
    _standing_graph,
    decision_is_reached,
    gate_refuses_waiver,
    standing_terminal,
)
from .graph_definition import GraphNode


def _hold_not_terminal(recovered) -> None:
    """A run that recorded its ending accepts nothing further, at the door.

    The gap this closes is exact. `_hold_terminal_is_last` is written over
    the journal as READ, so it judged nothing about the record being
    APPENDED: the byte got written, and only the NEXT read failed
    terminal-must-be-last. The product would brick a run through its own
    front door and then report the journal as corrupt.

    So all three HTTP write doors -- proposals, decisions and artifacts --
    ask this inside their transaction and strictly before the first call
    that can write, and they ask it through one method so the sentence
    exists once. `authorize_holds._hold_run_not_terminal` is the fourth
    door, asking the same question of the same predicate and raising its own
    type, because the runtime's callers are not on this wire.

    Decisions and artifacts ask it AFTER their identity branch, and that is
    the whole rule rather than a concession: the refusal is about RECORDS,
    an exact retry of one that already stands appends none, and a changed
    retry of that identity is a conflict whatever the run's state. Proposals
    ask it before and need no exception -- the id is minted here, so no
    request that door receives can be a retry of a standing record.

    The store holds the same rule beneath all of them, on the append road as
    well as on replay, which is the doubling `_hold_route` already has: the
    boundary refuses early and by name, the depth refuses whatever the caller.
    """
    if standing_terminal(recovered) is not None:
        raise ApiRefusal.fixed("run_terminal")


def _hold_gate_admits(run_id: str, recovered, submitted) -> None:
    """A gate that demands explicit approval is never waived, at this door.

    Asked BEFORE the append and inside the transaction, against the journal
    as it stands, so a refusal leaves the run byte-identical: the caller is
    told no, and nothing about the attempt is durable. The store holds the
    same rule beneath this one on raw replay, which is what makes a forged
    journal unreadable rather than merely unwritable -- the doubling
    `_hold_route` already has, for the same reason.

    The plan is read from the run's own records rather than from anything
    this process holds, and a run following no plan is not judged at all.
    """
    if submitted.action == "waive" and gate_refuses_waiver(
            recovered, submitted.gate_id):
        raise ApiRefusal.gate_refuses_waiver(run_id, submitted.gate_id)


def _hold_gate_is_reached(recovered, submitted) -> None:
    """A decision stands only on a gate this run's plan has REACHED.

    The eligibility rule `authorize` already holds, said at the other door a
    Human acts through. Without it a receipt could settle a gate no road had
    opened -- and because a gate settles from its receipts alone, the step
    behind it became runnable at once and every predecessor was skipped.

    It takes no `run_id`: the whole question is asked of the run's own plan and
    the run's own records, which `recovered` already is, and a parameter this
    hold could not spend would be a fact it looked authorized to use.

    A run following NO plan is not judged at all, exactly as
    `_hold_gate_admits` is not: there is no plan to have reached anything, and
    a journal written before graphs existed must go on being writable.

    The SCHEDULER is deliberately untouched. It settles a gate from that gate's
    receipts alone (scheduler-design §4.1), which is what lets a receipt
    appended straight into the journal -- by an older build, by a fixture, by
    the demo -- still settle its gate on replay. This refuses the LIVE road
    only, so no stored run changes meaning and no recorded terminal is
    recomputed differently.

    Asked inside the transaction, AFTER the prior-receipt lookup and after
    `_hold_not_terminal`, for `_write_artifact`'s reason: the refusal is about
    a NEW record, an exact retry of one that already stands appends none, and
    a changed retry of that identity is a conflict whatever the plan says.
    Strictly before the clock and the append, so a refusal reads no instant and
    leaves `records.jsonl` byte-identical.
    """
    definition = _standing_graph(recovered)
    if definition is None:
        return
    if not decision_is_reached(
            definition, tuple(row.value for row in recovered.records),
            submitted.gate_id, submitted.supersedes):
        raise ApiRefusal.fixed("gate_unreached")


def _hold_plan_pre_answers_no_gate(run_id: str, recovered, nodes) -> None:
    """A plan may not land on a run that already answered one of its gates.

    The second road to the same defect, and it needs its own door because the
    order is reversed: a run with no plan is not judged by the hold above, so a
    decision may legally be written first -- and then the PLAN arrives carrying
    that very gate, which is already settled, with every step in front of it
    untouched. The receipt was legal when it was written and the plan is
    refused instead.

    A decision written before the plan STAYS legal, which is the rule
    `_decision_names_a_planned_gate` keeps and every journal written before
    graphs existed depends on. This does not take it back: what is refused is
    the plan that would adopt such an answer, and only when the plan itself
    carries that gate. A receipt naming a gate the candidate does not draw is
    admitted exactly as it always was.

    Asked inside the transaction of both plan-writing roads, after the standing
    graph is looked for and before the append, so a refused plan leaves the run
    byte-identical.
    """
    planned = {node.gate_id for node in nodes if node.gate_id is not None}
    for row in recovered.records:
        if isinstance(row.value, DecisionReceipt) \
                and row.value.run_id == run_id \
                and row.value.gate_id in planned:
            raise ApiRefusal.fixed("gate_unreached")


def _sandboxes_are_provided(
        run_id: str, nodes: Iterable[GraphNode]) -> None:
    """No run is opened on a plan demanding a route this build cannot give.

    The FIRST of two pre-spawn doors, and the earliest one there is: nothing
    is created, so there is no run to explain afterwards. `authorize_holds`
    holds the same rule at the door where an attempt is authorized, for runs
    opened before this one existed.

    It is deliberately NOT a contract rule. `GraphResource` still admits any
    id-shaped name, so no shipped document moves a byte, no digest changes,
    and a journal already carrying an unprovidable route still REPLAYS --
    it simply authorizes nothing. Refusing in the contract would make such a
    run unreadable, which turns a plan this build cannot honour into a
    journal nobody can read.
    """
    for node in nodes:
        # The FIRST unprovidable route, because a refusal detail is one
        # reviewed fact -- a safe id or a counting number -- and never a
        # list. The caller fixes that row and the next attempt names the
        # next, which is how every other refusal on this boundary behaves.
        for route in unprovidable_sandboxes(node.resources)[:1]:
            raise ApiRefusal.plan_sandbox_unprovidable(
                run_id, node.node_id, route)


def _verifiers_are_servable(
        config, run_id: str, nodes, bound_adapter, verifies_independently, *,
        reachable=None) -> None:
    """Refuse an immutable plan whose named checker this build cannot provide."""
    for node in nodes:
        instance = node.verifier_instance_id
        if instance is None:
            continue
        bound = bound_adapter(config, run_id, instance)
        if reachable is not None and bound not in reachable:
            raise ApiRefusal.service_unreachable_adapter(run_id, instance)
        try:
            supported = verifies_independently(bound, node.capability) is True
        except Exception:
            supported = False
        if not supported:
            raise ApiRefusal.fixed("capability_unsupported")
