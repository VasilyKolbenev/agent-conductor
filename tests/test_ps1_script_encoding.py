"""A script written for Windows PowerShell survives a non-ASCII path, and a failure says why.

The native tests write a ``.ps1`` for a child, with absolute paths from the pytest base directory
inside it. On a machine whose profile is ``C:\\Users\\Пользователь`` that path is Cyrillic, and a
script written without a byte order mark is read by Windows PowerShell 5.1 in the ANSI code page:
the 0x82 byte of «т» becomes a quotation mark, the parse fails and no line runs (the finding of
``docs/recovery/2026-10-20/tasks/N1-NATIVE-CYRILLIC.md``). These tests do not depend on the name of
the machine's profile: the Cyrillic directory is made under ``tmp_path``, so a runner with an
ASCII profile meets the same bytes. The first two tests run everywhere, the rest on Windows only.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from tests._ps1 import SCRIPT_ENCODING, child_text, strict_text, write_ps1

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell 5.1 reads the script")

FOLDER = "Пользователь-т"
LITERAL = "т-ль"
#: The UTF-8 bytes of `LITERAL` as the child prints them: ASCII, whatever the console's code page.
SEEN = b"D1-82-2D-D0-BB-D1-8C"
EXPECTED = SEEN + b";True"


def _q(path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _probe(folder) -> str:
    """A script with a Cyrillic literal and a Cyrillic path: it prints the literal's bytes and
    whether the directory it was written in exists."""
    return (f"[Console]::Out.Write([BitConverter]::ToString([Text.Encoding]::UTF8.GetBytes("
            f"{_q(LITERAL)})) + ';' + [IO.Directory]::Exists({_q(folder)}))")


def _run(script) -> subprocess.CompletedProcess:
    """The command line the native tests give a child, without the container: it is not a factor."""
    from tests import os_boundary_windows as ac
    return subprocess.run(
        [str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script)], stdin=subprocess.DEVNULL, capture_output=True, timeout=60)


def _cyrillic_folder(tmp_path):
    folder = tmp_path / FOLDER
    folder.mkdir()
    return folder


def test_a_script_is_written_with_a_byte_order_mark_and_the_text_follows_as_written(tmp_path):
    text = "$o = 'т-ль'\n[Console]::Out.Write($o)"
    path = write_ps1(tmp_path / "entry.ps1", text)
    written = path.read_bytes()
    assert SCRIPT_ENCODING == "utf-8-sig" and written.startswith(b"\xef\xbb\xbf")
    assert written[3:] == text.encode("utf-8"), "the text changed on its way to the file"
    assert b"\r" not in written, "a newline was translated"


def test_output_that_is_not_utf8_fails_with_what_the_child_said_and_utf8_is_read_exactly():
    assert strict_text("work=ok;т=1".encode("utf-8")) == "work=ok;т=1"
    said = "Отсутствует закрывающая скобка".encode("cp866")
    with pytest.raises(AssertionError, match="not UTF-8") as caught:
        strict_text(said)
    if os.name == "nt":
        assert said.decode("oem", errors="replace") in str(caught.value)
        assert child_text(said) == said.decode("oem", errors="replace")
    assert child_text(b"plain ascii") == "plain ascii"


@windows_only
def test_windows_powershell_runs_a_script_with_a_cyrillic_literal_from_a_cyrillic_directory(
        tmp_path):
    folder = _cyrillic_folder(tmp_path)
    script = write_ps1(folder / "entry.ps1", _probe(folder))
    done = _run(script)
    assert done.returncode == 0, child_text(done.stdout + done.stderr)
    assert done.stdout == EXPECTED, child_text(done.stdout + done.stderr)


@windows_only
def test_the_same_script_without_the_mark_is_not_read_as_written(tmp_path):
    """The witness: what `write_ps1` prevents does happen, so the test above can fail."""
    import ctypes
    if ctypes.windll.kernel32.GetACP() == 65001:
        pytest.skip("the system code page is UTF-8: a script without a mark is read as UTF-8")
    folder = _cyrillic_folder(tmp_path)
    plain = folder / "plain.ps1"
    plain.write_bytes(_probe(folder).encode("utf-8"))
    done = _run(plain)
    assert done.stdout != EXPECTED, "a script without the mark ran as written: not a witness"
