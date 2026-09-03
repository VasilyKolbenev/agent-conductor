"""What the command boundary refuses from the records alone.

Three holds, and what makes them one circuit is what they do NOT need: no
registry, no clock, no session, nothing this process happens to be holding.
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
from .graph_causality import gate_refuses_waiver, standing_terminal
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
