"""The "Continue after" block of the console, in a real Chromium (spec 5.8, 4.3.4).

The block is the flag of the project's turn in the queue: a switch, the runs whose grant can
still be continued, the start of the task queue, one save that writes the flag in the name of the
person at the page, and one line that says what the flag is. It is drawn only in a desk a hub
frames (`embed=hub`), from the read of `/command/project/auto-continue`; the routes of that flag
were not in lane D1's branch when this was written, so they are answered in the page by
`desk_flag_fake.py`, in the record shape lane H's hand-off fixes, and the runs to continue are
given by answering the automation read of the newest run of each task. What this module holds,
each as a measurement of the page:

- only the runs whose grant can be continued have a mark (a pause, or a wait for an explicit
  resume), oldest first; a run whose grant expired has none and says why; nothing is sent until a
  person presses Save, and Save waits for the person's name;
- a save is ONE write whose body is exactly `{enabled, actor, resume_runs, start_task_queue}`, the
  runs in the order of the list and the actor the one of the console, through the transport's
  door with the project claim and the session token; the line then says the flag stands;
- taking the flag off is the same write with nothing listed and no queue start;
- a flag that stands opens with its runs marked, a consumed one reads "executed" with its switch
  off, and a refused save says so in place and keeps the marks; a `project_mismatch` on the
  write ends the desk;
- a desk nobody framed has no block and never reads the flag;
- no raw token in the words of the console, and nothing in any storage.

A fact and its sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

import json

import pytest

from browser_tests import desk_flag_fake as fake
from browser_tests.test_desk_embed import (  # noqa: F401  (fixtures and helpers)
    PROJECT, Embedded, Rig, _answering, _claim, _listen, embed, rig)
from browser_tests.test_desk_hash import QUIET
from browser_tests.test_desk_rail_scene import SETTLED
from browser_tests.test_desk_status import RAW

#: The newest run of each task that has one, as the desk reads them, and what each says.
AUTOMATIONS = {
    "run-fix-new": fake.automation("run-fix-new", "paused", "paused"),
    "run-docs": fake.automation("run-docs", "restart_required", "explicit_resume_required"),
    "run-check": fake.automation("run-check", "expired", "expired"),
}
#: Oldest first: `run-check` and `run-docs` were made together (by id), `run-fix-new` later.
LISTED = ["run-check", "run-docs", "run-fix-new"]
TITLES = {"run-check": "Check the export", "run-docs": "Write the docs",
          "run-fix-new": "Fix lost text"}
WORDS = {
    "en": {"head": "Continue after", "runs": "Continue runs",
           "expired": "permission expired — a new confirmation of terms is needed",
           "need_name": "Give your name above to record the flag in it.",
           "standing": "Flag set since 09/30 14:05 · vasya",
           "consumed": "Flag executed on activation 09/30 16:40 · vasya",
           "save": "Save", "clear": "Remove the flag"},
    "ru": {"head": "Продолжить после", "runs": "Продолжить запуски",
           "expired": "разрешение истекло — нужно новое подтверждение условий",
           "need_name": "Укажите имя выше, чтобы записать флаг от вашего имени.",
           "standing": "Флаг стоит с 30.09 14:05 · vasya",
           "consumed": "Флаг исполнен при активации 30.09 16:40 · vasya",
           "save": "Сохранить", "clear": "Снять флаг"},
}
#: Everything a test asks of the block, in one evaluation; `textContent`, because the style
#: draws the headings in capitals.
BLOCK = """() => {
  const block = document.querySelector("#deskPult .desk-flag");
  if (!block) return null;
  const control = (key) => block.querySelector(`[data-focus-key="${key}"]`);
  const text = (node) => (node ? node.textContent.trim() : null);
  const hint = block.querySelector("[data-flag-hint]");
  return {
    open: block.open, head: text(block.querySelector("summary")),
    runs: text(block.querySelector("legend")),
    enabled: control("flag:enabled") ? control("flag:enabled").checked : null,
    queue: control("flag:queue") ? control("flag:queue").checked : null,
    rows: [...block.querySelectorAll("[data-run-id]")].map((row) => {
      const mark = row.querySelector("input[type=checkbox]");
      return {run: row.dataset.runId, title: text(row.querySelector("[data-flag-title]")),
        note: text(row.querySelector("[data-flag-note]")),
        mark: mark ? mark.checked : null};
    }),
    line: text(block.querySelector("[data-flag-line]")),
    save: control("flag:save") ? [text(control("flag:save")), control("flag:save").disabled] : null,
    clear: control("flag:clear") ? [text(control("flag:clear")), control("flag:clear").disabled]
      : null,
    hint: hint ? [text(hint), hint.hidden] : null,
    sizes: [...block.querySelectorAll("button, input, summary")].map((node) => {
      const box = node.getBoundingClientRect();
      return [node.tagName, Math.round(box.height)];
    })};
}"""
CONSOLE_TEXT = "() => document.getElementById('deskPult').innerText"
STORAGE = "() => [localStorage.length, sessionStorage.length]"
FRAMED = "#project={project}&embed=hub&lang={language}"


def _open(embed, rig, language, *, server=None, automations=AUTOMATIONS):
    """A framed desk on the seeded project with the flag door and the automation reads given."""
    server = server if server is not None else fake.FlagServer()
    window = embed(FRAMED.format(project=PROJECT, language=language),
                   _answering(_claim(hub_origin=rig.host_origin)),
                   flag=server, automations=automations)
    window.frame.wait_for_selector("#deskPult .desk-flag", timeout=6000)
    return window, server


def _name(window, who: str) -> None:
    """Give the console the name of the person at the page, as a person does."""
    window.frame.locator('[data-focus-key="pult:actor-change"]').click()
    window.frame.locator('[name="actor"]').fill(who)
    window.frame.locator('[data-focus-key="pult:actor-save"]').click()


def _open_block(window) -> None:
    window.frame.locator("#deskPult .desk-flag > summary").click()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_continue_block_offers_only_resumable_runs_and_writes_the_flag_with_the_actor(
        embed, rig, language):
    words = WORDS[language]
    window, server = _open(embed, rig, language)
    window.frame.wait_for_function(SETTLED)
    opening = window.frame.evaluate(BLOCK)
    assert (opening["open"], opening["head"], opening["runs"]) == (
        False, words["head"], words["runs"])
    assert [row["run"] for row in opening["rows"]] == LISTED
    assert [(row["run"], row["title"], row["note"], row["mark"]) for row in opening["rows"]] == [
        ("run-check", TITLES["run-check"], words["expired"], None),
        ("run-docs", TITLES["run-docs"], None, False),
        ("run-fix-new", TITLES["run-fix-new"], None, False)]
    assert (opening["enabled"], opening["queue"], opening["line"]) == (False, False, None)
    assert opening["save"] == [words["save"], True] and opening["clear"][1] is True
    assert opening["hint"] == [words["need_name"], False]
    _name(window, "vasya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:enabled"]').check()
    for run in ("run-fix-new", "run-docs"):  # marked newest first: the body is the list's order
        window.frame.locator(f'[data-focus-key="flag:run:{run}"]').check()
    window.frame.locator('[data-focus-key="flag:queue"]').check()
    ready = window.frame.evaluate(BLOCK)
    assert ready["open"] is True and ready["save"][1] is False and ready["hint"][1] is True
    assert server.posts == [] and server.reads == 1, "nothing is written before the press"
    window.frame.locator('[data-focus-key="flag:save"]').click()
    window.frame.wait_for_function(
        "(line) => document.querySelector('#deskPult [data-flag-line]')?.textContent === line",
        arg=words["standing"])
    assert server.posts == [{"enabled": True, "actor": "vasya",
                             "resume_runs": ["run-docs", "run-fix-new"],
                             "start_task_queue": True}]
    assert list(server.posts[0]) == ["enabled", "actor", "resume_runs", "start_task_queue"]
    sent = server.headers[0]
    assert sent["x-conduct-project"] == PROJECT and sent["x-conduct-csrf"]
    after = window.frame.evaluate(BLOCK)
    assert (after["enabled"], after["queue"], after["line"]) == (True, True, words["standing"])
    assert [(row["run"], row["mark"]) for row in after["rows"]] == [
        ("run-check", None), ("run-docs", True), ("run-fix-new", True)]
    assert not RAW.search(window.frame.evaluate(CONSOLE_TEXT))
    assert window.frame.evaluate(STORAGE) == [0, 0] and window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_taking_the_flag_off_writes_nothing_listed_and_no_queue_start(embed, rig, language):
    words = WORDS[language]
    server = fake.FlagServer(record=fake.standing("vasya", ("run-docs", "run-fix-new"), True))
    window, server = _open(embed, rig, language, server=server)
    _name(window, "petya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:clear"]').click()
    window.frame.wait_for_function("() => !document.querySelector("
                                   "'#deskPult [data-focus-key=\"flag:enabled\"]').checked")
    assert server.posts == [{"enabled": False, "actor": "petya", "resume_runs": [],
                             "start_task_queue": False}]
    after = window.frame.evaluate(BLOCK)
    assert (after["enabled"], after["queue"], after["line"]) == (False, False, None)
    assert [row["mark"] for row in after["rows"]] == [None, False, False]
    assert after["clear"][0] == words["clear"] and window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_flag_that_stands_opens_with_its_runs_marked_and_says_who_set_it_and_when(
        embed, rig, language):
    words = WORDS[language]
    server = fake.FlagServer(record=fake.standing("vasya", ("run-docs", "run-check"), True))
    window, _server = _open(embed, rig, language, server=server)
    facts = window.frame.evaluate(BLOCK)
    assert (facts["enabled"], facts["queue"], facts["line"]) == (True, True, words["standing"])
    assert [(row["run"], row["mark"]) for row in facts["rows"]] == [
        ("run-check", None), ("run-docs", True), ("run-fix-new", False)]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_consumed_flag_reads_executed_and_its_switch_is_off(embed, rig, language):
    words = WORDS[language]
    server = fake.FlagServer(record=fake.consumed("vasya", ("run-docs",)))
    window, _server = _open(embed, rig, language, server=server)
    facts = window.frame.evaluate(BLOCK)
    assert (facts["enabled"], facts["line"]) == (False, words["consumed"])
    assert [row["mark"] for row in facts["rows"]] == [None, False, False]


def test_a_refused_save_says_so_in_place_and_keeps_the_marks(embed, rig):
    server = fake.FlagServer(refuse=(422, {"error": {
        "code": "contract_invalid", "message": "the body is not a contract",
        "detail": {"run_id": "run-docs"}}}))
    window, server = _open(embed, rig, "en", server=server)
    _name(window, "vasya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:enabled"]').check()
    window.frame.locator('[data-focus-key="flag:run:run-docs"]').check()
    window.frame.locator('[data-focus-key="flag:save"]').click()
    window.frame.wait_for_selector("#deskPult [data-flag-hint]:not([hidden])")
    facts = window.frame.evaluate(BLOCK)
    said = window.frame.evaluate("""async () => (await import("/panel/studio-i18n.js"))
      .message("en", "error.contract_invalid")""")
    assert facts["hint"] == [said, False]
    assert (facts["enabled"], facts["line"]) == (True, None)
    assert [row["mark"] for row in facts["rows"]] == [None, True, False]
    assert len(server.posts) == 1


def test_a_project_mismatch_on_the_save_ends_the_desk(embed, rig):
    server = fake.FlagServer(refuse=(409, {"error": {"code": "project_mismatch",
                                                     "message": "x", "detail": {}}}))
    window, server = _open(embed, rig, "en", server=server)
    _name(window, "vasya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:enabled"]').check()
    window.frame.locator('[data-focus-key="flag:save"]').click()
    window.frame.wait_for_function(
        "() => document.getElementById('deskStatus').innerText.includes('another project')")
    assert window.frame.evaluate(BLOCK) is None
    sent = len(server.posts)
    window.frame.evaluate(QUIET)
    assert len(server.posts) == sent == 1


def test_a_desk_nobody_framed_has_no_block_and_never_reads_the_flag(chromium, rig):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    server = fake.FlagServer()
    try:
        page = context.new_page()
        problems, asked = _listen(page, rig)
        page.route("**/command/project/auto-continue", server.handle)
        page.goto(f"{rig.desk_url}#project={PROJECT}&embed=hub&lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        window = Embedded(page, page.main_frame, problems, asked)
        assert page.evaluate(BLOCK) is None and server.reads == 0
        assert window.problems == []
    finally:
        context.close()
    assert json.dumps(server.posts) == "[]"
