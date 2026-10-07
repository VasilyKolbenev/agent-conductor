"""A deterministic stand-in for a pinned Grok Build binary, and a REAL executable.

Grok Build installs as a native binary, so its adapter pins ONE absolute path and
puts nothing in front of it. The executable is built by ``tests/_fakeexe.py``,
which produces a file the operating system really runs with no shell involved.

Every branch this child takes is chosen by a ``FAKEGROK_*`` environment knob
rather than by timing, an install, or a network, and importing this module never
runs the child body.

The hostile-child seam -- a child that replaces its own home with a portal --
is deliberately ABSENT here. That relation belongs to the shared workspace door
and is held once, against the dsh fake; carrying an unused copy of the machinery
would be forty lines no test drives.

Two things differ from the Kimi fake, and both are facts about Grok Build:

- the version print is a whole LINE, not a token: the vendor's entry point
  writes ``format!("grok {}\n", ...)`` and always stamps a commit, so the
  default knob emits exactly that and a test can ask for any other shape,
  published or refused;
- there are FOUR documented switches rather than one, so every spawn records all
  four values and a test can hold that this build turns each of them off.

Every spawn appends one JSON line to the spawn log, so a test can COUNT spawns
and read back the exact argv, cwd and Grok environment the adapter handed over.
That log is the evidence behind the version-mismatch gate: a mismatch must leave
zero prompt lines, not merely report a failure.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from tests import _fakeexe
from tests._fakeenv import probe_report

#: Where each spawn appends its one JSON line.
SPAWN_LOG = "FAKEGROK_SPAWN_LOG"
#: The whole line `--version` prints; the default is the form a real release
#: binary emits, spelled out at DEFAULT_VERSION below.
VERSION = "FAKEGROK_VERSION"
#: Bytes written to stdout / stderr by a prompt spawn (the secret-planting seam).
EMIT_STDOUT = "FAKEGROK_STDOUT"
EMIT_STDERR = "FAKEGROK_STDERR"
#: An output bomb, in bytes, written past any sane capture bound.
BOMB_BYTES = "FAKEGROK_BOMB_BYTES"
#: Seconds a prompt spawn sleeps before exiting; drives the real timeout path.
SLEEP = "FAKEGROK_SLEEP"
#: "relpath:text" written under the prompt's own cwd -- the evidence seam.
WRITE_FILE = "FAKEGROK_WRITE_FILE"
#: "relpath:text" written relative to the PARENT of the cwd, i.e. outside the
#: action's authorized subtree.
ESCAPE_FILE = "FAKEGROK_ESCAPE_FILE"
#: "relpath:text" written under the spawn's own GROK_HOME -- the seam a real
#: Grok Build fills with its config directory.
HOME_FILE = "FAKEGROK_HOME_FILE"
#: Exit code for a prompt spawn; `--version` always exits 0 unless this is set.
EXIT = "FAKEGROK_EXIT"
#: Non-empty makes `--version` itself fail, so the preflight refusal is testable.
VERSION_FAILS = "FAKEGROK_VERSION_FAILS"

#: A short commit of the shape a release binary stamps, so the DEFAULT print is
#: the one a real install produces rather than a shape it never emits.
DEFAULT_COMMIT = "abc1234"
#: The whole line `--version` prints by default: the reviewed semver dressed
#: exactly as the vendor's entry point dresses it -- `format!("grok {}\n", ...)`
#: with a commit always present, because `set_full_version` runs unconditionally.
#: The semver is read from the adapter rather than restated, because a fake that
#: carried its own copy would keep passing after the reviewed constant moved; the
#: DRESSING is spelled here, because that is this fake's own subject.
try:  # pragma: no cover -- the child runs with the package importable
    from conductor.command.adapters.grok_build import REVIEWED_GROK_VERSION

    DEFAULT_VERSION = f"grok {REVIEWED_GROK_VERSION} ({DEFAULT_COMMIT}) [stable]"
except ImportError:  # pragma: no cover -- never on a configured tree
    DEFAULT_VERSION = ""

#: The environment names this child reads back, so a test asserting the adapter's
#: environment does not spell them twice.
GROK_HOME_NAME = "GROK_HOME"
SWITCH_NAMES = (
    "GROK_TELEMETRY_ENABLED", "GROK_TELEMETRY_TRACE_UPLOAD",
    "GROK_TELEMETRY_MIXPANEL_ENABLED", "GROK_FEEDBACK_ENABLED")


def build_executable(directory: str | os.PathLike[str]) -> Path | None:
    """A REAL single-file executable standing in for the pinned grok binary."""
    return _fakeexe.build(directory, "grok", "_fakegrok")


def spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Every spawn recorded so far, oldest first; missing log means none."""
    try:
        text = Path(log_path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def prompt_spawns(log_path: str | os.PathLike[str]) -> list[dict]:
    """Only the spawns that really ran a prompt, never the version preflights."""
    return [row for row in spawns(log_path) if row["argv"][:1] != ["--version"]]


# --- the child body ----------------------------------------------------------


def _record(argv: list[str]) -> None:
    log = os.environ.get(SPAWN_LOG)
    if not log:
        return
    row = {
        "argv": argv,
        "cwd": os.getcwd(),
        "grok_home": os.environ.get(GROK_HOME_NAME),
        # All FOUR documented switches, by name, so a test holds every one of
        # them rather than the one that happened to be checked.
        "switches": {name: os.environ.get(name) for name in SWITCH_NAMES},
        "env_names": sorted(os.environ),
        # Two booleans about the parent's probe, and never a value. See
        # `tests/_fakeenv.py` for why an exact name set was not the question.
        "probe": probe_report(),
    }
    with open(log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_pair(base: Path, spec: str) -> None:
    relative, _, text = spec.partition(":")
    target = base / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def _run_prompt() -> int:
    env = os.environ
    if env.get(WRITE_FILE):
        _write_pair(Path.cwd(), env[WRITE_FILE])
    if env.get(ESCAPE_FILE):
        _write_pair(Path.cwd().parent, env[ESCAPE_FILE])
    if env.get(HOME_FILE) and env.get(GROK_HOME_NAME):
        _write_pair(Path(env[GROK_HOME_NAME]), env[HOME_FILE])
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
    return _run_prompt()


if __name__ == "__main__":
    sys.exit(main())
