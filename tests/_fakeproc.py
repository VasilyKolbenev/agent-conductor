"""A deterministic fake executable for the owned-process runner tests.

Run as a child through ``[sys.executable, FAKE_EXEC, *argv]`` it is driven
entirely by ``FAKEPROC_*`` environment knobs, so a test controls its output,
exit code, running time, and whether it spawns a grandchild -- no installed
tool and no timing luck is relied on. Imported by a test module it offers the
path, an argv builder, and small readers; importing it never runs the child
body, which is guarded by ``__main__``.

Every line the child prints is written to the raw stdout buffer with an
explicit ``\\n`` so captured bytes are identical on Windows and POSIX. The
heartbeat and pid files are published with ``os.replace``, so a reader sees a
whole value or nothing, never a torn one -- which is what lets a test prove a
child was terminated by watching its heartbeat freeze.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

FAKE_EXEC = str(Path(__file__).resolve())

#: The environment knobs the child reads. Named here so tests and child agree.
PID_FILE = "FAKEPROC_PID_FILE"
HEARTBEAT_FILE = "FAKEPROC_HEARTBEAT_FILE"
HEARTBEAT_MAX = "FAKEPROC_HEARTBEAT_MAX"
HEARTBEAT_INTERVAL = "FAKEPROC_HEARTBEAT_INTERVAL"
SPAWN_HB_FILE = "FAKEPROC_SPAWN_HB_FILE"
SLEEP = "FAKEPROC_SLEEP"
EMIT_BYTES = "FAKEPROC_EMIT_BYTES"
EMIT_STDOUT = "FAKEPROC_EMIT_STDOUT"
EMIT_STDERR = "FAKEPROC_EMIT_STDERR"
DUMP_ARGV = "FAKEPROC_DUMP_ARGV"
DUMP_ENV = "FAKEPROC_DUMP_ENV"
DUMP_CWD = "FAKEPROC_DUMP_CWD"
EXIT = "FAKEPROC_EXIT"


def fake_argv(*extra: str) -> list[str]:
    """The argv vector that runs this fake as the given interpreter's child."""
    return [sys.executable, FAKE_EXEC, *extra]


def read_int(path: str | os.PathLike[str]) -> int | None:
    """Read one atomically-published integer, or None if absent or not yet written."""
    try:
        text = Path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return int(text) if text else None


def wait_for_int(path: str | os.PathLike[str], *, timeout: float = 5.0) -> int:
    """Block until the file holds an integer; deterministic on a live child."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read_int(path)
        if value is not None:
            return value
        time.sleep(0.01)
    raise AssertionError(f"no integer appeared at {path!r} within {timeout}s")


def wait_for_pids(path: str | os.PathLike[str], *, timeout: float = 5.0) -> tuple[int, int]:
    """Block until the pid file holds the child's own (pid, ppid) pair.

    The child self-reports both because ``sys.executable`` may be a launcher
    stub that re-execs the real interpreter as its own child: the process the
    runner started directly is then the child's parent, not the child itself.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            parts = Path(path).read_text(encoding="ascii").split()
        except (OSError, UnicodeError):
            parts = []
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
        time.sleep(0.01)
    raise AssertionError(f"no (pid, ppid) pair appeared at {path!r} within {timeout}s")


def _write_atomic(path: str, text: str) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="ascii") as handle:
        handle.write(text)
    os.replace(tmp, path)


def _emit(line: str) -> None:
    sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _spawn_grandchild(heartbeat_file: str) -> None:
    env = dict(os.environ)
    env.pop(SPAWN_HB_FILE, None)
    env.pop(PID_FILE, None)
    env[HEARTBEAT_FILE] = heartbeat_file
    subprocess.Popen(fake_argv(), env=env)


def _heartbeat(path: str) -> None:
    interval = float(os.environ.get(HEARTBEAT_INTERVAL, "0.02"))
    limit = int(os.environ.get(HEARTBEAT_MAX, "3000"))
    counter = 0
    while counter < limit:
        counter += 1
        _write_atomic(path, str(counter))
        time.sleep(interval)


def main() -> int:
    env = os.environ
    if env.get(PID_FILE):
        _write_atomic(env[PID_FILE], f"{os.getpid()} {os.getppid()}")
    if env.get(SPAWN_HB_FILE):
        _spawn_grandchild(env[SPAWN_HB_FILE])
    if env.get(DUMP_ARGV):
        _emit("ARGV " + json.dumps(sys.argv[1:]))
    if env.get(DUMP_ENV):
        _emit("ENV " + json.dumps(dict(env)))
    if env.get(DUMP_CWD):
        _emit("CWD " + os.getcwd())
    if env.get(EMIT_STDOUT):
        _emit(env[EMIT_STDOUT])
    if env.get(EMIT_STDERR):
        sys.stderr.buffer.write(env[EMIT_STDERR].encode("utf-8") + b"\n")
        sys.stderr.buffer.flush()
    if env.get(EMIT_BYTES):
        sys.stdout.buffer.write(b"x" * int(env[EMIT_BYTES]))
        sys.stdout.buffer.flush()
    if env.get(HEARTBEAT_FILE):
        _heartbeat(env[HEARTBEAT_FILE])
    elif env.get(SLEEP):
        time.sleep(float(env[SLEEP]))
    return int(env.get(EXIT, "0"))


if __name__ == "__main__":
    sys.exit(main())
