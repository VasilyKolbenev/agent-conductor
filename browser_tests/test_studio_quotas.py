"""Usage in the real Studio against a real cache GET; no vendor is contacted."""
from __future__ import annotations

from datetime import timedelta
import json

import pytest
from playwright.sync_api import Browser, Page, expect

from conductor import server
from conductor.command.http_api import CommandApi
from conductor.command.quota import QuotaObservation
from tests.test_command_quota import AT, SOURCE, account
from tests.test_command_quota_routes import contracts
from tests.test_quota_connection import observed
from tests.test_studio_quotas import EXACT, MARKUP, NAMES, quota_seed
from browser_tests.test_studio_lifecycle import _open, _start_from_starter, project  # noqa: F401


@pytest.fixture
def quota_project(monkeypatch, request):
    cache, contexts = quota_seed()
    clock = {"now": AT}
    def make_api(*args, **kwargs):
        kwargs.update(quota_service=cache, providers=contracts(*NAMES),
                      clock=lambda: clock["now"].isoformat())
        return CommandApi(*args, **kwargs)
    monkeypatch.setattr(server, "CommandApi", make_api)
    served = request.getfixturevalue("project")
    served.quota_cache, served.quota_contexts, served.quota_clock = cache, contexts, clock
    return served


def _agents(page: Page):
    page.locator("#navAgents").click()
    expect(page.locator("#studioQuotas")).to_have_attribute("data-phase", "ready")
    return page.locator("#studioQuotas")


def _card(page: Page, binding: str):
    # The Agents screen's own card: the shell's 'Usage now' box carries the same bindings.
    return page.locator(f'#studioQuotas [data-quota-bindings="{binding}"]')


def _fact(card, label, value):
    row = card.locator(".studio-quota__fact").filter(has=card.page.locator("dt", has_text=label))
    expect(row.locator("dd")).to_have_text(value)


def _refresh(page: Page):
    with page.expect_response(lambda response: response.url.endswith("/command/quotas")) as heard:
        page.get_by_role("button", name="Refresh usage", exact=True).click()
    assert heard.value.status == 200
    expect(page.locator("#studioQuotas")).to_have_attribute("data-phase", "ready")


def _draft(page, title):
    disclosure = page.locator("#studioTasks details").first
    if disclosure.get_attribute("open") is None:
        disclosure.locator("summary").click()
    page.locator('[data-focus="task-title"]').fill(title)


def _publish(project, total):
    project.quota_clock["now"] += timedelta(seconds=1)
    ticket, context = project.quota_contexts["dsh-a"]
    reading = observed(context, total=total, at=project.quota_clock["now"], version=MARKUP)
    assert project.quota_cache.publish(ticket, reading, now=project.quota_clock["now"])


def test_actual_cache_shows_exact_money_zero_windows_and_unavailable_sources(
        chromium: Browser, quota_project, tmp_path):
    page, window = _open(chromium, quota_project, double=True)
    try:
        box = _agents(page)
        assert box.locator("[data-quota-bindings]").count() == 5
        for name in ("dsh-a", "dsh-b"):
            card = _card(page, name)
            expect(card).to_contain_text(f"{EXACT} CNY")
            expect(card).to_contain_text("Billing account unknown")
            expect(card).to_contain_text("Not applicable (monetary balance)")
            _fact(card, "Source reports funds available", "No")
            expect(card).to_contain_text(MARKUP)
        assert box.locator("img").count() == 0
        subscription = _card(page, "codex-cli codex-alias")
        _fact(subscription, "Used", "0%")
        _fact(subscription, "Remaining", "100%")
        expect(subscription).to_contain_text("2026-09-21 14:00:00 UTC")
        expect(_card(page, "missing")).to_contain_text("Data unavailable")
        expect(_card(page, "failed")).to_contain_text("Source error")
        assert window.writes("/command/") == 0 and window.storage() == [0, 0]
        assert window.page_errors == []
        page.set_viewport_size({"width": 1280, "height": 900})
        for scheme in ("light", "dark"):
            page.emulate_media(color_scheme=scheme)
            assert page.evaluate("document.documentElement.scrollWidth <= 1280")
            page.screenshot(path=str(tmp_path / f"studio-quotas-1280-{scheme}.png"))
    finally:
        page.context.close()


def test_newer_error_replaces_usage_and_stale_window_is_not_a_new_allowance(
        chromium: Browser, quota_project):
    page, window = _open(chromium, quota_project, double=True)
    try:
        _agents(page)
        quota_project.quota_clock["now"] = AT + timedelta(hours=2)
        identity = account()
        ticket = quota_project.quota_cache.bind("codex-cli", identity, SOURCE)
        reading = QuotaObservation(identity, SOURCE, quota_project.quota_clock["now"],
                                   "unavailable", reason="not_authenticated")
        assert quota_project.quota_cache.publish(ticket, reading, now=quota_project.quota_clock["now"])
        _refresh(page)
        subscription = _card(page, "codex-cli codex-alias")
        expect(subscription).to_contain_text("did not confirm a signed-in account")
        assert subscription.locator("[data-quota-window]").count() == 0
        expect(_card(page, "dsh-a")).to_contain_text("Stale — current values are unknown")
        expect(_card(page, "dsh-a")).to_contain_text(f"{EXACT} CNY")
        assert window.writes("/command/") == 0 and window.page_errors == []
    finally:
        page.context.close()


def test_coalesced_refresh_preserves_draft_and_human_notice_while_old_reply_waits(
        chromium: Browser, quota_project):
    page, window = _open(chromium, quota_project, double=True)
    held = []
    try:
        _start_from_starter(page, "quota-draft")
        notice = page.locator("#studioStatus").inner_text()
        nodes = window.node_ids()
        box = _agents(page)
        url = quota_project.url + "command/quotas"
        old = page.request.get(url).json()
        def intercept(route):
            if not held:
                held.append(route)
            else:
                route.continue_()
        page.route(url, intercept)
        before = len([row for row in window.rows if row[1] == url])
        with page.expect_request(url):
            page.get_by_role("button", name="Refresh usage", exact=True).click()
        for _ in range(8):
            page.get_by_role("button", name="Refresh usage", exact=True).click()
        assert len([row for row in window.rows if row[1] == url]) == before + 1
        _draft(page, "Keep this task draft")
        _publish(quota_project, "0.00000000000000000000")
        held[0].fulfill(status=200, content_type="application/json", body=json.dumps(old))
        expect(_card(page, "dsh-a")).to_contain_text("0.00000000000000000000 CNY")
        expect(box).to_have_attribute("data-phase", "ready")
        assert len([row for row in window.rows if row[1] == url]) == before + 2
        assert page.locator('[data-focus="task-title"]').input_value() == "Keep this task draft"
        assert page.locator("#studioStatus").inner_text() == notice and window.node_ids() == nodes
        assert "workflow=quota-draft" in page.url and window.writes("/command/") == 0
        assert window.page_errors == []
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


def test_malformed_wire_never_exposes_private_fields_or_replaces_drafts(
        chromium: Browser, quota_project):
    page, window = _open(chromium, quota_project, double=True)
    try:
        box = _agents(page)
        url = quota_project.url + "command/quotas"
        payload = page.request.get(url).json()
        payload["snapshots"][1]["connection"] = {"context_id": "private-must-not-render"}
        page.route(url, lambda route: route.fulfill(status=200,
                   content_type="application/json", body=json.dumps(payload)))
        _draft(page, "Keep after refusal")
        page.get_by_role("button", name="Refresh usage", exact=True).click()
        expect(box).to_have_attribute("data-phase", "failed")
        expect(box).to_contain_text("Usage could not be read")
        assert box.locator("[data-quota-bindings]").count() == 0
        assert "private-must-not-render" not in box.inner_text()
        assert page.locator('[data-focus="task-title"]').input_value() == "Keep after refusal"
        assert window.writes("/command/") == 0 and window.page_errors == []
    finally:
        page.context.close()


def test_minute_refresh_pauses_outside_agents_and_disposes_on_pagehide(
        chromium: Browser, quota_project):
    page, window = _open(chromium, quota_project, double=True)
    try:
        page.clock.install(time=AT)
        page.clock.pause_at(AT + timedelta(seconds=1))
        _agents(page)
        url = quota_project.url + "command/quotas"
        def count():
            return len([row for row in window.rows if row[1] == url])
        initial = count()
        page.clock.run_for(59999)
        assert count() == initial
        _publish(quota_project, "0.00")
        with page.expect_response(url):
            page.clock.run_for(1)
        expect(_card(page, "dsh-a")).to_contain_text("0.00 CNY")
        assert count() == initial + 1
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true, value:true});"
                      "document.dispatchEvent(new Event('visibilitychange'))")
        page.clock.run_for(120000)
        assert count() == initial + 1
        with page.expect_response(url):
            page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true, value:false});"
                          "document.dispatchEvent(new Event('visibilitychange'))")
        initial += 1
        page.locator("#navWorkflow").click()
        page.clock.run_for(120000)
        assert count() == initial + 1
        _agents(page)
        after_return = count()
        page.evaluate("window.__stream.fire('error')")
        page.clock.run_for(120000)
        assert count() == after_return
        with page.expect_response(url):
            page.evaluate("window.__stream.fire('open')")
        expect(page.locator("#studioQuotas")).to_have_attribute("data-phase", "ready")
        assert count() == after_return + 1
        page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        page.clock.run_for(120000)
        assert count() == after_return + 1 and window.page_errors == []
    finally:
        page.context.close()


BODY_HOLD = """
const original = window.fetch;
window.fetch = async (...args) => {
  const response = await original(...args);
  if (args[0] === '/command/quotas' && window.__holdQuotaBody) {
    window.__holdQuotaBody = false;
    const originalJson = response.json.bind(response);
    response.json = async () => {
      const body = await originalJson();
      return new Promise(resolve => {window.__releaseQuotaBody = () => resolve(body);});
    };
  }
  return response;
};
"""


def test_delayed_real_body_from_before_disconnect_cannot_land_after_reconnect(
        chromium: Browser, quota_project):
    page, window = _open(chromium, quota_project, double=True)
    try:
        _agents(page)
        page.evaluate(BODY_HOLD)
        page.evaluate("window.__holdQuotaBody = true")
        page.get_by_role("button", name="Refresh usage", exact=True).click()
        page.wait_for_function("typeof window.__releaseQuotaBody === 'function'")
        page.evaluate("window.__stream.fire('error')")
        expect(page.locator("#studioQuotas")).to_have_attribute("data-phase", "disconnected")
        _publish(quota_project, "5.50000000000000000001")
        page.evaluate("window.__stream.fire('open')")
        with page.expect_response(quota_project.url + "command/quotas"):
            page.evaluate("window.__releaseQuotaBody()")
        expect(_card(page, "dsh-a")).to_contain_text("5.50000000000000000001 CNY")
        expect(page.locator("#studioQuotas")).to_have_attribute("data-phase", "ready")
        assert window.writes("/command/") == 0 and window.page_errors == []
    finally:
        page.context.close()
