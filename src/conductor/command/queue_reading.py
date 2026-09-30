"""How the project queue is read (spec 4.4.6): the slot, and what each entry stands on.

Everything here is a pure function of facts the service gathers: the recovered run, the receipt
file, who holds the slot. That is what lets each rule of 4.4.6 be a row of a table in the tests,
and what keeps the read from writing anything (a read never removes an entry; it hides the ones
that are done and the pump removes them).

The run's journal is the only source of the fact that a grant or a control was accepted. A
receipt and an entry only say what was about to happen and on whose word, so the reading that
matters is the PAIRING of a receipt with the journal: digest, person and both times must agree,
or the entry is blocked and nothing is written or started on it.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .authorization_history import journal_prefix_digest
from .authorization_terms import _time_parts
from .contract_values import ContractError, _content_digest
from .graph_schedule import schedule
from .policy_history import current_authorization, current_control
from .queue_store import JOURNAL_KIND, QueueEntry, Receipt
from .run_authorization import RunAuthorization
from .run_terminal import RunTerminal
from .store_errors import StoreError

SLOT_STATES = ("free", "busy", "stuck", "unavailable")
SCHEMA_VERSION = 1


class _Corrupt:
    """A receipt file that could not be read: it says nothing, and never agrees with anything."""

    def __repr__(self) -> str:
        return "CORRUPT"


CORRUPT = _Corrupt()
#: The states of a holder that keep the slot busy, under the reason `automation_view` gave.
_BUSY = frozenset({"running", "ready", "waiting", "paused", "revoked", "complete"})
#: The states where the holder is stuck until a human pauses or revokes it.
_STUCK = frozenset({"stalled", "expired"})


def _slot(state: str, run_id: str | None, reason: str | None) -> dict[str, Any]:
    return {"state": state, "run_id": run_id, "reason_code": reason}


def slot_reading(driver: Any, mode: str,
                 holder_view: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """The slot of this process: free, busy, stuck or unavailable, with names that exist.

    The table is the one of spec 4.4.6, checked from the top and the first row that fits decides:
    no driver (a view process, or an active one with no owner), a drain, nothing held, and then
    the holder's own `(state, reason)` from the automation read. A holder that cannot be read is
    stuck and not free: its action may still be running.

    Args:
        driver: The policy driver, or None when this process has none.
        mode: `view` or `active`.
        holder_view: Reads the automation of one run (`policy_view.automation_view`).
    """
    if driver is None:
        return _slot("unavailable", None,
                     "project_not_active" if mode == "view" else "owner_required")
    snapshot = driver.slot()
    holder = snapshot.active_run_id or snapshot.inflight_run_id
    if snapshot.holding_new_work:
        return _slot("unavailable", holder, "server_stopping")
    if holder is None:
        return _slot("free", None, None)
    try:
        view = holder_view(holder)
    except (StoreError, ContractError):
        return _slot("stuck", holder, "run_unreadable")
    state, reason = view["state"], view["reason_code"]
    if state in _BUSY:
        return _slot("busy", holder, reason)
    if state == "restart_required":
        return _slot("unavailable", holder, "owner_required")
    return _slot("stuck", holder, reason)


# --- the journal, the receipt, and whether they agree ---------------------------------------------


def journal_value(recovered: Any, journal_kind: str, record_id: str) -> Any | None:
    """The record of this kind and id the run's journal holds, or None."""
    field = "authorization_id" if journal_kind == JOURNAL_KIND["start"] else "control_id"
    return next((row.value for row in recovered.records
                 if row.kind == journal_kind and getattr(row.value, field) == record_id), None)


def record_digest(value: Any) -> str:
    """The digest of a journal record the pump writes: a grant's own, a control's whole record."""
    if type(value) is RunAuthorization:
        return value.authorization_digest
    return _content_digest(value.as_dict())


def record_time(value: Any) -> str:
    return value.authorized_at if type(value) is RunAuthorization else value.recorded_at


def record_human(value: Any) -> str:
    return value.authorized_by if type(value) is RunAuthorization else value.actor


def receipt_agrees(receipt: Receipt, value: Any, *, digest: str, human: str,
                   preauthorized_at: str) -> bool:
    """Whether a receipt and a journal record say one thing: digest, person and both times.

    `digest`, `human` and `preauthorized_at` are what the human's permission says (an entry, or
    a flag); the journal record says the rest. `record_digest` covers the person and the time of
    the record, and the two are compared once more outright so a receipt cannot vouch for a
    record another hand wrote.
    """
    return (receipt.record_digest == record_digest(value) and receipt.digest == digest
            and receipt.authorized_by == human and receipt.preauthorized_at == preauthorized_at
            and receipt.started_at == record_time(value)
            and record_human(value) == receipt.authorized_by)


def pairing(preauth: Any, journal_kind: str, receipt: Any, value: Any) -> str:
    """How a receipt and a journal record stand to one entry's key.

    `none`: neither exists. `orphan`: a receipt and no record, so no permission was used and a
    retry replaces it. `elsewhere`: a record and no receipt, so another road wrote it. `paired`:
    both, and they agree. `conflict`: both, and they do not (or the receipt cannot be read).
    """
    if value is None:
        return "none" if receipt is None else "orphan"
    if receipt is None:
        return "elsewhere"
    if receipt is CORRUPT or (receipt.kind, receipt.record_id) != (
            journal_kind, preauth.record_id):
        return "conflict"
    agreed = receipt_agrees(receipt, value, digest=preauth.digest, human=preauth.human,
                            preauthorized_at=preauth.preauthorized_at)
    return "paired" if agreed else "conflict"


# --- what the run says about an entry -------------------------------------------------------------


def run_ended(recovered: Any) -> bool:
    """A terminal is recorded, or the plan has nothing left to open."""
    values = tuple(row.value for row in recovered.records)
    if any(type(value) is RunTerminal for value in values):
        return True
    definition = next((row.value for row in recovered.records if row.kind == "graph_definition"),
                      None)
    return definition is not None and schedule(definition, values).run_state == "complete"


def grant_standing(recovered: Any, now: str) -> bool:
    """A grant exists and is neither revoked nor past its time (a pause does not end it)."""
    values = tuple(row.value for row in recovered.records)
    grant = current_authorization(values)
    if grant is None:
        return False
    control = current_control(values, grant)
    if control is not None and control.action == "revoke":
        return False
    return _time_parts("now", now) < _time_parts("expires_at", grant.expires_at)


def terms_changed(entry: QueueEntry, recovered: Any) -> bool:
    """The run's journal is no longer the prefix the human reviewed (a start entry only)."""
    pre = entry.preauthorization
    return (entry.kind == "start" and pre is not None
            and journal_prefix_digest(recovered.records) != pre.source_prefix_digest)


def processed_reason(entry: QueueEntry, recovered: Any, now: str, *, pairing: str,
                     holds: bool) -> str | None:
    """Why an entry is done and only waits to be removed (spec 4.4.4 step 2), or None.

    An ended run first. A receipt that disagrees with the journal is never "done": the entry
    stays, blocked, for a human to take out.
    """
    if run_ended(recovered):
        return "ended"
    if pairing == "conflict":
        return None
    if pairing == "paired":
        return "started" if entry.kind == "start" else "resumed"
    if pairing == "elsewhere":
        return "started_elsewhere" if entry.kind == "start" else "resumed"
    if entry.kind == "start":
        return "started_elsewhere" if grant_standing(recovered, now) else None
    values = tuple(row.value for row in recovered.records)
    grant = current_authorization(values)
    if grant is None:
        return None
    control = current_control(values, grant)
    if control is not None and entry.preauthorization is not None and (
            control.control_id == entry.preauthorization.control_id):
        return "resumed"
    if control is not None and control.action == "revoke":
        return "revoked"
    return "held" if holds else None


# --- the read -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Facts:
    """What the service gathered about one entry: the run, the receipt, the driver, the task."""

    entry: QueueEntry
    recovered: Any | None       # the recovered run, or None when it cannot be read
    receipt: Receipt | _Corrupt | None
    admitted: bool              # this process admitted its preauthorization (spec 4.4.2)
    holds: bool                 # the driver holds this run now
    task_id: str | None
    title: str | None


def pairing_of(item: Facts) -> str:
    """How the receipt and the journal stand to this entry's key (see `pairing`)."""
    pre, entry = item.entry.preauthorization, item.entry
    if pre is None or item.recovered is None:
        return "none"
    value = journal_value(item.recovered, JOURNAL_KIND[entry.kind], pre.record_id)
    return pairing(pre, JOURNAL_KIND[entry.kind], item.receipt, value)


def done_reason(item: Facts, now: str) -> str | None:
    """Why this entry is done and only waits to be removed, or None (none for an unreadable run)."""
    if item.recovered is None:
        return None
    return processed_reason(item.entry, item.recovered, now, pairing=pairing_of(item),
                            holds=item.holds)


def _state(item: Facts, kind: str, *, slot: dict[str, Any], mode: str, ahead: bool,
           process_started: str) -> tuple[str, str | None, str | None]:
    """`(state, reason_code, state_since)` of a visible entry, the rules in the order of 4.4.6."""
    pre, dropped = item.entry.preauthorization, item.entry.dropped
    if item.recovered is None:
        return "blocked", "run_unreadable", None
    if kind == "conflict":
        return "blocked", "receipt_conflict", None
    if pre is None:
        return "confirmation_required", dropped.reason_code, dropped.at
    if terms_changed(item.entry, item.recovered):
        return "confirmation_required", "terms_changed", None
    if mode == "view":
        return "preauthorized", "project_not_active", pre.preauthorized_at
    if not item.admitted:
        return "confirmation_required", "server_restarted", process_started
    return "preauthorized", _waiting_reason(slot, ahead), pre.preauthorized_at


def _waiting_reason(slot: dict[str, Any], ahead: bool) -> str | None:
    if ahead:
        return "behind"
    if slot["state"] in ("busy", "stuck"):
        return "slot_busy"
    return "slot_unavailable" if slot["state"] == "unavailable" else None


def _row(item: Facts, position: int, judged: tuple[str, str | None, str | None]) -> dict[str, Any]:
    entry, pre = item.entry, item.entry.preauthorization
    state, reason, since = judged
    return {"run_id": entry.run_id, "task_id": item.task_id, "title": item.title,
            "position": position, "kind": entry.kind, "enqueued_at": entry.enqueued_at,
            "enqueued_by": entry.enqueued_by, "state": state, "reason_code": reason,
            "state_since": since,
            "preauthorization": None if pre is None else {
                "authorized_by": pre.human, "preauthorized_at": pre.preauthorized_at,
                "digest": pre.digest}}


def assemble(revision: int, facts: Sequence[Facts], *, slot: dict[str, Any], mode: str,
             now: str, process_started: str) -> dict[str, Any]:
    """The answer of `GET /command/queue` (spec 4.4.6) for these entries, in the file's order.

    A processed entry is not shown and does not count in `position`. An entry whose run says it
    was started already, or ended, is processed whatever it holds; the pump removes it later.
    """
    rows: list[dict[str, Any]] = []
    ahead = False
    for item in facts:
        kind = pairing_of(item)
        if item.recovered is not None and processed_reason(
                item.entry, item.recovered, now, pairing=kind, holds=item.holds):
            continue
        judged = _state(item, kind, slot=slot, mode=mode, ahead=ahead,
                        process_started=process_started)
        rows.append(_row(item, len(rows) + 1, judged))
        ahead = ahead or judged[0] == "preauthorized"
    return {"schema_version": SCHEMA_VERSION, "revision": revision, "slot": slot, "entries": rows}
