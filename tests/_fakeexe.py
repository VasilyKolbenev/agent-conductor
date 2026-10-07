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

**And it was wrong a second time, in the DIRECTORY rather than the bytes.** The
search looked only in ``Path(sys.executable).parent``. In a virtualenv that is
``Scripts`` and the search works, which is why every local run was green. On a
plain Windows install -- the layout ``actions/setup-python`` produces, and the
one CI uses -- ``sys.executable`` sits in the install ROOT and the console
scripts sit in ``Scripts`` one level down, so nothing was ever found. Measured on
this machine at Python 3.11.8: zero candidates in the searched directory, all
three in the one ``sysconfig`` names. The cost was **277 tests across four
provider transport suites skipping while CI stayed green**, which is the worst
shape a gate can take -- it reports on work it did not do.

So the directories are asked of ``sysconfig``, which is the interpreter's own
answer to where it installs console scripts, and the old directory is kept
beside it rather than replaced: dropping it would be an over-correction on a
layout nobody has measured. Both are searched, in that order, deduplicated.
"""
from __future__ import annotations

import io
import os
import stat
import sys
import sysconfig
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
    shebang = stub[marker + 2:].strip()
    if not shebang:
        return None
    # Two shapes, and reading only one of them has now been wrong twice. A path
    # containing a space is QUOTED, so it must be read to its closing quote and
    # not split on whitespace; an unquoted path may be FOLLOWED by interpreter
    # flags (`#!C:\\...\\python.exe -X utf8`), so the whole remainder must not be
    # required to end in `.exe`. Take the quoted run when there is one, the first
    # token otherwise.
    if shebang.startswith(b'"'):
        closing = shebang.find(b'"', 1)
        interpreter = shebang[1:closing] if closing > 0 else b""
    else:
        interpreter = shebang.split()[0]
    return interpreter if interpreter.lower().endswith(b".exe") else None


def script_directories() -> tuple[Path, ...]:
    """Every directory this interpreter could keep its console scripts in.

    ``sysconfig`` FIRST, because it is the interpreter's own answer and it is
    right on both layouts: in a virtualenv it names that venv's ``Scripts``, and
    on a plain install it names ``<prefix>/Scripts`` rather than the install root
    where ``sys.executable`` lives. Asking only the second is the defect this
    function exists to close.

    The old directory is kept rather than replaced. It is the same path as the
    first one inside a venv, so it costs nothing there; and on some layout nobody
    here has measured it may be the only right answer. Removing it would be an
    over-correction, and a test holds that it stays.

    Deduplicated by RESOLVED path, so a venv does not read the same directory
    twice, and ordered, so the interpreter's own answer is preferred.
    """
    found: dict[Path, None] = {}
    for raw in (sysconfig.get_path("scripts"), Path(sys.executable).parent):
        try:
            resolved = Path(raw).resolve()
        except OSError:  # pragma: no cover -- a path the OS will not resolve
            continue
        found.setdefault(resolved, None)
    return tuple(found)


def _stub_in(directory: Path) -> bytes | None:
    """The launcher stub in ONE directory, or None if it holds none.

    A candidate must be BOTH halves of a console script: a native launcher body
    carrying an interpreter in a trailing ``#!``, and an appended zip. Neither
    check may be dropped for the other's sake. Without the zip offset an
    ordinary ``.exe`` would be copied whole and the appended archive would never
    be found; without the shebang read, any file with a zip inside it -- a wheel,
    an egg, a plain archive somebody renamed -- would be accepted as a launcher
    and produce an executable that runs nothing.
    """
    for name in _CANDIDATES:
        candidate = directory / name
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


def launcher_stub() -> bytes | None:
    """The console-script launcher this environment ships, or None."""
    for directory in script_directories():
        stub = _stub_in(directory)
        if stub is not None:
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
