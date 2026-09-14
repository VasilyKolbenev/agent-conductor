"""What else meets a dead read: a queued frame, a dropped stream, the lists, and
the workflow queue.

The run queue's own witnesses, and the bench, are in
``browser_tests/test_studio_read_liveness.py``: a server whose handler holds one
GET by path and reports whether the page closed its socket, a stream double, and
a clock paused once the window has settled. These are the same class on the
roads around it, found by the review panel on the first correction:

- a deadline that passes while a frame's read of the SAME subject waits behind
  the dead one is still news -- nothing newer is on the wire, since the queue
  waits on this read -- so a person under steady frames is still told. A drop
  of the stream is not that case, and never gets its sentence painted over;
- a dropped and reopened stream aborts no read: `error` fires on every failed
  reconnect, and a window that aborted there would throw away healthy reads;
- a LIST read is not serialized -- every frame issues one -- so a dead list read
  and the recovery that replaced it can both be out at once. An outcome that
  settles after a NEWER read already landed must not paint over it, whether it
  is an answer or a failure;
- the WORKFLOW detail queue has the run queue's shape and needed both of its
  guarantees: busy ownership released on every exit, and a press or a new
  workflow retiring the read in flight instead of waiting the deadline out --
  including the read that confirms a publish, which only a read-back of its
  own may confirm.

A frame reads the run LIST beside the run. That read is not under test, and on
a paused clock its deadline would pass with the dead one's if it were still
out, so every witness that moves the clock after a frame waits for it first.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from browser_tests.test_studio_editing import DRAFT, SAVED_AT, WORKFLOW_ID
from browser_tests.test_studio_lifecycle import _publish
from browser_tests.test_studio_read_liveness import (
    BREAK_RENDER,
    MEND_RENDER,
    RUN_PATH,
    TICK,
    _expire,
    _frame,
    _notice,
    _open,
    _sentence,
    _state,
    _stalling_bench,
    _until,
)
from browser_tests.test_studio_step import RUN_ID, _read

OTHER_FLOW = "editing-bench-two"
FLOW_PATH = f"/command/workflows/{WORKFLOW_ID}"
REVISION_PATH = f"{FLOW_PATH}/revisions/1"
LISTS = {"runs": "/command/runs", "workflows": "/command/workflows"}
PICKER = "#workflowToolbar select[name='workflow']"
VALIDATE = '#workflowToolbar [data-focus="action:onValidate"]'
#: Record every state word a screen is drawn in from here on.
WATCH = """selector => {
  window.states = [];
  new MutationObserver((records) => {
    for (const record of records) {
      window.states.push(record.target.getAttribute('data-state'));
    }
  }).observe(document.querySelector(selector),
    {attributes: true, attributeFilter: ['data-state']});
}"""


def _two_workflows(root: Path) -> None:
    store = TemplateStore(root)
    for workflow_id in (WORKFLOW_ID, OTHER_FLOW):
        store.save_draft(WorkflowDraft(
            workflow_id=workflow_id, saved_at=SAVED_AT, document=DRAFT))


@pytest.fixture
def stalled(tmp_path) -> Iterator[tuple[object, object]]:
    with _stalling_bench(tmp_path) as bench:
        yield bench


@pytest.fixture
def flows(tmp_path) -> Iterator[tuple[object, object]]:
    """The same bench, holding two stored workflows for the workflow queue."""
    with _stalling_bench(tmp_path, _two_workflows) as bench:
        yield bench


def _state_frame(page: Page) -> None:
    """A `state` frame: it re-reads the workflow list and the chosen workflow."""
    page.evaluate("() => window.__stream.emit(JSON.stringify({kind: 'state'}))")


def _list_landed(page: Page) -> None:
    """Wait out the run LIST read a frame issued beside its run read."""
    page.wait_for_selector('#screenRuns[data-state="ready"]', state="attached")


def _quiet(stall, path: str, settle: float = 0.4) -> int:
    """Wait until no new GET of `path` has reached the server for `settle`.

    The boot reads both lists and the stream's `open` reads them again, so a
    list read can still be in flight when a witness arms the stall -- and then
    the arm holds THAT read rather than the press's. Measured: 1 run in 8 of
    this module recorded `loading` then `failed` from the RECOVERY read, which
    is the opposite of what the witness below claims to hold. Every list
    witness therefore quiets the road first and then proves, by the server's
    own count, that the read it holds is the one its press issued.
    """
    last, steady = stall.count(path), time.monotonic()
    while time.monotonic() - steady < settle:
        time.sleep(0.05)
        now = stall.count(path)
        if now != last:
            last, steady = now, time.monotonic()
    return last


def _nodes(page: Page, count: int) -> None:
    page.wait_for_function(
        "n => document.querySelectorAll('[data-node-id]').length === n", arg=count)


def _choose(page: Page, workflow_id: str) -> None:
    """Open one stored workflow, waiting on its drawing being the one read."""
    page.locator("#navWorkflow").click()
    page.locator(PICKER).select_option(workflow_id)
    page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
    _nodes(page, 3)


# -- 1. a queued frame, and a dropped stream ------------------------------------


def test_a_deadline_under_a_queued_frame_is_still_told_to_the_person(
        chromium: Browser, stalled) -> None:
    """A press's run read hangs and a frame queues another behind it. At the
    deadline the person is told -- the screens fail and the window's sentence
    stands -- and the queued read goes out after it. The queued read is held
    too, so what the deadline said is still on screen to be read."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        before = stall.count(RUN_PATH)
        stall.arm(RUN_PATH, "headers")
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        assert stall.entered.wait(10), "the press provoked no run read"
        _frame(page, RUN_ID)
        _list_landed(page)
        stall.arm(RUN_PATH, "headers")
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        assert stall.entered.wait(10), "the queued read never went out"
        page.wait_for_selector('#screenDecisions[data-state="failed"]',
                               state="attached")
        assert _notice(page) == _sentence("LATE_SAID")
        assert stall.count(RUN_PATH) == before + 2
        assert window.problems == []
    finally:
        page.context.close()


def test_a_deadline_after_the_stream_dropped_leaves_the_connection_sentence(
        chromium: Browser, stalled) -> None:
    """A frame's read hangs and then the stream drops. The drop retired the
    read along with the session, and says so in its own sentence. The dead
    read's deadline is not news the queue owes anyone: its socket is closed and
    the connection sentence stays exactly as it was."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        stall.arm(RUN_PATH, "headers")
        _frame(page, RUN_ID)
        assert stall.entered.wait(10), "the frame provoked no run read"
        _list_landed(page)
        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_selector('#studioConnection[data-connection="closed"]')
        dropped = _notice(page)
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        page.evaluate(TICK)
        assert _notice(page) == dropped
        assert _sentence("LATE_SAID") not in _notice(page)
        assert window.problems == []
    finally:
        page.context.close()


def test_a_dropped_and_reopened_stream_aborts_no_read(
        chromium: Browser, stalled) -> None:
    """A frame's read is held while the stream drops and comes back. Neither
    event closes its socket: released, it answers on the connection it was
    asked on, and the reconnect's own read follows it."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        before = stall.count(RUN_PATH)
        stall.arm(RUN_PATH, "answer")
        _frame(page, RUN_ID)
        assert stall.entered.wait(10), "the frame provoked no run read"
        page.evaluate(
            "() => { window.__stream.fire('error'); window.__stream.fire('open'); }")
        page.wait_for_selector('#studioConnection[data-connection="open"]')
        page.evaluate(TICK)
        stall.release.set()
        _until(lambda: stall.count(RUN_PATH) == before + 2,
               "the reconnect's read never followed the held one")
        page.wait_for_selector('#screenDecisions[data-state="ready"]',
                               state="attached")
        assert not stall.aborted.is_set(), "a drop or a reconnect aborted a read"
        assert window.problems == []
    finally:
        page.context.close()


# -- 2. the lists ------------------------------------------------------------------


#: Hold the first read of a list and hand back an OLDER list in its place: the
#: real answer with its runs emptied, as the list stood before any run existed.
#: `read` turns true once the page has taken that body, so the next macrotask
#: finds the reader already settled one way or the other.
HOLD_AN_OLDER_LIST = """target => {
  const original = window.fetch.bind(window);
  window.late = {held: false, ready: false, read: false, settle: null};
  window.fetch = (url, options = {}) => {
    const path = new URL(url, location.href).pathname;
    if (path !== target || window.late.held) return original(url, options);
    window.late.held = true;
    return new Promise((resolve) => {
      original(url, {cache: 'no-store'})
        .then((answer) => answer.json())
        .then((payload) => {
          const older = new Response(JSON.stringify({...payload, runs: []}),
            {status: 200, headers: {'Content-Type': 'application/json'}});
          const take = older.json.bind(older);
          older.json = () => take().then((value) => {
            window.late.read = true;
            return value;
          });
          window.late.settle = () => resolve(older);
          window.late.ready = true;
        });
    });
  };
}"""
#: Where each list is asked for again by a person, and the screen its state
#: word is drawn on.
RECOVERY = {
    "runs": ("#navRuns", '#studioPrimary [data-focus="action:onRefreshRuns"]',
             "#screenRuns"),
    "workflows": ("#navAgents",
                  '#studioPrimary [data-focus="action:onRefreshAgents"]',
                  "#screenWorkflow"),
}


@pytest.mark.parametrize("which", sorted(RECOVERY))
def test_a_dead_list_read_that_fails_late_never_paints_over_the_recovery(
        chromium: Browser, stalled, which: str) -> None:
    """A list read hangs; the person asks for the list again and that read
    lands. When the dead read's deadline passes, its socket is closed and
    nothing is drawn: the newer list stands, in `ready`, with no sentence
    about a read that was already replaced."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    screen, control, drawn = RECOVERY[which]
    try:
        page.locator(screen).click()
        page.wait_for_selector(f'{drawn}[data-state="ready"]', state="attached")
        asked = _quiet(stall, LISTS[which])
        stall.arm(LISTS[which], "headers")
        page.locator(control).click()
        assert stall.entered.wait(10), "the press provoked no list read"
        assert stall.count(LISTS[which]) == asked + 1, (
            "the stall holds a read this press did not issue")
        page.evaluate(WATCH, drawn)
        page.locator(control).click()
        _until(lambda: stall.count(LISTS[which]) == asked + 2,
               "the recovery press issued no list read")
        page.wait_for_function("() => window.states.includes('ready')")
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the dead list read open"
        page.evaluate(TICK)
        assert "failed" not in page.evaluate("() => window.states")
        assert page.locator(drawn).get_attribute("data-state") == "ready"
        assert _sentence("LATE_SAID") not in _notice(page)
        assert window.problems == []
    finally:
        page.context.close()


def test_a_dead_list_read_that_answers_late_never_paints_over_the_recovery(
        chromium: Browser, stalled) -> None:
    """The same race with an ANSWER: the held read comes back after the
    recovery landed, carrying an older list with no runs in it. The page takes
    that body and draws nothing from it -- every run row stays."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    screen, control, drawn = RECOVERY["runs"]
    rows = '[data-focus-key^="run:"]'
    try:
        page.locator(screen).click()
        page.wait_for_selector(f'{drawn}[data-state="ready"]', state="attached")
        _quiet(stall, LISTS["runs"])
        page.evaluate(HOLD_AN_OLDER_LIST, LISTS["runs"])
        page.locator(control).click()
        page.wait_for_function("() => window.late.ready")
        page.evaluate(WATCH, drawn)
        page.locator(control).click()
        page.wait_for_function("() => window.states.includes('ready')")
        standing = page.locator(rows).count()
        assert standing > 0
        page.evaluate("() => window.late.settle()")
        page.wait_for_function("() => window.late.read")
        page.evaluate(TICK)
        assert page.locator(rows).count() == standing
        assert page.locator(drawn).get_attribute("data-state") == "ready"
        assert window.problems == []
    finally:
        page.context.close()


def test_a_dead_run_list_read_fails_at_the_deadline_in_the_windows_words(
        chromium: Browser, stalled) -> None:
    """With no recovery racing it, a dead list read is news: at the deadline
    its socket is closed, the Runs screen FAILED -- it was not refused -- the
    window says so, and the next press reads the list and clears it."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    screen, control, drawn = RECOVERY["runs"]
    try:
        page.locator(screen).click()
        page.wait_for_selector(f'{drawn}[data-state="ready"]', state="attached")
        asked = _quiet(stall, LISTS["runs"])
        stall.arm(LISTS["runs"], "headers")
        page.locator(control).click()
        assert stall.entered.wait(10), "the press provoked no list read"
        assert stall.count(LISTS["runs"]) == asked + 1, (
            "the stall holds a read this press did not issue")
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        page.wait_for_selector(f'{drawn}[data-state="failed"]', state="attached")
        assert _notice(page) == _sentence("LATE_SAID")
        page.locator(control).click()
        page.wait_for_selector(f'{drawn}[data-state="ready"]', state="attached")
        assert _sentence("LATE_SAID") not in _notice(page)
        assert window.problems == []
    finally:
        page.context.close()


# -- 3. the workflow queue ----------------------------------------------------------


def test_a_workflow_read_whose_exit_throws_still_hands_the_workflow_queue_back(
        chromium: Browser, flows) -> None:
    """The timed-out workflow read's own dispatch throws. Exactly one page error
    is reported, and the workflow queue is free: the next `state` frame reads
    the workflow, and that read lands."""
    bench, stall = flows
    page, window = _open(chromium, bench)
    try:
        _choose(page, WORKFLOW_ID)
        before = stall.count(FLOW_PATH)
        stall.arm(FLOW_PATH, "headers")
        page.locator(VALIDATE).click()
        assert stall.entered.wait(10), "Validate provoked no workflow read"
        page.evaluate(BREAK_RENDER)
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        # A page call that WAITS, not a sleep: Playwright hands a page error to
        # Python only while one of its own calls is waiting on the page.
        for _ in range(400):
            if window.page_errors:
                break
            page.wait_for_timeout(25)
        assert len(window.page_errors) == 1, window.page_errors
        page.evaluate(MEND_RENDER)
        _state_frame(page)
        _until(lambda: stall.count(FLOW_PATH) == before + 2,
               "the workflow queue stayed latched behind a read whose exit threw")
        page.wait_for_selector('#screenWorkflow[data-state="ready"]',
                               state="attached")
        assert len(window.page_errors) == 1, window.page_errors
        assert window.console_errors == []
    finally:
        page.context.close()


@pytest.mark.parametrize("press", ["another-workflow", "validate"])
def test_a_press_or_another_workflow_escapes_a_dead_workflow_read(
        chromium: Browser, flows, press: str) -> None:
    """A `state` frame's read of the chosen workflow hangs. Validate, or
    choosing the other workflow, closes the dead socket at once -- the clock
    never moves -- and issues its own read instead of queueing behind it."""
    bench, stall = flows
    page, window = _open(chromium, bench)
    try:
        _choose(page, WORKFLOW_ID)
        before = stall.count(FLOW_PATH)
        stall.arm(FLOW_PATH, "headers")
        _state_frame(page)
        assert stall.entered.wait(10), "the frame provoked no workflow read"
        if press == "validate":
            page.locator(VALIDATE).click()
            assert stall.aborted.wait(10), "Validate left the dead read open"
            _until(lambda: stall.count(FLOW_PATH) == before + 2,
                   "Validate issued no read of its own")
        else:
            page.locator(PICKER).select_option(OTHER_FLOW)
            assert stall.aborted.wait(10), "a new workflow left the dead read open"
            _nodes(page, 3)
            assert stall.count(f"/command/workflows/{OTHER_FLOW}") == 1
            assert stall.count(FLOW_PATH) == before + 1
        page.wait_for_selector('#screenWorkflow[data-state="ready"]',
                               state="attached")
        assert _sentence("LATE_SAID") not in _notice(page)
        assert window.problems == []
    finally:
        page.context.close()


def test_a_dead_workflow_read_fails_at_the_deadline_beside_the_persons_words(
        chromium: Browser, flows) -> None:
    """Validate's read never answers. At the deadline its socket is closed, the
    Workflow screen FAILED, and the window's sentence is said AFTER the one
    Validate wrote -- beside the person's words, never over them -- while the
    drawing on screen stays."""
    bench, stall = flows
    page, window = _open(chromium, bench)
    try:
        _choose(page, WORKFLOW_ID)
        stall.arm(FLOW_PATH, "headers")
        page.locator(VALIDATE).click()
        assert stall.entered.wait(10), "Validate provoked no workflow read"
        asked = _notice(page)
        assert asked and _sentence("LATE_SAID") not in asked
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        page.wait_for_selector('#screenWorkflow[data-state="failed"]',
                               state="attached")
        assert _notice(page).startswith(f"{asked} {_sentence('LATE_SAID')}")
        _nodes(page, 3)
        assert _state(page, "Workflow") == "failed"
        assert window.problems == []
    finally:
        page.context.close()


def test_a_deadline_under_a_queued_state_frame_is_told_on_the_workflow_screen(
        chromium: Browser, flows) -> None:
    """Validate's read hangs and a `state` frame queues another behind it. At
    the deadline the Workflow screen fails and the window's sentence stands
    beside Validate's; the queued read goes out after it, and is held too so
    what the deadline said stays to be read."""
    bench, stall = flows
    page, window = _open(chromium, bench)
    try:
        _choose(page, WORKFLOW_ID)
        before = stall.count(FLOW_PATH)
        stall.arm(FLOW_PATH, "headers")
        page.locator(VALIDATE).click()
        assert stall.entered.wait(10), "Validate provoked no workflow read"
        _state_frame(page)
        page.wait_for_selector('#screenWorkflow[data-state="ready"]',
                               state="attached")
        stall.arm(FLOW_PATH, "headers")
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        assert stall.entered.wait(10), "the queued workflow read never went out"
        page.wait_for_selector('#screenWorkflow[data-state="failed"]',
                               state="attached")
        assert _notice(page).endswith(_sentence("LATE_SAID"))
        assert stall.count(FLOW_PATH) == before + 2
        assert window.problems == []
    finally:
        page.context.close()


@pytest.mark.parametrize("held", ["revision", "workflow"])
def test_validate_escapes_a_dead_read_back_of_a_publish_and_only_its_own_confirms(
        chromium: Browser, flows, held: str) -> None:
    """A publish is accepted and one of the two reads that confirm it -- the
    revision, or the workflow beside it -- never answers. Validate closes that
    socket at once and reads again. The publish is held as unconfirmed through
    the abort -- the retired read settles nothing -- and is announced only by
    the NEW read-back that shows revision 1. One POST.

    Both are needed. A dead REVISION read is swallowed into `null` beside a
    workflow read that already landed, so the retired read returns before its
    failure branch; only a dead WORKFLOW read carries the retirement into that
    branch, where settling the held outcome would lose the publish."""
    bench, stall = flows
    page, window = _open(chromium, bench)
    try:
        _choose(page, WORKFLOW_ID)
        stall.arm(REVISION_PATH if held == "revision" else FLOW_PATH, "headers")
        _publish(page)
        assert stall.entered.wait(10), "the accepted publish read no revision back"
        assert page.locator('#workflowToolbar [data-save="saved"]').count() == 0
        page.locator(VALIDATE).click()
        assert stall.aborted.wait(10), "Validate left the dead read-back open"
        page.wait_for_selector('#workflowToolbar [data-save="saved"]')
        assert stall.count(REVISION_PATH) == 2
        assert stall.posts == [f"{FLOW_PATH}/revisions"]
        assert window.problems == []
    finally:
        page.context.close()
