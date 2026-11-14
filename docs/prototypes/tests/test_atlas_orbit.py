"""User-visible checks of the standalone Do scene, run from the project test environment."""
import hashlib
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

PAGE = Path(__file__).resolve().parents[1] / "arachnid-studio.html"
MIXED = "test_mixed_input_counts_only_two_successes"
MANIFEST = "a571e89f5e372830d6a8dd089dfb45af8c3ed1051d81a653b69f7728a91ed415"
FILE_DIGESTS = {
    "runstats/counts.py": (
        "79fd0a46778eaa2ce0f2308a05052204be4c85e8760043fcbe08fd7de09cf6b1",
        "4efe3c904a97cb7cc12dc65d250c9690d7b9f6e35dcd9a7630b37e66b671d03f",
    ),
    "tests/test_counts.py": (
        "471f75c74c82ce8a0cf91f67233bd91419a1f790edcf3635f9a70481eee67997",
        "bbacf376e04084a0760c4d6bf208e5d1fb2107e40d533ca3a2b27c4bc75ee22a",
    ),
}


def test_diff_reconstructs_the_base_and_the_accepted_files():
    recorded = PAGE.with_name("atlas-evidence.js").read_text("utf-8")
    payload = json.loads(recorded.partition("const ATLAS_EVIDENCE = ")[2].strip().removesuffix(";"))
    assert payload["manifest"] == MANIFEST
    assert set(payload["files"]) == set(FILE_DIGESTS)
    for name, (base_hash, accepted_hash) in FILE_DIGESTS.items():
        entry = payload["files"][name]
        assert entry["sha256"] == accepted_hash
        for skip, expected in [("+", base_hash), ("-", accepted_hash)]:
            raw = "".join(line[1:] + "\n" for line in entry["lines"] if line[0] != skip)
            assert hashlib.sha256(raw.encode()).hexdigest() == expected


@pytest.fixture(scope="module")
def chromium():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.mark.parametrize("width", [375, 1280])
def test_orbit_to_checked_test_and_back(chromium, width):
    context = chromium.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    external, errors = [], []
    page.on("request", lambda r: external.append(r.url) if r.url.startswith("http") else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(PAGE.as_uri())
        orbit = page.get_by_role("group", name="Орбита Далио")
        expect(orbit.get_by_role("button")).to_have_count(5)
        step = orbit.get_by_role("button", name="Do · Исполнение")
        step.focus()
        step.press("Enter")
        detail = page.get_by_role("complementary", name="Детали сессии")
        expect(detail).to_be_visible()
        expect(detail).to_contain_text("return len(rows)")
        expect(detail).to_contain_text('row.get("outcome") == "succeeded"')
        detail.get_by_role("button", name="tests/test_counts.py").click()
        expect(detail).to_contain_text("import copy")
        if width == 375:
            page.get_by_role("button", name="Закрыть детали").click()
            expect(step).to_be_focused()
        field = page.get_by_role("textbox", name="Сообщение Атласу")
        field.fill("Какой тест подтверждает исправление?")
        field.press("Enter")
        expect(detail.get_by_role("tab", name="Тесты")).to_have_attribute("aria-selected", "true")
        expect(detail).to_contain_text(MIXED)
        expect(detail).to_contain_text("self.assertEqual(count_succeeded(rows), 2)")
        assertion = detail.get_by_text("self.assertEqual(count_succeeded(rows), 2)", exact=True)
        expect(assertion).to_be_in_viewport()
        if width == 1280:
            expect(page.get_by_role("log")).to_contain_text("12")
            expect(field).to_be_in_viewport()
        detail.get_by_role("tab", name="Изменения").click()
        expect(detail).to_contain_text("import copy")
        detail.get_by_role("tab", name="Проверка").click()
        expect(detail).to_contain_text(MANIFEST)
        expect(detail).to_contain_text("codex-test")
        expect(detail.get_by_role("button", name="Принять")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not external and not errors, (external, errors)
    finally:
        context.close()


def test_details_are_session_scoped_and_plain_text(chromium):
    page = chromium.new_page(viewport={"width": 1440, "height": 900})
    try:
        page.goto(PAGE.as_uri() + "#do")
        detail = page.get_by_role("complementary", name="Детали сессии")
        original = page.get_by_role("textbox", name="Сообщение Атласу")
        original.fill("Неотправленный вопрос")
        detail.get_by_role("button", name="tests/test_counts.py").click()
        page.get_by_role("button", name="Новая сессия").click()
        expect(detail).to_be_hidden()
        original.fill("<mark>Проверить остатки</mark>")
        original.press("Enter")
        expect(page.get_by_role("log")).to_contain_text("<mark>Проверить остатки</mark>")
        expect(page.get_by_role("log").locator("mark")).to_have_count(0)
        expect(page.get_by_role("group", name="Орбита Далио")).to_be_hidden()
        page.get_by_role("button", name="Лимиты", exact=True).click()
        expect(detail).to_contain_text("Нет показаний")
        expect(detail).not_to_contain_text("test_counts.py")
        page.get_by_role("button", name="Исправить счётчик", exact=True).click()
        expect(detail).to_contain_text("import copy")
        expect(original).to_have_value("Неотправленный вопрос")
        page.get_by_role("button", name="Сменить тему").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.get_by_role("button", name="Закрыть детали").click()
        expect(detail).to_be_hidden()
    finally:
        page.context.close()


def test_keyboard_keeps_session_focus_and_closes_the_front_layer_first(chromium):
    page = chromium.new_page(viewport={"width": 1280, "height": 850})
    try:
        page.goto(PAGE.as_uri() + "#do")
        other = page.get_by_role("button", name="Проверить отчёт", exact=True)
        other.focus()
        other.press("Enter")
        expect(other).to_be_focused()
        page.get_by_role("button", name="Исправить счётчик", exact=True).click()
        page.get_by_role("button", name="Диагноз", exact=True).click()
        expect(page.locator('.node[aria-pressed="true"]')).to_have_count(1)
        do_step = page.get_by_role("button", name="Do · Исполнение")
        expect(do_step).to_have_attribute("aria-pressed", "false")
        page.set_viewport_size({"width": 800, "height": 850})
        menu = page.get_by_role("button", name="Сессии", exact=True)
        menu.click()
        expect(page.locator("#detail")).to_have_attribute("inert", "")
        page.keyboard.press("Escape")
        expect(menu).to_be_focused()
        expect(page.get_by_role("complementary")).to_contain_text("Диагноз")
        expect(page.locator("#sidebar")).to_be_hidden()
    finally:
        page.context.close()


def test_atlas_selects_the_surface_for_the_question(chromium):
    page = chromium.new_page()
    try:
        page.goto(PAGE.as_uri())
        field = page.get_by_role("textbox", name="Сообщение Атласу")
        for question, expected in [
            ("Что изменилось?", "Изменения"),
            ("Какой тест исключает failed?", "Тесты"),
            ("Можно принимать?", "Проверка"),
        ]:
            field.fill(question)
            field.press("Enter")
            tab = page.get_by_role("tab", name=expected)
            expect(tab).to_have_attribute("aria-selected", "true")
            expect(page.get_by_role("log")).to_contain_text(question)
            if expected == "Тесты":
                expect(page.get_by_role("tabpanel")).to_contain_text(
                    "test_other_outcomes_and_missing_outcome_are_excluded")
        expect(page.get_by_role("tabpanel")).to_contain_text("codex-test")
    finally:
        page.context.close()
