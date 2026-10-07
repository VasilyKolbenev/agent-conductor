"""Step 6 as the owner reaches it and leaves it: the gate from step 5, and what the card knows.

The card's own rules (the preview, the slot, the countdown, the writes) are
`tests/test_desk_wizard_launch.py`. These are the seams around it that the drawing of step 6
stands on: the sixth step is built and is opened only from a prepared run, the slot's holder is
named and never guessed, and a queue entry in a project that is only being viewed keeps the wizard
open, because its closing line and the way to the flag are on the wizard's own screen.
"""
from __future__ import annotations

from tests.desk_wizard_node import run_js
from tests.test_desk_wizard_launch import DATA, LAUNCH, MODULES

RUN_STEP = LAUNCH + """
const toPrepare = (state) => wiz.reduceWizard(state, {type: "next"});
const gate = (state) => {
  const {ok, reason, step} = wiz.canAdvance(state);
  return {ok, reason, step, at: state.step};
};
const rowOf = (state, step) => wiz.stepStates(state).find((row) => row.step === step);
"""


def test_the_run_step_opens_only_from_a_prepared_run_and_closes_again_after_an_edit():
    out = run_js(RUN_STEP + """
      const fresh4 = toPrepare(ready());
      const prepared = toPrepare(reviewed());
      const edited = wiz.reduceWizard(prepared, {type: "edit-brief", value: "Something else."});
      const onRun = wiz.reduceWizard(prepared, {type: "next"});
      show({built: wiz.BUILT_STEPS, before: gate(fresh4), after: gate(prepared),
        edited: gate(edited), moved_before: wiz.reduceWizard(fresh4, {type: "next"}).step,
        moved: onRun.step, back: wiz.reduceWizard(onRun, {type: "back"}).step,
        beyond: wiz.reduceWizard(onRun, {type: "next"}).step,
        rows_before: [rowOf(fresh4, "prepare"), rowOf(fresh4, "run")],
        rows_after: [rowOf(prepared, "prepare"), rowOf(prepared, "run")],
        rows_on: [rowOf(onRun, "prepare"), rowOf(onRun, "run")],
        goto_early: wiz.reduceWizard(fresh4, {type: "goto", step: "run"}).step,
        goto_late: wiz.reduceWizard(prepared, {type: "goto", step: "run"}).step});
    """, DATA, modules=MODULES)
    assert out["built"] == ["task", "materials", "cycle", "roles", "prepare", "run"]
    assert out["before"] == {"ok": False, "reason": "prepare_not_done", "step": "prepare",
                             "at": "prepare"}
    assert out["after"] == {"ok": True, "reason": None, "step": "prepare", "at": "prepare"}
    assert out["edited"]["reason"] == "prepare_not_done", "an edit past the preview undoes it"
    assert (out["moved_before"], out["moved"], out["back"], out["beyond"]) == (
        "prepare", "run", "prepare", "run")
    assert [row["status"] for row in out["rows_before"]] == ["current", "blocked"]
    assert out["rows_before"][1]["reason"] == "prepare_not_done"
    assert [row["status"] for row in out["rows_after"]] == ["current", "ready"]
    assert [row["status"] for row in out["rows_on"]] == ["done", "current"]
    assert (out["goto_early"], out["goto_late"]) == ("prepare", "run")


def test_an_explanation_behind_an_info_mark_is_open_in_the_model_so_a_redraw_keeps_it_open():
    out = run_js(RUN_STEP + """
      const state = reviewed();
      const toggle = (now, name) => wiz.reduceWizard(now, {type: "launch-info", name});
      const once = toggle(state, "time"), both = toggle(once, "input:artifact-brief");
      const closed = toggle(both, "time");
      const ticked = wiz.reduceWizard(both, {type: "tick", now: CLOCK});
      show({start: wiz.launchFacts(state).infos, once: wiz.launchFacts(once).infos,
        both: wiz.launchFacts(both).infos, closed: wiz.launchFacts(closed).infos,
        ticked: wiz.launchFacts(ticked).infos,
        refused: ["", "Time", "a b", "x".repeat(200), null, 4, "instruction:", "input:"]
          .map((name) => toggle(state, name) === state),
        run_id: wiz.launchFacts(state).runId});
    """, DATA, modules=MODULES)
    assert out["start"] == [] and out["once"] == ["time"]
    assert out["both"] == ["time", "input:artifact-brief"]
    assert out["closed"] == ["input:artifact-brief"] and out["ticked"] == out["both"]
    assert out["refused"] == [True] * 8, "only a name the card draws can be opened"
    assert out["run_id"] == "task-t1-r1"


def test_the_slot_holder_is_named_by_its_run_and_its_task_is_looked_up_never_guessed():
    out = run_js(RUN_STEP + """
      const told = (holder) => {
        const begun = wiz.stepWizard(reviewed({queue: d.free}), {type: "launch-start"});
        const wire = {error: {code: "slot_busy", message: "busy", detail: {run_id: holder}}};
        const after = wiz.stepWizard(begun.state, {type: "answered", ask: begun.asks[0],
          result: refused("slot_busy", wire)});
        return wiz.launchFacts(after.state).note;
      };
      const holderOf = (queue) => wiz.launchFacts(reviewed({queue})).controls.holder;
      show({known: told("task-a-r1"), unlisted: told("task-zz-r1"), unnamed: told(undefined),
        busy: holderOf(d.busy_running), stuck: holderOf(d.stuck), free: holderOf(d.free),
        view: holderOf(d.view)});
    """, DATA, modules=MODULES)
    assert out["known"] == {"kind": "slot_busy", "holder": "task-a-r1",
                            "holderTitle": "Add a search box"}
    assert out["unlisted"] == {"kind": "slot_busy", "holder": "task-zz-r1", "holderTitle": None}
    assert out["unnamed"] == {"kind": "slot_busy", "holder": None, "holderTitle": None}
    assert (out["busy"], out["stuck"]) == ("task-a-r1", "task-a-r1")
    assert (out["free"], out["view"]) == (None, None)


def test_a_queue_entry_in_a_viewed_project_keeps_the_wizard_open_and_others_hand_it_back():
    out = run_js(RUN_STEP + """
      const entries = fresh(d.with_entries);
      entries.entries.push({run_id: runId, task_id: "task-t1", title: "Fix login", position: 3,
        kind: "start", state: "preauthorized", reason_code: "slot_busy",
        preauthorization: {authorized_by: "vasily", digest: "sha256:" + "d1ce5eed".repeat(8)}});
      const queued = (queue) => {
        const begun = wiz.stepWizard(reviewed({queue}), {type: "launch-enqueue"});
        return wiz.stepWizard(begun.state, {type: "answered", ask: begun.asks[0],
          result: ok(entries)}).state;
      };
      const inView = queued(d.view), inBusy = queued(d.busy_waiting);
      const starting = wiz.stepWizard(reviewed({queue: d.free}), {type: "launch-start"});
      const begun = wiz.stepWizard(starting.state, {type: "answered", ask: starting.asks[0],
        result: ok({authorization_id: "x"})}).state;
      const viewing = (queue) => wiz.launchFacts(reviewed({queue})).viewing;
      show({viewing: [viewing(d.view), viewing(d.free), viewing(d.busy_waiting), viewing(d.stuck)],
        in_view: [wiz.launchFacts(inView).result, wiz.launchFacts(inView).viewing,
          wiz.wizardExit(inView)],
        in_busy: [wiz.launchFacts(inBusy).result, wiz.wizardExit(inBusy)],
        started: wiz.wizardExit(begun)});
    """, DATA, modules=MODULES)
    assert out["viewing"] == [True, False, False, False]
    assert out["in_view"] == [{"kind": "queued", "position": 3}, True, None]
    assert out["in_busy"] == [{"kind": "queued", "position": 3},
                              {"runId": "task-t1-r1", "stage": "queued"}]
    assert out["started"] == {"runId": "task-t1-r1", "stage": "started"}
