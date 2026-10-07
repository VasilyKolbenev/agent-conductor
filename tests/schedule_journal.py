"""Build a run's record values the way a run builds them, for schedule tests.

`schedule` is a pure function of a plan and a list of record values in journal
order, so its witnesses need no store, no clock and no adapter -- they need a
journal. This is that journal, and it is a helper module rather than more of
`conftest.py` for the reason the repository already applies: a fixture every
test file inherits is a seam nobody reads, and this one is shared by exactly the
two schedule modules that ask lap questions.

Two things here are deliberate and are the difference between a journal that
proves something and one that merely runs:

- **ids come from a counter.** Every witness is about ORDER and about laps, and
  hand-numbered ids are how a test's belief about what it wrote drifts from what
  it wrote.
- **answering a gate SUPERSEDES the standing answer by default.** That is what a
  run does. A second receipt superseding nothing leaves `gate_decision` unable
  to say which answer is current, so the gate reads `unknown` and settles
  nothing -- a real state, driven deliberately by `supersede=False`, and a
  silent wrecker of any lap witness that reaches it by accident.
"""
from __future__ import annotations

from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    DecisionReceipt,
)
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
)
from conductor.command.graph_schedule_values import NodeSchedule, RunSchedule
from tests.alpha3_graph_artifacts import dalio_definition, dalio_edges

RUN_ID = "run-001"
NOW = "2026-08-30T10:00:00Z"
DIGEST = "sha256:" + "0" * 64
SOLO = {"instances": [{"id": "solo", "adapter": "claude-code"}]}


class Journal:
    """Record values in append order, with one counter and one standing answer."""

    def __init__(self, config_digest: str = DIGEST) -> None:
        self.values: list = []
        self.standing: dict[str, str] = {}
        self.count = 0
        #: The frozen run this journal belongs to. `schedule` never reads
        #: it, so most witnesses leave it at the fixture value -- but a
        #: journal written THROUGH the store must carry that run's own
        #: digest, because the store refuses a decision that does not.
        self.config_digest = config_digest

    def _next(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count:03d}"

    def request(self, node_id: str, *, attempt: str | None = None) -> str:
        """Authorize one attempt at a step, and answer with its action id."""
        action_id = self._next("action")
        self.values.append(ActionRequest(
            action_id=action_id, run_id=RUN_ID,
            attempt_id=attempt or self._next("attempt"), instance_id="solo",
            capability="review", arguments={}, scope=("docs",),
            requested_by="operator", requested_at=NOW,
            idempotency_key=self._next("key"), timeout_seconds=60,
            preview_digest=DIGEST, mode="confirm", node_id=node_id))
        return action_id

    def propose(self, node_id: str, *, attempt: str | None = None) -> None:
        self.values.append(ActionProposal(
            proposal_id=self._next("proposal"), run_id=RUN_ID,
            attempt_id=attempt or self._next("attempt"), instance_id="solo",
            capability="review", arguments={}, scope=("docs",),
            proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
            rationale="because the plan says so",
            config_digest=self.config_digest, node_id=node_id))

    def result(self, action_id: str, outcome: str = "succeeded") -> None:
        self.values.append(ActionResultReceipt(
            receipt_id=self._next("receipt"), action_id=action_id,
            run_id=RUN_ID, attempt_id=self._next("attempt"),
            instance_id="solo", outcome=outcome, observed_at=NOW))

    def did(self, node_id: str, outcome: str = "succeeded") -> None:
        """One whole attempt at a step: authorized, then observed."""
        self.result(self.request(node_id), outcome)

    def decide(self, gate_id: str, action: str, *,
               supersede: bool = True) -> str:
        """Answer a gate, replacing this run's standing answer by default."""
        receipt_id = self._next("decision")
        self.values.append(DecisionReceipt(
            receipt_id=receipt_id, run_id=RUN_ID, gate_id=gate_id,
            action=action, actor="operator", decided_at=NOW,
            reason="stated", scope_refs=("docs",),
            config_digest=self.config_digest,
            supersedes=self.standing.get(gate_id) if supersede else None))
        if supersede:
            self.standing[gate_id] = receipt_id
        return receipt_id

    def rows(self) -> tuple:
        return tuple(self.values)


def routed_dalio(**changes) -> GraphDefinition:
    """The Dalio cycle as revision 3 draws it: two roads gain a condition.

    `confirm-gate -> do` opens only on approval, so a rejected gate no longer
    opens the effecting step; `result-gate -> retry-loop` opens only on changes
    requested, so an approval ends the cycle. `do -> result-gate` stays
    unconditional, so the result gate reviews a failure as well as a success.

    Built from the shipped v2 edges rather than typed out, so a change to the
    canonical cycle reaches these witnesses instead of passing them by.
    """
    conditions = {("confirm-gate", "do"): "on_approved",
                  ("result-gate", "retry-loop"): "on_changes_requested"}
    edges = tuple(
        GraphEdge(from_node=edge.from_node, to_node=edge.to_node,
                  condition=conditions.get((edge.from_node, edge.to_node)))
        for edge in dalio_edges())
    return dalio_definition(run_id=RUN_ID, edges=edges, **changes)


def with_a_note(plan: GraphDefinition) -> GraphDefinition:
    """The same plan with a step that carries out no work, inside the body.

    Wired IN rather than left beside the plan: a body is the intersection of
    what the loop reopens and what reaches the loop, so a step hanging off
    nothing is in no body and would prove nothing about a reopened one.
    """
    return GraphDefinition(
        graph_id=plan.graph_id, run_id=plan.run_id, created_at=plan.created_at,
        nodes=(*plan.nodes,
               GraphNode(node_id="note", kind="task", title="Note")),
        edges=(*plan.edges,
               GraphEdge(from_node="identify", to_node="note"),
               GraphEdge(from_node="note", to_node="retry-loop")))


def a_bounded_plan(bound: int | None) -> GraphDefinition:
    """One gated, effecting step, with whatever attempt ceiling is asked."""
    return GraphDefinition(
        graph_id="graph-bounded", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="gate-1"),
               GraphNode(node_id="do", kind="task", title="Do",
                         instance_id="solo", capability="dispatch",
                         attempt_bound=bound)),
        edges=(GraphEdge(from_node="gate", to_node="do"),))


def row_of(computed: RunSchedule, node_id: str) -> NodeSchedule:
    return next(row for row in computed.nodes if row.node_id == node_id)


def loop_of(plan: GraphDefinition) -> GraphNode:
    return next(node for node in plan.nodes if node.loop is not None)


def through_the_body(journal: Journal, gate: str = "approve") -> None:
    """One traversal: every thinking step, the confirm gate, and the work."""
    for node_id in ("identify", "diagnose", "design"):
        journal.did(node_id)
    journal.decide("gate-confirm-do", gate)
    journal.did("do")
