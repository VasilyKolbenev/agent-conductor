"""Create two local Studio tasks from a colleague's explicitly accepted review notes."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from conductor.init import scaffold_default
from conductor.ownership_transition import activate


def _id(kind):
    return f"{kind}-{uuid.uuid4().hex}"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _line(value, limit, *, required=True):
    if not isinstance(value, str):
        raise ValueError("Ожидалась строка.")
    if any(ord(ch) < 32 or 127 <= ord(ch) <= 159 or ch in "\u2028\u2029" for ch in value):
        raise ValueError("Каждое поле должно занимать одну строку.")
    value = value.strip()
    if (required and not value) or len(value) > limit:
        raise ValueError(f"Проверьте длину поля (до {limit} знаков).")
    return value


def create(project: Path, first: str, second: str, checks: list[tuple[str, str]],
           reviewer: str, *, accepted: bool, performer: str = "", outcome: str = "") -> tuple[str, str]:
    """Publish a fresh personal project after the operator confirms the displayed notes.

    Return the accepted first run ID and the new second task ID. A cancelled review,
    invalid input, or interrupted write must never expose a partial project at this path.
    """
    if accepted is not True:
        raise ValueError("Для записи требуется явная приёмка оператора.")
    if not isinstance(checks, (list, tuple)) or not 1 <= len(checks) <= 12:
        raise ValueError("Укажите от 1 до 12 выполненных проверок.")
    steps = []
    for check in checks:
        if not isinstance(check, (list, tuple)) or len(check) != 2:
            raise ValueError("У каждой проверки должны быть название и наблюдаемый результат.")
        steps.append({"step": _line(check[0], 160), "result": _line(check[1], 600)})
    now = _now()
    first_id, second_id, run_id = _id("task"), _id("task"), _id("run")
    tasks = (TaskRecord(first_id, _line(first, 200), first_id, now),
             TaskRecord(second_id, _line(second, 200), second_id, now))
    actor_id = _id("operator")
    notes = {"schema_version": 1, "task_id": first_id, "run_id": run_id, "actor_id": actor_id,
             "reviewer": _line(reviewer, 100), "performer": _line(performer, 100, required=False),
             "outcome": _line(outcome, 600, required=False), "checks": steps}
    artifact = ArtifactDocument(artifact_id=_id("artifact"), artifact_ref="operator-review-procedure-v1",
                               run_id=run_id, created_at=now, media_type="text/plain",
                               content=json.dumps(notes, ensure_ascii=False, separators=(",", ":")))

    project = Path(project).absolute()
    if os.path.lexists(project):
        raise FileExistsError(f"Проект уже существует: {project}")
    with tempfile.TemporaryDirectory(prefix=".pilot-", dir=project.parent) as stage:
        root = Path(stage) / project.name
        scaffold_default(root)
        for task in tasks:
            TaskStore(root).create_task(task)
        cycle_id = _id("cycle")
        config = {"cycle": {"id": cycle_id}, "instances": [],
                  "task": {"id": first_id, "work_scope": first_id}}
        digest = snapshot_digest(config)
        store = RunStore(root)
        store.create_run(RunEnvelope(run_id=run_id, cycle_id=cycle_id, created_at=now,
                                     config_digest=digest, mode="confirm"), config)
        gate = GraphNode(node_id="operator-review", kind="gate", title="Приёмка записи оператором",
                         gate_id="gate-operator-review", success_requires="human_approval")
        store.append(GraphDefinition(graph_id=_id("graph"), run_id=run_id, created_at=now,
                                     nodes=(gate,), edges=()))
        store.append(artifact)
        store.append(DecisionReceipt(receipt_id=_id("decision"), run_id=run_id, gate_id=gate.gate_id,
                                     action="approve", actor=actor_id, decided_at=now, config_digest=digest,
                                     reason="Принята запись выполненных проверок. " + artifact.digest(),
                                     scope_refs=(artifact.artifact_id,)))
        terminal = close_if_terminal(store, run_id, clock=_now, ids=_id)
        if terminal is None or terminal.state != "complete":
            raise RuntimeError("Журнал не подтвердил завершение приёмки.")
        activate(root, legacy_writers_stopped=True)
        root.rename(project)
    return run_id, second_id
