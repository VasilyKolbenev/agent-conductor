"""A colleague answers only missing questions, editing the same ordinary task draft."""
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.test_desk_wizard_host import wizard_url  # noqa: F401


@pytest.mark.parametrize(("lang", "width"), [("ru", 375), ("en", 1280)])
@pytest.mark.parametrize("wizard_url", [True], indirect=True)
def test_one_sentence_to_review_keeps_each_answer_and_explains_suggestions(chromium, wizard_url, lang, width):
    page = chromium.new_page(viewport={"width": width, "height": 850})
    writes, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda req: writes.append(urlsplit(req.url).path) if req.method == "POST" else None)
    try:
        page.goto(f"{wizard_url}#lang={lang}")
        with page.expect_response(lambda resp: resp.url.endswith("/command/project/git")):
            page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")
        def key(name):
            return form.locator(f'[data-focus="wizard:{name}"]')

        goal = ("Считать только успешные строки." if lang == "ru" else "Count only successful rows.")
        revised = goal + (" Проверить смешанный пример." if lang == "ru" else " Check a mixed sample.")
        expect(key("brief")).to_be_focused()
        expect(key("git:run_without_git")).not_to_be_visible()
        expect(key("brief")).not_to_have_attribute("placeholder", "")
        key("brief").fill(goal)
        expect(key("git:run_without_git")).not_to_be_visible()
        key("next").click()
        expect(form.locator('[data-wizard-current="materials"]')).to_be_visible()
        expect(form.locator('[data-answer="goal"]')).to_contain_text(goal)
        expect(key("git:run_without_git")).to_be_visible()
        expect(key("next")).to_be_disabled()
        key("ask:edit-goal").click()
        expect(key("brief")).to_have_value(goal)
        key("brief").fill(revised)
        form.locator('[data-guide-details="optional"] summary').click()
        key("hint").fill("Use a mixed sample.")
        key("next").click()
        expect(form.locator('[data-answer="goal"]')).to_contain_text(revised)
        key("git:run_without_git").click()
        key("next").click()
        team = form.locator('[data-guide-stage="team"]')
        expect(team).to_have_attribute("aria-current", "step")
        expect(form.locator("[data-cycle-reason]")).to_be_visible()
        expect(form.locator('[data-guide-role="checker"] [data-assignment-reason]').first).to_be_visible()
        expect(form.locator('[data-guide-role="executor"] [data-assignment-reason]').first).to_be_visible()
        expect(form.locator('[data-answer="goal"]')).to_contain_text(revised)
        form.locator('[data-guide-details="assignments"] summary').click()
        pick = key("role:role-checker")
        pick.select_option("claude-code")
        key("mode").click()
        key("next").click()
        expect(key("role:role-checker")).to_have_value("claude-code")
        key("mode").click()
        expect(form.locator('[data-guide-role="checker"]')).to_contain_text("claude-code")
        if not key("role:role-checker").is_visible():
            form.locator('[data-guide-details="assignments"] summary').click()
        key("role:role-checker").select_option("codex")
        key("next").click()
        with page.expect_request(lambda req: req.method == "POST" and req.url.endswith("/artifacts")) as written:
            key("prepare:go").click()
        assert "Use a mixed sample." in str(written.value.post_data_json)
        expect(form.locator("[data-guide-executors]")).to_be_visible()
        expect(form.locator("[data-owner-gates]")).to_have_count(1)
        assert any(path.endswith("/automation/preview") for path in writes)
        assert not any(path.endswith("/automation/authorize") for path in writes)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        page.context.close()
