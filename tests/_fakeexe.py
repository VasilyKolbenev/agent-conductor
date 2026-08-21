"""Build a REAL single-file executable for a fake whose provider pins one binary.

Two products in the roster install as native binaries, so their adapters pin ONE
absolute path and put nothing in front of it. A fake driven through
``sys.executable`` would exercise the interpreter-and-entrypoint shape instead
and would quietly prove nothing about theirs, so this produces a file the
operating system really runs.

On Windows that means reusing the console-script launcher stub the environment
already ships: ``pip.exe`` and friends are a small native launcher followed by an
appended zip holding ``__main__.py``, with the interpreter carried in a trailing
``#!`` line. The stub is copied byte-for-byte and a new zip appended, so the
result needs no shell -- which matters, because this build never spawns through
one. Elsewhere an executable ``#!`` script is enough.

It lives here rather than in either fake because the stub reading is the part
that was WRONG once and must never be wrong in two places: the check used to
match the tail against ``.exe``, and a launcher whose interpreter path contains a
space carries it QUOTED, so it rejected a working stub and made a whole test
module skip behind a message blaming the platform.
"""
from __future__ import annotations

import io
import os
import stat
import sys
import zipfile
from pathlib import Path

#: Console scripts this environment is likely to ship, tried in order.
_CANDIDATES = ("pip.exe", "pytest.exe", "pip3.exe")


def _shebang_interpreter(stub: bytes) -> bytes | None:
    """The interpreter a launcher stub carries, or None if it carries none.

    Read from the LAST ``#!`` and unquoted, rather than by matching the tail's
    suffix. The suffix test looked equivalent and was not: an interpreter path
    containing a space is quoted, so ``endswith(".exe")`` rejected a perfectly
    good stub.
    """
    marker = stub.rfind(b"#!")
    if marker < 0:
        return None
    interpreter = stub[marker + 2:].strip().strip(b'"')
    return interpreter if interpreter.lower().endswith(b".exe") else None


def launcher_stub() -> bytes | None:
    """The console-script launcher this environment ships, or None."""
    scripts = Path(sys.executable).resolve().parent
    for name in _CANDIDATES:
        candidate = scripts / name
        if not candidate.is_file():
            continue
        data = candidate.read_bytes()
        start = data.find(b"PK\x03\x04")
        if start <= 0:
            continue
        stub = data[:start]
        if _shebang_interpreter(stub) is not None:
            return stub
    return None


def _body(repo_root: Path, module: str) -> str:
    """The child's entry point: reach the fake's module, then run its main.

    Both roots are baked in because the child inherits NO ``PYTHONPATH`` -- the
    adapter passes only the environment names the operator allowed, which is the
    whole point of the allowlist. Baking the reviewed VERSION instead would give
    a fake its own copy of the number and let it keep passing after the real
    constant moved, so the fakes read that from the adapter at runtime.
    """
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(repo_root / 'src')!r})\n"
        f"sys.path.insert(0, {str(repo_root)!r})\n"
        f"from tests.{module} import main\n"
        "sys.exit(main())\n")


def build(directory: str | os.PathLike[str], stem: str, module: str) -> Path | None:
    """A REAL single-file executable that runs ``tests.<module>.main``.

    Returns None when this platform grants no way to build one without a shell,
    so a caller SKIPS instead of quietly testing the wrong pin shape.
    """
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parent.parent
    if os.name == "nt":
        stub = launcher_stub()
        if stub is None:
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("__main__.py", _body(repo_root, module))
        exe = target / f"{stem}.exe"
        exe.write_bytes(stub + buffer.getvalue())
        return exe.resolve()
    script = target / stem
    script.write_text(
        f"#!{sys.executable}\n" + _body(repo_root, module), encoding="utf-8",
        newline="\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return script.resolve()
