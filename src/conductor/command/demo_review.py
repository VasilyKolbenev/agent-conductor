"""The offline counter exercise, available only in a throwaway demo project."""
from __future__ import annotations

from .graph_template import GraphTemplate

WORKFLOW = "demo-counter-review"


def template() -> GraphTemplate:
    return GraphTemplate.from_dict({
        "template_id": WORKFLOW, "revision": 1, "title": "Counter check / Проверка счётчика",
        "nodes": [{"node_id": "review-counter", "kind": "gate", "gate_id": "accept",
                   "title": "Result / Результат", "purpose": "A ✓ · B ✗ · C ✓   →   2 / 3"}],
        "edges": [],
    })


def requested(values) -> bool:
    return (values["workflow_id"] == WORKFLOW and values["revision"] == 1
            and values["mode"] == "confirm" and values["task_id"] is not None
            and values["assignments"] == {})
