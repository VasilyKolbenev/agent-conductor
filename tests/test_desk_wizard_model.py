"""The wizard model's frame and step 1 ("Задача"), run as the real JavaScript module.

The model is pure, so every claim here is a value: a state in, a state and the asks
it made due out. What a browser draws from it is `browser_tests/test_desk_wizard.py`.
The later steps have their own files (`test_desk_wizard_materials.py`, `_cycle.py`,
`_roles.py`) so none of the four passes the line cap.
"""
from __future__ import annotations

from tests.desk_wizard_node import PRELUDE, run_js

RU_BRIEF = ("# Починить вход\n\n## Что нужно сделать\nВход не работает.\nНужно починить.\n\n"
            "## Как понять, что готово (подсказка)\nТесты проходят\n")
EN_BRIEF = ("# Fix login\n\n## What needs to be done\nMake it work.\n\n"
            "## How to tell it is done (hint)\nTests pass\n")


def test_the_wizard_has_six_steps_in_the_owner_order_and_this_build_covers_the_first_five():
    out = run_js(PRELUDE + """
      show({steps: wiz.STEPS, built: wiz.BUILT_STEPS,
        status: wiz.stepStates(open()).map((row) => [row.step, row.status]),
        frozen: [Object.isFrozen(wiz.STEPS), Object.isFrozen(wiz.BUILT_STEPS)]});
    """)
    assert out["steps"] == ["task", "materials", "cycle", "roles", "prepare", "run"]
    assert out["built"] == out["steps"][:5]
    assert out["status"] == [["task", "current"], ["materials", "blocked"], ["cycle", "blocked"],
                             ["roles", "blocked"], ["prepare", "blocked"], ["run", "later"]]
    assert out["frozen"] == [True, True]


def test_hash_starters_admit_only_the_starter_docs_and_wizard_cards_are_standard_and_short():
    out = run_js(PRELUDE + "show({hash: wiz.HASH_STARTERS, cards: wiz.WIZARD_STARTERS});")
    assert out == {"hash": ["desk-starter-docs"], "cards": ["desk-standard", "desk-short"]}


def test_a_starter_key_counts_only_with_new_task_and_a_known_starter():
    known = ["desk-starter-docs", "desk-standard", "desk-short"]
    out = run_js(PRELUDE + """
      const read = (keys, starters) => wiz.openingFrom(keys, starters).starterId;
      show({
        counts: read({new: "task", starter: "desk-starter-docs"}, d.known),
        no_new: read({new: null, starter: "desk-starter-docs"}, d.known),
        other_new: read({new: "run", starter: "desk-starter-docs"}, d.known),
        not_a_hash_starter: read({new: "task", starter: "desk-standard"}, d.known),
        not_in_the_read: read({new: "task", starter: "desk-starter-docs"}, ["desk-short"]),
        read_not_landed: read({new: "task", starter: "desk-starter-docs"}, null),
        nothing_named: read({new: "task"}, d.known),
      });
    """, {"known": known})
    assert out == {"counts": "desk-starter-docs", "no_new": None, "other_new": None,
                   "not_a_hash_starter": None, "not_in_the_read": None,
                   "read_not_landed": None, "nothing_named": None}


def test_a_new_wizard_prefills_no_field():
    out = run_js(PRELUDE + """
      const state = open();
      show({task: state.task, step: state.step, reads: state.reads, mode: state.mode,
        asked: state.asked, starter: open({starterId: "desk-starter-docs"}).task});
    """)
    assert out["task"] == {"taskId": "task-t1", "title": "", "brief": "", "hint": "",
                           "idea": "", "written": False}
    assert out["starter"] == out["task"]
    assert (out["step"], out["reads"], out["asked"]) == ("task", {}, [])
    assert out["mode"] == {"starterId": None, "view": False}


def test_a_wizard_needs_a_valid_task_id_from_its_caller():
    out = run_js(PRELUDE + """
      const refused = (id) => {
        try { open({newTaskId: id}); return false; } catch { return true; }
      };
      show(["", "bad id", "../x", "task-ok"].map(refused).concat(refused(undefined)));
    """)
    assert out == [True, True, True, False, True]


def test_the_task_step_is_ready_only_with_a_valid_title_and_a_brief():
    out = run_js(PRELUDE + """
      const why = (state) => wiz.canAdvance(state).reason;
      const edit = (title, brief) => run(open(), {type: "edit-title", value: title},
        {type: "edit-brief", value: brief});
      show({
        empty: why(open()), title_only: why(edit("Fix", "")),
        blank_brief: why(edit("Fix", "  \\n ")), brief_only: why(edit("", "Do it")),
        control_char: why(edit("Fix\\u0007", "Do it")),
        too_long: why(edit("x".repeat(201), "Do it")),
        exactly_at_the_limit: why(edit("x".repeat(200), "Do it")),
        over_the_byte_limit: why(edit("Fix", "я".repeat(30000))),
        ready: wiz.canAdvance(edit("Fix", "Do it")).ok,
      });
    """)
    assert out == {"empty": "title_invalid", "title_only": "brief_empty",
                   "blank_brief": "brief_empty", "brief_only": "title_invalid",
                   "control_char": "title_invalid", "too_long": "title_invalid",
                   "exactly_at_the_limit": None, "over_the_byte_limit": "brief_too_large",
                   "ready": True}


def test_the_starter_task_step_asks_for_a_title_and_an_idea_and_no_hint():
    out = run_js(PRELUDE + """
      const start = open({starterId: "desk-starter-docs"});
      const kept = run(start, {type: "edit-brief", value: "x"}, {type: "edit-hint", value: "y"});
      const titled = run(start, {type: "edit-title", value: "Notes app"});
      const ready = run(titled, {type: "edit-idea", value: "An app for notes."});
      const plain = open();
      show({fields: wiz.taskFields(start), normal: wiz.taskFields(plain),
        brief_ignored: kept === start, before_idea: wiz.canAdvance(titled).reason,
        ready: wiz.canAdvance(ready).ok,
        idea_ignored_in_normal_mode:
          wiz.reduceWizard(plain, {type: "edit-idea", value: "z"}) === plain});
    """)
    assert out == {"fields": ["title", "idea"], "normal": ["title", "brief", "hint"],
                   "brief_ignored": True, "before_idea": "idea_empty", "ready": True,
                   "idea_ignored_in_normal_mode": True}


def test_brief_document_is_byte_for_byte_the_section_6_2_3_template_in_both_languages():
    out = run_js(PRELUDE + """
      const ru = run(open(), {type: "edit-title", value: "Починить вход"},
        {type: "edit-brief", value: "Вход не работает.\\nНужно починить."},
        {type: "edit-hint", value: "Тесты проходят"});
      const en = run(open(), {type: "edit-title", value: "Fix login"},
        {type: "edit-brief", value: "Make it work."}, {type: "edit-hint", value: "Tests pass"});
      const unknown = () => {
        try { wiz.briefDocument(en, "de"); return null; } catch (error) { return error.message; }
      };
      show({ru: wiz.briefDocument(ru, "ru"), en: wiz.briefDocument(en, "en"),
        unknown: unknown()});
    """)
    assert out["ru"] == RU_BRIEF
    assert out["en"] == EN_BRIEF
    assert out["unknown"] == "unknown document language"


def test_brief_document_of_a_starter_task_uses_the_idea_section_and_a_dash_for_a_missing_hint():
    out = run_js(PRELUDE + """
      const starter = run(open({starterId: "desk-starter-docs"}),
        {type: "edit-title", value: "Notes app"}, {type: "edit-idea", value: "An app for notes."});
      const plain = run(typed(), {type: "edit-hint", value: "   "});
      show({ru: wiz.briefDocument(starter, "ru"), en: wiz.briefDocument(starter, "en"),
        blank_hint: wiz.briefDocument(plain, "en")});
    """)
    assert out["ru"] == ("# Notes app\n\n## Идея проекта\nAn app for notes.\n\n"
                         "## Как понять, что готово (подсказка)\n—\n")
    assert out["en"] == ("# Notes app\n\n## Project idea\nAn app for notes.\n\n"
                         "## How to tell it is done (hint)\n—\n")
    assert out["blank_hint"].endswith("## How to tell it is done (hint)\n—\n")


def test_the_task_title_is_read_only_once_its_task_is_written():
    out = run_js(PRELUDE + """
      const written = open({taskWritten: true, title: "Fix login"});
      const retitled = wiz.reduceWizard(written, {type: "edit-title", value: "Another"});
      const rebriefed = wiz.reduceWizard(written, {type: "edit-brief", value: "Other text"});
      show({title_kept: retitled === written && retitled.task.title === "Fix login",
        brief_still_editable: rebriefed.task.brief, written: written.task.written,
        title_of_an_unwritten_task_is_not_taken: open({title: "Sneaky"}).task.title});
    """)
    assert out == {"title_kept": True, "brief_still_editable": "Other text", "written": True,
                   "title_of_an_unwritten_task_is_not_taken": ""}


def test_an_event_the_wizard_does_not_know_or_that_changes_nothing_returns_the_very_same_state():
    out = run_js(PRELUDE + """
      const state = typed();
      const same = (event) => wiz.stepWizard(state, event);
      const rows = [{type: "explode"}, {type: "constructor"}, {type: "__proto__"}, null,
        {type: "edit-title", value: "Fix login"}, {type: "edit-title", value: 7},
        {type: "goto", step: "run"}, {type: "back"}, {type: "answered", ask: {id: "read:git"},
          result: {status: "accepted"}}];
      show(rows.map((event) => {
        const step = same(event);
        return [step.state === state, step.asks.length];
      }));
    """)
    assert out == [[True, 0]] * 9


def test_next_moves_forward_only_when_the_current_step_is_ready_and_back_always_moves():
    out = run_js(PRELUDE + """
      const blocked = wiz.reduceWizard(open(), {type: "next"});
      const forward = run(typed(), {type: "next"});
      const back = wiz.reduceWizard(forward, {type: "back"});
      show({blocked: blocked.step, forward: forward.step, back: back.step,
        goto_forward: run(typed(), {type: "goto", step: "materials"}).step,
        goto_from_a_blocked_step: run(open(), {type: "goto", step: "materials"}).step,
        goto_back_over_a_gap: run(forward, {type: "edit-title", value: ""},
          {type: "goto", step: "task"}).step,
        next_of: wiz.nextStep(open())});
    """)
    assert out["blocked"] == "task" and out["forward"] == "materials" and out["back"] == "task"
    assert out["goto_forward"] == "materials" and out["goto_from_a_blocked_step"] == "task"
    assert out["goto_back_over_a_gap"] == "task"
    assert out["next_of"] == "materials"


def test_the_task_step_publishes_the_task_and_the_brief_only_once_it_is_complete():
    out = run_js(PRELUDE + """
      const ready = run(typed(), {type: "edit-hint", value: "Tests pass"});
      const ofTask = (state) => wiz.publications(state, "en").filter((row) => row.step === "task");
      show({incomplete: wiz.publications(open(), "en"), ready: ofTask(ready)});
    """)
    assert out["incomplete"] == []
    assert out["ready"] == [{"step": "task", "writes": [
        {"link": 1, "target": "tasks", "body": {"task_id": "task-t1", "title": "Fix login"}},
        {"link": 5, "target": "artifacts", "ref": "artifact-brief",
         "media_type": "text/markdown",
         "content": ("# Fix login\n\n## What needs to be done\nMake it work.\n\n"
                     "## How to tell it is done (hint)\nTests pass\n")}]}]


def test_opening_asks_for_each_read_the_later_steps_need_once_and_only_once():
    out = run_js(PRELUDE + """
      const first = wiz.stepWizard(open(), {type: "open"});
      const again = wiz.stepWizard(first.state, {type: "open"});
      const edited = wiz.stepWizard(first.state, {type: "edit-title", value: "Fix"});
      show({asks: first.asks, asked: first.state.asked, again: again.asks.length,
        again_same: again.state === first.state, edited: edited.asks.length,
        before_open: wiz.stepWizard(open(), {type: "edit-title", value: "x"}).asks.length});
    """)
    assert [ask["id"] for ask in out["asks"]] == [
        "read:git", "read:workflows", "read:runs", "read:cycle_read", "read:tasks",
        "read:quotas"]
    assert all(ask["door"] == "read" and ask["subject"] is None and ask["body"] is None
               for ask in out["asks"])
    assert [ask["target"] for ask in out["asks"]] == [
        "git", "workflows", "runs", "projectCycle", "tasks", "quotas"]
    assert out["asked"] == [ask["id"] for ask in out["asks"]]
    assert (out["again"], out["again_same"], out["edited"], out["before_open"]) == (0, True, 0, 0)


def test_an_answer_is_recorded_by_the_ask_it_answers_and_a_read_can_be_asked_again():
    out = run_js(PRELUDE + """
      const first = wiz.stepWizard(open(), {type: "open"});
      const git = first.asks[0];
      const got = wiz.reduceWizard(first.state, {type: "answered", ask: git,
        result: {status: "accepted", payload: {git: {state: "repo"}}}});
      const failed = wiz.reduceWizard(first.state, {type: "answered", ask: git,
        result: {status: "refused", code: "project_not_active"}});
      const stranger = wiz.reduceWizard(first.state, {type: "answered",
        ask: {...git, id: "read:never-asked"}, result: {status: "accepted", payload: {}}});
      const bad = wiz.reduceWizard(first.state,
        {type: "answered", ask: git, result: {status: "maybe"}});
      const again = wiz.stepWizard(failed, {type: "reread", name: "git"});
      const unknown = wiz.stepWizard(failed, {type: "reread", name: "nothing"});
      show({got: got.reads.git, failed: failed.reads.git, stranger: stranger === first.state,
        bad: bad === first.state, reask: again.asks.map((ask) => ask.id),
        cleared: again.state.reads.git ?? null, unknown_same: unknown.state === failed});
    """)
    assert out["got"] == {"status": "ok", "code": None, "payload": {"git": {"state": "repo"}}}
    assert out["failed"] == {"status": "failed", "code": "project_not_active", "payload": None}
    assert out["stranger"] is True and out["bad"] is True
    assert out["reask"] == ["read:git"] and out["cleared"] is None and out["unknown_same"]


def test_no_event_mutates_the_state_it_was_given_or_the_payload_it_was_handed():
    out = run_js(PRELUDE + """
      const first = wiz.stepWizard(typed(), {type: "open"});
      const before = JSON.stringify(first.state);
      const payload = {git: {state: "repo", head: {ref: "refs/heads/main"}}};
      const kept = JSON.stringify(payload);
      const after = wiz.reduceWizard(first.state, {type: "answered", ask: first.asks[0],
        result: {status: "accepted", payload}});
      show({state_unchanged: JSON.stringify(first.state) === before,
        payload_unfrozen: !Object.isFrozen(payload) && JSON.stringify(payload) === kept,
        state_frozen: Object.isFrozen(after) && Object.isFrozen(after.reads.git.payload)
          && Object.isFrozen(after.task) && Object.isFrozen(after.asked)});
    """)
    assert out == {"state_unchanged": True, "payload_unfrozen": True, "state_frozen": True}
