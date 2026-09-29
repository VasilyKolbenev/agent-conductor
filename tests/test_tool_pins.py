"""The pins of git and gh: `<conduct-home>/tools.json` (spec 8.8, 8.10 item 4).

A pin is the one thing that lets a child run `git` or `gh` at all (there is no PATH
search), so the file is read strictly, written whole and canonical, and never
overwritten when it is not the schema. The version of a tool is read by running it
in the environment `tool_env` builds; most tests hand `run=` a stand-in so the
version text is theirs, and one test runs a REAL executable (a two-line script) so
the default runner is not left unproven.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conductor import tool_pins
from conductor.tool_pins import ToolPin, ToolPinError, ToolPins

ABS_GIT = os.path.abspath(os.path.join(os.sep, "tools", "git"))
ABS_GH = os.path.abspath(os.path.join(os.sep, "tools", "gh"))
GIT_ENTRY = {"path": ABS_GIT, "version": "2.47.1"}
GH_ENTRY = {"path": ABS_GH, "version": "2.62.0"}


def _document(git=None, gh=None, **more) -> dict:
    return {"schema_version": 1, "git": git, "gh": gh, **more}


def _put(folder: Path, content: bytes | str | dict) -> Path:
    target = folder / "tools.json"
    folder.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        content = json.dumps(content)
    target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return target


def _says(text: str):
    """A stand-in for running `<tool> --version`: it answers `text`, whatever it is asked."""
    def run(argv, env):
        return text
    return run


def _raises(error: BaseException):
    def run(argv, env):
        raise error
    return run


def _code(call) -> str:
    with pytest.raises(ToolPinError) as caught:
        call()
    return caught.value.code


# -- reading: absent, null, present, and the strict schema -------------------------


def test_a_missing_tools_file_reads_as_no_pins(tmp_path):
    assert tool_pins.load_pins(tmp_path) == ToolPins()
    assert tool_pins.read_pin("git", tmp_path) is None
    assert tool_pins.read_pin("gh", tmp_path) is None


def test_a_null_entry_reads_as_no_pin_and_a_pinned_tool_reads_back_whole(tmp_path):
    _put(tmp_path, _document(git=GIT_ENTRY))
    assert tool_pins.read_pin("gh", tmp_path) is None
    assert tool_pins.read_pin("git", tmp_path) == ToolPin("git", ABS_GIT, "2.47.1")


def test_a_pretty_printed_file_of_the_exact_schema_reads(tmp_path):
    pretty = json.dumps(_document(git=GIT_ENTRY, gh=GH_ENTRY), indent=2) + "\n"
    _put(tmp_path, pretty)
    pins = tool_pins.load_pins(tmp_path)
    assert (pins.git.version, pins.gh.version) == ("2.47.1", "2.62.0")


def test_an_unknown_tool_name_is_a_programming_error_not_a_pin_state(tmp_path):
    with pytest.raises(ValueError, match="hg"):
        tool_pins.read_pin("hg", tmp_path)


def _entry(**fields) -> dict:
    return _document(git={**GIT_ENTRY, **fields})


INVALID = {
    "empty file": b"",
    "not json": b"{ nope",
    "utf-8 bom": b"\xef\xbb\xbf" + json.dumps(_document()).encode("utf-8"),
    "not utf-8": b"\xff\xfe{}",
    "a list": b"[]",
    "gh key missing": json.dumps({"schema_version": 1, "git": None}).encode("utf-8"),
    "extra top key": json.dumps(_document(extra=1)).encode("utf-8"),
    "schema_version 2": json.dumps(_document(**{"schema_version": 2})).encode("utf-8"),
    "schema_version true": json.dumps(_document(**{"schema_version": True})).encode("utf-8"),
    "schema_version text": json.dumps(_document(**{"schema_version": "1"})).encode("utf-8"),
    "schema_version float": json.dumps(_document(**{"schema_version": 1.0})).encode("utf-8"),
    "entry is text": json.dumps(_document(git=ABS_GIT)).encode("utf-8"),
    "entry has an extra key": json.dumps(_entry(extra="x")).encode("utf-8"),
    "entry lacks version": json.dumps(_document(git={"path": ABS_GIT})).encode("utf-8"),
    "relative path": json.dumps(_entry(path="git")).encode("utf-8"),
    "empty path": json.dumps(_entry(path="")).encode("utf-8"),
    "path with NUL": json.dumps(_entry(path=ABS_GIT + "\u0000x")).encode("utf-8"),
    "path is a number": json.dumps(_entry(path=5)).encode("utf-8"),
    "version two parts": json.dumps(_entry(version="2.47")).encode("utf-8"),
    "version four parts": json.dumps(_entry(version="2.47.1.1")).encode("utf-8"),
    "version with v": json.dumps(_entry(version="v2.47.1")).encode("utf-8"),
    "version is a number": json.dumps(_entry(version=247)).encode("utf-8"),
    "duplicate key": b'{"schema_version":1,"git":null,"gh":null,"git":null}',
    "NaN": b'{"schema_version":1,"git":null,"gh":NaN}',
}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_a_file_that_is_not_the_strict_schema_is_refused_tools_file_invalid(tmp_path, name):
    _put(tmp_path, INVALID[name])
    assert _code(lambda: tool_pins.load_pins(tmp_path)) == "tools_file_invalid"
    assert _code(lambda: tool_pins.read_pin("git", tmp_path)) == "tools_file_invalid"


# -- version text ------------------------------------------------------------------


@pytest.mark.parametrize("tool, text, version", [
    ("git", "git version 2.47.1.windows.1\n", "2.47.1"),
    ("git", "git version 2.52.0\nmore text\n", "2.52.0"),
    ("gh", "gh version 2.62.0 (2024-11-14)\nhttps://github.com/cli/cli/releases\n", "2.62.0"),
])
def test_the_first_line_of_version_output_gives_major_minor_patch(tool, text, version):
    assert tool_pins.parse_version(tool, text) == version


@pytest.mark.parametrize("tool, text", [
    ("git", ""), ("git", "\n"), ("git", "hello"), ("git", "git version 2.47\n"),
    ("git", "gh version 2.62.0\n"), ("gh", "git version 2.47.1\n"),
    ("git", "banner\ngit version 2.47.1\n"), ("git", " git version 2.47.1\n")])
def test_output_that_is_not_the_first_line_of_this_tool_is_unreadable(tool, text):
    assert _code(lambda: tool_pins.parse_version(tool, text)) == "tool_version_unreadable"


# -- pinning: the minimum, the failures, the canonical whole write ------------------


def _pin(tmp_path, tool="git", path=ABS_GIT, text="git version 2.47.1\n", **options):
    return tool_pins.pin_tool(tool, path, folder=tmp_path, run=_says(text), source={}, **options)


def test_a_pin_writes_the_canonical_bytes_sorted_compact_and_one_newline_long(tmp_path):
    pin = _pin(tmp_path)
    assert pin == ToolPin("git", ABS_GIT, "2.47.1")
    expected = json.dumps({"schema_version": 1, "git": GIT_ENTRY, "gh": None},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    assert (tmp_path / "tools.json").read_bytes() == expected.encode("utf-8")


def test_a_second_pin_keeps_the_first_and_a_repin_changes_only_its_own_tool(tmp_path):
    _pin(tmp_path)
    _pin(tmp_path, tool="gh", path=ABS_GH, text="gh version 2.62.0 (2024-11-14)\n")
    assert tool_pins.load_pins(tmp_path) == ToolPins(ToolPin("git", ABS_GIT, "2.47.1"),
                                                     ToolPin("gh", ABS_GH, "2.62.0"))
    _pin(tmp_path, text="git version 2.48.0\n")
    pins = tool_pins.load_pins(tmp_path)
    assert pins.git.version == "2.48.0" and pins.gh == ToolPin("gh", ABS_GH, "2.62.0")


def test_a_pin_never_overwrites_an_invalid_file(tmp_path):
    target = _put(tmp_path, b"{ the owner's own edit")
    assert _code(lambda: _pin(tmp_path)) == "tools_file_invalid"
    assert target.read_bytes() == b"{ the owner's own edit"


def test_a_git_older_than_2_31_is_refused_git_too_old_and_nothing_is_written(tmp_path):
    assert _code(lambda: _pin(tmp_path, text="git version 2.30.9.windows.1\n")) == "git_too_old"
    assert not (tmp_path / "tools.json").exists()


def test_git_2_31_0_is_pinned_and_gh_has_no_minimum(tmp_path):
    assert _pin(tmp_path, text="git version 2.31.0\n").version == "2.31.0"
    assert _pin(tmp_path, tool="gh", path=ABS_GH, text="gh version 0.0.1\n").version == "0.0.1"


@pytest.mark.parametrize("failure", [
    OSError(2, "no such file"), subprocess.TimeoutExpired(["git"], 10),
    subprocess.CalledProcessError(1, ["git"])])
def test_a_tool_that_cannot_run_is_tool_version_unreadable(tmp_path, failure):
    def pin():
        tool_pins.pin_tool("git", ABS_GIT, folder=tmp_path, run=_raises(failure), source={})
    assert _code(pin) == "tool_version_unreadable"
    assert not (tmp_path / "tools.json").exists()


def test_output_naming_the_other_tool_is_refused_and_nothing_is_written(tmp_path):
    assert _code(lambda: _pin(tmp_path, text="gh version 2.62.0\n")) == "tool_version_unreadable"
    assert not (tmp_path / "tools.json").exists()


def test_a_relative_path_is_tool_version_unreadable_and_says_why_before_anything_runs(tmp_path):
    def pin():
        tool_pins.pin_tool("git", "git", folder=tmp_path, run=_raises(AssertionError("ran")),
                           source={})
    with pytest.raises(ToolPinError) as caught:
        pin()
    assert caught.value.code == "tool_version_unreadable"
    assert "absolute" in caught.value.detail


# -- the closed list of codes: the spec's names, and the two proposals --------------

SPEC_NAMES = {"git_not_pinned", "gh_not_pinned", "git_changed", "gh_changed", "git_too_old",
              "tool_version_unreadable"}
PROPOSED_NAMES = {"tools_file_invalid", "tools_file_unwritable"}


def test_the_spec_codes_and_the_two_proposals_are_the_whole_list():
    assert tool_pins.SPEC_CODES == frozenset(SPEC_NAMES)
    assert tool_pins.PROPOSED_CODES == frozenset(PROPOSED_NAMES)


@pytest.mark.parametrize("code", ["tool_path_invalid", "tool_changed", "gh_unpinned", "", "x"])
def test_a_tool_pin_error_refuses_a_code_that_is_neither_in_the_spec_nor_proposed(code):
    with pytest.raises(ValueError):
        ToolPinError(code, "detail")


@pytest.mark.parametrize("code", sorted(SPEC_NAMES | PROPOSED_NAMES))
def test_a_tool_pin_error_carries_every_listed_code(code):
    assert ToolPinError(code, "detail").code == code


def test_every_code_a_raise_site_of_the_library_names_is_on_the_list():
    tree = ast.parse(Path(tool_pins.__file__).read_text(encoding="utf-8"))
    listed = SPEC_NAMES | PROPOSED_NAMES
    named = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "ToolPinError" and node.args):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant):
            named.append(first.value)
        elif isinstance(first, ast.JoinedStr):     # f"{tool}_not_pinned": one name per tool
            tail = "".join(part.value for part in first.values if isinstance(part, ast.Constant))
            named.extend(f"{tool}{tail}" for tool in tool_pins.TOOLS)
    assert named, "the scan found no raise site, so it proves nothing"
    assert set(named) <= listed, sorted(set(named) - listed)


def test_a_write_that_fails_is_tools_file_unwritable(tmp_path, monkeypatch):
    def refuse(path, payload, **options):
        raise PermissionError(13, "read-only")
    monkeypatch.setattr("conductor.atomic_replace.replace_bytes", refuse)
    assert _code(lambda: _pin(tmp_path)) == "tools_file_unwritable"


def test_the_version_probe_runs_in_the_built_environment_and_only_the_pinned_path(tmp_path):
    seen = []

    def spy(argv, env):
        seen.append((argv, dict(env)))
        return "git version 2.47.1\n"

    owner = {"GH_TOKEN": "planted", "GIT_DIR": "/elsewhere", "HOME": "/h", "PATH": "/owner/bin"}
    tool_pins.pin_tool("git", ABS_GIT, folder=tmp_path, run=spy, source=owner)
    (argv, env), = seen
    assert argv == [ABS_GIT, "--version"]
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["HOME"] == "/h"
    assert "GH_TOKEN" not in env and "GIT_DIR" not in env
    assert env["PATH"].split(os.pathsep)[0] == os.path.dirname(ABS_GIT)
    assert "/owner/bin" not in env["PATH"]


# -- verifying a pin: the check a hub does at start and a child once ----------------


def _verify(tmp_path, tool="git", text="git version 2.47.1\n"):
    return tool_pins.verify_pin(tool, folder=tmp_path, run=_says(text), source={})


@pytest.mark.parametrize("tool", ["git", "gh"])
def test_a_tool_that_is_not_pinned_is_named_in_its_own_not_pinned_code(tmp_path, tool):
    assert _code(lambda: _verify(tmp_path, tool)) == f"{tool}_not_pinned"
    _put(tmp_path, _document())
    assert _code(lambda: _verify(tmp_path, tool)) == f"{tool}_not_pinned"


def test_a_pinned_tool_whose_version_is_unchanged_verifies_and_returns_its_pin(tmp_path):
    _put(tmp_path, _document(git=GIT_ENTRY))
    assert _verify(tmp_path) == ToolPin("git", ABS_GIT, "2.47.1")


@pytest.mark.parametrize("tool, entry, text", [
    ("git", GIT_ENTRY, "git version 2.47.2\n"), ("gh", GH_ENTRY, "gh version 2.63.0 (x)\n")])
def test_a_version_that_moved_is_named_in_its_own_changed_code(tmp_path, tool, entry, text):
    _put(tmp_path, _document(**{tool: entry}))
    assert _code(lambda: _verify(tmp_path, tool, text)) == f"{tool}_changed"


def test_a_pinned_tool_that_cannot_answer_now_is_tool_version_unreadable(tmp_path):
    _put(tmp_path, _document(git=GIT_ENTRY))
    assert _code(lambda: _verify(tmp_path, text="")) == "tool_version_unreadable"


# -- the default runner, on a real executable --------------------------------------


def _fake_tool(folder: Path, says: str) -> str:
    """An executable that prints `says` for any arguments; a .cmd on Windows, else sh."""
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        target = folder / "fake-tool.cmd"
        target.write_bytes(f"@echo {says}\r\n".encode("ascii"))
    else:
        target = folder / "fake-tool"
        target.write_bytes(f'#!/bin/sh\necho "{says}"\n'.encode("ascii"))
        target.chmod(0o755)
    return str(target)


def test_a_real_executable_is_pinned_and_verified_through_the_default_runner(tmp_path):
    tool = _fake_tool(tmp_path / "bin", "git version 2.47.1.windows.1")
    home = tmp_path / "home"
    pin = tool_pins.pin_tool("git", tool, folder=home, source=dict(os.environ))
    assert pin == ToolPin("git", tool, "2.47.1")
    assert tool_pins.verify_pin("git", folder=home, source=dict(os.environ)) == pin
    _fake_tool(tmp_path / "bin", "git version 2.48.0")
    assert _code(lambda: tool_pins.verify_pin("git", folder=home,
                                              source=dict(os.environ))) == "git_changed"


def test_a_path_that_holds_no_executable_is_tool_version_unreadable_through_the_default_runner(
        tmp_path):
    missing = str(tmp_path / "bin" / "nothing-here")

    def pin() -> None:
        tool_pins.pin_tool("git", missing, folder=tmp_path, source=dict(os.environ))

    assert _code(pin) == "tool_version_unreadable"


# -- a pin is read-modify-write under one lock ---------------------------------------


def _pin_in_a_thread(tmp_path, tool, path, text, gate, failures):
    def probe(argv, env):
        gate.wait()                # both pins are past their probe before either writes
        return text

    def go():
        try:
            tool_pins.pin_tool(tool, path, folder=tmp_path, run=probe, source={})
        except BaseException as error:                          # noqa: BLE001 -- reported below
            failures.append(error)

    return threading.Thread(target=go)


def test_two_pins_of_different_tools_at_once_both_survive(tmp_path):
    gate, failures = threading.Barrier(2, timeout=15), []
    threads = [
        _pin_in_a_thread(tmp_path, "git", ABS_GIT, "git version 2.47.1\n", gate, failures),
        _pin_in_a_thread(tmp_path, "gh", ABS_GH, "gh version 2.62.0\n", gate, failures)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads) and failures == []
    assert tool_pins.load_pins(tmp_path) == ToolPins(ToolPin("git", ABS_GIT, "2.47.1"),
                                                     ToolPin("gh", ABS_GH, "2.62.0"))


def test_a_file_that_becomes_invalid_while_the_tool_answers_is_refused_and_left_alone(tmp_path):
    def probe(argv, env):
        _put(tmp_path, b"{ edited by the owner meanwhile")
        return "git version 2.47.1\n"

    def pin():
        tool_pins.pin_tool("git", ABS_GIT, folder=tmp_path, run=probe, source={})

    assert _code(pin) == "tools_file_invalid"
    assert (tmp_path / "tools.json").read_bytes() == b"{ edited by the owner meanwhile"


def test_a_pin_that_cannot_take_the_lock_refuses_tools_file_unwritable_and_writes_nothing(
        tmp_path, monkeypatch):
    from conductor.ownership_native import NativeHold
    monkeypatch.setattr(tool_pins, "LOCK_ATTEMPTS", 3)
    monkeypatch.setattr(tool_pins, "LOCK_PAUSE_SECONDS", 0.001)
    (tmp_path / "tools.lock").write_bytes(b"")
    holder = NativeHold(tmp_path / "tools.lock", exclusive=True)
    try:
        assert _code(lambda: _pin(tmp_path)) == "tools_file_unwritable"
    finally:
        holder.close()
    assert not (tmp_path / "tools.json").exists()
    assert _pin(tmp_path).version == "2.47.1"          # the same pin goes through once it is free


def test_a_pin_creates_the_lock_file_once_and_leaves_it_in_place(tmp_path):
    folder = tmp_path / "not-there-yet"
    tool_pins.pin_tool("git", ABS_GIT, folder=folder, run=_says("git version 2.47.1\n"), source={})
    lock = folder / "tools.lock"
    assert lock.is_file()
    identity = lock.stat().st_ino
    tool_pins.pin_tool("gh", ABS_GH, folder=folder, run=_says("gh version 2.62.0\n"), source={})
    assert lock.stat().st_ino == identity


def test_a_write_that_fails_lets_go_of_the_lock(tmp_path, monkeypatch):
    def refuse(path, payload, **options):
        raise PermissionError(13, "read-only")

    with monkeypatch.context() as patched:
        patched.setattr("conductor.atomic_replace.replace_bytes", refuse)
        assert _code(lambda: _pin(tmp_path)) == "tools_file_unwritable"
    monkeypatch.setattr(tool_pins, "LOCK_ATTEMPTS", 1)   # a lock still held would refuse at once
    assert _pin(tmp_path).version == "2.47.1"
