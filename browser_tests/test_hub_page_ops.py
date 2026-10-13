"""What the hub's page does with an operation the hub began for a press, in a real browser.

«Восстановить» on a project, «Восстановить вход» on a login box and «Применить профиль» answer `202
{operation_id}`. The page follows `GET /hub/operations/<id>` (and the `operation` frame by id, which
makes it read at once) and tells how the row ends, as a banner that names the project or the login
and says the sentence of the row's own reason: a recovery that needs a preparation first is never
told "restart" (lane H's handoff). A press that answers the SAME id (a login recovery pressed
twice) opens no second row. The fake hub checks each POST as the hub does and records it. Every
test runs in both languages.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from browser_tests.hub_bench import (HubPage, fixture, hub,  # noqa: F401
                                     hub_page, lang, ready, say)

PROJECTS = fixture("hub_projects.json")
WEB, LANDING, BOT = (row["project_id"] for row in PROJECTS["projects"])
LOGIN = fixture("hub_setup.json")["logins"][0]["login_key"]
OP, OTHER = "operation-" + "5" * 32, "operation-" + "6" * 32
REASONS = ("restart_needed", "prepare_needed", "other_environment", "not_proven")
OPERATION = '#hubBanners [data-banner="operation"]'
#: Shorter than the page's own slow read of a running operation: a change that shows inside it was
#: read because a frame said so.
FRAME_WAIT_MS = 3000


def op_row(kind: str, state: str, **over: object) -> dict[str, object]:
    """One row of `GET /hub/operations/<id>` in the form of 4.6.4 with the additive `detail`."""
    return {"operation_id": OP, "kind": kind, "source": None, "state": state, "step": kind,
            "project_id": None, "code": None, "detail": None, "result": None, **over}


def press(page: HubPage, key: str) -> None:
    page.page.locator(f'[data-focus="{key}"]').click()


def clause(page: HubPage, code: str) -> str:
    return page.page.evaluate("""async (code) => (await import("/hub/hub-copy.js"))
      .codeWords(document.documentElement.lang, code)""", code)


def stream_open(page: HubPage) -> None:
    """Wait until the page's one stream is open: the page reads nothing by itself after that."""
    for _ in range(160):
        if page.hub.streams_opened >= 1 and page.hub.requests("/hub/limits") >= 1:
            return
        page.page.wait_for_timeout(50)
    raise AssertionError("the stream was not opened")


def stuck(page: HubPage) -> None:
    """The third project is one whose stop was not confirmed: its main action is «Recover»."""
    rows = fixture("hub_projects.json")
    rows["projects"][2].update(state="stop_uncertain", working="stopped")
    page.hub.answer("/hub/projects", rows)
    page.page.reload()
    ready(page)
    stream_open(page)


def actions_of(page: HubPage, project: str) -> list[str]:
    return page.page.evaluate("""(id) => [...document.querySelectorAll(
      `.hub-project[data-project-id="${id}"] .hub-project__act`)].map((b) => b.dataset.action)""",
                              project)


def unclosed_login(page: HubPage) -> None:
    """The login box of the fixture is one that was not closed: the banner offers its recovery."""
    setup = fixture("hub_setup.json")
    setup["logins"][0]["state"] = "unclosed"
    page.hub.answer("/hub/setup", setup)
    page.page.reload()
    ready(page)


def take_recover(page: HubPage, operation: str = OP) -> None:
    page.hub.post_answers[f"/hub/projects/{BOT}/recover"] = (202, {"operation_id": operation})


def take_login(page: HubPage, operation: str = OP) -> None:
    page.hub.post_answers[f"/hub/logins/{LOGIN}/recover"] = (202, {"operation_id": operation})


def operation_at(page: HubPage, row: dict[str, object], operation: str = OP) -> None:
    page.hub.answer(f"/hub/operations/{operation}", {**row, "operation_id": operation})


@pytest.mark.parametrize("reason", REASONS)
def test_a_failed_recovery_is_told_by_its_reason_and_never_by_the_bare_words(hub_page, reason):
    page = hub_page
    stuck(page)
    take_recover(page)
    operation_at(page, op_row("recover", "failed", code="recovery_required", project_id=BOT,
                              detail={"reason": reason}))
    press(page, f"act:{BOT}:recover")
    banner = page.page.locator(OPERATION)
    expect(banner).to_have_count(1)
    sentence = say(page, f"hub.reason.recover.{reason}")
    expect(banner).to_contain_text(sentence)
    text = banner.text_content()
    assert text.startswith("bot"), "the banner names the project it is about"
    for bare in (say(page, "hub.state.recovery_required"), clause(page, "recovery_required")):
        assert bare not in text
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/recover", "body": {}}], (
        "one post went out, with nothing in it")
    assert page.hub.requests(f"/hub/operations/{OP}") >= 1


def test_a_reason_the_page_has_no_word_for_is_told_as_not_proven_and_never_as_a_restart(hub_page):
    page = hub_page
    stuck(page)
    take_recover(page)
    operation_at(page, op_row("recover", "failed", code="recovery_required", project_id=BOT,
                              detail={"reason": "reboot_twice"}))
    press(page, f"act:{BOT}:recover")
    expect(page.page.locator(OPERATION)).to_contain_text(
        say(page, "hub.reason.recover.not_proven"))
    assert say(page, "hub.reason.recover.restart_needed") not in page.page.locator(
        OPERATION).text_content()


def test_a_failed_login_recovery_is_told_by_its_reason_for_a_login_and_names_the_harness(hub_page):
    page = hub_page
    unclosed_login(page)
    take_login(page)
    operation_at(page, op_row("recover_login", "failed", code="login_recovery_required",
                              detail={"reason": "other_environment"}))
    press(page, f"login:{LOGIN}")
    banner = page.page.locator(OPERATION)
    expect(banner).to_contain_text(say(page, "hub.reason.recover_login.other_environment"))
    assert banner.text_content().startswith("claude-code")
    assert page.hub.posts == [{"path": f"/hub/logins/{LOGIN}/recover", "body": {}}]


def test_a_recovery_that_failed_for_another_code_says_the_clause_of_that_code(hub_page):
    page = hub_page
    stuck(page)
    take_recover(page)
    operation_at(page, op_row("recover", "failed", code="ownership_lost", project_id=BOT))
    press(page, f"act:{BOT}:recover")
    expect(page.page.locator(OPERATION)).to_contain_text(
        say(page, "hub.op.failed", reason=clause(page, "ownership_lost")))


def test_a_running_operation_is_one_row_until_a_frame_says_it_ended(hub_page):
    page = hub_page
    stuck(page)
    take_recover(page)
    operation_at(page, op_row("recover", "running", project_id=BOT))
    press(page, f"act:{BOT}:recover")
    banner = page.page.locator(OPERATION)
    expect(banner).to_have_count(1)
    expect(banner).to_contain_text(say(page, "hub.op.running"))
    expect(banner).to_have_attribute("data-phase", "running")
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.accepted"))
    assert actions_of(page, BOT) == ["recover"]
    operation_at(page, op_row("recover", "succeeded", project_id=BOT))
    recovered = fixture("hub_projects.json")
    page.hub.answer("/hub/projects", recovered)
    page.hub.push({"kind": "operation", "operation_id": OP})
    expect(banner).to_have_count(0, timeout=FRAME_WAIT_MS)
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.op.done.recover"))
    for _ in range(80):
        if actions_of(page, BOT) == ["activate"]:
            break
        page.page.wait_for_timeout(50)
    assert actions_of(page, BOT) == ["activate"], "what was done is read, not assumed"


def test_a_frame_makes_the_page_read_a_running_operation_at_once(hub_page):
    page = hub_page
    stuck(page)
    take_recover(page)
    operation_at(page, op_row("recover", "running", project_id=BOT))
    press(page, f"act:{BOT}:recover")
    expect(page.page.locator(OPERATION)).to_have_count(1)
    operation_at(page, op_row("recover", "failed", code="recovery_refused", project_id=BOT))
    page.hub.push({"kind": "operation", "operation_id": OP})
    expect(page.page.locator(OPERATION)).to_have_attribute("data-phase", "failed",
                                                           timeout=FRAME_WAIT_MS)


def test_a_frame_for_an_operation_nobody_follows_or_with_an_id_off_the_grammar_reads_nothing(
        hub_page):
    page = hub_page
    ready(page)
    stream_open(page)
    limits = page.hub.requests("/hub/limits")
    page.hub.push({"kind": "operation", "operation_id": "operation-x"})
    page.hub.push({"kind": "operation", "operation_id": OTHER})
    page.hub.push({"kind": "operation"})
    page.hub.push({"kind": "limits"})
    for _ in range(80):
        if page.hub.requests("/hub/limits") > limits:
            break
        page.page.wait_for_timeout(50)
    assert page.hub.requests("/hub/limits") > limits, "the frames after them were taken in order"
    assert [path for path in page.hub.gets if path.startswith("/hub/operations/")] == []


def test_a_login_recovery_pressed_twice_answers_the_same_id_and_opens_one_row(hub_page):
    page = hub_page
    unclosed_login(page)
    take_login(page)
    operation_at(page, op_row("recover_login", "running"))
    press(page, f"login:{LOGIN}")
    expect(page.page.locator(OPERATION)).to_have_count(1)
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.accepted"))
    press(page, f"login:{LOGIN}")
    for _ in range(80):
        if len(page.hub.posts) == 2:
            break
        page.page.wait_for_timeout(50)
    assert [post["path"] for post in page.hub.posts] == [f"/hub/logins/{LOGIN}/recover"] * 2
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.accepted"))
    expect(page.page.locator(OPERATION)).to_have_count(1)


def test_two_different_operations_are_two_rows_and_a_dismissed_one_leaves_the_other(hub_page):
    page = hub_page
    stuck(page)
    setup = fixture("hub_setup.json")
    setup["logins"][0]["state"] = "unclosed"
    page.hub.answer("/hub/setup", setup)
    page.page.reload()
    ready(page)
    take_recover(page, OP)
    take_login(page, OTHER)
    operation_at(page, op_row("recover", "failed", code="ownership_lost", project_id=BOT), OP)
    operation_at(page, op_row("recover_login", "failed", code="login_owner_busy"), OTHER)
    press(page, f"act:{BOT}:recover")
    expect(page.page.locator(OPERATION)).to_have_count(1)
    press(page, f"login:{LOGIN}")
    expect(page.page.locator(OPERATION)).to_have_count(2)
    press(page, f"op:{OTHER}:dismiss")
    banner = page.page.locator(OPERATION)
    expect(banner).to_have_count(1)
    expect(banner).to_contain_text(
        say(page, "hub.op.failed", reason=clause(page, "ownership_lost")))


def test_a_read_the_hub_refuses_ends_the_row_with_the_clause_of_its_code(hub_page):
    page = hub_page
    stuck(page)
    take_recover(page)
    page.hub.answer(f"/hub/operations/{OP}", {"error": {"code": "operation_not_found",
                    "message": "", "detail": None}}, status=404)
    press(page, f"act:{BOT}:recover")
    expect(page.page.locator(OPERATION)).to_contain_text(
        say(page, "hub.op.failed", reason=clause(page, "operation_not_found")))


def test_the_sentence_of_a_row_follows_the_language_of_the_page(hub_page, lang):
    page = hub_page
    stuck(page)
    take_recover(page)
    operation_at(page, op_row("recover", "failed", code="recovery_required", project_id=BOT,
                              detail={"reason": "prepare_needed"}))
    press(page, f"act:{BOT}:recover")
    banner = page.page.locator(OPERATION)
    expect(banner).to_contain_text(say(page, "hub.reason.recover.prepare_needed"))
    other = "ru" if lang == "en" else "en"
    press(page, f"seg:lang:{other}")
    expect(page.page.locator("html")).to_have_attribute("lang", other)
    expect(banner).to_contain_text(say(page, "hub.reason.recover.prepare_needed"))
    assert banner.text_content().count("conduct ownership recover --prepare-restart") == 1


# -- «Применить профиль» and «…и перезапустить»: one entry, one route ----------------------------


def menu_items(page: HubPage, project: str) -> list[list[str]]:
    """The entries of the menu of a project, opened: their keys and labels."""
    press(page, f"menu:{project}")
    return page.page.evaluate("""(id) => [...document.querySelectorAll(
      `.hub-project[data-project-id="${id}"] .hub-project__items button`)].map(
      (b) => [b.dataset.focus, b.textContent])""", project)


def test_the_menu_of_a_stopped_project_offers_the_profile_and_one_press_sends_one_empty_body(
        hub_page):
    page = hub_page
    ready(page)
    items = menu_items(page, BOT)
    assert [key for key, _ in items] == [f"act:{BOT}:view_open", f"act:{BOT}:apply_profile",
                                         f"act:{BOT}:forget"]
    assert dict(items)[f"act:{BOT}:apply_profile"] == say(page, "hub.act.apply_profile")
    page.hub.post_answers[f"/hub/projects/{BOT}/providers"] = (202, {"operation_id": OP})
    operation_at(page, op_row("providers", "running", project_id=BOT))
    press(page, f"act:{BOT}:apply_profile")
    expect(page.page.locator(OPERATION)).to_contain_text(say(page, "hub.op.running"))
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/providers", "body": {}}], (
        "no confirmation is asked and one empty body is sent")


def test_the_menu_of_a_running_project_says_restart_and_sends_the_same_request(hub_page):
    page = hub_page
    ready(page)
    items = menu_items(page, WEB)
    assert items == [[f"act:{WEB}:apply_profile", say(page, "hub.act.apply_profile_restart")]]
    page.hub.post_answers[f"/hub/projects/{WEB}/providers"] = (202, {"operation_id": OP})
    operation_at(page, op_row("providers", "succeeded", project_id=WEB,
                              result={"providers": "copied"}))
    press(page, f"act:{WEB}:apply_profile")
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.op.done.providers"))
    assert page.hub.posts == [{"path": f"/hub/projects/{WEB}/providers", "body": {}}]
    expect(page.page.locator(OPERATION)).to_have_count(0)


def test_a_profile_copy_that_met_a_project_not_closed_properly_names_the_recovery_first(hub_page):
    page = hub_page
    ready(page)
    menu_items(page, BOT)
    page.hub.post_answers[f"/hub/projects/{BOT}/providers"] = (202, {"operation_id": OP})
    operation_at(page, op_row("providers", "failed", code="subprocess_failed", project_id=BOT,
                              detail={"reason": "recovery_required"}))
    press(page, f"act:{BOT}:apply_profile")
    banner = page.page.locator(OPERATION)
    expect(banner).to_contain_text(say(page, "hub.reason.recovery_required"))
    assert clause(page, "subprocess_failed") not in banner.text_content()


def test_a_profile_copy_that_failed_for_its_own_code_says_the_clause_of_that_code(hub_page):
    page = hub_page
    ready(page)
    menu_items(page, BOT)
    page.hub.post_answers[f"/hub/projects/{BOT}/providers"] = (202, {"operation_id": OP})
    operation_at(page, op_row("providers", "failed", code="owner_busy", project_id=BOT))
    press(page, f"act:{BOT}:apply_profile")
    expect(page.page.locator(OPERATION)).to_contain_text(
        say(page, "hub.op.failed", reason=clause(page, "owner_busy")))


@pytest.mark.parametrize("code", ["profile_absent", "profile_invalid", "project_busy"])
def test_a_refusal_of_the_profile_route_is_said_in_the_clause_of_its_code(hub_page, code):
    page = hub_page
    ready(page)
    menu_items(page, BOT)
    page.hub.refuse(f"/hub/projects/{BOT}/providers", 409, code)
    press(page, f"act:{BOT}:apply_profile")
    expect(page.page.locator("#hubStatus")).to_have_text(
        say(page, "hub.notice.refused", reason=clause(page, code)))
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/providers", "body": {}}]
    expect(page.page.locator(OPERATION)).to_have_count(0)


@pytest.mark.parametrize("profile", ["absent", "invalid"])
def test_no_profile_is_offered_while_the_profile_is_absent_or_invalid(hub_page, profile):
    page = hub_page
    setup = fixture("hub_setup.json")
    setup["profile"] = profile
    page.hub.answer("/hub/setup", setup)
    page.page.reload()
    ready(page)
    keys = [key for key, _ in menu_items(page, BOT)]
    assert keys == [f"act:{BOT}:view_open", f"act:{BOT}:forget"]
    assert page.page.locator(f'[data-focus="menu:{WEB}"]').count() == 0, (
        "a running project has no menu at all while there is nothing in it")
