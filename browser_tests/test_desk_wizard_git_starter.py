"""The starter's «Создать репозиторий: 2 шага» on the real renderer: one press, two requests.

In «С нуля» a folder that is not under git is made a repository by one press: `init`, then a read
of the project, then the empty first commit. The route is the bench's fake with a memory
(`desk_wizard_git_server.py`). The decisions are `tests/test_desk_wizard_git_chain.py`; here:
what is drawn before and during the press, which requests go out and in which order, and what
the person sees when the first or the second step does not come to a done answer. The rules of
the slice stay: nothing is sent on load, a press that is blocked says why and sends nothing, a
lost answer is read and never repeated or called a cancel, and the second request is never the
result of a second click.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from browser_tests.desk_wizard_bench import bench, desk_url  # noqa: F401
from browser_tests.desk_wizard_git_steps import (
    at_materials, close_door, open_door, reason_beside, write_asks, writes)

LANGS = ("ru", "en")
STARTER = "desk-starter-docs"
#: The message the product gives the empty first commit (`git_setup_first.TITLES["empty"]`).
MESSAGE = "Начало проекта (Conduct)"
BANNED = re.compile(r"cancel|fail|error|abort|отмен|ошибк|не удалось", re.IGNORECASE)
INIT = {"step": "init", "actor": "Anna"}
EMPTY = {"step": "first_commit", "mode": "empty", "paths_digest": None, "actor": "Anna"}


def chain_at(bench, lang, start="git_not_git", **options):
    """The wizard of a starter on step 2 over a folder that is not a repository."""
    return at_materials(bench, lang, start, starter=STARTER, **options)


def row(bench, link):
    return bench.page.locator(f'[data-git-chain-row="{link}"]')


def rows(bench):
    return bench.page.locator("[data-git-chain-row]").evaluate_all(
        "nodes => nodes.map(node => [node.dataset.gitChainRow, node.dataset.gitChainStatus])")


def state_of(bench):
    return bench.page.locator("[data-git-state]").get_attribute("data-git-state")


def assert_close_line(bench, shown, other):
    """The close dialog is open, shows the line `shown` and not the line `other`."""
    dialog = bench.page.locator("[data-close-dialog]")
    expect(dialog).to_have_count(1)
    assert bench.say(shown) in dialog.inner_text()
    assert bench.say(other) not in dialog.inner_text()
    assert bench.page.evaluate("() => window.host.closed") == 0, "asking closes nothing"


@pytest.mark.parametrize("lang", LANGS)
def test_the_starter_shows_both_steps_with_their_effects_and_one_button_and_sends_nothing(
        bench, lang):
    world = chain_at(bench, lang)
    block = bench.page.locator("[data-git-chain]")
    expect(block).to_have_count(1)
    assert bench.page.locator("[data-git-connect]").count() == 0, "the plain connect is gone"
    assert bench.control("wizard:git:connect_git").count() == 0
    for key in ("wizard.first.chain.title", "wizard.first.chain.intro",
                "wizard.first.chain.step_init", "wizard.first.chain.step_commit",
                "wizard.first.connect.effect", "wizard.first.connect.exclude",
                "wizard.first.commit.effect_empty", "wizard.first.chain.message"):
        assert bench.say(key) in block.inner_text(), key
    codes = block.locator("code").evaluate_all("nodes => nodes.map(node => node.textContent)")
    assert codes == ["git init", MESSAGE], "each step shows its command or its fixed message"
    button = bench.control("wizard:git:chain")
    assert button.inner_text() == bench.say("wizard.first.chain.title")
    assert bench.page.locator('[data-git-exit="run_without_git"]').count() == 0
    assert world.posts() == [] and bench.page.locator("[data-git-chain-rows]").count() == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_with_the_confirm_switch_shut_the_chain_waits_beside_its_reason_and_sends_nothing(
        bench, lang):
    world = chain_at(bench, lang)
    close_door(bench)
    button = bench.control("wizard:git:chain")
    assert button.is_disabled()
    assert reason_beside(bench, "wizard:git:chain") == bench.say(
        "wizard.first.why.confirm_door_closed")
    button.click(force=True)
    assert world.posts() == [] and write_asks(bench) == [], "not even the first step goes"


@pytest.mark.parametrize("lang", LANGS)
def test_one_press_posts_init_then_the_empty_confirm_and_shows_the_result_of_each(bench, lang):
    world = chain_at(bench, lang)
    open_door(bench)
    bench.control("wizard:git:chain").click()
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "done")
    assert writes(world) == ["git_init", "git_confirm"]
    assert [post["body"] for post in world.posts()] == [INIT, EMPTY]
    assert rows(bench) == [["init", "done"], ["commit", "done"]]
    assert bench.say("wizard.first.done.init") in row(bench, "init").inner_text()
    assert bench.say("wizard.first.done.confirm", ref="refs/heads/main", commit="5e4d3c2",
                     count="0") in row(bench, "commit").inner_text()
    assert write_asks(bench) == ["write:git:init:1", "write:git:confirm:2"]
    assert [ask[0] for ask in bench.asks()].count("read:git") == 3, "open, between, after"
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "repo")
    expect(bench.control("wizard:next")).to_be_enabled()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_second_request_waits_for_the_read_after_the_first_and_the_wait_is_in_words(
        bench, lang):
    world = chain_at(bench, lang)
    open_door(bench)
    world.hold_read()
    bench.control("wizard:git:chain").click()
    expect(row(bench, "init")).to_have_attribute("data-git-chain-status", "done")
    root = bench.page.locator("[data-git-first]")
    expect(root).to_have_attribute("data-git-phase", "busy")
    assert rows(bench) == [["init", "done"], ["commit", "todo"]]
    assert bench.text("[data-git-busy]") == bench.say("wizard.first.busy.chain_read")
    assert writes(world) == ["git_init"], "the second step is not sent before the read"
    bench.dispatch(type="actor-edit", value="Mallory")
    assert bench.wizard()["launch"]["actor"] == "Anna", "the name is fixed in the wait"
    bench.control("wizard:close").click()
    assert_close_line(bench, "wizard.first.close_chain", "wizard.first.close_busy")
    bench.control("wizard:close:keep").click()
    world.release_read()
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "done")
    assert writes(world) == ["git_init", "git_confirm"]
    assert bench.page.locator("[data-git-first]").get_attribute("data-git-phase") == "idle"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_closing_while_the_first_step_works_says_the_second_step_will_not_be_started(bench, lang):
    world = chain_at(bench, lang, hold=["git_init"])
    open_door(bench)
    bench.control("wizard:git:chain").click()
    expect(row(bench, "init")).to_have_attribute("data-git-chain-status", "working")
    assert writes(world) == [], "the held first request has not reached the route"
    bench.control("wizard:close").click()
    assert_close_line(bench, "wizard.first.close_chain", "wizard.first.close_busy")
    bench.control("wizard:close:keep").click()
    world.release("git_init")
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "done")
    assert writes(world) == ["git_init", "git_confirm"]


@pytest.mark.parametrize("lang", LANGS)
def test_closing_while_the_second_step_works_keeps_the_line_for_a_request_that_is_not_stopped(
        bench, lang):
    world = chain_at(bench, lang, hold=["git_confirm"])
    open_door(bench)
    bench.control("wizard:git:chain").click()
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "working")
    bench.control("wizard:close").click()
    assert_close_line(bench, "wizard.first.close_busy", "wizard.first.close_chain")
    bench.control("wizard:close:keep").click()
    world.release("git_confirm")
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "done")
    assert writes(world) == ["git_init", "git_confirm"]


@pytest.mark.parametrize("lang", LANGS)
def test_a_second_click_and_the_first_commit_button_during_the_second_request_send_nothing(
        bench, lang):
    world = chain_at(bench, lang, hold=["git_confirm"])
    open_door(bench)
    bench.control("wizard:git:chain").click()
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "working")
    assert rows(bench) == [["init", "done"], ["commit", "working"]]
    assert bench.text("[data-git-busy]") == bench.say("wizard.first.busy.confirm")
    assert writes(world) == ["git_init"], "the held request has not reached the route"
    exit_button = bench.control("wizard:git:first_commit")
    assert exit_button.is_disabled()
    assert reason_beside(bench, "wizard:git:first_commit") == bench.say("wizard.first.why.busy")
    for _ in range(3):
        exit_button.click(force=True)
    assert write_asks(bench) == ["write:git:init:1", "write:git:confirm:2"], "one request"
    assert bench.wizard()["git"]["panel"] is None
    world.release("git_confirm")
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "done")
    assert writes(world) == ["git_init", "git_confirm"]


@pytest.mark.parametrize("lang", LANGS)
def test_a_refused_first_step_posts_one_request_and_the_second_is_never_sent(bench, lang):
    world = chain_at(bench, lang)
    open_door(bench)
    world.force("git_init", reason="unsafe_directory")
    bench.control("wizard:git:chain").click()
    refused = row(bench, "init").locator("[data-git-result]")
    expect(refused).to_have_attribute("data-git-notice", "git_setup.reason.unsafe_directory")
    assert rows(bench) == [["init", "refused"], ["commit", "skipped"]]
    assert bench.say("wizard.first.next.unsafe_directory") in row(bench, "init").inner_text()
    assert bench.say("wizard.first.chain.skipped.first_refused") in row(bench,
                                                                         "commit").inner_text()
    assert writes(world) == ["git_init"] and state_of(bench) == "not_git"
    world.unforce("git_init")
    expect(bench.control("wizard:git:chain")).to_be_enabled()
    bench.control("wizard:git:chain").click()
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "done")
    assert writes(world) == ["git_init", "git_init", "git_confirm"]
    assert write_asks(bench) == ["write:git:init:1", "write:git:init:2", "write:git:confirm:3"]


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_first_answer_is_read_and_the_chain_does_not_go_on_by_itself(bench, lang):
    world = chain_at(bench, lang)
    open_door(bench)
    world.lose("git_init")
    bench.control("wizard:git:chain").click()
    expect(row(bench, "init")).to_have_attribute("data-git-chain-status", "lost")
    expect(bench.page.locator("[data-git-verdict]")).to_have_text(
        bench.say("wizard.first.lost.done"))
    assert bench.say("wizard.first.lost.head") in row(bench, "init").inner_text()
    assert rows(bench) == [["init", "lost"], ["commit", "skipped"]]
    assert bench.say("wizard.first.chain.skipped.first_lost") in row(bench,
                                                                      "commit").inner_text()
    assert bench.say("wizard.first.chain.by_hand") in bench.text("[data-git-chain-rows]")
    said = bench.text("[data-git-chain-rows]")
    assert not BANNED.search(said), "an unknown outcome is not called a cancel or a failure"
    assert writes(world) == ["git_init"], "nothing continues by itself"
    assert state_of(bench) == "unborn"
    assert [ask[0] for ask in bench.asks()].count("read:git") == 2
    expect(bench.control("wizard:git:first_commit")).to_be_enabled()


@pytest.mark.parametrize("lang", LANGS)
def test_a_refused_second_step_keeps_the_repository_and_the_first_commit_button_finishes_it(
        bench, lang):
    world = chain_at(bench, lang)
    open_door(bench)
    world.force("git_confirm", reason="git_identity_missing")
    bench.control("wizard:git:chain").click()
    refused = row(bench, "commit").locator("[data-git-result]")
    expect(refused).to_have_attribute("data-git-notice", "git_setup.reason.git_identity_missing")
    assert rows(bench) == [["init", "done"], ["commit", "refused"]]
    text = row(bench, "commit").inner_text()
    assert bench.say("wizard.first.next.git_identity_missing") in text
    assert bench.say("wizard.first.chain.by_hand") in bench.text("[data-git-chain-rows]")
    assert state_of(bench) == "unborn" and writes(world) == ["git_init", "git_confirm"]
    world.unforce("git_confirm")
    bench.control("wizard:git:first_commit").click()
    assert bench.page.locator("[data-git-chain-rows]").count() == 0, "the panel takes over"
    assert bench.text("[data-git-mode]") == bench.say("wizard.first.mode.starter")
    bench.control("wizard:git:preview").click()
    expect(bench.page.locator('[data-git-preview="empty"]')).to_have_count(1)
    bench.control("wizard:git:confirm").click()
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "repo")
    assert writes(world) == ["git_init", "git_confirm", "git_preview", "git_confirm"]
    assert world.posts()[3]["body"] == EMPTY


@pytest.mark.parametrize("lang", LANGS)
def test_a_project_whose_git_signs_ends_the_chain_in_the_wait_for_a_signature(bench, lang):
    world = chain_at(bench, lang, signing=True)
    open_door(bench)
    bench.control("wizard:git:chain").click()
    waiting = bench.page.locator('[data-git-pending="awaiting_signature"]')
    expect(waiting).to_have_count(1)
    assert rows(bench) == [["init", "done"], ["commit", "refused"]]
    refused = row(bench, "commit").locator("[data-git-result]")
    assert refused.get_attribute("data-git-notice") == "git_setup.reason.signing_required"
    assert bench.page.locator("[data-git-command]").count() == 2, "the two commands are shown"
    assert bench.say("wizard.first.chain.by_hand") not in bench.text("[data-git-chain-rows]")
    assert writes(world) == ["git_init", "git_confirm"]


@pytest.mark.parametrize("lang", LANGS)
def test_in_view_the_chain_is_drawn_disabled_beside_the_project_not_being_active(bench, lang):
    world = chain_at(bench, lang, "git_not_active", view=True)
    open_door(bench)
    expect(bench.page.locator("[data-git-chain]")).to_have_count(1)
    button = bench.control("wizard:git:chain")
    assert button.is_disabled()
    assert reason_beside(bench, "wizard:git:chain") == bench.say(
        "wizard.first.why.project_not_active")
    button.click(force=True)
    assert world.posts() == [] and write_asks(bench) == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_desk_without_a_door_for_the_git_steps_draws_the_chain_disabled_and_sends_nothing(
        bench, lang):
    world = chain_at(bench, lang, setup_door=False)
    open_door(bench)
    button = bench.control("wizard:git:chain")
    assert button.is_disabled()
    assert reason_beside(bench, "wizard:git:chain") == bench.say("wizard.first.why.door_missing")
    button.click(force=True)
    assert world.posts() == [] and write_asks(bench) == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_chain_needs_a_valid_name_which_is_typed_where_the_press_is(bench, lang):
    world = chain_at(bench, lang, actor="")
    open_door(bench)
    button = bench.control("wizard:git:chain")
    assert button.is_disabled()
    assert reason_beside(bench, "wizard:git:chain") == bench.say("wizard.first.why.actor_invalid")
    button.click(force=True)
    assert world.posts() == []
    bench.type_into("wizard:git:actor", "Anna")
    expect(bench.control("wizard:git:chain")).to_be_enabled()
    bench.control("wizard:git:chain").click()
    expect(row(bench, "commit")).to_have_attribute("data-git-chain-status", "done")
    assert [post["body"]["actor"] for post in world.posts()] == ["Anna", "Anna"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_chain_is_not_offered_to_a_normal_task_and_the_old_connect_stays_there(bench, lang):
    world = at_materials(bench, lang, "git_not_git")
    expect(bench.page.locator("[data-git-connect]")).to_have_count(1)
    assert bench.page.locator("[data-git-chain]").count() == 0
    assert bench.control("wizard:git:chain").count() == 0
    assert world.posts() == []
