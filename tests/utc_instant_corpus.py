"""The one corpus that decides what a UTC instant is, on both sides of the wire.

A December Command instant is validated twice: by the durable contract
(``command/contracts.py`` ``_timestamp``, guarding everything the store will
ever hold) and by the Cockpit's own validator (``panel/command-projection.js``
``instantIsValid``, guarding what a Human is shown as an authorization). Two
validators are two chances to disagree, and a disagreement is not cosmetic: a
value the panel accepts but the store refuses shows an approval that can never
exist, and a value the store accepts but the panel refuses hides one that does.

So the accepted set is data, held here once, and driven through four bindings —
``ActionRequest.requested_at``, ``DecisionReceipt.decided_at``, and the browser's
own relation for each of those two fields. Adding a row obliges all four.

The refusals are grouped by the class each one closes, and the classes are not
arbitrary: every one of them is a spelling that ``datetime.fromisoformat``
accepts on at least one Python the package supports (>=3.11) while the browser
refuses it, or the reverse. The ISO end-of-day ``24:00:00`` is the sharpest:
3.11 and 3.12 refuse it, 3.14 accepts it. A contract that delegated to that
function would hold a different set of valid facts on different interpreters, so
the grammar is frozen here instead and neither side may widen it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

_CORPUS_PATH = Path(__file__).parent / "fixtures" / "utc_instant_parity_corpus.json"
_VERDICTS = {"accept": True, "refuse": False}


class InstantCase(NamedTuple):
    """One corpus row: the name it is reported under, its value, its verdict."""

    name: str
    value: str
    accepted: bool


def _load(path: Path) -> tuple[InstantCase, ...]:
    """Read the corpus, refusing a malformed one rather than testing less.

    Args:
        path: The corpus JSON file.

    Returns:
        Every row, in file order.

    Raises:
        ValueError: The file is not a non-empty list of ``{name, value, verdict}``
            rows, a verdict is not ``accept`` or ``refuse``, a name repeats, or
            either verdict has no rows at all.
    """
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path.name} must be a non-empty JSON list of cases")
    cases: list[InstantCase] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "value", "verdict"}:
            raise ValueError(f"{path.name} row must be {{name, value, verdict}}: {row!r}")
        if not isinstance(row["name"], str) or not isinstance(row["value"], str):
            raise ValueError(f"{path.name} name and value must be strings: {row!r}")
        if row["verdict"] not in _VERDICTS:
            raise ValueError(f"{path.name} verdict must be accept or refuse: {row!r}")
        cases.append(InstantCase(row["name"], row["value"], _VERDICTS[row["verdict"]]))
    names = [case.name for case in cases]
    if len(set(names)) != len(names):
        raise ValueError(f"{path.name} repeats a case name")
    if not any(case.accepted for case in cases) or all(case.accepted for case in cases):
        raise ValueError(f"{path.name} must hold rows of both verdicts")
    return tuple(cases)


CASES = _load(_CORPUS_PATH)
#: pytest parametrisation, shared so all four bindings are driven identically.
IDS = tuple(case.name for case in CASES)
PARAMS = tuple((case.value, case.accepted) for case in CASES)
