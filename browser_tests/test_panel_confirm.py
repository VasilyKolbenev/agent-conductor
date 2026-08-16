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
from playwright.sync_api import Browser, Page, sync_playwright

from browser_tests.test_panel_rendered import _contrast
from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_adapters import FakeAdapter
from tests.test_command_run_store import CONFIG, a_run
from tests.test_store import good_lane, write_project


RUN_ID = "run-cockpit-confirm"
TOKEN = "browser-only-process-token"
HOSTILE = '<img src=x onerror="window.__pwned = 1">'
ACCEPTED = "Action request accepted and recorded. Nothing was executed."


@pytest.fixture(scope="module")
def chromium() -> Iterator[Browser]:
    """Launch the same Chromium engine the independent CI job installs."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def cockpit_url(tmp_path) -> Iterator[str]:
    """Serve one confirm-mode run with a bound adapter through the real server."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    store = RunStore(root)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    httpd = server.build(
        root, 0, registry=AdapterRegistry([FakeAdapter()]),
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}/"
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
