"""The durable fact that a run's plan ENDED, and the two words it may end on.

A terminal could have been computed on every read, and it must not be. A
computed verdict is not monotone: a superseding `DecisionReceipt` can flip a
gate from `satisfied` to `failed`, closing one road and opening another, so a
run a person was told had finished would silently reopen behind them. Writing it
down makes *this run ended* a fact of the journal that later records are judged
against -- which is what lets "terminal" be a BEHAVIOUR rather than a reading:
the live doors refuse once this record stands.

It is NOT a stored projection, and the difference is the whole of why it is
allowed to exist beside `graph_projection`. It restates no node phase, no
outcome, no gate state and no pass count -- every one of those stays computed,
where a second copy could not disagree with the first. What it records is that
the verdict was TAKEN, plus the two partitions that were true at that moment, so
that a replay can ask the plan's own bytes whether they still support it.

`state` is deliberately one of two words and never three. "open" is the third
word the schedule computes and it is never durable: a run that has not ended has
nothing to record, and a record saying "not yet" would be a fact that goes stale
the moment after it is written.

This is its own module rather than a tenth record in `contracts`, for the reason
`artifacts` and `attempts` are theirs: that module is at its line cap, and a
durable record whose vocabulary, grammar and rendering are self-contained is
exactly the circuit those two already split out. `schema_version` defaults to 2
because `_schema` refuses anything below it and every durable record in this
package is a v2 document; a new kind entering a v2 journal is a v2 document, and
3 would claim a schema no reader in this build speaks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contract_values import (
    ContractError,
    _enum,
    _id,
    _raw,
    _schema,
    _take,
    _timestamp,
    _unique_ids,
)

#: The two words a run's plan may END on, and the whole of them. `complete`
#: means the plan has nothing left to do and never that the run succeeded --
#: a run that exhausted its retries and a run that was approved both reach it,
#: and only the facts beside it tell a person which. `stalled` means nothing is
#: runnable and something is still owed.
TERMINAL_STATES = frozenset({"complete", "stalled"})


@dataclass(frozen=True)
class RunTerminal:
    """One run's recorded verdict that its plan has nothing left to open.

    `settled_nodes` and `unreachable_nodes` are in the definition's own node
    order, which is the order every other reader of this plan uses, so the two
    arrays can be compared to a recomputed verdict entry for entry rather than
    as sets.
    """

    terminal_id: str
    run_id: str
    graph_id: str
    state: str
    settled_nodes: tuple[str, ...]
    unreachable_nodes: tuple[str, ...]
    recorded_at: str
    schema_version: int = 2

    _FIELDS = frozenset({
        "schema_version", "terminal_id", "run_id", "graph_id", "state",
        "settled_nodes", "unreachable_nodes", "recorded_at",
    })

    def __post_init__(self) -> None:
        for name in ("terminal_id", "run_id", "graph_id"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "state", _enum("state", self.state, TERMINAL_STATES))
        for name in ("settled_nodes", "unreachable_nodes"):
            object.__setattr__(self, name, _unique_ids(name, getattr(self, name)))
        overlap = sorted(set(self.settled_nodes) & set(self.unreachable_nodes))
        if overlap:
            raise ContractError(
                f"node(s) {overlap!r} are recorded as both settled and "
                "unreachable; a step is one or the other and never both")
        object.__setattr__(self, "recorded_at", _timestamp("recorded_at", self.recorded_at))
        object.__setattr__(self, "schema_version", _schema(self.schema_version))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "terminal_id": self.terminal_id,
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "state": self.state,
            "settled_nodes": list(self.settled_nodes),
            "unreachable_nodes": list(self.unreachable_nodes),
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RunTerminal":
        data = _raw(value)
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(
                f"run terminal carries unsupported field(s) {unknown!r}")
        return cls(
            terminal_id=_take(data, "terminal_id"),
            run_id=_take(data, "run_id"),
            graph_id=_take(data, "graph_id"),
            state=_take(data, "state"),
            settled_nodes=_take(data, "settled_nodes"),
            unreachable_nodes=_take(data, "unreachable_nodes"),
            recorded_at=_take(data, "recorded_at"),
            schema_version=data.pop("schema_version", 2),
        )
