"""Store a task's editable review plan separately from task identity and run evidence."""
from __future__ import annotations

import json

from ..atomic_replace import replace_bytes
from ..ownership import owned_write
from .accept_manifest import SnapshotRefused
from .accept_snapshot import _hold, _read
from .api_refusals import ApiRefusal
from .contract_values import _id
from .path_admission import admit_file, admit_name
from .review_plan_source import require_accepted_source
from .store_errors import StoreError
from .task_contracts import _bounded_id
from .task_routes import resolve_task_binding


MAX_REVISION = (1 << 53) - 1
SOURCE_FIELDS = {"task_id", "run_id", "artifact_id", "receipt_id"}


def _integer(value, minimum):
    return type(value) is int and minimum <= value <= MAX_REVISION


def _line(value, maximum):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= maximum
            and all(c.isprintable() for c in value))


def _validate(plan):
    if (not isinstance(plan, dict) or set(plan) != {"version", "reviewer", "steps", "source"}
            or not _integer(plan["version"], 1) or not _line(plan["reviewer"], 160)
            or not isinstance(plan["steps"], list) or not 1 <= len(plan["steps"]) <= 20
            or not all(_line(step, 320) for step in plan["steps"])
            or not isinstance(plan["source"], dict) or set(plan["source"]) != SOURCE_FIELDS):
        raise ApiRefusal.fixed("contract_invalid")
    for name, value in plan["source"].items():
        (_bounded_id if name == "task_id" else _id)(name, value)
        admit_name(value, name)


def _path(tasks, task_id):
    resolve_task_binding(tasks, task_id)
    path = tasks.task_path(task_id) / "review-plan.json"
    admit_file(path, "task review plan")
    return path


def _load(root, path, task_id):
    try:
        stored = json.loads(_read(root, path, 64 * 1024).decode("utf-8"))
        if (not isinstance(stored, dict) or set(stored) != {"task_id", "revision", "plan"}
                or stored["task_id"] != task_id or not _integer(stored["revision"], 1)):
            raise ValueError("invalid task review plan")
        _validate(stored["plan"])
    except FileNotFoundError:
        return {"revision": 0, "plan": None}
    except (ValueError, ApiRefusal, RecursionError, OSError) as error:
        raise StoreError("stored task review plan cannot be read") from error
    return {"revision": stored["revision"], "plan": stored["plan"]}


def read_plan(tasks, runs, task_id):
    with tasks.transaction():
        current = _load(tasks.project_root, _path(tasks, task_id), task_id)
        if current["plan"] is not None:
            require_accepted_source(tasks, runs, task_id, current["plan"]["source"])
        return current


@owned_write
def save_plan(tasks, runs, task_id, body):
    if set(body) != {"expected_revision", "plan"} or not _integer(body["expected_revision"], 0):
        raise ApiRefusal.fixed("contract_invalid")
    plan, expected = body["plan"], body["expected_revision"]
    _validate(plan)
    with tasks.transaction():
        path = _path(tasks, task_id)
        require_accepted_source(tasks, runs, task_id, plan["source"])
        old = _load(tasks.project_root, path, task_id)
        revision = old["revision"]
        if old["plan"] == plan and expected in {revision, revision - 1}:
            return old
        if revision != expected or revision == MAX_REVISION:
            raise ApiRefusal.fixed("draft_conflict")
        updated = {"revision": revision + 1, "plan": plan}
        data = json.dumps({"task_id": task_id, **updated}, ensure_ascii=False).encode("utf-8")
        try:
            _hold(tasks.project_root, path)
            replace_bytes(path, data)
        except (OSError, SnapshotRefused) as error:
            raise StoreError("task review plan could not be saved") from error
        return updated
