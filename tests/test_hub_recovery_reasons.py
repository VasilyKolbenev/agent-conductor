"""The reason a failed recovery carries is read from the REAL refusals, never from a copy (D-H11).

`tests/test_hub_owner_command.py` says what the hub does with a sentence. This file says that the
real commands still print that sentence: each situation below is made on disk in the fake boot
world (the one seam `ownership_boot.current_boot`, a model of a restart, never the OS), the real
`conduct ownership recover` / `recover-login` entry point refuses, and the hub's reader maps the
first line it printed. A rewording of either command that stops the table from matching fails here,
instead of turning an instruction to prepare into advice to restart.
"""
from __future__ import annotations

import pytest

from conductor import __main__ as cli, boot_witness
from conductor.hub import refusals
from tests._boot_world import counter, measure
from tests.test_login_recovery_prepare import legacy_lease
from tests.test_login_scope_change import counter_lease_of_a, receipt_in_a
from tests.test_project_recovery_prepare import abandoned_legacy
from tests.test_project_scope_change import NOW_A, NOW_B, counter_record_of_a, prepared_in_a


@pytest.fixture
def owner_ops():
    """The module under test, imported when a test runs (so a missing module fails that test)."""
    from conductor.hub import owner_ops as module
    return module


def _unmeasurable():
    raise boot_witness.BootRefused("native_unavailable", "the reader failed")


# -- the six situations of a project record, each left on disk and then met by the machine -------

def _project_same_boot(root, monkeypatch):
    abandoned_legacy(root, boot=NOW_A)
    measure(monkeypatch, NOW_A)


def _project_legacy_unprepared(root, monkeypatch):
    abandoned_legacy(root)
    measure(monkeypatch, counter(43))


def _project_prepared_in_another_scope(root, monkeypatch):
    prepared_in_a(root, monkeypatch)
    measure(monkeypatch, NOW_B)


def _project_counter_of_another_scope(root, monkeypatch):
    counter_record_of_a(root, monkeypatch)
    measure(monkeypatch, NOW_B)


def _project_counter_fell(root, monkeypatch):
    abandoned_legacy(root, boot=NOW_A)
    measure(monkeypatch, counter(41))


def _project_unmeasurable(root, monkeypatch):
    abandoned_legacy(root, boot=NOW_A)
    measure(monkeypatch, _unmeasurable)


# -- and the same six for a shared login lease ---------------------------------------------------

def _login_same_boot(root, monkeypatch):
    home, _box, _record = legacy_lease(root, monkeypatch, boot=NOW_A)
    measure(monkeypatch, NOW_A)
    return home


def _login_legacy_unprepared(root, monkeypatch):
    home, _box, _record = legacy_lease(root, monkeypatch)
    measure(monkeypatch, counter(43))
    return home


def _login_prepared_in_another_scope(root, monkeypatch):
    home, _box, _record = receipt_in_a(root, monkeypatch)
    measure(monkeypatch, NOW_B)
    return home


def _login_counter_of_another_scope(root, monkeypatch):
    home, _box, _record = counter_lease_of_a(root, monkeypatch)
    measure(monkeypatch, NOW_B)
    return home


def _login_counter_fell(root, monkeypatch):
    home, _box, _record = legacy_lease(root, monkeypatch, boot=NOW_A)
    measure(monkeypatch, counter(41))
    return home


def _login_unmeasurable(root, monkeypatch):
    home, _box, _record = legacy_lease(root, monkeypatch, boot=NOW_A)
    measure(monkeypatch, _unmeasurable)
    return home


#: (situation, makes it, the word the hub must read from the real refusal)
SITUATIONS = [
    ("same_boot", _project_same_boot, _login_same_boot, "restart_needed"),
    ("legacy_unprepared", _project_legacy_unprepared, _login_legacy_unprepared, "prepare_needed"),
    ("prepared_in_another_scope", _project_prepared_in_another_scope,
     _login_prepared_in_another_scope, "other_environment"),
    ("counter_of_another_scope", _project_counter_of_another_scope,
     _login_counter_of_another_scope, "other_environment"),
    ("counter_fell", _project_counter_fell, _login_counter_fell, "not_proven"),
    ("unmeasurable", _project_unmeasurable, _login_unmeasurable, "not_proven")]


def _refusal_line(capsys, step, root, monkeypatch, make_project, make_login):
    """What the real command printed first when it refused this situation, and its exit code."""
    root.mkdir()
    if step == "recover":
        make_project(root, monkeypatch)
        argv = ["ownership", "recover", "--dir", str(root)]
    else:
        argv = ["ownership", "recover-login", "--auth-home", str(make_login(root, monkeypatch))]
    capsys.readouterr()
    code = cli.main(argv)
    captured = capsys.readouterr()
    assert captured.out == "", "a refused recovery prints no result"
    return code, captured.err


@pytest.mark.parametrize("step", ["recover", "recover_login"])
@pytest.mark.parametrize(("situation", "make_project", "make_login", "word"), SITUATIONS,
                         ids=[row[0] for row in SITUATIONS])
def test_the_real_refusal_of_each_situation_reads_as_the_reason_the_hub_gives_it(
        owner_ops, tmp_path, monkeypatch, capsys, step, situation, make_project, make_login, word):
    code, error = _refusal_line(capsys, step, tmp_path / "subject", monkeypatch, make_project,
                                make_login)
    assert code == 1, error
    restart_code = {"recover": "recovery_required",
                    "recover_login": "login_recovery_required"}[step]
    assert owner_ops.refusal_code(error, refusals.OPERATION_CODES_BY_STEP[step]) == restart_code
    assert owner_ops.restart_reason(error, step) == word, error


@pytest.mark.parametrize("step", ["recover", "recover_login"])
def test_the_four_real_kinds_of_refusal_are_four_words_and_a_preparation_is_never_a_restart(
        owner_ops, tmp_path, monkeypatch, capsys, step):
    found = {}
    for number, (situation, make_project, make_login, _word) in enumerate(SITUATIONS):
        monkeypatch.undo()                       # each situation measures the machine afresh
        _code, error = _refusal_line(capsys, step, tmp_path / f"subject-{number}", monkeypatch,
                                     make_project, make_login)
        found[situation] = owner_ops.restart_reason(error, step)
    assert set(found.values()) == {"restart_needed", "prepare_needed", "other_environment",
                                   "not_proven"}
    assert found["legacy_unprepared"] == "prepare_needed"
    assert found["prepared_in_another_scope"] == found["counter_of_another_scope"] == (
        "other_environment")
    assert [name for name, word in found.items() if word == "restart_needed"] == ["same_boot"]


@pytest.mark.parametrize("step", ["recover", "recover_login"])
def test_the_real_sentences_tell_a_preparation_from_a_restart_only_through_the_stem_table(
        owner_ops, tmp_path, monkeypatch, capsys, step):
    """Without the stems a preparation and an environment change read as the neutral word.

    This is the witness that the two tests above observe the REAL sentences: take the table away
    and the sentences of a legacy record and of another environment lose their word.
    """
    sentences = {}
    for number, (situation, make_project, make_login, _word) in enumerate(SITUATIONS[1:3]):
        monkeypatch.undo()
        _code, error = _refusal_line(capsys, step, tmp_path / f"subject-{number}", monkeypatch,
                                     make_project, make_login)
        sentences[situation] = error
    assert owner_ops.restart_reason(sentences["legacy_unprepared"], step) == "prepare_needed"
    monkeypatch.setattr(owner_ops, "_RESTART_STEMS", ())
    assert [owner_ops.restart_reason(text, step) for text in sentences.values()] == [
        "not_proven", "not_proven"]
