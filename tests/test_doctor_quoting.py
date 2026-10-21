"""A printed `conduct doctor` command, held against the shells it is pasted into.

`test_doctor.py` and `test_doctor_printed.py` hold the rule from the inside:
which tokens `doctor.spell` quotes, and that a printed line reads back as the
argv it was spelled from. This module holds what the rule is FOR. A line a
person pastes into cmd, Windows PowerShell 5.1, POSIX sh or zsh must reach
`conduct` as exactly the argv the report named, and quoting a token is not
enough to get there in two places:

* A quoted token that ends in a backslash. The C runtime (`CommandLineToArgvW`)
  reads `\\"` as a literal quote, so `"C:\\x\\"` loses its closing quote:
  `spell` doubles a closing backslash. And Windows PowerShell 5.1 hands a
  quoted token WITHOUT a space to the program bare, doubling and all, so
  `inspect` never prints a directory root with a separator on the end: an
  anchor (`C:\\`, `\\`, `/`) is printed with a closing dot, `C:\\.`.
* A root `argparse` would read as a flag. `conduct doctor --dir -proj` is a
  usage error, so a root that opens with a dash is printed from the current
  directory, `./-proj`. (The tests hand such a root in as `--dir=-proj`: that
  spelling is the one way it reaches `main` at all.)

Kept apart from `test_doctor.py` because that file is close to the 800-line
limit. The fixtures come from it the way `test_doctor_claims.py` takes them,
and nothing imports this module, so there is no cycle.

Three kinds of measurement, cheapest first: `spell` against literal lines, a
Windows-only oracle that parses a printed token the way the C runtime does, and
the real shells (cmd and Windows PowerShell 5.1 on Windows, `/bin/sh` and zsh
elsewhere) running a stub that prints the argv it was given.
"""
import base64
import ctypes
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conductor import doctor
from conductor.__main__ import main
from tests.test_doctor import (
    TWO_ROLE_MAP, commands, lane, ran, report, role_map, write_project)

WINDOWS = sys.platform == "win32"


@pytest.mark.parametrize("argv, line", [
    # A closing backslash is doubled, the CRT's rule; an inner one is not.
    (("doctor", "--dir", "C:\\Мой проект\\"), 'conduct doctor --dir "C:\\Мой проект\\\\"'),
    (("doctor", "--dir", "C:\\"), 'conduct doctor --dir "C:\\\\"'),
    (("doctor", "--dir", "C:\\a\\\\"), 'conduct doctor --dir "C:\\a\\\\\\\\"'),
    (("doctor", "--dir", "C:\\a b"), 'conduct doctor --dir "C:\\a b"'),
    (("doctor", "--dir", "C:\\."), 'conduct doctor --dir "C:\\."'),
    # A backslash is an escape to POSIX sh wherever a token goes unquoted.
    (("doctor", "--dir", "ascii\\unheld"), 'conduct doctor --dir "ascii\\unheld"'),
    # `@` splats in PowerShell, `,` is its array operator, `~` is sh's home,
    # `=` is zsh's command-path expansion: each opens a word and changes it.
    (("prompt", "--role", "@scout"), 'conduct prompt --role "@scout"'),
    (("prompt", "--role", "a@b"), 'conduct prompt --role "a@b"'),
    (("prompt", "--role", "scout,07"), 'conduct prompt --role "scout,07"'),
    (("prompt", "--role", "=scout"), 'conduct prompt --role "=scout"'),
    (("prompt", "--role", "a=b"), 'conduct prompt --role "a=b"'),
    (("doctor", "--dir", "~"), 'conduct doctor --dir "~"'),
    # And what stays bare: every character the three shells read as itself.
    (("doctor", "--dir", "./-proj"), "conduct doctor --dir ./-proj"),
    (("prompt", "--role", "a.b:c/d+e_g-h"), "conduct prompt --role a.b:c/d+e_g-h"),
])
def test_spell_quotes_what_a_shell_would_change_and_doubles_a_closing_backslash(argv, line):
    assert doctor.spell(argv) == line


@pytest.mark.skipif(not WINDOWS, reason="CommandLineToArgvW is the Windows CRT's rule")
@pytest.mark.parametrize("token", ["C:\\Мой проект\\", "C:\\", "C:\\a\\\\", "\\\\srv\\s p\\",
                                   "C:\\a b", "C:\\.", "\\.", "\\\\srv\\s p\\.", "@scout",
                                   "scout,07", "=scout"])
def test_a_crt_program_reads_the_printed_token_back_as_itself(token):
    # The oracle for the doubling rule, with no process in the way: the same
    # parser every CRT program starts with, handed the printed line.
    shell32 = ctypes.windll.shell32
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    parsed = shell32.CommandLineToArgvW(doctor.spell(("--dir", token)), ctypes.byref(count))
    try:
        assert [parsed[i] for i in range(count.value)] == ["conduct", "--dir", token]
    finally:
        ctypes.windll.kernel32.LocalFree(parsed)


@pytest.mark.parametrize("seps", [1, 2])
def test_a_root_typed_with_trailing_separators_is_printed_without_them(tmp_path, capsys, seps):
    root = tmp_path / "Мой проект"
    root.mkdir()
    out = report(capsys, str(root) + os.sep * seps, 1)
    (argv,) = commands(out)
    assert argv[-2:] == ["--dir", str(root)]
    assert main(argv) == 0
    capsys.readouterr()


def test_an_empty_root_names_no_dir_rather_than_an_empty_one(tmp_path, monkeypatch):
    # Windows PowerShell 5.1 drops an empty argument, which leaves `--dir`
    # with no value; `Path("")` is the current directory, which needs no flag.
    monkeypatch.chdir(tmp_path)
    assert all("--dir" not in check.command for check in doctor.inspect(""))


@pytest.mark.parametrize("typed", ["-proj", "./-proj", "." + os.sep + "-proj" + os.sep,
                                   "." + os.sep + "--"])
def test_a_root_that_would_open_with_a_dash_is_printed_from_the_current_directory(
        tmp_path, capsys, monkeypatch, typed):
    # `.\-proj` is normalised to `-proj`, and `--dir -proj` is exit 2. The
    # root that is all dashes is typed `.\--`, not `--`: argparse on CPython
    # 3.11 drops the first `--` even from an option's value (bpo-14364,
    # `--dir=--` gives no value), so the bare form would fail in the parser
    # before it reached the rule, on the three OS the CI runs 3.11 on.
    monkeypatch.chdir(tmp_path)
    name = typed.strip("./" + os.sep)
    (tmp_path / name).mkdir()
    assert main(["doctor", f"--dir={typed}"]) == 1
    (argv,) = commands(capsys.readouterr().out)
    assert argv[-2:] == ["--dir", "./" + name]
    assert ran(argv) == 0
    capsys.readouterr()
    assert (tmp_path / name / "conductor").is_dir()


def test_a_project_that_would_open_with_a_dash_gets_its_role_prompt_from_the_current_directory(
        tmp_path, capsys, monkeypatch):
    # The same rule once the project exists: every check is handed the root as
    # printed, so the role check's `prompt` runs too, not only the `init`.
    monkeypatch.chdir(tmp_path)
    write_project(tmp_path / "-proj", map_toml=TWO_ROLE_MAP, lanes={"claude": lane()})
    assert main(["doctor", f"--dir=.{os.sep}-proj"]) == 1
    argv = next(a for a in commands(capsys.readouterr().out) if a[0] == "prompt")
    assert argv == ["prompt", "--role", "reviewer", "--dir", "./-proj"]
    assert ran(argv) == 0
    capsys.readouterr()


def _anchors(tmp_path):
    if WINDOWS:
        drive = Path(tmp_path).anchor
        return [drive, drive.replace("\\", "/"), "\\", "/"]
    return ["/", "//"]


def test_an_anchor_is_printed_with_a_closing_dot_rather_than_a_closing_separator(tmp_path):
    # Not run: the command for an unscaffolded root is `init`, and `init` would
    # scaffold the root of the drive. The value is read, not executed. A UNC
    # share is left out as well: `inspect` would go to the network for it.
    for typed in _anchors(tmp_path):
        for check in doctor.inspect(typed):
            argv = list(check.command)
            if "--dir" in argv:
                value = argv[argv.index("--dir") + 1]
                assert value.endswith(".") and Path(value) == Path(typed), (typed, value)


@pytest.mark.parametrize("role_id", ["@scout", "a,b", "scout,07", "x.y", "a:b", "a=b", "a+b",
                                     "=scout"])
def test_an_authored_id_a_shell_can_carry_quoted_still_gets_its_prompt(tmp_path, capsys,
                                                                       role_id):
    # Green before the change and after it: quoting `@` and `,` is not the same
    # as refusing them. `_AUTHORED_CHARS` is what decides whether an id earns a
    # printed `prompt`, and it must not shrink with `_BARE_CHARS`.
    root = write_project(tmp_path, map_toml=role_map(role_id), lanes={"claude": lane()})
    out = report(capsys, root, 1)
    argv = next(a for a in commands(out) if a[0] == "prompt")
    assert argv[:3] == ["prompt", "--role", role_id]
    assert ran(argv) == 0
    capsys.readouterr()


#: What the stand-in for `conduct` does: say, one line per run, the argv it got.
STUB = 'import json, sys\nsys.stdout.write("ARGV:" + json.dumps(sys.argv[1:]) + "\\n")\n'


def _argvs(stdout):
    """The argv lines of a shell run, and the shell's own `ERR:` lines, in order."""
    return [json.loads(ln[5:]) if ln.startswith("ARGV:") else ln
            for ln in stdout.decode("utf-8", "replace").splitlines()
            if ln.startswith(("ARGV:", "ERR:"))]


def _printed_for(*typed):
    """Every command `doctor.inspect` prints for these roots, as argv."""
    return [check.command for root in typed for check in doctor.inspect(root)
            if check.command]


def _windows_cases(tmp_path):
    root = tmp_path / "Мой проект"
    root.mkdir()
    (tmp_path / "-proj").mkdir()
    # Roots go through `inspect` so that it is the rule that is measured, and
    # not a raw token a reader never gets printed.
    return _printed_for(str(root) + "\\", Path(tmp_path).anchor, "\\", "-proj") + [
        ("prompt", "--role", "@scout", "--dir", "C:\\p q"),
        ("prompt", "--role", "scout,07"), ("prompt", "--role", "=scout"),
        ("doctor", "--dir", "x,07\\unheld"),
        ("doctor", "--dir", "C:\\Program Files (x86)\\p&q")]


@pytest.mark.skipif(not WINDOWS, reason="cmd and Windows PowerShell 5.1")
@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="no Windows PowerShell")
def test_printed_lines_reach_a_program_from_cmd_and_powershell_as_their_argv(tmp_path,
                                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub = tmp_path / "argv.py"
    stub.write_text(STUB, encoding="utf-8")
    cases = _windows_cases(tmp_path)
    tails = [doctor.spell(tuple(argv))[len("conduct "):] for argv in cases]
    # cmd, one process per line. `/s` strips exactly the outer pair of quotes
    # added here, so the printed tail reaches cmd as it would typed.
    via_cmd = []
    for tail in tails:
        proc = subprocess.run(f'cmd.exe /d /s /c ""{sys.executable}" "{stub}" {tail}"',
                              capture_output=True, timeout=60)
        via_cmd += _argvs(proc.stdout) or [proc.stderr]
    # PowerShell, one process for all lines, each one run as if pasted in.
    listing = tmp_path / "lines.txt"
    listing.write_text("\n".join(f'& "{sys.executable}" "{stub}" {t}' for t in tails),
                       encoding="utf-8")
    driver = (f"foreach ($l in Get-Content -LiteralPath '{listing}' -Encoding UTF8)"
              " { try { Invoke-Expression $l } catch { 'ERR:' + $_ } }")
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                           base64.b64encode(driver.encode("utf-16-le")).decode("ascii")],
                          capture_output=True, timeout=120)
    via_ps = _argvs(proc.stdout)
    assert len(via_ps) == len(cases), (via_ps, proc.stderr)
    # Exactly the argv in both shells, no exception: no printed root ends in a
    # separator, so PowerShell 5.1 has no closing backslash to double.
    wrong = [(shell, list(argv), got)
             for argv, c, s in zip(cases, via_cmd, via_ps)
             for shell, got in (("cmd", c), ("powershell", s)) if got != list(argv)]
    assert not wrong, wrong


@pytest.mark.skipif(WINDOWS, reason="POSIX sh and, where installed, zsh")
def test_printed_lines_reach_a_program_from_posix_sh_as_their_argv(tmp_path, monkeypatch):
    # Only ever skipped on Windows; on Linux CI it measures `/bin/sh`, and on
    # macOS also zsh, the one place the leading `=` of a bare token bites.
    monkeypatch.chdir(tmp_path)
    stub = tmp_path / "argv.py"
    stub.write_text(STUB, encoding="utf-8")
    root = tmp_path / "Мой проект"
    root.mkdir()
    (tmp_path / "-proj").mkdir()
    cases = _printed_for(str(root) + "/", "/", "-proj") + [
        ("doctor", "--dir", "a\\b"), ("doctor", "--dir", "rel\\dir\\"),
        ("doctor", "--dir", "~"), ("prompt", "--role", "@scout"), ("prompt", "--role", "a,b"),
        ("prompt", "--role", "=scout"), ("prompt", "--role", "=sh")]
    zsh = shutil.which("zsh")
    shells = [["/bin/sh", "-c"]] + ([[zsh, "-f", "-c"]] if zsh else [])
    wrong = []
    for shell in shells:
        for argv in cases:
            tail = doctor.spell(tuple(argv))[len("conduct "):]
            proc = subprocess.run([*shell, f'"$0" "$1" {tail}', sys.executable, str(stub)],
                                  capture_output=True, timeout=60)
            if _argvs(proc.stdout) != [list(argv)]:
                wrong.append((shell[0], list(argv), _argvs(proc.stdout), proc.stderr))
    assert not wrong, wrong
