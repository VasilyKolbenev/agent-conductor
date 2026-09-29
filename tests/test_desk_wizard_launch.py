"""The wizard model's step 6 ("Запуск"): the terms card and what may be pressed (6.4.4-6.4.5).

The card is the server's own answer, drawn as it came: the preview `{}` with its `budget`
(`tests/fixtures/wizard/preview_*.json`, the shapes of 6.4.4 and 7.8), and the slot of
`GET /command/queue` (`queue_*.json`, 4.4.6) says which button there is. The wizard adds nothing
to a number: the one arithmetic it does is a difference of two instants for the countdown. Every
test is a value run through the real module; what is drawn from it is
`browser_tests/test_desk_wizard_launch.py`.
"""
from __future__ import annotations

import re

import pytest

from tests.desk_wizard_node import fixture, run_js
from tests.test_desk_wizard_prepare import CHAIN, DATA as CHAIN_DATA, MODULES

DATA = {**CHAIN_DATA,
        "replacing": fixture("wizard", "preview_replacing.json"),
        "exhausted": fixture("wizard", "preview_exhausted.json"),
        "run_detail": fixture("wizard", "run_detail.json"),
        "auto_new": fixture("wizard", "automation_unconfigured.json"),
        "auto_holder": fixture("wizard", "automation_holder_waiting.json"),
        **{name: fixture("wizard", f"queue_{name}.json") for name in (
            "free", "busy_waiting", "busy_running", "stuck", "view", "owner_required",
            "server_stopping", "with_entries")},
        **{f"prep_{name}": fixture("wizard", f"preparation_{name}.json") for name in (
            "ready", "documents_missing", "queued", "authorized", "ended")}}
LAUNCH = CHAIN + """
const runId = "task-t1-r1";
const asksOf = (state, prefix = "launch_") => wiz.wantedAsks(state)
  .filter((ask) => ask.name.startsWith(prefix));
const named = (state, name) => asksOf(state).find((ask) => ask.name === name);
const say = (state, name, result) => wiz.stepWizard(state, {type: "answered",
  ask: named(state, name), result});
const fresh = (payload) => moved(payload);
//: The wizard past the chain (the preview landed) with the three reads of the card answered.
const reviewed = (over = {}) => {
  const {queue = d.free, automation = d.auto_new, plan = d.run_detail, opening = {},
    clock = null} = over;
  let state = drive(press(ready({}, d.flows.standard, d.git, opening))).state;
  state = say(state, "launch_queue", ok(fresh(queue))).state;
  state = say(state, "launch_automation", ok(fresh(automation))).state;
  state = say(state, "launch_run", ok(fresh(plan))).state;
  state = wiz.reduceWizard(state, {type: "actor-edit", value: "vasily"});
  return clock === null ? state : wiz.reduceWizard(state, {type: "tick", now: clock});
};
const CLOCK = "2026-09-29T10:00:30Z";
const buttons = (state) => {
  const {controls} = wiz.launchFacts(state);
  return {start: [controls.start.shown, controls.start.blocked],
    enqueue: [controls.enqueue.shown, controls.enqueue.blocked], release: controls.release,
    why: controls.why};
};
"""


def test_a_prepared_run_reads_its_queue_its_automation_and_its_plan_once_and_nothing_else():
    out = run_js(LAUNCH + """
      const state = drive(press(ready())).state;
      const first = asksOf(state).map((ask) => [ask.id, ask.name, ask.door, ask.target,
        ask.subject]);
      let now = say(state, "launch_queue", ok(fresh(d.free))).state;
      now = say(now, "launch_automation", ok(fresh(d.auto_new))).state;
      now = say(now, "launch_run", ok(fresh(d.run_detail))).state;
      const again = wiz.reduceWizard(now, {type: "launch-reread"});
      const failed = say(state, "launch_queue", refused("store_error")).state;
      show({first, quiet: asksOf(now).length, reread: asksOf(again).map((ask) => ask.id),
        failed_asks: asksOf(failed).map((ask) => ask.name), phase: state.launch.phase,
        before_the_chain: asksOf(ready()).length});
    """, DATA, modules=MODULES)
    assert out["first"] == [
        ["read:launch:queue:0", "launch_queue", "read", "queue", None],
        ["read:launch:automation:0", "launch_automation", "read", "automation", "task-t1-r1"],
        ["read:launch:run:0", "launch_run", "read", "run", "task-t1-r1"]]
    assert out["quiet"] == 0 and out["phase"] == "review"
    assert out["reread"] == ["read:launch:queue:1", "read:launch:automation:1"]
    assert out["failed_asks"] == ["launch_automation", "launch_run"], "a failed read stays failed"
    assert out["before_the_chain"] == 0


def test_the_wizard_needs_a_nonce_and_the_actor_holds_the_gate_decisions_grammar():
    out = run_js(LAUNCH + """
      const bad = (opening) => { try { wiz.initialWizard(opening); return false; }
        catch { return true; } };
      const base = {starterId: null, viewMode: false, newTaskId: "task-t1"};
      const edit = (value) => wiz.reduceWizard(reviewed(), {type: "actor-edit", value});
      show({missing: bad(base), short: bad({...base, nonce: "abc"}),
        upper: bad({...base, nonce: "ABCDEFGH12"}), fine: bad({...base, nonce: "abcd1234"}),
        valid: [wiz.launchFacts(edit("vasily")).actor, wiz.launchFacts(edit("Vasily.K-2_x")).actor],
        checks: ["vasily", "Vasily.K-2_x", "", " ", "Вы: Василий", "a b", "-x", "x".repeat(129),
          "x".repeat(128)].map((value) => wiz.launchFacts(edit(value)).actorValid)});
    """, DATA, modules=MODULES)
    assert out["missing"] is True and out["short"] is True and out["upper"] is True
    assert out["fine"] is False
    assert out["valid"] == ["vasily", "Vasily.K-2_x"]
    assert out["checks"] == [True, True, False, False, False, False, False, False, True]


def test_the_first_preview_becomes_the_card_and_one_that_is_not_the_servers_shape_is_unreadable():
    out = run_js(LAUNCH + """
      const stateOf = (payload) => {
        const state = drive(press(ready()), {preview: () => ok(payload)}).state;
        return wiz.launchFacts(state);
      };
      const extra = {...fresh(d.preview), surprise: 1};
      const other = fresh(d.preview);
      other.terms.run_id = "someone-elses-run";
      const noBudget = fresh(d.preview);
      delete noBudget.budget;
      show({good: [stateOf(fresh(d.preview)).card !== null, stateOf(fresh(d.preview)).error],
        extra: stateOf(extra).error, other: stateOf(other).error,
        no_budget: stateOf(noBudget).error, card_of_bad: stateOf(extra).card});
    """, DATA, modules=MODULES)
    assert out["good"] == [True, None]
    assert out["extra"] == out["other"] == out["no_budget"] == "preview_unreadable"
    assert out["card_of_bad"] is None


def test_the_card_is_the_servers_numbers_unchanged_for_the_standard_cycle():
    out = run_js(LAUNCH + """
      const facts = wiz.launchFacts(reviewed({clock: CLOCK}));
      show({actions: facts.card.actions, time: facts.card.time, window: facts.card.window,
        clean: facts.card.clean, worst: facts.card.worst, warnings: facts.card.warnings,
        steps: facts.card.steps, harnesses: facts.card.harnesses, receives: facts.card.receives,
        exhausted: facts.card.exhausted, spent: facts.card.spent});
    """, DATA, modules=MODULES)
    assert out["actions"] == {"max": 4, "of": 8} and out["spent"] is None
    assert out["time"] == 12600 and out["window"] == 16200
    assert out["clean"] == {"actions": 2, "seconds": 5400}
    assert out["worst"] == {"actions": 4, "seconds": 12600}
    assert out["warnings"] == [] and out["exhausted"] is False
    assert [(row["step"], row["timeout"], row["attempts"], row["clamped"], row["harness"])
            for row in out["steps"]] == [
        ("analyst", 1800, 1, False, "Claude Code (headless, experimental)"),
        ("do", 1800, 3, False, "Codex CLI (headless, experimental)")]
    assert [row["role"] for row in out["steps"]] == ["role-analyst", "role-doer"]
    assert [(row["id"], row["name"], row["version"]) for row in out["harnesses"]] == [
        ("claude-code", "Claude Code (headless, experimental)", "2.1.90"),
        ("codex", "Codex CLI (headless, experimental)", "0.157.1")]
    assert out["receives"]["instructions"] == [
        {"step": "do", "digest": "sha256:" + "0ddba11a" * 8}]
    assert [(row["ref"], row["digest"]) for row in out["receives"]["inputs"]] == [
        ("artifact-brief", "sha256:" + "0badf00d" * 8),
        ("artifact-materials", "sha256:" + "0defaced" * 8)]


def test_a_replacement_grants_card_says_what_was_spent_and_an_exhausted_one_says_so():
    out = run_js(LAUNCH + """
      const at = (payload) => {
        const state = drive(press(ready()), {preview: () => ok(fresh(payload))}).state;
        return wiz.launchFacts(state).card;
      };
      const replacing = at(d.replacing), exhausted = at(d.exhausted);
      show({spent: replacing.spent, actions: replacing.actions, exhausted: replacing.exhausted,
        drained: [exhausted.exhausted, exhausted.spent, exhausted.actions]});
    """, DATA, modules=MODULES)
    assert out["spent"] == {"actions": 2, "seconds": 5400}
    assert out["actions"] == {"max": 4, "of": 8} and out["exhausted"] is False
    assert out["drained"] == [True, {"actions": 2, "seconds": 7200}, {"max": 2, "of": 8}]


def test_the_two_warnings_are_named_only_when_the_servers_numbers_say_so():
    out = run_js(LAUNCH + """
      const warned = (edit) => {
        const payload = fresh(d.preview);
        edit(payload.budget);
        const state = drive(press(ready()), {preview: () => ok(payload)}).state;
        return wiz.launchFacts(state).card.warnings;
      };
      show({none: warned(() => {}),
        clean: warned((budget) => { budget.clean.actions = 9; }),
        worst: warned((budget) => { budget.worst.actions = 10; }),
        both: warned((budget) => { budget.clean.actions = 9; budget.worst.actions = 12; }),
        at_the_limit: warned((budget) => { budget.clean.actions = 8; budget.worst.actions = 8; })});
    """, DATA, modules=MODULES)
    assert out == {"none": [], "clean": [{"code": "clean_over_actions", "actions": 9, "limit": 8}],
                   "worst": [{"code": "worst_over_actions", "actions": 10, "limit": 8}],
                   "both": [{"code": "clean_over_actions", "actions": 9, "limit": 8},
                            {"code": "worst_over_actions", "actions": 12, "limit": 8}],
                   "at_the_limit": []}


def test_the_seed_line_is_what_the_chain_wrote_the_request_in_view_or_nothing():
    out = run_js(LAUNCH + """
      const seedOf = (over = {}, state = null) => wiz.launchFacts(state ?? reviewed(over))
        .card.receives.seed;
      const viewSeed = drive(press(ready({}, d.flows.standard, d.git, {viewMode: true})), {
        prep_seed: () => ok({...fresh(d.prep_seeded).seed, state: "requested", base_commit: null,
          base_ref: null})}).state;
      const starter = drive(press(readyStarter())).state;
      show({seeded: seedOf(), view: seedOf({}, viewSeed), starter: seedOf({}, starter)});
    """, DATA, modules=MODULES)
    assert out["seeded"] == {"kind": "copy", "ref": "main", "commit": "abc1234"}
    assert out["view"] == {"kind": "request"}
    assert out["starter"] is None


@pytest.mark.parametrize("queue,start,enqueue,release,why", [
    ("free", [True, None], [False, None], False, None),
    ("busy_waiting", [False, None], [True, None], False, None),
    ("busy_running", [False, None], [True, None], False, None),
    ("stuck", [False, None], [True, None], True, None),
    ("view", [True, "project_not_active"], [True, None], False, None),
    ("owner_required", [False, None], [False, None], False, "owner_required"),
    ("server_stopping", [False, None], [False, None], False, "server_stopping")])
def test_each_row_of_the_slot_table_gives_the_buttons_of_the_spec(
        queue, start, enqueue, release, why):
    out = run_js(LAUNCH + "show(buttons(reviewed({queue: d[d.which]})));",
                 {**DATA, "which": queue}, modules=MODULES)
    assert out == {"start": start, "enqueue": enqueue, "release": release, "why": why}


def test_before_the_queue_is_read_or_when_it_could_not_be_no_button_is_offered_and_it_says_why():
    out = run_js(LAUNCH + """
      const state = drive(press(ready())).state;
      const failed = say(state, "launch_queue", refused("store_error")).state;
      const lostRead = say(state, "launch_queue", lost).state;
      show({reading: buttons(state), failed: buttons(failed), lost: buttons(lostRead)});
    """, DATA, modules=MODULES)
    none = {"start": [False, None], "enqueue": [False, None], "release": False}
    assert out["reading"] == {**none, "why": "slot_reading"}
    assert out["failed"] == {**none, "why": "slot_unread"} == out["lost"]


def test_an_exhausted_limit_a_replaced_card_or_a_bad_name_disables_both_buttons_with_its_reason():
    out = run_js(LAUNCH + """
      const gone = drive(press(ready()), {preview: () => ok(fresh(d.exhausted))}).state;
      const readied = (state) => {
        let now = say(state, "launch_queue", ok(fresh(d.busy_waiting))).state;
        now = say(now, "launch_automation", ok(fresh(d.auto_new))).state;
        return wiz.reduceWizard(now, {type: "actor-edit", value: "vasily"});
      };
      const nameless = wiz.reduceWizard(reviewed(), {type: "actor-edit", value: ""});
      const free = reviewed();
      show({exhausted: buttons(readied(gone)), no_name: buttons(nameless), ok: buttons(free)});
    """, DATA, modules=MODULES)
    assert out["exhausted"]["enqueue"] == [True, "exhausted"]
    assert out["no_name"]["start"] == [True, "actor_invalid"]
    assert out["ok"]["start"] == [True, None]


def test_the_authorize_body_is_the_spec_body_and_the_id_is_one_per_card_and_never_twice():
    out = run_js(LAUNCH + """
      const state = reviewed();
      const begun = wiz.stepWizard(state, {type: "launch-start"});
      const preview = fresh(d.preview);
      const again = wiz.stepWizard(begun.state, {type: "launch-start"});
      show({asks: begun.asks.map((ask) => [ask.id, ask.name, ask.door, ask.target, ask.subject,
          ask.body]), phase: begun.state.launch.phase, terms: preview.terms,
        twice: again.asks.length, card: state.launch.card,
        blocked: wiz.stepWizard(wiz.reduceWizard(state, {type: "actor-edit", value: ""}),
          {type: "launch-start"}).asks.length,
        hidden: wiz.stepWizard(reviewed({queue: d.busy_waiting}), {type: "launch-start"})
          .asks.length});
    """, DATA, modules=MODULES)
    assert out["card"] == 1 and out["phase"] == "starting" and out["twice"] == 0
    ((ask_id, name, door, target, subject, body),) = out["asks"]
    assert re.fullmatch(r"write:launch:auth:auth-[a-z0-9]{8,32}-1:0", ask_id), ask_id
    assert (name, door, target, subject) == ("launch_authorize", "write", "automationAuthorize",
                                             "task-t1-r1")
    assert set(body) == {"authorization_id", "preview_digest", "authorized_by", "terms",
                         "supersedes"}
    assert body["authorized_by"] == "vasily" and body["supersedes"] is None
    assert body["preview_digest"] == "sha256:" + "d1ce5eed" * 8
    assert body["terms"] == out["terms"], "the terms the owner saw, byte for byte"
    assert body["authorization_id"] == ask_id.split(":")[3]
    assert out["blocked"] == 0 and out["hidden"] == 0, "a hidden or closed button sends nothing"


def test_a_grant_that_replaces_another_names_it_and_the_enqueue_body_is_the_queue_write_start():
    out = run_js(LAUNCH + """
      const grant = {...fresh(d.auto_holder), run_id: runId};
      const replacing = reviewed({automation: grant});
      const start = wiz.stepWizard(replacing, {type: "launch-start"});
      const queued = wiz.stepWizard(reviewed({queue: d.busy_waiting}), {type: "launch-enqueue"});
      show({supersedes: start.asks[0].body.supersedes,
        enqueue: queued.asks.map((ask) => [ask.id, ask.name, ask.target, ask.subject, ask.body]),
        phase: queued.state.launch.phase});
    """, DATA, modules=MODULES)
    assert out["supersedes"] == "auth-holder-1"
    ((ask_id, name, target, subject, body),) = out["enqueue"]
    assert re.fullmatch(r"write:launch:queue:auth-[a-z0-9]{8,32}-1:0", ask_id), ask_id
    assert (name, target, subject) == ("launch_enqueue", "queue", None)
    assert set(body) == {"run_id", "start"} and body["run_id"] == "task-t1-r1"
    assert set(body["start"]) == {"authorization_id", "preview_digest", "terms", "authorized_by",
                                  "supersedes"}
    assert body["start"]["authorized_by"] == "vasily" and out["phase"] == "enqueuing"


def test_the_countdown_is_the_time_to_valid_until_and_never_more_than_three_hundred_seconds():
    out = run_js(LAUNCH + """
      const at = (now) => wiz.launchFacts(reviewed({clock: now})).countdown;
      show({early: at("2026-09-29T10:00:30Z"), last: at("2026-09-29T10:04:59Z"),
        zero: at("2026-09-29T10:05:00Z"), late: at("2026-09-29T10:09:00Z"),
        before: at("2026-09-29T09:00:00Z"), unread_clock: wiz.launchFacts(reviewed()).countdown,
        garbage: wiz.launchFacts(wiz.reduceWizard(reviewed(), {type: "tick", now: "soon"}))
          .countdown});
    """, DATA, modules=MODULES)
    assert out["early"] == {"seconds": 270, "until": "2026-09-29T10:05:00Z"}
    assert out["last"]["seconds"] == 1 and out["zero"]["seconds"] == 0
    assert out["late"]["seconds"] == 0
    assert out["before"]["seconds"] == 300, "a clock behind the server's is not a longer window"
    assert out["unread_clock"] is None and out["garbage"] is None


def test_at_zero_the_preview_is_asked_again_with_the_same_body_and_the_same_digest_keeps_the_card():
    out = run_js(LAUNCH + """
      const state = reviewed({clock: "2026-09-29T10:05:00Z"});
      const due = asksOf(state).filter((ask) => ask.name === "launch_preview");
      const held = state.launch.card;
      const same = fresh(d.preview);
      same.previewed_at = "2026-09-29T10:05:00Z";
      same.valid_until = "2026-09-29T10:10:00Z";
      const after = wiz.stepWizard(state, {type: "answered", ask: due[0], result: ok(same)});
      show({due: due.map((ask) => [ask.id, ask.name, ask.target, ask.subject, ask.body]),
        early: asksOf(reviewed({clock: CLOCK})).filter((ask) => ask.name === "launch_preview")
          .length,
        card: [held, after.state.launch.card], seen: after.state.launch.seen,
        repeats: after.state.launch.repeats, changed: after.state.launch.changed,
        countdown: wiz.launchFacts(wiz.reduceWizard(after.state, {type: "tick",
          now: "2026-09-29T10:05:10Z"})).countdown, next: asksOf(after.state).length});
    """, DATA, modules=MODULES)
    assert out["due"] == [["write:launch:preview:0", "launch_preview", "automationPreview",
                           "task-t1-r1", {}]]
    assert out["early"] == 0
    assert out["card"] == [1, 1] and out["seen"] is True and out["repeats"] == 1
    assert out["changed"] == [] and out["next"] == 0
    assert out["countdown"] == {"seconds": 290, "until": "2026-09-29T10:10:00Z"}


def test_another_digest_replaces_the_card_marks_what_changed_and_waits_for_the_owner():
    out = run_js(LAUNCH + """
      const state = reviewed({clock: "2026-09-29T10:05:00Z"});
      const due = asksOf(state).find((ask) => ask.name === "launch_preview");
      const next = fresh(d.preview);
      next.preview_digest = "sha256:" + "5ca1ab1e".repeat(8);
      next.terms.max_actions = 5;
      next.terms.source_prefix_digest = "sha256:" + "9".repeat(64);
      next.terms.instruction_bindings[0].content_digest = "sha256:" + "8".repeat(64);
      next.previewed_at = "2026-09-29T10:05:00Z";
      next.valid_until = "2026-09-29T10:10:00Z";
      const after = wiz.stepWizard(state, {type: "answered", ask: due, result: ok(next)}).state;
      const facts = wiz.launchFacts(after);
      const looked = wiz.reduceWizard(after, {type: "launch-seen"});
      show({card: after.launch.card, changed: after.launch.changed, seen: after.launch.seen,
        start: facts.controls.start, actions: facts.card.actions,
        id_before: wiz.stepWizard(state, {type: "launch-start"}).asks[0].id,
        after_seen: wiz.launchFacts(looked).controls.start,
        id_after: wiz.stepWizard(looked, {type: "launch-start"}).asks[0].id,
        seen_twice: wiz.reduceWizard(looked, {type: "launch-seen"}) === looked});
    """, DATA, modules=MODULES)
    assert out["card"] == 2 and out["seen"] is False
    assert out["changed"] == ["actions", "receives"]
    assert out["actions"] == {"max": 5, "of": 8}
    assert out["start"] == {"shown": True, "blocked": "card_changed"}
    assert out["after_seen"] == {"shown": True, "blocked": None}
    assert out["id_before"].split(":")[3].endswith("-1")
    assert out["id_after"].split(":")[3].endswith("-2"), "a new card is a new authorization id"
    assert out["seen_twice"] is True


def test_six_repeats_in_a_row_stop_and_only_the_owners_refresh_asks_again():
    out = run_js(LAUNCH + """
      let state = reviewed({clock: "2026-09-29T10:05:00Z"});
      const minute = (at) => `2026-09-29T10:${String(5 * (at + 1)).padStart(2, "0")}:00Z`;
      const seen = [];
      for (let at = 0; at < 8; at += 1) {
        const due = asksOf(state).find((ask) => ask.name === "launch_preview");
        seen.push(due ? due.id : null);
        if (!due) break;
        const reply = fresh(d.preview);
        reply.previewed_at = minute(at);
        reply.valid_until = minute(at + 1);
        state = wiz.stepWizard(state, {type: "answered", ask: due, result: ok(reply)}).state;
        state = wiz.reduceWizard(state, {type: "tick", now: minute(at + 1)});
      }
      const stopped = wiz.launchFacts(state);
      const asked = wiz.stepWizard(state, {type: "launch-refresh"});
      show({seen, repeats: state.launch.repeats, capped: stopped.repeatsSpent,
        refresh: asked.asks.map((ask) => ask.id), after: asked.state.launch.repeats});
    """, DATA, modules=MODULES)
    assert out["seen"][:6] == [f"write:launch:preview:{n}" for n in range(6)]
    assert out["seen"][6] is None and out["repeats"] == 6 and out["capped"] is True
    assert out["refresh"] == ["write:launch:preview:6"] and out["after"] == 0


def test_the_answers_to_starting_and_to_queueing_are_said_and_a_lost_one_is_settled_by_reading():
    out = run_js(LAUNCH + """
      const send = (state, event) => wiz.stepWizard(state, event);
      const settled = (step, result) => wiz.stepWizard(step.state, {type: "answered",
        ask: step.asks[0], result});
      const ranStart = settled(send(reviewed(), {type: "launch-start"}),
        ok({authorization_id: "x"}));
      const queuedPayload = fresh(d.with_entries);
      queuedPayload.entries.push({run_id: runId, task_id: "task-t1", title: "Fix login",
        position: 3, kind: "start", state: "preauthorized", reason_code: "slot_busy",
        preauthorization: {authorized_by: "vasily", digest: "sha256:" + "d1ce5eed".repeat(8)}});
      const ranQueue = settled(send(reviewed({queue: d.busy_waiting}), {type: "launch-enqueue"}),
        ok(queuedPayload));
      show({started: [ranStart.state.launch.phase, ranStart.state.launch.result,
          wiz.wizardExit(ranStart.state)],
        queued: [ranQueue.state.launch.phase, ranQueue.state.launch.result,
          wiz.wizardExit(ranQueue.state)]});
    """, DATA, modules=MODULES)
    assert out["started"] == ["started", {"kind": "started"},
                              {"runId": "task-t1-r1", "stage": "started"}]
    assert out["queued"] == ["queued", {"kind": "queued", "position": 3},
                             {"runId": "task-t1-r1", "stage": "queued"}]


@pytest.mark.parametrize("code,detail,expect", [
    ("slot_busy", {"run_id": "task-a-r1"}, {"note": "slot_busy", "holder": "task-a-r1"}),
    ("preview_stale", {}, {"note": "stale"}),
    ("project_not_active", {}, {"note": "project_not_active"}),
    ("authorization_refused", {}, {"refusal": "authorization_refused"}),
    ("queue_full", {}, {"refusal": "queue_full"}),
    ("queue_not_ready", {}, {"refusal": "queue_not_ready"}),
    ("server_stopping", {}, {"refusal": "server_stopping"}),
    ("contract_invalid", {}, {"refusal": "contract_invalid"}),
    ("something_new", {}, {"refusal": "something_new"})])
def test_each_refusal_of_starting_is_told_apart_and_the_owner_presses_again_never_the_desk(
        code, detail, expect):
    out = run_js(LAUNCH + """
      const wire = {error: {code: d.code, message: d.code, detail: d.detail}};
      const start = wiz.stepWizard(reviewed(), {type: "launch-start"});
      const after = wiz.stepWizard(start.state, {type: "answered", ask: start.asks[0],
        result: refused(d.code, wire)});
      const launch = after.state.launch;
      show({phase: launch.phase, note: launch.note, refusal: launch.refusal,
        asks: after.asks.map((ask) => ask.name), start_id: start.asks[0].id});
    """, {**DATA, "code": code, "detail": detail}, modules=MODULES)
    assert out["phase"] == "review", "a refusal never starts a second write on its own"
    assert not [name for name in out["asks"] if name in ("launch_authorize", "launch_enqueue")]
    if "note" in expect:
        assert out["note"]["kind"] == expect["note"] and out["refusal"] is None
        assert out["note"].get("holder") == expect.get("holder")
    else:
        assert out["refusal"]["code"] == expect["refusal"] and out["note"] is None
    if code == "slot_busy":
        assert out["asks"] == ["launch_queue", "launch_automation"], "the slot is read again"
    if code == "preview_stale":
        assert out["asks"] == ["launch_preview"], "the preview is repeated; the owner presses again"


def test_a_lost_start_is_unknown_and_only_the_reads_settle_it_by_ids_and_terms():
    out = run_js(LAUNCH + """
      const start = wiz.stepWizard(reviewed(), {type: "launch-start"});
      const authId = start.asks[0].body.authorization_id;
      const unknown = wiz.stepWizard(start.state, {type: "answered", ask: start.asks[0],
        result: lost});
      const grant = {...fresh(d.auto_holder), run_id: runId};
      grant.authorization = {...grant.authorization, authorization_id: authId,
        authorized_by: "vasily", terms: undefined};
      const terms = fresh(d.preview).terms;
      const written = {...grant, authorization: {...grant.authorization, ...terms,
        authorization_id: authId, authorized_by: "vasily", supersedes: null}};
      delete written.authorization.duration_seconds;
      const settle = (automation) => {
        let now = wiz.stepWizard(unknown.state, {type: "answered", ask: unknown.asks
          .find((ask) => ask.name === "launch_queue"), result: ok(fresh(d.free))}).state;
        now = wiz.stepWizard(now, {type: "answered", ask: wiz.wantedAsks(now)
          .find((ask) => ask.name === "launch_automation"), result: ok(automation)}).state;
        return [now.launch.phase, now.launch.result, now.launch.note];
      };
      const other = {...written, authorization: {...written.authorization,
        max_actions: 999}};
      const slotRead = wiz.stepWizard(unknown.state, {type: "answered", ask: unknown.asks
        .find((ask) => ask.name === "launch_queue"), result: ok(fresh(d.free))}).state;
      show({phase: unknown.state.launch.phase, asks: unknown.asks.map((ask) => ask.name),
        landed: settle(written), none: settle(fresh(d.auto_new)), different: settle(other),
        just_lost: buttons(unknown.state), slot_read: buttons(slotRead)});
    """, DATA, modules=MODULES)
    assert out["phase"] == "unknown"
    assert out["asks"] == ["launch_queue", "launch_automation"]
    assert out["landed"][:2] == ["started", {"kind": "started"}]
    assert out["none"][0] == "review" and out["none"][2]["kind"] == "not_written"
    assert out["different"][0] == "review" and out["different"][2]["kind"] == "not_written"
    assert out["just_lost"]["start"] == [False, None], "nothing is pressed while the slot is read"
    assert out["just_lost"]["why"] == "slot_reading"
    assert out["slot_read"]["start"] == [True, "busy"], "the outcome is unknown: shown, held"


def test_a_lost_enqueue_is_settled_by_the_entry_the_queue_holds_for_this_run_and_this_digest():
    out = run_js(LAUNCH + """
      const begun = wiz.stepWizard(reviewed({queue: d.busy_waiting}), {type: "launch-enqueue"});
      const unknown = wiz.stepWizard(begun.state, {type: "answered", ask: begun.asks[0],
        result: lost});
      const entry = {run_id: runId, task_id: "task-t1", title: "Fix login", position: 1,
        kind: "start", enqueued_at: "2026-09-29T10:01:00Z", enqueued_by: "vasily",
        state: "preauthorized", reason_code: "slot_busy", state_since: "2026-09-29T10:01:00Z",
        preauthorization: {authorized_by: "vasily", preauthorized_at: "2026-09-29T10:01:00Z",
          digest: "sha256:" + "d1ce5eed".repeat(8)}};
      const settle = (entries) => {
        let now = wiz.stepWizard(unknown.state, {type: "answered", ask: unknown.asks
          .find((ask) => ask.name === "launch_queue"),
          result: ok({...fresh(d.busy_waiting), entries})}).state;
        now = wiz.stepWizard(now, {type: "answered", ask: wiz.wantedAsks(now)
          .find((ask) => ask.name === "launch_automation"),
          result: ok(fresh(d.auto_new))}).state;
        return [now.launch.phase, now.launch.result, now.launch.note?.kind ?? null];
      };
      const otherDigest = {...entry, preauthorization: {...entry.preauthorization,
        digest: "sha256:" + "1".repeat(64)}};
      show({landed: settle([entry]), absent: settle([]), stale: settle([otherDigest])});
    """, DATA, modules=MODULES)
    assert out["landed"] == ["queued", {"kind": "queued", "position": 1}, None]
    assert out["absent"] == ["review", None, "not_written"]
    assert out["stale"] == ["review", None, "not_written"]


LOST = LAUNCH + """
//: A press whose answer was lost: the wizard as it stands then and the id of the card's grant.
const lostAt = (kind) => {
  const begun = kind === "start" ? wiz.stepWizard(reviewed(), {type: "launch-start"})
    : wiz.stepWizard(reviewed({queue: d.busy_waiting}), {type: "launch-enqueue"});
  const step = wiz.stepWizard(begun.state, {type: "answered", ask: begun.asks[0], result: lost});
  const body = begun.asks[0].body;
  return {state: step.state, id: (body.start ?? body).authorization_id};
};
const bad = refused("store_error");
const both = (state, queue, automation) => say(say(state, "launch_queue", queue).state,
  "launch_automation", automation).state;
const standing = (id) => {
  const {duration_seconds: _window, ...terms} = fresh(d.preview).terms;
  const grant = fresh(d.auto_holder);
  return {...grant, run_id: runId, authorization: {...grant.authorization, ...terms,
    authorization_id: id, authorized_by: "vasily", supersedes: null}};
};
const entered = () => ({...fresh(d.busy_waiting), entries: [{run_id: runId, task_id: "task-t1",
  title: "Fix login", position: 1, kind: "start", state: "preauthorized",
  reason_code: "slot_busy", preauthorization: {authorized_by: "vasily",
    digest: "sha256:" + "d1ce5eed".repeat(8)}}]});
const seen = (state) => {
  const facts = wiz.launchFacts(state);
  return {phase: facts.phase, note: facts.note, result: facts.result, unread: facts.lostUnread,
    start: [facts.controls.start.shown, facts.controls.start.blocked], why: facts.controls.why};
};
"""


def test_a_lost_start_stays_unknown_while_the_automation_read_that_decides_it_has_failed():
    out = run_js(LOST + """
      const lostStart = lostAt("start");
      const none = both(lostStart.state, ok(fresh(d.free)), ok(fresh(d.auto_new)));
      const wholly = both(lostStart.state, bad, bad);
      const decides = both(lostStart.state, ok(fresh(d.free)), bad);
      const unrelated = both(lostStart.state, bad, ok(fresh(d.auto_new)));
      const reread = wiz.stepWizard(decides, {type: "launch-reread"});
      const settled = (automation) => seen(both(reread.state, ok(fresh(d.free)), automation));
      show({none: seen(none), wholly: seen(wholly), decides: seen(decides),
        unrelated: seen(unrelated), out: wiz.reduceWizard(lostStart.state,
          {type: "launch-reread"}) === lostStart.state,
        reread: reread.asks.map((ask) => [ask.name, ask.id]),
        landed: settled(ok(standing(lostStart.id))), absent: settled(ok(fresh(d.auto_new))),
        failed_again: seen(both(reread.state, ok(fresh(d.free)), bad))});
    """, DATA, modules=MODULES)
    assert out["none"]["phase"] == "review" and out["none"]["note"] == {"kind": "not_written"}
    unknown = {"phase": "unknown", "note": None, "result": None, "unread": True}
    assert out["wholly"] == {**unknown, "start": [False, None], "why": "slot_unread"}
    assert out["decides"] == {**unknown, "start": [True, "lost_unread"], "why": None}
    assert out["failed_again"] == out["decides"], "a second failed read keeps it open"
    assert out["unrelated"]["phase"] == "review", "the queue read does not decide a start"
    assert out["unrelated"]["note"] == {"kind": "not_written"}
    assert out["out"] is True, "nothing is read again while a read is still out"
    assert out["reread"] == [["launch_queue", "read:launch:queue:2"],
                             ["launch_automation", "read:launch:automation:2"]]
    assert (out["landed"]["phase"], out["landed"]["result"]) == ("started", {"kind": "started"})
    assert (out["absent"]["phase"], out["absent"]["note"]) == ("review", {"kind": "not_written"})


def test_a_lost_enqueue_stays_unknown_while_the_queue_read_that_decides_it_has_failed():
    out = run_js(LOST + """
      const lostEnqueue = lostAt("enqueue");
      const decides = both(lostEnqueue.state, bad, ok(fresh(d.auto_new)));
      const unrelated = both(lostEnqueue.state, ok(fresh(d.busy_waiting)), bad);
      const reread = wiz.stepWizard(decides, {type: "launch-reread"});
      const landed = both(reread.state, ok(entered()), ok(fresh(d.auto_new)));
      show({decides: seen(decides), unrelated: seen(unrelated),
        reread: reread.asks.map((ask) => ask.name), landed: seen(landed),
        absent: seen(both(reread.state, ok(fresh(d.busy_waiting)), ok(fresh(d.auto_new))))});
    """, DATA, modules=MODULES)
    assert out["decides"] == {"phase": "unknown", "note": None, "result": None, "unread": True,
                              "start": [False, None], "why": "slot_unread"}
    assert out["unrelated"]["phase"] == "review", "the automation read does not decide an enqueue"
    assert out["unrelated"]["note"] == {"kind": "not_written"}
    assert out["reread"] == ["launch_queue", "launch_automation"]
    assert (out["landed"]["phase"], out["landed"]["result"]) == (
        "queued", {"kind": "queued", "position": 1})
    assert (out["absent"]["phase"], out["absent"]["note"]) == ("review", {"kind": "not_written"})


def test_the_stand_still_refresh_and_reread_are_the_owners_and_change_nothing_they_do_not_name():
    out = run_js(LAUNCH + """
      const state = reviewed({clock: CLOCK});
      const refreshed = wiz.stepWizard(state, {type: "launch-refresh"});
      const reread = wiz.stepWizard(state, {type: "launch-reread"});
      const idle = wiz.stepWizard(open(), {type: "launch-refresh"});
      show({refresh: refreshed.asks.map((ask) => ask.name),
        reread: reread.asks.map((ask) => ask.name), idle: idle.asks.length,
        tick_same: wiz.reduceWizard(state, {type: "tick", now: CLOCK}) === state});
    """, DATA, modules=MODULES)
    assert out["refresh"] == ["launch_preview"]
    assert out["reread"] == ["launch_queue", "launch_automation"]
    assert out["idle"] == 0 and out["tick_same"] is True


#: A refusal of the queue write (or of the start), and what the preparation read says after it.
REFUSED = LAUNCH + """
const refusedWith = (code, kind = "enqueue") => {
  const begun = kind === "start" ? wiz.stepWizard(reviewed(), {type: "launch-start"})
    : wiz.stepWizard(reviewed({queue: d.busy_waiting}), {type: "launch-enqueue"});
  const wire = {error: {code, message: code, detail: {}}};
  return wiz.stepWizard(begun.state, {type: "answered", ask: begun.asks[0],
    result: refused(code, wire)});
};
const afterRead = (step, result) => wiz.stepWizard(step.state, {type: "answered",
  ask: step.asks.find((ask) => ask.name === "launch_prep"), result});
const outcome = (state) => {
  const facts = wiz.launchFacts(state);
  return {exit: wiz.wizardExit(state), check: facts.check, refusal: facts.refusal,
    phase: facts.phase};
};
"""


def test_queue_full_and_queue_not_ready_ask_the_preparation_of_the_task_and_no_other_refusal_does():
    out = run_js(REFUSED + """
      const asked = (code, kind) => refusedWith(code, kind).asks
        .filter((ask) => ask.name === "launch_prep")
        .map((ask) => [ask.id, ask.door, ask.target, ask.subject, ask.body]);
      const others = ["slot_busy", "preview_stale", "project_not_active", "authorization_refused",
        "server_stopping", "contract_invalid", "something_new"];
      show({full: asked("queue_full"), not_ready: asked("queue_not_ready"),
        start: asked("queue_not_ready", "start"),
        others: others.map((code) => asked(code)).flat(),
        reading: wiz.launchFacts(refusedWith("queue_full").state).check,
        quiet: wiz.launchFacts(refusedWith("slot_busy").state).check});
    """, DATA, modules=MODULES)
    read = [["read:launch:prep:1", "read", "preparation", "task-t1", None]]
    assert out["full"] == out["not_ready"] == out["start"] == read
    assert out["others"] == [], "only these two refusals are explained by the preparation"
    assert out["reading"] == {"status": "reading"} and out["quiet"] is None


def test_a_run_the_preparation_lists_past_step_six_lets_the_wizard_leave_and_any_other_is_said():
    out = run_js(REFUSED + """
      const after = (code, payload, result = ok(payload)) => outcome(
        afterRead(refusedWith(code), result).state);
      const prepared = fresh(d.prep_ready);
      show({queued: after("queue_not_ready", fresh(d.prep_queued)),
        authorized: after("queue_not_ready", fresh(d.prep_authorized)),
        ended: after("queue_full", fresh(d.prep_ended)),
        ready: after("queue_not_ready", prepared),
        missing: after("queue_not_ready", fresh(d.prep_documents_missing)),
        unlisted: after("queue_not_ready", {...prepared, runs: []}),
        other_task: after("queue_not_ready", {...prepared,
          task: {...prepared.task, task_id: "x"}}),
        refused: after("queue_not_ready", null, refused("service_refused")),
        lost: after("queue_not_ready", null, lost),
        unreadable: after("queue_not_ready", {runs: "none"})});
    """, DATA, modules=MODULES)
    for name, stage in (("queued", "queued"), ("authorized", "authorized"), ("ended", "ended")):
        row = out[name]
        assert row["exit"] == {"runId": "task-t1-r1", "stage": stage}, name
        assert row["check"] == {"status": "ok", "listed": True, "stage": stage}, name
        assert row["refusal"]["code"] in ("queue_not_ready", "queue_full"), name
        assert row["phase"] == "review", name
    for name, stage in (("ready", "ready_to_preview"), ("missing", "documents_missing")):
        assert out[name]["exit"] is None, name
        assert out[name]["check"] == {"status": "ok", "listed": True, "stage": stage}, name
    assert out["unlisted"]["exit"] is None
    assert out["unlisted"]["check"] == {"status": "ok", "listed": False, "stage": None}
    for name, code in (("other_task", "answer_unreadable"), ("refused", "service_refused"),
                       ("lost", "unknown"), ("unreadable", "answer_unreadable")):
        assert out[name]["exit"] is None, name
        assert out[name]["check"] == {"status": "failed", "code": code}, name


def test_a_second_refusal_reads_again_under_a_new_id_and_pressing_again_forgets_the_read():
    out = run_js(REFUSED + """
      const first = refusedWith("queue_not_ready");
      const read = afterRead(first, ok(fresh(d.prep_ready)));
      const pressed = wiz.stepWizard(read.state, {type: "launch-enqueue"});
      const wire = {error: {code: "queue_not_ready", message: "x", detail: {}}};
      const again = wiz.stepWizard(pressed.state, {type: "answered", ask: pressed.asks[0],
        result: refused("queue_not_ready", wire)});
      const outstanding = refusedWith("queue_full");
      const soon = wiz.stepWizard(outstanding.state, {type: "launch-enqueue"});
      const late = wiz.stepWizard(soon.state, {type: "answered", ask: outstanding.asks[0],
        result: ok(fresh(d.prep_authorized))});
      const prepIds = (step) => step.asks.filter((ask) => ask.name === "launch_prep")
        .map((ask) => ask.id);
      show({first: prepIds(first), pressed: wiz.launchFacts(pressed.state).check,
        second: prepIds(again), soon: wiz.launchFacts(soon.state).check,
        late: outcome(late.state)});
    """, DATA, modules=MODULES)
    assert out["first"] == ["read:launch:prep:1"] and out["second"] == ["read:launch:prep:2"]
    assert out["pressed"] is None, "a reason is about the last thing tried"
    assert out["soon"] is None
    assert out["late"]["exit"] is None and out["late"]["check"] is None, \
        "an answer nobody waits for changes nothing"
