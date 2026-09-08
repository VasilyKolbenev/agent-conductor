"""A deterministic stand-in for a pinned Claude Code binary, and a REAL executable.

Claude Code installs as a native binary, so its adapter pins ONE absolute path
and puts nothing in front of it. The executable is built by ``tests/_fakeexe.py``,
which produces a file the operating system really runs with no shell involved.

Every branch this child takes is chosen by a ``FAKECLAUDE_*`` environment knob
rather than by timing, an install, or a network, and importing this module never
runs the child body.

**What is different from every other fake in this roster, and why.** Claude Code
is the first provider whose task arrives on STDIN, so this child is the only
witness that can say whether it arrived at all. It therefore reads stdin to EOF
and records a MEASUREMENT of what it read -- a length and a digest -- into the
SPAWN LOG. It records the contents nowhere, and writes nothing of them to stdout.

The spawn log belongs under a test's own `tmp_path`, never under a project or
run root: it is an artefact this build does not sweep.

That split is deliberate and it is the whole design of this file:

- STDOUT is the transport's input, and a byte written there can reach a receipt,
  a journal record, an API response or an SSE frame. So this child never echoes
  the instruction to stdout. A fake that did would make every leak assertion in
  the Claude suites pass by accident, because the operator's prose would then be
  legitimately present in the child's own output and no test could tell a leak
  from an echo;
- the LOG carries a MEASUREMENT of what arrived and never a copy of it: a byte
  count and a sha256, from which a test computes the same digest and compares.
  That proves the exact bytes no less than storing them would, and it does not
  create a second copy of the operator's instruction in a file on disk. An
  earlier draft of this fake wrote `dict(os.environ)` and the decoded stdin
  text; with `ANTHROPIC_API_KEY` legitimately in a pin's `env_allow`, that log
  would have stored a real key on any machine that had one, and the test
  artefact would itself have become the leak channel every suite here exists to
  close.

**The leak question is asked INSIDE the child**, which is the only place that
can answer it about the environment without writing the environment down. The
probe token arrives ONLY in the piped task, in a closed form --
`CLAUDE_LEAK_PROBE_` followed by 64 hex digits -- and the child extracts it from
the stdin it has already read. It then scans its own argv, its own cwd and EVERY
value in its own environment, with no exclusions at all, and logs four BOOLEANS.
It never logs the token.

The no-exclusions part is the whole point, and an earlier draft got it wrong: it
took the marker from a `FAKECLAUDE_MARKER` variable and then had to skip that
variable when scanning the environment. "The marker is not in the environment"
was then true only by a carve-out for the test's own plumbing -- exactly the
shape of guard this suite exists to refuse. A token that never travels by
environment needs no exemption, so the scan has none.

The scan is OPT-IN, through `FAKECLAUDE_LEAK_CHECK=1`. Without it this child is
an ordinary transport double: it reads the task, measures it, records
`marker: null`, and runs. That matters because requiring a probe token from
every task would push a test-only syntax into every lifecycle scenario and into
the operator instruction each one composes -- which is not a shape a real Claude
Code would ever be handed, so the double would stop resembling the thing it
stands in for.

WITH the knob, a stdin that was read and carries no probe token, or more than
one, makes the CHILD FAIL with `PROBE_MISSING_EXIT`. That is the half that
cannot be optional: a leak scan that quietly skipped itself would turn every
future test that forgot its probe into a passing leak test that checked nothing.
The knob carries the string `"1"` and never the token, so the environment scan
still needs no exemption for it.

The read is BLOCKING and to EOF, so a parent that wrote the payload and never
closed the stream leaves this child waiting -- which is the failure the writer
lifecycle exists to prevent and which a test then sees as a timeout rather than
as a passing run.
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

#: Where each spawn appends its one JSON line.
SPAWN_LOG = "FAKECLAUDE_SPAWN_LOG"
#: The whole line `--version` prints. The default is the form two Anthropic issue
#: templates describe -- semver first, product name in parentheses -- so a test
#: asking for anything else is asking about a shape the vendor did not describe.
VERSION = "FAKECLAUDE_VERSION"
#: Non-empty makes `--version` itself fail, so the preflight refusal is testable.
VERSION_FAILS = "FAKECLAUDE_VERSION_FAILS"
#: Non-empty makes the LOGIN STATUS spawn answer "not signed in", the way the
#: reviewed binary does with an empty config directory: exit 1. Default is the
#: signed-in answer, so a subscription test that is about something else is not
#: forced to arrange a login first.
LOGIN_FAILS = "FAKECLAUDE_LOGIN_FAILS"
#: Which login the STATUS spawn reports. The default is a subscription, spelled
#: the way the reviewed binary spells its answer; `api_key` is the shape it
#: really returns when a key is in the environment, and that shape exits 0 --
#: which is why an exit-code test admitted it as a subscription.
LOGIN_METHOD = "FAKECLAUDE_LOGIN_METHOD"
LOGIN_ANSWERS = {
    "subscription": {"loggedIn": True, "authMethod": "claudeai",
                     "apiProvider": "firstParty"},
    "api_key": {"loggedIn": True, "authMethod": "api_key",
                "apiProvider": "firstParty",
                "apiKeySource": "ANTHROPIC_API_KEY"},
    "vertex": {"loggedIn": True, "authMethod": "claudeai",
               "apiProvider": "vertex"},
    #: A key with no source named, and a source named beside a subscription
    #: method. Each isolates ONE clause of the reader: without them the two
    #: clauses cover for each other and either could be deleted unnoticed.
    "quiet_key": {"loggedIn": True, "authMethod": "api_key",
                  "apiProvider": "firstParty"},
    "key_source": {"loggedIn": True, "authMethod": "claudeai",
                   "apiProvider": "firstParty",
                   "apiKeySource": "ANTHROPIC_API_KEY"},
    #: Signed OUT while still naming the method it last used.
    "stale": {"loggedIn": False, "authMethod": "claudeai",
              "apiProvider": "firstParty"},
    "none": {"loggedIn": False, "authMethod": "none",
             "apiProvider": "firstParty"},
    #: Valid JSON that names no method at all, and JSON that is not an object.
    #: Each isolates one guard of the reader that no other answer reaches.
    "methodless": {"loggedIn": True, "apiProvider": "firstParty"},
    "scalar": 7,
    "garbage": None,
}
#: Exit code for a prompt spawn; `--version` always exits 0 unless it is failed.
EXIT = "FAKECLAUDE_EXIT"
#: Emit this on stdout during a prompt spawn, to stand for a model's answer.
EMIT_STDOUT = "FAKECLAUDE_EMIT_STDOUT"
EMIT_HEX = "FAKECLAUDE_EMIT_HEX"
EMIT_REVIEW = "FAKECLAUDE_EMIT_REVIEW"
EMIT_VERDICT = "FAKECLAUDE_EMIT_VERDICT"
VERDICT_WRITE_FILE = "FAKECLAUDE_VERDICT_WRITE_FILE"
VERDICT_EXIT = "FAKECLAUDE_VERDICT_EXIT"
VERDICT_SLEEP = "FAKECLAUDE_VERDICT_SLEEP"
REVIEW_OUTPUT = "# Review\n\nThe contract is ready after its causal tests."
#: Emit this on stderr, which the runner merges into the same bounded capture.
EMIT_STDERR = "FAKECLAUDE_EMIT_STDERR"
#: Write this many bytes to stdout, to overrun the transport's capture bound.
BOMB_BYTES = "FAKECLAUDE_BOMB_BYTES"
#: Sleep this long during a prompt spawn, so a timeout is testable.
SLEEP = "FAKECLAUDE_SLEEP"
#: `relative/path:text` written inside the child's cwd, so a test can prove the
#: workspace evidence a real coding run would leave behind.
WRITE_FILE = "FAKECLAUDE_WRITE_FILE"
#: `name:text` written inside the child's own CONFIG DIRECTORY, which is what a
#: real harness does with its profile and what a persistent login directory has
#: to be judged about. Relative to that directory by construction: the whole
#: point is state left where the login lives.
HOME_FILE = "FAKECLAUDE_HOME_FILE"
#: REFRESH the login while this spawn runs: rewrite the credential file in this
#: child's own config directory with the given value, and print that value.
#:
#: This is what a real vendor does with a token that is about to expire, and it
#: is the case a scan built before the spawn cannot see: the value this child
#: echoes did not exist when the parent read the file.
#:
#: The value is carried as HEX, and that is not decoration. Every knob reaches
#: this child through the allowed environment, so a knob holding the token
#: itself would put that token in the runner's own scan set -- and a test would
#: watch the OLD scan catch it and conclude that nothing was missing.
REFRESH_LOGIN = "FAKECLAUDE_REFRESH_LOGIN"
#: `name:text` written into this child's own config directory during the LOGIN
#: STATUS spawn -- the preflight, not the task. A rule that stops a task running
#: and a rule that refuses one that has already run are different rules, and
#: only a preflight that leaves something can tell them apart.
PREFLIGHT_HOME_FILE = "FAKECLAUDE_PREFLIGHT_HOME_FILE"
#: `dir/name:text` written into the config directory and then LOCKED against
#: removal, in whatever way this platform locks one: Windows refuses to unlink a
#: read-only file, and POSIX refuses to unlink a child of a directory it may not
#: write. Both are set, so the production cleanup meets a real refusal on either
#: platform rather than a substitute for the function under test.
HOME_FILE_LOCKED = "FAKECLAUDE_HOME_FILE_LOCKED"
#: Do NOT read stdin at all -- the deaf child, for the delivery relation.
DEAF = "FAKECLAUDE_DEAF"
#: Turn the leak scan ON. A BOOLEAN, and the distinction matters: this knob
#: carries `"1"` and never the probe token, so the environment scan it enables
#: needs no exemption for the variable that enabled it. Off by default, so an
#: ordinary lifecycle test is not forced to write test-only syntax into the
#: operator instruction it composes.
LEAK_CHECK = "FAKECLAUDE_LEAK_CHECK"
#: The closed form of the leak probe token. It arrives ONLY inside the piped
#: task, never through the environment, so the scan needs no exemption for the
#: channel that delivered it. 64 hex digits make an accidental collision with an
#: operator's own prose impossible.
PROBE_PREFIX = "CLAUDE_LEAK_PROBE_"
PROBE_FORM = re.compile(PROBE_PREFIX + r"[0-9a-f]{64}")
#: What this child exits with when a task it READ carries no single probe token.
#: Loud on purpose: a run whose leak scan could not be performed must not be
#: mistaken for a run whose leak scan passed.
PROBE_MISSING_EXIT = 97

#: The environment names this child reads back, so a test asserting the
#: adapter's environment does not spell them twice.
CLAUDE_HOME_NAME = "CLAUDE_CONFIG_DIR"
SWITCH_NAMES = ("DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")

#: The line `--version` prints by default: the reviewed semver dressed exactly as
#: the vendor's own issue templates describe. The semver is read from the adapter
#: rather than restated, because a fake carrying its own copy would keep passing
#: after the reviewed constant moved; the DRESSING is spelled here, because that
#: is this fake's own subject.
try:  # pragma: no cover -- the child runs with the package importable
    from conductor.command.adapters.claude_code import (
        LOGIN_STATUS_ARGV,
        REVIEWED_CLAUDE_VERSION,
    )

    DEFAULT_VERSION = f"{REVIEWED_CLAUDE_VERSION} (Claude Code)"
    #: Read from the adapter for the same reason the semver is: a fake carrying
    #: its own copy would answer a login question the transport stopped asking.
    LOGIN_STATUS = list(LOGIN_STATUS_ARGV)
except ImportError:  # pragma: no cover -- never on a configured tree
    DEFAULT_VERSION = ""
    LOGIN_STATUS = []


def build_executable(directory: str | os.PathLike[str]) -> Path | None:
    """A REAL single-file executable standing in for the pinned claude binary."""
    return _fakeexe.build(directory, "claude", "_fakeclaude")


def spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Every spawn recorded so far, oldest first; missing log means none."""
    try:
        text = Path(log_path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _login_answer() -> int:
    """Answer the status question the way the reviewed binary answers it.

    It reads no stdin and writes no final message. The exit code follows the
    vendor's own: an API key IS a login as far as the binary is concerned, so
    this fake exits 0 for it too -- a fake that only ever exited 1 here could
    not have caught a product that read the code and called it a subscription.
    """
    if os.environ.get(PREFLIGHT_HOME_FILE) and os.environ.get(CLAUDE_HOME_NAME):
        _write_pair(Path(os.environ[CLAUDE_HOME_NAME]),
                    os.environ[PREFLIGHT_HOME_FILE])
    method = os.environ.get(LOGIN_METHOD) or (
        "none" if os.environ.get(LOGIN_FAILS) else "subscription")
    answer = LOGIN_ANSWERS[method]
    sys.stdout.buffer.write(
        b"not json at all\n" if answer is None
        else json.dumps(answer).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    return 1 if method == "none" else 0


def _login_question(argv: list[str]) -> bool:
    """Whether this spawn is the login-status question, behind any isolation flag.

    The transport sends that question with the same flag it sends a task with,
    so the fake recognises it by its TAIL rather than by its head -- a fake that
    matched only the bare form would read a flagged question as a prompt spawn
    and answer it by reading a stdin nobody will write.
    """
    return bool(LOGIN_STATUS) and argv[-len(LOGIN_STATUS):] == LOGIN_STATUS


def prompt_spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Only the spawns that really ran a prompt, never a preflight of either kind."""
    return [row for row in spawns(log_path)
            if row["argv"][:1] != ["--version"]
            and not _login_question(row["argv"])]


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


#: The delimiter the review frame draws before each durable input document.
#: Measured for its POSITION only, so a witness can say the plan's own words
#: stood before the material and not among it.
INPUTS_MARK = "--- durable artifact"


def _probe_report(argv: list[str], task_text: str) -> tuple[dict, dict]:
    """Where the probe token reached, as booleans and offsets and nothing else.

    The token is taken from the task this child just read, so the only channel
    it is known to have travelled by is the one under test. Every other channel
    is then scanned WITHOUT exception -- argv, cwd, and every environment value
    including the ones this fake's own knobs occupy.

    The second answer is WHERE in the task the token stood, beside where the
    first durable input began (``-1`` when the frame carried none): two
    integers, never a byte of the text. A frame that put project-authored
    context AMONG the material it was asked to review would be indistinguishable
    by count and digest alone.

    A task was read, or this is not called: the version preflight and the deaf
    child record ``None`` markers in the caller instead. A task without exactly
    one token raises out of here rather than guessing.
    """
    found = set(PROBE_FORM.findall(task_text))
    if len(found) != 1:
        raise _ProbeMissing(len(found))
    probe = found.pop()
    report = {
        "in_stdin": True,
        "in_argv": any(probe in token for token in argv),
        "in_cwd": probe in os.getcwd(),
        "in_env": any(probe in value for value in os.environ.values()),
    }
    frame = {"probe_at": task_text.find(probe),
             "inputs_at": task_text.find(INPUTS_MARK)}
    return report, frame


class _ProbeMissing(Exception):
    """A task was read and carried no single probe token, so no scan is possible."""

    def __init__(self, count: int) -> None:
        super().__init__(f"expected exactly one probe token, found {count}")
        self.count = count


def _record(argv: list[str], task: dict | None, marker: dict | None,
            frame: dict | None = None) -> None:
    """One JSON line per spawn, carrying measurements and never contents.

    What is deliberately ABSENT: every environment VALUE, and the text of the
    task. A pin may legitimately allow `ANTHROPIC_API_KEY` through, so a log
    holding values would hold a real credential on any machine that has one --
    and this file is a test artefact, written where nothing sweeps it. The two
    documented switches are recorded by name because their values are constants
    this build chose, not secrets it was handed. `frame` is two offsets into
    the task, recorded only when a probe was found, and never the task.
    """
    log = os.environ.get(SPAWN_LOG)
    if not log:
        return
    row = {
        "argv": argv,
        "cwd": os.getcwd(),
        "claude_home": os.environ.get(CLAUDE_HOME_NAME),
        "switches": {name: os.environ.get(name) for name in SWITCH_NAMES},
        "env_names": sorted(os.environ),
        "stdin": task,
        "marker": marker,
        "frame": frame,
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


def _run_prompt(checker=False) -> int:
    env = os.environ
    if checker and env.get(EMIT_VERDICT):
        return _run_verdict(env)
    if env.get(WRITE_FILE):
        _write_pair(Path.cwd(), env[WRITE_FILE])
    if env.get(HOME_FILE) and env.get(CLAUDE_HOME_NAME):
        _write_pair(Path(env[CLAUDE_HOME_NAME]), env[HOME_FILE])
    if env.get(HOME_FILE_LOCKED) and env.get(CLAUDE_HOME_NAME):
        base = Path(env[CLAUDE_HOME_NAME])
        where = env[HOME_FILE_LOCKED].split(":", 1)[0]
        (base / where).parent.mkdir(parents=True, exist_ok=True)
        _write_pair(base, env[HOME_FILE_LOCKED])
        os.chmod(base / where, 0o444)
        os.chmod((base / where).parent, 0o555)
    if env.get(REFRESH_LOGIN) and env.get(CLAUDE_HOME_NAME):
        fresh = bytes.fromhex(env[REFRESH_LOGIN]).decode("utf-8")
        (Path(env[CLAUDE_HOME_NAME]) / ".credentials.json").write_text(
            json.dumps({"claudeAiOauth": {"accessToken": fresh}}),
            encoding="utf-8", newline="\n")
        sys.stdout.buffer.write(fresh.encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
    if env.get(EMIT_STDOUT):
        sys.stdout.buffer.write(env[EMIT_STDOUT].encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
    if env.get(EMIT_REVIEW):
        sys.stdout.buffer.write(REVIEW_OUTPUT.encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
    if env.get(EMIT_HEX):
        sys.stdout.buffer.write(bytes.fromhex(env[EMIT_HEX]))
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
        # to read and reading would block on a stream nobody will close.
        # No task is piped to a preflight, so there is nothing to scan and
        # `marker: null` is the honest record of that.
        _record(argv, None, None)
        if os.environ.get(VERSION_FAILS):
            return 3
        sys.stdout.buffer.write(
            os.environ.get(VERSION, DEFAULT_VERSION).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
        return 0
    if LOGIN_STATUS and _login_question(argv):
        _record(argv, None, None)
        return _login_answer()
    # The task is read BEFORE anything is emitted: a child that answered first
    # and read afterwards would pass a test that only counts bytes back.
    task, task_text = _read_task()
    checker = (task_text.startswith("conduct independent verification")
               and any(argv[index:index + 2] == ["--permission-mode", "plan"]
                       for index in range(len(argv))))
    if not task["read"]:
        _record(argv, task, None)
        return _run_prompt(checker)
    if not os.environ.get(LEAK_CHECK):
        # An ordinary run: the task was read and measured, and no leak scan was
        # asked for. `marker: null` records that honestly rather than implying
        # a scan that passed.
        _record(argv, task, None)
        return _run_prompt(checker)
    try:
        report, frame = _probe_report(argv, task_text)
    except _ProbeMissing as missing:
        _record(argv, task, None)
        sys.stderr.buffer.write(f"FAKECLAUDE: {missing}\n".encode("utf-8"))
        sys.stderr.buffer.flush()
        return PROBE_MISSING_EXIT
    _record(argv, task, report, frame)
    return _run_prompt(checker)


if __name__ == "__main__":
    sys.exit(main())
