"""The project queue on the desk's console, on a real one-project server (spec 4.4.6, 4.4.8).

The server is `desk_queue_rig.py`: a real owner, a real driver, the real queue and its pump, the
real routes; only the adapters and the clock are doubles. A run that keeps the slot waits at its
final gate, so the queue behind it stands still while a test looks at it. What this module holds,
each as a measurement of the page, in Russian and in English:

- the desk READS the queue once at load (one `GET /command/queue`, no write of any kind) and
  draws the block "Project queue" from it: the slot line names the holder, each entry says what
  it will do, in the order the server gave;
- the rail says "Queued - Nth" under the task of an entry that starts on its own and "Waiting for
  your confirmation" under the one whose document changed after it was queued;
- a server that has no such route, or whose answer the desk cannot vouch for, leaves the console
  without the block and the rail in the words of the runs alone;
- a project opened for viewing reads the same queue and says, in the same block, that nothing
  starts there.

A fact and its sentence are read in ONE evaluation (`desk_queue_rig.FACTS`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from browser_tests import desk_queue_rig as rig
from browser_tests.test_desk_status import RAW

RUNS = [rig.Seed("task-a-r1", "task-a", "Alpha", final_gate=True),
        rig.Seed("task-b-r1", "task-b", "Bravo"), rig.Seed("task-c-r1", "task-c", "Charlie")]
WORDS = {
    "en": {"head": "Project queue", "now": "Now: Alpha · holds the slot",
           "b": "1. Bravo · starts on its own", "c": "2. Charlie · starts on its own",
           "queued": ("Queued · #1", "Queued · #2"),
           "a": "Waiting for your decision", "confirm": "Waiting for your confirmation",
           "b_confirm": "1. Bravo · waits for your confirmation: the terms changed"
                        " · noticed · time not given",
           "b_hint": "Give your name above to confirm this entry.",
           "inactive": "Project not active · the queue starts when the project becomes active",
           "inactive_rail": "Queued · starts once the project is active"},
    "ru": {"head": "Очередь проекта", "now": "Сейчас: Alpha · держит слот",
           "b": "1. Bravo · начнётся сама", "c": "2. Charlie · начнётся сама",
           "queued": ("В очереди · 1-я", "В очереди · 2-я"),
           "a": "Ждёт вашего решения", "confirm": "Ждёт вашего подтверждения",
           "b_confirm": "1. Bravo · ждёт вашего подтверждения: условия изменились"
                        " · замечено · время не указано",
           "b_hint": "Укажите имя выше, чтобы подтвердить эту запись.",
           "inactive": "Проект не активен · очередь начнётся, когда проект станет активным",
           "inactive_rail": "В очереди · начнётся после активации"},
}


def _world(tmp_path: Path, *, mode: str = "active"):
    return rig.project(tmp_path, RUNS, mode=mode)


def _queue_two(served: rig.Project) -> None:
    rig.hold(served, "task-a-r1", "g-a")
    rig.enqueue(served, "task-b-r1", "g-b")
    rig.enqueue(served, "task-c-r1", "g-c")


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_desk_reads_the_queue_once_and_the_console_and_the_rail_say_what_it_holds(
        chromium, tmp_path, language):
    words = WORDS[language]
    with _world(tmp_path) as served:
        _queue_two(served)
        window = rig.open_desk(chromium, served, language)
        facts = window.facts()
        assert (facts["block"], facts["head"], facts["now"]) == (True, words["head"], words["now"])
        assert [(row["run"], row["state"], row["tone"], row["text"]) for row in facts["entries"]
                ] == [("task-b-r1", "preauthorized", None, words["b"]),
                      ("task-c-r1", "preauthorized", None, words["c"])]
        assert facts["rail"] == {"task-a": words["a"], "task-b": words["queued"][0],
                                 "task-c": words["queued"][1]}
        assert window.requests("GET", "/command/queue") == 1
        assert [asked for asked in window.asked if asked[0] != "GET"] == []
        assert window.problems == []
        assert not RAW.search(window.page.inner_text("#deskPult")), "a machine word was said"


@pytest.mark.parametrize("language", ["en", "ru"])
def test_an_entry_whose_document_changed_after_it_was_queued_waits_for_confirmation(
        chromium, tmp_path, language):
    words = WORDS[language]
    with _world(tmp_path) as served:
        _queue_two(served)
        rig.publish(served, "task-b-r1", "doc-note")
        facts = rig.open_desk(chromium, served, language).facts()
        assert [(row["run"], row["state"], row["tone"], row["text"]) for row in facts["entries"]
                ] == [("task-b-r1", "confirmation_required", "amber", words["b_confirm"]),
                      ("task-c-r1", "preauthorized", None, words["c"])]
        # The desk has no name for the person, so the entry that waits for a confirmation asks
        # for one beside its facts, in a line of its own: the other entry says nothing more.
        assert [(row["run"], row["hint"]) for row in facts["entries"]] == [
            ("task-b-r1", words["b_hint"]), ("task-c-r1", None)]
        assert (facts["rail"]["task-b"], facts["rail"]["task-c"]) == (
            words["confirm"], words["queued"][1])


#: Answers the desk cannot vouch for: no route, a refusal, a body of another shape.
UNUSABLE = {"a route that is not there": (404, {"error": {"code": "route_not_found"}}),
            "a refusal": (500, {"error": {"code": "store_error"}}),
            "a body of another shape": (200, {"schema_version": 1, "entries": "none"})}


@pytest.mark.parametrize("answer", list(UNUSABLE.values()), ids=list(UNUSABLE))
def test_a_queue_the_desk_cannot_vouch_for_leaves_the_console_without_the_block(
        chromium, tmp_path, answer):
    status, body = answer
    with _world(tmp_path) as served:
        _queue_two(served)
        window = rig.open_desk(chromium, served, "en", before=lambda page: page.route(
            "**/command/queue", lambda route: route.fulfill(
                status=status, content_type="application/json", body=json.dumps(body))))
        facts = window.facts()
        assert (facts["block"], facts["entries"], facts["shell"]) == (False, [], "ready")
        assert facts["rail"]["task-b"] == "Not started"
        if status == 200:       # a browser itself logs a failed request; a judged body is silent
            assert window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_project_opened_for_viewing_reads_the_queue_and_says_nothing_starts_there(
        chromium, tmp_path, language):
    words = WORDS[language]
    with _world(tmp_path, mode="view") as served:
        rig.enqueue(served, "task-b-r1", "g-b")
        facts = rig.open_desk(chromium, served, language).facts()
        assert (facts["block"], facts["now"]) == (True, words["inactive"])
        assert [(row["run"], row["state"]) for row in facts["entries"]] == [
            ("task-b-r1", "preauthorized")]
        assert facts["rail"]["task-b"] == words["inactive_rail"]
