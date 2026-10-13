"""The git block as the wizard's model carries it: the slice, the closed event table, the asks.

`tests/test_desk_wizard_git_run.py` drives the seam on its own. Here the REAL model stands round it:
the eight events are in its one table, each ask is handed out once by `stepWizard`, an answer lands
through its table, the git read is not asked again while a press works, the name is fixed while a
press works, and closing a window that has a request in flight asks first.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import PRELUDE, fixture, run_js

MODULES = {"wiz": "desk-wizard-model.js", "g": "desk-wizard-git.js"}
EVENTS = ("git-start", "git-mode", "git-list", "git-preview", "git-init", "git-exclude",
          "git-confirm", "git-continue")
DATA: dict[str, Any] = {
    "unborn": fixture("wizard", "git_unborn.json"),
    "not_git": fixture("wizard", "git_not_git.json"),
    "pending": fixture("wizard", "git_pending_unfinished.json"),
    "preview": fixture("wizard", "setup_preview_snapshot.json"),
    "receipt": fixture("wizard", "setup_receipt_commit.json"),
    "init": fixture("wizard", "setup_receipt_init.json"),
}
#: A wizard that has read git, with the door of the confirm shut or open, and the asks the model
#: made due by one event (`step`).
STAND = PRELUDE + """
const ok = (payload) => ({status: "accepted", code: null, payload});
const onRead = (name, door = true, over = {}) => {
  const state = reply(opened(started({actor: "Anna", ...over})), "git", d[name]);
  return {...state, git: {...state.git, open: door}};
};
const step = (state, event) => wiz.stepWizard(state, event);
const ids = (result) => result.asks.map((ask) => ask.id);
"""


def js(body: str) -> Any:
    return run_js(STAND + body, DATA, modules=MODULES)


def test_the_wizard_opens_with_the_git_slice_made_from_the_switch_literal():
    out = js("""
      const state = open({actor: "Anna"});
      show({git: state.git, literal: g.FIRST_COMMIT_CONFIRM_OPEN,
        frozen: Object.isFrozen(state.git)});
    """)
    assert out["git"] == {"open": out["literal"], "door": True, "panel": None, "mode": None,
                          "preview": None, "list": False, "seq": 0, "sending": None,
                          "result": None}
    assert isinstance(out["literal"], bool) and out["frozen"] is True


def test_a_host_whose_transport_has_no_door_for_the_setup_route_says_so_at_the_opening():
    out = js("""
      const opened_ = (setupDoor) => open({actor: "Anna", setupDoor}).git.door;
      const state = reply(opened(started({actor: "Anna", setupDoor: false})), "git", d.unborn);
      const shut = {...state, git: {...state.git, open: true}};
      const kinds = ["init", "exclude", "preview", "confirm", "continue"];
      show({named: [opened_(true), opened_(false), opened_(undefined)],
        blocks: kinds.map((kind) => wiz.pressBlock(shut, kind)),
        init: step(reply(opened(started({actor: "Anna", setupDoor: false})), "git", d.not_git),
          {type: "git-init"}).asks.length});
    """)
    assert out["named"] == [True, False, True], "only an explicit false closes it"
    assert out["blocks"] == ["door_missing"] * 5
    assert out["init"] == 0


def test_the_eight_events_are_in_the_models_closed_table():
    out = js("""show({events: wiz.EVENTS});""")
    assert set(EVENTS) <= set(out["events"])


def test_connect_git_and_the_first_commit_are_not_waiting_for_a_door_any_more():
    out = js("""
      show({later: wiz.LATER, connect: wiz.isLater("connect_git"),
        first: wiz.isLater("first_commit")});
    """)
    assert out["connect"] is False and out["first"] is False
    assert "connect_git" not in out["later"] and "first_commit" not in out["later"]


def test_stepwizard_hands_a_press_out_as_one_write_ask_once_and_its_answer_lands():
    out = js("""
      let state = onRead("unborn");
      const started_ = step(state, {type: "git-start"});
      const preview = step(started_.state, {type: "git-preview"});
      const again = step(preview.state, {type: "tick", now: "2026-10-09T12:00:00Z"});
      const press = step(preview.state, {type: "git-preview"});
      const landed = step(preview.state, {type: "answered", ask: preview.asks[0],
        result: ok(d.preview)});
      const second = step(landed.state, {type: "git-preview"});
      show({start: ids(started_), first: preview.asks.map((ask) => [ask.id, ask.name, ask.door,
        ask.target, ask.subject, ask.body]), again: ids(again), press: ids(press),
        samePress: press.state === preview.state, landed: ids(landed),
        preview: landed.state.git.preview.mode, sending: landed.state.git.sending,
        second: ids(second), asked: second.state.asked.filter((id) => id.startsWith("write:"))});
    """)
    assert out["start"] == []
    assert out["first"] == [["write:git:preview:1", "git_preview", "write", "gitSetup", None,
                             {"step": "first_commit", "mode": "snapshot", "preview": True}]]
    assert out["again"] == [] and out["press"] == [] and out["samePress"] is True
    assert out["landed"] == [] and out["preview"] == "snapshot" and out["sending"] is None
    assert out["second"] == ["write:git:preview:2"]
    assert out["asked"] == ["write:git:preview:1", "write:git:preview:2"]


def test_the_confirm_the_connect_and_the_exclusion_land_through_the_models_own_table():
    out = js("""
      let state = onRead("unborn");
      state = step(step(state, {type: "git-start"}).state, {type: "git-preview"}).state;
      state = step(state, {type: "answered", ask: state.git.sending.ask,
        result: ok(d.preview)}).state;
      const confirm = step(state, {type: "git-confirm"});
      const done = step(confirm.state, {type: "answered", ask: confirm.asks[0],
        result: ok(d.receipt)});
      const init = step(onRead("not_git"), {type: "git-init"});
      const connected = step(init.state, {type: "answered", ask: init.asks[0],
        result: ok(d.init)});
      show({confirm: ids(confirm), result: done.state.git.result.status,
        next: ids(done), init: ids(init), initResult: connected.state.git.result.kind,
        initNext: ids(connected), readGone: connected.state.reads.git === undefined});
    """)
    assert out["confirm"] == ["write:git:confirm:2"] and out["result"] == "done"
    assert out["next"] == ["read:git"], "the read is the one thing asked after an answer"
    assert out["init"] == ["write:git:init:1"] and out["initResult"] == "init"
    assert out["initNext"] == ["read:git"] and out["readGone"] is True


def test_a_lost_answer_asks_the_git_read_through_the_model_and_nothing_else():
    out = js("""
      let state = onRead("not_git");
      const sent = step(state, {type: "git-init"});
      const lost = step(sent.state, {type: "answered", ask: sent.asks[0],
        result: {status: "unknown"}});
      show({asks: lost.asks.map((ask) => [ask.id, ask.name, ask.door]),
        result: [lost.state.git.result.status, lost.state.git.result.kind]});
    """)
    assert out["asks"] == [["read:git", "git", "read"]]
    assert out["result"] == ["lost", "init"]


def test_the_git_reread_is_held_while_a_press_works_and_the_exit_to_reread_works_after():
    out = js("""
      const sent = step(onRead("not_git"), {type: "git-init"});
      const held = step(sent.state, {type: "reread", name: "git"});
      const landed = step(sent.state, {type: "answered", ask: sent.asks[0], result: ok(d.init)});
      const idle = step(onRead("not_git"), {type: "reread", name: "git"});
      show({held: held.state === sent.state && held.asks.length === 0,
        readStands: held.state.reads.git !== undefined, idle: ids(idle),
        afterLanding: ids(landed)});
    """)
    assert out["held"] is True and out["readStands"] is True
    assert out["idle"] == ["read:git"] and out["afterLanding"] == ["read:git"]


def test_the_name_is_fixed_while_a_press_works_and_free_again_after_its_answer():
    out = js("""
      const sent = step(onRead("not_git"), {type: "git-init"});
      const refused = step(sent.state, {type: "actor-edit", value: "Mallory"});
      const landed = step(sent.state, {type: "answered", ask: sent.asks[0], result: ok(d.init)});
      const edited = step(landed.state, {type: "actor-edit", value: "Bob"});
      show({fixed: refused.state === sent.state, actor: refused.state.launch.actor,
        body: sent.asks[0].body.actor, after: edited.state.launch.actor});
    """)
    assert out == {"fixed": True, "actor": "Anna", "body": "Anna", "after": "Bob"}


def test_closing_asks_first_while_a_request_works_and_not_otherwise():
    out = js("""
      const idle = step(onRead("unborn"), {type: "close-request"});
      const sent = step(onRead("not_git"), {type: "git-init"});
      const asked = step(sent.state, {type: "close-request"});
      const kept = step(asked.state, {type: "close-cancel"});
      show({idle: [idle.state.closing, wiz.closeNeedsWarning(idle.state)],
        busy: [asked.state.closing, wiz.closeNeedsWarning(sent.state)],
        kept: kept.state.closing, closeBusy: wiz.closeBusy(sent.state)});
    """)
    assert out == {"idle": [None, False], "busy": ["confirm", True], "kept": None,
                   "closeBusy": True}


def test_in_view_the_model_never_makes_a_setup_ask():
    out = js("""
      const state = onRead("not_git", true, {viewMode: true});
      const rows = ["git-start", "git-preview", "git-init", "git-exclude", "git-confirm",
        "git-continue"].map((type) => ids(step(state, {type})));
      show(rows);
    """)
    assert out == [[]] * 6


def test_the_models_exports_carry_the_block_vocabulary_and_its_facts():
    out = js("""
      const state = onRead("unborn");
      show({words: Object.keys(wiz.FIRST_WORDS).sort(), facts: typeof wiz.firstFacts,
        block: wiz.pressBlock(state, "confirm"), shown: wiz.firstFacts(state).shown});
    """)
    assert out["words"] == sorted(["why", "lost", "busy", "done", "unsent", "next", "codes",
                                   "manual", "warning", "pending", "mode"])
    assert out["facts"] == "function"
    assert out["block"] == "not_offered", "the confirm exists only inside the opened panel"
    assert out["shown"]["panel"] is False


#: What `manual[].reason` can be in the current preview, read from `git_setup_snapshot._manual`:
#: its own three words and the codes that `containment.portal_violation` and
#: `first_directory_violation` give for a listed path. Twelve is that set united with all of
#: `RouteViolationCode`, which this path does not give: `missing`, `outside_root`,
#: `root_not_descendant` and `parent_traversal` are never returned for a listed file.
MANUAL_REASONS = ("unportable_name", "irregular_file", "hard_link", "symlink", "junction",
                  "reparse_point", "unreadable", "not_directory")


def test_the_desk_has_words_for_exactly_the_eight_reasons_the_current_preview_can_give():
    assert sorted(js("show(g.MANUAL_REASONS);")) == sorted(MANUAL_REASONS)
