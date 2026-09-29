"""The wizard's frame, its stepper and step 1, on the real renderer, in Russian and in English.

The model and the renderer are the real modules served from the real server; the host that owns
`state.wizard` and the doors is the few lines in `desk_wizard_bench.py`. Later steps have their
own files (`test_desk_wizard_materials.py`, `_cycle.py`, `_roles.py`).
"""
from __future__ import annotations

import pytest

from browser_tests.desk_wizard_bench import bench, desk_url  # noqa: F401

LANGS = ("ru", "en")
STEP_NAMES = {"ru": ["Задача", "Материалы", "Цикл", "Роли и указания", "Подготовка", "Запуск"],
              "en": ["Task", "Materials", "Cycle", "Roles and instructions", "Preparation",
                     "Run"]}


@pytest.mark.parametrize("lang", LANGS)
def test_the_wizard_opens_on_the_task_step_with_no_field_prefilled(bench, lang):
    bench.open(lang)
    root = bench.root()
    assert root.get_attribute("data-step") == "task" and root.get_attribute("data-mode") == "normal"
    fields = bench.page.locator('[data-body="task"] input, [data-body="task"] textarea')
    assert fields.count() == 3
    assert fields.evaluate_all("nodes => nodes.map(node => node.value)") == ["", "", ""]
    labels = bench.page.locator('[data-body="task"] label > span').all_inner_texts()
    assert labels == [bench.say("wizard.task.title"), bench.say("wizard.task.brief"),
                      bench.say("wizard.task.hint")]
    assert bench.text('[data-field="title"] span') == (
        "Название задачи" if lang == "ru" else "Task name")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_starter_mode_shows_a_title_and_an_idea_and_no_hint(bench, lang):
    bench.open(lang, starter="desk-starter-docs")
    assert bench.root().get_attribute("data-mode") == "starter"
    assert bench.page.locator("[data-field]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.field)") == ["title", "idea"]
    assert bench.text('[data-field="idea"] span') == (
        "Идея проекта" if lang == "ru" else "Project idea")


@pytest.mark.parametrize("lang", LANGS)
def test_the_stepper_lists_six_steps_and_marks_the_last_two_as_not_yet_built(bench, lang):
    bench.open(lang)
    rows = bench.page.locator("[data-wizard-step]")
    assert rows.count() == 6
    ids = rows.evaluate_all("nodes => nodes.map(node => node.dataset.wizardStep)")
    assert ids == ["task", "materials", "cycle", "roles", "prepare", "run"]
    names = rows.evaluate_all(
        "nodes => nodes.map(node => node.querySelector(':scope > :first-child').innerText)")
    assert names == [f"{at + 1}. {name}" for at, name in enumerate(STEP_NAMES[lang])]
    status = rows.evaluate_all("nodes => nodes.map(node => node.dataset.status)")
    assert status == ["current", "blocked", "blocked", "blocked", "later", "later"]
    later = bench.page.locator('[data-status="later"]')
    assert later.locator("button").count() == 0, "a step that is not built is not a control"
    assert all(bench.say("wizard.step_later") in text for text in later.all_inner_texts())
    assert bench.page.locator('[aria-current="step"]').count() == 1


@pytest.mark.parametrize("lang", LANGS)
def test_next_stays_disabled_until_the_title_and_the_brief_are_valid_and_says_why(bench, lang):
    bench.open(lang)
    next_button = bench.control("wizard:next")
    reason = bench.page.locator("[data-wizard-reason]")
    assert next_button.is_disabled()
    assert reason.inner_text() == bench.say("wizard.reason.title_invalid")
    bench.type_into("wizard:title", "Fix login")
    assert next_button.is_disabled()
    assert reason.inner_text() == bench.say("wizard.reason.brief_empty")
    bench.type_into("wizard:brief", "Make the login form accept a plus sign.")
    assert next_button.is_enabled() and reason.inner_text() == ""
    next_button.click()
    assert bench.root().get_attribute("data-step") == "materials"
    assert bench.control("wizard:back").is_enabled()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_step_that_is_blocked_says_why_on_the_stepper(bench, lang):
    bench.open(lang)
    blocked = bench.page.locator('[data-wizard-step="materials"] [title]')
    assert blocked.get_attribute("title") == bench.say("wizard.reason.title_invalid")


@pytest.mark.parametrize("lang", LANGS)
def test_every_control_the_wizard_writes_carries_a_focus_key_and_survives_a_rerender_with_its_caret(
        bench, lang):
    bench.open(lang)
    every = bench.page.locator("[data-wizard] input, [data-wizard] textarea, "
                               "[data-wizard] select, [data-wizard] button")
    assert every.count() >= 5
    assert every.evaluate_all("nodes => nodes.every(node => node.hasAttribute('data-focus'))")
    bench.type_into("wizard:title", "Fix login")
    field = bench.control("wizard:title")
    field.press("Home")
    for _ in range(3):
        field.press("ArrowRight")
    field.press_sequentially("X")
    held = bench.page.evaluate(
        "() => [document.activeElement.dataset.focus, document.activeElement.value,"
        " document.activeElement.selectionStart]")
    assert held == ["wizard:title", "FixX login", 4]
    other = "en" if lang == "ru" else "ru"
    bench.call("setLocale", other)
    after = bench.page.evaluate(
        "() => [document.activeElement.dataset.focus, document.activeElement.value,"
        " document.activeElement.selectionStart]")
    assert after == held, "a redraw in the other language keeps focus, text and caret"
    assert bench.page.locator('[data-field="title"] span').inner_text() != ""
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_typing_a_title_writes_nothing_to_the_browser_storage(bench, lang):
    bench.open(lang)
    bench.type_into("wizard:title", "Fix login")
    bench.type_into("wizard:brief", "A text the browser must not keep.")
    kept = bench.page.evaluate(
        "() => [localStorage.length, sessionStorage.length, document.cookie]")
    assert kept == [0, 0, ""]
    assert bench.page.context.cookies() == []
    assert [row for row in bench.requests if row[0] != "GET"] == []
    assert bench.wizard()["task"]["title"] == "Fix login", "the words live in the wizard's state"
