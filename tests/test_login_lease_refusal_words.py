"""The typed login-lease refusal and the runtime's words for it, held at their own seams.

`test_login_lease_refusal_reason` drives a whole dispatch. This file holds the two halves it stands
on: the guard that makes the typed refusal (only for an entry that was refused, never for a refusal
that comes after the task ran), and the runtime's table of words for the closed ids, which is held to
the sources that raise them and never echoes text the adapter wrote.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor import ownership
from conductor.boot_witness import CODES as BOOT_CODES, BootRefused
from conductor.command import failure_reasons
from conductor.command.adapters import login_lifetime, login_refusal
from conductor.command.adapters.process import OwnershipError, ProcessRunner

SENTENCE = "the shared page is not the documented layout of this build"
PRIVATE = "C:\\private\\path"
READER_CODES = ("native_unavailable", "layout_unknown", "partial_read", "value_empty",
                "counter_overflow", "unsupported_platform")
SOURCES = Path(__file__).resolve().parents[1] / "src" / "conductor"


# -- the guard makes the typed refusal only for an entry that was refused ------------------------


class Host:
    """The two things `owned_login_attempt` asks of an adapter, and a body that records it ran."""

    def __init__(self):
        self._workspace = type("Workspace", (), {"root": Path(".")})()
        self.ran = False

    def _signed_in_road(self):
        return "login-home"

    @login_lifetime.owned_login_attempt
    def attempt(self):
        self.ran = True
        return "result"


class Guard:
    """A stand-in for the guard `ProcessRunner.login_write_guard` returns."""

    def __init__(self, entering=None, leaving=None):
        self.entering, self.leaving = entering, leaving

    def __enter__(self):
        if self.entering is not None:
            raise self.entering
        return self

    def __exit__(self, kind, error, traceback):
        if self.leaving is not None:
            raise self.leaving
        return False


def refused(code, cause=None):
    """What the owner raises: a closed code, a sentence of its own, and the reader's refusal."""
    error = ownership.OwnerRefused(code, f"a sentence the owner wrote, with {PRIVATE} in it")
    error.__cause__ = cause
    return error


def converted(owner):
    """What `Owner.borrow_login` makes of a refusal: the adapters' own type, the owner as cause."""
    error = OwnershipError(str(owner))
    error.__cause__ = owner
    return error


def hosted(monkeypatch, guard):
    monkeypatch.setattr(ProcessRunner, "login_write_guard",
                        classmethod(lambda cls, root, home: guard))
    return Host()


@pytest.mark.parametrize("entering, ids", [
    (converted(refused("ownership_unavailable", BootRefused("value_empty", SENTENCE))),
     ("ownership_unavailable", "value_empty")),
    (converted(refused("ownership_unavailable", OSError("the state cannot be read"))),
     ("ownership_unavailable", None)),
    (converted(refused("login_recovery_required")), ("login_recovery_required", None)),
    (refused("recovery_required"), ("recovery_required", None)),
])
def test_a_refusal_at_the_entry_of_the_guard_becomes_the_typed_refusal_and_the_body_never_runs(
        monkeypatch, entering, ids):
    host = hosted(monkeypatch, Guard(entering=entering))
    with pytest.raises(login_lifetime.LoginLeaseRefused) as caught:
        host.attempt()
    assert (caught.value.code, caught.value.reader) == ids
    assert isinstance(caught.value, OwnershipError), "a caller that catches the old type still does"
    assert caught.value.__cause__ is entering
    assert not host.ran
    assert PRIVATE not in str(caught.value) and SENTENCE not in str(caught.value)


@pytest.mark.parametrize("entering", [
    OwnershipError("activated project needs a registered live owner"),
    converted(refused("a_code_the_run_has_no_words_for")),
    refused("a_code_the_run_has_no_words_for"),
    ValueError("not an ownership refusal at all"),
])
def test_an_entry_refusal_without_a_closed_code_propagates_unchanged(monkeypatch, entering):
    host = hosted(monkeypatch, Guard(entering=entering))
    with pytest.raises(type(entering)) as caught:
        host.attempt()
    assert caught.value is entering
    assert not host.ran


def test_a_refusal_raised_when_the_guard_closes_is_not_made_a_refusal_before_the_task(
        monkeypatch):
    leaving = converted(refused("login_recovery_required"))
    host = hosted(monkeypatch, Guard(leaving=leaving))
    with pytest.raises(OwnershipError) as caught:
        host.attempt()
    assert caught.value is leaving, "the task ran; its result is lost, which is not a refusal"
    assert not isinstance(caught.value, login_lifetime.LoginLeaseRefused)
    assert host.ran


# -- the words are the runtime's own and are held to the sources that raise the codes ------------


def test_every_code_the_lease_road_may_say_has_words_and_is_raised_by_the_owner_sources():
    owner = "\n".join((SOURCES / name).read_text(encoding="utf-8")
                      for name in ("ownership.py", "ownership_login.py", "ownership_records.py",
                                   "ownership_boot.py", "ownership_transition.py"))
    assert set(failure_reasons.LEASE_WORDS) == set(login_refusal.LEASE_CODES)
    assert set(failure_reasons.READER_WORDS) == set(login_refusal.READER_CODES)
    for code in login_refusal.LEASE_CODES:
        assert f'OwnerRefused("{code}"' in owner, f"{code} is raised nowhere in the owner sources"
    assert set(login_refusal.READER_CODES) <= BOOT_CODES
    assert set(login_refusal.READER_CODES) == set(READER_CODES)


@pytest.mark.parametrize("reader", [None, *READER_CODES])
@pytest.mark.parametrize("code", sorted(login_refusal.LEASE_CODES))
def test_the_sentence_an_adapter_writes_is_read_back_in_words_that_carry_its_ids(code, reader):
    sentence = login_refusal.sentence(code, reader)
    said = failure_reasons.reason_words(sentence)
    assert said is not None and code in said and (reader is None or reader in said), said
    assert "\\" not in said and "/" not in said


@pytest.mark.parametrize("sentence", [
    "the shared login lease was refused (C:\\Users\\someone\\auth), so no task was spawned",
    "the shared login lease was refused (ownership_unavailable: a made-up reader), "
    "so no task was spawned",
    "the shared login lease was refused (a_code_nobody_raises), so no task was spawned",
    "the shared login lease was refused (ownership_unavailable: a_reader_nobody_raises), "
    "so no task was spawned",
])
def test_a_sentence_with_an_id_outside_the_closed_lists_never_has_that_text_echoed(sentence):
    said = failure_reasons.reason_words(sentence)
    assert said is None or ("Users" not in said and "made-up" not in said
                            and "nobody_raises" not in said), said
    if "ownership_unavailable: a_reader" in sentence:
        assert said is not None and "ownership_unavailable" in said, "the known code is kept"
