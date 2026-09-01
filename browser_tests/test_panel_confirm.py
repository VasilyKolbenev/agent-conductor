"""The explicit Confirm control, driven in a real browser against the real server.

The fast suite in ``tests/test_panel_command_source.py`` reasons about the
Cockpit's source text. This module crosses the boundary that the Confirm slice
actually needs crossed: a real loopback server, a real run in ``confirm`` mode, a
real adapter, Chromium executing the shipped module graph, and every request the
page makes recorded — so "POST /actions fires only after a separate Human click"
is counted rather than argued about.

It lives outside pytest's configured ``testpaths`` for the same reason as
``test_panel_rendered``: Playwright stays an explicit development/CI dependency.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from browser_tests.test_panel_rendered import _contrast
from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_run_store import CONFIG, a_run
from tests.test_command_schema_doubles import DeepDispatchAdapter
from tests.test_store import good_lane, write_project


RUN_ID = "run-cockpit-confirm"
TOKEN = "browser-only-process-token"
HOSTILE = '<img src=x onerror="window.__pwned = 1">'
ACCEPTED = "Action request accepted and recorded. Nothing was executed."


@pytest.fixture
def cockpit_url(tmp_path) -> Iterator[str]:
    """Serve one confirm-mode run with a bound adapter through the real server.

    The adapter DECLARES the argument family this API speaks, and it has to.
    The pair authority admits a proposal only when the bound adapter records
    a schema for that capability, so the schema-less `FakeAdapter` this
    fixture used to bind stopped being able to propose at all: the POST
    answered `409 capability_unsupported` and the Cockpit said so, honestly,
    while every test waiting for a created proposal timed out.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    store = RunStore(root)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    httpd = server.build(
        root, 0, registry=AdapterRegistry([DeepDispatchAdapter()]),
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        # The classic panel's own route: `GET /` is the Workflow Studio's
        # shell now, and the Cockpit under test is mounted by index.html.
        yield f"http://{host}:{port}/panel/index.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "cockpit server did not stop"


class _Recorder:
    """Every request the page issues, so the action route can be counted."""

    def __init__(self, page: Page) -> None:
        self.rows: list[tuple[str, str, str | None]] = []
        page.on("request", lambda request: self.rows.append(
            (request.method, request.url, request.post_data)))

    def actions(self) -> list[tuple[str, str, str | None]]:
        return [row for row in self.rows if "/actions" in row[1]]


def _open(chromium: Browser, url: str, **context: object) -> tuple[Page, _Recorder]:
    page = chromium.new_context(**context).new_page()
    recorder = _Recorder(page)
    page.goto(url, wait_until="load")
    return page, recorder


def _load_run(page: Page) -> None:
    page.locator("#commandRunId").fill(RUN_ID)
    page.get_by_role("button", name="Load run").click()
    page.locator(".command-proposal-form").wait_for(state="visible")


def _create_proposal(page: Page, rationale: str = "Implement the item.") -> None:
    form = page.locator(".command-proposal-form")
    form.locator('input[name="scope"]').fill("src, tests")
    form.locator('input[name="rationale"]').fill(rationale)
    form.locator('input[name="argument:work_item_id"]').fill("work-001")
    form.locator('input[name="argument:instruction_ref"]').fill("instruction-001")
    form.locator('input[name="argument:artifact_refs"]').fill("artifact-001")
    form.locator('select[name="argument:profile"]').select_option("implement")
    form.locator('select[name="argument:output_limit_profile"]').select_option("small")
    form.locator('button[type="submit"]').click()
    page.locator('[data-proposal-state="created"]').wait_for()


def _snapshot(page: Page) -> dict[str, str]:
    return page.locator(".command-review").evaluate(
        """review => Object.fromEntries(
          [...review.querySelectorAll(".command-review-fact")].map(row => [
            row.querySelector("strong").textContent,
            row.querySelector("span").textContent,
          ]))"""
    )


def test_confirm_posts_one_snapshot_bound_request_only_after_a_human_click(
        chromium: Browser, cockpit_url: str) -> None:
    """The composer may change after the proposal; the confirmed body may not."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        assert recorder.actions() == []
        facts = _snapshot(page)

        # A Human edits the live composer after the immutable snapshot exists.
        page.locator('.command-proposal-form input[name="scope"]').fill("docs")
        page.locator('.command-proposal-form input[name="rationale"]').fill("changed")
        assert recorder.actions() == []

        page.locator("#commandConfirmedBy").fill("release-owner")
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.locator('[data-confirm-state="accepted"]').wait_for()

        assert len(recorder.actions()) == 1
        method, url, body = recorder.actions()[0]
        assert method == "POST"
        assert url.endswith(f"/command/runs/{RUN_ID}/actions")
        assert json.loads(body) == {
            "proposal_id": facts["proposal_id"],
            "preview_digest": facts["preview_digest"],
            "config_digest": facts["config_digest"],
            "capability": "dispatch",
            "scope": ["src", "tests"],
            "confirmed_by": "release-owner",
        }
        assert TOKEN not in body and TOKEN not in url
        assert page.locator(".command-confirm-status").text_content() == ACCEPTED
        assert page.locator(".command-action-fact strong").all_text_contents() == [
            "action_id", "capability", "mode"]
    finally:
        page.context.close()


def test_the_local_session_token_reaches_no_dom_url_cookie_or_storage(
        chromium: Browser, cockpit_url: str) -> None:
    """The CSRF token is a request header and nothing else the page keeps."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        page.locator("#commandConfirmedBy").fill("release-owner")
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.locator('[data-confirm-state="accepted"]').wait_for()
        assert len(recorder.actions()) == 1

        leaks = page.evaluate(
            """() => ({
              markup: document.documentElement.outerHTML,
              cookie: document.cookie,
              local: JSON.stringify(Object.entries(localStorage)),
              session: JSON.stringify(Object.entries(sessionStorage)),
              url: location.href,
            })"""
        )
        assert leaks["cookie"] == ""
        assert leaks["local"] == "[]" and leaks["session"] == "[]"
        assert "?" not in leaks["url"] and "#" not in leaks["url"]
        assert all(TOKEN not in value for value in leaks.values())
        assert all(TOKEN not in (url + (body or "")) for _, url, body in recorder.rows)
    finally:
        page.context.close()


def test_load_signals_reconnect_and_proposal_success_never_touch_the_action_route(
        chromium: Browser, cockpit_url: str) -> None:
    """Only the click mutates: signals refresh facts and disable the controls."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        page.locator("#commandConfirmedBy").fill("release-ow")
        page.evaluate(
            """runId => window.dispatchEvent(new CustomEvent("conduct:run", {
              detail: Object.freeze({run_id: runId}),
            }))""",
            RUN_ID,
        )
        page.wait_for_timeout(300)
        # A refresh must not eat what the Human already typed into the control.
        assert page.locator("#commandConfirmedBy").input_value() == "release-ow"

        page.evaluate("() => window.dispatchEvent(new Event('conduct:disconnected'))")
        assert page.locator("#commandCockpit").get_attribute("data-phase") == "stale"
        assert page.locator("#commandConfirmedBy").is_disabled()
        assert page.get_by_role(
            "button", name="Confirm unchanged proposal").is_disabled()

        page.evaluate("() => window.dispatchEvent(new Event('conduct:connected'))")
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        page.reload(wait_until="load")
        assert recorder.actions() == []
    finally:
        page.context.close()


def test_hostile_text_stays_text_and_a_hostile_actor_never_reaches_the_wire(
        chromium: Browser, cockpit_url: str) -> None:
    """Markup in durable facts renders inert, and a bad actor name never posts."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page, rationale=HOSTILE)
        rationale = page.locator(".command-review-fact").last.locator("span")
        assert rationale.text_content() == HOSTILE
        assert "&lt;img" in rationale.inner_html()
        assert page.locator(".command-review img").count() == 0
        assert page.evaluate("() => window.__pwned") is None

        page.locator("#commandConfirmedBy").fill("<b>owner</b>")
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.wait_for_timeout(300)
        assert recorder.actions() == []
        # patternMismatch, not merely invalid: a `pattern` the browser cannot
        # compile is ignored outright, and this names the constraint that held.
        assert page.locator("#commandConfirmedBy").evaluate(
            "node => [node.checkValidity(), node.validity.patternMismatch]"
        ) == [False, True]
        assert page.locator('[data-confirm-state="accepted"]').count() == 0
    finally:
        page.context.close()


#: Does a pattern compile the way a browser really compiles one? Asked in the
#: page's own engine, because no Python regex library has `v` semantics.
_COMPILES_UNDER_V = (
    "(p) => { try { new RegExp('^(?:' + p + ')$', 'v'); return true; }"
    " catch (error) { return String(error); } }")


def _validity(field) -> list[bool]:
    """``[checkValidity(), patternMismatch]`` for one field, read from the engine.

    ``patternMismatch`` rather than "not valid": an empty required field is
    invalid too, so a test that only asked whether the field was valid would
    pass while the pattern did nothing at all.
    """
    return field.evaluate(
        "node => [node.checkValidity(), node.validity.patternMismatch]")


def test_the_run_id_field_really_refuses_a_bad_id_in_this_engine(
        chromium: Browser, cockpit_url: str) -> None:
    """The run-id field's own native validation, asserted in a real engine.

    Born red. The shipped attribute carried a bare trailing `-` in its class. A
    browser compiles `pattern` with the RegExp `v` flag first, where that is a
    syntax error, and **a pattern that fails to compile is IGNORED rather than
    enforced** -- so the field looked validated and accepted anything. Measured
    on chromium 151.0.7922.34 before the fix: `!!! not a run id !!!` gave
    `patternMismatch=false` and `checkValidity()=true`. The sibling
    `confirmed_by` field above and `graph-view.js` already carried the escape;
    this one field did not, which is how the two surfaces came to disagree while
    every source test stayed green.

    **No expected pattern is written here.** This reads what really shipped off
    the live DOM and asks the ENGINE about it. Spelling the pattern out would
    pass on any build whose attribute matched the spelling -- including one the
    browser silently discards, which is the defect itself. The compile check is
    held separately from the validity check because a validity check alone goes
    quiet again, and just as invisibly, the day some other character in the
    class stops compiling.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        run_id = page.locator("#commandRunId")
        run_id.wait_for(state="visible")
        shipped = run_id.get_attribute("pattern")
        assert shipped, "the run id field ships no pattern at all"

        compiled = page.evaluate(_COMPILES_UNDER_V, shipped)
        assert compiled is True, (
            f"the shipped run-id pattern does not compile, so the browser "
            f"ignores it and the field enforces nothing: {compiled}")

        for bad in ("!!! not a run id !!!", "-leading-hyphen", "has space"):
            run_id.fill(bad)
            assert _validity(run_id) == [False, True], f"accepted {bad!r}"
        # The positive control. Without it a pattern refusing EVERYTHING would
        # satisfy every assertion above; the hyphen case is the one the escape
        # is about, so it is not optional here.
        for good in ("run-model-routing", "run.1", "A0", "a" * 128):
            run_id.fill(good)
            assert _validity(run_id) == [True, False], f"refused {good!r}"
    finally:
        page.context.close()


def test_the_confirm_control_is_operable_and_announced_from_the_keyboard(
        chromium: Browser, cockpit_url: str) -> None:
    """Keyboard alone completes it, and one stable live region carries the news."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        status = page.locator(".command-confirm-status")
        assert status.get_attribute("aria-live") == "polite"
        status.evaluate("node => { node.dataset.liveProbe = 'kept'; }")
        assert page.locator(
            'section.command-confirm[aria-labelledby="commandConfirmTitle"]'
        ).count() == 1
        assert page.locator("#commandConfirmTitle").text_content() == (
            "Confirm unchanged proposal")
        assert page.locator("#commandConfirmedBy").get_attribute(
            "aria-describedby") == "commandConfirmNote"
        assert page.locator("#commandConfirmNote").count() == 1

        # Locator key presses wait for an enabled control the way a click does:
        # an authoritative refresh disables the form, and a raw keystroke sent
        # into that window would be silently dropped.
        actor = page.locator("#commandConfirmedBy")
        actor.focus()
        assert page.evaluate("() => document.activeElement.id") == "commandConfirmedBy"
        actor.press_sequentially("release-owner")
        actor.press("Enter")
        page.locator('[data-confirm-state="accepted"]').wait_for()

        assert len(recorder.actions()) == 1
        # The outcome re-renders the control; the Human must not be dropped to
        # the top of the document by their own confirmation.
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        page.wait_for_function(
            "() => document.activeElement.id === 'commandConfirmedBy'")
        assert page.locator(".command-confirm-status").count() == 1
        assert status.get_attribute("data-live-probe") == "kept"
        assert status.text_content() == ACCEPTED
    finally:
        page.context.close()


@pytest.mark.parametrize("scheme", ("dark", "light"))
def test_the_confirm_control_holds_at_360px_in_both_schemes_without_motion(
        chromium: Browser, cockpit_url: str, scheme: str) -> None:
    """The narrowest supported viewport, both palettes, motion switched off."""
    page, recorder = _open(
        chromium, cockpit_url, color_scheme=scheme, reduced_motion="reduce",
        viewport={"width": 360, "height": 780})
    try:
        _load_run(page)
        _create_proposal(page)
        page.locator("#commandConfirmedBy").fill("release-owner")
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.locator('[data-confirm-state="accepted"]').wait_for()
        assert len(recorder.actions()) == 1

        assert page.locator("#commandCockpit").evaluate(
            "node => node.scrollWidth <= node.clientWidth")
        assert page.evaluate(
            "() => document.documentElement.scrollWidth"
            " <= document.documentElement.clientWidth")
        for selector in (
                ".command-confirm-submit", ".command-confirm-note",
                ".command-confirm-status", ".command-action-fact span"):
            assert _contrast(page, selector) >= 4.5
        # Resolved and measured inside one evaluation: the post-confirm refresh
        # re-renders the control, and a node read across two calls can be gone.
        page.wait_for_function(
            """() => {
              const node = document.querySelector(".command-confirm-submit");
              if (!node) return false;
              const style = getComputedStyle(node);
              return style.transitionDuration === "0s"
                && style.animationName === "none";
            }"""
        )
    finally:
        page.context.close()


# -- the keyboard survives an authoritative refresh ---------------------------

#: Focus a control, let the background refresh land INSIDE the same task, and
#: read where the keyboard is -- all without yielding to the event loop.
#:
#: `dispatchEvent` is synchronous, and so is everything the listener does up to
#: its first `await`: the phase moves, the form is re-rendered, and the focused
#: node is replaced, all before this function returns. So the read below is
#: taken at the exact instant the old test was sampling by luck. Nothing here
#: waits for a timing window to repeat.
_REFRESH_UNDER_FOCUS = """(asked) => {
  const control = document.querySelector(asked.selector);
  control.focus();
  const before = document.activeElement === control;
  window.dispatchEvent(new CustomEvent("conduct:run", {
    detail: Object.freeze({run_id: asked.runId})}));
  const active = document.activeElement;
  // BOTH names. These controls carry an id and a form name, and a probe that
  // picked one would report a real focus under a spelling the caller does not
  // use -- which reads exactly like the focus having been lost.
  return {before,
          id: active ? (active.id || "<body>") : "none",
          name: active ? (active.getAttribute("name") || "<none>") : "none",
          phase: document.getElementById("commandCockpit").dataset.phase};
}"""


def _refresh_under_focus(page: Page, selector: str) -> dict:
    return page.evaluate(_REFRESH_UNDER_FOCUS,
                         {"selector": selector, "runId": RUN_ID})


def test_a_background_refresh_never_takes_the_keyboard_out_of_the_confirm(
        chromium: Browser, cockpit_url: str) -> None:
    """WRITTEN RED, against a measured defect this suite was sampling.

    A run signal re-reads the authoritative facts, and that render replaces the
    node the person is typing in. The panel HAS a restoration for exactly this
    -- `renderConfirm` re-focuses the rebuilt control -- but it declined to
    when the form was disabled, and a background refresh disabled it. So the
    keyboard was taken away for the length of the read: measured at 8ms idle,
    and long enough under gate load that the test above failed twice on two
    different trees while passing eight times in a row on an idle host.

    The read here happens INSIDE the dispatch, so it cannot pass by luck: at
    the instant the refresh has re-rendered the form, the keyboard is still in
    the field, and the phase is asserted so this cannot pass by the refresh
    never having happened.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)

        seen = _refresh_under_focus(page, "#commandConfirmedBy")

        assert seen["before"] is True, "the control never took focus at all"
        assert seen["phase"] == "refreshing", (
            "the refresh did not land inside the dispatch, so this proves "
            "nothing about what a refresh does")
        assert seen["id"] == "commandConfirmedBy", seen
        # And it is still there once the read has landed.
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        assert page.evaluate(
            "() => document.activeElement.id") == "commandConfirmedBy"
    finally:
        page.context.close()


def test_a_background_refresh_never_takes_the_keyboard_out_of_the_composer(
        chromium: Browser, cockpit_url: str) -> None:
    """The same claim on the form a person types in most, where it was worse.

    The composer had no restoration at all, so a refresh did not merely open a
    window -- the keyboard never came back. Measured: focus `rationale`, signal,
    and the document is left on `<body>` for good.

    The field is named, because a restoration that put a person in the FIRST of
    six controls would satisfy "focus is somewhere in the form" while moving
    them somewhere they did not choose.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)

        seen = _refresh_under_focus(
            page, '.command-proposal-form [name="rationale"]')

        assert seen["before"] is True
        assert seen["phase"] == "refreshing", seen
        assert seen["name"] == "rationale", seen
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        assert page.evaluate(
            '() => document.activeElement.getAttribute("name")') == "rationale"
    finally:
        page.context.close()


def test_a_refresh_takes_no_focus_into_a_form_nobody_was_working_in(
        chromium: Browser, cockpit_url: str) -> None:
    """The other direction, and the one a restoration gets wrong.

    Giving the keyboard back is only correct for somebody who had it. A render
    that focused its form whenever it ran would move a person reading the
    journal, or working the run-id field at the top, into a form they never
    opened -- which is the same theft this slice is removing, wearing the
    opposite sign.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        page.locator("#commandRunId").focus()

        seen = _refresh_under_focus(page, "#commandRunId")

        assert seen["phase"] == "refreshing", seen
        assert seen["id"] == "commandRunId", seen
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        assert page.evaluate(
            "() => document.activeElement.id") == "commandRunId"
    finally:
        page.context.close()


def test_a_lost_connection_still_shuts_both_forms_and_says_so(
        chromium: Browser, cockpit_url: str) -> None:
    """What a background read may take away, and what a DEAD LINE still must.

    The fix says a refresh is not a reason to shut a form. That is only honest
    if the reasons that remain still shut it, so the other side is asserted
    here on the phase that has always meant "nothing may be written": the
    connection is down, and neither form is workable until it is back.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        assert not page.locator("#commandConfirmedBy").is_disabled()

        page.evaluate(
            "() => window.dispatchEvent(new Event('conduct:disconnected'))")

        assert page.locator("#commandCockpit").get_attribute(
            "data-phase") == "stale"
        assert page.locator("#commandConfirmedBy").is_disabled()
        assert page.locator(
            '.command-proposal-form [name="rationale"]').is_disabled()
    finally:
        page.context.close()
