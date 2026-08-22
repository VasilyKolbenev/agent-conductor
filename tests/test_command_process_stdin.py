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

from conductor.command.adapters import process as process_module
from conductor.command.adapters.harness_workspace import INSTRUCTION_LIMIT
from conductor.command.adapters.process import (
    STDIN_DELIVERED,
    STDIN_INCOMPLETE,
    STDIN_LIMIT,
    STDIN_NOT_PROVIDED,
    STDIN_STATES,
    CommandSpec,
    CommandSpecError,
    OwnershipError,
    ProcessOutcome,
    ProcessRunner,
    _Owned,
    _map_outcome,
)

from tests._fakeproc import (
    DEAF_EXIT,
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


# --- the delivery fact, and what may be built on it --------------------------


def test_a_child_that_exits_without_reading_is_not_a_run_that_succeeded(
        root, runners):
    """The defect this field was added for, held as its own claim.

    A child that calls `os._exit(0)` having read nothing exits zero, exits
    cleanly, and exits fast. Every process fact about it is good. It was also
    never told what to do -- so a build that read those facts as success would
    be reporting on a task it never posed, over and over, with no signal
    anywhere that anything was wrong.

    The runner still reports the process honestly: `completed`, exit zero. What
    changes is that it now also reports what it could not deliver, and the
    receipt vocabulary refuses to call that a success.
    """
    payload = INSTRUCTION * 400

    outcome = runners(root).run(_spec(
        root, payload, env={DEAF_EXIT: "0"}))

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert outcome.stdin_state == STDIN_INCOMPLETE
    mapped, detail = _map_outcome(outcome)
    assert mapped == "failed", "an undelivered instruction became a success"
    assert "never delivered whole" in detail


def test_a_delivered_payload_is_reported_as_delivered_and_the_run_can_succeed(
        root, runners):
    """The positive control the refusals above cannot supply, and it is load-bearing.

    Every other claim here is about `incomplete`. A seam that answered
    `incomplete` unconditionally would satisfy all of them, pass the whole
    suite, and quietly make it impossible for any provider taking its task on
    stdin to ever succeed -- a failure that looks exactly like the vendor's
    fault. So the successful state is asserted on the object AND carried through
    the receipt vocabulary, which is the only reader that acts on it.
    """
    outcome = runners(root).run(_spec(root, INSTRUCTION))

    assert outcome.status == "completed"
    assert outcome.stdin_state == STDIN_DELIVERED
    assert _map_outcome(outcome)[0] == "succeeded"


def test_a_close_that_fails_leaves_the_delivery_unclaimed(root):
    """The EOF is part of the claim, so a close that did not happen unmakes it.

    Unreachable through a real child: a pipe whose write and flush both
    succeeded does not then refuse to close, and no knob on the far side can
    make it. So the feed is driven directly against a stream that fails exactly
    where the branch is -- which is the only way this relation is falsifiable at
    all, and saying that out loud is better than leaving the branch unguarded
    because it is inconvenient to reach.
    """
    class _RefusesToClose:
        def __init__(self):
            self.written = bytearray()

        def write(self, view):
            self.written += bytes(view)
            return len(view)

        def flush(self):
            return None

        def close(self):
            raise OSError("the descriptor was already gone")

    stream = _RefusesToClose()
    owned = _Owned.__new__(_Owned)
    owned.proc = type("_P", (), {"stdin": stream})()
    owned.stdin_state = STDIN_INCOMPLETE

    _Owned._feed(owned, INSTRUCTION)

    assert bytes(stream.written) == INSTRUCTION, "the write itself must have run"
    assert owned.stdin_state == STDIN_INCOMPLETE, (
        "a payload whose stream never closed was reported as delivered")


def test_the_delivery_state_is_one_of_three_words_and_a_fourth_is_refused():
    """A closed vocabulary, refused at construction like every other closed one.

    Without this an outcome could carry `"ok"`, or `"delivered "`, and every
    comparison against the real word would quietly answer `False` -- which for
    this field means quietly answering "not incomplete", which means success.
    """
    assert set(STDIN_STATES) == {"not_provided", "delivered", "incomplete"}

    for rejected in ("ok", "DELIVERED", "delivered ", "", None):
        with pytest.raises(CommandSpecError):
            ProcessOutcome(
                status="completed", exit_code=0, output=b"", output_truncated=False,
                output_limit=64, pid=1, token="t", stdin_state=rejected)


@pytest.mark.parametrize("state", [STDIN_NOT_PROVIDED, STDIN_DELIVERED])
def test_a_zero_exit_is_still_a_success_when_the_input_was_not_the_problem(state):
    """The positive control. The guard must not have made every zero a failure.

    `not_provided` is the three shipped providers, which pass nothing at all;
    `delivered` is a payload that arrived whole. Both must still succeed, or the
    fix for the defect above would have broken the roster instead.
    """
    outcome = ProcessOutcome(
        status="completed", exit_code=0, output=b"done", output_truncated=False,
        output_limit=64, pid=1, token="t", stdin_state=state)

    mapped, _detail = _map_outcome(outcome)

    assert mapped == "succeeded"


def test_an_undelivered_input_does_not_overwrite_a_timeout_or_a_cancellation():
    """It must never become a success; it must also not eat a truer word.

    A run that timed out did time out, and a stopped run was cancelled. Both
    already say the work did not succeed, so relabelling them would trade one
    true fact for another and lose the operator's own action from the record.
    """
    def built(status):
        return ProcessOutcome(
            status=status, exit_code=None, output=b"", output_truncated=False,
            output_limit=64, pid=1, token="t", stdin_state=STDIN_INCOMPLETE)

    assert _map_outcome(built("timed_out"))[0] == "failed"
    assert _map_outcome(built("stopped"))[0] == "cancelled"


def test_a_spawn_that_fails_before_ownership_closes_the_input_it_opened(
        root, runners, monkeypatch):
    """The parent's write handle must not outlive a spawn that never published.

    Between `Popen(stdin=PIPE)` and the ownership publish there is no `_Owned`
    to close anything and no token anyone could stop, so a failure in that
    window used to leave the parent holding a pipe to a child it had just
    killed -- open until the garbage collector happened to notice.

    The failure is injected at the ownership step rather than simulated, and the
    handle is read afterwards from the process object itself.
    """
    captured = {}
    real_popen = process_module.subprocess.Popen

    def remember(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        captured["proc"] = proc
        return proc

    monkeypatch.setattr(process_module.subprocess, "Popen", remember)
    monkeypatch.setattr(
        process_module.secrets, "token_hex",
        lambda _n: (_ for _ in ()).throw(RuntimeError("no token today")))

    runner = runners(root)
    with pytest.raises(RuntimeError, match="no token today"):
        runner.run(_spec(root, INSTRUCTION))

    proc = captured["proc"]
    assert proc.stdin is not None
    assert proc.stdin.closed, "the failed spawn left the child's input open"
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
