"""The drain harness's own waits, judged without a subprocess.

`wait_until` is the instrument every drain witness stands on, so its ordering
has to be a claim of its own. A durable fact is written BEFORE the process that
wrote it exits, which makes the order of the two looks the whole matter: a wait
that asks "has it exited?" before "is it true yet?" fails a correct child that
publishes its last state and leaves within one poll. Here the child is a real
`DrainChild` over a scripted stand-in process, so no timing is involved.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from conductor.ownership_errors import OwnerRefused
from tests._drain_harness import DrainChild, stays_true, wait_until

AWAITED = "the ownership head to say closed"


@dataclass
class Timeline:
    """What the scripted child has published and whether it has exited (and how)."""

    published: bool
    exit_code: int | None


class StandInProcess:
    """The one member of `subprocess.Popen` that the waits read."""

    def __init__(self, timeline: Timeline) -> None:
        self.timeline = timeline

    def poll(self) -> int | None:
        return self.timeline.exit_code


def _child(tmp_path: Path, timeline: Timeline) -> DrainChild:
    stderr_path = tmp_path / "child.err"
    stderr_path.write_text("boom", encoding="utf-8")
    return DrainChild(None, StandInProcess(timeline), False, stderr_path)


def test_wait_until_accepts_a_state_published_before_the_child_exited(tmp_path):
    timeline = Timeline(published=True, exit_code=0)
    wait_until(lambda: timeline.published, 1.0, AWAITED, _child(tmp_path, timeline))


def test_wait_until_accepts_a_state_that_appears_together_with_the_exit(tmp_path):
    timeline = Timeline(published=False, exit_code=None)

    def published_yet() -> bool:
        answer = timeline.published
        timeline.published, timeline.exit_code = True, 0
        return answer

    wait_until(published_yet, 1.0, AWAITED, _child(tmp_path, timeline))


def test_wait_until_names_the_exit_when_the_state_never_arrives(tmp_path):
    timeline = Timeline(published=False, exit_code=3)
    with pytest.raises(AssertionError) as caught:
        wait_until(lambda: timeline.published, 1.0, AWAITED, _child(tmp_path, timeline))
    message = str(caught.value)
    assert f"exited with 3 while waiting for {AWAITED}" in message
    assert "boom" in message


def _unreadable_once(then=True, code="transition_conflict"):
    """A predicate that fails to read the ownership head on its first call, as a read
    that lands inside the child's own publication does, and answers `then` after."""
    calls = []

    def predicate():
        calls.append(True)
        if len(calls) == 1:
            raise OwnerRefused(code, "ownership generation does not extend its predecessor")
        return then

    return predicate, calls


def test_wait_until_reads_a_head_that_is_being_published_as_not_yet():
    predicate, calls = _unreadable_once()
    wait_until(predicate, 2.0, AWAITED)
    assert len(calls) == 2


def test_wait_until_times_out_naming_what_it_awaited_when_the_head_never_becomes_readable():
    def always_unreadable():
        raise OwnerRefused("transition_conflict", "ownership file has multiple names")

    with pytest.raises(AssertionError, match=f"timed out after 0.2s waiting for {AWAITED}"):
        wait_until(always_unreadable, 0.2, AWAITED)


def test_wait_until_does_not_hide_an_ownership_refusal_that_is_not_a_transition_conflict():
    predicate, _ = _unreadable_once(code="ownership_lost")
    with pytest.raises(OwnerRefused) as caught:
        wait_until(predicate, 2.0, AWAITED)
    assert caught.value.code == "ownership_lost"


def test_stays_true_skips_a_poll_that_could_not_read_the_head():
    predicate, calls = _unreadable_once()
    stays_true(predicate, 0.3, AWAITED)
    assert len(calls) >= 2


def test_stays_true_still_fails_when_a_readable_poll_says_the_fact_stopped_holding():
    predicate, _ = _unreadable_once(then=False)
    with pytest.raises(AssertionError, match="stopped holding"):
        stays_true(predicate, 0.5, AWAITED)


def test_stays_true_does_not_hide_an_ownership_refusal_that_is_not_a_transition_conflict():
    predicate, _ = _unreadable_once(code="ownership_lost")
    with pytest.raises(OwnerRefused):
        stays_true(predicate, 0.5, AWAITED)
