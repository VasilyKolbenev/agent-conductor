"""An unfinished first commit, a wait for a signature, a request that works, an answer that is lost.

Everything here is something the person could not have caused by a second click: a reload that
finds an operation the product stored, two commands to run in their own terminal, a request that
takes a while, and an answer that never comes. The rules are `L-to-D2-first-commit-contract.md`
sections 5 and 6: one press is one request, a lost answer is not a cancel, the continue is
explicit, nothing is sent on load, and every text the person or a foreign file chose is text.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from browser_tests.desk_wizard_bench import bench, desk_url  # noqa: F401
from browser_tests.desk_wizard_git_steps import (
    at_materials, close_door, open_door, reason_beside, result, to_preview, write_asks, writes)

LANGS = ("ru", "en")
BANNED = re.compile(r"cancel|fail|error|abort|отмен|ошибк|не удалось", re.IGNORECASE)
STORED = "sha256:9f2c1ad04b7e5d36c8a1f0e24b95d7c3a6e8b10f4d2c97a5e3b6180d4f7a29c1"


def pending_of(bench):
    return bench.page.locator("[data-git-pending]")


def terms(bench):
    return bench.page.locator("[data-git-term]").evaluate_all(
        "nodes => Object.fromEntries(nodes.map(node => [node.dataset.gitTerm, node.textContent]))")


def commands(bench):
    return bench.page.evaluate("""() => Object.fromEntries([...document.querySelectorAll(
      '[data-git-command]')].map((node) => [node.dataset.gitCommand, node.value]))""")


@pytest.mark.parametrize("lang", LANGS)
def test_a_request_that_works_is_a_wait_without_a_percentage_and_a_second_press_sends_nothing(
        bench, lang):
    world = at_materials(bench, lang, hold=["git_confirm"])
    open_door(bench)
    to_preview(bench)
    confirm = bench.control("wizard:git:confirm")
    confirm.click()
    root = bench.page.locator("[data-git-first]")
    expect(root).to_have_attribute("data-git-phase", "busy")
    assert root.get_attribute("aria-busy") == "true"
    words = bench.say("wizard.first.busy.confirm")
    assert bench.text("[data-git-busy]") == words and "%" not in words
    assert bench.page.locator("progress, [role='progressbar']").count() == 0
    assert bench.control("wizard:git:confirm").is_disabled()
    assert reason_beside(bench, "wizard:git:confirm") == bench.say("wizard.first.why.busy")
    for _ in range(3):
        bench.control("wizard:git:confirm").click(force=True)
        bench.control("wizard:git:preview").click(force=True)
    assert write_asks(bench) == ["write:git:preview:1", "write:git:confirm:2"], "one request"
    assert writes(world) == ["git_preview"], "the held request has not reached the route"
    bench.control("wizard:close").click()
    dialog = bench.page.locator("[data-close-dialog]")
    expect(dialog).to_have_count(1)
    assert bench.say("wizard.first.close_busy") in dialog.inner_text()
    assert bench.page.evaluate("() => window.host.closed") == 0, "asking closes nothing"
    bench.control("wizard:close:keep").click()
    world.release("git_confirm")
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert writes(world) == ["git_preview", "git_confirm"]
    assert bench.page.locator("[data-git-first]").get_attribute("data-git-phase") == "idle"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_answer_after_the_write_landed_is_unknown_then_read_as_done_and_not_resent(
        bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    world.lose("git_confirm")
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-result", "lost")
    text = result(bench).inner_text()
    assert bench.say("wizard.first.lost.head") in text
    expect(bench.page.locator("[data-git-verdict]")).to_have_text(
        bench.say("wizard.first.lost.done"))
    assert not BANNED.search(result(bench).inner_text()), "an unknown outcome is not a verdict"
    assert [row[0] for row in bench.asks()].count("read:git") == 2, "the read was asked again"
    assert writes(world) == ["git_preview", "git_confirm"], "the body is never resent"
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "repo")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_answer_before_the_write_landed_keeps_the_preview_for_the_same_confirm_on_purpose(
        bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    shown = bench.page.evaluate("() => window.host.state.wizard.git.preview.paths_digest")
    world.lose("git_confirm", landed=False)
    bench.control("wizard:git:confirm").click()
    expect(bench.page.locator("[data-git-verdict]")).to_have_text(
        bench.say("wizard.first.lost.none"))
    assert writes(world) == ["git_preview", "git_confirm"]
    expect(bench.page.locator("[data-git-preview]")).to_have_count(1)
    expect(bench.control("wizard:git:confirm")).to_be_enabled()
    assert [row for row in bench.asks() if "preview" in row[0]] == [
        ["write:git:preview:1", "git_preview", None]], "no new preview was asked for"
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    bodies = [post["body"] for post in world.posts() if post["name"] == "git_confirm"]
    assert len(bodies) == 2 and bodies[0] == bodies[1] and bodies[0]["paths_digest"] == shown


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_answer_that_left_an_unfinished_operation_shows_the_continue_and_does_not_make_it(
        bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    world.set(crash_after_ref=True)
    bench.control("wizard:git:confirm").click()
    expect(bench.page.locator("[data-git-verdict]")).to_have_text(
        bench.say("wizard.first.lost.pending"))
    expect(pending_of(bench)).to_have_attribute("data-git-pending", "unfinished")
    expect(bench.control("wizard:git:continue")).to_be_enabled()
    assert writes(world) == ["git_preview", "git_confirm"], "nothing continues by itself"
    assert bench.control("wizard:next").is_disabled()
    assert bench.text("[data-wizard-reason]") == bench.say("wizard.reason.git_unfinished")
    assert not BANNED.search(result(bench).inner_text())


@pytest.mark.parametrize("lang", LANGS)
def test_the_unfinished_panel_shows_the_stored_terms_and_a_page_that_opens_on_it_sends_nothing(
        bench, lang):
    world = at_materials(bench, lang, "git_pending_unfinished")
    panel = pending_of(bench)
    expect(panel).to_have_attribute("data-git-pending", "unfinished")
    assert bench.say("wizard.first.pending.unfinished") in panel.inner_text()
    assert terms(bench) == {
        "mode": bench.say("wizard.first.mode.snapshot"),
        "files": bench.say("wizard.first.preview.files", count="2"),
        "branch": bench.say("wizard.first.preview.branch", ref="refs/heads/main"),
        "author": bench.say("wizard.first.preview.author", name="First Author",
                            email="first@example.invalid"),
        "by": bench.say("wizard.first.pending.by", name="Owner")}
    assert bench.page.locator("[data-git-exit]").count() == 0, "no new first commit is offered"
    assert bench.text(".desk-wizard__git-sentence") == bench.say(
        "wizard.git.repo_pending", ref="main", commit="abc1234")
    assert write_asks(bench) == [] and world.posts() == [], "nothing is sent on load"
    assert bench.control("wizard:next").is_disabled()
    assert bench.text("[data-wizard-reason]") == bench.say("wizard.reason.git_unfinished")


@pytest.mark.parametrize("lang", LANGS)
def test_the_continue_posts_the_stored_mode_and_digest_and_the_name_of_now_not_the_confirmers(
        bench, lang):
    world = at_materials(bench, lang, "git_pending_unfinished", actor="Anna")
    open_door(bench)
    bench.control("wizard:git:continue").click()
    expect(result(bench)).to_have_attribute("data-git-notice",
                                            "git_setup.reason.setup_terms_changed")
    assert world.posts() == [{"name": "git_confirm", "body": {
        "step": "first_commit", "mode": "snapshot", "paths_digest": STORED, "actor": "Anna"}}]
    assert "git_preview" not in writes(world), "a continue never asks for a new preview"
    expect(pending_of(bench)).to_have_attribute("data-git-pending", "unfinished")
    assert bench.say("wizard.first.next.setup_terms_changed") in result(bench).inner_text()
    bench.control("wizard:git:actor").fill("Owner")
    expect(bench.control("wizard:git:continue")).to_be_enabled()
    bench.control("wizard:git:continue").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert world.posts()[1]["body"]["actor"] == "Owner"
    assert pending_of(bench).count() == 0
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "repo")


@pytest.mark.parametrize("lang", LANGS)
def test_an_unfinished_empty_first_commit_is_continued_with_a_null_digest(bench, lang):
    world = at_materials(bench, lang, "git_pending_empty")
    open_door(bench)
    bench.control("wizard:git:continue").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert world.posts()[0]["body"] == {"step": "first_commit", "mode": "empty",
                                        "paths_digest": None, "actor": "Anna"}


@pytest.mark.parametrize("lang", LANGS)
def test_with_the_door_closed_the_continue_is_disabled_beside_its_reason(bench, lang):
    world = at_materials(bench, lang, "git_pending_unfinished")
    close_door(bench)
    assert bench.control("wizard:git:continue").is_disabled()
    assert reason_beside(bench, "wizard:git:continue") == bench.say(
        "wizard.first.why.confirm_door_closed")
    bench.control("wizard:git:continue").click(force=True)
    assert world.posts() == []


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("start, zeros", (("git_pending_signature", 40),
                                          ("git_pending_signature_sha256", 64)))
def test_the_wait_for_a_signature_shows_the_two_commands_exactly_and_check_again_posts_the_body(
        bench, lang, start, zeros):
    world = at_materials(bench, lang, start, signing=True)
    open_door(bench)
    panel = pending_of(bench)
    expect(panel).to_have_attribute("data-git-pending", "awaiting_signature")
    pending = bench.page.evaluate(
        "() => window.host.world.git.first_commit_pending.signing")
    path = "conductor.v3/git/msg-first-0123456789abcdef0123456789abcdef.txt"
    assert commands(bench) == {
        "commit": f"git commit-tree {pending['tree']} -S -F {path}",
        "update": f"git update-ref refs/heads/main <oid> {'0' * zeros}"}
    assert bench.say("wizard.first.sign.oid") == bench.text("[data-git-oid-hint]")
    assert bench.say("wizard.first.sign.level") in panel.inner_text()
    assert bench.control("wizard:git:continue").inner_text() == bench.say(
        "wizard.first.check_again")
    assert write_asks(bench) == [] and world.posts() == []
    bench.control("wizard:git:continue").click()
    expect(result(bench)).to_have_attribute("data-git-notice",
                                            "git_setup.reason.signing_required")
    assert world.posts()[0]["body"]["paths_digest"] == STORED
    assert commands(bench)["update"].endswith("0" * zeros), "the commands stay"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_after_the_owner_made_the_commit_check_again_finishes_and_says_present_not_verified(
        bench, lang):
    world = at_materials(bench, lang, "git_pending_signature", signing=True)
    open_door(bench)
    world.set(owner_commit=True)
    bench.control("wizard:git:continue").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    text = result(bench).inner_text()
    assert bench.say("wizard.first.done.signature_present") in text
    assert not re.search(r"\bvalid\b|действительн", text, re.IGNORECASE), "presence is not validity"
    assert pending_of(bench).count() == 0
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "repo")


@pytest.mark.parametrize("lang", LANGS)
def test_an_unsigned_commit_on_the_branch_keeps_the_wait_and_the_notice_offers_no_deletion(
        bench, lang):
    world = at_materials(bench, lang, "git_pending_signature", signing=True)
    open_door(bench)
    world.force("git_confirm", reason="head_exists")
    bench.control("wizard:git:continue").click()
    expect(result(bench)).to_have_attribute("data-git-notice", "git_setup.reason.head_exists")
    text = result(bench).inner_text()
    assert bench.say("wizard.first.next.head_exists") in text
    assert not re.search(r"delete|удали(?:те|ть)", text, re.IGNORECASE)
    expect(pending_of(bench)).to_have_attribute("data-git-pending", "awaiting_signature")
    expect(bench.control("wizard:git:continue")).to_be_enabled()
    assert len(commands(bench)) == 2


@pytest.mark.parametrize("lang", LANGS)
def test_a_branch_the_owner_retargeted_replaces_the_commands_and_the_old_ones_are_not_kept(
        bench, lang):
    world = at_materials(bench, lang, "git_pending_signature", signing=True)
    open_door(bench)
    moved = bench.page.evaluate("""() => {
      const git = structuredClone(window.host.world.git);
      git.first_commit_pending.signing.target_ref = "refs/heads/trunk";
      git.first_commit_pending.terms.target_ref = "refs/heads/trunk";
      return git;
    }""")
    world.swap(moved)
    assert "refs/heads/main" in commands(bench)["update"], "the page still shows what it read"
    bench.control("wizard:git:continue").click()
    expect(bench.page.locator('[data-git-command="update"]')).to_have_value(
        re.compile(r"update-ref refs/heads/trunk "))
    assert "refs/heads/main" not in commands(bench)["update"]


@pytest.mark.parametrize("lang", LANGS)
def test_damaged_offers_no_continue_says_so_and_does_not_hold_next(bench, lang):
    world = at_materials(bench, lang, "git_pending_damaged")
    open_door(bench)
    panel = pending_of(bench)
    expect(panel).to_have_attribute("data-git-pending", "damaged")
    assert bench.say("git_setup.reason.setup_damaged") in panel.inner_text()
    assert bench.say("wizard.first.pending.damaged") in panel.inner_text()
    assert bench.control("wizard:git:continue").count() == 0
    assert bench.text(".desk-wizard__git-sentence") == bench.say(
        "wizard.git.repo_damaged", ref="main", commit="abc1234")
    expect(bench.control("wizard:next")).to_be_enabled()
    assert world.posts() == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_text_a_person_or_a_foreign_file_chose_stays_text_in_the_stored_terms(bench, lang):
    world = at_materials(bench, lang, "git_pending_unfinished")
    marked = bench.page.evaluate("""() => {
      const git = structuredClone(window.host.world.git);
      const terms = git.first_commit_pending.terms;
      terms.requested_by = "<b>Eve</b>";
      terms.author = {name: "<img src=x onerror=alert(1)>", email: "e@<u>x</u>"};
      terms.target_ref = "refs/heads/<i>y</i>";
      return git;
    }""")
    world.swap(marked)
    bench.dispatch(type="reread", name="git")
    expect(bench.page.locator('[data-git-term="by"]')).to_contain_text("<b>Eve</b>")
    panel = pending_of(bench)
    assert panel.locator("b, img, i, u").count() == 0, "no element was made from a text"
    assert "<img src=x onerror=alert(1)>" in bench.text('[data-git-term="author"]')
    assert "refs/heads/<i>y</i>" in bench.text('[data-git-term="branch"]')
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_at_375_pixels_the_commands_of_a_long_branch_and_a_sha256_tree_wrap_inside_the_page(
        bench, lang):
    world = at_materials(bench, lang, "git_pending_signature_sha256", signing=True)
    long_ref = "refs/heads/" + "a" * 229
    wide = bench.page.evaluate("""(ref) => {
      const git = structuredClone(window.host.world.git);
      git.first_commit_pending.signing.target_ref = ref;
      git.first_commit_pending.terms.target_ref = ref;
      return git;
    }""", long_ref)
    world.swap(wide)
    bench.dispatch(type="reread", name="git")
    expect(bench.page.locator('[data-git-command="update"]')).to_have_value(
        re.compile(re.escape(long_ref)))
    bench.page.set_viewport_size({"width": 375, "height": 812})
    fits = bench.page.evaluate("""() => ({
      page: document.documentElement.scrollWidth <= window.innerWidth,
      areas: [...document.querySelectorAll('[data-git-command]')].every(
        (node) => node.clientWidth > 0 && node.scrollWidth <= node.clientWidth + 1)})""")
    assert fits == {"page": True, "areas": True}, "the commands wrap, they do not widen the page"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_first_commit_exit_is_not_offered_while_an_operation_is_pending_even_if_unborn(
        bench, lang):
    at_materials(bench, lang, "git_pending_unfinished_unborn")
    assert bench.page.locator('[data-git-exit="first_commit"]').count() == 0
    assert bench.text(".desk-wizard__git-sentence") == bench.say("wizard.git.unborn")
    expect(pending_of(bench)).to_have_attribute("data-git-pending", "unfinished")
