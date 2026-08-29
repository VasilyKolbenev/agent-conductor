"""The Studio shell in a real Chromium, against the real loopback server.

Every gate the Studio has passed so far reads SOURCE TEXT. This module is the
first that runs the thing: Chromium resolves the shipped module graph from the
production entry route ``/``, the real ``server.build`` answers every request,
and what is asserted is what a person would see -- rendered tabs, computed
styles, the state word on each screen container and the sentence beside it.

Three properties this module exists to hold, and each of them is a claim the
product makes out loud in ``studio.html``:

- five screens, exactly ONE of them showing, and which one is carried by three
  independent carriers so it is never named by colour alone;
- the tablist is the platform's: arrows move it, focus follows, and a keyboard
  focus is VISIBLE -- measured as a computed outline, not asserted from the
  stylesheet's source;
- every screen container carries one of the seven machine words in
  ``data-state`` AND the plain-language sentence its own module owns. The
  sentences are read out of ``studio-view.js`` in the page rather than copied
  here, so a rewritten sentence moves this test with it and a MISSING one still
  reds.

There is no ``window.conductStudio``: ``studio.js`` is an IIFE that exposes no
public seam the way ``graph.js`` exposes ``window.conductGraph``. So nothing
here is fed through a seam -- every fact on screen arrived through a real read
of a real route, which is a stronger statement about the same surface.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.graph_template import GraphTemplate
from conductor.command.template_store import TemplateStore

from tests.test_store import good_lane, write_project

#: The one workflow this module's project holds, published once. The Studio is
#: read-only here: nothing below writes, so a session-scoped server is honest.
WORKFLOW_ID = "release-check"
WORKFLOW_TITLE = "Release check"
PUBLISHED = {
    "schema_version": 1,
    "template_id": WORKFLOW_ID,
    "revision": 1,
    "title": WORKFLOW_TITLE,
    "nodes": [
        {"node_id": "draft-notes", "kind": "task", "title": "Draft the notes",
         "resources": []},
        {"node_id": "read-notes", "kind": "task", "title": "Read the notes",
         "resources": []},
    ],
    "edges": [{"from_node": "draft-notes", "to_node": "read-notes"}],
}
#: The five screens, in the product's own order, with the tab and container ids
#: ``studio.html`` froze. Spelled here so a screen quietly dropped from the
#: markup reds instead of shrinking a count nobody pinned.
SCREENS = (
    ("overview", "navOverview", "screenOverview", "stateOverview"),
    ("workflow", "navWorkflow", "screenWorkflow", "stateWorkflow"),
    ("runs", "navRuns", "screenRuns", "stateRuns"),
    ("decisions", "navDecisions", "screenDecisions", "stateDecisions"),
    ("agents", "navAgents", "screenAgents", "stateAgents"),
)
#: ``studio-store.PHASES``. The word in ``data-state`` is one of these or the
#: shell invented one.
PHASES = ("empty", "loading", "ready", "stale", "refused", "failed",
          "disconnected")


@pytest.fixture(scope="session")
def studio_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The Studio at its production entry route, over a real seeded server."""
    root = write_project(tmp_path_factory.mktemp("studio-shell"),
                         lanes={"claude": good_lane()})
    TemplateStore(root).save(GraphTemplate.from_dict(PUBLISHED))
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "studio server did not stop"


def _watch(page: Page) -> list[str]:
    """Collect every console error and every uncaught exception on one page."""
    problems: list[str] = []
    page.on("console", lambda message: problems.append(
        getattr(message, "text", ""))
        if getattr(message, "type", "") == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    return problems


def _boot(page: Page) -> None:
    """Wait on a REAL signal of the first render pass, never on a clock.

    ``#studioPrimary`` is empty in the static document and is filled by
    ``mountShell``, so a child there is the module graph having resolved and
    ``render()`` having run.
    """
    page.wait_for_function(
        "() => document.getElementById('studioPrimary').children.length > 0")


def _connected(page: Page) -> None:
    """Wait for the real EventSource to open against the real ``/events``."""
    page.wait_for_selector('#studioConnection[data-connection="open"]')


@pytest.fixture
def studio(chromium: Browser, studio_url: str) -> Iterator[tuple[Page, list[str]]]:
    """One isolated Studio window, booted and connected, per test."""
    context = chromium.new_context(viewport={"width": 1600, "height": 1200})
    page = context.new_page()
    problems = _watch(page)
    page.goto(studio_url, wait_until="load")
    _boot(page)
    _connected(page)
    try:
        yield page, problems
    finally:
        context.close()


def _phase_sentences(page: Page) -> dict[str, str]:
    """The view module's own table, read out of the module the page loaded."""
    return page.evaluate(
        """() => import("/panel/studio-view.js")
             .then(view => ({...view.PHASE_SENTENCES}))""")


def test_the_studio_boots_from_the_entry_route_with_no_error_at_all(
        chromium: Browser, studio_url: str) -> None:
    """Chromium resolves the shipped module graph and every file answers 200.

    The entry route is ``/`` -- ``studio.html`` is deliberately NOT on the
    asset allowlist -- and every asset it names is root-relative under
    ``/panel/``. This counts the responses rather than trusting the markup:
    a name the allowlist does not carry answers 404 and would be invisible in
    a test that only looked at what rendered.
    """
    context = chromium.new_context(viewport={"width": 1600, "height": 1200})
    page = context.new_page()
    problems = _watch(page)
    served: list[tuple[str, int]] = []
    page.on("response", lambda response: served.append(
        (response.url, response.status)))
    try:
        page.goto(studio_url, wait_until="load")
        _boot(page)
        _connected(page)
        names = {url.rsplit("/", 1)[1]: status for url, status in served
                 if "/panel/" in url}
        assert names == {
            "studio.css": 200, "studio.js": 200, "studio-store.js": 200,
            "studio-model.js": 200, "studio-view.js": 200,
            "studio-canvas.js": 200, "studio-inspector.js": 200,
            "studio-runs.js": 200, "studio-people.js": 200,
            "studio-runread.js": 200, "studio-review.js": 200,
            "studio-layout.js": 200,
            "command-projection.js": 200, "command-view.js": 200,
        }
        # The reads the window opens with, both landed and both real.
        assert page.locator("#workflowToolbar select[name='workflow'] option"
                            ).count() == 2
        assert problems == []
    finally:
        context.close()


def test_the_five_screens_show_exactly_one_at_a_time(
        studio: tuple[Page, list[str]]) -> None:
    """Five tabpanels, one visible, and the invisible ones really are hidden.

    ``hidden`` is asserted through the browser's own visibility answer rather
    than through the attribute: a stylesheet that overrode ``[hidden]`` would
    leave the attribute perfectly in place and put five screens on screen.
    """
    page, problems = studio
    for _screen, _tab, container, _state in SCREENS:
        assert page.locator(f"#{container}").count() == 1
    visible = [container for _s, _t, container, _st in SCREENS
               if page.locator(f"#{container}").is_visible()]
    assert visible == ["screenOverview"]
    selected = [tab for _s, tab, _c, _st in SCREENS
                if page.locator(f"#{tab}").get_attribute("aria-selected") == "true"]
    assert selected == ["navOverview"]
    assert problems == []


def test_choosing_each_tab_shows_that_screen_and_only_that_screen(
        studio: tuple[Page, list[str]]) -> None:
    """Every one of the five is reachable, and each arrival is exclusive."""
    page, problems = studio
    for screen, tab, container, _state in SCREENS:
        page.locator(f"#{tab}").click()
        page.wait_for_selector(f"#{container}:not([hidden])")
        shown = [name for name, _t, box, _st in SCREENS
                 if page.locator(f"#{box}").is_visible()]
        assert shown == [screen], f"{screen} did not arrive alone: {shown}"
        marked = [name for name, other, _c, _st in SCREENS
                  if page.locator(f"#{other}").get_attribute(
                      "aria-selected") == "true"]
        assert marked == [screen]
    assert problems == []


def test_the_tablist_moves_on_the_arrow_keys_and_carries_focus_with_it(
        studio: tuple[Page, list[str]]) -> None:
    """The platform's own tablist road: arrows move, focus follows, it wraps.

    Roving tabindex is asserted beside it, because that is what makes a Tab
    into the tablist land on the CURRENT tab rather than on the first one.
    """
    page, problems = studio
    page.locator("#navOverview").focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_selector("#screenWorkflow:not([hidden])")
    assert page.evaluate("() => document.activeElement.id") == "navWorkflow"
    assert page.locator("#navWorkflow").evaluate("node => node.tabIndex") == 0
    assert page.locator("#navOverview").evaluate("node => node.tabIndex") == -1

    page.keyboard.press("ArrowLeft")
    page.wait_for_selector("#screenOverview:not([hidden])")
    assert page.evaluate("() => document.activeElement.id") == "navOverview"

    # It wraps in both directions: a tablist that stops at its ends strands a
    # keyboard reader at whichever end they walked into.
    page.keyboard.press("ArrowLeft")
    page.wait_for_selector("#screenAgents:not([hidden])")
    assert page.evaluate("() => document.activeElement.id") == "navAgents"
    page.keyboard.press("ArrowRight")
    page.wait_for_selector("#screenOverview:not([hidden])")
    assert page.evaluate("() => document.activeElement.id") == "navOverview"
    assert problems == []


def test_a_keyboard_focus_draws_a_visible_ring_on_the_tab_it_lands_on(
        studio: tuple[Page, list[str]]) -> None:
    """Measured, not read off the stylesheet.

    The ring is asked of the COMPUTED style after a real Tab press, so a rule
    that never matched -- a typo'd selector, a later reset, a colour equal to
    the background -- is caught here and cannot be caught by reading source.
    """
    page, problems = studio
    page.locator("#navOverview").focus()
    ring = page.locator("#navOverview").evaluate(
        """node => {
          const style = getComputedStyle(node);
          return {style: style.outlineStyle, width: style.outlineWidth,
                  colour: style.outlineColor,
                  background: getComputedStyle(document.body).backgroundColor,
                  visible: node.matches(":focus-visible")};
        }""")
    assert ring["visible"] is True, "a keyboard focus was not focus-visible"
    assert ring["style"] == "solid", ring
    assert float(ring["width"].removesuffix("px")) >= 2, ring
    assert ring["colour"] != ring["background"], (
        "the focus ring is drawn in the page's own background colour")
    assert problems == []


def test_every_screen_carries_a_machine_word_and_the_sentence_beside_it(
        studio: tuple[Page, list[str]]) -> None:
    """``data-state`` for a test, a plain sentence for a person, on all five.

    The sentence is compared against ``studio-view.PHASE_SENTENCES`` read out
    of the module the page actually loaded, so this pins the RELATION rather
    than a copy of the prose: rewording a sentence moves both sides together,
    while a screen left with no sentence, or with another phase's, reds.
    """
    page, problems = studio
    sentences = _phase_sentences(page)
    assert set(sentences) == set(PHASES)
    for _screen, _tab, container, state in SCREENS:
        word = page.locator(f"#{container}").get_attribute("data-state")
        assert word in PHASES, f"{container} stands in {word!r}"
        said = page.locator(f"#{state}").inner_text().strip()
        assert said == sentences[word], (container, word, said)
        # A sentence, not a second copy of the machine word: `data-state` is
        # what a test reads and this is what a person reads, and a screen that
        # printed `refused` in both places would answer neither.
        assert said and said.rstrip(".").lower() != word, (state, word, said)
        assert said.endswith("."), (state, said)
    assert problems == []


def test_a_landed_read_moves_the_screens_off_the_word_they_started_in(
        studio: tuple[Page, list[str]]) -> None:
    """The state word is a fact about a read, not a decoration.

    Booting says ``empty``; the reads the window opens with land and the two
    screens they feed say ``ready``. Without this, a shell that hardcoded one
    word would pass every assertion above.
    """
    page, problems = studio
    # `state="attached"`: four of the five containers are hidden by design, and
    # a wait that insisted on visibility would be asking a different question.
    page.wait_for_selector('#screenWorkflow[data-state="ready"]',
                           state="attached")
    assert page.locator("#screenOverview").get_attribute("data-state") == "ready"
    assert page.locator("#stateOverview").inner_text().strip() == "Read."
    assert problems == []


def test_the_shell_says_it_is_connected_in_a_machine_word_and_in_english(
        studio: tuple[Page, list[str]]) -> None:
    """The stream is real: a real EventSource against the real ``/events``."""
    page, problems = studio
    assert page.locator("#studioConnection").get_attribute(
        "data-connection") == "open"
    said = page.locator("#studioConnection").inner_text()
    assert "Connected" in said, said
    assert problems == []


def test_each_tab_names_the_panel_it_controls_and_each_panel_names_its_tab(
        studio: tuple[Page, list[str]]) -> None:
    """The two halves of the tablist relation, both directions, in the DOM.

    A dangling ``aria-controls`` is invisible to a person, invisible to a
    screenshot, and is exactly what a screen reader follows.
    """
    page, problems = studio
    assert page.locator("#studioNav").get_attribute("role") == "tablist"
    for _screen, tab, container, _state in SCREENS:
        node = page.locator(f"#{tab}")
        assert node.get_attribute("role") == "tab"
        assert node.get_attribute("aria-controls") == container
        panel = page.locator(f"#{container}")
        assert panel.get_attribute("role") == "tabpanel"
        assert panel.get_attribute("aria-labelledby") == tab
    assert problems == []


def test_the_overview_derives_its_readiness_from_the_payload_it_read(
        studio: tuple[Page, list[str]]) -> None:
    """A sentence with a REASON in it, and the reason MOVES with the payload.

    Two readings of the same card, and the second is what makes the first mean
    anything: with nothing chosen the answer is "there is nothing to start",
    and once a workflow with a published revision IS chosen the answer changes
    to the provider roster -- which is the next real condition the open-run
    route enforces. A card that hardcoded either sentence fails one of them.
    """
    page, problems = studio
    # Lowered before matching: `studio.css` sets `text-transform:uppercase` on
    # every card heading, so `inner_text` answers with what is PAINTED. A test
    # matching the source casing would be pinning the stylesheet by accident.
    body = page.locator("#bodyOverview").inner_text().lower()
    assert "ready to run?" in body
    assert "not yet" in body
    assert "no workflow is chosen, so there is nothing to start" in body
    # The Overview names the project the server was started in, read out of
    # conductor/map.toml -- `tests.test_store.write_project` writes
    # `project = "p"`, so that is the name that must appear.
    assert "this is p, the project this server was started in" in body
    assert "records no project name" not in body
    # Every unreachable provider is counted as blocking, each row naming the
    # payload it came from rather than a severity this window invented.
    assert "5 blocking" in body
    assert "provider claude-code is unconfigured on this machine" in body

    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    page.locator("#navOverview").click()
    moved = page.locator("#bodyOverview").inner_text().lower()
    assert "no configured provider is available on this machine" in moved
    assert "no workflow is chosen" not in moved
    revision = page.locator("#bodyOverview p.studio-row",
                            has_text="Latest revision")
    assert revision.inner_text().strip().endswith("1"), revision.inner_text()
    assert problems == []


def test_the_workflow_screen_offers_the_project_workflow_and_the_bundled_starters(
        studio: tuple[Page, list[str]]) -> None:
    """Both roads onto the canvas came from a read, not from a written-down list.

    The picker's rows are this PROJECT's durable workflows; the starter rows
    are what the WHEEL ships. Two questions, two arrays, one screen.
    """
    page, problems = studio
    page.locator("#navWorkflow").click()
    page.wait_for_selector("#screenWorkflow:not([hidden])")
    picker = page.locator("#workflowToolbar select[name='workflow']")
    assert picker.locator("option").all_inner_texts() == [
        "choose a workflow", f"{WORKFLOW_ID} — {WORKFLOW_TITLE}"]
    starters = page.locator("#workflowToolbar select[name='new-from']")
    assert starters.locator("option").all_inner_texts() == [
        "start blank", "Dalio five-step cycle", "Dalio five-step cycle"]
    assert problems == []


def test_choosing_the_published_workflow_draws_its_revision_read_only(
        studio: tuple[Page, list[str]]) -> None:
    """A published revision is immutable, and the canvas says so out loud.

    This is the read path end to end: a select change, a real GET, a landed
    payload, two drawn steps and one drawn connection -- and every editing
    control disabled with the reason on screen rather than implied by grey.
    """
    page, problems = studio
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    assert page.locator("[data-node-id]").count() == 2
    assert page.locator("[data-edge]").count() == 1
    banner = page.locator(".studio-canvas__document").inner_text()
    assert "immutable and read-only" in banner, banner
    assert page.locator('[data-add-kind="task"]').is_disabled()
    assert "no step can be added to it" in page.locator(
        ".studio-palette__note").inner_text()
    # The header names the PROJECT, because that is the thing a person opened.
    # It used to name the workflow, and only because no project name existed to
    # show; the workflow is named on the canvas banner and in the toolbar, both
    # asserted above, so nothing was lost by giving the largest type on screen
    # to the project it belongs to.
    assert page.locator("#studioProject").inner_text() == "p"
    assert problems == []


def test_the_agents_screen_keeps_the_machine_and_the_build_apart_per_provider(
        studio: tuple[Page, list[str]]) -> None:
    """Two facts per row, answering two questions, neither read off the other.

    This build resolves five providers and this machine has configured none of
    them, so every row must carry ``unconfigured`` (what the MACHINE resolved)
    beside ``real_experimental`` (what the BUILD claims), each with its own
    plain sentence. A screen that merged them into one word would read as "this
    product cannot do it", which is a different and false statement.
    """
    page, problems = studio
    page.locator("#navAgents").click()
    page.wait_for_selector("#screenAgents:not([hidden])")
    body = page.locator("#bodyAgents").inner_text().lower()
    for provider in ("claude-code", "codex", "deepseek-harness", "grok-build",
                     "kimi-code"):
        assert provider in body, provider
    assert body.count("unconfigured") >= 5
    assert "no provider configuration names it, so nothing was looked at" in body
    assert "this build talks to the real product, experimentally" in body
    # A participant is a RUN's fact and no run is in view, so the screen says
    # that rather than showing an empty table.
    assert "no run in view binds anybody yet" in body
    assert problems == []


def test_the_runs_and_decisions_screens_state_their_emptiness_in_plain_words(
        studio: tuple[Page, list[str]]) -> None:
    """An empty project is drawn as empty and says what would fill it."""
    page, problems = studio
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    assert "This project holds no runs yet" in page.locator(
        "#bodyRuns").inner_text()
    page.locator("#navDecisions").click()
    page.wait_for_selector("#screenDecisions:not([hidden])")
    assert "Nothing is waiting for you" in page.locator(
        "#bodyDecisions").inner_text()
    assert problems == []


def test_the_window_writes_nothing_into_browser_storage_while_it_reads(
        studio: tuple[Page, list[str]]) -> None:
    """Facts live on the server. Every screen visited, both stores still empty.

    A window that cached a workflow in ``localStorage`` would answer a later
    reader from a copy nobody can invalidate; this build has no such door and
    this is the measurement that says so.
    """
    page, problems = studio
    for _screen, tab, container, _state in SCREENS:
        page.locator(f"#{tab}").click()
        page.wait_for_selector(f"#{container}:not([hidden])")
    assert page.evaluate(
        "() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert problems == []
