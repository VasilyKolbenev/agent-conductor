"""The hub's stub and its side, as values (spec 4.1.9, 4.1.10, 4.5.4, 4.5.5).

When no project is chosen, or the chosen one has no running desk, the centre of the page is a stub:
the project's line, its one main action, and the countdown of a stop that is under way; beside it
stand the queue of projects (who is in progress, who waits for their turn and since when) and the
limits of the active project, one card per account. `hub-stub.js` holds the pure part: a stub is the
rail's own words for the same project (one rule for a project's line wherever it is drawn); the
countdown is handed the clock, never read; a limit that has no reading is "no data" and never a
zero; an account the hub could not confirm is its own card and says so. The address a running desk
is opened at is the one the hub gave, judged by the rule of 4.5.5. The tests run the packaged
modules under Node on the contract fixtures; the drawing is proved in the browser
(`browser_tests/test_hub_page.py`).
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"stub": "hub-stub.js", "rail": "hub-rail.js", "time": "desk-time.js"}
PAGE = fixture("hub", "hub_projects.json")["response"]
LIMITS = fixture("hub", "hub_limits.json")["response"]
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const page = d.page, limits = d.limits;
const ctx = (over = {}) => ({locale: "en", projects: page.projects,
  activeId: page.active_project_id, queue: page.project_queue, ...over});
const when = (iso) => time.instantText("en", iso).short;
const row = (over) => ({...structuredClone(page.projects[2]), ...over});
"""


def js(body: str, **extra: Any) -> Any:
    return run_js(PRELUDE + body, {"page": PAGE, "limits": LIMITS, **extra}, modules=MODULES)


def test_the_countdown_of_a_stop_is_the_time_left_as_minutes_and_seconds_from_the_clock_handed_in():
    out = js("""
      const at = Date.parse("2026-09-29T10:05:00Z");
      const left = (ms) => stub.drainText("en", "2026-09-29T10:05:00Z", at - ms);
      show({minute: left(60000), odd: left(65000), hour: left(3725000), now: left(0),
        past: left(-1), none: stub.drainText("en", null, at), junk: stub.drainText("en", "x", at),
        ru: stub.drainText("ru", "2026-09-29T10:05:00Z", at - 90000)});
    """)
    assert out == {"minute": "Stopping: 1:00 left", "odd": "Stopping: 1:05 left",
                   "hour": "Stopping: 62:05 left", "now": None, "past": None, "none": None,
                   "junk": None, "ru": "Остановка: осталось 1:30"}


def test_a_stub_says_the_rails_words_for_its_project_and_a_stop_under_way_its_countdown():
    out = js("""
      const at = Date.parse("2026-09-29T10:05:00Z");
      const stopping = row({state: "stopping", working: "stopped", stopped_at: null,
        drain_deadline: "2026-09-29T10:05:00Z"});
      const plain = row({resume_run_id: "run-1"});
      show({said: stub.stubModel(stopping, ctx(), at - 30000),
        same: rail.projectLine(stopping, ctx()).text, plain: stub.stubModel(plain, ctx(), at),
        muted: stub.stubModel(page.projects[1], ctx(), at)});
    """)
    said = out["said"]
    assert said["line"] == out["same"], "one rule for a project's line wherever it is drawn"
    assert said["line"].startswith("Stopped · Stopping, until ")
    assert said["drain"] == "Stopping: 0:30 left" and said["actions"] == []
    assert [a["label"] for a in out["plain"]["actions"]] == ["Continue"]
    assert out["plain"]["drain"] is None
    assert out["muted"]["note"].startswith("snapshot from ") and out["muted"]["tone"] is None


def test_the_centre_is_a_choice_a_link_to_a_running_desk_or_a_stub_and_nothing_else():
    out = js("""
      const sel = (id) => ({project_id: id, task_id: null, run_id: null, gate_id: null});
      const view = (selection, over = {}) => ({locale: "en", projects: page.projects,
        activeId: page.active_project_id, queue: page.project_queue, selection, hubPort: "7700",
        theme: null, ...over});
      show({none: stub.centerCase(view(sel(null))),
        running: stub.centerCase(view(sel(page.projects[0].project_id))),
        stopped: stub.centerCase(view(sel(page.projects[2].project_id))),
        gone: stub.centerCase(view(sel("f".repeat(32))))});
    """)
    assert out == {"none": "choose", "running": "running", "stopped": "stub", "gone": "choose"}


def test_the_queue_names_who_is_in_progress_and_each_project_waiting_with_its_controls():
    out = js("""
      const two = structuredClone(page);
      two.projects[2].working = "queued";
      two.projects[2].queue_position = 2;
      two.projects[2].auto_continue = null;
      two.project_queue = [page.projects[1].project_id, page.projects[2].project_id];
      const view = {locale: "en", projects: two.projects, activeId: two.active_project_id,
        queue: two.project_queue};
      const idle = {...view, activeId: null};
      const stopping = {...view, projects: two.projects.map((one, at) => at === 0
        ? {...one, state: "stopping", drain_deadline: null} : one)};
      show({now: stub.queueModel(view), idle: stub.queueModel(idle).now,
        stopping: stub.queueModel(stopping).now, empty: stub.queueModel({...view, queue: []}).rows,
        at: when(page.projects[1].auto_continue.set_at)});
    """)
    now = out["now"]
    assert now["now"] == "In progress: web-app"
    assert [row["text"] for row in now["rows"]] == [
        f"1. landing · will continue by itself · flag since {out['at']}",
        "2. bot · will continue by itself"]
    assert [[a["id"] for a in row["actions"]] for row in now["rows"]] == [
        ["lower", "clear_flag"], ["raise", "clear_flag"]]
    assert [row["project_id"] for row in now["rows"]] == [PAGE["projects"][1]["project_id"],
                                                         PAGE["projects"][2]["project_id"]]
    assert out["idle"] == "There is no active project"
    assert out["stopping"] == "In progress: web-app · Stopping…"
    assert out["empty"] == []


def test_a_queue_holds_no_project_the_hub_does_not_list_and_no_raw_id():
    out = js("""
      const view = {locale: "en", projects: page.projects, activeId: page.active_project_id,
        queue: ["f".repeat(32), page.projects[1].project_id]};
      show(stub.queueModel(view).rows.map((one) => one.text));
    """)
    assert len(out) == 1 and out[0].startswith("2. landing"), (
        "a place in the queue is its place in the hub's list; an id the hub does not list has none")


def test_each_account_of_the_limits_is_one_card_and_what_was_not_read_says_no_data_not_zero():
    out = js("""
      show({model: stub.limitsModel(limits, "en"), ru: stub.limitsModel(limits, "ru").caption,
        at: when(limits.taken_at), reset: when(limits.accounts[0].row.windows[0].resets_at)});
    """)
    model = out["model"]
    assert model["caption"] == "limits are read by the active project"
    first, second = model["cards"]
    assert first == {"title": "openai", "unverified": False, "note": None, "rows": [
        {"text": f"5 h: 75% left · resets {out['reset']}", "quiet": False}]}
    assert second == {"title": "glm-1", "unverified": True,
                      "note": "the account is not confirmed",
                      "rows": [{"text": "no data", "quiet": True}]}
    assert out["ru"] == "лимиты читает активный проект"


def test_a_snapshot_of_the_limits_is_captioned_with_its_moment_and_no_reading_is_captioned_so():
    out = js("""
      const snap = {...structuredClone(limits), source: "snapshot"};
      const none = {...structuredClone(limits), source: "none", accounts: [], taken_at: null};
      show({snap: stub.limitsModel(snap, "en").caption, none: stub.limitsModel(none, "en"),
        absent: stub.limitsModel(null, "en"), at: when(limits.taken_at)});
    """)
    assert out["snap"] == f"limits are read by the active project · snapshot from {out['at']}"
    assert out["none"] == {"caption": "no data · limits are read by the active project",
                           "cards": []}
    assert out["absent"] == out["none"]


def test_a_balance_and_the_windows_of_a_subscription_are_said_as_the_server_gave_them():
    out = js("""
      const money = {key: {vendor: "deepseek", account_digest: "sha256:" + "a".repeat(64)},
        verified: true, row: {account: {vendor: "deepseek"}, state: "observed", windows: [],
          freshness: "current", balances: [{currency: "USD", total_balance: "4.20",
            granted_balance: "0", topped_up_balance: "4.20"}], is_available: true,
          reset_applicability: "not_applicable", resets_at: null}};
      const stale = structuredClone(limits.accounts[0]);
      stale.row.windows = [{...stale.row.windows[0], freshness: "stale", duration_minutes: 45,
        resets_at: null, remaining_percent: 12.4}];
      const broken = structuredClone(limits.accounts[1]);
      broken.row.state = "error";
      const odd = {key: {vendor: "x"}, verified: true, row: null};
      const model = stub.limitsModel({...limits, accounts: [money, stale, broken, odd]}, "en");
      show(model.cards.map((card) => [card.title, card.rows.map((one) => one.text)]));
    """)
    assert out == [
        ["deepseek", ["Balance 4.20 USD · reset does not apply"]],
        ["openai", ["45 min: 12% left · out of date"]],
        ["glm-1", ["the source is unavailable"]],
        ["x", ["no data"]]]


def test_the_address_of_a_running_desk_is_the_one_the_hub_gave_and_judged_by_the_rule_of_the_spec():
    out = js("""
      const prefs = {locale: "ru", theme: "dark"};
      const at = (desk_url, over = {}) => rail.deskLink(row({state: "running", desk_url,
        project_id: "a".repeat(32), ...over}), {task: "task-1", run: "run-1", gate: null,
        panel: "continue"}, prefs, "7700");
      const ok = "http://127.0.0.1:7701/panel/desk.html";
      show({ok: at(ok), hubPort: at("http://127.0.0.1:7700/panel/desk.html"),
        big: at("http://127.0.0.1:65536/panel/desk.html"),
        zero: at("http://127.0.0.1:0/panel/desk.html"),
        host: at("http://localhost:7701/panel/desk.html"),
        path: at("http://127.0.0.1:7701/panel/desk.html?x=1"),
        other: at("http://127.0.0.1:7701/panel/studio.html"), none: at(null),
        notRunning: at(ok, {state: "stopped"}),
        scheme: at("https://127.0.0.1:7701/panel/desk.html"),
        maxPort: at("http://127.0.0.1:65535/panel/desk.html") !== null});
    """)
    link = out["ok"]
    assert link.startswith("http://127.0.0.1:7701/panel/desk.html#")
    fields = dict(part.split("=") for part in link.split("#")[1].split("&"))
    assert fields == {"project": "a" * 32, "task": "task-1", "run": "run-1", "panel": "continue",
                      "lang": "ru", "theme": "dark"}, "identifiers and interface words only"
    assert "embed" not in fields, "opened in a tab of its own, not framed"
    assert all(out[name] is None for name in ("hubPort", "big", "zero", "host", "path", "other",
                                              "none", "notRunning", "scheme"))
    assert out["maxPort"] is True
