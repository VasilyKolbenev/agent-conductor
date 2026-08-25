"""The builder two provider suites depend on, held by tests that cannot skip.

``tests/_fakeexe.py`` decides whether 68 tests across the Kimi Code and Grok
Build suites RUN or skip. When it answers None those suites skip, quietly, and a
skip is green -- so a fault in the stub reader silently removes both providers'
transport coverage and nothing says so. That has already happened once: the
reader required the whole post-``#!`` remainder to end in ``.exe``, which
discards a launcher whose interpreter path is quoted because it contains a space.

So the reader is held here directly, against synthetic bytes, with no launcher,
no platform primitive and no install involved. Nothing in this module can skip.

The two shapes are held together on purpose. Reading only one of them has now
been wrong twice, in opposite directions: a QUOTED path must be read to its
closing quote and not split on whitespace, and an UNQUOTED path may be followed
by interpreter flags, so the remainder must not be required to end in ``.exe``.
A fix for either alone breaks the other.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from tests._fakeexe import (
    _shebang_interpreter,
    _stub_in,
    build,
    launcher_stub,
    script_directories,
)

#: A real zip, so a candidate that carries one is refused for the reason under
#: test rather than because its bytes were not an archive at all.
_ZIP = None


def _zip_bytes() -> bytes:
    global _ZIP
    if _ZIP is None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("__main__.py", "raise SystemExit(0)\n")
        _ZIP = buffer.getvalue()
    return _ZIP

#: (stub tail, whether an interpreter should be read out of it). The leading NUL
#: bytes stand in for the launcher body a real stub carries before its shebang.
SHEBANGS = (
    (b"\x00\x00#!C:\\py\\python.exe", True),
    (b'\x00\x00#!"C:\\Program Files\\Py\\python.exe"', True),
    (b"\x00\x00#!C:\\py\\python.exe -X utf8", True),
    (b'\x00\x00#!"C:\\Program Files\\Py\\python.exe" -X utf8', True),
    (b"\x00\x00#!C:\\py\\PYTHON.EXE", True),
    (b"\x00\x00#!C:\\py\\python", False),
    (b'\x00\x00#!"C:\\Program Files\\Py\\python"', False),
    (b"\x00\x00#!", False),
    (b"\x00\x00#!   ", False),
    (b'\x00\x00#!"unterminated.exe', False),
    (b"no shebang at all", False),
)


@pytest.mark.parametrize("tail,readable", SHEBANGS)
def test_the_stub_reader_accepts_a_quoted_path_and_a_flagged_one(tail, readable):
    """Both published shapes, and the near-misses that must still be refused."""
    assert (_shebang_interpreter(tail) is not None) is readable, (
        f"the reader disagrees about {tail!r}")


def test_a_quoted_interpreter_path_keeps_its_spaces():
    """The whole point of reading to the closing quote rather than splitting."""
    read = _shebang_interpreter(b'\x00#!"C:\\Program Files\\Py\\python.exe" -X utf8')

    assert read == b"C:\\Program Files\\Py\\python.exe"


def test_the_search_covers_both_layouts_a_windows_python_really_ships(
        monkeypatch, tmp_path):
    """Born of the second defect: the search knew only one of the two layouts.

    SIMULATED rather than sampled, and that is the whole design of this test. On
    the machine a developer usually runs it on, a virtualenv puts
    ``sys.executable`` INSIDE ``Scripts``, so the two answers are the same
    directory and an ambient assertion passes whether the search consults
    ``sysconfig`` or not -- it would have passed every day the defect was live.
    Two DISTINCT directories are injected here, so the test can see which of
    them the search really reaches.

    Both directions are held. Dropping the ``sysconfig`` answer is the original
    defect: on a plain Windows install the scripts sit one level below
    ``sys.executable`` and 277 tests skipped while CI stayed green. Dropping the
    interpreter's own directory would be the over-correction, and there is no
    layout here that measured it as wrong.
    """
    prefix = tmp_path / "Python311"
    scripts = prefix / "Scripts"
    scripts.mkdir(parents=True)
    monkeypatch.setattr("sysconfig.get_path", lambda name, *a, **k: (
        str(scripts) if name == "scripts" else str(prefix)))
    monkeypatch.setattr("sys.executable", str(prefix / "python.exe"))

    searched = script_directories()

    assert scripts.resolve() in searched, (
        "the search skips the directory this interpreter installs console "
        "scripts into -- exactly how 277 tests skipped while CI reported green")
    assert prefix.resolve() in searched, (
        "the search dropped the interpreter's own directory, which is where a "
        "virtualenv really keeps its console scripts")


def test_a_real_shaped_console_script_yields_its_stub(tmp_path):
    """The positive control. Without it the two refusals below would be
    satisfied by a reader that refused everything."""
    stub = b"MZ\x00\x00\x00#!C:\\py\\python.exe"
    (tmp_path / "pip.exe").write_bytes(stub + _zip_bytes())

    assert _stub_in(tmp_path) == stub


def test_a_file_carrying_a_zip_but_no_interpreter_is_not_a_launcher(tmp_path):
    """The over-correction guard: a wheel, an egg, or any renamed archive.

    Dropping the shebang read would accept this and produce an "executable"
    that runs nothing at all -- and the provider suites would then fail for a
    reason no message names, which is worse than the skip this replaced.
    """
    (tmp_path / "pip.exe").write_bytes(b"MZ\x00\x00" + _zip_bytes())

    assert _stub_in(tmp_path) is None


def test_a_launcher_with_no_appended_zip_is_not_a_launcher(tmp_path):
    """The other half. Copied whole, such a file would carry no ``__main__``.

    Held separately from the case above because the two are refused by
    different checks, and a fix for either alone leaves the other open.
    """
    (tmp_path / "pip.exe").write_bytes(b"MZ\x00\x00\x00#!C:\\py\\python.exe")

    assert _stub_in(tmp_path) is None


def test_this_environment_really_builds_an_executable_the_suites_can_use(tmp_path):
    """The one claim that decides whether 277 tests RUN, asserted, never skipped.

    This test used to skip when no stub was found, and that skip was the defect
    wearing a disguise: on the layout CI really uses, the stub search failed,
    this test skipped, the four transport suites skipped, and every one of them
    was green. A guard that disappears under exactly the condition it exists to
    detect is not a guard.

    So it may not skip on any platform now. Windows takes the launcher road and
    POSIX takes the ``#!`` road, and ``build`` answers for both: whichever road
    this platform has, it must really produce a file.
    """
    built = build(tmp_path, "probe", "_fakegrok")

    assert built is not None, (
        "this environment produced no fake executable, so the four provider "
        "transport suites are about to skip -- 277 tests reporting green "
        "without running. Fix the builder rather than accepting the skip")
    assert built.is_file()
    assert Path(built).stat().st_size > 0
