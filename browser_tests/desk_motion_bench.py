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
  the element it was called on, its timing and where the element stood, and every element that
  the motion layer drew. It changes nothing the page does;
* the page is served the product's `desk-scene.js` with the two lines that hand each render to
  the motion module, until the product carries them itself (`wiring`). Those two lines are in a
  file lane D1 writes (`handoffs/D2-to-D1-desk-motion-wiring.md`); the edit is asserted to have
  happened once, and is not made at all the day the product has them.

The windows are closed through `desk_hold.close_context`, because the staged reads are handlers
that fetch. This is a helper and not a test module.
"""
from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page, Route, expect

from browser_tests.desk_hold import Hold, close_context
from browser_tests.desk_settled import SETTLED
from conductor import server
from tests.desk_progress_seed import seed_project
from tests.test_store import good_lane, write_project

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
JS = "text/javascript; charset=utf-8"
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
})();
"""
#: Two animation frames: what a response started has been drawn by then.
QUIET = """() => new Promise((done) => requestAnimationFrame(
  () => requestAnimationFrame(done)))"""
SCENE_IMPORT = 'from "./studio-participants.js";\n'
SCENE_HEAD = "export function mountScene(mount, view, handlers) {\n"
WIRING_IMPORT = 'import {watchMotion} from "./desk-motion.js";\n'
WIRING_CALL = "  watchMotion(view);\n"


def wiring() -> dict[str, bytes]:
    """The modules the page is served with an edit: the scene with the two lines that hand each
    render to the motion module, or nothing once the product carries them (in the scene or in the
    boot module). The edit is asserted to be exactly those two lines, each made once."""
    assert all((PANEL / name).is_file() for name in ("desk-motion.js", "desk-motion-model.js")), (
        "the transitions module is not packaged")
    scene = (PANEL / "desk-scene.js").read_text(encoding="utf-8")
    boot = (PANEL / "desk.js").read_text(encoding="utf-8")
    if "desk-motion.js" in scene or "desk-motion.js" in boot:
        return {}
    assert scene.count(SCENE_IMPORT) == 1 and scene.count(SCENE_HEAD) == 1
    edited = scene.replace(SCENE_IMPORT, SCENE_IMPORT + WIRING_IMPORT)
    edited = edited.replace(SCENE_HEAD, SCENE_HEAD + WIRING_CALL)
    return {"desk-scene.js": edited.encode("utf-8")}


def answering(body: bytes) -> Callable[[Route], None]:
    """A route handler that answers every request it is given with `body`, as a script.

    The handler takes the route alone: the browser hands a handler the route and the request, and
    passes both to one that can take both, so a body kept as a second parameter's default would
    be replaced by the request."""
    return lambda route: route.fulfill(status=200, content_type=JS, body=body)


@dataclass
class Staged:
    """What the test has changed in the project's lists: a patch of one run's row, and tasks."""

    run: dict[str, Any] = field(default_factory=dict)
    tasks: list[dict[str, Any]] = field(default_factory=list)

    def runs(self, body: dict[str, Any]) -> dict[str, Any]:
        for row in body["runs"]:
            if row["run_id"] == RUN:
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


def serve(tmp_path: Path) -> Served:
    root = write_project(tmp_path / "project", lanes={"claude": good_lane()})
    seed_project(root)
    return Served(root)


def open_desk(browser: Browser, served: Served, *, motion: bool, language: str = "en",
              task: str | None = TASK, staged: Staged | None = None) -> Desk:
    """Boot the desk with the preference asked for, wired to the motion module, and wait for the
    stream to be open: the reading the first change is compared with has been taken by then."""
    context = browser.new_context(viewport={"width": 1280, "height": 900},
                                  reduced_motion="no-preference" if motion else "reduce")
    page = context.new_page()
    desk = Desk(page, served, staged or Staged())
    context.add_init_script(INSTRUMENT)
    Hold(page, "**/command/runs").rewrite = desk.staged.runs
    Hold(page, "**/command/tasks").rewrite = desk.staged.task_list
    for name, body in wiring().items():
        page.route(f"**/panel/{name}", answering(body))
    page.on("pageerror", lambda error: desk.problems.append(str(error)))
    page.on("console", lambda message: desk.problems.append(message.text)
            if message.type == "error" else None)
    page.goto(served.url + f"#lang={language}" + ("" if task is None else f"&task={task}"),
              wait_until="load")
    page.wait_for_function(SETTLED)
    expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open", timeout=15000)
    return desk


@contextlib.contextmanager
def window(browser: Browser, served: Served, **options: Any) -> Iterator[Desk]:
    """A booted desk, closed through the helper that leaves no handler's error to the next test."""
    desk = open_desk(browser, served, **options)
    try:
        yield desk
    finally:
        close_context(desk.page.context)
