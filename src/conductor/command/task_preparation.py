"""What a task has and lacks before a run of it may start (spec 6.4.2).

The desk's preparation chain writes in a fixed order and, after a reload, needs one answer to
"where did I get to": this reads it off the durable records. It joins the task, its runs, the
documents each run still lacks, the grant of each and, when the queue has one, its entry. It only
reads. `missing_bindings` is the rule `bind_inputs` holds, asked as a question that answers
instead of raising, and it lives here so the authorization module is not touched.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import studio_routes
from .api_refusals import ApiRefusal
from .artifacts import required_input_refs, settled_products
from .containment import run_route_violations
from .contract_values import ContractError
from .contracts import frozen_config_workflow
from .graph_schedule import schedule
from .policy_history import current_authorization
from .store_errors import StoreError
from .task_contracts import frozen_config_task

if TYPE_CHECKING:  # pragma: no cover - collaborators, never constructed here
    from .run_store import RunStore
    from .task_store import TaskStore

Answer = tuple[int, dict[str, Any]]
#: The stage of a run: the first of these that fits (spec 6.4.2).
STAGES = ("ended", "queued", "authorized", "documents_missing", "ready_to_preview")
#: The two capabilities a bounded run carries out (`authorization_inputs.executable_nodes`).
_BOUND_CAPABILITIES = frozenset({"dispatch", "review"})
_QUEUE_FACTS = ("position", "state", "reason_code", "state_since")


@dataclass(frozen=True)
class QueueView:
    """What the run queue says, handed in by whoever holds the queue (spec 4.4.6).

    `entries` maps a run id to its row (`position`, `state`, `reason_code`, `state_since`) and
    `preauthorized_at` maps the id of a grant the queue started to the instant the human
    pre-authorized it (the receipt of spec 4.4.3). Until the queue exists both are empty.
    """

    entries: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    preauthorized_at: Mapping[str, str] = field(default_factory=dict)


NO_QUEUE = QueueView()


def first_stage(ended: bool, queued: bool, granted: bool, missing: bool) -> str:
    """The stage of a run from the four facts, in the order of `STAGES`; the last always holds."""
    return next(name for name, holds in zip(STAGES, (ended, queued, granted, missing, True))
                if holds)


def read_preparation(tasks: "TaskStore", store: "RunStore", task_id: str,
                     queue: QueueView = NO_QUEUE) -> Answer:
    """`GET /command/tasks/<task_id>/preparation`: the task, its runs and what each still lacks.

    A run whose binding to the task cannot be read is not listed (it is `unreadable` in the run
    list), but its number is counted, so the next run never collides with it.

    Raises:
        ApiRefusal: `service_refused`, naming the id, when no task stands.
        CorruptTask: The directory under this id holds no readable record.
    """
    record = tasks.standing(task_id)
    if record is None:
        raise ApiRefusal.missing_task(task_id)
    ids = studio_routes.run_ids(store)
    rows = (_run_row(store, run_id, task_id, queue) for run_id in ids)
    return 200, {"task": record.as_dict(), "seed": None,
                 "next_run_number": _next_number(ids, task_id),
                 "runs": [row for row in rows if row is not None]}


def _next_number(run_ids: tuple[str, ...], task_id: str) -> int:
    pattern = re.compile(re.escape(task_id) + r"-r([0-9]+)")
    found = [int(named.group(1)) for run_id in run_ids
             if (named := pattern.fullmatch(run_id)) is not None]
    return 1 + max(found, default=0)


def _run_row(store: "RunStore", run_id: str, task_id: str,
             queue: QueueView) -> dict[str, Any] | None:
    if run_route_violations(store, run_id):
        return None
    try:
        recovered = store.read(run_id)
        binding = frozen_config_task(recovered.config)
        followed = frozen_config_workflow(recovered.config)
    except (StoreError, ContractError):
        return None
    if binding is None or binding.task_id != task_id:
        return None
    values = tuple(row.value for row in recovered.records)
    plan = next((row.value for row in recovered.records if row.kind == "graph_definition"), None)
    missing = (missing_bindings(plan, values) if plan is not None
               else {"instructions": [], "inputs": []})
    grant, entry = current_authorization(values), queue.entries.get(run_id)
    ended = any(row.kind == "run_terminal" for row in recovered.records) or (
        plan is not None and schedule(plan, values).run_state == "complete")
    return {
        "run_id": run_id, "created_at": recovered.envelope.created_at,
        "workflow_id": None if followed is None else followed[0],
        "revision": None if followed is None else followed[1],
        "stage": first_stage(ended, entry is not None, grant is not None,
                             bool(missing["instructions"] or missing["inputs"])),
        "missing": missing,
        "grant": None if grant is None else {
            "authorization_id": grant.authorization_id, "authorized_by": grant.authorized_by,
            "authorized_at": grant.authorized_at,
            "preauthorized_at": queue.preauthorized_at.get(grant.authorization_id)},
        "queue": None if entry is None else {key: entry[key] for key in _QUEUE_FACTS},
    }


def missing_bindings(definition: Any, values: tuple[object, ...]) -> dict[str, list]:
    """The documents a run's steps still lack, by the rules of `bind_inputs`, never raising.

    `instructions` names each dispatch step whose instruction is not a document a human
    published (an agent's document does not count), in the order of the plan. `inputs` names,
    sorted, every document a step reads that no document holds and no review of the plan
    produces. Whether a plan can be bound at all (a step that is neither a dispatch nor a
    review) is `bind_inputs`'s verdict and not a document to publish, so such a step is left
    out here. Empty in both lists exactly when `bind_inputs` accepts.
    """
    steps = [node for node in definition.nodes
             if node.kind == "task" and node.capability in _BOUND_CAPABILITIES]
    latest = {row.artifact_ref: row for row in settled_products(values)}
    instructions = [
        {"node_id": node.node_id, "instruction_ref": _ref(node.arguments.get("instruction_ref"))}
        for node in steps if node.capability == "dispatch" and _lacks_instruction(node, latest)]
    reads = {ref for node in steps
             for ref in _refs(required_input_refs(node.capability, node.arguments))}
    made = {_ref(node.arguments.get("result_artifact_ref"))
            for node in steps if node.capability == "review"}
    return {"instructions": instructions, "inputs": sorted(reads - set(latest) - made)}


def _lacks_instruction(node: Any, latest: Mapping[str, Any]) -> bool:
    """Whether no human's document stands under the instruction ref this step names."""
    ref = _ref(node.arguments.get("instruction_ref"))
    return ref is None or ref not in latest or latest[ref].source_action_id is not None


def _ref(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _refs(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(
        value, (list, tuple)) else []
