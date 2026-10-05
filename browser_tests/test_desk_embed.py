"""Embed mode in a real Chromium: a desk framed by a page of another origin, as a hub frames it.

A host page on one loopback origin frames the desk of a seeded one-project server (built with
that origin as its `hub_origin`, so the frame policy admits it, and served AS the project the
hashes name, so its own check of the claim header and its own answer to the claim read are the
real ones) in the sandbox spec 4.5.5 gives a hub's iframe. The desk's project claim
(`GET /command/project`) is the first read of every window (spec 4.5.1); the tests answer it in
the page where a test is about a claim the real server would not give.

What this module holds, each as a measurement of the page and not a reading of source:

- a framed desk whose hash says `embed=hub` and whose claim agrees tells the host where it is
  by `postMessage`, at the host's origin: its `origin` is the desk's, its `source` is the frame,
  its data is exactly `{kind, project_id, task_id, run_id}`, and a change of what the desk draws
  sends the next one (RU and EN);
- the origin it posts to is the one the claim named, and nothing else: a claim naming another
  origin reaches the host with nothing, though the desk is embedded (the witness that the target
  is not the wildcard);
- a hash the hub sets by `location.replace` selects without a reload and is announced;
- every condition of embed alone keeps it off: no or a bad `hub_origin`, a refused read, a route
  that does not exist, no `project` in the hash, a repeated `embed`, and a window that is not
  framed -- and the claim is read once, first, by every window, framed or not;
- a claim that names another project (or none) is not one more reason for embed to stay off: it
  is the terminal state "open for another project" (spec 4.5.1), which the desk enters once,
  asks and says nothing after, and never leaves; the lists are not even asked while the claim
  is out;
- the desk listens for nothing the host posts, and a desk that has gone foreign sends nothing.

A fact and its sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit

import pytest
from playwright.sync_api import Browser, Frame, Page, Request, Route

from browser_tests.desk_flag_fake import FlagServer
from browser_tests.desk_identity import identify
from browser_tests.test_desk_hash import (
    FACTS, INIT, ON_RUN, QUIET, PROJECT_A as PROJECT, PROJECT_B, _foreign)
from browser_tests.desk_settled import SETTLED, shell_is
from browser_tests.test_desk_rail_scene import _seed
from conductor import server
from tests.test_store import good_lane, write_project

#: The hub's iframe attributes of spec 4.5.5: forms and same-origin are what a desk needs.
SANDBOX = ("allow-scripts allow-same-origin allow-forms allow-popups "
           "allow-popups-to-escape-sandbox")
HOST_PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>host</title></head><body>
<iframe id="desk" title="desk" sandbox="{SANDBOX}" style="width:1280px;height:900px"></iframe>
<script>
window.__messages = [];
window.addEventListener("message", (event) => {{
  const frame = document.getElementById("desk");
  window.__messages.push({{origin: event.origin, fromFrame: event.source === frame.contentWindow,
    data: event.data, keys: event.data && typeof event.data === "object"
      ? Object.keys(event.data).sort() : null}});
}});
document.getElementById("desk").src = decodeURIComponent(location.hash.slice(1));
</script></body></html>
"""
FOUR_KEYS = ["kind", "project_id", "run_id", "task_id"]
#: The one place the desk stands before it draws anything, and the two it stands at after a task
#: is chosen: the task read, then the run drawn.
NOWHERE = {"kind": "desk-location", "project_id": PROJECT, "task_id": None, "run_id": None}


def _where(task: str | None, run: str | None) -> dict:
    return {"kind": "desk-location", "project_id": PROJECT, "task_id": task, "run_id": run}


@dataclass
class Rig:
    """The origins of the host page and of the desk it frames."""

    host_origin: str
    desk_origin: str
    desk_url: str

    @property
    def host_url(self) -> str:
        return f"{self.host_origin}/host.html"


class _Host(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (the server's name for it)
        found = self.path.split("#")[0] == "/host.html"
        body = HOST_PAGE.encode("utf-8") if found else b"not found"
        self.send_response(200 if found else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


@pytest.fixture(scope="session")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    """A host page and a desk server that names the host as its hub."""
    host = ThreadingHTTPServer(("127.0.0.1", 0), _Host)
    host_thread = threading.Thread(target=host.serve_forever, daemon=True)
    host_thread.start()
    host_origin = f"http://127.0.0.1:{host.server_address[1]}"
    root = write_project(tmp_path_factory.mktemp("desk-embed"), lanes={"claude": good_lane()})
    _seed(root)
    desk = server.build(root, 0, hub_origin=host_origin)
    identify(desk, PROJECT, hub_origin=host_origin)
    desk_thread = threading.Thread(target=desk.serve_forever, daemon=True)
    desk_thread.start()
    desk_origin = f"http://127.0.0.1:{desk.server_address[1]}"
    try:
        yield Rig(host_origin, desk_origin, f"{desk_origin}/panel/desk.html")
    finally:
        for httpd, thread in ((desk, desk_thread), (host, host_thread)):
            httpd.shutdown()
            thread.join(timeout=5)
            httpd.server_close()
            assert not thread.is_alive(), "a server did not stop"


def _claim(*, hub_origin: str | None, project_id: str | None = PROJECT) -> dict:
    """The body of `GET /command/project` as spec 4.5.1 gives it."""
    return {"project_id": project_id, "hub_origin": hub_origin, "demo": False, "mode": "active"}


def _answering(body: dict, status: int = 200) -> Callable[[Route], None]:
    """A route handler for `GET /command/project` that answers with `body`."""
    return lambda route: route.fulfill(status=status, content_type="application/json",
                                       body=json.dumps(body))


@dataclass
class Embedded:
    """One host page, the desk in its frame, and what the desk asked and said."""

    page: Page
    frame: Frame
    problems: list[str] = field(default_factory=list)
    asked: list[tuple[str, str, bool]] = field(default_factory=list)

    def messages(self) -> list[dict]:
        return self.page.evaluate("() => window.__messages")

    def wait_for_messages(self, count: int) -> list[dict]:
        self.page.wait_for_function("(n) => window.__messages.length >= n", arg=count)
        return self.messages()

    def settle(self) -> list[dict]:
        """Everything the desk has posted so far: two frames in the desk, then two in the host."""
        self.frame.evaluate(QUIET)
        self.page.evaluate(QUIET)
        return self.messages()

    def claim_reads(self) -> int:
        return sum(path == "/command/project" for _method, path, _header in self.asked)

    def command_paths(self) -> list[str]:
        """Every `/command/` route the desk asked, in order."""
        return [path for _method, path, _header in self.asked if path.startswith("/command/")]


@pytest.fixture
def embed(chromium: Browser, rig: Rig) -> Iterator[Callable[..., Embedded]]:
    """A factory of framed desks, each closed when the test is over."""
    opened: list[Embedded] = []

    def make(fragment: str, claim: Callable[[Route], None] | None = None, *,
             before: Callable[[Page], None] | None = None, wait: bool = True,
             flag: FlagServer | None = None,
             automations: dict[str, dict] | None = None) -> Embedded:
        context = chromium.new_context(viewport={"width": 1400, "height": 1000},
                                       timezone_id="UTC")
        page = context.new_page()
        problems, asked = _listen(page, rig)
        page.add_init_script(INIT)
        if before is not None:
            before(page)
        if claim is not None:
            page.route("**/command/project", claim)
        # The flag's routes are answered in the page: they are not served by this branch yet.
        page.route("**/command/project/auto-continue", (flag or FlagServer()).handle)
        for run, body in (automations or {}).items():
            page.route(f"**/command/runs/{run}/automation", _answering(body))
        page.goto(f"{rig.host_url}#{quote(rig.desk_url + fragment, safe='')}",
                  wait_until="load")
        frame = page.query_selector("#desk").content_frame()
        if wait:
            frame.wait_for_selector("#deskShell")
            frame.wait_for_function(SETTLED)
        opened.append(Embedded(page, frame, problems, asked))
        return opened[-1]

    yield make
    for window in opened:
        window.page.context.close()


def _listen(page: Page, rig: Rig) -> tuple[list[str], list[tuple[str, str, bool]]]:
    """Collect console errors and uncaught exceptions, and every request the DESK's origin
    answered (its method, path and whether it carried the project header)."""
    problems: list[str] = []
    asked: list[tuple[str, str, bool]] = []
    # These cases attribute reads to host messages and hash navigation. Keep SSE
    # deliberately closed; live refresh/reconnect has separate server witnesses.
    page.route("**/events", lambda route: route.fulfill(status=204))
    page.on("console", lambda message: problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.on("request", lambda request: _note(asked, request, rig))
    return problems, asked


def _note(asked: list[tuple[str, str, bool]], request: Request, rig: Rig) -> None:
    parts = urlsplit(request.url)
    if f"{parts.scheme}://{parts.netloc}" == rig.desk_origin:
        asked.append((request.method, parts.path, "x-conduct-project" in request.headers))


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_framed_desk_tells_its_hub_where_it_is_and_only_where_it_is(
        embed, rig, language):
    window = embed(f"#project={PROJECT}&embed=hub&lang={language}",
                   _answering(_claim(hub_origin=rig.host_origin)))
    window.wait_for_messages(1)
    window.frame.locator('#deskRail [data-task-id="task-fix"]').click()
    window.frame.wait_for_function(ON_RUN, arg="run-fix-new")
    window.wait_for_messages(3)
    messages = window.settle()
    assert [message["data"] for message in messages] == [
        NOWHERE, _where("task-fix", None), _where("task-fix", "run-fix-new")]
    assert all(message["origin"] == rig.desk_origin and message["fromFrame"]
               and message["keys"] == FOUR_KEYS for message in messages)
    assert window.frame.evaluate("() => [document.documentElement.lang, location.hash]") == [
        language, f"#project={PROJECT}&embed=hub&task=task-fix&run=run-fix-new&lang={language}"]
    assert window.problems == []


def test_a_selection_the_hash_makes_at_load_is_announced_as_it_lands(embed, rig):
    window = embed(f"#project={PROJECT}&embed=hub&task=task-docs&run=run-docs&lang=en",
                   _answering(_claim(hub_origin=rig.host_origin)))
    window.frame.wait_for_function(ON_RUN, arg="run-docs")
    window.wait_for_messages(1)
    window.page.wait_for_function(
        "() => window.__messages.at(-1)?.data.run_id === 'run-docs'")
    messages = [message["data"] for message in window.settle()]
    assert messages[-1] == _where("task-docs", "run-docs")
    assert all(message in (NOWHERE, _where("task-docs", None), _where("task-docs", "run-docs"))
               for message in messages)
    assert all(left != right for left, right in zip(messages, messages[1:]))
    assert window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_location_replace_from_the_hub_selects_without_a_reload_and_is_announced(
        embed, rig, language):
    window = embed(f"#project={PROJECT}&embed=hub&lang={language}",
                   _answering(_claim(hub_origin=rig.host_origin)))
    window.wait_for_messages(1)
    marker = window.frame.evaluate("window.__marker")
    window.page.evaluate(
        "(url) => document.getElementById('desk').contentWindow.location.replace(url)",
        f"{rig.desk_url}#project={PROJECT}&embed=hub&task=task-docs&lang={language}")
    window.frame.wait_for_function(ON_RUN, arg="run-docs")
    window.page.wait_for_function(
        "() => window.__messages.at(-1)?.data.run_id === 'run-docs'")
    messages = [message["data"] for message in window.settle()]
    assert messages == [NOWHERE, _where("task-docs", None), _where("task-docs", "run-docs")]
    assert window.frame.evaluate("() => [window.__marker, window.__hashchanges]") == [marker, 1]
    assert window.problems == []


def test_the_message_goes_only_to_the_origin_the_claim_names(embed):
    """The claim names an origin that is not the host's: the desk is embedded all the same,
    and the host receives nothing. A desk that posted to the wildcard would reach it."""
    window = embed(f"#project={PROJECT}&embed=hub&lang=en",
                   _answering(_claim(hub_origin="http://127.0.0.1:1")))
    window.frame.locator('#deskRail [data-task-id="task-fix"]').click()
    window.frame.wait_for_function(ON_RUN, arg="run-fix-new")
    assert window.settle() == []
    assert "embed=hub" in window.frame.evaluate("location.hash")
    assert window.problems == []


#: (row, the address, the answer to the claim read). Each row is ONE reason embed stays off; the
#: host must receive nothing and the desk must drop `embed`. The claim is read in every row.
STAYS_OFF = (
    ("the-claim-has-no-hub-origin", f"#project={PROJECT}&embed=hub&lang=en",
     lambda rig: _answering(_claim(hub_origin=None))),
    ("the-claim-has-a-badly-formed-origin", f"#project={PROJECT}&embed=hub&lang=en",
     lambda rig: _answering(_claim(hub_origin="http://localhost:7700"))),
    ("the-read-is-refused", f"#project={PROJECT}&embed=hub&lang=en",
     lambda rig: _answering({"error": {"code": "same_origin_denied"}}, 403)),
    ("the-route-does-not-exist", f"#project={PROJECT}&embed=hub&lang=en",
     lambda rig: _answering({"error": {"code": "route_not_found"}}, 404)),
    ("the-address-carries-no-project", "#embed=hub&lang=en",
     lambda rig: _answering(_claim(hub_origin=rig.host_origin))),
    ("the-address-repeats-embed", f"#project={PROJECT}&embed=hub&embed=hub&lang=en",
     lambda rig: _answering(_claim(hub_origin=rig.host_origin))),
    ("the-address-asks-for-another-embed", f"#project={PROJECT}&embed=parent&lang=en",
     lambda rig: _answering(_claim(hub_origin=rig.host_origin))),
)


@pytest.mark.parametrize("fragment,claim", [pytest.param(row[1], row[2], id=row[0])
                                            for row in STAYS_OFF])
def test_embed_stays_off_and_nothing_is_sent_when_any_one_of_its_conditions_fails(
        embed, rig, fragment, claim):
    window = embed(fragment, claim(rig))
    window.frame.locator('#deskRail [data-task-id="task-fix"]').click()
    window.frame.wait_for_function(ON_RUN, arg="run-fix-new")
    assert window.settle() == []
    assert window.claim_reads() == 1
    address, shell = window.frame.evaluate("""() => [location.hash,
      document.getElementById('deskShell').getAttribute('data-state')]""")
    assert "embed" not in address and shell == "ready"
    # A refused read and a missing route are logged by the browser as failed resource loads.
    assert [text for text in window.problems if "Failed to load resource" not in text] == []


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("named", [PROJECT_B, None], ids=["another-project", "no-project"])
def test_a_claim_naming_another_project_leaves_a_framed_desk_foreign_with_no_message_and_no_read(
        embed, rig, language, named):
    """The stale-iframe-on-a-reused-port case (spec 4.5.1). The claim's answer is held: until it
    is given the desk has asked for nothing else and said nothing to the hub. It is then
    released, naming a project that is not the hash's, and the desk ends having asked for no
    list at all."""
    held: list[Route] = []
    opened = f"#project={PROJECT}&embed=hub&task=task-fix&lang={language}"
    window = embed(opened, lambda route: held.append(route), wait=False)
    for _frames in range(30):  # a bounded wait for the request to be made
        if held:
            break
        window.frame.evaluate(QUIET)
    assert len(held) == 1 and window.settle() == []
    assert window.command_paths() == ["/command/project"]
    held[0].fulfill(status=200, content_type="application/json",
                    body=json.dumps(_claim(project_id=named, hub_origin=rig.host_origin)))
    window.frame.wait_for_function(shell_is("refused"))
    window.frame.evaluate(QUIET)
    facts = window.frame.evaluate(FACTS)
    _foreign(facts, language)
    assert facts["hash"] == opened
    # Terminal: a hash the same project's hub would send now moves nothing and asks nothing.
    window.frame.evaluate("(hash) => location.replace(location.href.split('#')[0] + hash)",
                          f"#project={PROJECT}&embed=hub&task=task-docs&lang={language}")
    window.frame.evaluate(QUIET)
    _foreign(window.frame.evaluate(FACTS), language)
    assert window.settle() == [] and window.command_paths() == ["/command/project"]
    assert window.problems == []


def test_a_desk_that_is_not_framed_reads_the_claim_like_any_window_and_drops_embed(
        chromium: Browser, rig):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    problems, asked = _listen(page, rig)
    window = Embedded(page, page.main_frame, problems, asked)
    try:
        page.goto(f"{rig.desk_url}#project={PROJECT}&embed=hub&lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        page.locator('#deskRail [data-task-id="task-fix"]').click()
        page.wait_for_function(ON_RUN, arg="run-fix-new")
        assert page.evaluate("() => [window.parent === window, location.hash]") == [
            True, f"#project={PROJECT}&task=task-fix&run=run-fix-new&lang=en"]
    finally:
        context.close()
    assert window.claim_reads() == 1 and problems == []


def test_a_framed_desk_reads_the_claim_once_with_a_get_and_every_command_carries_the_project(
        embed, rig):
    window = embed(f"#project={PROJECT}&embed=hub&lang=en",
                   _answering(_claim(hub_origin=rig.host_origin)))
    window.wait_for_messages(1)
    window.frame.wait_for_function(SETTLED)
    assert window.claim_reads() == 1
    assert {method for method, _path, _header in window.asked} == {"GET"}
    commands = [header for _method, path, header in window.asked if path.startswith("/command/")]
    assert commands and all(commands)
    assert window.frame.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]


def test_a_message_the_host_posts_changes_nothing_and_starts_no_read(embed, rig):
    window = embed(f"#project={PROJECT}&embed=hub&lang=en",
                   _answering(_claim(hub_origin=rig.host_origin)))
    window.wait_for_messages(1)
    before, sent = len(window.asked), len(window.settle())
    window.page.evaluate("""(project) => {
      const target = document.getElementById("desk").contentWindow;
      target.postMessage({kind: "desk-navigate", task_id: "task-docs"}, "*");
      target.postMessage({kind: "desk-location", project_id: project, task_id: "task-docs",
        run_id: "run-docs"}, "*");
      target.postMessage("task=task-docs", "*");
    }""", PROJECT)
    messages = window.settle()
    facts = window.frame.evaluate("""() => ({hash: location.hash,
      chosen: document.querySelectorAll('#deskRail [aria-pressed="true"]').length})""")
    assert len(messages) == sent and len(window.asked) == before
    assert facts == {"hash": f"#project={PROJECT}&embed=hub&lang=en", "chosen": 0}
    assert window.problems == []


def test_a_desk_that_has_gone_foreign_says_nothing_more_to_its_hub(embed, rig):
    window = embed(f"#project={PROJECT}&embed=hub&task=task-fix&lang=en",
                   _answering(_claim(hub_origin=rig.host_origin)))
    window.frame.wait_for_function(ON_RUN, arg="run-fix-new")
    window.page.wait_for_function(
        "() => window.__messages.at(-1)?.data.run_id === 'run-fix-new'")
    sent = len(window.settle())
    window.page.evaluate(
        "(url) => document.getElementById('desk').contentWindow.location.replace(url)",
        f"{rig.desk_url}#project={PROJECT_B}&embed=hub&task=task-docs&lang=en")
    window.frame.wait_for_function(shell_is("refused"))
    assert len(window.settle()) == sent
    assert window.problems == []
