"""A deterministic stand-in for the pinned dsh entrypoint.

Run as ``[sys.executable, FAKE_DSH, *argv]`` it plays the parts of the real
contract this adapter depends on -- ``--version`` prints one token and exits, and
``--profile headless <task>`` runs one task and exits -- while every branch it
takes is chosen by a ``FAKEDSH_*`` environment knob rather than by timing, an
install, or a network. Importing it never runs the child body.

Every spawn appends one JSON line to the spawn log, so a test can COUNT spawns
and read back the exact argv, cwd and dsh environment the adapter handed over.
That log is the evidence behind the version-mismatch gate: a mismatch must leave
zero task lines, not merely report a failure.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

FAKE_DSH = str(Path(__file__).resolve())

#: Where each spawn appends its one JSON line.
SPAWN_LOG = "FAKEDSH_SPAWN_LOG"
#: The token `--version` prints; default is the version the adapter reviewed.
VERSION = "FAKEDSH_VERSION"
#: Bytes written to stdout / stderr by a task spawn (the secret-planting seam).
EMIT_STDOUT = "FAKEDSH_STDOUT"
EMIT_STDERR = "FAKEDSH_STDERR"
#: An output bomb, in bytes, written past any sane capture bound.
BOMB_BYTES = "FAKEDSH_BOMB_BYTES"
#: Seconds a task spawn sleeps before exiting; drives the real timeout path.
SLEEP = "FAKEDSH_SLEEP"
#: "relpath:text" written under the task's cwd -- the workspace evidence seam.
WRITE_FILE = "FAKEDSH_WRITE_FILE"
#: "relpath:text" written relative to the PARENT of the task's cwd, i.e. outside
#: the action's authorized subtree.
ESCAPE_FILE = "FAKEDSH_ESCAPE_FILE"
#: "relpath:text" written under the spawn's own DSH_HOME -- the model-text seam
#: a real harness fills with prompt, session and tool output.
HOME_FILE = "FAKEDSH_HOME_FILE"
#: Exit code for a task spawn; `--version` always exits 0 unless this is set.
EXIT = "FAKEDSH_EXIT"
#: Non-empty makes `--version` itself fail, so the preflight refusal is testable.
VERSION_FAILS = "FAKEDSH_VERSION_FAILS"

#: The version the adapter was written against, so the default path is the happy one.
DEFAULT_VERSION = "0.1.0-rc.7"


def fake_pins() -> tuple[str, str]:
    """The (node_executable, entrypoint) pair that runs this fake through Python."""
    return sys.executable, FAKE_DSH


def spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Every spawn recorded so far, oldest first; missing log means none."""
    try:
        text = Path(log_path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def task_spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Only the spawns that actually ran a task, never the version preflights."""
    return [row for row in spawns(log_path) if row["argv"][:1] != ["--version"]]


def _record(argv: list[str]) -> None:
    log = os.environ.get(SPAWN_LOG)
    if not log:
        return
    row = {
        "argv": argv,
        "cwd": os.getcwd(),
        "dsh_home": os.environ.get("DSH_HOME"),
        "telemetry_disabled": os.environ.get("DSH_TELEMETRY_DISABLED"),
        "env_names": sorted(os.environ),
    }
    with open(log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_pair(base: Path, spec: str) -> None:
    relative, _, text = spec.partition(":")
    target = base / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def _run_task() -> int:
    env = os.environ
    if env.get(WRITE_FILE):
        _write_pair(Path.cwd(), env[WRITE_FILE])
    if env.get(ESCAPE_FILE):
        _write_pair(Path.cwd().parent, env[ESCAPE_FILE])
    if env.get(HOME_FILE) and env.get("DSH_HOME"):
        _write_pair(Path(env["DSH_HOME"]), env[HOME_FILE])
    if env.get(EMIT_STDOUT):
        sys.stdout.buffer.write(env[EMIT_STDOUT].encode("utf-8") + b"\n")
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
    _record(argv)
    if argv[:1] == ["--version"]:
        if os.environ.get(VERSION_FAILS):
            return 3
        sys.stdout.buffer.write(
            os.environ.get(VERSION, DEFAULT_VERSION).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()
        return 0
    return _run_task()


if __name__ == "__main__":
    sys.exit(main())
