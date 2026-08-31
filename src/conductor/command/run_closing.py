"""Recording that a run's plan has ended, on the two doors that can end one.

`graph_schedule` computes the verdict and deliberately cannot write it: that
module states, and a test holds, that it touches no store, no clock and no
filesystem. So the road that turns a computed verdict into a durable record
lives here, beside nothing else, and is the only thing in this package that
appends a `RunTerminal`.

Two properties make it safe to call from more places than it is called from:

- **it is a no-op unless it has something new to say.** No plan, a terminal
  already standing, or a plan still open, and it writes nothing and returns
  without minting an identity.
- **what is judged is what is appended.** The record is built from the verdict's
  OWN values and the store is never re-read between deciding and writing. A
  second read there would let the facts move under one identity -- the defect
  this shape exists to make unrepresentable.

That is also why a terminal already standing is returned UNCHANGED rather than
recomputed. Two calls at two instants must not be able to produce two different
sets of facts under one run's one ending.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .graph_causality import _standing_graph, standing_terminal
from .graph_schedule import schedule
from .run_terminal import RunTerminal

if TYPE_CHECKING:  # pragma: no cover -- import cycle avoided at runtime
    from .run_store import RunStore


def close_if_terminal(store: "RunStore", run_id: str, *, clock,
                      ids) -> RunTerminal | None:
    """Record this run's ending if its own records now support one.

    Called from the two doors that append a settling fact -- a Human's decision
    and an attempt's terminal receipt -- inside the transaction that appended
    it, so the verdict is taken against the very journal that caused it.
    `reconcile` needs no third call site: it ends in the same `_finish`.

    Args:
        store: The run store, already inside a transaction on this run.
        run_id: The run whose plan is being judged.
        clock: Supplies `recorded_at`.
        ids: Supplies `terminal_id`.

    Returns:
        The terminal this call recorded, the one already standing, or None when
        the run follows no plan or its plan is still open.
    """
    with store.transaction():
        recovered = store.read(run_id)
        graph = _standing_graph(recovered)
        if graph is None:
            return None
        standing = standing_terminal(recovered)
        if standing is not None:
            return standing
        computed = schedule(graph, tuple(row.value for row in recovered.records))
        if computed.run_state == "open":
            return None
        # Built from `computed`'s own values. Nothing between this line and the
        # append reads the store again, so the facts cannot move under the
        # identity being minted for them.
        terminal = RunTerminal(
            terminal_id=ids("terminal"), run_id=run_id,
            graph_id=graph.graph_id, state=computed.run_state,
            settled_nodes=computed.settled,
            unreachable_nodes=computed.unreachable, recorded_at=clock())
        store.append(terminal)
        return terminal
