"""The desk reads live cache facts and the provider roster from a real command server."""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, expect

from conductor import server
from conductor.command.http_api import CommandApi
from conductor.command.quota_snapshot_view import HubLimitsView
from browser_tests.test_studio_quotas import quota_project  # noqa: F401
from browser_tests.test_studio_lifecycle import project  # noqa: F401
from tests.test_command_quota_routes import contracts
from tests.test_studio_quotas import EXACT, NAMES


@pytest.fixture
def empty_view_project(monkeypatch, request):
    def make_api(*args, **kwargs):
        kwargs.update(quota_view=HubLimitsView(None), providers=contracts(*NAMES))
        return CommandApi(*args, **kwargs)
    monkeypatch.setattr(server, "CommandApi", make_api)
    return request.getfixturevalue("project")


def test_live_quota_pult_and_people_share_readings_without_claiming_an_account(
        chromium: Browser, quota_project):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors, writes = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: writes.append(request.url)
            if request.method != "GET" else None)
    try:
        page.goto(quota_project.url + "panel/desk.html#panel=people&lang=en")
        expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open")
        pult = page.locator("#deskPult [data-desk-quotas]")
        people = page.locator("#deskPeople")
        expect(pult).to_have_attribute("data-quota-phase", "ready")
        expect(people.locator("#studioQuotas")).to_have_attribute("data-phase", "ready")
        assert pult.locator("[data-quota-bindings]").count() == 5
        assert people.locator(".studio-providers .studio-provider").count() == 6
        expect(pult.locator('[data-quota-bindings="codex-cli codex-alias"]')).to_contain_text("100%")
        expect(people.locator('[data-quota-bindings="dsh-a"]')).to_contain_text(EXACT)
        expect(people.locator('[data-quota-bindings="dsh-a"]')).to_contain_text("Billing account unknown")
        refresh = people.locator('[data-focus-key="quota-read"]')
        refresh.focus()
        refresh.click()
        expect(people.locator("#studioQuotas")).to_have_attribute("data-phase", "ready")
        assert page.evaluate('document.activeElement?.getAttribute("data-focus-key")') == "quota-read"
        assert writes == [] and errors == []
    finally:
        context.close()


def test_real_view_without_snapshot_says_unknown_in_both_quota_surfaces(
        chromium: Browser, empty_view_project):
    context = chromium.new_context()
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(empty_view_project.url + "panel/desk.html#panel=people&lang=ru")
        expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open")
        pult = page.locator("#deskPult [data-desk-quotas]")
        expect(pult).to_have_attribute("data-quota-phase", "no_data")
        expect(page.locator("#deskPeople #studioQuotas")).to_have_attribute("data-phase", "no_data")
        expect(pult).to_contain_text("Нет данных")
        assert pult.locator("[data-quota-bindings]").count() == 0
        assert page.locator("#deskPeople [data-quota-bindings]").count() == 0
        assert errors == []
    finally:
        context.close()
