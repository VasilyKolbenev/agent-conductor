"""The owned-process runner's core guards: argv, environment, output, timeout.

Each safety rule is exercised as a relation the child itself can witness. The
child is `tests/_fakeproc.py`, driven by environment knobs, so nothing here
depends on an installed tool or on timing luck: output size, exit code, and
running time are all knobs. The shell-injection, environment-leak, output-bound,
and timeout sabotages each pin a relation whose inversion this suite would catch.

Containment of the cwd and process ownership are large enough circuits to live
in their own modules (`test_command_process_containment.py`,
`test_command_process_ownership.py`).
"""
from __future__ import annotations

import json

import pytest

from conductor.command.adapters import process as process_module
from conductor.command.adapters.process import (
    CommandSpec,
    CommandSpecError,
    OwnershipError,
    ProcessRunner,
)

from tests._fakeproc import (
    DUMP_ARGV,
    DUMP_ENV,
    EMIT_BYTES,
    EMIT_STDERR,
    EMIT_STDOUT,
    HEARTBEAT_FILE,
    HEARTBEAT_INTERVAL,
    fake_argv,
    read_int,
    wait_for_int,
)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "project" / "work").mkdir(parents=True)
    return tmp_path / "project"


@pytest.fixture
def runners():
    """A factory that drains every runner it built, so no child outlives a test."""
    built = []

    def make(project_root, **kwargs):
        runner = ProcessRunner(project_root, **kwargs)
        built.append(runner)
        return runner

    yield make
    for runner in built:
        for token in runner.active_tokens():
            try:
                runner.stop(token)
            except OwnershipError:
                pass


def _first_line(output: bytes, prefix: str) -> str:
    line = output.decode("utf-8").splitlines()[0]
    assert line.startswith(prefix), output
    return line[len(prefix):]


# --- structured argv only, shell text stays inert ---


def test_a_structured_argv_runs_the_named_executable_and_returns_its_zero_exit(
        root, runners):
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env={EMIT_STDOUT: "hello"}, timeout_seconds=10))
    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert outcome.output == b"hello\n"
    assert runner.active_tokens() == ()


def test_argv_must_be_a_list_of_strings_never_a_shell_string():
    with pytest.raises(CommandSpecError, match="never a shell string"):
        CommandSpec(argv="echo hi", cwd="work")
    with pytest.raises(CommandSpecError, match="at least the executable"):
        CommandSpec(argv=[], cwd="work")
    with pytest.raises(CommandSpecError, match="must be a string"):
        CommandSpec(argv=["python", 3], cwd="work")
    with pytest.raises(CommandSpecError, match="NUL"):
        CommandSpec(argv=["python", "a\x00b"], cwd="work")


def test_shell_metacharacters_in_an_argument_reach_the_child_as_one_inert_token(
        root, runners):
    """The named injection sabotage: with shell=False the text is data, not code.

    The argument is a space-free Windows-cmd chain: `list2cmdline` would quote a
    payload with spaces (masking the sabotage), so this one carries none, and a
    shell -- and only a shell -- would split it at `&` and create `pwned.txt`.
    Two witnesses, both independent of the runner's own bookkeeping: the child
    echoes its argv (the whole payload arrives as one element, not split), and
    the file the injection would create never appears. Inverting the runner to
    `shell=True` fails both -- the child then sees only `zzz` and pwned.txt lands.
    """
    runner = runners(root)
    work = root / "work"
    payload = "zzz&echo.>pwned.txt"
    assert not (work / "pwned.txt").exists()
    outcome = runner.run(CommandSpec(
        argv=fake_argv(payload), cwd="work", env={DUMP_ARGV: "1"}, timeout_seconds=10))
    echoed = json.loads(_first_line(outcome.output, "ARGV "))
    assert echoed == [payload]
    assert not (work / "pwned.txt").exists()
    assert not (root / "pwned.txt").exists()


def test_child_stderr_is_merged_into_the_captured_output(root, runners):
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work",
        env={EMIT_STDOUT: "on-out", EMIT_STDERR: "on-err"}, timeout_seconds=10))
    assert b"on-out\n" in outcome.output
    assert b"on-err\n" in outcome.output


def test_a_caller_may_bound_stderr_without_admitting_it_as_stdout(root, runners):
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work",
        env={EMIT_STDOUT: "on-out", EMIT_STDERR: "on-err"},
        timeout_seconds=10, separate_stderr=True))

    assert outcome.output == b"on-out\n"
    assert outcome.error_output == b"on-err\n"
    assert outcome.output_truncated is False
    assert outcome.error_truncated is False

    with pytest.raises(CommandSpecError, match="separate_stderr"):
        CommandSpec(argv=fake_argv(), cwd="work", separate_stderr=1)


def test_output_only_reports_whether_it_repeated_an_allowed_env_value(
        root, runners):
    secret = "synthetic-secret-that-is-never-real"
    runner = runners(root, environ={"SECRET": secret})
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env_allow=("SECRET",),
        env={EMIT_STDOUT: secret}, timeout_seconds=10,
        separate_stderr=True))

    assert outcome.output_contains_env_value is True
    assert secret not in repr(outcome)


# --- sanitized environment: an allowlist, never wholesale inheritance ---


def _dumped_env(runner, allow) -> dict:
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env_allow=allow, env={DUMP_ENV: "1"},
        timeout_seconds=10))
    return json.loads(_first_line(outcome.output, "ENV "))


def test_a_referenced_parent_variable_reaches_the_child_only_when_allowlisted(
        root, runners):
    """Before/after over one variable: the allowlist is what admits it, nothing else."""
    runner = runners(root, environ={"V2B_MARKER": "present", "V2B_SECRET_LEAK": "leak"})
    without = _dumped_env(runner, ())
    assert "V2B_MARKER" not in without
    with_marker = _dumped_env(runner, ["V2B_MARKER"])
    assert with_marker["V2B_MARKER"] == "present"


def test_a_parent_secret_outside_the_allowlist_never_reaches_the_child(root, runners):
    """The named environment-leak sabotage, witnessed by the child's own os.environ.

    The parent environment carries a secret the request never allowlists. The
    child dumps the environment it actually received; the secret is absent.
    Inverting the runner to inherit the parent environment wholesale leaks it,
    and this assertion reds.
    """
    runner = runners(root, environ={"V2B_SECRET_LEAK": "leak", "OTHER": "x"})
    received = _dumped_env(runner, ())
    assert "V2B_SECRET_LEAK" not in received
    assert "OTHER" not in received
    # and the allowlist is a genuine door, not a no-op: naming it admits it.
    assert _dumped_env(runner, ["V2B_SECRET_LEAK"])["V2B_SECRET_LEAK"] == "leak"


def test_a_malformed_environment_name_is_refused_at_the_boundary():
    with pytest.raises(CommandSpecError, match="env_allow names an invalid"):
        CommandSpec(argv=["python"], cwd="work", env_allow=["bad-name"])
    with pytest.raises(CommandSpecError, match="env names an invalid"):
        CommandSpec(argv=["python"], cwd="work", env={"1bad": "x"})
    with pytest.raises(CommandSpecError, match="without NUL"):
        CommandSpec(argv=["python"], cwd="work", env={"OK": "a\x00b"})


# --- bounded capture: truncation is stated, never silent ---


def test_output_within_the_bound_is_captured_whole_and_not_flagged(root, runners):
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env={EMIT_BYTES: "128"},
        output_limit=4096, timeout_seconds=10))
    assert outcome.output == b"x" * 128
    assert outcome.output_truncated is False


def test_output_beyond_the_bound_is_truncated_and_flagged_never_silently_dropped(
        root, runners):
    """The named output-bound sabotage, with a before/after over the same child.

    A child that writes far past the bound is captured to exactly the bound and
    the outcome says it was truncated; the parent's buffer never grows past it.
    Raising the bound above the child's output flips the flag off and captures
    the whole stream, so the flag tracks the fact rather than being hardcoded.
    """
    runner = runners(root)
    big = 500_000
    bounded = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env={EMIT_BYTES: str(big)},
        output_limit=1024, timeout_seconds=20))
    assert len(bounded.output) == 1024
    assert bounded.output_truncated is True
    assert bounded.output_limit == 1024
    whole = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env={EMIT_BYTES: str(big)},
        output_limit=big + 16, timeout_seconds=20))
    assert len(whole.output) == big
    assert whole.output_truncated is False


def test_output_limit_must_be_a_positive_byte_count():
    with pytest.raises(CommandSpecError, match="positive integer byte count"):
        CommandSpec(argv=["python"], cwd="work", output_limit=0)
    with pytest.raises(CommandSpecError, match="positive integer byte count"):
        CommandSpec(argv=["python"], cwd="work", output_limit=True)


# --- timeout is its own distinct fact, never a silent success ---


def test_a_child_within_its_timeout_completes_as_its_own_exit(root, runners):
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env={"FAKEPROC_EXIT": "7"}, timeout_seconds=10))
    assert outcome.status == "completed"
    assert outcome.exit_code == 7


def test_a_child_exceeding_its_timeout_is_terminated_and_reported_timed_out(
        root, runners, tmp_path):
    """The named timeout sabotage: the outcome is `timed_out`, and the child dies.

    A heartbeat child runs far longer than the timeout. After `run` returns, the
    outcome is `timed_out` (never `completed`, never a zero exit), and the
    heartbeat is frozen across two reads: the child that was advancing it is
    dead, not merely abandoned. No token is left owned.
    """
    heartbeat = str(tmp_path / "beat")
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work",
        env={HEARTBEAT_FILE: heartbeat, HEARTBEAT_INTERVAL: "0.02"},
        timeout_seconds=0.5))
    assert outcome.status == "timed_out"
    assert outcome.exit_code is None
    advanced = read_int(heartbeat)
    assert advanced is not None and advanced >= 1  # the child was alive and running
    frozen = read_int(heartbeat)
    import time
    time.sleep(0.2)
    assert read_int(heartbeat) == frozen  # and is now dead: nothing still advances it
    assert runner.active_tokens() == ()


def test_wait_for_int_is_a_real_witness(tmp_path):
    """The heartbeat reader must actually observe a written value, not pass vacuously."""
    beat = tmp_path / "beat"
    beat.write_text("5", encoding="ascii")
    assert wait_for_int(beat, timeout=1.0) == 5
    with pytest.raises(AssertionError):
        wait_for_int(tmp_path / "absent", timeout=0.2)


def test_token_entropy_failure_reaps_the_child_and_leaves_no_ownership(
        root, runners, monkeypatch):
    """Mint failure happens after spawn/group creation and must still fail closed."""
    runner = runners(root)
    spawned = []
    real_popen = process_module.subprocess.Popen

    def recording_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(process_module.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(
        process_module.secrets, "token_hex",
        lambda size: (_ for _ in ()).throw(OSError("entropy unavailable")))
    with pytest.raises(OSError, match="entropy unavailable"):
        runner.start(CommandSpec(argv=fake_argv(), cwd="work"))
    assert len(spawned) == 1 and spawned[0].poll() is not None
    assert runner.active_tokens() == ()


def test_cleanup_reaps_directly_even_when_group_termination_raises(
        root, runners, monkeypatch):
    runner = runners(root)
    spawned, groups = [], []
    real_popen = process_module.subprocess.Popen

    class BrokenGroup:
        def __init__(self):
            self.closed = False

        def terminate(self):
            raise OSError("group termination failed")

        def close(self):
            self.closed = True

    def recording_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        spawned.append(proc)
        return proc

    def broken_group(proc):
        group = BrokenGroup()
        groups.append(group)
        return group

    monkeypatch.setattr(process_module.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(process_module._procgroup, "make_group", broken_group)
    monkeypatch.setattr(
        process_module.secrets, "token_hex",
        lambda size: (_ for _ in ()).throw(OSError("entropy unavailable")))
    with pytest.raises(OSError, match="entropy unavailable"):
        runner.start(CommandSpec(argv=fake_argv(), cwd="work"))
    assert len(spawned) == 1 and spawned[0].poll() is not None
    assert len(groups) == 1 and groups[0].closed
    assert runner.active_tokens() == ()
