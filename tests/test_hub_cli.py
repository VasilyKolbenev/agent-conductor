"""The bodies of the hub-side commands of `conduct` live in `conductor.hub.cli` (spec 4.1.12).

Today that is `conduct tools pin git|gh --path <abs>` (8.8): one JSON line on stdout and
exit 0 after a pin was written, or ONE stderr line `conduct tools pin: refused <code>:
<detail>`, empty stdout, exit 1. The library it calls, `conductor.tool_pins`, decides and
raises; it never prints, and a guard holds that line so the body cannot drift back.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from conductor import tool_pins
from conductor.tool_pins import ToolPin
from tests.test_tool_pins import ABS_GIT, _fake_tool, _put


def _cli(argv: list[str], capsys) -> tuple[int, str, str]:
    from conductor.__main__ import main
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "home"
    monkeypatch.setenv("CONDUCT_HOME", str(folder))
    return folder


def test_tools_pin_prints_one_json_line_of_tool_path_and_version_and_writes_the_pin(
        tmp_path, home, capsys):
    tool = _fake_tool(tmp_path / "bin", "git version 2.47.1")
    code, out, err = _cli(["tools", "pin", "git", "--path", tool], capsys)
    assert (code, err) == (0, "")
    assert out.count("\n") == 1 and json.loads(out) == {
        "tool": "git", "path": tool, "version": "2.47.1"}
    assert tool_pins.read_pin("git", home) == ToolPin("git", tool, "2.47.1")


def _one_refusal(code: int, out: str, err: str, refused: str) -> None:
    assert (code, out) == (1, "")
    assert len(err.splitlines()) == 1 and "Traceback" not in err
    assert err.startswith(f"conduct tools pin: refused {refused}: "), err


def test_a_git_that_is_too_old_is_refused_on_one_line_and_pins_nothing(
        tmp_path, home, capsys):
    tool = _fake_tool(tmp_path / "bin", "git version 2.30.0")
    _one_refusal(*_cli(["tools", "pin", "git", "--path", tool], capsys), "git_too_old")
    assert not (home / "tools.json").exists()


def test_a_path_that_runs_nothing_is_refused_tool_version_unreadable(tmp_path, home, capsys):
    missing = str(tmp_path / "bin" / "nothing-here")
    _one_refusal(*_cli(["tools", "pin", "gh", "--path", missing], capsys),
                 "tool_version_unreadable")


def test_a_relative_path_is_refused_tool_version_unreadable_with_the_reason(home, capsys):
    result = _cli(["tools", "pin", "git", "--path", "git"], capsys)
    _one_refusal(*result, "tool_version_unreadable")
    assert "absolute" in result[2]


def test_an_invalid_tools_file_is_refused_and_left_as_the_owner_wrote_it(
        tmp_path, home, capsys):
    tool = _fake_tool(tmp_path / "bin", "git version 2.47.1")
    target = _put(home, b"{ not the schema")
    _one_refusal(*_cli(["tools", "pin", "git", "--path", tool], capsys), "tools_file_invalid")
    assert target.read_bytes() == b"{ not the schema"


def test_a_relative_conduct_home_is_refused_conduct_home_invalid(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CONDUCT_HOME", "relative/home")
    tool = _fake_tool(tmp_path / "bin", "git version 2.47.1")
    _one_refusal(*_cli(["tools", "pin", "git", "--path", tool], capsys), "conduct_home_invalid")


@pytest.mark.parametrize("argv", [
    ["tools", "pin", "hg", "--path", ABS_GIT], ["tools", "pin", "git"], ["tools"],
    ["tools", "unpin", "git"]])
def test_a_tools_command_line_argparse_cannot_read_is_a_usage_error(argv, home, capsys):
    from conductor.__main__ import main
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == 2
    assert not (home / "tools.json").exists()


def test_the_body_of_tools_pin_is_hub_cli_tools_pin(tmp_path, home, monkeypatch, capsys):
    from conductor.hub import cli
    calls = []

    def stand_in(tool: str, path: str) -> int:
        calls.append((tool, path))
        return 0

    monkeypatch.setattr(cli, "tools_pin", stand_in)
    from conductor.__main__ import main
    assert main(["tools", "pin", "gh", "--path", ABS_GIT]) == 0
    assert calls == [("gh", ABS_GIT)]


def test_tool_pins_library_code_never_prints_or_writes_a_standard_stream():
    source = Path(tool_pins.__file__).read_text(encoding="utf-8")
    faults = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "print":
            faults.append(f"print at line {node.lineno}")
        if isinstance(node, ast.Attribute) and node.attr in {"stdout", "stderr"} \
                and isinstance(node.value, ast.Name) and node.value.id == "sys":
            faults.append(f"sys.{node.attr} at line {node.lineno}")
    assert not faults, f"the library prints; a body that prints belongs to hub/cli.py: {faults}"
