"""The words the schedule answers in, and the two shapes it answers with.

Split from `graph_schedule` the way `graph_values` was split from the two node
contracts: the vocabulary and the answer shape are a self-contained circuit, and
the machinery that computes them is not. The pre-agreed home for exactly this,
so the arithmetic next door has the whole line budget it needs.

Nothing here decides anything. There is no validation either, and that absence
is deliberate: a `NodeSchedule` is not a durable contract and never becomes one.
It is a READING, recomputed from the journal on every question, so there is no
second copy to disagree with the first and nothing for a grammar to protect.
The durable half of an ending is `run_terminal.RunTerminal`, and it is the only
thing here that reaches a byte.

**No `set` reaches an output, and nothing sorts.** Every sequence below is in
the plan's own document order -- `definition.nodes` for nodes, `definition.edges`
for the roads out of one. That is a display order and a tie-break, never an
execution order: when two steps are runnable both are, and a Human chooses which.
A set would have destroyed the order the document already fixed, and a sort
would have invented a different one.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

#: Where one step stands. `blocked` covers two situations a reader must be able
#: to tell apart, and `NodeSchedule.attempts_spent` is what tells them: a step
#: waiting for a road to open can still run, and a step that has spent its
#: `attempt_bound` never can.
NODE_SCHEDULE_STATES = ("blocked", "runnable", "settled", "unreachable")

#: Where the whole plan stands. `complete` means the plan has nothing left to
#: open and NEVER that the run succeeded -- a run that exhausted its retries and
#: a run that was approved both reach it, which is why the Runs screen must show
#: the loop's position and the last outcome beside the word. `open` is the one
#: word that is never durable; `run_terminal.TERMINAL_STATES` is the rest of this
#: tuple, and a test holds the two to each other.
RUN_SCHEDULE_STATES = ("open", "complete", "stalled")

#: What each gate state ROUTES to, derived from `contracts.gate_decision` and
#: from nothing else. `idle` (no receipt stands) and `unknown` (two stand, so the
#: journal supports neither) map to None: they are not decided states, a gate in
#: either is not settled at all, and a road out of one opens for nothing.
#:
#: `MappingProxyType` for `_CONDITIONS_BY_KIND`'s reason next door: a map a
#: caller can edit in place is not a contract.
GATE_ROUTES = MappingProxyType({
    "satisfied": "on_approved",
    "failed": "on_rejected",
    "changes_requested": "on_changes_requested",
    "waived": "on_waived",
    "idle": None,
    "unknown": None,
})


@dataclass(frozen=True)
class NodeSchedule:
    """Where one step stands, and every road into and out of it.

    The three road tuples partition this step's in-edges and are in
    `definition.edges` order, so a reader can say not merely THAT a step is
    blocked but by whom -- and, at a join, that **all** of `blocked_by` must
    open, never any one of them.
    """

    node_id: str
    state: str
    #: Predecessors whose road into this step is OPEN, PENDING and CLOSED.
    opened_by: tuple[str, ...]
    blocked_by: tuple[str, ...]
    closed_by: tuple[str, ...]
    #: Every road OUT of this step as `(to_node, condition)`, in edge order --
    #: the plan's own answer to "where could this go next", replacing the
    #: browser's own walk of the edge list. A `None` condition is unconditional.
    opens: tuple[tuple[str, str | None], ...]
    #: Which lap this step currently owes, and how many it has delivered. For an
    #: auto-settling step -- a task carrying no capability, or a loop node --
    #: `settled_laps` is 0 and stays 0: such a step has no settling fact to
    #: count, it satisfies its lap by construction, and comparing a count here
    #: would deadlock it on the second lap.
    required_pass: int
    settled_laps: int
    #: This step has authorized every attempt the plan allows it, so it can
    #: never settle again and no Human action can change that. The sole producer
    #: of a stalled run.
    attempts_spent: bool
    #: The documents this step is WAITING for, in the order its own arguments
    #: name them. Non-empty only for a `blocked` step whose plan says `block`
    #: and whose inputs are not all standing -- so it is the answer to "why is
    #: this not offered", and it is a third reason distinct from the two above.
    #:
    #: It is NOT part of `blocked_by`, and the difference is load-bearing rather
    #: than tidy. Those three tuples partition this step's IN-EDGES by
    #: predecessor, and the Runs screen renders `blocked_by` under "Waiting on"
    #: followed by the sentence that ALL incoming roads must open. An artifact
    #: reference put there would be read as a step name, and a step waiting only
    #: for a document would render an empty "Waiting on" beside a rule about
    #: roads -- a true sentence about the wrong thing.
    awaiting_artifacts: tuple[str, ...]


@dataclass(frozen=True)
class RunSchedule:
    """What one run's plan says may happen now, computed and never stored."""

    run_id: str
    graph_id: str
    #: Every step, in `definition.nodes` order -- the same order
    #: `graph_runtime` projects in, so the two arrays index alike.
    nodes: tuple[NodeSchedule, ...]
    #: The three subsets a reader acts on, in that same order. `blocked` is not
    #: among them on purpose: it is the residue, and a fourth tuple would be a
    #: fourth thing to keep in step with the first three.
    runnable: tuple[str, ...]
    settled: tuple[str, ...]
    unreachable: tuple[str, ...]
    run_state: str

    def state_of(self, node_id: str) -> str:
        """Where one named step stands, or `unreachable` for a step no plan carries.

        A step this plan does not draw is not blocked and is not runnable: it is
        somewhere the plan cannot reach at all, which is the honest reading and
        the one the eligibility refusal needs when a caller names a stranger.
        """
        for row in self.nodes:
            if row.node_id == node_id:
                return row.state
        return "unreachable"
