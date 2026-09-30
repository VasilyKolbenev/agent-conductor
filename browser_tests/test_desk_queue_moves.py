"""A person's order and withdraw on the console's queue block, on a real one-project server
(spec 4.4.5, 4.4.8): the real routes, the real queue, the real pump; only adapters and clock are
doubles (`desk_queue_rig.py`). A run that keeps the slot waits at its final gate, so the queue
behind it stands still. What this module holds, each as a measurement of the page, in Russian and
English:

- a step up or down writes `POST /command/queue/order` with the revision the desk READ and the
  full list of the visible entries in their new places, and the console and the rail are drawn from
  the answer -- no second read, no second write; the first entry has no "up" and the last no
  "down";
- "Remove from the queue" writes `POST /command/queue/<run_id>/withdraw` with an empty body, and the
  rail then says the task is not started;
- another window moved the queue first: the write is refused `queue_changed`, the console says it
  in the catalogue's words and reads the queue again, so what stands is the other window's order;
- an answer that is lost is settled by reading the queue: a write that landed says nothing, one that
  did not says the change could not be confirmed and shows what the server holds;
- while a write is out no control of the block can be pressed again;
- in a project opened for viewing the same controls work; no control is under 44 px.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from browser_tests import desk_queue_rig as rig
from browser_tests.test_desk_queue import RUNS, WORDS

FOUR = [*RUNS, rig.Seed("task-d-r1", "task-d", "Delta")]
CHANGED = {
    "en": "The queue changed while you were looking at it. Nothing was reordered; look at it "
          "again.",
    "ru": "Очередь изменилась, пока вы её смотрели. Ничего не переставлено; посмотрите её заново."}
UNSURE = {
    "en": "The change could not be confirmed. This is the queue the server holds.",
    "ru": "Изменение не удалось подтвердить. Здесь — очередь, как её хранит сервер."}
MOVE = {"en": {"up": "Move up", "down": "Move down", "withdraw": "Remove from the queue"},
        "ru": {"up": "Выше", "down": "Ниже", "withdraw": "Убрать из очереди"}}
ORDER, PATH = "/command/queue/order", "/command/queue/{}/withdraw"
B, C, D = "task-b-r1", "task-c-r1", "task-d-r1"


def _three(served: rig.Project) -> None:
    """The slot is held; Bravo, Charlie and Delta wait behind it, each preauthorized."""
    rig.hold(served, "task-a-r1", "g-a")
    for run, grant in ((B, "g-b"), (C, "g-c"), (D, "g-d")):
        rig.enqueue(served, run, grant)


def _order(served: rig.Project) -> list[str]:
    return [row["run_id"] for row in served.queue()["entries"]]


def _wait_order(window: rig.Window, expected: list[str]) -> None:
    window.page.wait_for_function(
        """(ids) => [...document.querySelectorAll("#deskPult .desk-queue__entry")]
          .map((row) => row.dataset.runId).join() === ids.join()""", arg=expected, timeout=8000)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_step_writes_the_order_with_the_revision_read_and_the_console_is_drawn_from_the_answer(
        chromium, tmp_path: Path, language):
    words = MOVE[language]
    with rig.project(tmp_path, FOUR) as served:
        _three(served)
        window = rig.open_desk(chromium, served, language)
        opening = window.facts()
        assert window.order() == [B, C, D]
        first, last = opening["entries"][0]["buttons"], opening["entries"][2]["buttons"]
        assert [(one["key"], one["label"], one["disabled"]) for one in first] == [
            (f"queue:up:{B}", words["up"], True), (f"queue:down:{B}", words["down"], False),
            (f"queue:withdraw:{B}", words["withdraw"], False)]
        assert [(one["key"], one["disabled"]) for one in last][:2] == [
            (f"queue:up:{D}", False), (f"queue:down:{D}", True)]
        assert all(one["size"][1] >= 44 and one["size"][0] >= 44
                   for row in opening["entries"] for one in row["buttons"])
        window.press(f"queue:down:{B}")
        _wait_order(window, [C, B, D])
        assert window.page.evaluate(       # the press keeps the keyboard's place across the redraw
            "() => document.activeElement.dataset.focusKey") == f"queue:down:{B}"
        window.press(f"queue:up:{D}")
        _wait_order(window, [C, D, B])
        facts = window.facts()
        assert window.posted == [
            (ORDER, {"expected_revision": 3, "run_ids": [C, B, D]}),
            (ORDER, {"expected_revision": 4, "run_ids": [C, D, B]})]
        assert _order(served) == [C, D, B] and facts["notice"] is None
        assert facts["rail"] == {"task-a": WORDS[language]["a"],
                                 "task-c": WORDS[language]["queued"][0],
                                 "task-d": _nth(language, 2), "task-b": _nth(language, 3)}
        assert window.requests("GET", "/command/queue") == 1
        assert window.errors() == []


def _nth(language: str, place: int) -> str:
    return f"Queued · #{place}" if language == "en" else f"В очереди · {place}-я"


def _said(language: str, place: int, title: str) -> str:
    """The row of an entry that starts on its own."""
    return (f"{place}. {title} · starts on its own" if language == "en"
            else f"{place}. {title} · начнётся сама")


@pytest.mark.parametrize("language", ["en", "ru"])
def test_withdraw_removes_the_entry_with_an_empty_body_and_the_rail_says_not_started(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, FOUR) as served:
        _three(served)
        window = rig.open_desk(chromium, served, language)
        window.press(f"queue:withdraw:{B}")
        _wait_order(window, [C, D])
        facts = window.facts()
        assert window.posted == [(PATH.format(B), {})]
        assert _order(served) == [C, D] and facts["notice"] is None
        assert [row["text"] for row in facts["entries"]] == [
            _said(language, 1, "Charlie"), _said(language, 2, "Delta")]
        assert facts["rail"]["task-b"] == ("Not started" if language == "en" else "Не запущена")
        assert facts["rail"]["task-c"] == _nth(language, 1)
        assert facts["rail"]["task-d"] == _nth(language, 2)
        assert window.errors() == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_stale_revision_says_the_queue_changed_and_the_console_reads_the_queue_again(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, FOUR) as served:
        _three(served)
        window = rig.open_desk(chromium, served, language)
        status, payload = served.call("POST", ORDER, {"expected_revision": 3,
                                                       "run_ids": [D, B, C]})
        assert status == 200, payload
        window.press(f"queue:down:{B}")
        _wait_order(window, [D, B, C])
        facts = window.facts()
        assert window.posted == [(ORDER, {"expected_revision": 3, "run_ids": [C, B, D]})]
        assert facts["notice"] == CHANGED[language]
        assert _order(served) == [D, B, C]
        assert window.requests("GET", "/command/queue") == 2
        assert window.errors(ignore=("409",)) == []


def _lose(land: bool):
    """A route handler that loses the answer of the order write, after it landed or before."""
    def handle(route) -> None:
        if land:
            route.fetch()
        route.abort()
    return handle


@pytest.mark.parametrize("language", ["en", "ru"])
def test_an_answer_lost_after_the_write_landed_is_settled_by_the_read_and_says_nothing(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, FOUR) as served:
        _three(served)
        window = rig.open_desk(chromium, served, language, before=lambda page: page.route(
            "**" + ORDER, _lose(True)))
        window.press(f"queue:down:{B}")
        _wait_order(window, [C, B, D])
        assert window.facts()["notice"] is None and _order(served) == [C, B, D]
        assert window.requests("GET", "/command/queue") == 2
        assert len(window.posted) == 1


@pytest.mark.parametrize("language", ["en", "ru"])
def test_an_answer_lost_before_the_write_landed_says_the_change_could_not_be_confirmed(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, FOUR) as served:
        _three(served)
        window = rig.open_desk(chromium, served, language, before=lambda page: page.route(
            "**" + ORDER, _lose(False)))
        window.press(f"queue:down:{B}")
        window.page.wait_for_function(
            "() => document.querySelector('#deskPult [data-pult-notice]') !== null")
        facts = window.facts()
        assert facts["notice"] == UNSURE[language]
        assert window.order() == [B, C, D] and _order(served) == [B, C, D]
        assert window.requests("GET", "/command/queue") == 2


def test_while_a_write_is_out_no_control_of_the_block_can_be_pressed_again(
        chromium, tmp_path: Path):
    held = []
    with rig.project(tmp_path, FOUR) as served:
        _three(served)
        window = rig.open_desk(chromium, served, "en", before=lambda page: page.route(
            "**" + ORDER, lambda route: held.append(route)))
        window.press(f"queue:down:{B}")
        window.page.wait_for_function(       # "Remove" is unavailable only while a write is out
            "() => document.querySelector('#deskPult "
            "[data-focus-key=\"queue:withdraw:task-b-r1\"][aria-disabled=\"true\"]') !== null")
        window.until("the order write is held at the route", lambda: held)
        locked = window.facts()
        assert all(one["disabled"] for row in locked["entries"] for one in row["buttons"])
        window.press(f"queue:down:{C}", force=True)   # a second press while one is out: ignored
        window.page.wait_for_timeout(200)
        assert len(held) == 1
        held[0].continue_()
        _wait_order(window, [C, B, D])
        head = window.facts()["entries"][0]["buttons"]
        assert [one["disabled"] for one in head] == [True, False, False]   # "up" at the head
        assert len(window.posted) == 1 and window.errors() == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_in_a_project_opened_for_viewing_the_same_controls_order_and_withdraw(
        chromium, tmp_path: Path, language):
    with rig.project(tmp_path, FOUR, mode="view") as served:
        for run, grant in ((B, "g-b"), (C, "g-c"), (D, "g-d")):
            rig.enqueue(served, run, grant)
        window = rig.open_desk(chromium, served, language)
        assert window.facts()["now"] == WORDS[language]["inactive"]
        window.press(f"queue:down:{B}")
        _wait_order(window, [C, B, D])
        window.press(f"queue:withdraw:{C}")
        _wait_order(window, [B, D])
        assert _order(served) == [B, D] and window.errors() == []
        assert [path for path, _body in window.posted] == [ORDER, PATH.format(C)]
