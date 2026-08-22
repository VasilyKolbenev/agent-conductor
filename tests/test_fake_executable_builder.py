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

import pytest

from tests._fakeexe import _shebang_interpreter, build, launcher_stub

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


def test_this_environment_really_builds_an_executable_the_suites_can_use():
    """The one claim that would make 68 tests skip, asserted rather than assumed.

    If this environment genuinely cannot build one, this test SKIPS with the
    cause named -- which is the honest answer, and different from the two
    provider suites skipping for a reason nobody reads.
    """
    if launcher_stub() is None:
        pytest.skip(
            "this environment ships no console-script launcher to copy, so the "
            "provider transport suites will skip too -- that is the cause")
    built = build(
        __import__("tempfile").mkdtemp(prefix="fakeexe-"), "probe", "_fakegrok")

    assert built is not None, (
        "a launcher stub was found and yet no executable was produced, so the "
        "provider suites are skipping for a reason the message does not name")
    assert built.is_file()
