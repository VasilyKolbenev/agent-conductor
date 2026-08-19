"""The one corpus that decides where a loop may send work back to.

A loop's ``back_to`` is validated twice: by the durable contract
(``graph_definition.GraphDefinition._settle_loops``, guarding what the store
will hold) and by the Cockpit's own payload check (``panel/graph-store.js``,
guarding what a Human is shown). Two validators are two chances to disagree,
and a disagreement here is not cosmetic: a graph the backend accepts and the
panel calls corrupt is a plan a Human composed, saw persisted, and then found
unreadable.

That is exactly what happened. The backend accepted a loop whose ``back_to``
was its own ``node_id`` while ``graph-store.js`` had refused that all along --
a loop that reopens itself reopens nothing. So the accepted set is data, held
here once, and driven from both sides.

The graph these rows are read against carries ``alpha``, ``beta``, ``gate``,
``apply``, ``loop-node`` and ``loop-other``; ``loop-node`` is the loop under
test. Adding a row obliges both bindings.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

_CORPUS_PATH = Path(__file__).parent / "fixtures" / "graph_loop_parity_corpus.json"
_VERDICTS = {"accept": True, "refuse": False}

#: The nodes the corpus is read against; `LOOP_NODE` is the loop under test.
CARRIED = ("alpha", "beta", "gate", "apply", "loop-other")
LOOP_NODE = "loop-node"


class LoopCase(NamedTuple):
    """One corpus row: the name it is reported under, its target, its verdict."""

    name: str
    back_to: str
    accepted: bool


def _load(path: Path) -> tuple[LoopCase, ...]:
    """Read the corpus, refusing a malformed one rather than testing less.

    Args:
        path: The corpus JSON file.

    Returns:
        Every row, in file order.

    Raises:
        ValueError: The file is not a non-empty list of ``{name, back_to,
            verdict}`` rows, a verdict is not ``accept`` or ``refuse``, a name
            repeats, or either verdict has no rows at all.
    """
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path.name} must be a non-empty JSON list of cases")
    cases: list[LoopCase] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "back_to", "verdict"}:
            raise ValueError(
                f"{path.name} row must be {{name, back_to, verdict}}: {row!r}")
        if not isinstance(row["name"], str) or not isinstance(row["back_to"], str):
            raise ValueError(f"{path.name} name and back_to must be strings: {row!r}")
        if row["verdict"] not in _VERDICTS:
            raise ValueError(f"{path.name} verdict must be accept or refuse: {row!r}")
        cases.append(LoopCase(row["name"], row["back_to"], _VERDICTS[row["verdict"]]))
    names = [case.name for case in cases]
    if len(set(names)) != len(names):
        raise ValueError(f"{path.name} repeats a case name")
    if not any(case.accepted for case in cases) or all(case.accepted for case in cases):
        raise ValueError(f"{path.name} must hold rows of both verdicts")
    return tuple(cases)


CASES = _load(_CORPUS_PATH)
#: pytest parametrisation, shared so both bindings are driven identically.
IDS = tuple(case.name for case in CASES)
PARAMS = tuple((case.back_to, case.accepted) for case in CASES)
