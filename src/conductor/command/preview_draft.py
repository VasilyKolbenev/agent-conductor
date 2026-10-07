"""The terms of a preview the server drafts itself, and the budget behind them (spec 6.4.4, 7.8).

The desk sends `{}` and the server answers with the terms it would offer. They come from the
run's frozen plan through `plan_budget`, so the desk holds no arithmetic and the editor's counter
and the conditions card are one calculation. When a grant already stands in the journal the draft
is for the grant that replaces it: the totals of a run span every grant, so what the run spent
is added here, read off the journal, and the plan-budget module reads no journal itself.
"""
from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from .contract_values import ContractError
from .contracts import ActionRequest
from .plan_budget import plan_budget
from .policy_history import current_authorization, spent_budget


def drafted_preview(records: Iterable[Any], limits: Mapping[str, int]) -> tuple[dict, dict]:
    """The body of a preview for a run, and the `Budget` it comes from.

    Args:
        records: The run's stored rows (`kind` and `value`), in journal order.
        limits: `max_actions`, `max_action_seconds` and `max_total_task_seconds` of the
            deployment, from the boundary.

    Returns:
        `(body, budget)`: the five preview fields (`terms_draft` of the budget) and the whole
        `Budget`. The budget is not part of the terms and is never digested.

    Raises:
        ContractError: The run does not follow exactly one frozen plan, or an action it holds
            names a node the plan does not have.
    """
    rows = tuple(records)
    definitions = [row.value for row in rows if row.kind == "graph_definition"]
    if len(definitions) != 1:
        raise ContractError("authorization requires one frozen graph")
    definition, = definitions
    values = tuple(row.value for row in rows)
    spent = _spent(values, definition) if current_authorization(values) is not None else None
    budget = plan_budget(definition.nodes, definition.edges, limits, spent)
    return copy.deepcopy(budget["terms_draft"]), budget


def _spent(values: tuple[object, ...], definition: Any) -> dict[str, Any]:
    """What the run's earlier grants used: actions, reserved seconds, and attempts per step."""
    actions, seconds = spent_budget(values, definition)
    used = Counter(row.node_id for row in values if type(row) is ActionRequest)
    return {"actions": actions, "seconds": seconds,
            "attempts": [{"step_id": node.node_id, "attempts": used[node.node_id]}
                         for node in definition.nodes if used[node.node_id]]}
