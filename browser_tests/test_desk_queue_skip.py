"""The holder's "Skip ahead" on the console, on a real one-project server (spec 4.4.8): the real
routes, the real queue, the real pump; only adapters and clock are doubles (`desk_queue_rig.py`).
A run that keeps the slot waits at its final gate; one press on "Skip ahead" pauses it and queues
its continuation last, and the pump starts the head of the queue when the slot frees. What this
module holds, each as a measurement of the page, in Russian and English:

- a holder that waits for a person offers "Skip ahead" while the queue behind it is not empty
  and a name is given (without one the console says so); no other slot, no empty queue and no
  project opened for viewing is offered it;
- the dialog names the holder, says what the press does and that the permission window keeps
  running until the instant it ends (the desk reads no clock, so it says when, not how long);
- one press writes the pause (the grant the desk read, the last control it saw, the person) and then
  the continuation (`POST /command/queue` with a `resume` entry whose `expected_control_id` is that
  pause), in that order, once each; the head of the queue starts and the holder's continuation is
  last;
- a lost answer is settled by reading: a continuation that landed says nothing; one that did not
  says it could not be confirmed, keeps the dialog, and the next press continues from the step
  that is undone -- the pause is not written twice;
- a refusal of the pause writes nothing more and says so; a refusal of the continuation says the
  run is paused and was not queued.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from browser_tests import desk_queue_rig as rig

A, B, C = "task-a-r1", "task-b-r1", "task-c-r1"
SEEDS = [rig.Seed(A, "task-a", "Alpha", final_gate=True),
         rig.Seed(B, "task-b", "Bravo", final_gate=True), rig.Seed(C, "task-c", "Charlie")]
CONTROL, PUT = f"/command/runs/{A}/automation/control", "/command/queue"
WORDS = {
    "en": {"skip": "Skip ahead", "need_name": "Give your name above to skip ahead.",
           "lines": ["Skip ahead",
                     "Alpha waits for a decision and holds the slot. Skip ahead pauses it, queues "
                     "its continuation last and lets the first entry start.",
                     "Its permission window keeps running: it ends at 08/11 12:05."],
           "buttons": ["Pause it and queue its continuation", "Cancel"],
           "unconfirmed": "The change could not be confirmed. This is the queue the server "
                          "holds.",
           "partial": "Alpha is paused, but its continuation was not queued. This run cannot be "
                      "queued now. Nothing was queued; the preparation of its task says why.",
           "refused": "The request shape is invalid.", "starts": "starts on its own"},
    "ru": {"skip": "Пропустить вперёд", "need_name": "Укажите имя выше, чтобы пропустить вперёд.",
           "lines": ["Пропустить вперёд",
                     "Alpha ждёт решения и держит слот. «Пропустить вперёд» приостановит его, "
                     "поставит продолжение в конец очереди и даст стартовать первой записи.",
                     "Окно его разрешения продолжает идти: оно кончается в 11.08 12:05."],
           "buttons": ["Приостановить и поставить продолжение в очередь", "Отмена"],
           "unconfirmed": "Изменение не удалось подтвердить. Здесь — очередь, как её хранит "
                          "сервер.",
           "partial": "Alpha приостановлен, но его продолжение не поставлено в очередь. Этот "
                      "запуск сейчас нельзя поставить в очередь. Ничего не поставлено; причину "
                      "показывает подготовка его задачи.",
           "refused": "Форма запроса неверна.", "starts": "начнётся сама"}}


def _world(served: rig.Project) -> None:
    """Alpha holds the slot at its final gate; Bravo and Charlie wait behind it."""
    rig.hold(served, A, "g-a")
    rig.enqueue(served, B, "g-b")
    rig.enqueue(served, C, "g-c")


def _desk(chromium, served, language, **more):
    window = rig.open_desk(chromium, served, language, **more)
    window.name("vasya")
    return window


def _skip_ahead(window: rig.Window) -> None:
    window.press("queue:skip")
    window.press("queue:skip:confirm")


def _wait_notice(window: rig.Window) -> None:
    window.page.wait_for_function(
        "() => document.querySelector('#deskPult [data-pult-notice]') !== null")


def _entries(served: rig.Project) -> list[tuple[str, str]]:
    return [(row["run_id"], row["kind"]) for row in served.queue()["entries"]]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_holder_that_waits_for_a_person_offers_skip_ahead_while_the_queue_is_not_empty(
        chromium, tmp_path: Path, language):
    words = WORDS[language]
    with rig.project(tmp_path, SEEDS) as served:
        rig.hold(served, A, "g-a")
        window = rig.open_desk(chromium, served, language)
        alone = window.facts()                          # an empty queue: nothing to skip for
        window.name("vasya")
        assert (alone["slotHint"], window.facts()["skip"], window.facts()["release"]) == (
            None, None, None)
        rig.enqueue(served, B, "g-b")
        window = rig.open_desk(chromium, served, language)
        assert (window.facts()["skip"], window.facts()["slotHint"]) == (None, words["need_name"])
        window.name("vasya")
        assert (window.facts()["skip"], window.facts()["slotHint"]) == (words["skip"], None)


def test_no_other_slot_and_no_project_in_view_is_offered_skip_ahead(
        chromium, tmp_path: Path):
    (tmp_path / "active").mkdir()
    (tmp_path / "view").mkdir()
    with rig.project(tmp_path / "active", SEEDS) as served:
        rig.hold(served, A, "g-a")
        rig.enqueue(served, B, "g-b")
        served.ticks[0] = rig.PAST_THE_WINDOW         # the holder's grant runs out: stuck
        served.wait("the slot is stuck", lambda: served.queue()["slot"]["state"] == "stuck")
        window = _desk(chromium, served, "en")
        assert window.facts()["skip"] is None and window.facts()["release"] == "Free the slot"
    with rig.project(tmp_path / "view", SEEDS, mode="view") as served:
        rig.enqueue(served, B, "g-b")
        window = _desk(chromium, served, "en", before=lambda page: page.route(
            "**/command/queue", _slot_as("busy", "plan_waiting", A)))
        assert window.facts()["skip"] is None and window.facts()["slotHint"] is None


def _slot_as(state: str, reason: str, run_id: str):
    def handle(route) -> None:
        body = route.fetch().json()
        body["slot"] = {"state": state, "run_id": run_id, "reason_code": reason}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    return handle


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_dialog_names_the_holder_and_the_end_of_its_window_and_nothing_is_written_yet(
        chromium, tmp_path: Path, language):
    words = WORDS[language]
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)
        window = _desk(chromium, served, language)
        window.press("queue:skip")
        window.until("the holder's permission window", lambda: window.facts()["dialog"]
                     is not None and len(window.facts()["dialog"]["lines"]) == 3)
        facts = window.facts()
        assert facts["dialog"]["kind"] == "skip" and facts["dialog"]["lines"] == words["lines"]
        assert [button["text"] for button in facts["dialog"]["buttons"]] == words["buttons"]
        assert [button["key"] for button in facts["dialog"]["buttons"]] == [
            "queue:skip:confirm", "queue:skip:cancel"]
        assert all(button["size"][1] >= 44 for button in facts["dialog"]["buttons"])
        window.press("queue:skip:cancel")
        assert window.facts()["dialog"] is None and window.posted == []
        assert served.automation(A)["control"] is None and _entries(served) == [
            (B, "start"), (C, "start")]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_one_press_pauses_the_holder_then_queues_its_continuation_last_and_the_head_starts(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)
        grant = served.automation(A)["authorization"]
        window = _desk(chromium, served, language)
        _skip_ahead(window)
        served.wait("Bravo holds the slot", lambda: served.queue()["slot"]["run_id"] == B)
        window.page.wait_for_function(
            "() => document.querySelector('#deskPult [data-pult-dialog]') === null")
        (control, pause), (put, resume) = window.posted
        assert (control, put) == (CONTROL, PUT)
        assert (pause["action"], pause["actor"], pause["expected_control_id"]) == (
            "pause", "vasya", None)
        assert pause["authorization_id"] == grant["authorization_id"]
        assert pause["control_id"].startswith("control-") and pause["control_id"].endswith("-pause")
        assert sorted(resume) == ["resume", "run_id"] and resume["run_id"] == A
        assert sorted(resume["resume"]) == ["actor", "authorization_digest", "authorization_id",
                                            "control_id", "expected_control_id"]
        assert resume["resume"]["expected_control_id"] == pause["control_id"]
        assert resume["resume"]["actor"] == "vasya"
        assert _entries(served) == [(C, "start"), (A, "resume")]
        assert served.automation(A)["control"]["control_id"] == pause["control_id"]
        facts = window.facts()
        assert facts["notice"] is None and [row["run"] for row in facts["entries"]] in (
            [C, A], [A])
        assert window.errors() == []


def _lost_put(land_first: bool):
    """Loses the answer of the first write to the queue (after it landed, or before), then lets
    the next through; a read is never touched."""
    calls = []

    def handle(route) -> None:
        if route.request.method != "POST":
            route.continue_()
            return
        calls.append(1)
        if len(calls) > 1:
            route.continue_()
            return
        if land_first:
            route.fetch()
        route.abort()
    return handle


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_continuation_whose_answer_was_lost_after_it_landed_is_settled_by_the_read(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)
        window = _desk(chromium, served, language, before=lambda page: page.route(
            "**" + PUT, _lost_put(True)))
        _skip_ahead(window)
        window.until("the intercepted queue write", lambda: len(window.posted) >= 2)
        window.until("the settled dialog", lambda: window.facts()["dialog"] is None)
        served.wait("Bravo holds the slot", lambda: served.queue()["slot"]["run_id"] == B)
        assert window.facts()["notice"] is None
        assert _entries(served) == [(C, "start"), (A, "resume")]
        assert [path for path, _body in window.posted] == [CONTROL, PUT]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_an_unlanded_continuation_keeps_the_dialog_and_the_next_press_only_retries_it(
        chromium, tmp_path: Path, language):
    words = WORDS[language]
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)
        window = _desk(chromium, served, language, before=lambda page: page.route(
            "**" + PUT, _lost_put(False)))
        _skip_ahead(window)
        _wait_notice(window)
        facts = window.facts()
        assert facts["notice"] == words["unconfirmed"]
        assert facts["dialog"] is not None and facts["dialog"]["kind"] == "skip"
        assert served.automation(A)["control"]["action"] == "pause"
        assert (A, "resume") not in _entries(served)
        window.press("queue:skip:confirm")
        window.until("the retried continuation", lambda: len(window.posted) >= 3)
        served.wait("the continuation is queued", lambda: (A, "resume") in _entries(served))
        window.page.wait_for_function(
            "() => document.querySelector('#deskPult [data-pult-dialog]') === null")
        paths = [path for path, _body in window.posted]
        assert paths == [CONTROL, PUT, PUT]            # the pause is written once, the put twice
        assert window.facts()["notice"] is None


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_refused_pause_writes_nothing_more_and_says_so(chromium, tmp_path: Path, language):
    words = WORDS[language]
    body = {"error": {"code": "contract_invalid", "message": "refused", "detail": {}}}
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)
        window = _desk(chromium, served, language, before=lambda page: page.route(
            "**" + CONTROL, lambda route: route.fulfill(
                status=422, content_type="application/json", body=json.dumps(body))))
        _skip_ahead(window)
        _wait_notice(window)
        facts = window.facts()
        assert facts["notice"] == words["refused"] and facts["dialog"] is None
        assert [path for path, _body in window.posted] == [CONTROL]
        assert served.queue()["slot"]["run_id"] == A and served.automation(A)["control"] is None
        assert window.errors(ignore=("422",)) == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_refused_continuation_says_the_run_is_paused_and_was_not_queued(
        chromium, tmp_path: Path, language):
    words = WORDS[language]
    body = {"error": {"code": "queue_not_ready", "message": "refused", "detail": {}}}
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)
        window = _desk(chromium, served, language, before=lambda page: page.route(
            "**" + PUT, lambda route: route.fulfill(
                status=409, content_type="application/json", body=json.dumps(body))
            if route.request.method == "POST" else route.continue_()))
        _skip_ahead(window)
        _wait_notice(window)
        facts = window.facts()
        assert facts["notice"] == words["partial"] and facts["dialog"] is None
        assert served.automation(A)["control"]["action"] == "pause"
        assert window.errors(ignore=("409",)) == []
