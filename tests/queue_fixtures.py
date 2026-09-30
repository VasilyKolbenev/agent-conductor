"""Runs, a driver double and request bodies for the queue's tests (spec 4.4).

`setup` of `test_policy_runtime` builds ONE bounded run named `run` in a store with a real
`PolicyService`. A queue needs several runs in one store, so `add_run` makes another with the same
plan (a gate, then `do`, then `next`, each checked independently) and the same frozen
configuration. `Holder` is the driver double for tests that need a slot in a chosen state: it
refuses exactly as the real driver refuses (`SlotBusy`, `NewWorkHeld`, not running), and the real
driver is used where a test is about the driver itself.
"""
from __future__ import annotations

from conductor.command import queue_store
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contract_values import ContractError
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.path_admission import WindowsPathError
from conductor.command.policy_driver import NewWorkHeld, SlotBusy, SlotSnapshot
from conductor.command.run_store import snapshot_digest
from tests.test_policy_driver import ask
from tests.test_policy_runtime import ARGS, NOW, Activation, setup

__all__ = ["NOW", "ask", "add_run", "start_body", "resume_body", "Holder", "project",
           "CONFIG_TEMPLATE", "long_root", "refuse_receipt_budget"]

CONFIG_TEMPLATE = {"cycle": {"id": "cycle"},
                   "instances": [{"id": "doer", "adapter": "claude-code"},
                                 {"id": "checker", "adapter": "codex-cli"}],
                   "workflow": {"id": "custom", "revision": 1},
                   "automation_contract": "bounded-run-v1"}


def add_run(f, run_id, *, task_id=None):
    """Another bounded run in the store of `f`, the plan of `setup(two_steps, checker)`."""
    config = {**CONFIG_TEMPLATE}
    if task_id is not None:
        config = {**config, "task": {"id": task_id, "work_scope": task_id}}
    f.store.create_run(RunEnvelope(run_id, "cycle", NOW, snapshot_digest(config), mode="policy"),
                       config)
    nodes = [GraphNode("gate", "gate", "Approve", gate_id="gate-id")]
    edges = []
    for index, node_id in enumerate(("do", "next")):
        nodes.append(GraphNode(node_id, "task", node_id, instance_id="doer", capability="dispatch",
            arguments=ARGS, timeout_seconds=30, attempt_bound=2, verifier_instance_id="checker"))
        edges.append(GraphEdge("gate" if index == 0 else "do", node_id,
                               condition="on_approved" if index == 0 else "on_succeeded"))
    f.store.append(GraphDefinition("graph", run_id, NOW, nodes=tuple(nodes), edges=tuple(edges),
                                   execution_contract="bounded-run-v1"))
    f.store.append(ArtifactDocument(artifact_id="instruction-1", run_id=run_id,
        artifact_ref="instructions", created_at=NOW, media_type="text/plain",
        content="Keep my task.\n"))
    f.store.append(DecisionReceipt("decision", run_id, "gate-id", "approve", "owner", NOW,
                                   "Reviewed", ("gate-id",), snapshot_digest(config)))


def project(tmp_path, *run_ids):
    """`setup` with its run `run` and one more run for each id given."""
    f = setup(tmp_path, two_steps=True, checker=True)
    for run_id in run_ids:
        add_run(f, run_id)
    return f


def start_body(f, run_id, authorization_id, *, by="vasily", supersedes=None, terms=None):
    """The `start` half of a `POST /command/queue`: a fresh preview of the run, as reviewed."""
    preview = f.policy.preview(run_id, terms or ask())
    return {"authorization_id": authorization_id, "preview_digest": preview["preview_digest"],
            "terms": preview["terms"], "authorized_by": by, "supersedes": supersedes}


def resume_body(grant, control_id, expected, *, actor="vasily"):
    """The `resume` half: the control of a grant the human was looking at, without its action."""
    return {"control_id": control_id, "authorization_id": grant.authorization_id,
            "authorization_digest": grant.authorization_digest,
            "expected_control_id": expected, "actor": actor}


def long_root(tmp_path, length):
    """A real directory under `tmp_path` whose path is at least `length` characters long."""
    root = tmp_path
    while len(str(root)) < length:
        root = root / "ordinary-parent"
    root.mkdir(parents=True, exist_ok=True)
    return root


def refuse_receipt_budget(monkeypatch, run_id):
    """The receipts of this run are over the Windows path budget, on any platform.

    The trigger is made up, the road is not: `admit_file` is what the store asks for every
    receipt, and it raises here what it raises for a real path over the budget.
    """
    real = queue_store.admit_file

    def budget(path, label):
        if path.parent.parent.name == run_id:       # .../started/<run_id>/<kind>/<record>.json
            raise WindowsPathError(f"{label} exceeds the Windows path budget")
        real(path, label)

    monkeypatch.setattr(queue_store, "admit_file", budget)


class Holder(Activation):
    """A driver whose slot a test sets: who is active, who has an action in flight, who drains."""

    def __init__(self):
        super().__init__()
        self.inflight = None
        self.holding = False
        self.reasons = {}
        self.running = True
        self.woken = 0

    def hold_activation(self, run_id):
        if self.holding:
            raise NewWorkHeld("policy driver is holding new work")
        if not self.running:
            raise ContractError("policy driver is not running")
        for held in (self.active, self.inflight):
            if held is not None and held[0] != run_id:
                raise SlotBusy(held[0])

    def slot(self):
        return SlotSnapshot(self.active[0] if self.active else None,
                            self.inflight[0] if self.inflight else None, self.holding)

    def reason(self, run_id):
        return self.reasons.get(run_id, "ready")

    def wake_queue(self):
        self.woken += 1

    def wake(self, run_id):
        pass
