"""The wizard's step 2 ("Материалы") on the real renderer, in Russian and in English.

The answers are the stand-in reads under `tests/fixtures/wizard/`, handed to the bench host as the
table it answers each ask from. What the model decides is in `tests/test_desk_wizard_materials.py`;
what is drawn from it, and what a press does, is here.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from browser_tests.desk_wizard_bench import bench, desk_url  # noqa: F401
from tests.desk_wizard_node import fixture

LANGS = ("ru", "en")
GIT_STATES = ("repo", "unborn", "not_git", "not_repo_root", "unsupported", "unsafe_directory",
              "unavailable", "not_active")
GIT = {name: fixture("wizard", f"git_{name}.json") for name in GIT_STATES}
DOCS = fixture("wizard", "documents.json")
DOC = fixture("wizard", "document.json")
SPEC_DOC = "d-1f0a9c3e5b7d2468a1f0a9c3e5b7d246"


def ok(payload):
    return {"status": "accepted", "payload": payload}


def answers(git="repo", **more):
    """The table the host answers the opening asks from; `git` names a fixture state."""
    return {"git": {"*": ok(GIT[git])}, "documents": {"*": ok(DOCS)},
            "document": {"*": ok(DOC)}, **more}


def to_materials(bench, lang, *, git="repo", starter=None, view=False, auto=None):
    """Open the wizard, fill step 1 and step on to step 2."""
    bench.open(lang, starter=starter, view=view, auto=auto or answers(git))
    bench.type_into("wizard:title", "Fix login")
    bench.type_into("wizard:idea" if starter else "wizard:brief", "Make it work.")
    bench.control("wizard:next").click()
    expect(bench.root()).to_have_attribute("data-wizard-current", "materials")


def on(bench, key):
    """Whether a choice drawn as a radio or a switch is on (`aria-checked`)."""
    return bench.control(key).get_attribute("aria-checked") == "true"


def body(bench):
    """The wizard's own materials as the model would send them."""
    return bench.page.evaluate(
        "lang => window.host.wiz.materialsBody(window.host.state.wizard, lang)", "en")


@pytest.mark.parametrize("lang", LANGS)
def test_a_project_document_is_a_link_by_default_and_a_copy_fills_the_field(bench, lang):
    to_materials(bench, lang)
    bench.control("wizard:add:project_doc").click()
    rows = bench.page.locator("[data-picker-doc]")
    expect(rows).to_have_count(3)
    assert rows.locator("code").all_inner_texts() == ["docs/spec.md", "README.md",
                                                       "notes/todo.txt"]
    bench.control(f"wizard:picker:take:{SPEC_DOC}").click()
    card = bench.page.locator('[data-card="m1"]')
    expect(card).to_have_count(1)
    assert bench.page.locator("[data-picker]").count() == 0, "adding a document closes the list"
    assert on(bench, "wizard:card:m1:mode:link")
    assert card.locator("textarea").count() == 0, "a link carries no text"
    assert body(bench)["items"][0] == {"kind": "project_doc", "doc_id": SPEC_DOC,
                                       "git_oid": "1" * 40, "mode": "link"}
    bench.control("wizard:card:m1:mode:copy").click()
    field = bench.control("wizard:card:m1:content")
    expect(field).to_have_value(DOC["content"])
    assert body(bench)["items"][0]["content"] == DOC["content"]
    assert ["document", SPEC_DOC] in [row[1:] for row in bench.asks()]
    bench.control("wizard:card:m1:mode:link").click()
    assert card.locator("textarea").count() == 0
    assert "content" not in body(bench)["items"][0]
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_thirteenth_material_is_refused_with_a_reason_and_the_counter_says_approximately(
        bench, lang):
    to_materials(bench, lang)
    for _ in range(12):
        bench.control("wizard:add:note").click()
    expect(bench.page.locator("[data-card]")).to_have_count(12)
    counter = bench.page.locator("[data-materials-counter]")
    assert "≈" in counter.inner_text() and "12" in counter.inner_text()
    assert bench.page.locator("[data-refusal]").count() == 0
    bench.control("wizard:add:note").click()
    refusal = bench.page.locator('[data-refusal="too_many_materials"]')
    expect(refusal).to_have_text(bench.say("wizard.refusal.too_many_materials"))
    assert bench.page.locator("[data-card]").count() == 12
    assert bench.control("wizard:next").is_disabled() is True, "twelve empty cards are not finished"
    bench.control("wizard:card:m1:remove").click()
    expect(bench.page.locator("[data-card]")).to_have_count(11)
    assert bench.page.locator("[data-refusal]").count() == 0


@pytest.mark.parametrize("lang", LANGS)
def test_the_over_limit_hint_offers_to_make_the_document_a_link(bench, lang):
    huge = {**DOC, "content": "я" * 30000}
    to_materials(bench, lang, auto=answers(document={"*": ok(huge)}))
    bench.control("wizard:add:project_doc").click()
    bench.control(f"wizard:picker:take:{SPEC_DOC}").click()
    bench.control("wizard:card:m1:mode:copy").click()
    hint = bench.page.locator('[data-hint="make_link"]')
    expect(hint).to_have_text(bench.say("wizard.materials.make_link"))
    assert bench.control("wizard:next").is_disabled()
    assert bench.page.locator("[data-wizard-reason]").inner_text() == bench.say(
        "wizard.reason.materials_over_bytes")
    bench.control("wizard:card:m1:to-link").click()
    expect(hint).to_have_count(0)
    assert on(bench, "wizard:card:m1:mode:link")
    assert bench.control("wizard:next").is_enabled()


@pytest.mark.parametrize("lang", LANGS)
def test_closing_the_wizard_with_materials_warns_they_are_not_saved_and_keeping_them_closes_nothing(
        bench, lang):
    to_materials(bench, lang)
    bench.control("wizard:close").click()
    assert bench.call("snapshot")["closing"] is None
    assert bench.page.evaluate("() => window.host.closed") == 1, "no cards: nothing to lose"
    bench.control("wizard:add:note").click()
    bench.control("wizard:card:m1:title").fill("Idea")
    bench.control("wizard:close").click()
    dialog = bench.page.locator("[data-close-dialog]")
    expect(dialog).to_have_count(1)
    assert bench.say("wizard.close.warning") in dialog.inner_text()
    assert ("материалы не сохранены" if lang == "ru" else "materials not saved") in \
        dialog.inner_text()
    assert bench.page.evaluate("() => window.host.closed") == 1, "asking closes nothing"
    bench.control("wizard:close:keep").click()
    expect(dialog).to_have_count(0)
    assert bench.page.evaluate("() => window.host.closed") == 1
    assert bench.control("wizard:card:m1:title").input_value() == "Idea"
    bench.control("wizard:close").click()
    bench.control("wizard:close:discard").click()
    assert bench.page.evaluate("() => window.host.closed") == 2
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_project_instructions_row_and_switch_appear_only_when_files_were_found(bench, lang):
    to_materials(bench, lang)
    row = bench.page.locator("[data-instructions]")
    expect(row).to_have_count(1)
    assert bench.say("wizard.instr.row", count="4") in row.inner_text()
    assert bench.say("wizard.instr.switch") in row.inner_text()
    assert not on(bench, "wizard:include-instructions"), "it defaults to the last seed's choice"
    bench.control("wizard:include-instructions").click()
    assert bench.wizard()["materials"]["includeInstructions"] is True
    assert on(bench, "wizard:include-instructions")
    assert bench.control("wizard:instructions-info").count() == 1
    for state in ("unborn", "not_git", "not_active"):
        to_materials(bench, lang, git=state)
        assert bench.page.locator("[data-instructions]").count() == 0, state


@pytest.mark.parametrize("lang", LANGS)
def test_starter_mode_without_git_stops_at_the_materials_step(bench, lang):
    to_materials(bench, lang, git="not_git", starter="desk-starter-docs")
    exits = bench.page.locator("[data-git-exit]")
    assert exits.evaluate_all("nodes => nodes.map(node => node.dataset.gitExit)") == [
        "connect_git"], "only the one exit that can help"
    assert bench.control("wizard:next").is_disabled()
    assert bench.page.locator("[data-wizard-reason]").inner_text() == bench.say(
        "wizard.reason.starter_needs_git")
    cycle = bench.page.locator('[data-wizard-step="cycle"]')
    assert cycle.get_attribute("data-status") == "blocked"


@pytest.mark.parametrize("lang", LANGS)
def test_in_view_mode_the_git_step_says_not_active_and_there_is_no_project_document_button(
        bench, lang):
    to_materials(bench, lang, git="not_active", view=True)
    assert bench.root().get_attribute("data-mode") == "view"
    sentence = bench.page.locator('[data-git-state="not_active"] p').first
    assert sentence.inner_text() == bench.say("wizard.git.not_active")
    assert bench.control("wizard:add:project_doc").count() == 0
    for kind in ("plan", "ideas", "note", "scheme"):
        assert bench.control(f"wizard:add:{kind}").count() == 1, kind
    why = bench.page.locator('[data-blocked="wizard:git:connect_git"] small')
    assert why.inner_text() == bench.say("wizard.later.connect_git_view")
    assert [row for row in bench.asks() if row[1] in ("documents", "document")] == []


@pytest.mark.parametrize("lang", LANGS)
def test_in_view_mode_git_is_unread_until_the_answer_lands_and_only_then_not_active(bench, lang):
    unanswered = {name: table for name, table in answers().items() if name != "git"}
    to_materials(bench, lang, view=True, auto=unanswered)
    panel = bench.page.locator("[data-git-state]")
    assert panel.get_attribute("data-git-state") == "reading"
    assert panel.locator("p").first.inner_text() == bench.say("wizard.git.reading")
    assert bench.control("wizard:next").is_disabled()
    assert bench.text("[data-wizard-reason]") == bench.say("wizard.reason.git_reading")
    bench.answer("git", GIT["not_active"])
    expect(panel).to_have_attribute("data-git-state", "not_active")
    assert panel.locator("p").first.inner_text() == bench.say("wizard.git.not_active")
    expect(bench.control("wizard:next")).to_be_enabled()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_git_exits_keep_later_buttons_disabled_and_enable_explicit_no_git_choice(bench, lang):
    for state, ids in (("not_git", ["connect_git"]),
                       ("unborn", ["first_commit"])):
        to_materials(bench, lang, git=state)
        for control in ids:
            button = bench.control(f"wizard:git:{control}")
            assert button.is_disabled(), control
            why = bench.page.locator(f'[data-blocked="wizard:git:{control}"] small')
            assert why.inner_text() == bench.say(f"wizard.later.{control}")
            before = bench.wizard()
            button.click(force=True)
            assert bench.wizard() == before, "a disabled control is not a silent no-op"
    to_materials(bench, lang, git="not_git")
    without_git = bench.control("wizard:git:run_without_git")
    expect(without_git).to_be_enabled()
    assert not on(bench, "wizard:git:run_without_git")
    without_git.click()
    assert on(bench, "wizard:git:run_without_git")
    assert bench.wizard()["materials"]["withoutGit"] is True
    starter = bench.control("wizard:add:starter_docs")
    assert starter.is_disabled()
    assert bench.page.locator('[data-blocked="wizard:add:starter_docs"] small').inner_text() == \
        bench.say("wizard.later.from_starter_docs")


@pytest.mark.parametrize("lang", LANGS)
def test_each_git_state_is_said_with_its_own_sentence_and_exits_and_never_a_path(bench, lang):
    expected = {"repo": ("wizard.git.repo", []), "unborn": ("wizard.git.unborn", ["first_commit"]),
                "not_git": ("wizard.git.not_git", ["connect_git", "run_without_git"]),
                "not_repo_root": ("wizard.git.not_repo_root", []),
                "unsupported": ("wizard.git.unsupported", []),
                "unsafe_directory": ("wizard.git.unsafe_directory", []),
                "unavailable": ("wizard.git.unavailable", []),
                "not_active": ("wizard.git.not_active", ["connect_git"])}
    for state, (key, exits) in expected.items():
        to_materials(bench, lang, git=state)
        panel = bench.page.locator(f'[data-git-state="{state}"]')
        expect(panel).to_have_count(1)
        params = {"repo": {"ref": "main", "commit": "abc1234"},
                  "unsupported": {"names": "work"}}.get(state, {})
        assert bench.say(key, **params) in panel.inner_text(), state
        assert panel.locator("[data-git-exit]").evaluate_all(
            "nodes => nodes.map(node => node.dataset.gitExit)") == exits, state
        assert not re.search(r"[A-Za-z]:\\|/Users/|/home/", bench.root().inner_text()), state


@pytest.mark.parametrize("lang", LANGS)
def test_a_dirty_repository_says_how_many_files_never_reach_the_agents(bench, lang):
    to_materials(bench, lang)
    dirty = bench.page.locator("[data-git-dirty]")
    assert dirty.inner_text() == bench.say("wizard.git.dirty", count="3")


@pytest.mark.parametrize("lang", LANGS)
def test_an_unsafe_folder_shows_the_terminal_command_as_text_and_runs_nothing(bench, lang):
    to_materials(bench, lang, git="unsafe_directory")
    command = bench.page.locator('[data-git-command="safe_directory"]')
    text = command.inner_text()
    assert 'safe.directory "$(pwd)"' in text and "(Get-Location).Path" in text
    assert [row for row in bench.requests if row[0] != "GET"] == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_document_picker_says_when_it_could_not_read_and_reads_again_and_closes(bench, lang):
    refused = {"status": "refused", "code": "store_error", "payload": None}
    to_materials(bench, lang, auto=answers(documents={"*": refused}))
    bench.control("wizard:add:project_doc").click()
    expect(bench.page.locator("[data-picker-failed]")).to_have_text(
        bench.say("wizard.picker.failed"))
    bench.control("wizard:picker:reread").click()
    assert [row[0] for row in bench.asks()].count("read:documents") == 2
    bench.control("wizard:picker:close").click()
    expect(bench.page.locator("[data-picker]")).to_have_count(0)
    assert bench.wizard()["materials"]["items"] == []
