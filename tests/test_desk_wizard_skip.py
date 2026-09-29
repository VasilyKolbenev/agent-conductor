"""«Пропустить вперёд» from the card, as the wizard's model does it (spec 6.4.5, 4.4.8).

One press is the spec's three steps, each idempotent, and the third is two writes: the new run is
queued with this card's authorization, put first, the holder is paused, and its own resume is
queued behind. What is done is never remembered: after every answer (and after a lost one) the
queue, this run's automation and the holder's automation are read again, and the next step is the
first one those reads say is not done. A stand-in server with a memory (`skipWorld`) applies each
write to a queue and a holder, so what the tests read back is what a server would hold.
"""
from __future__ import annotations

from tests.desk_wizard_node import run_js
from tests.test_desk_wizard_launch import DATA, LAUNCH, MODULES

SKIP = LAUNCH + """
const entryOf = (run, kind, digest) => ({run_id: run, task_id: run.split("-r")[0], title: run,
  position: 0, kind, state: "preauthorized", reason_code: "behind",
  preauthorization: {authorized_by: "vasily", digest}});
const renumber = (w) => w.queue.entries.forEach((row, at) => { row.position = at + 1; });
const changedWire = {error: {code: "queue_changed", message: "changed", detail: {}}};
//: A server that remembers: the slot's queue, the holder's automation, what was written and how
//: often, and what it will lose (answered unknown though it landed) or drop (never landed).
const skipWorld = (over = {}) => ({queue: structuredClone(over.queue ?? d.with_entries),
  holder: structuredClone(over.holder ?? d.auto_holder), log: [], asked: [], writes: {},
  lose: {...over.lose}, drop: {...over.drop}, changed: over.changed ?? 0,
  refuse: {...over.refuse}});
const serve = (w, ask) => {
  const key = ask.name;
  w.log.push(key);
  w.asked.push(ask);
  w.writes[key] = (w.writes[key] ?? 0) + 1;
  if ((w.drop[key] ?? 0) > 0) { w.drop[key] -= 1; return lost; }
  if (w.refuse[key]) return refused(w.refuse[key], null);
  const landed = (payload) => {
    if ((w.lose[key] ?? 0) > 0) { w.lose[key] -= 1; return lost; }
    return ok(payload);
  };
  if (key === "launch_queue") return ok(structuredClone(w.queue));
  if (key === "launch_holder") return ok(structuredClone(w.holder));
  if (key === "launch_automation") return ok(structuredClone(moved(d.auto_new)));
  if (key === "launch_run") return ok(structuredClone(moved(d.run_detail)));
  if (key === "launch_preview") return ok(structuredClone(moved(d.preview)));
  if (key === "launch_skip_enqueue") {
    if (!w.queue.entries.some((row) => row.run_id === ask.body.run_id)) {
      w.queue.entries.push(entryOf(ask.body.run_id, "start", ask.body.start.preview_digest));
      renumber(w);
      w.queue.revision += 1;
    }
    return landed(structuredClone(w.queue));
  }
  if (key === "launch_skip_order") {
    const stale = w.changed > 0 || ask.body.expected_revision !== w.queue.revision;
    if (w.changed > 0) w.changed -= 1;
    if (stale) { w.queue.revision += 1; return refused("queue_changed", changedWire); }
    w.queue.entries.sort((a, b) => ask.body.run_ids.indexOf(a.run_id)
      - ask.body.run_ids.indexOf(b.run_id));
    renumber(w);
    w.queue.revision += 1;
    return landed(structuredClone(w.queue));
  }
  if (key === "launch_skip_pause") {
    w.holder.control = {control_id: ask.body.control_id, action: "pause"};
    w.holder.state = "paused";
    return landed(structuredClone(w.holder));
  }
  if (key === "launch_skip_resume") {
    w.queue.entries.push(entryOf(ask.body.run_id, "resume", ""));
    renumber(w);
    w.queue.revision += 1;
    return landed(structuredClone(w.queue));
  }
  throw new Error(`the stand-in server does not know ${key}`);
};
//: A wizard on the card of a busy slot whose holder waits for a human, the holder read answered.
const offered = (w, over = {}) => {
  const state = reviewed({queue: w.queue, ...over});
  return say(state, "launch_holder", ok(structuredClone(w.holder))).state;
};
//: Answer every ask the model makes, one at a time, from the stand-in server, until it is quiet.
const settle = (first, w, cap = 120) => {
  let state = first.state, pending = [...first.asks], guard = 0;
  while (pending.length > 0 && guard < cap) {
    guard += 1;
    const ask = pending.shift();
    const step = wiz.stepWizard(state, {type: "answered", ask, result: serve(w, ask)});
    state = step.state;
    pending.push(...step.asks);
  }
  return {state, world: w, rounds: guard};
};
const tap = (state, type) => wiz.stepWizard(state, {type});
const writesOf = (w) => w.log.filter((name) => name.startsWith("launch_skip_"));
const order = (w) => w.queue.entries.map((row) => [row.run_id, row.kind]);
"""

# The names the first press asks for, in the order the four steps are written.
STEPS = ["launch_skip_enqueue", "launch_skip_order", "launch_skip_pause", "launch_skip_resume"]
#: The queue the stand-in server starts with (two entries wait) and the new run, first of them.
WAITING = [["task-c-r1", "start"], ["task-d-r1", "start"]]
FIRST = [["task-t1-r1", "start"], *WAITING]


def test_the_holder_is_read_and_skip_ahead_is_offered_only_when_it_waits_for_a_human():
    out = run_js(SKIP + """
      const seenBy = (queue, holder = d.auto_holder) => {
        const state = reviewed({queue});
        const ask = asksOf(state).find((one) => one.name === "launch_holder");
        const after = ask ? say(state, "launch_holder", ok(structuredClone(holder))).state : state;
        return {asked: ask ? [ask.target, ask.subject, ask.door] : null,
          skip: wiz.launchFacts(after).controls.skip};
      };
      const running = structuredClone(d.auto_holder); running.state = "running";
      const noGrant = structuredClone(d.auto_holder); noGrant.authorization = null;
      const failed = say(reviewed({queue: d.busy_waiting}), "launch_holder", lost).state;
      const cold = reviewed({queue: d.busy_waiting});
      const unseen = wiz.launchFacts(say(cold, "launch_holder", ok(d.auto_holder)).state);
      show({waiting: seenBy(d.busy_waiting), running_slot: seenBy(d.busy_running),
        stuck: seenBy(d.stuck), free: seenBy(d.free), view: seenBy(d.view),
        holder_running: seenBy(d.busy_waiting, running), no_grant: seenBy(d.busy_waiting, noGrant),
        read_failed: wiz.launchFacts(failed).controls.skip,
        before_read: wiz.launchFacts(cold).controls.skip});
    """, DATA, modules=MODULES)
    assert out["waiting"] == {"asked": ["automation", "task-a-r1", "read"],
                              "skip": {"shown": True, "blocked": None}}
    for name in ("running_slot", "stuck", "free", "view"):
        assert out[name] == {"asked": None, "skip": {"shown": False, "blocked": None}}, name
    for name in ("holder_running", "no_grant"):
        assert out[name]["skip"] == {"shown": False, "blocked": None}, name
    assert out["read_failed"] == {"shown": False, "blocked": None}
    assert out["before_read"] == {"shown": False, "blocked": None}


def test_the_press_opens_a_dialog_that_names_the_holders_task_and_its_grants_end():
    out = run_js(SKIP + """
      const w = skipWorld(), state = offered(w);
      const dialog = tap(state, "launch-skip");
      const facts = wiz.launchFacts(dialog.state);
      const cancelled = tap(dialog.state, "launch-skip-cancel").state;
      const early = tap(reviewed({queue: d.busy_waiting}), "launch-skip");
      const free = tap(reviewed({queue: d.free}), "launch-skip");
      show({dialog: facts.skip, phase: facts.phase, writes: dialog.asks.map((ask) => ask.name),
        buttons: [facts.controls.start.shown, facts.controls.enqueue.shown],
        after_cancel: wiz.launchFacts(cancelled).skip, refused_early: early.state.launch.skip,
        refused_free: free.state.launch.skip,
        twice: tap(dialog.state, "launch-skip").state === dialog.state});
    """, DATA, modules=MODULES)
    assert out["dialog"]["phase"] == "confirm"
    assert out["dialog"]["holder"] == {"runId": "task-a-r1", "title": "Add a search box",
                                       "expiresAt": "2026-09-29T13:00:00Z"}
    assert out["phase"] == "review" and out["writes"] == [], "the dialog writes nothing"
    assert out["after_cancel"] is None
    assert out["refused_early"] is None and out["refused_free"] is None
    assert out["twice"] is True


def test_one_press_writes_four_steps_in_order_with_ids_made_from_the_card():
    out = run_js(SKIP + """
      const w = skipWorld(), dialog = tap(offered(w), "launch-skip").state;
      const done = settle(tap(dialog, "launch-skip-confirm"), w);
      const facts = wiz.launchFacts(done.state);
      const bodies = Object.fromEntries(w.asked.filter((ask) => ask.name.startsWith("launch_skip_"))
        .map((ask) => [ask.name, [ask.target, ask.subject, ask.id, ask.body]]));
      show({writes: writesOf(w), order: order(w), holder: [w.holder.state, w.holder.control],
        phase: facts.phase, result: facts.result, skip: facts.skip && facts.skip.phase,
        exit: wiz.wizardExit(done.state), bodies});
    """, DATA, modules=MODULES)
    assert out["writes"] == STEPS
    assert out["order"] == [*FIRST, ["task-a-r1", "resume"]], "the new run first, the holder last"
    assert out["holder"][0] == "paused"
    assert out["holder"][1]["control_id"] == "pause-n0nce0001-1"
    assert (out["phase"], out["result"]) == ("queued", {"kind": "queued", "position": 1})
    assert out["skip"] == "done"
    assert out["exit"] == {"runId": "task-t1-r1", "stage": "queued"}
    enqueue, ordered, pause, resume = (out["bodies"][name] for name in STEPS)
    assert enqueue[0] == "queue" and enqueue[1] is None
    assert set(enqueue[3]) == {"run_id", "start"} and enqueue[3]["run_id"] == "task-t1-r1"
    assert set(enqueue[3]["start"]) == {"authorization_id", "preview_digest", "terms",
                                        "authorized_by", "supersedes"}
    assert enqueue[3]["start"]["authorization_id"] == "auth-n0nce0001-1"
    assert enqueue[2].startswith("write:launch:skip:enqueue:auth-n0nce0001-1:")
    assert ordered[0] == "queueOrder"
    assert ordered[3]["run_ids"] == ["task-t1-r1", "task-c-r1", "task-d-r1"]
    assert ordered[3]["expected_revision"] == 8, "the revision the last read of the queue said"
    assert pause[:2] == ["automationControl", "task-a-r1"]
    assert pause[3] == {"control_id": "pause-n0nce0001-1", "action": "pause", "actor": "vasily",
                        "authorization_id": "auth-holder-1", "expected_control_id": None,
                        "authorization_digest": DATA["auto_holder"]["authorization"][
                            "authorization_digest"]}
    assert resume[:2] == ["queue", None]
    assert resume[3] == {"run_id": "task-a-r1", "resume": {
        "control_id": "resume-n0nce0001-1", "authorization_id": "auth-holder-1",
        "authorization_digest": DATA["auto_holder"]["authorization"]["authorization_digest"],
        "expected_control_id": "pause-n0nce0001-1", "actor": "vasily"}}


def test_a_lost_answer_at_any_step_is_settled_by_the_reads_and_continues_from_that_step():
    out = run_js(SKIP + """
      const attempt = (over) => {
        const w = skipWorld(over), dialog = tap(offered(w), "launch-skip").state;
        const done = settle(tap(dialog, "launch-skip-confirm"), w);
        return {writes: w.writes, order: order(w), phase: done.state.launch.phase,
          paused: w.holder.state, control: w.holder.control && w.holder.control.control_id};
      };
      show({landed_at_pause: attempt({lose: {launch_skip_pause: 1}}),
        lost_at_pause: attempt({drop: {launch_skip_pause: 1}}),
        landed_at_enqueue: attempt({lose: {launch_skip_enqueue: 1}}),
        lost_at_order: attempt({drop: {launch_skip_order: 1}}),
        landed_at_resume: attempt({lose: {launch_skip_resume: 1}}),
        lost_at_resume: attempt({drop: {launch_skip_resume: 1}})});
    """, DATA, modules=MODULES)
    final = [*FIRST, ["task-a-r1", "resume"]]
    for name, again in (("landed_at_pause", None), ("lost_at_pause", "launch_skip_pause"),
                        ("landed_at_enqueue", None), ("lost_at_order", "launch_skip_order"),
                        ("landed_at_resume", None), ("lost_at_resume", "launch_skip_resume")):
        row = out[name]
        assert row["phase"] == "queued" and row["order"] == final, name
        writes = {key: row["writes"].get(key, 0) for key in STEPS}
        expected = {key: 1 for key in STEPS}
        if again is not None:
            expected[again] = 2
        assert writes == expected, (name, writes)
        assert row["paused"] == "paused"
    assert out["lost_at_pause"]["control"] == "pause-n0nce0001-1", "the same pause id is sent again"


def test_the_press_reads_first_and_writes_only_the_steps_those_reads_say_are_undone():
    out = run_js(SKIP + """
      const w = skipWorld(), dialog = tap(offered(w), "launch-skip").state;
      //: Between the dialog and the press another window did everything but the holder's resume,
      //: and the pump has already started the new run: its entry left the queue and its
      //: grant stands.
      w.holder.control = {control_id: "pause-n0nce0001-1", action: "pause"};
      w.holder.state = "paused";
      const grant = {...structuredClone(d.auto_holder.authorization), run_id: "task-t1-r1",
        authorization_id: "auth-n0nce0001-1", authorized_by: "vasily"};
      const automation = structuredClone(moved(d.auto_new));
      automation.authorization = grant;
      const answered = (ask) => (ask.name === "launch_automation" ? ok(automation)
        : serve(w, ask));
      let step = wiz.stepWizard(dialog, {type: "launch-skip-confirm"});
      const firstAsks = step.asks.map((ask) => ask.name);
      let state = step.state, pending = [...step.asks], guard = 0;
      while (pending.length > 0 && guard < 60) {
        guard += 1;
        const ask = pending.shift();
        step = wiz.stepWizard(state, {type: "answered", ask, result: answered(ask)});
        state = step.state; pending.push(...step.asks);
      }
      show({firstAsks, writes: writesOf(w), phase: state.launch.phase, result: state.launch.result,
        order: order(w)});
    """, DATA, modules=MODULES)
    assert sorted(out["firstAsks"]) == ["launch_automation", "launch_holder", "launch_queue"]
    assert out["writes"] == ["launch_skip_resume"], "no enqueue, no order, no second pause"
    assert (out["phase"], out["result"]) == ("started", {"kind": "started"})
    assert out["order"] == [*WAITING, ["task-a-r1", "resume"]]


def test_a_changed_queue_is_read_and_ordered_once_more_and_a_second_change_shows_the_queue():
    out = run_js(SKIP + """
      const attempt = (changes) => {
        const w = skipWorld({changed: changes}), dialog = tap(offered(w), "launch-skip").state;
        const done = settle(tap(dialog, "launch-skip-confirm"), w);
        const facts = wiz.launchFacts(done.state);
        return {writes: w.writes, phase: facts.phase, skip: facts.skip,
          order: order(w), holder: w.holder.state, note: facts.note,
          buttons: [facts.controls.start.shown, facts.controls.enqueue.shown]};
      };
      show({none: attempt(0), once: attempt(1), twice: attempt(2)});
    """, DATA, modules=MODULES)
    assert out["none"]["writes"]["launch_skip_order"] == 1
    assert out["once"]["writes"]["launch_skip_order"] == 2 and out["once"]["phase"] == "queued"
    twice = out["twice"]
    assert twice["writes"]["launch_skip_order"] == 2, "no third order"
    assert twice["phase"] == "review" and twice["skip"]["phase"] == "stopped"
    assert twice["skip"]["stop"] == {"code": "queue_changed", "step": "order"}
    assert [row["runId"] for row in twice["skip"]["queue"]] == [
        "task-c-r1", "task-d-r1", "task-t1-r1"], "the queue is shown as it stands, unordered"
    assert twice["holder"] == "waiting", "nothing paused the holder"
    assert "launch_skip_pause" not in twice["writes"]


def test_a_refusal_or_a_step_that_stays_undone_stops_with_what_stands_said():
    out = run_js(SKIP + """
      const attempt = (over) => {
        const w = skipWorld(over), dialog = tap(offered(w), "launch-skip").state;
        const done = settle(tap(dialog, "launch-skip-confirm"), w);
        const facts = wiz.launchFacts(done.state);
        return {writes: w.writes, phase: facts.phase, stop: facts.skip && facts.skip.stop,
          order: order(w), previewed: w.log.includes("launch_preview"),
          steps: facts.skip.steps.map((row) => row.done)};
      };
      show({pause_refused: attempt({refuse: {launch_skip_pause: "contract_invalid"}}),
        resume_refused: attempt({refuse: {launch_skip_resume: "queue_not_ready"}}),
        enqueue_refused: attempt({refuse: {launch_skip_enqueue: "queue_full"}}),
        stale: attempt({refuse: {launch_skip_enqueue: "preview_stale"}}),
        never_lands: attempt({drop: {launch_skip_pause: 9}})});
    """, DATA, modules=MODULES)
    assert out["pause_refused"]["stop"] == {"code": "contract_invalid", "step": "pause"}
    assert out["pause_refused"]["order"] == FIRST, "the new run stays first"
    assert out["resume_refused"]["stop"] == {"code": "queue_not_ready", "step": "resume"}
    assert out["enqueue_refused"]["stop"] == {"code": "queue_full", "step": "enqueue"}
    assert out["enqueue_refused"]["order"] == WAITING
    assert out["stale"]["stop"]["code"] == "preview_stale"
    assert out["stale"]["previewed"] is True, "the terms are read again, the owner presses again"
    assert out["never_lands"]["stop"] == {"code": "not_written", "step": "pause"}
    assert out["never_lands"]["writes"]["launch_skip_pause"] == 3, "three tries, then it stops"
    for name in ("pause_refused", "resume_refused", "enqueue_refused", "stale", "never_lands"):
        assert out[name]["phase"] == "review", name
    #: What stands when it stops is what the last consistent reads said, step by step.
    assert out["pause_refused"]["steps"] == [True, True, False, False]
    assert out["never_lands"]["steps"] == [True, True, False, False]
    assert out["resume_refused"]["steps"] == [True, True, True, False]
    assert out["enqueue_refused"]["steps"] == [False, False, False, False]
    assert out["stale"]["steps"] == [False, False, False, False]


def test_the_steps_are_unknown_while_a_read_is_out_and_all_done_when_the_press_ends():
    out = run_js(SKIP + """
      const rows = (state) => wiz.launchFacts(state).skip.steps.map((row) => row.done);
      const w = skipWorld(), begun = tap(tap(offered(w), "launch-skip").state,
        "launch-skip-confirm");
      const done = settle(begun, w);
      const w2 = skipWorld(), again = tap(tap(offered(w2), "launch-skip").state,
        "launch-skip-confirm");
      const asks = Object.fromEntries(again.asks.map((ask) => [ask.name, ask]));
      let state = again.state;
      const feed = (ask, result) => {
        state = wiz.stepWizard(state, {type: "answered", ask, result}).state;
      };
      feed(asks.launch_holder, serve(w2, asks.launch_holder));
      feed(asks.launch_automation, serve(w2, asks.launch_automation));
      const waiting = rows(state);
      feed(asks.launch_queue, lost);
      show({begun: rows(begun.state), done: rows(done.state), waiting, stop: state.launch.skip.stop,
        unreadable: rows(state), phase: state.launch.phase});
    """, DATA, modules=MODULES)
    assert out["begun"] == [None, None, None, None]
    assert out["waiting"] == [None, None, None, None], "one read is still out"
    assert out["done"] == [True, True, True, True]
    assert out["stop"] == {"code": "read_failed", "step": None}
    assert out["unreadable"] == [None, None, None, None], "nothing is claimed of a failed read"
    assert out["phase"] == "review"


def test_a_second_press_after_a_stopped_one_writes_again_under_the_same_ids():
    out = run_js(SKIP + """
      const w = skipWorld({refuse: {launch_skip_pause: "contract_invalid"}});
      const dialog = tap(offered(w), "launch-skip").state;
      const first = settle(tap(dialog, "launch-skip-confirm"), w);
      const stopped = wiz.launchFacts(first.state).skip.stop;
      w.refuse = {};
      const cancelled = settle(tap(first.state, "launch-skip-cancel"), w);
      const again = tap(cancelled.state, "launch-skip");
      const second = settle(tap(again.state, "launch-skip-confirm"), w);
      const pauses = w.asked.filter((ask) => ask.name === "launch_skip_pause");
      show({stopped, writes: w.writes, phase: second.state.launch.phase,
        control: w.holder.control && w.holder.control.control_id, order: order(w),
        bodies: pauses.map((ask) => ask.body.control_id),
        asks: pauses.map((ask) => ask.id)});
    """, DATA, modules=MODULES)
    assert out["stopped"] == {"code": "contract_invalid", "step": "pause"}
    assert out["writes"]["launch_skip_pause"] == 2, "the second press wrote the pause again"
    assert out["writes"]["launch_skip_enqueue"] == 1 and out["writes"]["launch_skip_order"] == 1
    assert out["bodies"] == ["pause-n0nce0001-1", "pause-n0nce0001-1"], "the same card, one id"
    assert len(set(out["asks"])) == 2, "each press is its own ask, so the model hands it out"
    assert out["control"] == "pause-n0nce0001-1"
    assert (out["phase"], out["order"]) == ("queued", [*FIRST, ["task-a-r1", "resume"]])


def test_the_owners_name_cannot_change_while_the_press_is_writing():
    out = run_js(SKIP + """
      const w = skipWorld(), dialog = tap(offered(w), "launch-skip").state;
      const running = tap(dialog, "launch-skip-confirm").state;
      const edit = (state, value) => wiz.reduceWizard(state, {type: "actor-edit", value});
      const before = edit(dialog, "ann");
      const during = edit(running, "mallory");
      const done = settle(tap(dialog, "launch-skip-confirm"), w);
      show({before: before.launch.actor, during: during.launch.actor,
        same: during === running, bodies: [...new Set(w.asked.filter((ask) => ask.body)
          .map((ask) => ask.body.actor ?? ask.body.start?.authorized_by
            ?? ask.body.resume?.actor).filter((who) => who))],
        phase: done.state.launch.phase});
    """, DATA, modules=MODULES)
    assert out["before"] == "ann", "a name may change while only the dialog is open"
    assert out["during"] == "vasily" and out["same"] is True
    assert out["bodies"] == ["vasily"] and out["phase"] == "queued"
