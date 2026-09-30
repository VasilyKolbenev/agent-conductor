"""The reads that establish whether a task was closed, in a real page.

A task is closed when its newest run was accepted at its final gate (spec 5.4), and no list the
desk reads says so: the run itself does. `desk-closing.js` reads a run only when its row says it
could have been accepted -- nothing open, no step asking a person, its last outcome a success --
and only the newest run of a task, through the boot module's own read door. What this module
holds, in the real module and in the real desk:

- only such a run is read, once, and a run that fails the row's test is never read;
- a read that fails, is refused, names another task or another run establishes nothing and
  disturbs no other task;
- a desk that has gone foreign, or whose lists were not read, asks for nothing;
- a read that hangs holds nothing else: the scene of the task the address names, and every hash
  that comes after (a language, a task), are drawn and applied while the read is still out, and
  the summary, which alone needs the answer, is drawn when the read lands.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route

from browser_tests.desk_progress_bench import ZONE, desk_in, progress_url  # noqa: F401

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "desk"
                      / "feed_reads.json").read_text(encoding="utf-8"))
SEEDED = FIXTURE["seeded"]
#: The module in the page, handed the real lists and reads of the seeded project and a read
#: door that answers from them (or fails for the runs it is told to).
READ_CLOSING = """async ({tasks, runs, reads, fail, stopped, phase}) => {
  const {readClosing} = await import("/panel/desk-closing.js");
  const asked = [];
  const read = async (runId) => {
    asked.push(runId);
    if (fail.includes(runId)) throw new Error("store_error");
    return structuredClone(reads[runId]);
  };
  const found = await readClosing({read, tasks: {phase, list: tasks}, runs: {phase, list: runs},
    stopped: () => stopped});
  return {asked, found: [...found].map(([task, digest]) => [task, digest.run_id, digest.closed])};
}"""


def _closing(page, *, reads=None, fail=(), stopped=False, phase="ready", tasks=None):
    return page.evaluate(READ_CLOSING, {
        "tasks": SEEDED["tasks"]["tasks"] if tasks is None else tasks,
        "runs": SEEDED["runs"]["runs"], "reads": SEEDED["reads"] if reads is None else reads,
        "fail": list(fail), "stopped": stopped, "phase": phase})


def test_only_the_newest_run_that_could_have_been_accepted_is_read_and_it_is_read_once(desk_in):
    window = desk_in("en")
    found = _closing(window.page)
    assert found == {"asked": ["run-closed"], "found": [["task-closed", "run-closed", True]]}
    assert window.problems == []


def test_a_read_that_fails_establishes_nothing_and_throws_nothing(desk_in):
    window = desk_in("en")
    assert _closing(window.page, fail=["run-closed"]) == {"asked": ["run-closed"], "found": []}
    assert window.problems == []


def test_a_read_that_names_another_task_establishes_nothing(desk_in):
    reads = json.loads(json.dumps(SEEDED["reads"]))
    reads["run-closed"]["config"]["task"] = {"id": "task-idle", "work_scope": "task-idle"}
    reads["run-closed"]["task"] = {"id": "task-idle", "work_scope": "task-idle",
                                   "title": "Update the API docs", "unreadable": False}
    window = desk_in("en")
    assert _closing(window.page, reads=reads) == {"asked": ["run-closed"], "found": []}


def test_a_read_the_scene_would_refuse_establishes_nothing(desk_in):
    reads = json.loads(json.dumps(SEEDED["reads"]))
    reads["run-closed"]["not_a_key_of_a_run_read"] = 1
    window = desk_in("en")
    assert _closing(window.page, reads=reads) == {"asked": ["run-closed"], "found": []}


def test_a_read_that_answers_with_another_run_of_the_task_establishes_nothing(desk_in):
    """The body of a different run that says it belongs to the task: the run asked about is
    what a digest must be of, not merely the task."""
    reads = json.loads(json.dumps(SEEDED["reads"]))
    other = reads["run-waiting"]
    other["config"]["task"] = {"id": "task-closed", "work_scope": "task-closed"}
    other["task"] = {"id": "task-closed", "work_scope": "task-closed",
                     "title": "Ship the landing page", "unreadable": False}
    reads["run-closed"] = other
    window = desk_in("en")
    assert _closing(window.page, reads=reads)["found"] == []
    assert window.problems == []


def test_a_desk_that_went_foreign_or_whose_lists_were_not_read_asks_for_nothing(desk_in):
    window = desk_in("en")
    assert _closing(window.page, stopped=True) == {"asked": [], "found": []}
    assert _closing(window.page, phase="failed") == {"asked": [], "found": []}
    assert _closing(window.page, phase="loading") == {"asked": [], "found": []}


def test_a_task_the_list_cannot_read_is_never_asked_about(desk_in):
    lost = {"task_id": "task-closed", "title": None, "unreadable": True, "created_at": None,
            "schema_version": None, "work_scope": None}
    others = [task for task in SEEDED["tasks"]["tasks"] if task["task_id"] != "task-closed"]
    window = desk_in("en")
    assert _closing(window.page, tasks=[lost, *others]) == {"asked": [], "found": []}


@pytest.mark.parametrize("task", [None, "task-closed"])
def test_the_desk_reads_the_run_of_a_finished_task_and_no_other_run_besides_the_one_it_draws(
        desk_in, task):
    """Chosen or not, the closing read is one GET of the finished run; the scene adds its own."""
    window = desk_in("en", task=task)
    reads = [path for method, path in window.asked
             if method == "GET" and path.startswith("/command/runs/")
             and path.count("/") == 3]
    assert sorted(reads) == sorted(["/command/runs/run-closed"] * (1 if task is None else 2))
    assert {method for method, _path in window.asked} == {"GET"}
    assert window.problems == []


# -- a read that hangs holds nothing but the summary ---------------------------------------------

#: What a desk that is not held by the closing read may take to draw what an address names: far
#: under the deadline a read is abandoned at (20 s), so a desk that waits for the read fails on the
#: wait and not on the deadline.
UNGATED_MS = 8000
#: One evaluation: what the page says of itself.
DESK_FACTS = """() => {
  const at = (id) => document.getElementById(id);
  return {lang: document.documentElement.lang, shell: at("deskShell").getAttribute("data-state"),
    scene: at("deskScene").getAttribute("data-state"),
    run: at("deskFeed").querySelector(".desk-feed__log")?.dataset.run ?? null,
    bar: at("deskSummary").childElementCount,
    chips: [...at("deskSummary").querySelectorAll(".desk-sum__chip")].map((chip) => [
      chip.querySelector(".desk-sum__label").textContent, chip.querySelector("b").textContent])};
}"""
FEED_OF = "(run) => document.querySelector('#deskFeed .desk-feed__log')?.dataset.run === run"
LANGUAGE = "(lang) => document.documentElement.lang === lang"
BAR_DRAWN = "() => document.querySelector('#deskSummary .desk-sum__bar') !== null"
RAIL_DRAWN = "() => document.querySelectorAll('#deskRail [data-task-id]').length === 4"


@dataclass
class HeldDesk:
    """A window on the seeded project whose read of the finished run is asked and not answered."""

    page: Page
    held: list[Route]
    problems: list[str]

    def release(self) -> None:
        while self.held:
            self.held.pop().continue_()


@pytest.fixture
def held_desk(chromium, progress_url):
    """`open_at(address)`: the desk booted at the address, its closing read out and held."""
    context = chromium.new_context(viewport={"width": 1280, "height": 900}, timezone_id=ZONE)
    page = context.new_page()
    held: list[Route] = []
    problems: list[str] = []
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.route("**/command/runs/run-closed", lambda route: held.append(route))

    def open_at(address: str) -> HeldDesk:
        page.goto(f"{progress_url}{address}", wait_until="load")
        for _wait in range(200):
            if held:
                break
            page.wait_for_timeout(50)
        assert held, "the closing read of the finished run was never asked"
        return HeldDesk(page, held, problems)

    try:
        yield open_at
    finally:
        while held:
            held.pop().abort()
        context.close()


def test_a_task_the_address_names_is_drawn_while_the_closing_read_is_held_and_then_counted(
        held_desk):
    window = held_desk("#lang=en&task=task-working")
    window.page.wait_for_function(FEED_OF, arg="run-working", timeout=UNGATED_MS)
    drawn = window.page.evaluate(DESK_FACTS)
    assert (drawn["shell"], drawn["scene"], drawn["run"]) == ("ready", "ready", "run-working")
    assert drawn["bar"] == 0, "the summary waits for the numbers the held read will bring"
    window.release()
    window.page.wait_for_function(BAR_DRAWN)
    assert ["Closed", "1"] in window.page.evaluate(DESK_FACTS)["chips"]
    assert window.problems == []


def test_a_language_and_a_task_set_by_a_later_hash_apply_while_the_closing_read_is_held(
        held_desk):
    window = held_desk("#lang=en")
    window.page.wait_for_function(RAIL_DRAWN, timeout=UNGATED_MS)
    window.page.evaluate("() => { location.hash = '#lang=ru'; }")
    window.page.wait_for_function(LANGUAGE, arg="ru", timeout=UNGATED_MS)
    window.page.evaluate("() => { location.hash = '#lang=ru&task=task-working'; }")
    window.page.wait_for_function(FEED_OF, arg="run-working", timeout=UNGATED_MS)
    drawn = window.page.evaluate(DESK_FACTS)
    assert (drawn["lang"], drawn["run"], drawn["bar"]) == ("ru", "run-working", 0)
    window.release()
    window.page.wait_for_function(BAR_DRAWN)
    assert window.problems == []
