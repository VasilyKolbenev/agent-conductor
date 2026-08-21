"""A deterministic stand-in for a pinned Kimi Code binary, and a REAL executable.

Kimi Code installs as a native binary, so its adapter pins ONE absolute path and
puts nothing in front of it. A fake that needed an interpreter in front would be
testing a pin shape this provider does not have, so ``build_executable`` produces
a file the operating system really runs on its own:

- on Windows, by reusing the console-script launcher stub the environment already
  ships (``pip.exe`` and friends are a small launcher followed by an appended zip
  holding ``__main__.py``). The stub is copied byte-for-byte and a new zip is
  appended, so the result is a genuine ``.exe`` that needs no shell -- which
  matters, because this build never spawns through one;
- elsewhere, by writing an executable script with a ``#!`` line.

Either way the child body is the one below, so there is exactly one copy of the
fake's behaviour. Every branch it takes is chosen by a ``FAKEKIMI_*``
environment knob rather than by timing, an install, or a network, and importing
this module never runs the child body.

Every spawn appends one JSON line to the spawn log, so a test can COUNT spawns
and read back the exact argv, cwd and Kimi environment the adapter handed over.
That log is the evidence behind the version-mismatch gate: a mismatch must leave
zero prompt lines, not merely report a failure.
"""
from __future__ import annotations

import io
import json
import os
import stat
import sys
import time
import zipfile
from pathlib import Path

#: Where each spawn appends its one JSON line.
SPAWN_LOG = "FAKEKIMI_SPAWN_LOG"
#: The token `--version` prints; default is the version the adapter reviewed.
VERSION = "FAKEKIMI_VERSION"
#: Bytes written to stdout / stderr by a prompt spawn (the secret-planting seam).
EMIT_STDOUT = "FAKEKIMI_STDOUT"
EMIT_STDERR = "FAKEKIMI_STDERR"
#: An output bomb, in bytes, written past any sane capture bound.
BOMB_BYTES = "FAKEKIMI_BOMB_BYTES"
#: Seconds a prompt spawn sleeps before exiting; drives the real timeout path.
SLEEP = "FAKEKIMI_SLEEP"
#: "relpath:text" written under the prompt's own cwd -- the evidence seam.
WRITE_FILE = "FAKEKIMI_WRITE_FILE"
#: "relpath:text" written relative to the PARENT of the cwd, i.e. outside the
#: action's authorized subtree.
ESCAPE_FILE = "FAKEKIMI_ESCAPE_FILE"
#: "relpath:text" written under the spawn's own KIMI_CODE_HOME -- the seam a real
#: Kimi Code fills with config, sessions, logs and OAuth credentials.
HOME_FILE = "FAKEKIMI_HOME_FILE"
#: An absolute path the child REPLACES its own KIMI_CODE_HOME with, as a portal.
HOME_PORTAL = "FAKEKIMI_HOME_PORTAL"
#: Where the child records which portal kind it managed to plant, relative to
#: its own cwd; ``none`` means the platform granted neither primitive.
PORTAL_WITNESS = "home-portal-kind.txt"
#: Exit code for a prompt spawn; `--version` always exits 0 unless this is set.
EXIT = "FAKEKIMI_EXIT"
#: Non-empty makes `--version` itself fail, so the preflight refusal is testable.
VERSION_FAILS = "FAKEKIMI_VERSION_FAILS"

#: The version the adapter was written against, so the default path is the happy
#: one. Read from the adapter rather than restated, because a fake that carried
#: its own copy would keep passing after the reviewed constant moved.
try:  # pragma: no cover -- the child runs with the package importable
    from conductor.command.adapters.kimi_code import REVIEWED_KIMI_VERSION

    DEFAULT_VERSION = REVIEWED_KIMI_VERSION
except ImportError:  # pragma: no cover -- never on a configured tree
    DEFAULT_VERSION = ""

#: The name every knob above shares, so a test can pass the whole family through
#: an operator's env_allow without spelling them one at a time.
KNOBS = (
    SPAWN_LOG, VERSION, EMIT_STDOUT, EMIT_STDERR, BOMB_BYTES, SLEEP,
    WRITE_FILE, ESCAPE_FILE, HOME_FILE, HOME_PORTAL, EXIT, VERSION_FAILS)


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


# --- building a file the operating system really executes ---------------------


def _launcher_stub() -> bytes | None:
    """The console-script launcher this environment already ships, or None.

    A console script on Windows is a small native launcher followed by an
    appended zip holding ``__main__.py``; the launcher carries the interpreter
    path in a trailing ``#!`` line. Copying the stub and appending a different
    zip is how a genuine single-file executable is produced here without any
    build tool -- and if the layout is ever not this, the caller skips rather
    than falling back to a shim that would need a shell.
    """
    scripts = Path(sys.executable).resolve().parent
    for name in ("pip.exe", "pytest.exe", "pip3.exe"):
        candidate = scripts / name
        if not candidate.is_file():
            continue
        data = candidate.read_bytes()
        start = data.find(b"PK\x03\x04")
        if start > 0 and data[:start].rstrip().endswith(b".exe"):
            return data[:start]
    return None


def _body(repo_root: Path) -> str:
    """The child's entry point: reach this module, then run its main.

    Both roots are baked in because the child inherits NO ``PYTHONPATH``: the
    adapter passes only the environment names the operator allowed, which is the
    whole point of the allowlist. Baking the paths keeps the fake's behaviour in
    one place; baking the reviewed VERSION instead would give the fake its own
    copy of the number and let it keep passing after the real constant moved.
    """
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(repo_root / 'src')!r})\n"
        f"sys.path.insert(0, {str(repo_root)!r})\n"
        "from tests._fakekimi import main\n"
        "sys.exit(main())\n")


def build_executable(directory: str | os.PathLike[str]) -> Path | None:
    """A REAL single-file executable standing in for the pinned kimi binary.

    Returns None when this platform grants no way to build one without a shell,
    so a caller skips instead of quietly testing the wrong pin shape.
    """
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parent.parent
    if os.name == "nt":
        stub = _launcher_stub()
        if stub is None:
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("__main__.py", _body(repo_root))
        exe = target / "kimi.exe"
        exe.write_bytes(stub + buffer.getvalue())
        return exe.resolve()
    script = target / "kimi"
    script.write_text(
        f"#!{sys.executable}\n" + _body(repo_root), encoding="utf-8",
        newline="\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return script.resolve()


# --- the child body ----------------------------------------------------------


def _record(argv: list[str]) -> None:
    log = os.environ.get(SPAWN_LOG)
    if not log:
        return
    row = {
        "argv": argv,
        # What the OS actually started, so a test can see IN FRONT of the pin.
        # Recording only argv[1:] made "one pinned binary is the whole command"
        # unfalsifiable: an interpreter, a shell, or any prefix at all would have
        # been invisible to it.
        "argv0": sys.argv[0],
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "kimi_home": os.environ.get("KIMI_CODE_HOME"),
        "telemetry_disabled": os.environ.get("KIMI_DISABLE_TELEMETRY"),
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
    """Swap this spawn's own KIMI_CODE_HOME for a portal at the very same name.

    The parent minted a directory here and remembers the name; a child that
    replaces it with a junction or a symbolic link is the hostile case the
    workspace door's cleanup was rebuilt for. Returns the kind actually planted,
    so a test reads what happened from the child rather than assuming it.
    """
    home = Path(os.environ.get("KIMI_CODE_HOME", ""))
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


def _run_prompt() -> int:
    env = os.environ
    if env.get(WRITE_FILE):
        _write_pair(Path.cwd(), env[WRITE_FILE])
    if env.get(ESCAPE_FILE):
        _write_pair(Path.cwd().parent, env[ESCAPE_FILE])
    if env.get(HOME_FILE) and env.get("KIMI_CODE_HOME"):
        _write_pair(Path(env["KIMI_CODE_HOME"]), env[HOME_FILE])
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
    return _run_prompt()


if __name__ == "__main__":
    sys.exit(main())
