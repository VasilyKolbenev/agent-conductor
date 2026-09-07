"""A deterministic stand-in for a pinned Codex CLI binary, and a REAL executable.

Codex CLI installs as a native binary -- the npm package vendors one and spawns
it through a shim -- so its adapter pins ONE absolute path and puts nothing in
front of it. The executable is built by ``tests/_fakeexe.py``, which produces a
file the operating system really runs with no shell involved.

Every branch this child takes is chosen by a ``FAKECODEX_*`` environment knob
rather than by timing, an install, or a network, and importing this module never
runs the child body.

**What this fake has that no other in the roster does: it writes where it was
TOLD to.** The real CLI takes ``-o <FILE>`` and writes the agent's last message
there, so this child reads that path out of its OWN argv and writes there too.
Reading it from argv rather than from a knob is the whole point: a fake handed
the path by the test would prove that the test knows where the file goes, and
what needs proving is that the TRANSPORT put a usable path on the command line.

The three states the adapter tells apart are all reachable, and each by its own
knob, because they are three different facts about a real run:

- an ordinary run writes a non-empty file, as a real one does when the model
  answered;
- ``FAKECODEX_EMPTY_LAST_MESSAGE`` writes zero bytes, which is exactly what the
  real CLI does when a run produced no final agent message -- it writes the file
  empty and warns on stderr;
- ``FAKECODEX_NO_LAST_MESSAGE`` writes nothing at all, which is a run that never
  reached the point of reporting;
- ``FAKECODEX_LAST_MESSAGE_DIRECTORY`` puts a DIRECTORY at that name, standing in
  for anything a hostile or broken child might leave where a file was expected.

The default text is a CONSTANT and never the task: a fake that echoed the piped
instruction into a file would put the operator's prose somewhere the suites hunt
for leaks, and every leak assertion touching that file would then pass by
accident.

**The rest is the shape ``tests/_fakeclaude.py`` established, and the reasons are
the same.** This child reads stdin to EOF and records a MEASUREMENT of what it
read -- a length and a digest -- into the SPAWN LOG. It records the contents
nowhere and writes nothing of them to stdout:

- STDOUT is the transport's input, and a byte written there can reach a receipt,
  a journal record, an API response or an SSE frame. A fake that echoed the
  instruction would make every leak assertion pass by accident, because the
  operator's prose would then be legitimately present in the child's own output;
- the LOG carries a MEASUREMENT and never a copy: a byte count and a sha256,
  from which a test computes the same digest and compares. That proves the exact
  bytes no less than storing them would, and it creates no second copy of the
  operator's instruction on disk. An earlier draft of the Claude fake wrote
  ``dict(os.environ)``; with ``OPENAI_API_KEY`` legitimately in a pin's
  ``env_allow`` such a log would store a real key on any machine that has one.

**The leak question is asked INSIDE the child**, which is the only place that can
answer it about the environment without writing the environment down. The probe
token arrives ONLY in the piped task, in a closed form -- ``CODEX_LEAK_PROBE_``
followed by 64 hex digits -- and the child extracts it from the stdin it has
already read. It then scans its own argv, its own cwd and EVERY value in its own
environment, with no exclusions at all, and logs four BOOLEANS. It never logs the
token. A token that never travels by environment needs no exemption, so the scan
has none.

The scan is OPT-IN, through ``FAKECODEX_LEAK_CHECK=1``. Without it this child is
an ordinary transport double. WITH the knob, a stdin that was read and carries no
probe token, or more than one, makes the CHILD FAIL with ``PROBE_MISSING_EXIT``.
That half cannot be optional: a leak scan that quietly skipped itself would turn
every future test that forgot its probe into a passing leak test that checked
nothing.

The read is BLOCKING and to EOF, so a parent that wrote the payload and never
closed the stream leaves this child waiting -- which is the failure the writer
lifecycle exists to prevent and which a test then sees as a timeout rather than
as a passing run.

The spawn log belongs under a test's own ``tmp_path``, never under a project or
run root: it is an artefact this build does not sweep.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from tests import _fakeexe
from tests._fakeenv import probe_report

#: Where each spawn appends its one JSON line.
SPAWN_LOG = "FAKECODEX_SPAWN_LOG"
#: The whole line `--version` prints. The default is the form the reviewed binary
#: really prints -- the PACKAGE name and then the semver -- so a test asking for
#: anything else is asking about a shape that install does not produce.
VERSION = "FAKECODEX_VERSION"
#: Non-empty makes `--version` itself fail, so the preflight refusal is testable.
VERSION_FAILS = "FAKECODEX_VERSION_FAILS"
#: Exit code for a task spawn; `--version` always exits 0 unless it is failed.
EXIT = "FAKECODEX_EXIT"
#: Emit this on stdout during a task spawn, to stand for a model's answer.
EMIT_STDOUT = "FAKECODEX_EMIT_STDOUT"
#: Emit the fixed review answer below on stdout. A knob of its own rather than a
#: value passed through `EMIT_STDOUT`, because the leak suites drive that one
#: with a credential and a review test must be able to ask for an ordinary
#: answer without borrowing the channel a leak probe is using.
EMIT_REVIEW = "FAKECODEX_EMIT_REVIEW"
EMIT_VERDICT = "FAKECODEX_EMIT_VERDICT"
VERDICT_WRITE_FILE = "FAKECODEX_VERDICT_WRITE_FILE"
VERDICT_EXIT = "FAKECODEX_VERDICT_EXIT"
VERDICT_SLEEP = "FAKECODEX_VERDICT_SLEEP"
#: What a review spawn answers with. Fixed, so a test asserts the exact bytes
#: that became the durable artifact rather than a shape.
REVIEW_OUTPUT = "# Review\n\nThe durable material holds; publish it."
#: Emit this on stderr, which the runner merges into the same bounded capture.
EMIT_STDERR = "FAKECODEX_EMIT_STDERR"
#: Write this many bytes to stdout, to overrun the transport's capture bound.
BOMB_BYTES = "FAKECODEX_BOMB_BYTES"
#: Sleep this long during a task spawn, so a timeout is testable.
SLEEP = "FAKECODEX_SLEEP"
#: `relative/path:text` written inside the child's cwd, so a test can prove the
#: workspace evidence a real coding run would leave behind.
WRITE_FILE = "FAKECODEX_WRITE_FILE"
#: Do NOT read stdin at all -- the deaf child, for the delivery relation.
DEAF = "FAKECODEX_DEAF"
#: Turn the leak scan ON. A BOOLEAN: this knob carries `"1"` and never the probe
#: token, so the environment scan it enables needs no exemption for the variable
#: that enabled it.
LEAK_CHECK = "FAKECODEX_LEAK_CHECK"
#: What to write into the file `-o` names. A CONSTANT by default and never the
#: task; a test that wants particular bytes there spells them.
LAST_MESSAGE = "FAKECODEX_LAST_MESSAGE"
#: Write ZERO bytes to that file: what the real CLI does when a run produced no
#: final agent message at all.
EMPTY_LAST_MESSAGE = "FAKECODEX_EMPTY_LAST_MESSAGE"
#: Write nothing at all: a run that never reached the point of reporting.
NO_LAST_MESSAGE = "FAKECODEX_NO_LAST_MESSAGE"
#: Put a DIRECTORY where the file should be, for the kind the adapter refuses to
#: read as a message.
LAST_MESSAGE_DIRECTORY = "FAKECODEX_LAST_MESSAGE_DIRECTORY"

#: The closed form of the leak probe token. It arrives ONLY inside the piped
#: task, never through the environment, so the scan needs no exemption for the
#: channel that delivered it. 64 hex digits make an accidental collision with an
#: operator's own prose impossible.
PROBE_PREFIX = "CODEX_LEAK_PROBE_"
PROBE_FORM = re.compile(PROBE_PREFIX + r"[0-9a-f]{64}")
#: What this child exits with when a task it READ carries no single probe token.
#: Loud on purpose: a run whose leak scan could not be performed must not be
#: mistaken for a run whose leak scan passed.
PROBE_MISSING_EXIT = 96

#: The environment name this child reads back, so a test asserting the adapter's
#: environment does not spell it twice.
CODEX_HOME_NAME = "CODEX_HOME"
#: The flag this child takes its output path from, spelled here because reading
#: it out of argv is what proves the transport really sent it.
LAST_MESSAGE_FLAG = "-o"
#: The default body, which says nothing about the task and carries no prose an
#: operator wrote.
DEFAULT_LAST_MESSAGE = "the fake Codex CLI reports a final message"

#: The line `--version` prints by default: the reviewed semver dressed exactly as
#: the installed binary dresses it. The semver is read from the adapter rather
#: than restated, because a fake carrying its own copy would keep passing after
#: the reviewed constant moved; the DRESSING is spelled here, because that is
#: this fake's own subject.
try:  # pragma: no cover -- the child runs with the package importable
    from conductor.command.adapters.codex_cli import REVIEWED_CODEX_VERSION

    DEFAULT_VERSION = f"codex-cli {REVIEWED_CODEX_VERSION}"
except ImportError:  # pragma: no cover -- never on a configured tree
    DEFAULT_VERSION = ""


def build_executable(directory: str | os.PathLike[str]) -> Path | None:
    """A REAL single-file executable standing in for the pinned codex binary."""
    return _fakeexe.build(directory, "codex", "_fakecodex")


def spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Every spawn recorded so far, oldest first; missing log means none."""
    try:
        text = Path(log_path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def task_spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Only the spawns that really ran a task, never the version preflights."""
    return [row for row in spawns(log_path) if row["argv"][:1] != ["--version"]]


# --- the child body ----------------------------------------------------------


def _read_task() -> tuple[dict, str]:
    """Read stdin to EOF and MEASURE what arrived, without copying it anywhere.

    A length and a digest, never the text. A test that knows what it sent can
    compute the same digest, which proves the exact bytes as strictly as storing
    them would -- and storing them would put the operator's instruction in a
    second file that nothing sweeps.

    The decoded text is returned separately, to the caller in this process only,
    so the marker scan below can run without any of it reaching the log.
    """
    if os.environ.get(DEAF):
        return {"read": False}, ""
    payload = sys.stdin.buffer.read()
    return {
        "read": True,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }, payload.decode("utf-8", errors="replace")


def _probe_report(argv: list[str], task_text: str) -> dict:
    """Where the probe token reached, as booleans and nothing else.

    The token is taken from the task this child just read, so the only channel
    it is known to have travelled by is the one under test. Every other channel
    is then scanned WITHOUT exception -- argv, cwd, and every environment value
    including the ones this fake's own knobs occupy.
    """
    found = set(PROBE_FORM.findall(task_text))
    if len(found) != 1:
        raise _ProbeMissing(len(found))
    probe = found.pop()
    return {
        "in_stdin": True,
        "in_argv": any(probe in token for token in argv),
        "in_cwd": probe in os.getcwd(),
        "in_env": any(probe in value for value in os.environ.values()),
    }


class _ProbeMissing(Exception):
    """A task was read and carried no single probe token, so no scan is possible."""

    def __init__(self, count: int) -> None:
        super().__init__(f"expected exactly one probe token, found {count}")
        self.count = count


def last_message_target(argv: list[str]) -> str | None:
    """The path this spawn was TOLD to write its final message to, from argv.

    Read from the command line rather than from a knob, because what needs
    proving is that the transport put a usable path there. A spawn that was
    given no such flag -- the version preflight -- answers None.
    """
    for index, token in enumerate(argv):
        if token == LAST_MESSAGE_FLAG and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _write_last_message(argv: list[str]) -> str | None:
    """Do to that path whatever the knobs ask, and report which path it was.

    The real CLI writes this file on the way out of a completed run, including
    when the model said nothing -- in which case it writes it EMPTY. All four
    outcomes an adapter has to tell apart are reachable from here.
    """
    target = last_message_target(argv)
    if target is None or os.environ.get(NO_LAST_MESSAGE):
        return target
    path = Path(target)
    if os.environ.get(LAST_MESSAGE_DIRECTORY):
        path.mkdir(parents=True, exist_ok=True)
        return target
    body = "" if os.environ.get(EMPTY_LAST_MESSAGE) else os.environ.get(
        LAST_MESSAGE, DEFAULT_LAST_MESSAGE)
    path.write_text(body, encoding="utf-8", newline="\n")
    return target


def _record(argv: list[str], task: dict | None, marker: dict | None,
            last_message: str | None) -> None:
    """One JSON line per spawn, carrying measurements and never contents.

    What is deliberately ABSENT: every environment VALUE, and the text of the
    task. A pin may legitimately allow `OPENAI_API_KEY` through, so a log holding
    values would hold a real credential on any machine that has one -- and this
    file is a test artefact, written where nothing sweeps it.
    """
    log = os.environ.get(SPAWN_LOG)
    if not log:
        return
    home = os.environ.get(CODEX_HOME_NAME)
    row = {
        "argv": argv,
        "cwd": os.getcwd(),
        "codex_home": home,
        # The far side's own answer to the one question no parent can settle:
        # this vendor REFUSES a `CODEX_HOME` that is not an existing directory,
        # so whether it was one at the moment the child ran is a fact only the
        # child holds. A boolean, never a second copy of the path.
        "codex_home_is_dir": bool(home) and Path(home).is_dir(),
        "env_names": sorted(os.environ),
        # Two booleans about the parent's probe, and never a value. See
        # `tests/_fakeenv.py` for why an exact name set was not the question.
        "probe": probe_report(),
        "stdin": task,
        "marker": marker,
        "last_message": last_message,
    }
    with open(log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_pair(base: Path, spec: str) -> None:
    relative, _, text = spec.partition(":")
    target = base / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def _run_verdict(env) -> int:
    if env.get(VERDICT_WRITE_FILE):
        _write_pair(Path.cwd(), env[VERDICT_WRITE_FILE])
    if env.get(VERDICT_SLEEP):
        time.sleep(float(env[VERDICT_SLEEP]))
    answer = {"enabled-verdict-accept": "VERDICT: accept",
              "enabled-verdict-reject": "VERDICT: reject"}.get(
                  env[EMIT_VERDICT], "No valid verdict was emitted.")
    sys.stdout.buffer.write((answer + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    return int(env.get(VERDICT_EXIT, "0"))


def _run_task(checker=False) -> int:
    env = os.environ
    if checker and env.get(EMIT_VERDICT):
        return _run_verdict(env)
    if env.get(WRITE_FILE):
        _write_pair(Path.cwd(), env[WRITE_FILE])
    if env.get(EMIT_STDOUT):
        sys.stdout.buffer.write(env[EMIT_STDOUT].encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
    if env.get(EMIT_REVIEW):
        sys.stdout.buffer.write(REVIEW_OUTPUT.encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
    if env.get(EMIT_STDERR):
        sys.stderr.buffer.write(env[EMIT_STDERR].encode("utf-8") + b"\n")
        sys.stderr.buffer.flush()
    if env.get(BOMB_BYTES):
        sys.stdout.buffer.write(b"B" * int(env[BOMB_BYTES]))
        sys.stdout.buffer.flush()
    if env.get(SLEEP):
        time.sleep(float(env[SLEEP]))
    return int(env.get(EXIT, "0"))


def main() -> int:
    argv = sys.argv[1:]
    if argv[:1] == ["--version"]:
        # The preflight is spawned with no payload at all, so there is nothing
        # to read and reading would block on a stream nobody will close. It
        # carries no `-o` either, so it writes no final message and says so.
        _record(argv, None, None, None)
        if os.environ.get(VERSION_FAILS):
            return 3
        sys.stdout.buffer.write(
            os.environ.get(VERSION, DEFAULT_VERSION).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
        return 0
    # The task is read BEFORE anything is emitted: a child that answered first
    # and read afterwards would pass a test that only counts bytes back.
    task, task_text = _read_task()
    checker = (task_text.startswith("conduct independent verification")
               and any(argv[index:index + 2] == ["--sandbox", "read-only"]
                       for index in range(len(argv))))
    written = _write_last_message(argv)
    if not task["read"]:
        _record(argv, task, None, written)
        return _run_task(checker)
    if not os.environ.get(LEAK_CHECK):
        # An ordinary run: the task was read and measured, and no leak scan was
        # asked for. `marker: null` records that honestly rather than implying
        # a scan that passed.
        _record(argv, task, None, written)
        return _run_task(checker)
    try:
        report = _probe_report(argv, task_text)
    except _ProbeMissing as missing:
        _record(argv, task, None, written)
        sys.stderr.buffer.write(f"FAKECODEX: {missing}\n".encode("utf-8"))
        sys.stderr.buffer.flush()
        return PROBE_MISSING_EXIT
    _record(argv, task, report, written)
    return _run_task(checker)


if __name__ == "__main__":
    sys.exit(main())
