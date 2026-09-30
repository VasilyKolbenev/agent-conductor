"""A project whose runs hold every kind of record the desk's feed and summary draw.

The records are written through the production contracts and the real run store, so a run
read of this project is the server's own answer and not a hand-made one. Four tasks stand at
four different places: one whose newest run was accepted at its final gate, one with an attempt
in flight, one whose check did not pass and which waits at the result gate for a person, and
one nobody has started. `tests/desk_feed_reads.py` derives the frozen reads the model tests use
from it, and the browser tests serve it.

The plan is short: one review step that turns the person's brief into a plan document, a gate
where a person confirms it, the `do` step verified by a second participant, and the result gate
that ends the cycle when it is approved. Two harnesses take part, and their duties differ.
"""
from __future__ import annotations

from pathlib import Path

from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, ActionRequest
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.graph_schedule import schedule
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.run_terminal import RunTerminal
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.alpha3_graph_artifacts import dalio_nodes
from tests.test_command_graph_projection import (
    a_decision, a_request, a_result, an_evidence, an_event)
from tests.test_command_run_store import a_run

#: The project's tasks, each with the newest run it earned (None: never started).
TASKS = (
    ("task-closed", "Ship the landing page", "run-closed"),
    ("task-working", "Fix lost text", "run-working"),
    ("task-waiting", "Import the export", "run-waiting"),
    ("task-idle", "Update the API docs", None),
)
DOER, CHECKER = "claude-dev", "codex-check"
CREATED = "2026-08-19T08:00:00Z"
#: Text a person published and text an action published; the second has markup in it, which
#: must be shown as the characters it is.
BRIEF = "Ship the landing page by Friday.\nKeep the hero copy short."
PLAN = "# Plan\n\n1. Draft the hero copy\n2. Put <b>bold</b> in the footer\n"
GRAPH = "graph-progress"
#: What the review step is asked: read the brief, answer under the plan's reference.
ANALYSE = {"work_item_id": "work-001", "target_artifact_refs": ["artifact-brief"],
           "review_profile": "spec", "result_artifact_ref": "artifact-plan"}


def _nodes() -> tuple[GraphNode, ...]:
    do = next(node for node in dalio_nodes() if node.node_id == "do")
    return (
        GraphNode(node_id="analyse", kind="task", title="Analyse the brief",
                  instance_id=DOER, capability="review", arguments=ANALYSE),
        GraphNode(node_id="confirm-gate", kind="gate", title="Confirm the plan",
                  gate_id="gate-confirm-do"),
        GraphNode(node_id="do", kind="task", title="Do the work", stage="do",
                  instance_id=DOER, capability="dispatch", arguments=dict(do.arguments),
                  resources=do.resources, verifier_instance_id=CHECKER),
        GraphNode(node_id="result-gate", kind="gate", title="Accept the result",
                  gate_id="gate-result"))


def _definition(run_id: str) -> GraphDefinition:
    edges = (GraphEdge(from_node="analyse", to_node="confirm-gate"),
             GraphEdge(from_node="confirm-gate", to_node="do", condition="on_approved"),
             GraphEdge(from_node="do", to_node="result-gate"))
    return GraphDefinition(graph_id=GRAPH, run_id=run_id, created_at=CREATED,
                           nodes=_nodes(), edges=edges)


class Journal:
    """One run being written: a store, its digest, an id counter and a clock in minutes."""

    def __init__(self, store: RunStore, run_id: str, digest: str, start: int) -> None:
        self.store, self.run_id, self.digest = store, run_id, digest
        self.index, self.minutes = start, 0
        self.brief_id = ""

    def at(self) -> str:
        self.minutes += 3
        hour, minute = divmod(8 * 60 + self.minutes, 60)
        return f"2026-08-19T{hour:02d}:{minute:02d}:00Z"

    def brief(self) -> None:
        """The person's own document: it names no action as its source."""
        self.index += 1
        self.brief_id = f"artifact-{self.index:03d}"
        self.store.append(ArtifactDocument(
            artifact_id=self.brief_id, artifact_ref="artifact-brief", run_id=self.run_id,
            created_at=self.at(), media_type="text/markdown", content=BRIEF))

    def _start(self, node: GraphNode) -> ActionRequest:
        """Proposed, authorized and started, exactly as the plan's step says."""
        self.index += 1
        run = {"run_id": self.run_id}
        proposal = ActionProposal(
            proposal_id=f"proposal-{self.index}", attempt_id=f"attempt-{self.index:03d}",
            instance_id=node.instance_id, capability=node.capability,
            arguments=dict(node.arguments), scope=("src",), proposed_by=DOER,
            proposed_at=self.at(), timeout_seconds=900, rationale=f"Carry out {node.node_id}.",
            config_digest=self.digest, node_id=node.node_id, **run)
        self.store.append(proposal)
        request = a_request(proposal, self.index, requested_at=self.at(), **run)
        self.store.append(request)
        self.store.append(an_event(request, "effect_lease", self.index,
                                   recorded_at=self.at(), **run))
        return request

    def _observed(self, request: ActionRequest) -> None:
        self.store.append(an_event(request, "execution_observed", self.index,
                                   recorded_at=self.at(), outcome="succeeded", exit_code=0,
                                   run_id=self.run_id))

    def analyse(self) -> None:
        """The review step: it answers the brief with the plan document, and is verified."""
        request = self._start(_nodes()[0])
        self._observed(request)
        run = {"run_id": self.run_id}
        self.index += 1
        plan = ArtifactDocument(
            artifact_id=f"artifact-{self.index:03d}", artifact_ref="artifact-plan",
            run_id=self.run_id, created_at=self.at(), media_type="text/markdown", content=PLAN,
            source_action_id=request.action_id, input_artifact_ids=(self.brief_id,))
        self.store.append(plan)
        proof = an_evidence(request, self.index, observed_at=self.at(), verified_at=self.at(),
                            digest=plan.digest(), **run)
        self.store.append(proof)
        self.store.append(a_result(request, self.index, outcome="succeeded",
                                   observed_at=self.at(), evidence_refs=(proof.evidence_id,),
                                   **run))

    def do(self, outcome: str | None = "succeeded") -> None:
        """The effecting step, checked by the second participant; `None`: still running.

        Only a success names evidence: a check that did not pass leaves no evidence row,
        only a result that says so.
        """
        request = self._start(_nodes()[2])
        if outcome is None:
            return
        self._observed(request)
        run = {"run_id": self.run_id}
        refs: tuple[str, ...] = ()
        if outcome == "succeeded":
            proof = an_evidence(request, self.index, observed_at=self.at(), verified_at=self.at(),
                                created_by="codex-cli", verified_by="codex-cli",
                                verifier_instance_id=CHECKER, **run)
            self.store.append(proof)
            refs = (proof.evidence_id,)
        self.store.append(a_result(request, self.index, outcome=outcome, observed_at=self.at(),
                                   evidence_refs=refs, **run))

    def decide(self, gate_id: str, action: str, reason: str, actor: str = "release-owner") -> None:
        self.index += 1
        self.store.append(a_decision(self.index, gate_id, run_id=self.run_id,
                                     config_digest=self.digest, action=action, actor=actor,
                                     reason=reason, decided_at=self.at()))

    def end(self) -> None:
        values = tuple(row.value for row in self.store.read(self.run_id).records)
        computed = schedule(_definition(self.run_id), values)
        self.index += 1
        self.store.append(RunTerminal(
            terminal_id=f"terminal-{self.index}", run_id=self.run_id, graph_id=GRAPH,
            state=computed.run_state, settled_nodes=computed.settled,
            unreachable_nodes=computed.unreachable, recorded_at=self.at()))


def _open(store: RunStore, run_id: str, task_id: str, start: int) -> Journal:
    config = {"cycle": {"id": "default-orbit"}, "task": {"id": task_id, "work_scope": task_id},
              "instances": [{"id": DOER, "adapter": "claude-code"},
                            {"id": CHECKER, "adapter": "codex-cli"}]}
    digest = snapshot_digest(config)
    store.create_run(a_run(run_id=run_id, mode="confirm", config_digest=digest,
                           created_at=CREATED), config)
    store.append(_definition(run_id))
    journal = Journal(store, run_id, digest, start)
    journal.brief()
    journal.analyse()
    journal.decide("gate-confirm-do", "approve", "Reviewed the plan.")
    return journal


def seed_project(root: Path) -> None:
    """Create the tasks and their runs under `root`."""
    tasks = TaskStore(root)
    for task_id, title, _run in TASKS:
        tasks.create_task(TaskRecord(task_id, title, task_id, CREATED))
    store = RunStore(root)
    closed = _open(store, "run-closed", "task-closed", 100)
    closed.do()
    closed.decide("gate-result", "approve", "Looks right.")
    closed.end()
    _open(store, "run-working", "task-working", 200).do(outcome=None)
    _open(store, "run-waiting", "task-waiting", 300).do("verification_failed")


__all__ = ["CHECKER", "DOER", "TASKS", "seed_project"]
