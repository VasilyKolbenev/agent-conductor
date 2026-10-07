"""The durable boot probe: one appended line per run, honest about what it could not read."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from conductor import boot_probe, boot_witness
from conductor.boot_witness import BootRefused
from tests._boot_world import GUID, OTHER_GUID, counter

WINDOWS = os.name == "nt"
LEGACY = f"windows:{GUID}"


def stand_in(monkeypatch, witness):
    """The reader answers `witness` (a text) or refuses (a BootRefused); diagnostics are fixed."""
    def read():
        if isinstance(witness, BootRefused):
            raise witness
        return witness
    monkeypatch.setattr(boot_probe, "read_witness", read)
    monkeypatch.setattr(boot_probe, "legacy_identity", lambda: LEGACY)
    monkeypatch.setattr(boot_probe, "diagnostics", lambda: {"tick_ms": 1234, "elevated": False})


def run(tmp_path, capsys, *extra):
    log = tmp_path / "probe.jsonl"
    code = boot_probe.main(["--log", str(log), *extra])
    captured = capsys.readouterr()
    return code, captured, log


def lines(log):
    return [json.loads(row) for row in log.read_bytes().splitlines()]


def test_one_run_appends_exactly_one_canonical_line_and_prints_the_same_line(
        tmp_path, capsys, monkeypatch):
    stand_in(monkeypatch, counter(42))
    code, captured, log = run(tmp_path, capsys, "--label", "before restart")
    raw = log.read_bytes()
    assert code == 0 and raw.endswith(b"\n") and raw.count(b"\n") == 1
    record = json.loads(raw)
    assert json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                      ).encode() + b"\n" == raw
    assert captured.out.encode() == raw and captured.err == ""


def test_the_line_names_the_witness_its_parts_the_legacy_string_and_the_diagnostics(
        tmp_path, capsys, monkeypatch):
    stand_in(monkeypatch, counter(42))
    _, _, log = run(tmp_path, capsys, "--label", "before restart")
    record = lines(log)[0]
    assert record["label"] == "before restart" and record["pid"] == os.getpid()
    assert record["boot_witness"] == counter(42) and record["boot_counter"] == 42
    assert record["environment_guid"] == GUID and record["legacy_boot_identity"] == LEGACY
    assert record["diagnostics"] == {"tick_ms": 1234, "elevated": False}
    assert record["error"] is None and record["relation_to_previous"] == "first_record"
    assert record["taken_at"].endswith("+00:00")


def test_a_second_run_appends_and_leaves_the_first_line_byte_for_byte(
        tmp_path, capsys, monkeypatch):
    stand_in(monkeypatch, counter(42))
    _, _, log = run(tmp_path, capsys)
    first = log.read_bytes()
    run(tmp_path, capsys)
    assert log.read_bytes().startswith(first) and len(lines(log)) == 2


def test_each_run_says_how_the_boot_relates_to_the_previous_line(tmp_path, capsys, monkeypatch):
    seen = []
    for witness in (counter(42), counter(42), counter(43), counter(5, OTHER_GUID),
                    counter(4, OTHER_GUID)):
        stand_in(monkeypatch, witness)
        run(tmp_path, capsys)
        seen.append(lines(tmp_path / "probe.jsonl")[-1]["relation_to_previous"])
    assert seen == ["first_record", "same_boot", "restart_proven", "other_scope",
                    "counter_decreased"]


def test_a_reader_that_refuses_is_logged_as_the_measurement_with_its_code_and_exit_3(
        tmp_path, capsys, monkeypatch):
    stand_in(monkeypatch, BootRefused("layout_unknown", "the page is not the documented one"))
    code, _, log = run(tmp_path, capsys, "--label", "odd machine")
    record = lines(log)[0]
    assert code == 3 and record["boot_witness"] is None and record["boot_counter"] is None
    assert record["error"] == {"code": "layout_unknown",
                               "detail": "the page is not the documented one"}
    assert record["relation_to_previous"] == "unmeasured"


def test_a_damaged_previous_line_is_kept_and_reported_not_repaired(tmp_path, capsys, monkeypatch):
    log = tmp_path / "probe.jsonl"
    log.write_bytes(b'{"boot_witness": "half a li')
    stand_in(monkeypatch, counter(42))
    code, _, _ = run(tmp_path, capsys)
    raw = log.read_bytes()
    assert code == 0 and raw.startswith(b'{"boot_witness": "half a li')
    assert lines_after_damage(raw)["relation_to_previous"] == "previous_unreadable"


def lines_after_damage(raw):
    return json.loads(raw.split(b"\n")[-2])


def test_a_log_in_a_missing_directory_is_refused_and_nothing_is_created(
        tmp_path, capsys, monkeypatch):
    stand_in(monkeypatch, counter(42))
    log = tmp_path / "absent" / "probe.jsonl"
    code = boot_probe.main(["--log", str(log)])
    captured = capsys.readouterr()
    assert code == 2 and "directory" in captured.err and not (tmp_path / "absent").exists()


def test_a_run_writes_nothing_but_the_log(tmp_path, capsys, monkeypatch):
    stand_in(monkeypatch, counter(42))
    run(tmp_path, capsys)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["probe.jsonl"]


needs_windows = pytest.mark.skipif(not WINDOWS, reason="reads the real Windows page")


@needs_windows
def test_the_real_probe_logs_the_witness_the_reader_gives_and_real_diagnostics(
        tmp_path, capsys):
    code, _, log = run(tmp_path, capsys, "--label", "real")
    record = lines(log)[0]
    assert code == 0 and record["boot_witness"] == boot_witness.parse(
        record["boot_witness"]).text
    assert record["boot_counter"] == boot_witness.parse(record["boot_witness"]).counter
    diagnostics = record["diagnostics"]
    assert type(diagnostics["tick_ms"]) is int and diagnostics["tick_ms"] > 0
    assert type(diagnostics["unbiased_ms"]) is int and diagnostics["unbiased_ms"] > 0
    assert type(diagnostics["elevated"]) is bool
    assert "system_boot_time_utc" in diagnostics and "hiberboot_enabled" in diagnostics
    assert "process_telemetry_boot_id" in diagnostics


@needs_windows
def test_the_command_the_owner_types_runs_as_a_module_and_appends_to_the_log(tmp_path):
    log = tmp_path / "owner.jsonl"
    done = subprocess.run([sys.executable, "-m", "conductor.boot_probe", "--log", str(log),
                           "--label", "owner command"], capture_output=True, text=True,
                          env=dict(os.environ))
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["label"] == "owner command"
    assert lines(log)[0]["boot_witness"] == json.loads(done.stdout)["boot_witness"]
