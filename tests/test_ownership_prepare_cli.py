"""`conduct ownership recover --prepare-restart`: a preparation is visible and releases nothing."""
from __future__ import annotations

import json

import pytest

from conductor import __main__ as cli, ownership_records as records
from tests._boot_world import counter, measure
from tests.test_login_recovery_prepare import legacy_lease, receipt_path
from tests.test_command_task_store import durable_bytes
from tests.test_project_recovery_prepare import abandoned_legacy, tree


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("operation", ["status", "activate", "rollback"])
def test_the_flag_is_refused_on_every_operation_but_the_two_recoveries_and_writes_nothing(
        tmp_path, capsys, monkeypatch, operation):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    before = tree(tmp_path)
    code, out, err = run(capsys, "ownership", operation, "--prepare-restart", "--dir",
                         str(tmp_path))
    assert code == 1 and out == "" and "only for recover" in err
    assert tree(tmp_path) == before


def test_preparing_a_project_prints_the_record_and_says_ownership_is_not_released(
        tmp_path, capsys, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    code, out, err = run(capsys, "ownership", "recover", "--prepare-restart", "--dir",
                         str(tmp_path))
    result = json.loads(out)
    assert code == 0 and result["state"] == "recovery_prepared" and result["released"] is False
    assert result["created"] is True and result["prepared_boot"] == counter(42)
    assert result["generation"] == records.chain(tmp_path)["generation"]
    assert "NOT released" in err and "Restart" in err and "ownership recover" in err
    assert str(tmp_path) in err


def test_a_repeated_preparation_says_it_was_already_prepared_and_writes_nothing(
        tmp_path, capsys, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    run(capsys, "ownership", "recover", "--prepare-restart", "--dir", str(tmp_path))
    before = tree(tmp_path)
    measure(monkeypatch, counter(77))
    code, out, err = run(capsys, "ownership", "recover", "--prepare-restart", "--dir",
                         str(tmp_path))
    assert code == 0 and json.loads(out)["created"] is False
    assert "already prepared" in err and "NOT released" in err
    assert tree(tmp_path) == before


def test_a_plain_recover_of_an_old_record_writes_nothing_and_names_the_next_command(
        tmp_path, capsys, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(43))
    before = tree(tmp_path)
    code, out, err = run(capsys, "ownership", "recover", "--dir", str(tmp_path))
    assert code == 1 and out == "" and "--prepare-restart" in err
    assert tree(tmp_path) == before


def test_status_shows_the_prepared_phase_and_the_recovery_after_the_restart_completes_it(
        tmp_path, capsys, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    run(capsys, "ownership", "recover", "--prepare-restart", "--dir", str(tmp_path))
    assert json.loads(run(capsys, "ownership", "status", "--dir", str(tmp_path))[1])[
        "state"] == "recovery_prepared"
    measure(monkeypatch, counter(43))
    code, out, _ = run(capsys, "ownership", "recover", "--dir", str(tmp_path))
    assert code == 0 and json.loads(out)["phase"] == "recovered"


def test_preparing_a_login_prints_the_receipt_facts_and_says_the_lease_is_not_released(
        tmp_path, capsys, monkeypatch):
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    code, out, err = run(capsys, "ownership", "recover-login", "--prepare-restart",
                         "--auth-home", str(home))
    result = json.loads(out)
    assert code == 0 and result["state"] == "recovery_prepared" and result["released"] is False
    assert result["created"] is True and receipt_path(box, record).is_file()
    assert (box / "active.json").is_file()
    assert "NOT released" in err and "recover-login" in err and str(home) in err


def test_a_repeated_login_preparation_and_a_plain_recover_write_nothing_new(
        tmp_path, capsys, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(43))
    before = durable_bytes(box)
    code, out, err = run(capsys, "ownership", "recover-login", "--auth-home", str(home))
    assert code == 1 and out == "" and "--prepare-restart" in err and durable_bytes(box) == before
    measure(monkeypatch, counter(42))
    run(capsys, "ownership", "recover-login", "--prepare-restart", "--auth-home", str(home))
    after = durable_bytes(box)
    measure(monkeypatch, counter(90))
    code, out, err = run(capsys, "ownership", "recover-login", "--prepare-restart",
                         "--auth-home", str(home))
    assert code == 0 and json.loads(out)["created"] is False and "already prepared" in err
    assert durable_bytes(box) == after


def test_recover_login_after_the_restart_completes_it_through_the_command(
        tmp_path, capsys, monkeypatch):
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    run(capsys, "ownership", "recover-login", "--prepare-restart", "--auth-home", str(home))
    measure(monkeypatch, counter(43))
    code, out, _ = run(capsys, "ownership", "recover-login", "--auth-home", str(home))
    assert code == 0 and json.loads(out)["state"] == "recovered"
    assert (box / f"recovered-{record['nonce']}.json").is_file()


def test_the_flag_without_a_login_directory_is_refused_for_recover_login(
        tmp_path, capsys, monkeypatch):
    measure(monkeypatch, counter(42))
    code, out, err = run(capsys, "ownership", "recover-login", "--prepare-restart")
    assert code == 1 and out == "" and "requires --auth-home" in err
