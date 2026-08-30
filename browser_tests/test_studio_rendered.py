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
#: The control that copies a published revision into an editable draft, and the
#: selector that reaches it. Spelled here rather than imported: this module runs
#: against its own read-only project and shares no fixture with the modules that
#: write, so a label pinned in two places is two independent statements about
#: one product rather than one statement made twice.
NEW_DRAFT = "Edit as new draft"
NEW_DRAFT_CONTROL = '#workflowToolbar [data-focus="action:onEditPublished"]'


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
            "studio-runform.js": 200,
            "studio-canvas.js": 200, "studio-inspector.js": 200,
            "studio-runs.js": 200, "studio-people.js": 200,
            "studio-runread.js": 200, "studio-review.js": 200,
            "studio-layout.js": 200, "studio-edits.js": 200,
            "studio-sections.js": 200, "studio-fields.js": 200,
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


def test_the_classic_surfaces_are_reachable_from_every_screen_of_the_studio(
        studio: tuple[Page, list[str]]) -> None:
    """The map, findings, feed and handoffs are not in this application yet.

    While they are not, a person has to be able to GET to them, and the only
    route that existed was a sentence inside `<noscript>` -- markup a browser
    running the Studio never renders at all. So the claim is measured the way a
    person meets it: a visible, focusable link, present on every screen rather
    than on one, pointing at a route this server serves.
    """
    page, problems = studio
    link = page.locator("header .studio-elsewhere")
    assert link.get_attribute("href") == "/panel/index.html"
    said = link.inner_text()
    for word in ("Map", "findings", "feed", "handoffs"):
        assert word in said, said
    for _screen, tab, _container, _state in SCREENS:
        page.locator(f"#{tab}").click()
        assert link.is_visible(), f"the route disappeared on {tab}"
    # Focusable by keyboard, and its target is large enough to hit.
    link.focus()
    assert page.evaluate(
        "() => document.activeElement.classList.contains('studio-elsewhere')")
    assert link.bounding_box()["height"] >= 44
    assert problems == []


def test_the_classic_route_the_studio_offers_is_answered_by_the_server(
        studio: tuple[Page, list[str]]) -> None:
    """A link is discoverability only if what is behind it answers.

    Followed for real rather than asserted from the allowlist: the shell could
    name a route the asset table serves and still send a person somewhere that
    renders nothing.
    """
    page, problems = studio
    page.locator("header .studio-elsewhere").click()
    page.wait_for_load_state("load")
    assert page.url.endswith("/panel/index.html")
    assert page.locator("h2", has_text="Map").count() >= 1
    assert page.locator("h2", has_text="Findings").count() >= 1
    assert page.locator("h2", has_text="Feed").count() >= 1
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


def _choose_the_published_workflow(page: Page) -> None:
    """Pick this project's one workflow and come back to the Overview."""
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    page.locator("#navOverview").click()


def test_the_overview_counts_as_blocking_only_what_a_revision_needs(
        studio: tuple[Page, list[str]]) -> None:
    """Not one row per unconfigured provider, before or after a workflow.

    This project's readiness card DOES say no provider is available, and the
    blocked card says nothing is blocking, and both are true: "you cannot open
    a run yet" and "something stands between this workflow and running" are
    different questions. This revision's two steps declare no capability at
    all, so no provider could be in its way.

    These assertions used to read `"5 blocking"` and `"provider claude-code is
    unconfigured on this machine"` -- one row per catalogued provider, before
    anybody had chosen a workflow that needed any of them. That was the
    mandate's own complaint and this test was pinning it.

    The POSITIVE case needs a revision that declares capabilities, so it lives
    on the demo: `browser_tests/test_studio_demo.py`.
    """
    page, problems = studio
    body = page.locator("#bodyOverview").inner_text().lower()
    assert "nothing read so far is blocking" in body, body
    assert "is unconfigured on this machine" not in body, body

    _choose_the_published_workflow(page)
    moved = page.locator("#bodyOverview").inner_text().lower()
    assert "nothing read so far is blocking" in moved, moved
    assert "is unconfigured on this machine" not in moved, moved
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

    _choose_the_published_workflow(page)
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
    offered = starters.locator("option").all_inner_texts()
    assert offered[0] == "start blank"
    # This used to read `["start blank", "Dalio five-step cycle", "Dalio
    # five-step cycle"]`, and it passed: it was pinning the defect. Both shipped
    # starters carry that one title, so the picker offered a person two rows
    # they could not choose between -- and they are not equivalent, which is the
    # half that made it worth fixing rather than tolerating.
    assert len(offered[1:]) == len(set(offered[1:])) == 2, offered
    assert all("Dalio five-step cycle · revision " in row for row in offered[1:])
    ready = [row for row in offered[1:] if row.endswith("ready to run")]
    caveated = [row for row in offered[1:] if "name no result artifact" in row]
    assert len(ready) == 1 and len(caveated) == 1, offered
    # And the caveat is the DERIVED one, naming the steps it read.
    assert "4 review step(s)" in caveated[0], caveated
    assert problems == []


def test_a_workflow_just_started_is_the_one_the_picker_says_is_chosen(
        studio: tuple[Page, list[str]]) -> None:
    """A person who names a workflow is looking at it; the picker must agree.

    The picker's rows are the SERVER's list, and a workflow just started is not
    in it -- nothing has been saved under that id. Setting the control's value
    to a name no option carried left it falling back to "choose a workflow",
    so somebody who had just named a workflow and seeded its drawing was told
    nothing was chosen, and only a save plus a reload put it right.

    Nothing is written here: starting a workflow seeds a draft in the window and
    issues a read, which is why this belongs in a module whose project is
    otherwise read-only.
    """
    page, problems = studio
    page.locator("#navWorkflow").click()
    page.wait_for_selector("#screenWorkflow:not([hidden])")
    picker = page.locator("#workflowToolbar select[name='workflow']")

    page.locator('[data-focus="new-workflow"]').fill("a-brand-new-cycle")
    page.locator('[data-focus="action:onStartWorkflow"]').click()
    page.wait_for_function(
        "() => document.querySelector(\"#workflowToolbar select[name='workflow']\")"
        ".value === 'a-brand-new-cycle'")

    assert picker.input_value() == "a-brand-new-cycle"
    chosen = picker.locator("option:checked").inner_text()
    assert chosen == "a-brand-new-cycle — new, not saved yet", chosen
    # And the server's own row is still there, unshadowed by the new one.
    assert f"{WORKFLOW_ID} — {WORKFLOW_TITLE}" in (
        picker.locator("option").all_inner_texts())
    assert problems == []


def test_choosing_the_published_workflow_draws_its_revision_read_only(
        studio: tuple[Page, list[str]]) -> None:
    """A published revision is immutable, and the canvas says so out loud.

    This is the read path end to end: a select change, a real GET, a landed
    payload, two drawn steps and one drawn connection -- and every editing
    control disabled with the reason on screen rather than implied by grey.

    The banner also has to say what a reader may do INSTEAD, and the control
    that does it has to be there and be pressable. Read-only was the whole
    sentence once, and it left a person looking at a workflow they had no way
    to change; the revision is still untouchable, and the road on is a copy.
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
    assert f"{NEW_DRAFT} copies it into a draft you can change" in banner, banner
    fresh = page.locator(NEW_DRAFT_CONTROL)
    assert fresh.inner_text() == NEW_DRAFT
    assert not fresh.is_disabled(), (
        "the read-only revision was drawn with no road on from it")
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


def _blocking(page: Page, state: object) -> list[str]:
    """Ask the SHIPPED `blockingRows` what it makes of one crafted state.

    The rendered assertions above cover the two states this project can be put
    into from the screen. The third -- a provider that IS available and DOES
    serve the capability a step needs -- cannot be reached that way, because the
    fixture configures no provider and the demo configures none either. It is
    the over-correction control and it is the one that matters: a rule that
    answered "blocked" whatever the roster said would satisfy both rendered
    cases and be wrong about the only case a working install is ever in.
    """
    import json

    return page.evaluate(
        "async (given) => { const m = await import('/panel/studio-view.js');"
        " return m.blockingRows(given).map((row) => row.text); }",
        json.loads(json.dumps(state)))


def _state(*, nodes, providers):
    """The smallest state shape `blockingRows` reads, and nothing else."""
    return {
        "workflows": {"problems": [], "diagnostics": [], "list": [],
                      "detail": {"published": {"nodes": nodes}}},
        "runs": {"list": []},
        "providers": providers,
    }


def test_a_provider_blocks_only_what_the_chosen_revision_actually_needs(
        studio: tuple[Page, list[str]]) -> None:
    """The whole truth table, including the case the screens cannot produce."""
    page, problems = studio
    dispatching = [{"node_id": "do", "capability": "dispatch"}]
    unconfigured = [{"provider_id": "claude-code", "availability": "unconfigured",
                     "controls": ["dispatch", "review"]}]

    # Nothing chosen: five unconfigured providers are five setup facts, not five
    # problems. This is the mandate's complaint, stated as an empty list.
    assert _blocking(page, _state(nodes=[], providers=unconfigured * 5)) == []

    # Chosen, and nothing available serves what it needs: exactly ONE row, and
    # it names the capability and the step rather than any product.
    said = _blocking(page, _state(nodes=dispatching, providers=unconfigured * 5))
    assert len(said) == 1, said
    assert "No available provider serves dispatch" in said[0], said
    assert "do" in said[0], said

    # THE CONTROL: available, and serving that capability. Nothing is blocked.
    serving = [{"provider_id": "claude-code", "availability": "available",
                "controls": ["dispatch", "review"]}]
    assert _blocking(page, _state(nodes=dispatching, providers=serving)) == []

    # Available, but serving something else: blocked again, so "available" alone
    # is not what the rule reads.
    elsewhere = [{"provider_id": "claude-code", "availability": "available",
                  "controls": ["review"]}]
    assert len(_blocking(page, _state(nodes=dispatching,
                                      providers=elsewhere))) == 1
    assert problems == []
