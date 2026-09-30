"""The summary of the children: rows, limit cards, and what "free" means (spec 4.1.9, 4.5.6, 4.6.4).

The hub gives the page raw fields and no words (4.1.9: "Hub отдаёт сырые поля и своей арифметики
не имеет"). A row of `GET /hub/projects` is made here from what the supervisor says of a child
(its lifecycle, working state, port, instance), from the last pass over it (`Live`) or, when there
is none, from its last snapshot, each read kept as the child answered it. For a run that needs a
person the row also holds the raw projection of its wait (`attention`, see `attention.py`) and the
moment the hub first saw each reason (`ObservedLedger`). The page turns those into the items of
"Ждут вас" with the shared `desk-status.js`; there is no second implementation of that table here.

`is_free` is the one rule of 4.1.9 by which the queue of projects may move on. The limit cards are
one per verified account (vendor and digest, the freshest row) and one per unverified row.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conductor.hub import attention, child_client, registry, snapshots, supervisor

#: The states of the automation of a run in which its grant is still standing (4.1.9).
HOLDING = frozenset({"running", "waiting", "ready", "stalled", "restart_required"})
#: The verdicts that stop a pass: the child is another project, or another hub's or mode.
STOPPING_VERDICTS = ("identity_mismatch", "busy_elsewhere")
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class Live:
    """The last pass over one child, ready to be shown: the cycle and the rows made from it."""

    cycle: child_client.Cycle
    taken_at: str
    rows: tuple[dict[str, Any], ...]


class ObservedLedger:
    """When the hub first saw each reason a person is waited for, per project and run.

    A reason is remembered while it stands and forgotten the pass it does not; it is seeded
    from the last snapshot's rows when the hub starts, so a restart does not make a wait young.
    Keys carry the project, so two projects with a task of the same id never share a moment.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str, str], str] = {}

    def seed(self, project_id: str, rows: Iterable[dict[str, Any]]) -> None:
        """Remember the moments a snapshot's rows recorded (the earliest stands for each reason)."""
        for row in rows:
            seen, run = row.get("attention"), row.get("run")
            if not isinstance(seen, dict) or not isinstance(run, dict):
                continue
            names = [entry["reason"] for entry in seen.get("reasons", [])] or ["none"]
            for name in names:
                self._seen.setdefault((project_id, str(run.get("run_id")), name),
                                      seen.get("observed_at", ""))

    def observe(self, project_id: str, run_id: str, reasons: Iterable[str], now: str) -> str:
        """The earliest first-seen moment of the reasons standing now; a new one starts at `now`."""
        moments = [self._seen.setdefault((project_id, run_id, reason), now)
                   for reason in reasons]
        return min(moments)

    def sweep(self, project_id: str, keep: set[tuple[str, str]]) -> None:
        """Forget every reason of this project that did not stand in the pass just read."""
        stale = [key for key in self._seen
                 if key[0] == project_id and (key[1], key[2]) not in keep]
        for key in stale:
            del self._seen[key]


def _attention(project_id: str, read: child_client.TaskRead, ledger: ObservedLedger, now: str,
               keep: set[tuple[str, str]]) -> dict[str, Any] | None:
    run = read.run
    if run is None or run.get("human_state") != "required":
        return None
    run_id = str(run.get("run_id"))
    built = attention.attention_of(read.detail, now)
    names = [entry["reason"] for entry in built["reasons"]]
    if built["unreadable"] or not names:
        names = ["unreadable" if built["unreadable"] else "none"]
    keep.update((run_id, name) for name in names)
    return {**built, "observed_at": ledger.observe(project_id, run_id, names, now)}


def live_from_cycle(project_id: str, cycle: child_client.Cycle, ledger: ObservedLedger,
                    taken_at: str) -> Live:
    """Make the rows of a pass; the ledger of this project is swept to what stands in it."""
    keep: set[tuple[str, str]] = set()
    rows = tuple({"task": read.task, "run": read.run, "automation": read.automation,
                  "attention": _attention(project_id, read, ledger, taken_at, keep)}
                 for read in cycle.tasks)
    ledger.sweep(project_id, keep)
    return Live(cycle, taken_at, rows)


# -- free ---------------------------------------------------------------------------------------


def _run_holds(read: child_client.TaskRead) -> bool:
    run, automation = read.run, read.automation
    if run is None:
        return False
    if run.get("unreadable") or run.get("human_state") == "required":
        return True
    return isinstance(automation, dict) and automation.get("state") in HOLDING


def _queue_is_free(queue: object) -> bool:
    if queue is None:
        return True                       # a child with no queue route has no queue (4.5.6)
    if not isinstance(queue, dict):
        return False
    slot, entries = queue.get("slot"), queue.get("entries")
    return (isinstance(slot, dict) and slot.get("state") == "free"
            and isinstance(entries, list) and not entries)


def is_free(cycle: child_client.Cycle) -> bool:
    """Whether a project is free for the queue of projects to move on (4.1.9, 4.3.4).

    Free means: every read of the pass was answered (one failed read is not free), no newest run has
    a grant that still stands (`running`, `waiting`, `ready`, `stalled`, `restart_required`), none
    needs a person, a run that could not be read holds the project, and the task queue has a free
    slot and no entries.
    """
    if not cycle.complete:
        return False
    return not any(_run_holds(read) for read in cycle.tasks) and _queue_is_free(cycle.queue)


# -- the limits ---------------------------------------------------------------------------------


def _freshness(row: dict[str, Any]) -> str:
    moment = row.get("observed_at")
    return moment if isinstance(moment, str) else ""


def limit_cards(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One card per verified account, one per unverified row (4.1.9, L27).

    A verified account is told by its vendor and account digest, and its card keeps the freshest row
    of the bindings that share it. An unverified row is never merged with anything.
    """
    cards: list[dict[str, Any]] = []
    where: dict[tuple[str, str], int] = {}
    for row in rows:
        account = row.get("account")
        if not isinstance(account, dict):
            cards.append({"key": {"binding_ids": list(row.get("binding_ids", []))},
                          "verified": False, "row": row})
            continue
        key = (str(account.get("vendor")), str(account.get("account_digest")))
        card = {"key": {"vendor": key[0], "account_digest": f"sha256:{key[1]}"},
                "verified": True, "row": row}
        if key not in where:
            where[key] = len(cards)
            cards.append(card)
        elif _freshness(row) >= _freshness(cards[where[key]]["row"]):
            cards[where[key]] = card
    return cards


def limits_response(computed_at: str, *, active_project_id: str | None, live: Live | None,
                    stored: snapshots.LimitsSnapshot | None) -> dict[str, Any]:
    """`GET /hub/limits`: the active project's live read, else `limits.json`, else nothing.

    A live read counts only when it is of a child that runs as the active one (`active_quotas`).
    """
    quotas = None if live is None else live.cycle.active_quotas
    if active_project_id is not None and live is not None and quotas is not None:
        return _limits(computed_at, "live", active_project_id, live.taken_at, quotas)
    if stored is not None:
        return _limits(computed_at, "snapshot", stored.project_id, stored.taken_at, stored.quotas)
    return {"computed_at": computed_at, "project_id": None, "source": "none", "taken_at": None,
            "as_of": None, "max_age_seconds": None, "accounts": []}


def _limits(computed_at: str, source: str, project_id: str, taken_at: str,
            quotas: dict[str, Any]) -> dict[str, Any]:
    rows = quotas.get("snapshots")
    return {"computed_at": computed_at, "project_id": project_id, "source": source,
            "taken_at": taken_at, "as_of": quotas.get("as_of"),
            "max_age_seconds": quotas.get("max_age_seconds"),
            "accounts": limit_cards(rows if isinstance(rows, list) else [])}


# -- the row ------------------------------------------------------------------------------------


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(timezone.utc).strftime(_INSTANT)


def _resume_run(rows: Iterable[dict[str, Any]]) -> str | None:
    """The newest run whose automation says `restart_required`: what "Продолжить" opens."""
    found = [row["run"] for row in rows
             if isinstance(row.get("automation"), dict) and isinstance(row.get("run"), dict)
             and row["automation"].get("state") == "restart_required"]
    if not found:
        return None
    newest = max(found, key=lambda run: (str(run.get("created_at")), str(run.get("run_id"))))
    return newest.get("run_id")


def _data(live: Live | None, snapshot: snapshots.Snapshot | None) -> tuple[str, list, Any, Any]:
    """`(data, rows, task_queue, auto_continue)`: live, else the snapshot, else nothing."""
    if live is not None and live.cycle.verdict in STOPPING_VERDICTS:
        return "none", [], None, None
    if live is not None and live.cycle.verdict == "live":
        return "live", list(live.rows), live.cycle.queue, live.cycle.auto_continue
    if snapshot is not None:
        return "snapshot", list(snapshot.tasks), snapshot.task_queue, snapshot.auto_continue
    return "none", [], None, None


def project_row(project: registry.Project, status: supervisor.ProjectStatus, *,
                queue: tuple[str, ...], live: Live | None,
                snapshot: snapshots.Snapshot | None) -> dict[str, Any]:
    """One project of `GET /hub/projects` (4.6.4): the raw fields the page turns into words."""
    data, rows, task_queue, flag = _data(live, snapshot)
    state = status.lifecycle.state
    if live is not None and live.cycle.verdict in STOPPING_VERDICTS and state == "running":
        state = live.cycle.verdict
    running = state == "running" and status.port is not None
    return {
        "project_id": project.project_id, "name": project.name,
        "folder": Path(project.root.replace("\\", "/")).name, "source": project.source,
        "repo": project.repo, "state": state, "working": status.working, "mode": status.mode,
        "queue_position": queue.index(project.project_id) + 1 if project.project_id in queue
        else None,
        "stopped_at": _iso(status.stopped_at), "resume_run_id": _resume_run(rows),
        "auto_continue": flag, "state_code": status.lifecycle.state_code,
        "drain_deadline": _iso(status.drain_deadline), "instance": status.instance,
        "desk_url": f"http://127.0.0.1:{status.port}/panel/desk.html" if running else None,
        "data": data, "snapshot_at": snapshot.taken_at if data == "snapshot" and snapshot else None,
        "tasks": rows, "task_queue": task_queue}
