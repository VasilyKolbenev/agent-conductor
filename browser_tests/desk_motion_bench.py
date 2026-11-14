"""A desk on a real server whose lists a test changes, and the instruments that read what it plays.

The production `server.build` over the project of `tests/desk_progress_seed.py`, one window of a
browser context that either prefers reduced motion or does not, and three things a transition
test needs that a person's eyes would otherwise supply:

* the lists the desk reads (`/command/tasks`, `/command/runs`) are the server's own answers with
  one run's row patched, or one task added, by the test (`Staged`). A real stream frame
  (`publish_state`) then makes the desk read them again, exactly as it would after a change in the
  project. The run the scene draws is the real one, so the scene's participants and gates are the
  real ones;
* an instrument in the page (`INSTRUMENT`) records every call of `Element.prototype.animate` with
  the element it was called on, its timing and where the element stood, every element that the
  motion layer drew, and how many times each path was fetched. It changes nothing the page does;
* the page is served the product's modules as they are. Nothing under `/panel/` is routed,
  rewritten or substituted here, so what runs is the packaged chain `desk.html`, `desk.js`,
  `desk-scene.js`, `desk-motion.js`: the scene hands each render to the motion module itself, or
  nothing moves. Every answer for a file of `/panel/` is kept (`Desk.panel`), so a test can
  compare what the page was served with the file in the package.

A tab the person is not looking at is emulated the way Chromium makes one (`HIDE`, `STARVE`): the
document says `hidden`, sends `visibilitychange`, and the page is given no animation frame until it
comes back. A page that is given no frames and is NOT hidden (the desk in the hub's iframe, scrolled
out of the host's view: `document.hidden` stays false and no event comes) is `STARVE` alone, and
`STEP` gives the held callbacks one frame at a time. The new-task wizard needs no emulation: it is
opened by a press, and what the layer holds when its shell is first drawn is read in
`WIZARD_FIRST_FRAME`.

The windows are closed through `desk_hold.close_context`, because the staged reads are handlers
that fetch. This is a helper and not a test module.
"""
from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page, Response, expect

from browser_tests.desk_hold import Hold, close_context
from browser_tests.desk_settled import SETTLED
from conductor import server
from conductor.command.run_store import RunStore, snapshot_digest
from tests.desk_progress_seed import CHECKER, DOER, Journal, _definition, seed_project
from tests.test_command_run_store import a_run
from tests.test_store import good_lane, write_project

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: The task the scene draws, its newest run, and the title the plaque says.
TASK, RUN, TITLE = "task-working", "run-working", "Fix lost text"
#: What each status of that task needs from its run's row. The server's own row stands for
#: `running` (an attempt in flight); the others patch it into the row that earns their word.
RUN_ROWS: dict[str, dict[str, Any]] = {
    "running": {},
    "not_started": {"open_actions": 0, "last_outcome": None},
    "waiting_you": {"human_state": "required"},
    "outcome_succeeded": {"open_actions": 0},
}
#: A task the project does not have yet, as `GET /command/tasks` spells a row.
NEW_TASK = {"created_at": "2026-09-30T12:00:00Z", "schema_version": 1, "task_id": "task-new",
            "title": "Brand new task", "unreadable": False, "work_scope": "task-new"}
#: The words of the rail for each status, which the plaque repeats after the title.
WORDS = {"en": {"running": "Running", "not_started": "Not started",
                "waiting_you": "Waiting for your decision", "outcome_succeeded": "Succeeded"},
         "ru": {"running": "Идёт", "not_started": "Не запущена",
                "waiting_you": "Ждёт вашего решения", "outcome_succeeded": "Успешно"}}
#: What the page records about itself (it only watches).
INSTRUMENT = """
(() => {
  const seen = {calls: [], added: []};
  window.__fx = seen;
  const real = Element.prototype.animate;
  Element.prototype.animate = function (frames, options) {
    seen.calls.push({fx: this.dataset?.fx ?? this.tagName, duration: options?.duration,
      delay: options?.delay ?? 0, x: parseFloat(this.style?.left), y: parseFloat(this.style?.top),
      inLayer: this.closest?.("#deskMotion") !== null});
    return real.call(this, frames, options);
  };
  new MutationObserver((records) => {
    for (const record of records) for (const node of record.addedNodes) {
      if (node.nodeType === 1 && node.dataset?.fx) seen.added.push(node.dataset.fx);
    }
  }).observe(document, {childList: true, subtree: true});
  const asked = {};
  window.__asked = asked;
  const fetched = window.fetch;
  window.fetch = function (input, init) {
    const path = new URL(input instanceof Request ? input.url : String(input), location.href)
      .pathname;
    asked[path] = (asked[path] ?? 0) + 1;
    return fetched.call(this, input, init);
  };
})();
"""
#: The desk is quiet when the refreshes of its boot have ended. The stream's open and the first
#: frame the server sends on it each make one full refresh, and the desk reads the limits
#: (`/command/quotas`) once as each of them ends and the stream says `open`: the word `open` that
#: the page shows after the first refresh is not yet the end of the second, which a read held a
#: moment later would catch in flight.
BOOTED = "() => (window.__asked['/command/quotas'] ?? 0) >= 2"
#: Two animation frames: what a response started has been drawn by then.
QUIET = """() => new Promise((done) => requestAnimationFrame(
  () => requestAnimationFrame(done)))"""
#: A tab the person is not looking at, the way Chromium makes one: the document says `hidden` and
#: sends `visibilitychange`, and the page is given no animation frame until it is shown again.
#: Neither a second page with `bring_to_front()` nor the CDP emulations can do it (none of them
#: makes `document.visibilityState` `hidden` in the headless Chromium these tests run in), so the
#: two facts a page can see are set by hand: the properties of the document are shadowed by
#: configurable getters, and `requestAnimationFrame` of the page keeps the callbacks it is given
#: (`STARVE`) and runs them in one real frame when the frames come back (`FEED`). The marks
#: `STARVE` counts are the frames asked by `desk-motion.js` itself, told by the stack of the call.
STARVE = """() => {
  if (window.__frames) return;
  const real = window.requestAnimationFrame;
  const frames = {real, held: [], motion: 0};
  window.__frames = frames;
  window.requestAnimationFrame = (call) => {
    if (/\\/desk-motion\\.js/.test(new Error().stack ?? "")) frames.motion += 1;
    frames.held.push(call);
    return 1e9 + frames.held.length;
  };
}"""
FEED = """() => new Promise((done) => {
  const {real, held} = window.__frames;
  delete window.__frames;
  window.requestAnimationFrame = real;
  real.call(window, (time) => {
    for (const call of held.splice(0)) call(time);
    real.call(window, () => real.call(window, () => real.call(window, done)));
  });
})"""
#: One frame for the callbacks held so far, and the page still starved: what they ask for in it (the
#: second frame of a wait, say) is held in its turn. It returns when that frame has run them.
STEP = """() => new Promise((done) => {
  const frames = window.__frames;
  const batch = frames.held.splice(0);
  frames.real.call(window, (time) => {
    for (const call of batch) call(time);
    done();
  });
})"""
HIDE = """() => {
  Object.defineProperty(document, "hidden", {configurable: true, get: () => true});
  Object.defineProperty(document, "visibilityState", {configurable: true, get: () => "hidden"});
  document.dispatchEvent(new Event("visibilitychange"));
  return document.querySelectorAll("#deskMotion [data-fx]").length;
}"""
SHOW = """() => {
  delete document.hidden;
  delete document.visibilityState;
  document.dispatchEvent(new Event("visibilitychange"));
  return document.visibilityState;
}"""
#: What the layer holds at the first frame the page draws with the wizard's shell on the screen:
#: the marks and the plaque of the layer, by name, in `window.__wizardFrame` (`null` until then).
#: It is read in a frame and not in the callback of the observer that sees the shell shown,
#: because the observer of the page is told of the change before the motion module has had its
#: turn after the render; a frame is drawn after both, and a frame is what a person sees.
WIZARD_FIRST_FRAME = """() => {
  const shell = document.getElementById("deskWizard");
  window.__wizardFrame = null;
  new MutationObserver(() => {
    if (shell.hidden) return;
    requestAnimationFrame(() => {
      window.__wizardFrame = window.__wizardFrame ?? [...document.querySelectorAll(
        "#deskMotion [data-fx]")].map((node) => node.dataset.fx);
    });
  }).observe(shell, {attributes: true, attributeFilter: ["hidden"]});
}"""


@dataclass
class Staged:
    """What the test has changed in the project's lists: a patch of one run's row, and tasks."""

    run: dict[str, Any] = field(default_factory=dict)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    #: The run whose row the patch is made to: the task's newest, which is the one the rail reads.
    target: str = RUN

    def runs(self, body: dict[str, Any]) -> dict[str, Any]:
        for row in body["runs"]:
            if row["run_id"] == self.target:
                row.update(self.run)
        return body

    def task_list(self, body: dict[str, Any]) -> dict[str, Any]:
        body["tasks"] = [*body["tasks"], *self.tasks]
        return body

    def stand_at(self, status: str) -> None:
        self.run = dict(RUN_ROWS[status])


class Served:
    """The project server on one port, which can be stopped and started again on the same one."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.httpd = server.build(root, 0)
        self.port = self.httpd.server_address[1]
        self.thread = self._run()

    def _run(self) -> threading.Thread:
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        return thread

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/panel/desk.html"

    def stop(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()
        assert not self.thread.is_alive(), "the project server did not stop"

    def start(self) -> None:
        self.httpd = server.build(self.root, self.port)
        self.thread = self._run()

    def publish(self) -> None:
        """A real state frame on the real stream: every open desk reads its lists again."""
        self.httpd.clients.publish_state()


@dataclass
class Desk:
    """One booted window and the project behind it."""

    page: Page
    served: Served
    staged: Staged
    problems: list[str] = field(default_factory=list)
    #: The latest answer the page got for each file of `/panel/`, by file name.
    panel: dict[str, Response] = field(default_factory=dict)

    def take(self, response: Response) -> None:
        path = urlsplit(response.url).path
        if path.startswith("/panel/"):
            self.panel[path.rsplit("/", 1)[1]] = response

    def listen(self) -> list[tuple[str, str]]:
        """From now on, every request the page makes as (method, path), in the order made."""
        asked: list[tuple[str, str]] = []
        self.page.on("request", lambda request: asked.append(
            (request.method, urlsplit(request.url).path)))
        return asked

    def say(self, status: str, language: str = "en") -> None:
        """Wait until the rail says the word of `status` for the task the scene draws."""
        row = self.page.locator(f'#deskRail [data-task-id="{TASK}"] .desk-task__state')
        expect(row).to_have_text(WORDS[language][status])

    def change(self, status: str, language: str = "en") -> None:
        """The task moves to `status` in the project; a real frame; the rail says it."""
        self.staged.stand_at(status)
        self.served.publish()
        self.say(status, language)

    def fx(self) -> dict[str, list[Any]]:
        return self.page.evaluate("() => window.__fx")

    def plaque(self):
        return self.page.locator("#deskMotion p[data-fx='plaque']")

    def refreshed(self) -> None:
        """One more full refresh is asked of the server and has landed, and the page has had two
        frames to draw it: the desk has read both lists again after everything that was staged,
        so whatever it was going to do about that, it has done."""
        with self.page.expect_response(lambda one: urlsplit(one.url).path == "/command/runs"):
            self.served.publish()
        self.page.evaluate(QUIET)

    # -- a tab the person is not looking at, and frames that do not come ---------------------------
    #
    # While the frames are held (`starve`) the page is asked for none: `QUIET`, `refreshed()` and
    # `wait_for_function` (which polls by frames) would never return, so none of them is called
    # until `feed`. What is judged is judged after the frames are back.

    def starve(self) -> None:
        """From now on the page is given no animation frame."""
        self.page.evaluate(STARVE)

    def feed(self) -> None:
        """The held frames run, and the page has drawn three more."""
        self.page.evaluate(FEED)

    def step(self) -> None:
        """One real frame is given to the callbacks held so far; the page stays starved."""
        self.page.evaluate(STEP)

    def asked_for_frames(self) -> int:
        """How many frames `desk-motion.js` asked for since `starve`. While no frame is given, every
        one of them is still waiting."""
        return self.page.evaluate("() => window.__frames.motion")

    def visible(self) -> bool:
        """Whether the page says its tab is on the screen: the frames are held and the document does
        not say `hidden` (a frame the host scrolled out of sight, as the hub's iframe can be)."""
        return not self.page.evaluate("() => document.hidden")

    def hide(self) -> int:
        """The tab leaves the screen (frames held, the document `hidden`): how many marks and
        plaques stand on the layer the moment the event has been handled."""
        self.starve()
        return self.page.evaluate(HIDE)

    def show(self, frames_first: bool = False) -> None:
        """The tab comes back: the event and then the frames, or the frames and then the event."""
        if frames_first:
            self.feed()
            self.page.evaluate(SHOW)
        else:
            self.page.evaluate(SHOW)
            self.feed()

    def refresh_unseen(self) -> None:
        """One real stream frame, and the scene's read of its run has landed: the desk has drawn
        everything it was going to draw for it, with no frame of the page asked for. The read is
        made after the render that shows the lists, so the response is a mark that the render has
        happened; the scene is `ready` again once the answer has been drawn."""
        controls = f"/command/runs/{RUN}/controls"
        with self.page.expect_response(lambda one: urlsplit(one.url).path == controls):
            self.served.publish()
        expect(self.page.locator("#deskScene")).to_have_attribute("data-state", "ready")

    def change_unseen(self, status: str) -> None:
        """`change`, for a page that is given no frame: the rail says the word of `status`."""
        self.staged.stand_at(status)
        self.refresh_unseen()
        self.say(status)


def serve(tmp_path: Path) -> Served:
    root = write_project(tmp_path / "project", lanes={"claude": good_lane()})
    seed_project(root)
    return Served(root)


def add_run(root: Path, run_id: str, task_id: str, created_at: str) -> None:
    """A second run of a task, still in flight, made like the seed's own (`seed_project`). With a
    `created_at` later than the seed's it is the task's NEWEST run: the one the rail reads, and not
    the one a desk opened on `run=` of an older one draws."""
    config = {"cycle": {"id": "default-orbit"}, "task": {"id": task_id, "work_scope": task_id},
              "instances": [{"id": DOER, "adapter": "claude-code"},
                            {"id": CHECKER, "adapter": "codex-cli"}]}
    digest = snapshot_digest(config)
    store = RunStore(root)
    store.create_run(a_run(run_id=run_id, mode="confirm", config_digest=digest,
                           created_at=created_at), config)
    store.append(_definition(run_id))
    journal = Journal(store, run_id, digest, 400)
    journal.brief()
    journal.analyse()
    journal.decide("gate-confirm-do", "approve", "Reviewed the plan.")
    journal.do(outcome=None)


def open_desk(browser: Browser, served: Served, *, motion: bool, language: str = "en",
              task: str | None = TASK, run: str | None = None,
              staged: Staged | None = None) -> Desk:
    """Boot the desk as the product serves it, with the preference asked for, and wait for the
    stream to be open and for the refreshes of the boot to have ended (`BOOTED`): the reading the
    first change is compared with has been taken by then, and no read of the boot is still out.
    `run` is the run the address asks the scene to draw (the task's newest when it is left out)."""
    context = browser.new_context(viewport={"width": 1280, "height": 900},
                                  reduced_motion="no-preference" if motion else "reduce")
    page = context.new_page()
    desk = Desk(page, served, staged or Staged())
    context.add_init_script(INSTRUMENT)
    Hold(page, "**/command/runs").rewrite = desk.staged.runs
    Hold(page, "**/command/tasks").rewrite = desk.staged.task_list
    page.on("response", desk.take)
    page.on("pageerror", lambda error: desk.problems.append(str(error)))
    page.on("console", lambda message: desk.problems.append(message.text)
            if message.type == "error" else None)
    page.goto(served.url + f"#lang={language}" + ("" if task is None else f"&task={task}")
              + ("" if run is None else f"&run={run}"), wait_until="load")
    page.wait_for_function(SETTLED)
    expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open", timeout=15000)
    page.wait_for_function(BOOTED)
    page.evaluate(QUIET)
    return desk


@contextlib.contextmanager
def window(browser: Browser, served: Served, **options: Any) -> Iterator[Desk]:
    """A booted desk, closed through the helper that leaves no handler's error to the next test."""
    desk = open_desk(browser, served, **options)
    try:
        yield desk
    finally:
        close_context(desk.page.context)
