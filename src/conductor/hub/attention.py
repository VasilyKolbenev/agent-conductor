"""The raw projection of a run's wait that the hub carries (spec 4.5.6, "Ждут вас").

`human_state = "required"` of a run row means one of five checked reasons (`gate_decision`,
`confirmation`, `input_document`, `reconcile`, `attempt_bound`), not necessarily a gate. For such a
row the hub reads the run once (`GET /command/runs/<run_id>`) and keeps, without a word of its own,
what the desk needs to say how long the wait has lasted:

- `reasons`: the rows of `graph.situation.checked` with a count, except `run_ended`;
- `gates`: `{node_id, gate_id}` of the gates that need a decision (only a `gate_decision` has one);
- `runtime`: `{node_id, opened_by}` of each step of the plan;
- `journal`: the last 256 typed records of the run, each cut to five keys and none of its payload.

The hub does not compute the time. `waitingSince` in the desk's `desk-status.js` does, from this
index; the projection here and `journalIndex` there are held equal by a shared fixture
(`tests/test_hub_attention.py`). A run read that is not the shape this module knows is `unreadable`
and names no reason: a reason is never invented.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

#: The hub keeps the last 256 rows of a journal and so does the desk: a record older than the window
#: is found by neither.
JOURNAL_ROWS = 256
#: Which field of a record says when it happened. A kind absent here states no instant this build
#: knows, and its row carries none. The table is the Studio's own (`studio-runwords.js`) and the
#: desk's (`desk-status.js`); a test holds the three equal, kind by kind.
INSTANT_FIELDS: Mapping[str, str] = MappingProxyType({
    "action_proposal": "proposed_at", "action_request": "requested_at",
    "action_result": "observed_at", "adapter_observation": "observed_at",
    "artifact": "created_at", "attempt_event": "recorded_at",
    "correction_feedback": "recorded_at", "decision": "decided_at", "evidence": "observed_at",
    "graph_definition": "created_at", "run_authorization": "authorized_at",
    "run_authorization_control": "recorded_at", "run_terminal": "recorded_at",
})


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _index_row(row: object) -> dict[str, str | None] | None:
    """One row of the index, or `None` for a row that is not a typed record."""
    if not isinstance(row, Mapping):
        return None
    kind, record = row.get("record_type"), row.get("record")
    if not isinstance(kind, str) or not isinstance(record, Mapping):
        return None
    field = INSTANT_FIELDS.get(kind)
    return {"record_type": kind, "instant": None if field is None else _text(record.get(field)),
            "action_id": _text(record.get("action_id")), "node_id": _text(record.get("node_id")),
            "proposal_id": _text(record.get("proposal_id"))}


def journal_projection(records: object) -> list[dict[str, str | None]]:
    """The last 256 typed rows of a run's journal (the `records` of a run read), five keys each.

    Args:
        records: The `records` list of `GET /command/runs/<run_id>`; anything else gives `[]`.
    """
    if not isinstance(records, (list, tuple)):
        return []
    rows = [found for found in map(_index_row, records) if found is not None]
    return rows[-JOURNAL_ROWS:]


def unreadable(observed_at: str) -> dict[str, Any]:
    """The `attention` of a run whose read failed or was not the shape: no reason is named."""
    return {"reasons": [], "gates": [], "runtime": [], "journal": [],
            "observed_at": observed_at, "unreadable": True}


def _reasons(situation: Mapping[str, Any]) -> list[dict[str, Any]]:
    found = []
    for entry in situation["checked"]:
        if not (isinstance(entry["reason"], str) and type(entry["count"]) is int
                and isinstance(entry["sources"], list)):
            raise ValueError("a checked reason is not the shape")
        if entry["count"] > 0 and entry["reason"] != "run_ended":
            found.append({"reason": entry["reason"], "count": entry["count"],
                          "sources": [str(source) for source in entry["sources"]]})
    return found


def _gates(situation: Mapping[str, Any]) -> list[dict[str, str]]:
    return [{"node_id": str(row["node_id"]), "gate_id": str(row["gate_id"])}
            for row in situation["gates"] if row["needs_decision"] is True]


def _runtime(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = graph.get("runtime")
    if runtime is None:
        return []
    return [{"node_id": str(node["node_id"]), "opened_by": [str(s) for s in node["opened_by"]]}
            for node in runtime["nodes"]]


def attention_of(detail: Any, observed_at: str) -> dict[str, Any]:
    """The `attention` object of one run; `unreadable` when its read is not the shape.

    Args:
        detail: The answer of `GET /command/runs/<run_id>`.
        observed_at: The moment the hub first saw the reason (its ledger's, not this read's).
    """
    try:
        graph = detail["graph"]
        situation = graph["situation"]
        records = detail.get("records")
        return {"reasons": _reasons(situation), "gates": _gates(situation),
                "runtime": _runtime(graph), "journal": journal_projection(records),
                "observed_at": observed_at, "unreadable": False}
    except (KeyError, TypeError, AttributeError, ValueError):
        return unreadable(observed_at)
