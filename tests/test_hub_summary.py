"""The summary of the children (spec 4.1.9, 4.5.6, 4.6.4): rows, limit cards, and "free".

The hub gives the page raw fields and no words of its own: a row of `GET /hub/projects` holds the
reads as they were, the reasons a person is waited for (five, `reconcile` among them, a `gate_id`
only where there is a gate), and the moment the hub first saw each. Whether a project is FREE for
the queue to move on is the one pure function `is_free`. The cards of the limits are one per
verified account and one per unverified row. Two projects that hold a task of the same id keep
separate rows, attention and snapshots.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from conductor.hub import child_client, lifecycle, registry, snapshots, summary, supervisor
from tests._hub_fake_child import run_detail, run_row, task_row

A, B = "a" * 32, "b" * 32
NOW = "2026-09-30T10:00:00Z"
LATER = "2026-09-30T10:05:00Z"
ROW_KEYS = {"project_id", "name", "folder", "source", "repo", "state", "working", "mode",
            "queue_position", "stopped_at", "resume_run_id", "auto_continue", "state_code",
            "drain_deadline", "instance", "desk_url", "data", "snapshot_at", "tasks", "task_queue"}


def _read(task_id: str, title: str, *, state: str | None = "waiting", reason: str = "plan_waiting",
          human: str = "not_required", detail: dict | None = None, failed: bool = False,
          run_id: str | None = None, created: str = "2026-09-30T09:00:00Z"
          ) -> child_client.TaskRead:
    run_id = run_id or f"run-{task_id}"
    return child_client.TaskRead(
        task_row(task_id, title), run_row(run_id, task_id, human_state=human, created_at=created),
        None if state is None else {"state": state, "reason_code": reason,
                                    "expires_at": "2026-09-30T12:00:00Z"}, detail, failed)


def _cycle(*reads, queue=None, flag=None, quotas=None, failures=(), verdict="live",
           mode="active"):
    project = {"project_id": A, "hub_origin": "http://127.0.0.1:7700", "demo": False, "mode": mode}
    return child_client.Cycle(verdict, project, tuple(reads), queue, flag, quotas,
                              tuple(failures))


def _project(project_id: str = A, name: str = "web-app", root: str = "C:\\work\\web-app"
             ) -> registry.Project:
    return registry.Project(project_id, name, root, (1, 1), 7701, "folder", None, NOW)


def _status(state: str = "running", working: str = "active", mode: str | None = "active", *,
            code: str | None = None, port: int | None = 7701, instance: str | None = "i" * 32,
            stopped_at: datetime | None = None, drain: datetime | None = None
            ) -> supervisor.ProjectStatus:
    return supervisor.ProjectStatus(lifecycle.Lifecycle(state, code), working, mode, drain,
                                    port, instance, stopped_at)


def _live(read: child_client.TaskRead | None, *, ledger=None, taken: str = NOW,
          project_id: str = A, **cycle) -> summary.Live:
    reads = () if read is None else (read,)
    return summary.live_from_cycle(project_id, _cycle(*reads, **cycle),
                                   ledger or summary.ObservedLedger(), taken)


def _row(status=None, live=None, snap=None, queue=(), project=None) -> dict:
    return summary.project_row(project or _project(), status or _status(), queue=tuple(queue),
                               live=live, snapshot=snap)


def _detail(reasons: dict[str, list[str]], gates=None) -> dict:
    return run_detail("run-task-1", reasons, gates)


# -- the row ------------------------------------------------------------------------------------


def test_a_row_has_exactly_the_keys_of_the_contract_and_no_absolute_path():
    row = _row(live=_live(_read("task-1", "Fix")))
    assert set(row) == ROW_KEYS
    assert row["folder"] == "web-app" and row["name"] == "web-app"
    assert "C:" not in json.dumps(row) and "work" not in row["folder"]
    assert row["desk_url"] == "http://127.0.0.1:7701/panel/desk.html"
    assert (row["state"], row["working"], row["mode"], row["data"], row["snapshot_at"]) == (
        "running", "active", "active", "live", None)
    assert row["instance"] == "i" * 32 and row["queue_position"] is None


def test_a_live_row_carries_the_reads_as_they_were_and_adds_no_word():
    read = _read("task-1", "Fix", state="running", reason="action_in_flight")
    row = _row(live=_live(read, queue={"revision": 2, "entries": []}, flag={"enabled": False}))
    (task,) = row["tasks"]
    assert set(task) == {"task", "run", "automation", "attention"}
    assert task["task"] == read.task and task["run"] == read.run
    assert task["automation"] == {"state": "running", "reason_code": "action_in_flight",
                                  "expires_at": "2026-09-30T12:00:00Z"}
    assert task["attention"] is None
    assert row["task_queue"] == {"revision": 2, "entries": []}
    assert row["auto_continue"] == {"enabled": False}


def test_the_five_reasons_are_told_apart_reconcile_included_and_a_line_may_have_no_gate_id():
    reasons = {"gate_decision": ["review"], "confirmation": ["p1"], "input_document": ["doc"],
               "reconcile": ["n1"], "attempt_bound": ["do"]}
    gate = {"node_id": "review", "gate_id": "gate-review", "needs_decision": True}
    read = _read("task-1", "Fix", human="required", detail=_detail(reasons, [gate]))
    (task,) = _row(live=_live(read))["tasks"]
    seen = task["attention"]
    assert [entry["reason"] for entry in seen["reasons"]] == list(reasons)
    assert seen["gates"] == [{"node_id": "review", "gate_id": "gate-review"}]
    lone = _read("task-1", "Fix", human="required",
                 detail=_detail({"input_document": ["doc"]}))
    (task,) = _row(live=_live(lone))["tasks"]
    assert task["attention"]["gates"] == []
    assert task["attention"]["reasons"][0]["sources"] == ["doc"]


def test_a_required_row_whose_run_could_not_be_read_says_unreadable_and_names_no_reason():
    read = _read("task-1", "Fix", human="required", detail=None, failed=True)
    (task,) = _row(live=_live(read))["tasks"]
    assert task["attention"]["unreadable"] is True and task["attention"]["reasons"] == []
    assert task["attention"]["observed_at"] == NOW


def test_a_row_that_needs_no_one_has_no_attention_and_a_checkpoint_of_a_view_child_is_raw():
    read = _read("task-1", "Fix", state="restart_required", reason="project_not_active")
    row = _row(_status(working="view", mode="view"), live=_live(read))
    (task,) = row["tasks"]
    assert task["attention"] is None
    assert task["automation"]["state"] == "restart_required"
    assert task["automation"]["reason_code"] == "project_not_active"
    assert row["working"] == "view" and set(row) == ROW_KEYS, "no item was made of it"


def test_the_wait_of_a_run_is_the_raw_index_and_the_queue_entries_keep_their_own_time():
    record = {"record_type": "action_proposal", "record": {
        "proposal_id": "p1", "node_id": "do", "proposed_at": "2026-09-30T09:05:00Z"}}
    detail = run_detail("run-task-1", {"confirmation": ["p1"]}, records=[record],
                        nodes=[{"node_id": "do", "opened_by": ["intake"]}])
    queue = {"slot": {"state": "free"}, "entries": [
        {"run_id": "run-x", "state": "confirmation_required", "state_since": None}]}
    read = _read("task-1", "Fix", human="required", detail=detail)
    row = _row(live=_live(read, queue=queue))
    seen = row["tasks"][0]["attention"]
    assert seen["journal"] == [{"record_type": "action_proposal", "instant": "2026-09-30T09:05:00Z",
                                "action_id": None, "node_id": "do", "proposal_id": "p1"}]
    assert seen["runtime"] == [{"node_id": "do", "opened_by": ["intake"]}]
    assert row["task_queue"]["entries"][0]["state_since"] is None


def test_the_newest_run_with_a_standing_checkpoint_is_what_continue_opens():
    older = _read("task-1", "A", state="restart_required", reason="explicit_resume_required",
                  created="2026-09-30T08:00:00Z")
    newer = _read("task-2", "B", state="restart_required", reason="explicit_resume_required",
                  created="2026-09-30T09:00:00Z")
    quiet = _read("task-3", "C", state="waiting", created="2026-09-30T09:30:00Z")
    row = _row(_status("stopped", "stopped", None, port=None, instance=None),
               snap=_snap([older, newer, quiet]))
    assert row["resume_run_id"] == "run-task-2" and row["data"] == "snapshot"
    assert _row(live=_live(quiet))["resume_run_id"] is None


# -- where the data comes from -------------------------------------------------------------------


def _snap(reads, taken: str = NOW, flag=None, queue=None) -> snapshots.Snapshot:
    rows = summary.live_from_cycle(A, _cycle(*reads), summary.ObservedLedger(), taken).rows
    return snapshots.Snapshot(A, taken, list(rows), queue, flag, None)


def test_a_stopped_project_shows_its_snapshot_with_the_one_mark_and_its_stop_time():
    snap = _snap([_read("task-1", "Fix")], "2026-09-30T08:40:00Z", flag={"enabled": True},
                 queue={"entries": []})
    stopped = datetime(2026, 9, 30, 8, 40, tzinfo=timezone.utc)
    row = _row(_status("stopped", "stopped", None, port=None, instance=None, stopped_at=stopped),
               snap=snap)
    assert (row["data"], row["snapshot_at"]) == ("snapshot", "2026-09-30T08:40:00Z")
    assert row["stopped_at"] == "2026-09-30T08:40:00Z" and row["desk_url"] is None
    assert row["instance"] is None and row["auto_continue"] == {"enabled": True}
    assert row["task_queue"] == {"entries": []} and len(row["tasks"]) == 1


def test_a_project_never_read_has_no_data_and_no_rows():
    row = _row(_status("stopped", "stopped", None, port=None, instance=None))
    assert (row["data"], row["snapshot_at"], row["tasks"], row["task_queue"]) == (
        "none", None, [], None)


def test_a_live_read_wins_over_a_snapshot_and_an_unreadable_one_falls_back_to_it():
    snap = _snap([_read("task-9", "Old")])
    live = _live(_read("task-1", "Fix"))
    assert _row(live=live, snap=snap)["tasks"][0]["task"]["task_id"] == "task-1"
    failed = summary.live_from_cycle(A, child_client.Cycle("unreadable", failures=("tasks",)),
                                     summary.ObservedLedger(), LATER)
    back = _row(live=failed, snap=snap)
    assert back["data"] == "snapshot" and back["tasks"][0]["task"]["task_id"] == "task-9"
    assert _row(live=failed)["data"] == "none"


def test_a_cycle_with_a_failed_side_read_is_still_live_data_but_a_failed_list_is_not():
    partial = _live(_read("task-1", "Fix", state=None), failures=("automation", "quotas"))
    row = _row(live=partial)
    assert row["data"] == "live" and row["tasks"][0]["automation"] is None


def test_a_child_that_is_another_project_or_another_hubs_says_so_and_shows_no_data():
    snap = _snap([_read("task-1", "Fix")])
    for verdict in ("identity_mismatch", "busy_elsewhere"):
        live = summary.live_from_cycle(A, child_client.Cycle(verdict),
                                       summary.ObservedLedger(), NOW)
        row = _row(live=live, snap=snap)
        assert row["state"] == verdict and row["tasks"] == [] and row["data"] == "none"
        assert row["desk_url"] is None and row["snapshot_at"] is None


def test_the_state_code_and_the_drain_deadline_and_the_queue_place_come_from_the_supervisor():
    deadline = datetime(2026, 9, 30, 16, 40, tzinfo=timezone.utc)
    row = _row(_status("stopping", "active", "active", code="status_unreadable", drain=deadline),
               queue=(B, A))
    assert (row["state"], row["state_code"], row["drain_deadline"], row["queue_position"]) == (
        "stopping", "status_unreadable", "2026-09-30T16:40:00Z", 2)
    assert row["desk_url"] is None, "the desk is only offered while the child runs"


# -- the ledger: when the hub first saw a reason ------------------------------------------------


def _waiting(reasons: dict[str, list[str]], **kw) -> child_client.TaskRead:
    return _read("task-1", "Fix", human="required", detail=_detail(reasons), **kw)


def test_the_moment_a_reason_was_first_seen_stays_while_it_stands_and_restarts_when_it_returns():
    ledger = summary.ObservedLedger()
    first = _live(_waiting({"confirmation": ["p1"]}), ledger=ledger, taken=NOW)
    assert first.rows[0]["attention"]["observed_at"] == NOW
    again = _live(_waiting({"confirmation": ["p1"]}), ledger=ledger, taken=LATER)
    assert again.rows[0]["attention"]["observed_at"] == NOW
    both = _live(_waiting({"confirmation": ["p1"], "input_document": ["doc"]}), ledger=ledger,
                 taken="2026-09-30T10:10:00Z")
    assert both.rows[0]["attention"]["observed_at"] == NOW, "the earliest of the reasons that stand"
    gone = _live(_read("task-1", "Fix"), ledger=ledger, taken="2026-09-30T10:20:00Z")
    assert gone.rows[0]["attention"] is None
    back = _live(_waiting({"confirmation": ["p1"]}), ledger=ledger, taken="2026-09-30T10:30:00Z")
    assert back.rows[0]["attention"]["observed_at"] == "2026-09-30T10:30:00Z"


def test_a_restarted_hub_keeps_the_moments_its_last_snapshot_recorded():
    before = summary.ObservedLedger()
    snap_rows = _live(_waiting({"confirmation": ["p1"]}), ledger=before, taken=NOW).rows
    after = summary.ObservedLedger()
    after.seed(A, snap_rows)
    fresh = _live(_waiting({"confirmation": ["p1"]}), ledger=after, taken=LATER)
    assert fresh.rows[0]["attention"]["observed_at"] == NOW


def test_two_projects_with_equal_task_ids_keep_separate_rows_attention_and_snapshots(tmp_path):
    ledger = summary.ObservedLedger()
    title = "Исправить оплату"
    in_a = _read("task-1", title, human="required", detail=_detail({"confirmation": ["pa"]}))
    in_b = _read("task-1", title, human="required", detail=_detail({"gate_decision": ["rb"]}),
                 run_id="run-b")
    live_a = summary.live_from_cycle(A, _cycle(in_a), ledger, NOW)
    live_b = summary.live_from_cycle(B, _cycle(in_b), ledger, LATER)
    assert live_a.rows[0]["attention"]["observed_at"] == NOW
    assert live_b.rows[0]["attention"]["observed_at"] == LATER
    assert live_a.rows[0]["attention"]["reasons"][0]["reason"] == "confirmation"
    assert live_b.rows[0]["attention"]["reasons"][0]["reason"] == "gate_decision"
    store = snapshots.SnapshotStore(tmp_path)
    for pid, live in ((A, live_a), (B, live_b)):
        assert store.put(pid, taken_at=live.taken_at, tasks=list(live.rows), task_queue=None,
                         auto_continue=None, quotas=None) == "written"
    got_a, got_b = store.get(A), store.get(B)
    assert got_a.tasks[0]["attention"]["reasons"][0]["sources"] == ["pa"]
    assert got_b.tasks[0]["attention"]["reasons"][0]["sources"] == ["rb"]
    assert got_a.tasks[0]["task"]["title"] == got_b.tasks[0]["task"]["title"] == title
    swept = summary.live_from_cycle(A, _cycle(_read("task-1", title)), ledger, LATER)
    assert swept.rows[0]["attention"] is None
    again_b = summary.live_from_cycle(B, _cycle(in_b), ledger, "2026-09-30T10:10:00Z")
    assert again_b.rows[0]["attention"]["observed_at"] == LATER, "A's sweep touched B's moments"


# -- free ---------------------------------------------------------------------------------------


QUIET = {"slot": {"state": "free", "run_id": None, "reason_code": None}, "entries": []}


def _free(*reads, queue=QUIET, **cycle) -> bool:
    return summary.is_free(_cycle(*reads, queue=queue, **cycle))


def test_a_project_is_free_when_no_grant_stands_no_human_is_required_and_the_queue_is_empty():
    assert _free(_read("task-1", "A", state="paused"), _read("task-2", "B", state="complete"))
    assert _free(), "no task at all is free"
    assert _free(_read("task-1", "A", state=None)), "a task with no run read has no grant"
    paused = _read("task-1", "A", state="paused")
    assert _free(paused, queue=None), "a child with no queue route has no queue"


@pytest.mark.parametrize("state", ["running", "waiting", "ready", "stalled", "restart_required"])
def test_a_run_whose_grant_still_stands_holds_the_project(state):
    assert not _free(_read("task-1", "A", state=state))


@pytest.mark.parametrize("state", ["paused", "revoked", "expired", "complete", "unconfigured"])
def test_a_run_with_no_current_grant_does_not_hold_the_project(state):
    assert _free(_read("task-1", "A", state=state))


def test_a_run_waiting_for_a_human_keeps_its_project_active():
    assert not _free(_read("task-1", "A", state="paused", human="required"))
    assert _free(_read("task-1", "A", state="paused", human="unknown")) is True


@pytest.mark.parametrize("queue", [
    {"slot": {"state": "busy"}, "entries": []}, {"slot": {"state": "stuck"}, "entries": []},
    {"slot": {"state": "unavailable"}, "entries": []},
    {"slot": {"state": "free"}, "entries": [{"run_id": "r"}]}, {"entries": []}, {"slot": {}},
    {"slot": {"state": "free"}, "entries": None}, [], "free"])
def test_a_busy_slot_or_any_queue_entry_or_a_queue_that_is_not_the_shape_holds_the_project(queue):
    assert not _free(queue=queue)


def test_one_failed_read_is_not_free_and_neither_is_a_run_that_cannot_be_read():
    assert not _free(failures=("quotas",))
    assert not _free(verdict="unreadable")
    assert not _free(verdict="busy_elsewhere")
    unreadable = child_client.TaskRead(task_row("task-1", "A"), {**run_row("r", None),
                                                                 "unreadable": True}, None)
    assert not summary.is_free(_cycle(unreadable, queue=QUIET))


# -- the cards of the limits ------------------------------------------------------------------


def _row_of(vendor: str | None, digest: str | None, observed: str | None, bindings: list[str],
            **extra) -> dict:
    account = None if vendor is None else {"vendor": vendor, "account_digest": digest,
                                           "verified_by": "read"}
    return {"account": account, "source": None, "observed_at": observed, "state": "observed",
            "reason": None, "windows": [], "binding_ids": bindings, "freshness": "current",
            "deferred_at": None, "account_status": "unknown" if account is None else "verified",
            **extra}


def test_several_bindings_of_one_verified_account_are_one_card_with_the_freshest_row():
    old = _row_of("openai", "c85e", "2026-09-30T09:00:00Z", ["first"], marker="old")
    new = _row_of("openai", "c85e", "2026-09-30T09:59:40Z", ["alias"], marker="new")
    other = _row_of("anthropic", "9f00", "2026-09-30T09:30:00Z", ["claude"])
    cards = summary.limit_cards([old, other, new])
    assert [card["key"] for card in cards] == [
        {"vendor": "openai", "account_digest": "sha256:c85e"},
        {"vendor": "anthropic", "account_digest": "sha256:9f00"}]
    assert cards[0]["row"]["marker"] == "new" and cards[0]["verified"] is True
    assert all(set(card) == {"key", "verified", "row"} for card in cards)


def test_an_unverified_account_is_never_merged_with_anything_and_is_one_card_per_row():
    first = _row_of(None, None, None, ["glm-1"])
    second = _row_of(None, None, None, ["glm-1"])
    verified = _row_of("openai", "c85e", NOW, ["glm-1"])
    cards = summary.limit_cards([first, verified, second])
    assert [card["verified"] for card in cards] == [False, True, False]
    assert cards[0]["key"] == {"binding_ids": ["glm-1"]} and cards[2]["key"] == cards[0]["key"]
    assert len(cards) == 3


def test_a_row_that_carries_a_balance_instead_of_windows_reaches_the_card_as_it_is():
    money = _row_of("dsh", "d001", NOW, ["dsh-1"],
                    balances=[{"currency": "USD", "total_balance": "12.50"}],
                    reset_applicability="not_applicable", is_available=True)
    (card,) = summary.limit_cards([money])
    assert card["row"]["balances"] == [{"currency": "USD", "total_balance": "12.50"}]
    assert card["row"]["reset_applicability"] == "not_applicable"


def _quotas(rows: list[dict], as_of: str = NOW) -> dict:
    return {"as_of": as_of, "max_age_seconds": 300, "providers": [], "snapshots": rows}


def test_the_limits_come_from_the_active_projects_live_read_then_limits_json_then_nothing():
    rows = [_row_of("openai", "c85e", NOW, ["first"])]
    live = summary.live_from_cycle(A, _cycle(quotas=_quotas(rows)), summary.ObservedLedger(), NOW)
    got = summary.limits_response(LATER, active_project_id=A, live=live, stored=None)
    assert (got["source"], got["project_id"], got["taken_at"], got["as_of"],
            got["max_age_seconds"]) == ("live", A, NOW, NOW, 300)
    assert got["computed_at"] == LATER and len(got["accounts"]) == 1
    earlier = "2026-09-30T09:00:00Z"
    stored = snapshots.LimitsSnapshot(B, earlier, _quotas(rows, earlier))
    from_file = summary.limits_response(LATER, active_project_id=None, live=None, stored=stored)
    assert (from_file["source"], from_file["project_id"], from_file["taken_at"]) == (
        "snapshot", B, "2026-09-30T09:00:00Z")
    failed = summary.live_from_cycle(A, child_client.Cycle("unreadable", failures=("tasks",)),
                                     summary.ObservedLedger(), LATER)
    assert summary.limits_response(LATER, active_project_id=A, live=failed,
                                   stored=stored)["source"] == "snapshot"
    none = summary.limits_response(LATER, active_project_id=None, live=None, stored=None)
    assert none == {"computed_at": LATER, "project_id": None, "source": "none",
                    "taken_at": None, "as_of": None, "max_age_seconds": None, "accounts": []}


def test_a_live_cycle_whose_quotas_read_failed_is_not_a_source_of_limits():
    stored = snapshots.LimitsSnapshot(A, NOW, _quotas([_row_of("openai", "c85e", NOW, ["x"])]))
    live = summary.live_from_cycle(A, _cycle(quotas=None, failures=("quotas",)),
                                   summary.ObservedLedger(), LATER)
    assert summary.limits_response(LATER, active_project_id=A, live=live,
                                   stored=stored)["source"] == "snapshot"


def test_a_live_read_of_a_child_that_is_not_the_active_one_is_not_a_source_of_limits():
    stored = snapshots.LimitsSnapshot(B, NOW, _quotas([_row_of("openai", "c85e", NOW, ["x"])]))
    echo = {**_quotas([]), "hub_snapshot": {"project_id": B, "taken_at": NOW}}
    viewed = summary.live_from_cycle(A, _cycle(quotas=echo, mode="view"),
                                     summary.ObservedLedger(), LATER)
    got = summary.limits_response(LATER, active_project_id=A, live=viewed, stored=stored)
    assert (got["source"], got["project_id"], got["taken_at"]) == ("snapshot", B, NOW)
    unsaid = child_client.Cycle("live", {"project_id": A}, (), None, None, _quotas([]), ())
    silent = summary.live_from_cycle(A, unsaid, summary.ObservedLedger(), LATER)
    assert summary.limits_response(LATER, active_project_id=A, live=silent,
                                   stored=None)["source"] == "none", "no mode said is not active"
