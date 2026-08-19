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
#: An absolute path the child REPLACES its own DSH_HOME with, as a portal. This
#: is the seam behind Codex's silent-retention probe: a child that swaps the
#: directory the parent minted for a link makes the parent's cleanup refuse.
HOME_PORTAL = "FAKEDSH_HOME_PORTAL"
#: Where the child records which portal kind it managed to plant, relative to
#: the task's own cwd; ``none`` means the platform granted neither primitive.
PORTAL_WITNESS = "home-portal-kind.txt"
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


def _empty_tree(root: Path) -> None:
    """Remove everything under ``root``, then ``root`` itself, following nothing."""
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        else:
            path.unlink()
    root.rmdir()


def _replace_home_with_portal(target: str) -> str:
    """Swap this spawn's own DSH_HOME for a portal at the very same name.

    The parent minted a directory here and remembers the name; a child that
    replaces it with a junction or a symbolic link is the hostile case Codex
    drove. Returns the kind actually planted, so the caller's test reads what
    happened from the child rather than assuming it: a platform that grants
    neither primitive answers ``"none"`` and leaves an ordinary directory.
    """
    home = Path(os.environ.get("DSH_HOME", ""))
    if not home.name or not home.is_dir():
        return "none"
    _empty_tree(home)
    try:
        import _winapi

        _winapi.CreateJunction(target, str(home))
        return "junction"
    except (ImportError, AttributeError, OSError):
        pass
    try:
        home.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        home.mkdir(parents=True, exist_ok=True)
        return "none"
    return "symlink"


def _run_task() -> int:
    env = os.environ
    if env.get(WRITE_FILE):
        _write_pair(Path.cwd(), env[WRITE_FILE])
    if env.get(ESCAPE_FILE):
        _write_pair(Path.cwd().parent, env[ESCAPE_FILE])
    if env.get(HOME_FILE) and env.get("DSH_HOME"):
        _write_pair(Path(env["DSH_HOME"]), env[HOME_FILE])
    if env.get(HOME_PORTAL):
        kind = _replace_home_with_portal(env[HOME_PORTAL])
        _write_pair(Path.cwd(), f"{PORTAL_WITNESS}:{kind}")
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
