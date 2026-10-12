"""The first commit through the live route, with the door gone (plan Task 8.7).

Until 8.7 the route answered the confirm body `422 contract_invalid`, and every test of the writer
held a door open with a fixture. The door is deleted, and this file judges the route as a page
meets it:

* `test_the_confirm_body_is_accepted_by_the_route_with_no_patch` replaces the closed-door test of
  `tests/test_git_setup.py` (one id per mode): the body that answered 422 answers 201, and nothing
  is patched;
* `test_no_confirm_door_flag_remains_in_the_source` fails while the constant that closed the door
  stands anywhere in `src/conductor/command`;
* the live test starts a real server on a real socket over an activated folder whose Git is the
  PINNED one, takes the preview, confirms it, reads the repository with that same Git and repeats
  the confirmation: 201, then 200 with the same receipt and not one byte written. It runs in both
  modes, in both object formats and with both Gits (the current one, and the isolated 2.31 when
  `CONDUCT_OLD_GIT` names it).
"""
from __future__ import annotations

import functools
import http.client
import json
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from conductor import ownership_transition, server, tool_pins
from conductor.command.project_claim import Launch
from conductor.ownership import data_root
from tests.git_first_bench import confirm, project
from tests.git_first_readers import READERS, reader_binary
from tests.git_repo_helpers import empty_home_environment, git, needs_git, snapshot
from tests.test_command_http_api import NOW, TOKEN
from tests.test_command_run_socket import pinned
from tests.test_git_setup import PATH
from tests.test_git_setup_first_commit import FILES, commit_body, own_leftovers, text
from tests.test_store import good_lane, write_project

pytestmark = needs_git
WAIT = 120                  # seconds a socket may stay silent: a bound, never a pause
for_both_modes = pytest.mark.parametrize("mode", ["snapshot", "empty"])


@for_both_modes
def test_the_confirm_body_is_accepted_by_the_route_with_no_patch(tmp_path, mode):
    p = project(tmp_path, FILES)
    answer = confirm(p, mode)
    assert answer.status == 201, answer.payload
    assert answer.payload["setup"]["mode"] == mode


def test_no_confirm_door_flag_remains_in_the_source():
    folder = Path(__file__).parents[1] / "src" / "conductor" / "command"
    found = [path.name for path in sorted(folder.rglob("*.py"))
             if "_CONFIRM_OPEN" in path.read_text(encoding="utf-8")]
    assert found == []


@contextmanager
def served(tmp_path, monkeypatch, binary):
    """An activated folder with no repository yet, served on a real socket in `active` mode.

    `binary` is the Git the server pins in a hub folder of its own (the owner's pin is never
    touched). The account's home variables point at an empty folder, so the Git of the server
    cannot read the settings of whoever runs the test; the server passes them on as it does for
    an owner.
    """
    home, root, providers = (tmp_path / name for name in ("hub-home", "project", "providers"))
    for folder in (home, root, providers):
        folder.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    for name, value in empty_home_environment().items():
        monkeypatch.setenv(name, value)
    write_project(root, lanes={"claude": good_lane()})
    (root / "work").mkdir()
    tool_pins.pin_tool("git", binary, folder=home)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, providers=pinned(providers), clock=lambda: NOW,
                           token_factory=lambda _: TOKEN, launch=Launch(mode="active"))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    try:
        yield subject, root
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(10)
        assert not thread.is_alive()


def call(subject, method, path, body=None):
    """One request over a real socket, as a page makes it: the status and the JSON answer."""
    port = subject.server_address[1]
    raw, headers = None, {}
    if body is not None:
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Origin": f"http://127.0.0.1:{port}", "X-Conduct-CSRF": TOKEN,
                   "Content-Type": "application/json"}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=WAIT)
    try:
        connection.request(method, path, body=raw, headers=headers)
        answer = connection.getresponse()
        return answer.status, json.loads(answer.read())
    finally:
        connection.close()


def ask(subject, body, expected):
    """A POST to the setup route that must answer `expected`; its JSON."""
    status, payload = call(subject, "POST", PATH, body)
    assert status == expected, (body, status, payload)
    return payload


def make_repository(subject, root, binary, fmt):
    """The unborn repository a desk makes first, through the route, and the owner's own look at it.

    A SHA-1 repository is made by the route's `init`; Git is asked for a SHA-256 one by hand
    (`init` has no object-format word) and the route writes its exclusion block. The identity
    is the owner's, set in the repository.
    """
    if fmt == "sha256":
        made = git("init", "-q", "--object-format=sha256", str(root), cwd=root.parent,
                   check=False, binary=binary)
        if made.returncode != 0:
            pytest.skip("this git cannot make a SHA-256 repository")
    ask(subject, dict(step="exclude" if fmt == "sha256" else "init", actor="Owner"), 201)
    p = SimpleNamespace(root=root, git=functools.partial(git, binary=binary))
    for key, value in (("user.name", "First Author"), ("user.email", "first@example.invalid"),
                       ("core.autocrlf", "false")):
        p.git("config", key, value, cwd=root)
    for relative, data in FILES.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(data)
    return p


def judge_repository(p, shown, receipt, mode):
    """What the owner's Git says about a first commit that the route reported as the receipt."""
    count = len(shown["files"]) if mode == "snapshot" else 0
    assert (receipt["mode"], receipt["file_count"]) == (mode, count)
    assert (receipt["requested_by"], receipt["signature"]) == ("Owner", "not_required")
    assert text(p, "rev-parse", "HEAD") == receipt["commit"]
    assert text(p, "rev-parse", "HEAD^{tree}") == receipt["tree"]
    assert text(p, "symbolic-ref", "HEAD") == receipt["target_ref"]
    assert text(p, "rev-list", "--parents", "-n", "1", "HEAD") == receipt["commit"]
    assert text(p, "rev-list", "--count", "HEAD") == "1"
    rows = [row.split("\t", 1) for row in text(p, "ls-tree", "-r", "HEAD").splitlines()]
    committed = {path: meta.split()[2] for meta, path in rows}
    status = text(p, "status", "--porcelain").splitlines()
    if mode == "snapshot":
        assert committed == {row["path"]: row["git_oid"] for row in shown["files"]}
        assert sorted(committed) == sorted(FILES) and status == []
        message = f"Первый коммит: {count} файлов (Conduct)\n\nConduct-Setup: first-commit\n"
    else:
        assert committed == {} and {"?? a.txt", "?? docs/"} <= set(status)
        assert all(line.startswith("??") for line in status)
        message = "Начало проекта (Conduct)\n\nConduct-Setup: first-commit\n"
    assert commit_body(p) == message
    assert own_leftovers(p) == []


@pytest.mark.parametrize("which", READERS)
@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@for_both_modes
def test_the_first_commit_goes_through_the_live_route_and_its_exact_repeat_is_a_200_receipt(
        tmp_path, monkeypatch, which, fmt, mode):
    binary = reader_binary(which)
    with served(tmp_path, monkeypatch, binary) as (subject, root):
        p = make_repository(subject, root, binary, fmt)
        shown = ask(subject, dict(step="first_commit", mode=mode, preview=True), 200)["setup"]
        assert (shown["object_format"], shown["head"]) == (fmt, None)
        body = dict(step="first_commit", mode=mode, actor="Owner",
                    paths_digest=shown["paths_digest"] if mode == "snapshot" else None)
        receipt = ask(subject, body, 201)["setup"]
        assert receipt["object_format"] == fmt
        judge_repository(p, shown, receipt, mode)
        standing = (snapshot(root / ".git"), snapshot(data_root(root) / "git" / "setup"))
        assert ask(subject, body, 200)["setup"] == receipt
        assert (snapshot(root / ".git"), snapshot(data_root(root) / "git" / "setup")) == standing
        status, payload = call(subject, "GET", "/command/project/git")
        assert (status, payload["git"]["state"]) == (200, "repo"), payload
        assert payload["git"]["first_commit_pending"] is None
