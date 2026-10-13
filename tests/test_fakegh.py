"""The scripted `gh` that the push and pull request tests run: what it answers, what it records."""
import json
import os
import subprocess

from conductor import tool_pins
from tests import _fakegh

PROBE = "probe-value-that-must-not-reach-the-log"


def built(tmp_path):
    exe = _fakegh.build_executable(tmp_path / "bin")
    assert exe is not None, "this host has no way to build a real executable for the fake gh"
    return exe


def run(exe, *arguments, stdin=b"", env=None):
    return subprocess.run([str(exe), *arguments], input=stdin, capture_output=True,
                          env={**os.environ, **(env or {})}, timeout=60)


def test_the_fake_answers_the_version_line_a_pin_reads_and_logs_nothing_for_it(tmp_path):
    exe = built(tmp_path)
    done = run(exe, "--version")
    assert done.returncode == 0
    assert tool_pins.parse_version("gh", done.stdout.decode()) == "2.50.0"
    assert _fakegh.calls(exe.parent) == []


def test_replies_come_in_order_by_the_first_two_arguments_and_the_last_one_repeats(tmp_path):
    exe = built(tmp_path)
    _fakegh.script(exe.parent, {
        "pr list": [_fakegh.said("first"), _fakegh.said("second", exit=3)],
        "repo view": [_fakegh.repo_view()]})
    answers = [run(exe, "pr", "list", "--repo", "o/r") for _ in range(3)]
    assert [(a.returncode, a.stdout) for a in answers] == [
        (0, b"first"), (3, b"second"), (3, b"second")]
    view = run(exe, "repo", "view", "o/r", "--json", "x")
    assert json.loads(view.stdout)["nameWithOwner"] == "o/r"


def test_a_command_the_script_does_not_name_exits_one_and_prints_nothing(tmp_path):
    exe = built(tmp_path)
    _fakegh.script(exe.parent, {"pr list": [_fakegh.said("x")]})
    answer = run(exe, "pr", "create", "--title", "t")
    assert (answer.returncode, answer.stdout) == (1, b"")
    assert [row["key"] for row in _fakegh.calls(exe.parent)] == ["pr create"]


def test_every_call_is_logged_with_its_arguments_its_stdin_and_the_names_of_its_environment(
        tmp_path):
    exe = built(tmp_path)
    _fakegh.script(exe.parent, {"pr create": [_fakegh.created(7)]})
    answer = run(exe, "pr", "create", "--body-file", "-", stdin="Line one\nLine two\n".encode(),
                 env={"FAKEGH_PROBE": PROBE})
    assert answer.stdout == b"https://github.com/o/r/pull/7\n"
    row, = _fakegh.calls(exe.parent)
    assert row["argv"] == ["pr", "create", "--body-file", "-"]
    assert row["stdin"] == "Line one\nLine two\n"
    assert "FAKEGH_PROBE" in row["env_names"] and row["path"]
    assert PROBE not in (exe.parent / _fakegh.LOG_NAME).read_text(encoding="utf-8")


def test_the_helpers_build_the_rows_the_product_will_read():
    row = _fakegh.pr_row(4, "a" * 40, base="dev", cross=True, draft=True)
    assert row == {
        "number": 4, "url": "https://github.com/o/r/pull/4", "state": "OPEN",
        "headRefName": "conduct/run-001", "headRefOid": "a" * 40, "baseRefName": "dev",
        "isCrossRepository": True, "isDraft": True}
    assert json.loads(_fakegh.pr_list(row)["stdout"]) == [row]
    view = json.loads(_fakegh.repo_view(permission="READ", archived=True)["stdout"])
    assert view == {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"},
                    "viewerPermission": "READ", "isArchived": True}
