"""Find the actions a crash left neither resumable nor finished, and close one.

`ControlRuntime.reconcile` has been the whole operation since it landed, and
ADR 0002 sent an operator to it directly. That was not an operable recovery for
two reasons, and this module answers both.

The first is discovery. `reconcile` takes a `run_id` and an `action_id`, and
nothing in the product would tell anyone what those were. A durable request with
no effect lease leaves no message, no exit code and no line in any listing; the
only way to find one was to read `records.jsonl` and replay the causality rules
by eye. :func:`survey` asks the same three questions the runtime asks -- is
there a durable request, does it carry an attempt event, does it already have a
terminal -- and names every action for which the answers are yes, no, no.

The second is that the documented procedure did not run. ADR 0002 printed

    ControlRuntime(RunStore(project_root)).reconcile(run_id, action_id)

and `ControlRuntime.__init__` requires `registry` positionally and `clock` and
`ids` as keyword-only, so the three documented lines raised `TypeError` before
`reconcile` was ever reached. An operator following the only recovery the
product documented got a stack trace. :func:`close` is that call spelled
correctly, once, where a test can execute it.

Nothing here relaxes a refusal. Every gate `reconcile` holds it still holds:
this module resolves no adapter, judges nothing itself, and hands the runtime
two strings. The registry it constructs is deliberately EMPTY -- `reconcile`
never touches `self._registry`, and an empty registry is the honest value for
an operation that starts no effect.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .adapters.base import AdapterRegistry
from .attempt_replay import (
    action_request_for, attempt_events_for, terminal_result_for)
from .run_store import RunStore
from .runtime import ControlRuntime

if TYPE_CHECKING:  # pragma: no cover - import cycle only a checker walks
    from .contracts import ActionResultReceipt


def _clock() -> str:
    """This process's UTC instant, in the one grammar the contracts accept."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ids(kind: str) -> str:
    """An id no other record can collide with, in the contract's own grammar."""
    return f"{kind}-{secrets.token_hex(16)}"


def stuck_actions(values: tuple[object, ...]) -> tuple[str, ...]:
    """Every action in one replayed run that only `reconcile` can close.

    The three questions are the runtime's own, asked in its order and against
    the same replay helpers, so this listing cannot come to disagree with what
    `reconcile` will do when it is called. An action qualifies when it has a
    durable request, carries no attempt event at all, and holds no terminal
    result: that is precisely the state a crash between the request append and
    the effect lease leaves behind.

    Deliberately NOT asked here: the run's mode, and whether the replay left
    warnings. Both are refusals `reconcile` owns, and answering them here would
    hide a run from the listing that an operator needs to be told about -- a
    survey that silently omits a stuck action is worse than one that names it
    and then refuses.

    Args:
        values: The record values of one replayed run, in journal order.

    Returns:
        The action ids, ascending, that a `reconcile` would consider.
    """
    seen: set[str] = set()
    for value in values:
        action_id = getattr(value, "action_id", None)
        if type(action_id) is not str or action_id in seen:
            continue
        seen.add(action_id)
    found = []
    for action_id in sorted(seen):
        if action_request_for(values, action_id) is None:
            continue
        if attempt_events_for(values, action_id):
            continue
        if terminal_result_for(values, action_id) is not None:
            continue
        found.append(action_id)
    return tuple(found)


def survey(root: Path | str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Every run this project holds, with the actions only `reconcile` closes.

    A run that cannot be replayed is reported with an EMPTY tuple rather than
    dropped or raised over: the operator is looking for something to fix, and a
    run whose journal will not read is a different repair with its own
    procedure. Hiding it here would say there was nothing wrong with it.

    Args:
        root: The project root, the directory holding `conductor/`.

    Returns:
        One `(run_id, action_ids)` pair per run directory, ascending by run id.
    """
    from .studio_routes import run_ids

    store = RunStore(root)
    rows: list[tuple[str, tuple[str, ...]]] = []
    for run_id in run_ids(store):
        try:
            recovered = store.read(run_id)
        except Exception:  # noqa: BLE001 - any unreadable run is still listed
            rows.append((run_id, ()))
            continue
        values = tuple(row.value for row in recovered.records)
        rows.append((run_id, stuck_actions(values)))
    return tuple(rows)


def close(root: Path | str, run_id: str, action_id: str) -> "ActionResultReceipt":
    """Close one request-only action, through the runtime and nothing else.

    Args:
        root: The project root, the directory holding `conductor/`.
        run_id: The run the action belongs to.
        action_id: The action to close.

    Returns:
        The one terminal receipt the runtime appended.

    Raises:
        ExecutionError: Any refusal `reconcile` holds.
        StoreError: The run does not exist, or its journal will not read.
    """
    runtime = ControlRuntime(RunStore(root), AdapterRegistry(),
                             clock=_clock, ids=_ids)
    return runtime.reconcile(run_id, action_id).receipt
