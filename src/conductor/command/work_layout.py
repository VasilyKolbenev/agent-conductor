"""The single pure work layout, shared by core admission and every transport.

No adapter, store, filesystem or process dependency. Re-exported by the existing
harness_workspace module so readers, argv construction and historical imports
continue to use precisely the same functions and path components.
"""
from __future__ import annotations

WORK_DIR = "work"
#: The container every TASK's work lives in, one level below the work tree. It
#: can never be a work item's own directory: a work item id begins with a letter
#: or a digit, so no plan written before tasks existed -- and no task-less plan
#: written since -- can name it, in any letter case, on any filesystem. A task's
#: work is kept apart from history by STRUCTURE, not by a spelling that a legal
#: legacy id could also have used (the 2026-09-18 review's R1 and R2).
TASKS_DIR = "_tasks"


def work_parts(work_item_id: str, work_scope: str | None = None) -> tuple[str, ...]:
    """The route below the workspace root where ONE work item's files live.

    The single definition of that place: the directory a child stands in, the
    tree a checker reads, and the path an argv names are all this answer, so they
    cannot come to disagree. A task-less item lives at ``work/<item>``, exactly
    where it always has, so no standing plan's directory moves. A task's item
    lives at ``work/_tasks/<scope>/<item>``: two tasks are two directories because
    their scopes are two path COMPONENTS -- there is no encoding to be ambiguous --
    and nothing a task-less item can be named reaches under ``_tasks``.

    Args:
        work_item_id: The plan's own work item id.
        work_scope: The run's task scope, or None for a task-less run.

    Returns:
        The route parts, the work tree's own name first.
    """
    if work_scope is None:
        return (WORK_DIR, work_item_id)
    return (WORK_DIR, TASKS_DIR, work_scope, work_item_id)


def work_route(work_item_id: str, work_scope: str | None = None) -> str:
    """`work_parts` spelled as the relative path an argv carries."""
    return "/".join(work_parts(work_item_id, work_scope))
