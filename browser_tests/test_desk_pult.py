"""The desk's console in a real Chromium: the actor line, the project queue and the view lines.

Two kinds of measurement, both on the production server's desk page:

- the queue block is drawn from lane D1's fixtures of the task-queue read
  (`tests/fixtures/desk/queue_read.json`, spec 4.4.6; lane L's route is not served yet), by the
  real `desk-pult.js` and `desk-queue-model.js` mounted into the page's own console, so what is
  read is the real CSS, the real width of the column and the real `innerText`, in Russian and
  English, in a zone the test names;
- the actor line and the view lines are measured on the booted desk itself: the name asked for
  once and kept in the page's memory and nowhere else, a refused name, a name typed and not yet
  saved that survives a redraw, a desk that went foreign drawing nothing, and a framed desk whose
  project claim says `view` saying so (through the embed rig of `test_desk_embed.py`).

A fact and its sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from browser_tests.test_desk_embed import (  # noqa: F401  (fixtures and helpers)
    Embedded, Rig, _answering, _claim, embed, rig)
from browser_tests.test_desk_hash import (  # noqa: F401  (fixtures and helpers)
    FACTS, PROJECT_A, QUIET, _go, open_desk)
from browser_tests.test_desk_rail_scene import SETTLED, seeded_url  # noqa: F401  (a fixture)
from browser_tests.test_desk_status import RAW

QUEUES = json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "desk"
                     / "queue_read.json").read_text(encoding="utf-8"))["cases"]
MOSCOW = "Europe/Moscow"
#: The tasks and runs the holder of a busy slot is found in: the desk's own lists, as the routes
#: spell their rows.
TASKS = [{"task_id": "task-fix", "title": "Fix lost text", "unreadable": False}]
RUNS = [{"run_id": "run-fix-new", "task_id": "task-fix"}]
#: What the console says of the actor, in each language.
ACTOR = {
    "en": {"none": "You: name not given · set", "named": "You: vasya · change",
           "label": "Your name (it signs what is recorded in your name)",
           "hint": "Use letters and digits, then dots, hyphens or underscores; "
                   "up to 128 characters.", "save": "Save", "cancel": "Cancel"},
    "ru": {"none": "Вы: имя не указано · указать", "named": "Вы: vasya · изменить",
           "label": "Ваше имя (оно подписывает записи от вашего имени)",
           "hint": "Латинские буквы и цифры, затем точки, дефисы или подчёркивания; "
                   "до 128 знаков.", "save": "Сохранить", "cancel": "Отмена"}}
HEAD = {"en": "Your console", "ru": "Ваш пульт"}
CHANGE = '#deskPult [data-focus-key="pult:actor-change"]'
NAME = '#deskPult [data-focus-key="pult:actor-name"]'
SAVE = '#deskPult [data-focus-key="pult:actor-save"]'
CANCEL = '#deskPult [data-focus-key="pult:actor-cancel"]'
#: Everything a test asks of the console, in one evaluation. The rows of the queue block are read
#: by `textContent`: the headings are drawn in capitals by the style, and what a screen reader
#: says is the text of the node, not its capitals. `text` is the rendered `innerText`, and is
#: what the raw-token check reads.
PULT = """() => {
  const pult = document.getElementById("deskPult");
  const form = pult.querySelector("form");
  const actor = pult.querySelector(".desk-pult__actor");
  const block = pult.querySelector(".desk-queue");
  return {
    state: pult.getAttribute("data-state"), children: pult.childElementCount,
    head: pult.querySelector(".desk-pult__head")?.textContent ?? null,
    actor: actor ? actor.innerText.trim() : null, form: form !== null,
    label: form ? form.querySelector("label span").textContent : null,
    input: form ? form.querySelector("input").value : null,
    hint: form ? form.querySelector(".desk-pult__hint").textContent : null,
    hintHidden: form ? form.querySelector(".desk-pult__hint").hidden : null,
    save: form ? form.querySelectorAll("button")[0].textContent : null,
    cancel: form ? form.querySelectorAll("button")[1].textContent : null,
    focus: document.activeElement?.getAttribute("data-focus-key") ?? null,
    block: block ? [...block.querySelectorAll("h3, p, li")].map((node) => node.textContent.trim())
      : null,
    text: pult.innerText, lang: document.documentElement.lang,
    storage: [localStorage.length, sessionStorage.length], cookie: document.cookie,
    hash: location.hash,
    small: [...pult.querySelectorAll("button, input")]
      .filter((node) => node.getBoundingClientRect().height < 44).length,
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""
#: The queue drawn from a fixture by the real modules, mounted into the console the desk booted.
BENCH = """async ({locale, mode, actor, editing, body, tasks, runs}) => {
  const [pult, model] = await Promise.all([
    import("/panel/desk-pult.js"), import("/panel/desk-queue-model.js")]);
  const handlers = {setActor: () => true, editActor: () => {}, cancelActor: () => {}};
  const view = {locale, foreign: false, mode, actor, editing, tasks: {list: tasks},
    runs: {list: runs}, queue: body === null ? null : model.projectQueue(body)};
  pult.mountPult(document.getElementById("deskPult"), view, handlers);
  return true;
}"""


@pytest.fixture
def bench(chromium: Browser, seeded_url: str) -> Iterator[Callable[..., dict]]:  # noqa: F811
    """A factory: the desk's page in a language, its console redrawn from a fixture."""
    contexts = []

    def make(language: str, body: dict | None, *, mode: str | None = "active",
             actor: str | None = None, editing: bool = False, width: int = 1280) -> dict:
        context = chromium.new_context(viewport={"width": width, "height": 900},
                                       timezone_id=MOSCOW, locale=language)
        contexts.append(context)
        page: Page = context.new_page()
        problems: list[str] = []
        page.on("console", lambda message: problems.append(message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.goto(f"{seeded_url}#lang={language}", wait_until="load")
        page.wait_for_function(SETTLED)
        page.evaluate(BENCH, {"locale": language, "mode": mode, "actor": actor,
                              "editing": editing, "body": body, "tasks": TASKS, "runs": RUNS})
        facts = page.evaluate(PULT)
        assert problems == []
        return facts

    yield make
    for context in contexts:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("case", QUEUES, ids=[case["name"] for case in QUEUES])
def test_the_queue_block_says_each_fixture_read_in_the_page_and_no_machine_word_reaches_it(
        bench, case, language):
    facts = bench(language, case["body"], mode=case["mode"])
    assert facts["block"] == case["text"][language]
    assert not RAW.search(facts["text"]), RAW.search(facts["text"]).group(0)
    assert facts["head"] == HEAD[language]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_queue_that_was_not_read_draws_no_block_and_a_view_project_still_says_so(
        bench, language):
    """Nothing is drawn for a queue nobody read, and "nothing is queued" is never said of one
    that is unknown; in `view` the two lines of the mode stand, and the queue's rows do not."""
    silent = bench(language, None, mode="active")
    unknown = bench(language, None, mode=None)
    view = bench(language, None, mode="view")
    assert silent["block"] is None and unknown["block"] is None
    assert view["block"] == [line for line in QUEUES[3]["text"][language]
                             if not line.startswith("1.")]
    assert all(facts["state"] == "ready" for facts in (silent, unknown, view))


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_console_says_the_actor_before_and_after_a_name(bench, language):
    said = ACTOR[language]
    assert bench(language, None, actor=None)["actor"] == said["none"]
    assert bench(language, None, actor="vasya")["actor"] == said["named"]


@pytest.mark.parametrize("width", [320, 375, 600, 899, 900, 1280])
def test_no_control_of_the_console_is_under_44px_and_the_page_never_scrolls_sideways(
        bench, width):
    """The busiest console: the longest queue, the sentence of the view, and the name form."""
    facts = bench("ru", QUEUES[2]["body"], mode="view", actor="a" * 128, editing=True,
                  width=width)
    assert facts["form"] and facts["small"] == 0 and facts["overflow"] <= 0
    quiet = bench("en", QUEUES[2]["body"], mode="active", actor="a" * 128, width=width)
    assert quiet["small"] == 0 and quiet["overflow"] <= 0


# -- the actor on the booted desk ------------------------------------------------------------
@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_name_is_asked_for_once_kept_in_the_pages_memory_and_nowhere_else(
        open_desk, language):
    window = open_desk(f"#lang={language}")
    page, said = window.page, ACTOR[language]
    page.wait_for_function(SETTLED)
    first = page.evaluate(PULT)
    assert (first["actor"], first["form"], first["state"]) == (said["none"], False, "ready")
    assert first["head"] == HEAD[language] and first["block"] is None
    page.click(CHANGE)
    form = page.evaluate(PULT)
    assert (form["form"], form["label"], form["input"], form["hintHidden"]) == (
        True, said["label"], "", True)
    assert (form["hint"], form["save"], form["cancel"]) == (
        said["hint"], said["save"], said["cancel"])
    assert form["focus"] == "pult:actor-name"
    page.fill(NAME, "vasya")
    page.click(SAVE)
    done = page.evaluate(PULT)
    assert (done["actor"], done["form"], done["focus"]) == (
        said["named"], False, "pult:actor-change")
    assert done["storage"] == [0, 0] and done["cookie"] == "" and "vasya" not in done["hash"]
    page.click(CHANGE)
    assert page.evaluate(PULT)["input"] == "vasya"
    page.reload(wait_until="load")
    page.wait_for_function(SETTLED)
    assert page.evaluate(PULT)["actor"] == said["none"]
    assert {method for method, _path, _header in window.asked} == {"GET"}
    assert window.problems == []


@pytest.mark.parametrize("name", ["", "   ", "a b", "-x", "_x", ".x", "a/b", "x" * 129,
                                  "имя", "a;b"])
def test_a_name_outside_the_id_grammar_is_refused_in_place_and_the_typed_text_stays(
        open_desk, name):
    """The length limit of the field is lifted first, so it is the boot module's grammar that
    refuses a name of 129 characters and not the field that cut it short."""
    window = open_desk("#lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    page.click(CHANGE)
    page.eval_on_selector(NAME, "(input) => input.removeAttribute('maxlength')")
    page.fill(NAME, name)
    page.click(SAVE)
    facts = page.evaluate(PULT)
    assert (facts["form"], facts["hintHidden"], facts["focus"]) == (
        True, False, "pult:actor-name")
    assert facts["input"] == name
    page.click(CANCEL)
    assert page.evaluate(PULT)["actor"] == ACTOR["en"]["none"]
    assert window.problems == []


def test_the_name_field_cuts_what_is_typed_at_128_characters(open_desk):
    window = open_desk("#lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    page.click(CHANGE)
    assert page.get_attribute(NAME, "maxlength") == "128"
    page.fill(NAME, "a" * 130)
    assert page.evaluate(PULT)["input"] == "a" * 128
    assert window.problems == []


def test_a_name_at_the_ends_of_the_grammar_is_kept_and_a_padded_one_is_trimmed(open_desk):
    window = open_desk("#lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    for typed, kept in (("A", "A"), ("a" * 128, "a" * 128), ("  vasya.p-1_b  ", "vasya.p-1_b")):
        page.click(CHANGE)
        page.fill(NAME, typed)
        page.click(SAVE)
        assert page.evaluate(PULT)["actor"] == f"You: {kept} · change"
    assert window.problems == []


def test_cancelling_keeps_the_name_that_stood_and_returns_the_keyboard_to_the_button(open_desk):
    window = open_desk("#lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    page.click(CHANGE)
    page.fill(NAME, "vasya")
    page.click(SAVE)
    page.click(CHANGE)
    page.fill(NAME, "someone-else")
    page.click(CANCEL)
    facts = page.evaluate(PULT)
    assert (facts["actor"], facts["form"], facts["focus"]) == (
        "You: vasya · change", False, "pult:actor-change")
    assert window.problems == []


def test_words_typed_and_not_saved_survive_a_redraw_and_are_said_in_the_new_language(open_desk):
    window = open_desk("#lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    page.click(CHANGE)
    page.fill(NAME, "va")
    _go(page, "#lang=ru")
    page.wait_for_function("() => document.documentElement.lang === 'ru'")
    facts = page.evaluate(PULT)
    assert (facts["input"], facts["focus"], facts["label"]) == (
        "va", "pult:actor-name", ACTOR["ru"]["label"])
    assert window.problems == []


def test_a_desk_that_went_foreign_draws_nothing_in_the_console_and_keeps_no_name(open_desk):
    window = open_desk(f"#project={PROJECT_A}&lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    page.click(CHANGE)
    page.fill(NAME, "vasya")
    page.click(SAVE)
    assert page.evaluate(PULT)["actor"] == "You: vasya · change"
    _go(page, f"#project={'b' * 32}&lang=en")
    page.wait_for_function(
        "() => document.getElementById('deskShell').getAttribute('data-state') === 'refused'")
    facts = page.evaluate(PULT)
    assert (facts["children"], facts["state"], facts["text"].strip()) == (0, "empty", "")
    assert window.problems == []


# -- the mode on a framed desk ---------------------------------------------------------------
def _framed(embed: Callable[..., Embedded], rig: Rig, language: str, mode: str) -> dict:
    window = embed(f"#project={PROJECT_A}&embed=hub&lang={language}",
                   _answering({**_claim(hub_origin=rig.host_origin), "mode": mode}))
    window.frame.evaluate(QUIET)
    facts = window.frame.evaluate(PULT)
    assert window.problems == [] and window.settle() is not None
    return facts


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_framed_desk_whose_claim_says_view_says_the_project_is_not_active(
        embed, rig, language):
    facts = _framed(embed, rig, language, "view")
    assert facts["block"] == [line for line in QUEUES[3]["text"][language]
                              if not line.startswith("1.")]
    assert facts["state"] == "ready" and not RAW.search(facts["text"])


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_framed_desk_whose_claim_says_active_draws_no_queue_block_and_no_view_line(
        embed, rig, language):
    facts = _framed(embed, rig, language, "active")
    assert facts["block"] is None and facts["actor"] == ACTOR[language]["none"]


def test_a_mode_the_claim_does_not_know_is_no_view_and_no_line(embed, rig):
    assert _framed(embed, rig, "en", "paused")["block"] is None


def test_a_plain_desk_with_no_claim_says_nothing_of_a_view(open_desk):
    window = open_desk("#lang=en")
    window.page.wait_for_function(SETTLED)
    assert window.page.evaluate(PULT)["block"] is None
    assert window.page.evaluate(FACTS)["shell"] == "ready"
