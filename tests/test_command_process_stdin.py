"""The runner's stdin channel: a bounded payload, an EOF, and no way back out.

This is its own module for the reason the containment and ownership circuits
are: it is one closed question with several exits, and every one of them has to
be driven through a REAL child. The child is `tests/_fakeproc.py`, which reports
what it read as a LENGTH and a DIGEST rather than as bytes -- a fake that echoed
the payload would make every leak assertion below pass by accident, because the
payload would then be legitimately present in the child's own output.

Three claims, and the third is the one that pays for the field:

- the child reads exactly the bytes it was handed, and then sees EOF. Without
  the EOF a print-mode child waits for more input until its own timeout, which
  is an expensive way to say nothing;
- the writer closes on all four exits -- completed, early exit, timed out,
  stopped -- and none of them leaves a thread holding the child's input open;
- `None` is not a new spawn shape. It is the DEVNULL spawn every provider had
  before this field existed, and the providers that pass nothing must not be
  able to tell that the field was added.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from conductor.command.adapters.harness_workspace import INSTRUCTION_LIMIT
from conductor.command.adapters.process import (
    STDIN_LIMIT,
    CommandSpec,
    CommandSpecError,
    OwnershipError,
    ProcessRunner,
)

from tests._fakeproc import (
    DUMP_ARGV,
    DUMP_CWD,
    DUMP_ENV,
    DUMP_STDIN,
    EXIT,
    SLEEP,
    fake_argv,
)

#: Prose an operator could really have written, so a leak assertion is looking
#: for something a human would recognise in a log rather than for `b"x" * n`.
INSTRUCTION = b"Add the missing guard and prove it with one failing test."


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


def _reported(outcome) -> dict:
    """What the child says it read, taken from its own output."""
    for line in outcome.output.decode("utf-8").splitlines():
        if line.startswith("STDIN "):
            return json.loads(line[len("STDIN "):])
    raise AssertionError(f"the child reported no stdin read: {outcome.output!r}")


def _spec(root, payload, **changes):
    values = {
        "argv": fake_argv(), "cwd": "work",
        "env": {DUMP_STDIN: "1"}, "timeout_seconds": 20,
        "stdin_bytes": payload,
    }
    values.update(changes)
    return CommandSpec(**values)


# --- what the child receives -------------------------------------------------


def test_the_child_reads_exactly_the_payload_and_then_reaches_end_of_input(
        root, runners):
    """A blocking read to EOF returns the whole payload and returns AT ALL.

    The child's read cannot finish unless the parent closed the stream, so this
    test proves the EOF as much as it proves the bytes: a writer that wrote
    everything and never closed would leave the child blocked here and this
    would come back `timed_out`.
    """
    outcome = runners(root).run(_spec(root, INSTRUCTION))

    assert outcome.status == "completed", outcome.status
    assert _reported(outcome) == {
        "bytes": len(INSTRUCTION),
        "sha256": hashlib.sha256(INSTRUCTION).hexdigest()}


def test_a_payload_at_the_ceiling_arrives_whole_rather_than_in_one_write(
        root, runners):
    """The loop, not the single `write`, is what makes a large payload arrive.

    The child is spawned unbuffered, so a raw stream may accept fewer bytes than
    it was offered. A writer that called `write` once and trusted it would
    deliver a truncated instruction and nothing anywhere would say so -- the
    child would simply have been asked to do something else.
    """
    payload = (INSTRUCTION * (STDIN_LIMIT // len(INSTRUCTION) + 1))[:STDIN_LIMIT]

    outcome = runners(root).run(_spec(root, payload))

    assert outcome.status == "completed", outcome.status
    assert _reported(outcome) == {
        "bytes": STDIN_LIMIT, "sha256": hashlib.sha256(payload).hexdigest()}


def test_an_empty_payload_is_an_open_stream_at_end_of_input_not_no_stream(
        root, runners):
    """`b""` and `None` are different instructions to this runner.

    Both leave the child reading nothing, and they are still not the same: one
    opens a pipe and closes it, the other never opens one. The difference is
    invisible from inside a child that only reads, which is why it is stated
    here rather than left for a reader to assume either way.
    """
    outcome = runners(root).run(_spec(root, b""))

    assert outcome.status == "completed"
    assert _reported(outcome) == {
        "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}


def test_passing_nothing_leaves_the_devnull_spawn_every_provider_already_had(
        root, runners):
    """The regression that matters to the three providers that pass no payload.

    They must not be able to observe that this field was added. A child reading
    stdin under `None` sees end-of-input immediately, exactly as it did when the
    spawn had no choice about it.
    """
    outcome = runners(root).run(_spec(root, None))

    assert outcome.status == "completed"
    assert _reported(outcome) == {
        "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}


# --- the writer closes on every exit -----------------------------------------


def test_a_child_that_exits_without_reading_does_not_hang_the_writer(
        root, runners):
    """The early exit. The pipe breaks under the writer, and that is not an error.

    A run whose child refused its input still has an account of itself -- its
    exit code and its output -- and that account is the run's, not the writer's.
    A writer that raised here would replace a real exit code with a traceback.
    """
    outcome = runners(root).run(_spec(
        root, INSTRUCTION * 200, env={EXIT: "7"}))

    assert outcome.status == "completed"
    assert outcome.exit_code == 7


def test_a_child_that_never_reads_and_never_exits_still_times_out(root, runners):
    """The timeout exit, with a payload still queued behind it.

    `finish` joins the writer, so a writer that could block forever would turn
    every timeout into a hang -- the runner would stop being able to report the
    one status it exists to report.
    """
    outcome = runners(root).run(_spec(
        root, INSTRUCTION * 200, env={SLEEP: "30"}, timeout_seconds=2))

    assert outcome.status == "timed_out"
    assert outcome.exit_code is None


def test_a_stopped_child_releases_its_writer_and_leaks_no_token(root, runners):
    """The stop exit, on the asynchronous road that never calls `run`."""
    runner = runners(root)
    owned = runner.start(_spec(
        root, INSTRUCTION * 200, env={SLEEP: "30"}, timeout_seconds=None))

    outcome = runner.stop(owned.token)

    assert outcome.status == "stopped"
    assert outcome.exit_code is None
    assert runner.active_tokens() == ()


# --- what may never carry the payload ----------------------------------------


REFUSED = (
    ("too large", b"z" * (STDIN_LIMIT + 1)),
    ("NUL inside", INSTRUCTION + b"\x00" + INSTRUCTION),
    ("text, not bytes", "an instruction as str"),
    ("a bytearray", bytearray(INSTRUCTION)),
    ("a memoryview", memoryview(INSTRUCTION)),
)


@pytest.mark.parametrize("label,payload", REFUSED, ids=[row[0] for row in REFUSED])
def test_an_inadmissible_payload_is_refused_before_any_child_exists(
        root, runners, label, payload):
    """Construction refuses, so no child was ever handed the workspace.

    The order is the claim. A payload judged after the spawn is a payload judged
    when the child already has the work tree, the environment and a process
    group -- and refusing then is cleanup, not a refusal.
    """
    runner = runners(root)

    with pytest.raises(CommandSpecError):
        _spec(root, payload)

    assert runner.active_tokens() == ()


def test_the_refusal_for_an_oversized_payload_names_its_size_and_not_its_bytes():
    """An error message is a road out of the process, so it carries no prose."""
    oversized = INSTRUCTION + b"q" * STDIN_LIMIT

    with pytest.raises(CommandSpecError) as raised:
        CommandSpec(argv=("x",), cwd="work", stdin_bytes=oversized)

    message = str(raised.value)
    assert str(len(oversized)) in message and str(STDIN_LIMIT) in message
    assert "Add the missing guard" not in message


def test_the_payload_is_absent_from_the_specs_own_repr():
    """`repr` is the cheapest leak there is: a debugger frame, a log line.

    The other fields must still be there -- a spec whose repr said nothing would
    pass this by being useless.
    """
    spec = CommandSpec(
        argv=("claude", "-p"), cwd="work", stdin_bytes=INSTRUCTION)

    shown = repr(spec)

    assert "Add the missing guard" not in shown
    assert "stdin_bytes" not in shown
    assert "claude" in shown and "work" in shown


def test_the_payload_reaches_neither_argv_nor_environment_nor_working_directory(
        root, runners):
    """The whole point of choosing stdin over a positional argument.

    A prompt on argv is readable by any process lister on the machine. So the
    child is asked to report its own argv, its own environment and its own cwd,
    and the instruction must appear in none of them -- read from the CHILD,
    because what the parent believes it passed is not evidence.
    """
    outcome = runners(root).run(_spec(
        root, INSTRUCTION,
        env={DUMP_STDIN: "1", DUMP_ARGV: "1", DUMP_ENV: "1", DUMP_CWD: "1"}))

    assert outcome.status == "completed"
    reported = outcome.output.decode("utf-8")
    assert _reported(outcome)["bytes"] == len(INSTRUCTION)
    for line in reported.splitlines():
        if line.startswith(("ARGV ", "ENV ", "CWD ")):
            assert "Add the missing guard" not in line, line


def test_the_stdin_ceiling_is_the_instruction_ceiling_the_workspace_already_holds():
    """One ceiling, stated twice, pinned equal.

    The only thing this build ever writes to a child's stdin is an instruction
    body, and the workspace door already bounds those. A second and larger
    ceiling here would not be a coincidence -- it would be a way to deliver an
    instruction the first ceiling refused.
    """
    assert STDIN_LIMIT == INSTRUCTION_LIMIT
