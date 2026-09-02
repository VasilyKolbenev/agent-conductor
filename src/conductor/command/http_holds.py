"""What the command boundary refuses from the records alone.

Three holds, and what makes them one circuit is what they do NOT need: no
registry, no clock, no session, nothing this process happens to be holding.
Each is a pure question about a run's own durable records and the caller's own
body, which is why each was a `@staticmethod` on ``CommandApi`` -- a method
that never touches ``self`` is a function that has not been moved yet, and
``http_api`` reached its line cap carrying three of them.

They are the boundary's half of a doubling this build uses deliberately. Every
one of them is asked again beneath the boundary -- the store refuses a waiver on
a protected gate when it READS the journal, and refuses a record after a
terminal the same way -- so bytes written around this door are still refused
when they come back. The boundary refuses early and says why; the depth refuses
whatever the caller.
"""
from __future__ import annotations

from collections.abc import Iterable

from .api_contracts import ApiRefusal
from .containment import unprovidable_sandboxes
from .graph_causality import gate_refuses_waiver, standing_terminal
from .graph_definition import GraphNode


def _hold_not_terminal(recovered) -> None:
    """A run that recorded its ending accepts nothing further, at the door.

    The gap this closes is exact. `_validate_records` never judges the
    record being APPENDED: it runs over the journal as read, which passes,
    and then `_validate_new_relation` is asked about the new value alone --
    and none of its arms fires for a decision or a proposal on a terminated
    run. The byte gets written, and only the NEXT read fails
    terminal-must-be-last. The product would brick a run through its own
    front door and then report the journal as corrupt.

    So both write doors ask this inside their transaction and strictly
    before the first call that can write, and they ask it through one method
    so the sentence exists once. The runtime holds it again beneath them,
    which is the doubling `_hold_route` already has: the boundary refuses
    early, the depth refuses whatever the caller.
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
