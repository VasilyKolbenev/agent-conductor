"""Journal-only foundation for acceptance (spec 9.4), never permission to write Git.

The caller supplies validated journal values in append order and a COMPLETE inventory of
the task's runs, including the current run and current execution/queue facts. No filesystem,
Git, clock or store is consulted here. A successful files basis still owes snapshot integrity
and current work-tree checks to the future preview; an evidence digest alone proves neither.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .artifacts import ArtifactDocument, REVIEW_CAPABILITY
from .contract_values import ContractError, _digest, _id, _timestamp
from .contracts import ActionRequest, DecisionReceipt, EvidenceRef, gate_decision
from .graph_definition import GraphDefinition
from .run_terminal import RunTerminal
from .seed_record import SeedRecord, WORK_ITEM_ID
from .task_contracts import TaskBinding

STARTER_DOC_PATHS = {"desk-starter-docs": {
    "artifact-brief": "docs/idea.md", "artifact-plan": "docs/plan.md",
    "artifact-ideas": "docs/ideas.md", "artifact-scheme": "docs/scheme.md"}}


@dataclass(frozen=True)
class AcceptanceRun:
    """Facts read by the caller, with the task taken from this run's frozen config.

    Unknown execution, queue or journal state must refuse at the calling boundary; it must
    not be converted to False. Timestamps do not order journal records, only separate runs.
    """

    run_id: str
    task: TaskBinding | None
    created_at: str
    has_action_requests: bool
    active: bool
    queued: bool

    def __post_init__(self):
        _id("run_id", self.run_id)
        _timestamp("created_at", self.created_at)
        if self.task is not None and type(self.task) is not TaskBinding:
            raise ContractError("acceptance run needs its frozen TaskBinding or None")
        if any(type(value) is not bool for value in (
                self.has_action_requests, self.active, self.queued)):
            raise ContractError("acceptance run activity facts must be known booleans")


@dataclass(frozen=True)
class AcceptanceBasis:
    """A refusal or confirmed JOURNAL facts plus checks the preview still MUST perform.

    `pending_checks` is explicit even for a successful files basis: only a future preview can
    establish `snapshot_damaged` or `work_changed_since_verification`. This is not a preview,
    contains no acceptance digest and authorizes no commit, push or other write.
    """

    kind: str
    refused: str | None = None
    final_gate: str | None = None
    decision_id: str | None = None
    decided_at: str | None = None
    verified_action: str | None = None
    work_tree_digest: str | None = None
    accept_manifest_digest: str | None = None
    pending_checks: tuple[str, ...] = ()


def acceptance_basis(definition: GraphDefinition, records: Iterable[object],
                     task_runs: Iterable[AcceptanceRun], seed: SeedRecord | None) -> AcceptanceBasis:
    """Judge 9.4's journal facts; caller-owned inventory completeness is a precondition.

    Malformed input or a seed bound to another task/scope is a ContractError, not an absent
    seed. `records` contains record values, not store wrappers. Journal replay owns the full
    record/plan validity contract; this function adds acceptance's stricter requirements.
    """
    values, runs = tuple(records), tuple(task_runs)
    run = _current_run(definition, values, runs)
    dispatch = tuple(node.node_id for node in definition.nodes if node.capability == "dispatch")
    kind = "files" if dispatch else "documents"
    refuse = lambda reason: AcceptanceBasis(kind, refused=reason)
    if run.task is None:
        return refuse("run_has_no_task")
    _hold_seed(seed, run.task)
    if kind == "files" and seed is None:
        return refuse("seed_missing")
    terminals = [value for value in values if isinstance(value, RunTerminal)]
    if (len(terminals) != 1 or terminals[0].state != "complete"
            or terminals[0].graph_id != definition.graph_id):
        return refuse("run_not_complete")
    decision = _final_decision(definition, values)
    if decision is None:
        return refuse("final_gate_not_approved")
    checked = _checked_dispatch(values, dispatch) if dispatch else _checked_documents(values)
    if checked is None:
        return refuse("result_not_verified")
    decision_at, receipt = decision
    if any(position >= decision_at for position, _evidence, _action in checked):
        return refuse("decision_precedes_result")
    if kind == "files":
        return _files_basis(run, runs, values, checked, receipt)
    latest = max(checked, key=lambda row: row[0], default=None)
    return AcceptanceBasis(kind, final_gate=receipt.gate_id, decision_id=receipt.receipt_id,
        decided_at=receipt.decided_at, verified_action=None if latest is None else latest[2].action_id)


def _files_basis(run, runs, values, checked, receipt):
    same_task = [other for other in runs if other.task is not None
                 and other.task.task_id == run.task.task_id]
    if any(other.run_id != run.run_id and other.has_action_requests
           and _instant(other.created_at) == _instant(run.created_at) for other in same_task):
        raise ContractError("same-time task runs with work cannot be ordered for acceptance")
    if any(other.has_action_requests and _instant(other.created_at) > _instant(run.created_at)
           for other in same_task):
        return AcceptanceBasis("files", refused="superseded_by_later_run")
    if any(other.active or other.queued for other in same_task):
        return AcceptanceBasis("files", refused="task_run_active")
    final = _final_snapshot(values, checked)
    if final is None:
        return AcceptanceBasis("files", refused="final_check_missing")
    evidence, action = final
    return AcceptanceBasis("files", final_gate=receipt.gate_id, decision_id=receipt.receipt_id,
        decided_at=receipt.decided_at, verified_action=action.action_id,
        work_tree_digest=evidence.extra["work_tree_digest"],
        accept_manifest_digest=evidence.extra["accept_manifest_digest"],
        pending_checks=("snapshot_integrity", "current_work_tree"))


def _current_run(definition, values, runs):
    if any(type(run) is not AcceptanceRun for run in runs):
        raise ContractError("task_runs must contain AcceptanceRun facts")
    if len({run.run_id for run in runs}) != len(runs):
        raise ContractError("task_runs contains duplicate runs")
    current = [run for run in runs if run.run_id == definition.run_id]
    if len(current) != 1:
        raise ContractError("complete task_runs must include the current run")
    if any(getattr(value, "run_id", None) != definition.run_id for value in values):
        raise ContractError("acceptance journal contains another run's record")
    if current[0].has_action_requests != any(isinstance(value, ActionRequest) for value in values):
        raise ContractError("current run action facts disagree with its journal")
    return current[0]


def _hold_seed(seed, task):
    if seed is not None and (type(seed) is not SeedRecord or
            (seed.task_id, seed.work_scope, seed.work_item_id)
            != (task.task_id, task.work_scope, WORK_ITEM_ID)):
        raise ContractError("seed does not match the frozen task and work item")


def _final_decision(definition, values):
    receipts = [value for value in values if isinstance(value, DecisionReceipt)]
    finals = {node.gate_id for node in definition.nodes if node.kind == "gate"
              and not any(edge.from_node == node.node_id and edge.condition in (None, "on_approved")
                          for edge in definition.edges)}
    satisfied = {gate for gate in finals
                 if gate_decision(receipts, definition.run_id, gate) == "satisfied"}
    superseded = {receipt.supersedes for receipt in receipts}
    return next(((at, value) for at, value in reversed(tuple(enumerate(values)))
                 if isinstance(value, DecisionReceipt) and value.gate_id in satisfied
                 and value.receipt_id not in superseded), None)


def _evidence(values, action):
    rows = [(at, value) for at, value in enumerate(values) if isinstance(value, EvidenceRef)
            and value.kind == "verification" and value.uri == f"verification/{action.action_id}"]
    if len(rows) != 1 or rows[0][1].verification != "verified" or rows[0][1].digest is None:
        return None
    return rows[0]


def _checked_dispatch(values, nodes):
    latest = {value.node_id: (at, value) for at, value in enumerate(values)
              if isinstance(value, ActionRequest) and value.capability == "dispatch"}
    checked = []
    for node in nodes:
        if node not in latest:
            return None
        requested_at, action = latest[node]
        found = _evidence(values, action)
        if (found is None or found[0] <= requested_at or
                found[1].verifier_instance_id in (None, action.instance_id)):
            return None
        checked.append((*found, action))
    return checked


def _checked_documents(values):
    reviews = {value.action_id: (at, value) for at, value in enumerate(values)
               if isinstance(value, ActionRequest) and value.capability == REVIEW_CAPABILITY}
    documents = [value for value in values if isinstance(value, ArtifactDocument)
                 and value.source_action_id in reviews]
    checked = []
    for document in documents:
        requested_at, action = reviews[document.source_action_id]
        found = _evidence(values, action)
        if found is None or found[0] <= requested_at or found[1].digest != document.digest():
            return None
        checked.append((*found, action))
    return checked


def _final_snapshot(values, checked):
    actions = {f"verification/{value.action_id}": value for value in values
               if isinstance(value, ActionRequest) and value.capability == "dispatch"}
    proofs = [(at, value, actions[value.uri]) for at, value in enumerate(values)
              if isinstance(value, EvidenceRef) and value.kind == "verification"
              and value.uri in actions]
    position, evidence, action = max(proofs, key=lambda row: row[0])
    if not any(evidence is row[1] for row in checked):
        return None
    if any(isinstance(value, ActionRequest) and value.capability == "dispatch"
           for value in values[position + 1:]):
        return None
    try:
        for name in ("accept_manifest_digest", "work_tree_digest"):
            _digest(name, evidence.extra.get(name))
    except ContractError:
        return None
    return evidence, action


def _instant(value):
    # AcceptanceRun validated the fixed UTC grammar; equal suffix/fraction spellings tie.
    seconds, _, fraction = value.removesuffix("Z").removesuffix("+00:00").partition(".")
    return seconds, fraction.rstrip("0")
