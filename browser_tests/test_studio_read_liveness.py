"""A read that never answers, and what the Studio's run queue does about it.

P2 of the Codex review of ``3a2bfbd``: one stuck GET held the run queue's busy
latch, so no later read of any run went out -- not a frame's, not a person's
press, not the read of another run they chose. The correction bounds every GET
through its body and aborts it, lets a person's press or a change of run retire
the read in flight, and leaves ordinary frames coalescing as they did.

Every claim here is about a SOCKET or a RECORD, never only about a screen:

- the abort is proved at the server. A test-only ``Handler`` subclass holds one
  GET and watches its socket; an abandoned request closes it, and a
  ``Promise.race`` that only forgot the request would leave it open. That is
  the difference acceptance item 1 names, so it is what is asserted;
- the deadline is driven by ``page.clock``, never waited out: the clock is
  paused once the window has settled and moved by exactly the window's own
  ``READ_DEADLINE``, read out of ``studio.js`` rather than copied here;
- the stream is the lifecycle module's double, so the only reads are the ones a
  test provokes and every count is exact;
- the late outcome of a retired read is the one place a fetch stub is used. It
  fetches without the page's signal, so no abort can reach it and only the
  generation guard stands between that outcome and the screen.

The same bench serves ``browser_tests/test_studio_read_queues.py``: what a queued
frame and a dropped stream do around a dead read, the two lists, and the
workflow queue.
"""
from __future__ import annotations

import re
import select
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.run_store import RunStore

from browser_tests.test_studio_lifecycle import _STREAM_DOUBLE, _Window, _settle
from browser_tests.test_studio_step import (
    ACTOR,
    DIGEST,
    DONE_RUN,
    RUN_ID,
    STEP,
    TOKEN,
    WHY,
    _Bench,
    _read,
    _seed,
    _type,
)
from browser_tests.test_studio_step_races import (
    WRITING,
    _press_anyway,
    _state_of,
    _wait_until_open,
)
from tests.test_command_execution_coordinator import ids, provider_registry
from tests.test_command_graph_projection import a_proposal
from tests.test_store import good_lane, write_project

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
BOOT = (PANEL / "studio.js").read_text(encoding="utf-8")
#: The window's own deadline, read out of the window rather than copied.
DEADLINE = int(re.search(r"^const READ_DEADLINE = (\d+);$", BOOT, re.M).group(1))
#: The sentence an unreadable body used to be laundered into (critic U1).
STORE_ERROR = re.search(
    r'^  store_error: "([^"]*)",$',
    (PANEL / "command-projection.js").read_text(encoding="utf-8"), re.M).group(1)
RUN_PATH = f"/command/runs/{RUN_ID}"
CONTROLS_PATH = f"/command/runs/{RUN_ID}/controls"
PROPOSE = f"propose:{STEP}"
SHUT = ("key => { const b = document.querySelector(`[data-focus-key='${key}']`);"
        " return b !== null && b.disabled; }")
#: One macrotask boundary the paused clock does not own, so every microtask a
#: settled fetch queued has run before the next assertion reads the screen.
TICK = """() => new Promise((done) => {
  const channel = new MessageChannel();
  channel.port1.onmessage = () => done();
  channel.port2.postMessage(0);
})"""


def _sentence(name: str) -> str:
    """One of the boot module's sentence constants, joined as JavaScript joins it."""
    found = re.search(rf'^const {name} = ((?:"[^"\n]*"(?:\s*\+\s*)?)+);$',
                      BOOT, re.M)
    assert found is not None, f"studio.js declares no sentence {name}"
    return "".join(re.findall(r'"([^"\n]*)"', found.group(1)))


# -- the server side: one GET held, and what its socket did ---------------------


class _Stall:
    """GETs held at the server by path, and what each held socket did."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.armed: dict[str, str] = {}
        self.entered = threading.Event()
        self.aborted = threading.Event()
        self.release = threading.Event()
        self.gets: list[str] = []
        self.posts: list[str] = []

    def arm(self, path: str, mode: str) -> None:
        """Hold the NEXT GET of `path`: `headers`, `body` (half sent) or `answer`."""
        self.entered.clear()
        self.aborted.clear()
        self.release.clear()
        with self.lock:
            self.armed[path] = mode

    def take(self, path: str) -> str | None:
        with self.lock:
            return self.armed.pop(path, None)

    def count(self, path: str) -> int:
        return self.gets.count(path)


def _peer_closed(connection: socket.socket) -> bool:
    """True once the browser has closed its end: readable, and nothing to read."""
    readable, _, _ = select.select([connection], [], [], 0.02)
    if not readable:
        return False
    try:
        return connection.recv(1, socket.MSG_PEEK) == b""
    except OSError:
        return True


def _stalling(stall: _Stall) -> type:
    class Stalling(server.Handler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            stall.gets.append(path)
            mode = stall.take(path)
            if mode is None:
                super().do_GET()
                return
            if mode == "body":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", "4096")
                self.end_headers()
                self.wfile.write(b'{"run": {"run_id": ')
                self.wfile.flush()
            stall.entered.set()
            while not stall.release.is_set():
                if _peer_closed(self.connection):
                    stall.aborted.set()
                    self.close_connection = True
                    return
            if mode == "answer":
                super().do_GET()
                return
            self.close_connection = True

        def do_POST(self) -> None:
            stall.posts.append(urlsplit(self.path).path)
            super().do_POST()

    return Stalling


@contextmanager
def _stalling_bench(tmp_path: Path, seed: Callable[[Path], None] | None = None
                    ) -> Iterator[tuple[_Bench, _Stall]]:
    """The step bench, served by a handler that can hold one GET.

    `seed` adds to the project before the server starts: the queues module
    stores the workflows its workflow queue reads through it.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    _seed(root)
    if seed is not None:
        seed(root)
    mint = ids()
    harness = tmp_path / "harness"
    harness.mkdir()
    httpd = server.build(root, 0, registry=provider_registry(harness, mint),
                         ids=mint, token_factory=lambda _size: TOKEN)
    stall = _Stall()
    httpd.RequestHandlerClass = _stalling(stall)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield _Bench(f"http://{host}:{port}/", root), stall
    finally:
        stall.release.set()
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "stalling bench server did not stop"


@pytest.fixture
def stalled(tmp_path) -> Iterator[tuple[_Bench, _Stall]]:
    with _stalling_bench(tmp_path) as bench:
        yield bench


# -- the page side ----------------------------------------------------------------


def _open(chromium: Browser, bench: _Bench) -> tuple[Page, _Window]:
    """The Studio on a stream double, with its clock paused once it has settled."""
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    context.add_init_script(_STREAM_DOUBLE)
    page = context.new_page()
    window = _Window(page)
    page.clock.install()
    page.goto(bench.url, wait_until="load")
    _settle(page)
    now = page.evaluate("() => Date.now()")
    page.clock.pause_at((now + 1000) / 1000)
    return page, window


def _frame(page: Page, run_id: str) -> None:
    """A `run` frame, through the production handler: it only ever queues."""
    page.evaluate(
        "id => window.__stream.emit(JSON.stringify({kind: 'run', run_id: id}))",
        run_id)


def _notice(page: Page) -> str:
    return page.locator("#studioStatus").inner_text()


def _state(page: Page, screen: str) -> str | None:
    return page.locator(f"#screen{screen}").get_attribute("data-state")


def _until(condition: Callable[[], bool], what: str) -> None:
    for _ in range(400):
        if condition():
            return
        time.sleep(0.025)
    raise AssertionError(what)


def _expire(page: Page) -> None:
    """Move the paused clock by exactly the window's deadline, and no further."""
    page.clock.run_for(DEADLINE)


def _items(page: Page) -> int:
    return page.locator("ol.studio-timeline > li").count()


def _more_items_than(page: Page, items: int) -> None:
    page.wait_for_function(
        "n => document.querySelectorAll('ol.studio-timeline > li').length > n",
        arg=items)


# -- 1. the deadline ----------------------------------------------------------------


def test_a_hung_run_read_is_aborted_at_the_deadline_and_frees_the_queue(
        chromium: Browser, stalled) -> None:
    """The run GET never answers. At the deadline its socket is closed by the
    page, the screens say the read FAILED and the notice says so in the
    window's own words, the detail and the words typed against it stay, and the
    NEXT frame -- which only queues -- still reads: the busy latch went with
    the dead read."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        before = stall.count(RUN_PATH)
        stall.arm(RUN_PATH, "headers")
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        assert stall.entered.wait(10), "the press provoked no run read"
        assert not stall.aborted.is_set()
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        page.wait_for_selector('#screenDecisions[data-state="failed"]',
                               state="attached")
        assert _state(page, "Runs") == "failed"
        assert _state(page, "Agents") == "failed"
        assert _notice(page) == _sentence("LATE_SAID")
        assert page.locator(".studio-runs__detail h2").inner_text().strip() == RUN_ID
        assert page.locator(
            '[data-focus-key="field:proposed_by"]').input_value() == ACTOR

        _frame(page, RUN_ID)
        page.wait_for_selector('#screenDecisions[data-state="ready"]',
                               state="attached")
        assert stall.count(RUN_PATH) == before + 2
        assert stall.posts == []
        assert window.problems == []
    finally:
        page.context.close()


#: Make every render pass throw until mended. The reducer has already moved when
#: a render throws, so this is the one way a read's own exit can raise.
BREAK_RENDER = """() => {
  window.kept = Element.prototype.replaceChildren;
  Element.prototype.replaceChildren = function () {
    throw new Error('a render that throws');
  };
}"""
MEND_RENDER = "() => { Element.prototype.replaceChildren = window.kept; }"


def test_a_read_whose_exit_throws_still_hands_the_queue_back(
        chromium: Browser, stalled) -> None:
    """The timed-out read's own dispatch throws. The fault is reported -- it is
    a page error, and exactly one is asserted -- and the run queue is still
    free: the next frame reads, and that read lands."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        before = stall.count(RUN_PATH)
        stall.arm(RUN_PATH, "headers")
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        assert stall.entered.wait(10), "the press provoked no run read"
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
        _frame(page, RUN_ID)
        _until(lambda: stall.count(RUN_PATH) == before + 2,
               "the queue stayed latched behind a read whose exit threw")
        page.wait_for_selector('#screenDecisions[data-state="ready"]',
                               state="attached")
        assert len(window.page_errors) == 1, window.page_errors
        assert window.console_errors == []
    finally:
        page.context.close()


#: Count the run bodies the page has finished reading. The real request and its
#: signal pass through untouched -- this observes and answers nothing -- so the
#: clock can be moved only once the run read has landed, as a real one would.
BODIES_OF = """target => {
  const original = window.fetch.bind(window);
  window.bodies = 0;
  window.fetch = (url, options = {}) => {
    const answer = original(url, options);
    if (new URL(url, location.href).pathname !== target) return answer;
    return answer.then((response) => {
      const read = response.json.bind(response);
      response.json = () => read().then((value) => {
        window.bodies += 1;
        return value;
      });
      return response;
    });
  };
}"""


def test_a_hung_controls_read_is_aborted_and_the_step_stays_shut(
        chromium: Browser, stalled) -> None:
    """The run GET lands and its controls GET never answers. At the deadline
    the controls socket is closed, the run read lands WITHOUT controls, and
    Propose is shut however complete the draft is -- a missing controls read
    reopens nothing. The next frame reads the controls and opens it again.

    The two GETs start in one turn, so their deadlines fall on one fake
    instant: the clock moves only after the run body has been read."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        assert _state_of(page, PROPOSE) == "open"
        page.evaluate(BODIES_OF, RUN_PATH)
        before = stall.count(CONTROLS_PATH)
        stall.arm(CONTROLS_PATH, "headers")
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        assert stall.entered.wait(10), "the press provoked no controls read"
        page.wait_for_function("() => window.bodies > 0")
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        page.wait_for_function(SHUT, arg=PROPOSE)
        assert _state(page, "Decisions") == "ready"
        form = page.locator(f'[data-step="{PROPOSE}"]')
        assert form.locator('[name="proposed_by"]').input_value() == ACTOR
        assert form.locator('[name="rationale"]').input_value() == WHY

        _frame(page, RUN_ID)
        _wait_until_open(page, PROPOSE)
        assert stall.count(CONTROLS_PATH) == before + 2
        assert stall.posts == [] and window.writes("/command") == 0
        assert window.problems == []
    finally:
        page.context.close()


def test_a_hung_json_body_is_aborted_and_keeps_its_timeout_identity(
        chromium: Browser, stalled) -> None:
    """Headers and half a body arrive, and the rest never does. The deadline
    covers the body: the socket is closed, and the screen says the read was
    abandoned -- never that the store is unavailable, which is what a body
    failure used to be laundered into."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        stall.arm(RUN_PATH, "body")
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        assert stall.entered.wait(10), "the press provoked no run read"
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        page.wait_for_selector('#screenDecisions[data-state="failed"]',
                               state="attached")
        assert _notice(page) != STORE_ERROR
        assert _notice(page) == _sentence("LATE_SAID")
        assert window.problems == []
    finally:
        page.context.close()


# -- 2. escaping a dead read --------------------------------------------------------


#: Every press that asks for the CHOSEN run again: the screen it lives on, and
#: the control. The Overview's "Read this run" is not here -- it names the most
#: recent run, which is a change of run unless that happens to be the chosen one.
PRESSES = {
    "header": ("#navDecisions", '#studioPrimary [data-focus="action:onRefreshRun"]'),
    "row": ("#navRuns", f'[data-focus-key="run:{RUN_ID}"]'),
    "decisions-link": ("#navRuns",
                       '#screenRuns [data-focus-key="action:showDecisions"]'),
    "roster": ("#navAgents", '#screenAgents [data-focus-key="action:refreshAgents"]'),
}


@pytest.mark.parametrize("press", sorted(PRESSES))
@pytest.mark.parametrize("held", [RUN_PATH, CONTROLS_PATH], ids=["run", "controls"])
def test_a_press_for_the_same_run_escapes_a_dead_read_without_waiting_for_it(
        chromium: Browser, stalled, held: str, press: str) -> None:
    """A frame's read hangs -- the run GET, or the controls GET beside it --
    and the person presses a control that asks for this run again. The clock
    never moves: the press closes the dead socket, its own read lands -- the
    record appended meanwhile is on screen -- and the words typed stay."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        before = stall.count(held)
        stall.arm(held, "headers")
        _frame(page, RUN_ID)
        assert stall.entered.wait(10), "the frame provoked no held read"
        items = _items(page)
        RunStore(bench.root).append(a_proposal(
            node_id="identify", index=51, run_id=RUN_ID, config_digest=DIGEST))
        screen, control = PRESSES[press]
        page.locator(screen).click()
        page.locator(control).click()
        assert stall.aborted.wait(10), "the press left the dead read's socket open"
        _more_items_than(page, items)
        assert stall.count(held) == before + 2
        assert _state(page, "Decisions") == "ready"
        page.locator("#navRuns").click()
        assert page.locator(
            '[data-focus-key="field:proposed_by"]').input_value() == ACTOR
        assert _sentence("LATE_SAID") not in _notice(page)
        assert window.problems == []
    finally:
        page.context.close()


def test_choosing_another_run_escapes_a_dead_read(
        chromium: Browser, stalled) -> None:
    """A frame's read of run A hangs; the person opens run B. B is read and
    drawn at once, and A's socket is closed rather than left to the deadline."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        stall.arm(RUN_PATH, "headers")
        _frame(page, RUN_ID)
        assert stall.entered.wait(10), "the frame provoked no run read"
        _read(page, DONE_RUN)
        assert stall.aborted.wait(10), "choosing B left A's socket open"
        assert stall.count(f"/command/runs/{DONE_RUN}") == 1
        assert page.locator(
            f'[data-focus-key="run:{DONE_RUN}"]').get_attribute("aria-pressed") == "true"
        assert window.problems == []
    finally:
        page.context.close()


def test_the_overviews_press_for_the_chosen_run_escapes_a_dead_read(
        chromium: Browser, stalled) -> None:
    """The Overview's "Read this run" names the MOST RECENT run. Once that run
    is the chosen one, the press asks for the chosen run again, and it escapes
    a dead read of it like every other press: the socket closes at once and the
    press's own read goes out."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    overview = '#bodyOverview [data-focus="action:onSelectRun"]'
    try:
        page.locator("#navOverview").click()
        page.locator(overview).click()
        page.wait_for_selector(".studio-runs__detail h2")
        chosen = page.locator(".studio-runs__detail h2").inner_text().strip()
        held = f"/command/runs/{chosen}"
        before = stall.count(held)
        stall.arm(held, "headers")
        _frame(page, chosen)
        assert stall.entered.wait(10), "the frame provoked no run read"
        page.locator("#navOverview").click()
        page.locator(overview).click()
        assert stall.aborted.wait(10), "the Overview press left the dead read open"
        _until(lambda: stall.count(held) == before + 2,
               "the Overview press issued no read of its own")
        assert window.problems == []
    finally:
        page.context.close()


#: Hold the FIRST read of one path. The real request is made WITHOUT the page's
#: signal and its bytes are kept, so its outcome can be handed over at an exact
#: moment -- an answer already in hand, which no abort can take back.
HOLD_ONE = """target => {
  const original = window.fetch.bind(window);
  window.late = {held: false, ready: false, settle: null};
  window.fetch = (url, options = {}) => {
    const path = new URL(url, location.href).pathname;
    if (path !== target || window.late.held) return original(url, options);
    window.late.held = true;
    return new Promise((resolve, reject) => {
      original(url, {cache: 'no-store'})
        .then((answer) => answer.arrayBuffer())
        .then((bytes) => {
          window.late.settle = (how) => (how === 'answer'
            ? resolve(new Response(bytes, {status: 200,
              headers: {'Content-Type': 'application/json'}}))
            : reject(new TypeError('a late failure')));
          window.late.ready = true;
        });
    });
  };
}"""
#: In ONE task: watch every detail heading and state word drawn from here on,
#: hand the held read its outcome, and press a run's row. The outcome's
#: continuation cannot run before the press has retired it -- the window in
#: which only the generation guard can keep it off the screen.
LATE_UNDER_A_PRESS = """([how, target]) => {
  window.seen = {heads: [], states: []};
  const heads = (node) => (node.matches && node.matches('.studio-runs__detail h2')
    ? [node] : (node.querySelectorAll
      ? [...node.querySelectorAll('.studio-runs__detail h2')] : []));
  new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === 'attributes') {
        window.seen.states.push(record.target.getAttribute('data-state'));
      }
      for (const node of record.addedNodes) {
        for (const head of heads(node)) window.seen.heads.push(head.textContent);
      }
    }
  }).observe(document.getElementById('studioShell'), {subtree: true,
    childList: true, attributes: true, attributeFilter: ['data-state']});
  window.late.settle(how);
  document.querySelector(`[data-focus-key='run:${target}']`).click();
}"""


@pytest.mark.parametrize(("how", "subject"), [
    ("answer", "other"), ("error", "other"), ("error", "same")])
def test_a_retired_reads_late_answer_or_error_changes_nothing(
        chromium: Browser, stalled, how: str, subject: str) -> None:
    """A's read is held until its answer -- or its failure -- is in hand, and
    it is handed over in the same task as a press: of run B's row, or of A's
    own row again. The press's read is drawn; the retired outcome draws
    nothing on the way, not even for one frame: no heading of A's over B, and
    no stale, refused or failed state word.

    A late ERROR is the case that needed its own same-run row. The window
    tells a person about a deadline passing under a queued frame, and a press
    retiring a read aborts it too -- so only the abort's REASON separates the
    failure a person must be told of from one nobody is waiting for."""
    bench, _stall = stalled
    page, window = _open(chromium, bench)
    target = DONE_RUN if subject == "other" else RUN_ID
    try:
        _read(page, RUN_ID)
        page.evaluate(HOLD_ONE, RUN_PATH)
        _frame(page, RUN_ID)
        page.wait_for_function("() => window.late.ready")
        items = _items(page)
        if subject == "same":
            RunStore(bench.root).append(a_proposal(
                node_id="identify", index=53, run_id=RUN_ID, config_digest=DIGEST))
        page.evaluate(LATE_UNDER_A_PRESS, [how, target])
        if subject == "same":
            _more_items_than(page, items)
        else:
            page.wait_for_function(
                "id => { const h = document.querySelector('.studio-runs__detail h2');"
                " return h !== null && h.textContent.trim() === id; }", arg=target)
        page.evaluate(TICK)
        seen = page.evaluate("() => window.seen")
        if subject == "other":
            assert RUN_ID not in [head.strip() for head in seen["heads"]], seen
        assert not {"stale", "refused", "failed"} & set(seen["states"]), seen
        assert _sentence("LATE_SAID") not in _notice(page)
        assert page.locator(
            f'[data-focus-key="run:{target}"]').get_attribute("aria-pressed") == "true"
        assert window.problems == []
    finally:
        page.context.close()


def test_a_burst_of_frames_under_a_hung_read_queues_one_read_and_aborts_nothing(
        chromium: Browser, stalled) -> None:
    """Six frames for the chosen run while its read is held: one read in
    flight, one queued behind it, and the held socket untouched. Released, the
    queued read follows and nothing else does."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        before, lists = stall.count(RUN_PATH), stall.count("/command/runs")
        stall.arm(RUN_PATH, "answer")
        _frame(page, RUN_ID)
        assert stall.entered.wait(10), "the frame provoked no run read"
        for _ in range(5):
            _frame(page, RUN_ID)
        _until(lambda: stall.count("/command/runs") >= lists + 6,
               "the burst's list reads never reached the server")
        assert stall.count(RUN_PATH) == before + 1
        assert not stall.aborted.is_set(), "a frame aborted the read it should queue behind"

        items = _items(page)
        RunStore(bench.root).append(a_proposal(
            node_id="identify", index=52, run_id=RUN_ID, config_digest=DIGEST))
        stall.release.set()
        _more_items_than(page, items)
        _until(lambda: stall.count(RUN_PATH) >= before + 2,
               "the queued read never followed the released one")
        assert stall.count(RUN_PATH) == before + 2
        assert window.problems == []
    finally:
        page.context.close()


# -- 3. a timeout is not a write's answer --------------------------------------------


def test_an_accepted_proposal_whose_confirming_read_stalls_is_written_exactly_once(
        chromium: Browser, stalled) -> None:
    """The proposal is accepted and the read that would confirm it never
    answers. At the deadline the read is abandoned and NOTHING else happens:
    the person's receipt stands with the window's own sentence beside it, the
    control stays shut and says why, a forced press writes nothing, and no POST
    is replayed. Only a landed read -- the person's own press here -- gives the
    road on. One POST, overall."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        stall.arm(RUN_PATH, "headers")
        with page.expect_response(
                lambda answer: answer.url.endswith("/proposals")) as waited:
            page.locator(f'[data-focus-key="{PROPOSE}"]').click()
        assert waited.value.status == 201, waited.value.json()
        assert stall.entered.wait(10), "the accepted write provoked no read"
        receipt = _notice(page)
        assert receipt and _sentence("LATE_SAID") not in receipt
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        page.wait_for_selector('#screenDecisions[data-state="failed"]',
                               state="attached")
        assert _notice(page) == f"{receipt} {_sentence('LATE_SAID')}"
        assert _state_of(page, PROPOSE) == "shut"
        assert WRITING in page.locator(f'[data-step="{PROPOSE}"]').inner_text()
        _press_anyway(page, PROPOSE)
        assert len(stall.posts) == 1

        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        page.wait_for_selector(f'[data-step="confirm:{STEP}"]')
        assert _state(page, "Decisions") == "ready"
        assert len(stall.posts) == 1
        assert [row[1] for row in window.rows if row[0] == "POST"] == [
            f"{bench.url.rstrip('/')}/command/runs/{RUN_ID}/proposals"]
        assert len(bench.records(RUN_ID, "action_proposal")) == 1
        assert window.problems == []
    finally:
        page.context.close()


def test_a_stalled_session_read_refuses_the_write_and_sends_nothing(
        chromium: Browser, stalled) -> None:
    """The session read a write needs never answers. At the deadline the write
    is refused in words that say this press wrote nothing -- true, because no
    POST left -- the control and the words come back, and the next press
    writes."""
    bench, stall = stalled
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        stall.arm("/command/session", "headers")
        page.locator(f'[data-focus-key="{PROPOSE}"]').click()
        assert stall.entered.wait(10), "the press read no session"
        assert _state_of(page, PROPOSE) == "shut"
        _expire(page)
        assert stall.aborted.wait(10), "the deadline left the socket open"
        _wait_until_open(page, PROPOSE)
        assert _notice(page) == _sentence("UNSENT")
        assert stall.posts == [] and window.writes("/command") == 0
        form = page.locator(f'[data-step="{PROPOSE}"]')
        assert form.locator('[name="proposed_by"]').input_value() == ACTOR
        assert form.locator('[name="rationale"]').input_value() == WHY

        with page.expect_response(
                lambda answer: answer.url.endswith("/proposals")) as waited:
            page.locator(f'[data-focus-key="{PROPOSE}"]').click()
        assert waited.value.status == 201, waited.value.json()
        assert len(stall.posts) == 1
        assert window.problems == []
    finally:
        page.context.close()
