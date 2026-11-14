"""The fixture launch seam preserves real process behavior without executing synthetic PE."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from conductor.command.adapters.process import CommandSpec, ProcessRunner
from tests import _fakeexe, _fakegh, _fakeprocess


def _built(tmp_path):
    path = _fakeexe.build(tmp_path / "bin", "codex", "_fakecodex")
    assert path is not None
    return path


def _recorder():
    calls = []

    class RecordedPopen:
        def __init__(self, args, *positional, **options):
            calls.append((args, positional, options))

    return RecordedPopen, calls


def test_recording_launch_uses_python_only_for_the_registered_fake(tmp_path):
    fake = _built(tmp_path)
    original, calls = _recorder()
    logical = [str(fake), "--version", "argument with spaces"]
    environment = {"ONLY_THIS_NAME": "fake-value"}
    options = {"cwd": str(tmp_path), "env": environment, "stdin": subprocess.PIPE,
               "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "shell": False}

    _fakeprocess.popen_for(original, windows=True)(logical, **options)

    assert calls == [([sys.executable, *logical], (), options)]
    assert logical == [str(fake), "--version", "argument with spaces"]
    assert calls[0][2]["env"] is environment


def test_recording_launch_refuses_a_tampered_fake_without_native_fallback(tmp_path):
    fake = _built(tmp_path)
    fake.write_bytes(fake.read_bytes() + b"changed")
    original, calls = _recorder()

    with pytest.raises(ValueError, match="changed"):
        _fakeprocess.popen_for(original, windows=True)([str(fake), "--version"])

    assert calls == []


def test_native_not_intercepted_and_a_same_named_unregistered_pin_is_not_a_fake(tmp_path):
    _built(tmp_path)
    original, calls = _recorder()
    # Recording only: never start an unknown/native binary in this guard.
    native = [str(tmp_path / "protected" / "codex.exe"), "--version"]
    _fakeprocess.popen_for(original, windows=True)(native, shell=False)
    assert calls == [(native, (), {"shell": False})]
    assert calls[0][0] is native


def test_non_windows_keeps_the_original_process_constructor():
    original, _calls = _recorder()
    assert _fakeprocess.popen_for(original, windows=False) is original


def test_a_test_that_undoes_its_monkeypatch_leaves_the_launch_seam_standing(monkeypatch):
    """`undo()` reverts what the test patched, not the seam the suite installed for it: a fake
    started after it must still go through the current Python, not the unsigned PE itself."""
    monkeypatch.undo()
    expected = "RegisteredFakePopen" if os.name == "nt" else "Popen"
    assert subprocess.Popen.__name__ == expected


def test_recording_launch_registers_only_an_explicit_verified_copy(tmp_path):
    source = _built(tmp_path)
    copied = tmp_path / "moved.exe"
    copied.write_bytes(source.read_bytes())
    _fakeprocess.register_copy(source, copied)
    original, calls = _recorder()

    _fakeprocess.popen_for(original, windows=True)([str(copied), "--version"])

    assert calls[0][0] == [sys.executable, str(copied), "--version"]


def test_recording_launch_does_not_reinterpret_an_unregistered_copy(tmp_path):
    source = _built(tmp_path)
    copied = tmp_path / "unregistered.exe"
    copied.write_bytes(source.read_bytes())
    original, calls = _recorder()
    logical = [str(copied), "--version"]
    _fakeprocess.popen_for(original, windows=True)(logical)
    assert calls == [(logical, (), {})]


def test_a_modified_copy_cannot_be_registered(tmp_path):
    source = _built(tmp_path)
    copied = tmp_path / "changed.exe"
    copied.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="differs"):
        _fakeprocess.register_copy(source, copied)


@pytest.mark.parametrize("options", [{"shell": True}, {"executable": sys.executable}])
def test_recording_launch_refuses_ambiguous_execution_of_a_registered_fake(tmp_path, options):
    fake = _built(tmp_path)
    original, calls = _recorder()
    with pytest.raises(ValueError, match="no shell"):
        _fakeprocess.popen_for(original, windows=True)([str(fake)], **options)
    assert calls == []


def test_recording_launch_failure_has_no_second_native_attempt(tmp_path):
    fake = _built(tmp_path)
    calls = []

    class RefusedPopen:
        def __init__(self, args, **_options):
            calls.append(args)
            raise OSError("controlled Python launch refusal")

    with pytest.raises(OSError, match="controlled"):
        _fakeprocess.popen_for(RefusedPopen, windows=True)([str(fake), "--version"])
    assert calls == [[sys.executable, str(fake), "--version"]]


def test_direct_subprocess_keeps_logical_argv_stdin_environment_and_cwd(tmp_path, monkeypatch):
    fake = _fakegh.build_executable(tmp_path / "ghbin")
    assert fake is not None
    _fakegh.script(fake.parent, {"pr create": [_fakegh.said("fixture output", exit=7)]})
    monkeypatch.setenv("FAKE_PARENT_ONLY", "not forwarded")
    logical = [str(fake), "pr", "create", "--title", 'spaces and "quotes"']
    payload = "first line\nsecond line\n".encode()

    result = subprocess.run(logical, cwd=tmp_path, env={"FIXTURE_ALLOWED": "fake-value"},
                            input=payload, capture_output=True, timeout=10)

    assert (result.returncode, result.stdout, result.stderr) == (7, b"fixture output", b"")
    row, = _fakegh.calls(fake.parent)
    assert row["argv"] == logical[1:] and row["stdin"] == payload.decode()
    assert row["cwd"] == str(tmp_path)
    assert "FIXTURE_ALLOWED" in row["env_names"] and "FAKE_PARENT_ONLY" not in row["env_names"]


@pytest.mark.parametrize("slow", [False, True])
def test_real_process_runner_keeps_eof_timeout_and_retirement(tmp_path, slow):
    fake = _fakegh.build_executable(tmp_path / "ghbin")
    assert fake is not None
    _fakegh.script(fake.parent, {"pr list": [
        {"stdout": "done", "exit": 0, "sleep": 20 if slow else 0}]})
    (tmp_path / "work").mkdir()
    runner = ProcessRunner(tmp_path, environ={})
    held = []
    spawn = runner._spawn

    def record(spec):
        child = spawn(spec)
        held.append(child)
        return child

    runner._spawn = record
    spec = CommandSpec((str(fake), "pr", "list"), "work", stdin_bytes=b"input until EOF",
                       timeout_seconds=2 if slow else 10)

    outcome = runner.run(spec)

    assert outcome.status == ("timed_out" if slow else "completed")
    assert outcome.exit_code == (None if slow else 0)
    assert outcome.output == (b"" if slow else b"done")
    assert outcome.stdin_state == "delivered" and not outcome.output_truncated
    row, = _fakegh.calls(fake.parent)
    assert row["stdin"] == "input until EOF" and row["argv"] == ["pr", "list"]
    assert runner.active_tokens() == () and len(held) == 1
    child = held[0]
    assert child.proc.poll() is not None
    assert not child._pump.is_alive() and not child._feeder.is_alive()
