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

This module holds the shell and the fixtures. What each screen says once its
reads land -- the Overview's cards, the Workflow picker and canvas, the Agents
rows, the storage census and the provider truth table -- was split out at the
project's 800-line cap into ``test_studio_screens_rendered.py``, which imports
the fixtures from here.
"""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, Route

from conductor import server
from conductor.command.graph_template import GraphTemplate
from conductor.command.template_store import TemplateStore

from tests.test_store import good_lane, write_project
from tests.test_panel_colour import contrast

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
#: Every file the entry route's module graph fetches, with the answer each one
#: owes. Frozen here beside the other facts about what ``studio.html`` ships,
#: and spelled out rather than derived: a census built from the server's own
#: allowlist would only agree with itself, while a name the allowlist does not
#: carry answers 404 and would be invisible in a test that read the markup.
BOOT_ASSETS = {
    "studio.css": 200, "studio.js": 200, "studio-store.js": 200,
    "studio-tasks-model.js": 200, "studio-tasks.js": 200, "studio-taskflow.js": 200,
    "studio-model.js": 200, "studio-view.js": 200,
    "studio-runform.js": 200,
    "studio-canvas.js": 200, "studio-inspector.js": 200,
    "studio-canvas-edges.js": 200, "studio-canvas-flow.js": 200,
    "studio-orbit.js": 200,
    "studio-runs.js": 200, "studio-runwords.js": 200,
    "studio-runstep.js": 200, "studio-runwrite.js": 200,
    "studio-people.js": 200, "studio-rundocs.js": 200,
    "studio-rundraft.js": 200, "studio-runwrites.js": 200,
    "studio-toolbardraft.js": 200,
    "studio-runread.js": 200, "studio-review.js": 200,
    "studio-layout.js": 200, "studio-edits.js": 200,
    "studio-sections.js": 200, "studio-artifacts.js": 200,
    "studio-transitions.js": 200,
    "studio-fields.js": 200,
    # The controls route's own answer and the section it draws before a person
    # confirms. Both are real modules on the boot graph, so both must be on the
    # allowlist -- a module the server does not serve answers 404, and the
    # window would come up half-built.
    "studio-controls.js": 200, "studio-isolation.js": 200,
    # The focus net the boot module carries across every render pass.
    "studio-focus.js": 200,
    "studio-participants.js": 200,
    # The ceilings, split off the boundary at its line cap; the edits and the
    # sections import it, so the entry route's module graph fetches it.
    "studio-ceilings.js": 200,
    "command-projection.js": 200, "command-view.js": 200,
    # The wire doors the boot module imports: reads, writes, session and stream.
    "desk-transport.js": 200,
    # The five-screen shell and its mounts, preferences and the scene lenses.
    "studio-shell.js": 200, "studio-runhead.js": 200, "studio-mounts.js": 200, "studio-preferences.js": 200,
    # The address grammar `studio-preferences.js` re-exports (the desk shares it with the hub).
    "desk-hash.js": 200,
    "studio-bridge.js": 200, "studio-situation.js": 200, "studio-taskruns.js": 200,
    "studio-scene-model.js": 200, "studio-trace.js": 200, "studio-draft.js": 200,
    "studio-workflowwrite.js": 200,
    # The RU/EN catalogues: the shared table and one copy module per screen area.
    "studio-i18n.js": 200, "studio-agents-copy.js": 200, "studio-automation-copy.js": 200,
    "studio-feedback-copy.js": 200, "studio-participant-copy.js": 200,
    "studio-run-docs-copy.js": 200, "studio-runform-copy.js": 200, "studio-runs-copy.js": 200,
    "studio-runstep-copy.js": 200, "studio-view-copy.js": 200, "studio-workflow-copy.js": 200,
    "studio-workflow-detail-copy.js": 200, "studio-notice-copy.js": 200,
    # The wizard's catalogue and the desk's own words, spread into the shared table, so the
    # entry route fetches them too.
    "desk-wizard-copy.js": 200, "desk-copy.js": 200, "desk-status-copy.js": 200,
    "desk-flow-copy.js": 200, "desk-feed-copy.js": 200, "desk-summary-copy.js": 200,
    # Readings, bounded automation and typed checker findings.
    "studio-quotaflow.js": 200, "studio-quotas-model.js": 200, "studio-quotas.js": 200,
    "studio-automation.js": 200, "studio-automation-flow.js": 200,
    "studio-automation-model.js": 200, "studio-automation-providers.js": 200,
    "studio-feedback.js": 200, "studio-feedback-model.js": 200,
}


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
    """The shell's phase words, each with the catalogue's sentence in the page's language.

    Read out of the modules the page loaded: the shell names the words, and
    what it draws beside each one is the catalogue row ``phase.<word>``.
    """
    return page.evaluate(
        """() => Promise.all([import("/panel/studio-shell.js"), import("/panel/studio-i18n.js")])
             .then(([shell, i18n]) => {
               const locale = new URLSearchParams(location.hash.slice(1)).get("lang") || "en";
               return Object.fromEntries(Object.keys(shell.PHASE_SENTENCES)
                 .map((word) => [word, i18n.message(locale, `phase.${word}`)]));
             })""")


def _screen_facts(page: Page, rows: tuple) -> list[dict[str, str]]:
    """Each container's machine word and the sentence beside it, in ONE evaluation.

    Two locator reads are two round trips, and a read that lands between them
    hands back a word from before it and a sentence from after it. One
    evaluation is one synchronous turn of the page, so the pair is one moment's.
    """
    return page.evaluate(
        """(pairs) => pairs.map(([container, state]) => ({
             container,
             word: document.getElementById(container).getAttribute("data-state"),
             said: document.getElementById(state).innerText.trim()}))""",
        [[container, state] for _screen, _tab, container, state in rows])


#: A page whose one word and one sentence change TOGETHER, on every turn of the
#: event loop it can get. Whatever a reader sees of it is one of the two pairs
#: below; a reading that mixes them read the page at two different moments.
FLIP_PAIRS = {"a": "said a", "b": "said b"}
FLIPPING = """<!doctype html><p id="w" data-state="a"></p><p id="s">said a</p>
<script>
  const pairs = [["a", "said a"], ["b", "said b"]];
  let at = 0;
  setInterval(() => {
    at = 1 - at;
    document.getElementById("w").setAttribute("data-state", pairs[at][0]);
    document.getElementById("s").textContent = pairs[at][1];
  }, 0);
</script>"""


def test_a_state_word_and_its_sentence_are_never_read_from_two_moments(
        chromium: Browser) -> None:
    """The instrument, driven on a page that changes under it.

    The first version of the screen-word check read `data-state` and then the
    sentence in two round trips, and CI saw ``('screenWorkflow', 'loading',
    'Read.')``: the word from before a read landed and the sentence from after
    it. Nothing on the real Studio can be made to tear on demand, so the
    property is held here on a page that flips every turn: three hundred
    readings, each of them one page's pair or the reader is wrong.
    """
    context = chromium.new_context()
    page = context.new_page()
    try:
        page.set_content(FLIPPING)
        for _ in range(300):
            (fact,) = _screen_facts(page, (("flip", "tab", "w", "s"),))
            assert FLIP_PAIRS[fact["word"]] == fact["said"], fact
    finally:
        context.close()


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
        assert names == BOOT_ASSETS
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


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_tab_text_keeps_contrast_in_the_first_frames_of_a_theme_change(
        studio: tuple[Page, list[str]], theme: str, tmp_path) -> None:
    """Measure actual paint during a theme change, with motion permitted."""
    page, problems = studio
    initial = "light" if theme == "dark" else "dark"
    page.emulate_media(color_scheme=initial, reduced_motion="reduce")
    page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    page.emulate_media(color_scheme=initial, reduced_motion="no-preference")
    page.evaluate("""theme => {
      window.tabContrastFrames = [];
      const media = matchMedia(`(prefers-color-scheme: ${theme})`);
      const sample = () => {
        const rows = [...document.querySelectorAll('#studioNav [role=tab]')].map(tab => {
          const surfaces = [];
          for (let at = tab; at && at !== document.body; at = at.parentElement) {
            const style = getComputedStyle(at);
            surfaces.push({background: style.backgroundColor, opacity: style.opacity,
              image: style.backgroundImage});
          }
          return {id: tab.id, selected: tab.getAttribute('aria-selected'), surfaces,
            color: getComputedStyle(tab).color};
        });
        window.tabContrastFrames.push({themeMatches: media.matches, rows,
          background: getComputedStyle(document.body).backgroundColor});
        if (window.tabContrastFrames.length < 4) requestAnimationFrame(sample);
      };
      media.addEventListener('change', event => { if (event.matches) sample(); }, {once: true});
    }""", theme)
    page.emulate_media(color_scheme=theme, reduced_motion="no-preference")
    page.wait_for_function("() => window.tabContrastFrames.length === 4")
    frames = page.evaluate("() => window.tabContrastFrames")
    (tmp_path / f"tab-contrast-{theme}.json").write_text(
        json.dumps(frames, indent=2), encoding="utf-8")
    rgb = lambda value: tuple(float(channel) for channel in re.findall(r"[\d.]+", value)[:3])
    for frame in frames:
        assert frame["themeMatches"]
        assert {row["id"] for row in frame["rows"]} == {row[1] for row in SCREENS}
        assert sum(row["selected"] == "true" for row in frame["rows"]) == 1
        for row in frame["rows"]:
            # The actual body is the surface only while these ancestors are
            # transparent and opaque as layers; refuse a different paint stack.
            assert all(surface == {"background": "rgba(0, 0, 0, 0)",
                "opacity": "1", "image": "none"} for surface in row["surfaces"]), row
            measured = contrast(rgb(row["color"]), rgb(frame["background"]))
            assert measured >= 4.5, (theme, row["id"], measured, frame)
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
    # One evaluation for all five: a word and its sentence are read from the
    # same moment, or a read landing between two round trips tears the pair.
    for fact, (_screen, _tab, container, state) in zip(
            _screen_facts(page, SCREENS), SCREENS, strict=True):
        word, said = fact["word"], fact["said"]
        assert word in PHASES, f"{container} stands in {word!r}"
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

    The overview is waited for on ITS OWN word. Its word is the worst of the
    workflows read and the runs read, so the workflow screen saying ``ready``
    says nothing about the runs read, which can still be in flight when it
    does; and its word and sentence are read in one evaluation.
    """
    page, problems = studio
    # `state="attached"`: four of the five containers are hidden by design, and
    # a wait that insisted on visibility would be asking a different question.
    page.wait_for_selector('#screenOverview[data-state="ready"]',
                           state="attached")
    (overview,) = _screen_facts(page, SCREENS[:1])
    assert (overview["word"], overview["said"]) == ("ready", "Read.")
    assert problems == []


def test_the_overview_stays_loading_while_the_runs_read_is_held_and_reads_ready_once_it_lands(
        chromium: Browser, studio_url: str) -> None:
    """The overview's word is the worst of two reads, and one landing is not the other.

    With the runs read held, the workflow screen says ``ready`` (its read has
    landed) while the overview says ``loading``. So a reader that waited on the
    workflow screen alone and then read the overview got a word from before the
    runs read: the pair that turned the ubuntu gate red. Released, the overview
    says ``ready`` and the sentence beside it says ``Read.``, from one evaluation.
    """
    context = chromium.new_context(viewport={"width": 1600, "height": 1200})
    page = context.new_page()
    problems = _watch(page)
    held: list[Route] = []
    gate = {"open": False}

    def hold(route: Route) -> None:
        if gate["open"]:
            route.continue_()
        else:
            held.append(route)

    page.route("**/command/runs", hold)
    try:
        page.goto(studio_url, wait_until="load")
        _boot(page)
        page.wait_for_selector('#screenWorkflow[data-state="ready"]',
                               state="attached")
        (overview,) = _screen_facts(page, SCREENS[:1])
        assert (overview["word"], overview["said"]) == ("loading", "Reading.")
        gate["open"] = True
        for route in held:
            route.continue_()
        page.wait_for_selector('#screenOverview[data-state="ready"]',
                               state="attached")
        (overview,) = _screen_facts(page, SCREENS[:1])
        assert (overview["word"], overview["said"]) == ("ready", "Read.")
        assert problems == []
    finally:
        context.close()


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
