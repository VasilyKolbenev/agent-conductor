"""The git block of step 2 on the real renderer: connecting, the preview, the confirm, the words.

The route is the bench's fake with a memory (`desk_wizard_git_server.py`), so a press changes what
the next read says. The model's decisions are `tests/test_desk_wizard_git_run.py`; the contract of
the route is `tests/test_desk_wizard_git_contract.py`; the real server over real Git is
`test_desk_wizard_git_fresh.py`. Here: what is drawn from the answers, what a press posts, and what
is NOT sent while a control says why it cannot be pressed.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from browser_tests.desk_wizard_bench import bench, desk_url  # noqa: F401
from browser_tests.desk_wizard_git_steps import (
    at_materials, close_door, open_door, patch_preview, reason_beside, result, to_preview,
    write_asks, writes)
from conductor.command.api_refusals import GIT_SETUP_REASONS

LANGS = ("ru", "en")
OTHER_CODES = ("project_not_active", "contract_invalid", "windows_path_too_long",
               "tool_unavailable")
ROW = {"length": 1, "sha256": "sha256:" + "1a" * 32, "git_oid": "1f" * 20, "git_mode": "100644"}
#: What only a wait for a signature may say: there are two commands and a second check.
WAIT_WORDS = re.compile(r"two commands|check again|двумя командами|проверьте снова", re.IGNORECASE)


@pytest.mark.parametrize("lang", LANGS)
def test_not_git_offers_connecting_with_its_effect_and_command_and_posts_the_init_body(bench, lang):
    world = at_materials(bench, lang, "git_not_git")
    block = bench.page.locator("[data-git-connect]")
    expect(block).to_have_count(1)
    assert bench.say("wizard.first.connect.effect") in block.inner_text()
    assert bench.say("wizard.first.connect.exclude") in block.inner_text()
    assert block.locator("code").inner_text() == "git init"
    button = bench.control("wizard:git:connect_git")
    expect(button).to_be_enabled()
    assert world.posts() == [], "nothing is sent on load"
    button.click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert world.posts() == [{"name": "git_init", "body": {"step": "init", "actor": "Anna"}}]
    assert result(bench).inner_text() == bench.say("wizard.first.done.init")
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "unborn")
    expect(bench.control("wizard:git:first_commit")).to_be_enabled()
    assert [row[0] for row in bench.asks()].count("read:git") == 2, "the read is asked once more"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_in_view_connecting_git_is_disabled_with_its_reason_and_sends_nothing(bench, lang):
    world = at_materials(bench, lang, "git_not_git", view=True)
    button = bench.control("wizard:git:connect_git")
    assert button.is_disabled()
    assert reason_beside(bench, "wizard:git:connect_git") == bench.say(
        "wizard.later.connect_git_view")
    button.click(force=True)
    assert world.posts() == [] and bench.page.locator("[data-git-connect]").count() == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_desk_without_a_door_for_the_git_steps_disables_them_and_sends_nothing(bench, lang):
    world = at_materials(bench, lang, "git_not_git", setup_door=False)
    connect = bench.control("wizard:git:connect_git")
    assert connect.is_disabled()
    assert reason_beside(bench, "wizard:git:connect_git") == bench.say(
        "wizard.first.why.door_missing")
    connect.click(force=True)
    world = at_materials(bench, lang, "git_unborn", setup_door=False)
    bench.control("wizard:git:first_commit").click()
    assert bench.control("wizard:git:preview").is_disabled(), "opening the panel sent nothing"
    assert reason_beside(bench, "wizard:git:preview") == bench.say(
        "wizard.first.why.door_missing")
    bench.control("wizard:git:preview").click(force=True)
    assert world.posts() == [] and write_asks(bench) == []
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_press_needs_a_valid_name_which_is_typed_where_the_press_is(bench, lang):
    world = at_materials(bench, lang, "git_not_git", actor="")
    button = bench.control("wizard:git:connect_git")
    assert button.is_disabled()
    assert reason_beside(bench, "wizard:git:connect_git") == bench.say(
        "wizard.first.why.actor_invalid")
    button.click(force=True)
    assert world.posts() == []
    bench.type_into("wizard:git:actor", "Anna")
    expect(bench.control("wizard:git:connect_git")).to_be_enabled()
    assert bench.wizard()["launch"]["actor"] == "Anna"
    bench.control("wizard:git:connect_git").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert world.posts()[0]["body"]["actor"] == "Anna"


@pytest.mark.parametrize("lang", LANGS)
def test_the_preview_shows_branch_author_files_manual_rows_and_warnings_as_text(bench, lang):
    world = at_materials(bench, lang)
    bench.control("wizard:git:first_commit").click()
    panel = bench.page.locator('[data-git-commit="snapshot"]')
    expect(panel).to_have_count(1)
    assert bench.say("wizard.first.commit.effect_snapshot") in panel.inner_text()
    assert world.posts() == [], "opening the panel sends nothing"
    bench.control("wizard:git:preview").click()
    expect(bench.page.locator("[data-git-preview]")).to_have_count(1)
    assert world.posts() == [{"name": "git_preview", "body": {
        "step": "first_commit", "mode": "snapshot", "preview": True}}]
    assert bench.text("[data-git-branch]") == bench.say("wizard.first.preview.branch",
                                                        ref="refs/heads/main")
    assert bench.text("[data-git-author]") == bench.say(
        "wizard.first.preview.author", name="First Author", email="first@example.invalid")
    assert bench.text("[data-git-count]") == bench.say("wizard.first.preview.files", count="4")
    assert bench.text('[data-git-warning="suspicious_name"]') == bench.say(
        "wizard.first.warning.suspicious_name")
    manual = bench.page.locator("[data-git-manual-row]")
    assert manual.evaluate_all("nodes => nodes.map(node => node.dataset.gitManualRow)") == [
        "notes-link.md", "data/shared.bin"]
    assert bench.say("wizard.first.manual.symlink") in manual.first.inner_text()
    assert bench.page.locator("[data-git-file]").count() == 0, "the list waits for its toggle"
    bench.control("wizard:git:list").click()
    assert bench.page.locator("[data-git-file]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.gitFile)") == [
        "README.md", "src/app.py", "scripts/run.sh", "config/.env.example"]
    assert len(world.posts()) == 1, "showing the list asks nothing"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_list_of_six_hundred_files_is_drawn_whole_behind_its_toggle(bench, lang):
    world = at_materials(bench, lang)
    rows = [{**ROW, "path": f"src/file-{number:04d}.py"} for number in range(600)]
    patch_preview(bench, {"files": rows})
    to_preview(bench)
    assert bench.text("[data-git-count]") == bench.say("wizard.first.preview.files", count="600")
    bench.control("wizard:git:list").click()
    expect(bench.page.locator("[data-git-file]")).to_have_count(600)
    bench.control("wizard:git:list").click()
    expect(bench.page.locator("[data-git-file]")).to_have_count(0)
    assert len(world.posts()) == 1


@pytest.mark.parametrize("lang", LANGS)
def test_a_text_chosen_by_the_owner_or_a_foreign_file_stays_text_in_the_preview(bench, lang):
    at_materials(bench, lang)
    marked = "a<img src=x onerror=1>.md"
    patch_preview(bench, {
        "target_ref": "refs/heads/<i>x</i>",
        "author": {"name": "<b>Evil</b>", "email": "e@<u>x</u>"},
        "files": [{**ROW, "path": marked}],
        "manual": [{"path": "<script>1</script>", "reason": "made_up"}]})
    to_preview(bench)
    bench.control("wizard:git:list").click()
    root = bench.page.locator("[data-git-preview]")
    expect(bench.page.locator("[data-git-file]")).to_have_count(1)
    assert root.locator("img, b, i, u, script").count() == 0, "no element was made from a text"
    assert marked in bench.text("[data-git-file]")
    assert "<b>Evil</b>" in bench.text("[data-git-author]")
    assert "refs/heads/<i>x</i>" in bench.text("[data-git-branch]")
    assert "<script>1</script>" in bench.text("[data-git-manual-row]")
    assert bench.say("wizard.first.manual.other", code="made_up") in bench.text(
        "[data-git-manual-row]"), "a reason the desk has no words for is said by its code"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_with_the_door_closed_the_confirm_is_disabled_beside_its_reason_and_sends_nothing(
        bench, lang):
    world = at_materials(bench, lang)
    close_door(bench)
    to_preview(bench)
    confirm = bench.control("wizard:git:confirm")
    assert confirm.is_disabled()
    assert reason_beside(bench, "wizard:git:confirm") == bench.say(
        "wizard.first.why.confirm_door_closed")
    confirm.click(force=True)
    assert writes(world) == ["git_preview"], "the closed door is never reached"


@pytest.mark.parametrize("lang", LANGS)
def test_before_a_preview_the_confirm_says_to_prepare_one_and_sends_nothing(bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    bench.control("wizard:git:first_commit").click()
    assert bench.control("wizard:git:confirm").is_disabled()
    assert reason_beside(bench, "wizard:git:confirm") == bench.say(
        "wizard.first.why.preview_missing")
    bench.control("wizard:git:confirm").click(force=True)
    assert world.posts() == []


@pytest.mark.parametrize("lang", LANGS)
def test_with_the_door_open_the_confirm_posts_the_four_keys_once_and_shows_the_receipts_branch(
        bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    bench.page.evaluate("() => { window.host.world.receipt_ref = 'refs/heads/other'; }")
    to_preview(bench)
    shown = bench.page.evaluate("() => window.host.state.wizard.git.preview.paths_digest")
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert writes(world) == ["git_preview", "git_confirm"]
    assert world.posts()[1]["body"] == {"step": "first_commit", "mode": "snapshot",
                                        "paths_digest": shown, "actor": "Anna"}
    assert result(bench).inner_text() == bench.say(
        "wizard.first.done.confirm", ref="refs/heads/other", commit="5e4d3c2", count="4")
    assert bench.page.locator("[data-git-preview]").count() == 0, "the preview is spent"
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "repo")
    assert [row[0] for row in bench.asks()].count("read:git") == 2
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_branch_the_receipt_names_stays_text_too(bench, lang):
    at_materials(bench, lang)
    open_door(bench)
    bench.page.evaluate("() => { window.host.world.receipt_ref = 'refs/heads/<b>x</b>'; }")
    to_preview(bench)
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert result(bench).locator("b").count() == 0, "no element was made from a branch name"
    assert "refs/heads/<b>x</b>" in result(bench).inner_text()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_an_empty_first_commit_is_confirmed_with_a_null_digest(bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench, "empty")
    assert bench.text("[data-git-count]") == bench.say("wizard.first.preview.empty")
    assert bench.page.locator("[data-git-files], [data-git-manual], [data-focus='wizard:git:list']"
                              ).count() == 0
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert world.posts()[0]["body"] == {"step": "first_commit", "mode": "empty", "preview": True}
    assert world.posts()[1]["body"] == {"step": "first_commit", "mode": "empty",
                                        "paths_digest": None, "actor": "Anna"}


@pytest.mark.parametrize("lang", LANGS)
def test_changing_the_mode_drops_the_preview_and_the_confirm_waits_for_a_new_one(bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    assert bench.control("wizard:git:confirm").is_enabled()
    bench.control("wizard:git:mode:empty").click()
    expect(bench.page.locator("[data-git-preview]")).to_have_count(0)
    assert bench.control("wizard:git:confirm").is_disabled()
    assert reason_beside(bench, "wizard:git:confirm") == bench.say(
        "wizard.first.why.preview_missing")
    assert writes(world) == ["git_preview"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_starter_connects_git_and_then_makes_only_an_empty_first_commit(bench, lang):
    world = at_materials(bench, lang, "git_not_git", starter="desk-starter-docs")
    assert bench.say("wizard.first.connect.starter") in bench.text("[data-git-connect]")
    assert bench.page.locator('[data-git-exit="run_without_git"]').count() == 0
    bench.control("wizard:git:connect_git").click()
    expect(bench.control("wizard:git:first_commit")).to_be_enabled()
    open_door(bench)
    bench.control("wizard:git:first_commit").click()
    assert bench.page.locator("[data-focus^='wizard:git:mode:']").count() == 0, "no mode to choose"
    assert bench.text("[data-git-mode]") == bench.say("wizard.first.mode.starter")
    bench.control("wizard:git:preview").click()
    expect(bench.page.locator('[data-git-preview="empty"]')).to_have_count(1)
    bench.control("wizard:git:confirm").click()
    expect(bench.page.locator("[data-git-state]")).to_have_attribute("data-git-state", "repo")
    assert writes(world) == ["git_init", "git_preview", "git_confirm"]
    assert world.posts()[2]["body"]["paths_digest"] is None
    expect(bench.control("wizard:next")).to_be_enabled()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_each_reason_of_the_route_shows_its_notice_and_what_to_do_and_sends_nothing_again(
        bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    for reason in GIT_SETUP_REASONS:
        expect(bench.page.locator("[data-git-commit]")).to_have_count(1)
        if bench.page.locator("[data-git-preview]").count() == 0:
            bench.control("wizard:git:preview").click()
            expect(bench.page.locator("[data-git-preview]")).to_have_count(1)
        world.force("git_confirm", reason=reason)
        before = len(world.posts())
        bench.control("wizard:git:confirm").click()
        expect(result(bench)).to_have_attribute("data-git-notice", f"git_setup.reason.{reason}")
        text = result(bench).inner_text()
        assert bench.say(f"git_setup.reason.{reason}") in text, reason
        assert bench.say(f"wizard.first.next.{reason}") in text, reason
        if reason == "head_exists":
            assert not WAIT_WORDS.search(text), "a plain confirm has no commands to run again"
        assert len(world.posts()) == before + 1, f"{reason}: one press, one request"
        for banned in (bench.say("wizard.first.lost.head"),):
            assert banned not in text, f"{reason}: a refusal is not an unknown outcome"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_refusal_that_means_try_again_offers_the_same_press_and_does_not_make_it(bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    world.force("git_confirm", reason="index_locked")
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-notice", "git_setup.reason.index_locked")
    expect(bench.control("wizard:git:confirm")).to_be_enabled()
    assert writes(world) == ["git_preview", "git_confirm"], "nothing is resent by itself"
    assert [row[0] for row in bench.asks()].count("read:git") == 2, "the read is asked again too"
    world.unforce("git_confirm")
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-result", "done")
    assert writes(world) == ["git_preview", "git_confirm", "git_confirm"]
    assert world.posts()[1]["body"] == world.posts()[2]["body"], "the same body, on purpose"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("reason", ("paths_changed", "signing_ref_unsupported"))
def test_a_refusal_that_wants_a_new_preview_drops_the_old_one_and_says_so_on_the_button(
        bench, lang, reason):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    world.force("git_confirm", reason=reason)
    bench.control("wizard:git:confirm").click()
    expect(result(bench)).to_have_attribute("data-git-notice", f"git_setup.reason.{reason}")
    expect(bench.page.locator("[data-git-preview]")).to_have_count(0)
    assert bench.control("wizard:git:preview").inner_text() == bench.say(
        "wizard.first.preview.again")
    assert bench.control("wizard:git:confirm").is_disabled()
    world.unforce("git_confirm")
    bench.control("wizard:git:preview").click()
    expect(bench.page.locator("[data-git-preview]")).to_have_count(1)
    expect(bench.control("wizard:git:confirm")).to_be_enabled()


@pytest.mark.parametrize("lang", LANGS)
def test_each_other_code_of_the_route_shows_the_existing_notice_of_that_code(bench, lang):
    world = at_materials(bench, lang)
    open_door(bench)
    to_preview(bench)
    for code in OTHER_CODES:
        expect(bench.page.locator("[data-git-commit]")).to_have_count(1)
        detail = {"tool": "git", "reason": "not_pinned"} if code == "tool_unavailable" else {}
        world.force("git_confirm", code=code, detail=detail)
        bench.control("wizard:git:confirm").click()
        expect(result(bench)).to_have_attribute("data-git-notice", f"error.{code}")
        assert bench.say(f"error.{code}") in result(bench).inner_text()
    assert bench.say("wizard.first.tool", tool="git", reason="not_pinned") in result(
        bench).inner_text()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_press_the_desks_own_door_turns_away_says_nothing_was_sent_and_not_unknown(bench, lang):
    world = at_materials(bench, lang, "git_not_git")
    world.force("git_init", code="route_not_found", bare=True)
    bench.control("wizard:git:connect_git").click()
    expect(result(bench)).to_have_attribute("data-git-result", "unsent")
    assert result(bench).inner_text() == bench.say("wizard.first.unsent.route_not_found")
    assert bench.say("wizard.first.lost.head") not in result(bench).inner_text()
    assert [row[0] for row in bench.asks()].count("read:git") == 1, "no read: nothing was sent"
    assert bench.page.locator("[data-git-state]").get_attribute("data-git-state") == "not_git"


@pytest.mark.parametrize("lang", LANGS)
def test_the_exclusion_step_is_offered_only_when_the_read_says_deferred_and_posts_its_body(
        bench, lang):
    world = at_materials(bench, lang)
    assert bench.page.locator("[data-git-exclude]").count() == 0
    deferred = bench.page.evaluate("() => ({...window.host.world.git, exclude: 'deferred'})")
    world.swap(deferred)
    bench.dispatch(type="reread", name="git")
    block = bench.page.locator("[data-git-exclude]")
    expect(block).to_have_count(1)
    assert bench.say("wizard.first.exclude.effect") in block.inner_text()
    bench.control("wizard:git:exclude").click()
    expect(result(bench)).to_have_attribute("data-git-result-kind", "exclude")
    assert world.posts() == [{"name": "git_exclude", "body": {"step": "exclude",
                                                              "actor": "Anna"}}]
    assert result(bench).inner_text() == bench.say("wizard.first.done.exclude")
    expect(bench.page.locator("[data-git-exclude]")).to_have_count(0)
    assert bench.problems == []
