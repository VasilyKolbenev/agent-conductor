"""The slot line and "Free the slot" on the console, on a real one-project server (spec 4.4.6,
4.4.8): the real routes, the real queue, the real pump; only adapters and clock are doubles
(`desk_queue_rig.py`). A holder's grant runs out when the test moves the clock, and the slot then
reads `stuck`. What this module holds, each as a measurement of the page, in Russian and English:

- the slot line says the state of the slot and, for a holder that stopped and for a slot nobody can
  use, the reason in the words of the desk, for every row of the table of spec 4.4.6 (the rows
  the server cannot be made to give are answered in the page, the rest by the server itself);
- a stopped holder offers "Free the slot" once a name is given; the dialog has two choices, equal
  and none of them chosen, says what each does and, for a run that needs a correction the desk
  cannot make, says so; "Pause" and "Revoke the permission" write the control with the person's
  name, the grant the desk read and the last control it saw, and the slot reads free;
- a holder that is not stuck, a project opened for viewing and a console with no name are offered
  nothing (the last says why);
- an answer that is lost is settled by reading the holder: a control that landed says nothing, one
  that did not says it could not be confirmed and the slot stays stuck; a refusal is said in place.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from browser_tests.desk_hold import close_context
from browser_tests import desk_queue_rig as rig
from browser_tests.test_desk_queue import RUNS, WORDS

A = "task-a-r1"
CONTROL = f"/command/runs/{A}/automation/control"
#: The state of the slot in words, without its reason.
LINES = {
    "en": {"free": "Now: nothing is running · the slot is free",
           "busy": "Now: Alpha · holds the slot",
           "stuck": "Now: Alpha · stopped and holds the slot",
           "unavailable": "Now: the slot is unavailable"},
    "ru": {"free": "Сейчас: ничего не идёт · слот свободен",
           "busy": "Сейчас: Alpha · держит слот",
           "stuck": "Сейчас: Alpha · остановился и держит слот",
           "unavailable": "Сейчас: слот недоступен"}}
#: The reason each row that has one gives, in the desk's words.
WHY = {
    "en": {"expired": "the permission expired",
           "feedback_required": "a rejected check needs your review",
           "unknown_action": "an action has an unknown result",
           "ambiguous_actions": "several actions are unsettled",
           "admission_refused": "the next action did not pass the checks",
           "stalled": "the run needs attention",
           "plan_stalled": "the plan has no eligible next step",
           "seed_blocked": "the working folder could not be seeded",
           "owner_required": "the project has no owner",
           "server_stopping": "the server is stopping",
           "project_not_active": "the project is not active"},
    "ru": {"expired": "разрешение истекло",
           "feedback_required": "отклонённая проверка ждёт вашего просмотра",
           "unknown_action": "результат действия неизвестен",
           "ambiguous_actions": "несколько действий не завершены",
           "admission_refused": "следующее действие не прошло проверки допуска",
           "stalled": "запуск требует внимания",
           "plan_stalled": "в плане нет допустимого шага",
           "seed_blocked": "рабочую папку не удалось засеять",
           "owner_required": "у проекта нет владельца",
           "server_stopping": "сервер останавливается",
           "project_not_active": "проект не активен"}}
ROWS = ([("free", None, None)]
        + [("busy", reason, A) for reason in ("action_in_flight", "plan_waiting", "paused",
                                              "revoked", "plan_ended", "ready")]
        + [("stuck", reason, A) for reason in (
            "expired", "feedback_required", "unknown_action", "ambiguous_actions",
            "admission_refused", "stalled", "plan_stalled", "seed_blocked")]
        + [("unavailable", reason, None) for reason in (
            "owner_required", "server_stopping", "project_not_active")])
DIALOG = {
    "en": {"release": "Free the slot",
           "lines": ["Free the slot",
                     "Alpha is stopped and holds the slot. Choose what to do with its "
                     "permission: nothing is chosen for you.",
                     "It can be continued while the permission has not expired.",
                     "It cannot be undone; next comes a new permission or “Rework”."],
           "buttons": ["Pause", "Revoke the permission", "Cancel"],
           "feedback": "Nothing to correct here: continuing would bring back the same stop.",
           "need_name": "Give your name above to free the slot."},
    "ru": {"release": "Освободить слот",
           "lines": ["Освободить слот",
                     "Alpha остановился и держит слот. Выберите, что сделать с его "
                     "разрешением: за вас ничего не выбрано.",
                     "Продолжить можно, пока разрешение не истекло.",
                     "Необратимо; дальше — новое разрешение или «Доработать»."],
           "buttons": ["Приостановить", "Отозвать разрешение", "Отмена"],
           "feedback": "Исправлять нечем — продолжение вернёт ту же остановку.",
           "need_name": "Укажите имя выше, чтобы освободить слот."}}
REFUSED = {"en": "The request shape is invalid.", "ru": "Форма запроса неверна."}


def _stuck(served: rig.Project) -> None:
    """Alpha holds the slot at its final gate; then its grant runs out and the slot is stuck."""
    rig.hold(served, A, "g-a")
    served.ticks[0] = rig.PAST_THE_WINDOW
    served.wait("the slot is stuck", lambda: served.queue()["slot"]["state"] == "stuck")


def _slot_as(state: str, reason: str | None, run_id: str | None):
    """A route handler that answers the real queue with its slot replaced."""
    def handle(route) -> None:
        body = route.fetch().json()
        body["slot"] = {"state": state, "run_id": run_id, "reason_code": reason}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    return handle


def _wait_slot(window: rig.Window, state: str) -> None:
    window.page.wait_for_function(
        """(word) => document.querySelector("#deskPult .desk-queue__now")
          ?.textContent.includes(word)""", arg=state, timeout=8000)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_slot_line_says_its_state_and_why_for_every_row_of_the_table(
        chromium, tmp_path: Path, language):
    words, why = LINES[language], WHY[language]
    with rig.project(tmp_path, RUNS) as served:
        rig.hold(served, A, "g-a")
        for state, reason, run_id in ROWS:
            window = rig.open_desk(chromium, served, language, before=lambda page, row=(
                state, reason, run_id): page.route("**/command/queue", _slot_as(*row)))
            base = words[state]
            expected = f"{base}: {why[reason]}" if state in ("stuck", "unavailable") else base
            assert window.facts()["now"] == expected, (state, reason)
            close_context(window.page.context)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_real_server_gives_the_rows_a_free_slot_a_held_slot_and_an_expired_holder(
        chromium, tmp_path: Path, language):
    words, why = LINES[language], WHY[language]
    with rig.project(tmp_path, RUNS) as served:
        assert rig.open_desk(chromium, served, language).facts()["now"] == words["free"]
        rig.hold(served, A, "g-a")
        assert rig.open_desk(chromium, served, language).facts()["now"] == words["busy"]
        served.ticks[0] = rig.PAST_THE_WINDOW
        served.wait("the slot is stuck", lambda: served.queue()["slot"]["state"] == "stuck")
        assert rig.open_desk(chromium, served, language).facts()["now"] == (
            f"{words['stuck']}: {why['expired']}")


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_stopped_holder_offers_the_release_and_the_dialog_has_two_choices_and_none_chosen(
        chromium, tmp_path: Path, language):
    words = DIALOG[language]
    with rig.project(tmp_path, RUNS) as served:
        _stuck(served)
        window = rig.open_desk(chromium, served, language)
        window.name("vasya")
        assert window.facts()["release"] == words["release"]
        assert window.facts()["dialog"] is None
        window.press("queue:release")
        window.until("the slot read behind the dialog", lambda: window.facts()["dialog"]
                     is not None)
        facts = window.facts()
        assert facts["dialog"]["kind"] == "release" and facts["dialog"]["lines"] == words["lines"]
        assert [button["text"] for button in facts["dialog"]["buttons"]] == words["buttons"]
        assert [button["key"] for button in facts["dialog"]["buttons"]] == [
            "queue:release:pause", "queue:release:revoke", "queue:release:cancel"]
        assert all(button["size"][1] >= 44 for button in facts["dialog"]["buttons"])
        assert facts["focus"] not in ("queue:release:pause", "queue:release:revoke")
        window.press("queue:release:cancel")
        assert window.facts()["dialog"] is None and window.posted == []
        assert window.errors() == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_run_that_needs_a_correction_the_desk_cannot_make_says_so_in_the_dialog(
        chromium, tmp_path: Path, language):
    words = DIALOG[language]
    with rig.project(tmp_path, RUNS) as served:
        rig.hold(served, A, "g-a")
        window = rig.open_desk(chromium, served, language, before=lambda page: page.route(
            "**/command/queue", _slot_as("stuck", "feedback_required", A)))
        window.name("vasya")
        window.press("queue:release")
        window.until("the slot read behind the dialog", lambda: window.facts()["dialog"]
                     is not None)
        lines = window.facts()["dialog"]["lines"]
        assert lines == [*words["lines"][:2], words["feedback"], *words["lines"][2:]]


@pytest.mark.parametrize("action", ["pause", "revoke"])
@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_choice_writes_the_control_with_the_person_and_the_grant_read_and_the_slot_reads_free(
        chromium, tmp_path: Path, language, action):
    with rig.project(tmp_path, RUNS) as served:
        _stuck(served)
        grant = served.automation(A)["authorization"]
        window = rig.open_desk(chromium, served, language)
        window.name("vasya")
        window.press("queue:release")
        window.press(f"queue:release:{action}")
        window.page.wait_for_function(
            "() => document.querySelector('#deskPult .desk-queue__now')"
            "?.textContent.includes('Alpha') === false", timeout=8000)
        facts = window.facts()
        ((path, body),) = window.posted
        assert path == CONTROL
        assert sorted(body) == ["action", "actor", "authorization_digest", "authorization_id",
                                "control_id", "expected_control_id"]
        assert (body["action"], body["actor"], body["authorization_id"],
                body["authorization_digest"], body["expected_control_id"]) == (
            action, "vasya", grant["authorization_id"], grant["authorization_digest"], None)
        assert body["control_id"].startswith("control-")
        assert served.automation(A)["control"]["action"] == action
        assert served.queue()["slot"]["state"] == "free"
        assert facts["now"] == LINES[language]["free"] and facts["dialog"] is None
        assert facts["release"] is None and facts["notice"] is None
        assert window.errors() == []


def _lose(land: bool):
    def handle(route) -> None:
        if land:
            route.fetch()
        route.abort()
    return handle


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_control_whose_answer_was_lost_after_it_landed_is_settled_by_the_read(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, RUNS) as served:
        _stuck(served)
        window = rig.open_desk(chromium, served, language, before=lambda page: page.route(
            "**" + CONTROL, _lose(True)))
        window.name("vasya")
        window.press("queue:release")
        window.press("queue:release:pause")
        _wait_slot(window, LINES[language]["free"])
        facts = window.facts()
        assert facts["notice"] is None and facts["dialog"] is None
        assert served.queue()["slot"]["state"] == "free" and len(window.posted) == 1


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_control_whose_answer_was_lost_before_it_landed_says_it_could_not_be_confirmed(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, RUNS) as served:
        _stuck(served)
        window = rig.open_desk(chromium, served, language, before=lambda page: page.route(
            "**" + CONTROL, _lose(False)))
        window.name("vasya")
        window.press("queue:release")
        window.press("queue:release:revoke")
        window.page.wait_for_function(
            "() => document.querySelector('#deskPult [data-pult-notice]') !== null")
        facts = window.facts()
        assert facts["notice"] == (
            "The change could not be confirmed. This is the queue the server holds."
            if language == "en"
            else "Изменение не удалось подтвердить. Здесь — очередь, как её хранит сервер.")
        assert served.queue()["slot"]["state"] == "stuck"
        assert facts["release"] == DIALOG[language]["release"] and facts["dialog"] is None


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_refused_control_is_said_in_place_and_the_slot_stays_stuck(
        chromium, tmp_path: Path, language):
    body = {"error": {"code": "contract_invalid", "message": "refused", "detail": {}}}
    with rig.project(tmp_path, RUNS) as served:
        _stuck(served)
        window = rig.open_desk(chromium, served, language, before=lambda page: page.route(
            "**" + CONTROL, lambda route: route.fulfill(
                status=422, content_type="application/json", body=json.dumps(body))))
        window.name("vasya")
        window.press("queue:release")
        window.press("queue:release:pause")
        window.page.wait_for_function(
            "() => document.querySelector('#deskPult [data-pult-notice]') !== null")
        facts = window.facts()
        assert facts["notice"] == REFUSED[language] and facts["dialog"] is None
        assert served.queue()["slot"]["state"] == "stuck"
        assert window.errors(ignore=("422",)) == []


def test_a_control_by_another_window_after_the_dialog_prevents_its_stale_revoke(
        chromium, tmp_path: Path):
    with rig.project(tmp_path, RUNS) as served:
        _stuck(served)
        window = rig.open_desk(chromium, served, "en")
        window.name("vasya")
        window.press("queue:release")
        window.until("the holder read behind the dialog", lambda: window.facts()["dialog"]
                     is not None)
        grant = served.automation(A)["authorization"]
        body = {"control_id": "control-other-pause",
                "authorization_id": grant["authorization_id"],
                "authorization_digest": grant["authorization_digest"],
                "expected_control_id": None, "action": "pause", "actor": "other"}
        status, _answer = served.call("POST", CONTROL, body)
        assert status in (200, 201)
        window.press("queue:release:revoke")
        window.until("the stale dialog closes", lambda: window.facts()["dialog"] is None)
        assert window.requests("POST", CONTROL) == 0
        assert served.automation(A)["control"]["control_id"] == "control-other-pause"


@pytest.mark.parametrize("language", ["en", "ru"])
def test_without_a_name_the_console_says_why_it_offers_no_release(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, RUNS) as served:
        _stuck(served)
        window = rig.open_desk(chromium, served, language)
        facts = window.facts()
        assert facts["release"] is None and facts["slotHint"] == DIALOG[language]["need_name"]
        window.name("vasya")
        facts = window.facts()
        assert facts["release"] == DIALOG[language]["release"] and facts["slotHint"] is None


def test_a_holder_that_is_not_stuck_and_a_project_in_view_are_offered_no_release(
        chromium, tmp_path: Path):
    (tmp_path / "active").mkdir()
    (tmp_path / "view").mkdir()
    with rig.project(tmp_path / "active", RUNS) as served:
        rig.hold(served, A, "g-a")                      # waiting at its final gate: busy
        window = rig.open_desk(chromium, served, "en")
        window.name("vasya")
        assert window.facts()["release"] is None and window.facts()["slotHint"] is None
    with rig.project(tmp_path / "view", RUNS, mode="view") as served:
        window = rig.open_desk(chromium, served, "en", before=lambda page: page.route(
            "**/command/queue", _slot_as("stuck", "expired", A)))
        window.name("vasya")
        assert window.facts()["release"] is None and window.facts()["slotHint"] is None
