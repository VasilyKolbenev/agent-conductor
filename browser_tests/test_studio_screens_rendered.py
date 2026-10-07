"""The Studio's screens in a real Chromium: what each one says once its reads land.

Split out of ``test_studio_rendered.py`` when that module passed the project's
800-line cap, along the seam the file already had. The shell -- tabs, focus,
contrast, the machine word and the sentence beside it, the classic route, the
tablist relation -- stays there with the fixtures. The checks that follow a
person onto the screens themselves live here: the Overview's cards, the
Workflow picker and its canvas, the Agents rows, the empty Runs and Decisions,
the browser-storage census and the provider truth table.

Nothing below was edited in the move. The fixtures and the facts about the
seeded project belong to the shell module and are imported the way the other
Studio browser modules import them, so this file runs against the same
read-only project and the same real server.
"""
from __future__ import annotations

from playwright.sync_api import Page

from browser_tests.test_studio_rendered import (  # noqa: F401 -- fixtures by name
    SCREENS, WORKFLOW_ID, WORKFLOW_TITLE, studio, studio_url)

#: The control that copies a published revision into an editable draft, and the
#: selector that reaches it. Spelled here rather than imported: this module runs
#: against its own read-only project and shares no fixture with the modules that
#: write, so a label pinned in two places is two independent statements about
#: one product rather than one statement made twice.
NEW_DRAFT = "Edit as new draft"
NEW_DRAFT_CONTROL = '#workflowToolbar [data-focus="action:onEditPublished"]'


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
    # Five shipped revisions, including both independent-checker starters, and no two
    # rows a person cannot tell apart. Revision 5 is the standard and is offered first.
    # Three more files ship since: the desk's ready cycles (spec 7.9), which follow the Dalio
    # revisions in the order of their names.
    assert len(offered[1:]) == len(set(offered[1:])) == 8, offered
    assert offered[1] == "Стандартный цикл · revision 5 — ready to run"
    assert offered[5] == "Стандартный цикл · revision 4 — ready to run"
    assert all("Dalio five-step cycle · revision " in row for row in offered[2:5])
    assert offered[6:] == ["Short · revision 1 — ready to run",
                           "Standard · revision 1 — ready to run",
                           "Starter documents · revision 1 — ready to run"]
    ready = [row for row in offered[1:] if row.endswith("ready to run")]
    caveated = [row for row in offered[1:] if row.endswith("see the note")]
    # Seven run-ready starters, and still exactly one
    # caveated: the caveat is DERIVED, so revision 3 inherits revision 2's fixed
    # artifact chain rather than a sentence somebody remembered to copy.
    assert len(ready) == 7 and len(caveated) == 1, offered
    # The caveat itself is no longer IN the option -- its 191 characters were
    # the select's intrinsic width and the page's overflow (R08) -- but under
    # the control, for the starter chosen, and it is the DERIVED one, naming
    # the steps it read.
    values = starters.locator("option").evaluate_all(
        "items => items.map(item => item.value)")
    starters.select_option(values[offered.index(caveated[0])])
    said = page.locator("#workflowToolbar [data-starter-note]").inner_text()
    assert "4 review step(s)" in said and "name no result artifact" in said, said
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
