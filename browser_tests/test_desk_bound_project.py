"""The desk binds to its project before it reads anything else, in a real Chromium (spec 4.5.1).

The desk is booted on the production server's seeded one-project directory, and the `/command/*`
answers the tests care about are given in the page: the project claim above all, and the refusals
of the routes a mismatch may come from. Every other answer is the real server's, forwarded with
the claim header taken off (this server serves no identified project), after the header has been
counted on the way out. What this module holds, each as a measurement of the page:

- the first request of every window is `GET /command/project`, and nothing else is asked until
  it has answered; it is asked once;
- a project in the hash, or the one the server names when the hash names none, is claimed by
  every later request; a window bound to nothing sends no header, and the address the desk
  keeps is never given a project the hub did not write;
- a claim that names another project (an id that differs, or `null` against an id), and a
  `409 project_mismatch` on any read, end the desk in the state "open for another project": one
  sentence, a Reload button of the touch size, the regions empty, and no request after it; the
  button reloads the document, and the new document asks the claim again;
- a claim read that fails some other way (a route that is not there, a refusal, a body that is not
  a claim, no answer) leaves the desk running on what its hash said;
- the mode the claim names is the desk's mode in every window, framed or not.

The two doors of the transport themselves are held in `test_desk_binding.py`. A fact and its
sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Route

from browser_tests.desk_identity import identified_server
from browser_tests.desk_settled import FOREIGN_SAID, SETTLED
from browser_tests.test_desk_binding import HEADER, PROJECT_A, PROJECT_B, _json
from browser_tests.test_desk_rail_scene import _seed, seeded_url  # noqa: F401  (a fixture)
from tests.test_store import good_lane, write_project

#: Two animation frames: whatever a handler does before its first real wait has been done, and
#: any request it made has been asked. A frame boundary, never a clock.
QUIET = """() => new Promise((done) => requestAnimationFrame(
  () => requestAnimationFrame(done)))"""
FOREIGN = {"en": "This desk is open for another project. Reload the page to continue.",
           "ru": "Стол открыт для другого проекта. Перезагрузите страницу, чтобы продолжить."}
RELOAD = {"en": "Reload", "ru": "Перезагрузить"}
INIT = "window.__marker = Math.random();"
#: Everything a test asks of the page about the terminal state, in one evaluation.
FOREIGN_FACTS = """() => {
  const button = document.querySelector("#deskScene button");
  const box = button ? button.getBoundingClientRect() : null;
  return {
    shell: document.getElementById("deskShell").getAttribute("data-state"),
    said: document.getElementById("deskStatus").innerText.trim(),
    plate: [...document.getElementById("deskScene").children].map((one) => one.innerText.trim()),
    button: button ? button.textContent : null,
    box: box ? [Math.round(box.width), Math.round(box.height)] : null,
    rail: document.getElementById("deskRail").childElementCount,
    pult: document.getElementById("deskPult").childElementCount,
    marker: window.__marker};
}"""
MISMATCH = (409, {"error": {"code": "project_mismatch",
                            "message": "this server serves another project", "detail": {}}})
#: What a test may say about a route: a (status, body) answer, `"hold"` to keep the request
#: until the test lets it go, or `"abort"` for a request that never gets an answer.
Answer = tuple[int, object] | str


def claim(project_id: str | None, mode: str = "active") -> dict:
    """The body of `GET /command/project` (spec 4.5.1)."""
    return {"project_id": project_id, "hub_origin": None, "demo": False, "mode": mode}


@dataclass
class Desk:
    """One booted desk window, everything it asked, and the routes it held back."""

    page: Page
    wire: list[tuple[str, str, list[str]]] = field(default_factory=list)
    held: list[Route] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def paths(self) -> list[str]:
        return [path for _method, path, _claims in self.wire]

    def claims(self) -> list[list[str]]:
        return [claims for _method, _path, claims in self.wire]


@pytest.fixture
def open_desk(chromium: Browser, seeded_url: str) -> Iterator[Callable[..., Desk]]:  # noqa: F811
    """A factory of desk windows on the seeded server, with its `/command/*` answers given."""
    contexts = []

    def make(fragment: str = "", *, answers: dict[str, Answer] | None = None,
             wait: bool = True) -> Desk:
        context = chromium.new_context(viewport={"width": 1280, "height": 900})
        contexts.append(context)
        page = context.new_page()
        desk = Desk(page)
        given = answers or {}
        page.on("console", lambda message: desk.problems.append(message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: desk.problems.append(str(error)))
        page.add_init_script(INIT)

        def handle(route: Route) -> None:
            request = route.request
            path = urlsplit(request.url).path
            claims = [one["value"] for one in request.headers_array()
                      if one["name"].lower() == HEADER]
            desk.wire.append((request.method, path, claims))
            said = given.get(path)
            if said == "hold":
                desk.held.append(route)
            elif said == "abort":
                route.abort()
            elif said is not None:
                _json(route, said[1], said[0])
            else:
                # The real data, without the claim: this server serves no identified project.
                route.continue_(headers={name: value for name, value in request.headers.items()
                                         if name.lower() != HEADER})

        page.route("**/command/**", handle)
        page.goto(f"{seeded_url}{fragment}", wait_until="load")
        if wait:
            page.wait_for_function(SETTLED)
        return desk

    yield make
    for context in contexts:
        context.close()


def _quiet(page: Page) -> None:
    page.evaluate(QUIET)


def _replace(page: Page, fragment: str) -> None:
    """What the hub does to a mounted desk: replace the address, changing only the fragment."""
    page.evaluate("(hash) => location.replace(location.href.split('#')[0] + hash)", fragment)


def test_the_first_request_of_every_window_is_the_claim_and_nothing_is_asked_before_it_answers(
        open_desk):
    desk = open_desk("#lang=en", answers={"/command/project": "hold"}, wait=False)
    for _frames in range(30):  # a bounded wait for the request to be made
        if desk.held:
            break
        _quiet(desk.page)
    _quiet(desk.page)
    assert desk.paths() == ["/command/project"], desk.paths()
    assert len(desk.held) == 1
    desk.held[0].fulfill(status=200, content_type="application/json",
                         body=json.dumps(claim(None)))
    desk.page.wait_for_function(SETTLED)
    assert desk.paths()[:3] == ["/command/project", "/command/tasks", "/command/runs"]
    assert desk.paths().count("/command/project") == 1
    assert desk.problems == []


def test_a_project_in_the_hash_is_claimed_by_every_later_request_of_the_window(open_desk):
    desk = open_desk(f"#project={PROJECT_A}&lang=en",
                     answers={"/command/project": (200, claim(PROJECT_A))})
    desk.page.locator('#deskRail [data-task-id="task-fix"]').click()
    desk.page.wait_for_function(
        "() => document.querySelector('#deskScene [data-deck-run]') !== null")
    assert desk.paths()[0] == "/command/project"
    assert desk.claims() == [[PROJECT_A]] * len(desk.wire)
    assert {"/command/tasks", "/command/runs", "/command/runs/run-fix-new",
            "/command/runs/run-fix-new/controls"} <= set(desk.paths())
    assert desk.problems == []


def test_a_window_the_server_binds_to_nothing_sends_no_claim(open_desk):
    desk = open_desk("#lang=en")
    assert desk.claims() == [[]] * len(desk.wire)
    assert desk.paths()[0] == "/command/project"
    assert desk.problems == []


def test_a_window_with_no_project_in_its_hash_claims_the_one_the_server_names(open_desk):
    desk = open_desk("#lang=en", answers={"/command/project": (200, claim(PROJECT_B))})
    assert desk.claims()[0] == []
    assert desk.claims()[1:] == [[PROJECT_B]] * (len(desk.wire) - 1)
    hub_wrote_none = desk.page.evaluate("() => location.hash")
    assert hub_wrote_none == "#lang=en", "the desk wrote a project the hub did not write"
    assert desk.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("named", [PROJECT_B, None], ids=["another-id", "no-id"])
def test_a_claim_that_names_another_project_ends_the_desk_with_a_way_out(
        open_desk, language, named):
    desk = open_desk(f"#project={PROJECT_A}&lang={language}",
                     answers={"/command/project": (200, claim(named))})
    facts = desk.page.evaluate(FOREIGN_FACTS)
    assert facts["shell"] == "refused" and facts["said"] == FOREIGN[language]
    assert facts["plate"] == [FOREIGN[language], RELOAD[language]]
    assert facts["button"] == RELOAD[language]
    assert facts["box"][0] >= 44 and facts["box"][1] >= 44
    assert (facts["rail"], facts["pult"]) == (0, 0)
    _quiet(desk.page)
    assert desk.paths() == ["/command/project"]
    assert desk.problems == []


#: The routes whose refusal ends the desk, each with the press (if any) that asks for it.
MISMATCHED = (
    ("/command/tasks", None), ("/command/runs", None),
    ("/command/runs/run-fix-new/automation", None),
    ("/command/runs/run-fix-new", "task-fix"),
    ("/command/runs/run-fix-new/controls", "task-fix"),
)


@pytest.mark.parametrize("route,press", MISMATCHED, ids=[row[0] for row in MISMATCHED])
def test_a_project_mismatch_on_any_answer_ends_the_desk_and_nothing_is_asked_after(
        open_desk, route, press):
    desk = open_desk(f"#project={PROJECT_A}&lang=en", answers={
        "/command/project": (200, claim(PROJECT_A)), route: MISMATCH}, wait=press is None)
    if press is not None:
        desk.page.wait_for_function(SETTLED)
        desk.page.locator(f'#deskRail [data-task-id="{press}"]').click()
    desk.page.wait_for_function(FOREIGN_SAID)
    facts = desk.page.evaluate(FOREIGN_FACTS)
    assert facts["shell"] == "refused" and facts["button"] == RELOAD["en"]
    asked = len(desk.wire)
    _quiet(desk.page)
    assert len(desk.wire) == asked
    if route in ("/command/tasks", "/command/runs"):  # a list was refused: no run is asked about
        assert not [path for path in desk.paths() if path.endswith("/automation")]
    assert all("409" in text for text in desk.problems), desk.problems


def test_a_press_on_the_reload_button_reloads_the_document_and_asks_the_claim_again(open_desk):
    desk = open_desk(f"#project={PROJECT_A}&lang=en",
                     answers={"/command/project": (200, claim(PROJECT_B))})
    before = desk.page.evaluate(FOREIGN_FACTS)["marker"]
    with desk.page.expect_navigation():
        desk.page.locator("#deskScene button").click()
    desk.page.wait_for_function(SETTLED)
    assert desk.page.evaluate("() => window.__marker") != before
    assert desk.paths().count("/command/project") == 2


@pytest.mark.parametrize("failure", [(404, {"error": {"code": "route_not_found"}}),
                                     (500, {"error": {"code": "store_error"}}),
                                     (200, ["not", "a", "claim"]), "abort"],
                         ids=["not-found", "store-error", "malformed", "no-answer"])
def test_a_claim_read_that_fails_leaves_the_desk_running_on_what_its_hash_said(
        open_desk, failure):
    desk = open_desk(f"#project={PROJECT_A}&lang=en", answers={"/command/project": failure})
    facts = desk.page.evaluate(FOREIGN_FACTS)
    assert facts["shell"] == "ready" and facts["button"] is None
    assert desk.paths().count("/command/project") == 1
    assert desk.claims()[1:] == [[PROJECT_A]] * (len(desk.wire) - 1)


def test_a_hash_that_later_names_another_project_ends_a_desk_the_server_bound(open_desk):
    desk = open_desk("#lang=en", answers={"/command/project": (200, claim(PROJECT_B))})
    _replace(desk.page, f"#project={PROJECT_B}&lang=en")
    _quiet(desk.page)
    assert desk.page.evaluate(FOREIGN_FACTS)["shell"] == "ready"
    _replace(desk.page, f"#project={PROJECT_A}&lang=en")
    desk.page.wait_for_function(FOREIGN_SAID)
    assert desk.page.evaluate(FOREIGN_FACTS)["button"] == RELOAD["en"]


@pytest.fixture(scope="session")
def real_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The desk over the seeded project, served AS `PROJECT_A`: nothing of it is answered in
    the page, so the claim read and the header check are the server's own."""
    root = write_project(tmp_path_factory.mktemp("desk-bound"), lanes={"claude": good_lane()})
    _seed(root)
    with identified_server(root, PROJECT_A) as origin:
        yield f"{origin}/panel/desk.html"


@pytest.mark.parametrize("fragment,ends", [
    (f"#project={PROJECT_A}&lang=en", False), ("#lang=en", False),
    (f"#project={PROJECT_B}&lang=en", True)],
    ids=["its-own-project", "no-project-in-the-hash", "another-project"])
def test_against_a_server_that_really_is_a_project_the_claim_and_the_header_agree_or_end_the_desk(
        chromium: Browser, real_url: str, fragment: str, ends: bool):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        wire: list[tuple[str, str, list[str]]] = []
        page.on("request", lambda request: wire.append((request.method,
                urlsplit(request.url).path, [one["value"] for one in request.headers_array()
                                             if one["name"].lower() == HEADER]))
                if urlsplit(request.url).path.startswith("/command/") else None)
        page.goto(f"{real_url}{fragment}", wait_until="load")
        page.wait_for_function(SETTLED)
        facts = page.evaluate(FOREIGN_FACTS)
    finally:
        context.close()
    assert (facts["shell"] == "refused") is ends
    claimed = PROJECT_B if ends else PROJECT_A
    if ends:
        assert wire == [("GET", "/command/project", [PROJECT_B])]
    else:
        assert wire[0][:2] == ("GET", "/command/project") and len(wire) > 3
        assert [claims for _m, _p, claims in wire[1:]] == [[claimed]] * (len(wire) - 1)


def test_the_mode_of_the_claim_reaches_a_window_nobody_framed(open_desk):
    view = open_desk("#lang=en", answers={"/command/project": (200, claim(None, "view"))})
    active = open_desk("#lang=en", answers={"/command/project": (200, claim(None))})
    said = "() => document.getElementById('deskPult').innerText"
    assert "Project not active" in view.page.evaluate(said)
    assert "Project not active" not in active.page.evaluate(said)
