"""The git and gh candidates the hub offers for a pin: found once, never a path (spec 8.8).

The hub looks for the tools one time in its life (`shutil.which` and the standard folders of the
spec), reads each one's version the way a pin does, and offers them in `GET /hub/setup` only for
a tool that is not settled. A candidate has an id of this hub's making and no path in any
answer. Every test here stands in for the file system, the search and the version probe; one
test runs the real probe with a stand-in runner to see which environment the tool runs in.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

import pytest

from conductor import tool_pins
from conductor.hub import routes
from tests._hub_stack import Stack

BIN = os.path.abspath(os.path.join(os.sep, "tools", "bin"))
OTHER = os.path.abspath(os.path.join(os.sep, "tools", "other"))
EXE = ".exe" if os.name == "nt" else ""
GIT, GH = os.path.join(BIN, "git" + EXE), os.path.join(BIN, "gh" + EXE)
GIT_ELSEWHERE = os.path.join(OTHER, "git" + EXE)


class Probe:
    """Stands in for `tool_pins.probe_version`: says what a test told it, records each call."""

    def __init__(self, versions: dict) -> None:
        self.versions, self.calls = versions, []

    def __call__(self, tool, path, **keywords):
        self.calls.append((tool, path, keywords))
        version = self.versions[path]
        if isinstance(version, BaseException):
            raise version
        return version


def counting_token():
    numbers = iter(range(1, 10_000))
    return lambda: f"{next(numbers):032x}"


def build(tmp_path, *, which=None, files=(), versions=None, monkeypatch=None, standard=None,
          **more):
    """A `ToolCandidates` over fakes (not yet discovered) and the probe it was given."""
    from conductor.hub import tool_candidates

    folders = {"git": (), "gh": ()} if standard is None else standard
    if monkeypatch is not None:
        monkeypatch.setattr(tool_candidates, "STANDARD", {"nt": folders, "posix": folders})
    probe = Probe(versions if versions is not None else {})
    options = {"which": lambda tool: (which or {}).get(tool), "isfile": set(files).__contains__,
               "probe": probe, "token": counting_token(), **more}
    return tool_candidates.ToolCandidates(tmp_path, **options), probe


def discovered(tmp_path):
    """The candidates of git at `GIT` and gh at `GH`, found once."""
    found, probe = build(tmp_path, which={"git": GIT, "gh": GH}, files=(GIT, GH),
                         versions={GIT: "2.47.1", GH: "2.62.0"})
    found.discover()
    return found, probe


def only(path: str):
    """A stand-in for `os.path.isfile` that knows one file."""
    return lambda candidate: candidate == path


def _paths(probe) -> list[str]:
    return [path for _tool, path, _keywords in probe.calls]


# -- what is found -----------------------------------------------------------------------------


def test_candidates_are_the_which_result_and_the_standard_folders_each_once(
        tmp_path, monkeypatch):
    spelled_differently = os.path.join(BIN, ".", "git" + EXE)
    found, probe = build(
        tmp_path, which={"git": spelled_differently}, files=(GIT, GIT_ELSEWHERE),
        versions={GIT: "2.47.1", GIT_ELSEWHERE: "2.45.2"}, monkeypatch=monkeypatch,
        standard={"git": (BIN, OTHER), "gh": ()})
    found.discover()
    rows = found.offered("git", settled=False)
    assert [row["version"] for row in rows] == ["2.47.1", "2.45.2"], "the which result is first"
    ids = [row["candidate_id"] for row in rows]
    assert all(re.fullmatch(r"cand-[0-9a-f]{32}", ident) for ident in ids)
    assert len(set(ids)) == 2
    assert _paths(probe) == [GIT, GIT_ELSEWHERE], "the same file was probed once, not twice"
    assert found.offered("gh", settled=False) == []


def test_the_standard_folders_are_the_ones_of_the_spec_per_os():
    from conductor.hub import tool_candidates

    assert tool_candidates.standard_paths("git", "nt") == [
        "C:\\Program Files\\Git\\cmd\\git.exe"]
    assert tool_candidates.standard_paths("gh", "nt") == [
        "C:\\Program Files\\GitHub CLI\\gh.exe"]
    for tool in ("git", "gh"):
        assert tool_candidates.standard_paths(tool, "posix") == [
            f"/opt/homebrew/bin/{tool}", f"/usr/local/bin/{tool}", f"/usr/bin/{tool}"]


def test_on_windows_only_an_exe_is_a_candidate_and_on_posix_no_suffix_rule_applies(tmp_path):
    shim, plain = os.path.join(BIN, "git.cmd"), os.path.join(BIN, "git.EXE")
    found, probe = build(tmp_path, which={"git": shim}, files=(shim, plain),
                         versions={shim: "2.47.1", plain: "2.47.1"}, osname="nt")
    found.discover()
    assert found.offered("git", settled=False) == [], "a .cmd shim would run through cmd.exe"
    assert probe.calls == []
    found, _probe = build(tmp_path, which={"git": plain}, files=(plain,),
                          versions={plain: "2.47.1"}, osname="nt")
    found.discover()
    assert len(found.offered("git", settled=False)) == 1
    found, _probe = build(tmp_path, which={"git": shim}, files=(shim,),
                          versions={shim: "2.47.1"}, osname="posix")
    found.discover()
    assert len(found.offered("git", settled=False)) == 1


def test_a_relative_or_missing_or_unreadable_path_is_not_offered(tmp_path, monkeypatch):
    unreadable = os.path.join(OTHER, "git" + EXE)
    missing = os.path.join(OTHER, "gh" + EXE)
    found, probe = build(
        tmp_path, which={"git": "git" + EXE, "gh": missing}, files=(GIT, unreadable),
        versions={GIT: "2.47.1",
                  unreadable: tool_pins.ToolPinError("tool_version_unreadable", "no")},
        monkeypatch=monkeypatch, standard={"git": (BIN, OTHER), "gh": ()})
    found.discover()
    assert [row["version"] for row in found.offered("git", settled=False)] == ["2.47.1"]
    assert found.offered("gh", settled=False) == []
    assert missing not in _paths(probe) and "git" + EXE not in _paths(probe)


def test_a_probe_that_fails_in_any_way_leaves_the_other_candidates_in_the_table(
        tmp_path, monkeypatch):
    broken = os.path.join(OTHER, "git" + EXE)
    found, _probe = build(
        tmp_path, which={"git": GIT}, files=(GIT, broken),
        versions={GIT: "2.47.1", broken: OSError(13, "denied")}, monkeypatch=monkeypatch,
        standard={"git": (OTHER,), "gh": ()})
    found.discover()
    assert [row["version"] for row in found.offered("git", settled=False)] == ["2.47.1"]


# -- what is offered, and to whom ----------------------------------------------------------------


def test_a_candidate_is_offered_only_for_a_tool_that_is_not_settled(tmp_path):
    found, _probe = discovered(tmp_path)
    assert found.offered("git", settled=True) == []
    (row,) = found.offered("git", settled=False)
    assert set(row) == {"candidate_id", "display", "version"}
    assert row["display"] == f"{Path(BIN).name}{os.sep}git{EXE}" and row["version"] == "2.47.1"
    assert BIN not in json.dumps(row) and os.path.dirname(BIN) not in json.dumps(row)


def test_the_candidate_probe_runs_only_the_absolute_path_with_version_in_the_built_environment(
        tmp_path):
    from conductor.hub import tool_candidates

    seen = []

    def run(argv, env):
        seen.append((argv, dict(env)))
        return "git version 2.47.1\n"

    owner = {"GH_TOKEN": "planted", "GITHUB_TOKEN": "planted", "GIT_DIR": "/elsewhere",
             "PATH": "/owner/bin", "HOME": "/h"}
    found = tool_candidates.ToolCandidates(
        tmp_path, which=lambda tool: GIT if tool == "git" else None, isfile=only(GIT),
        run=run, source=owner)
    found.discover()
    assert [argv for argv, _env in seen] == [[GIT, "--version"]]
    env = seen[0][1]
    assert not {"GH_TOKEN", "GITHUB_TOKEN", "GIT_DIR"} & set(env)
    assert env["PATH"].split(os.pathsep)[0] == BIN and "/owner/bin" not in env["PATH"]
    assert found.offered("git", settled=False)[0]["version"] == "2.47.1"


def test_a_candidate_id_is_issued_by_this_hub_and_unknown_to_a_new_one(tmp_path):
    from conductor.hub import tool_candidates

    found, _probe = discovered(tmp_path)
    ident = found.offered("git", settled=False)[0]["candidate_id"]
    assert found.get("git", ident).path == GIT and found.get("git", ident).version == "2.47.1"
    assert found.get("gh", ident) is None, "an id of the other tool is not found"
    assert found.get("git", "cand-" + "0" * 32) is None
    restarted = tool_candidates.ToolCandidates(
        tmp_path, which=lambda tool: GIT if tool == "git" else None, isfile=only(GIT),
        probe=Probe({GIT: "2.47.1"}))
    restarted.discover()
    assert restarted.get("git", ident) is None


# -- once, in the background, and never again -----------------------------------------------------


def test_discovery_runs_once_and_announces_setup_when_done(tmp_path):
    found, probe = build(tmp_path, which={"git": GIT, "gh": GH}, files=(GIT, GH),
                         versions={GIT: "2.47.1", GH: "2.62.0"})
    done = []
    thread = found.start(lambda: done.append("setup"))
    thread.join(10)
    assert not thread.is_alive() and done == ["setup"]
    found.discover()
    found.discover()
    assert sorted(_paths(probe)) == sorted([GIT, GH]), "each candidate was probed once"


def test_a_search_in_a_thread_of_its_own_is_a_daemon_with_a_name(tmp_path):
    found, _probe = build(tmp_path)
    thread = found.start(lambda: None)
    thread.join(10)
    assert thread.name == "hub-tool-candidates" and thread.daemon is True


def test_a_tool_installed_after_the_pass_is_not_found_until_the_hub_is_restarted_and_no_route_searches_again(  # noqa: E501
        tmp_path):
    from conductor.hub import tool_candidates

    installed = {}
    found = tool_candidates.ToolCandidates(
        tmp_path, which=installed.get, isfile=only(GIT), probe=Probe({GIT: "2.47.1"}))
    found.discover()
    installed["git"] = GIT
    found.discover()
    assert found.offered("git", settled=False) == [], "no search again for the life of the hub"
    restarted = tool_candidates.ToolCandidates(
        tmp_path, which=installed.get, isfile=only(GIT), probe=Probe({GIT: "2.47.1"}))
    restarted.discover()
    assert len(restarted.offered("git", settled=False)) == 1
    tool_paths = {row.path for row in routes.HUB_ROUTES if "tool" in row.path}
    assert tool_paths == {"/hub/tools/<tool>/pin"}
    assert not [row.path for row in routes.HUB_ROUTES
                if re.search(r"candidate|search|discover|refresh", row.path)]


# -- through the hub's setup --------------------------------------------------------------------


def write_pins(folder: Path, **entries) -> None:
    document = {"schema_version": 1, "git": None, "gh": None, **entries}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tools.json").write_bytes(json.dumps(document).encode("utf-8"))


class Verdicts:
    """Stands in for `tool_pins.verify_pin`: the pin as read, unless a test names a refusal."""

    def __init__(self) -> None:
        self.refuse: dict[str, str] = {}

    def __call__(self, tool, *, folder, **_keywords):
        if tool in self.refuse:
            raise tool_pins.ToolPinError(self.refuse[tool], "because")
        return tool_pins.read_pin(tool, folder)


@pytest.fixture
def setup_stack(tmp_path):
    made = []

    def build_stack(candidates=None, **options):
        found = candidates if candidates is not None else discovered(tmp_path / "candidates")[0]
        verdicts = Verdicts()
        stack = Stack(tmp_path, candidates=found, verify_tool=verdicts, **options)
        made.append(stack)
        return stack, found, verdicts

    yield build_stack
    for stack in made:
        stack.close()


def _tool(stack, tool: str) -> dict:
    return stack.get("/hub/setup").json()["tools"][tool]


def test_the_setup_offers_the_candidates_while_a_tool_is_not_pinned_and_none_once_it_is(
        setup_stack):
    stack, found, _verdicts = setup_stack()
    git = _tool(stack, "git")
    assert git["state"] == "not_pinned" and git["display"] is None
    assert git["candidates"] == found.offered("git", settled=False) != []
    assert _tool(stack, "gh")["candidates"] == found.offered("gh", settled=False)
    write_pins(stack.world.home, git={"path": GIT, "version": "2.47.1"})
    git = _tool(stack, "git")
    assert (git["state"], git["candidates"]) == ("pinned", [])
    assert _tool(stack, "gh")["candidates"] != [], "the other tool is still not settled"


@pytest.mark.parametrize(("refusal", "state"), [
    ("git_changed", "changed"), ("git_too_old", "too_old"),
    ("tool_version_unreadable", "unreadable")])
def test_a_pinned_tool_that_is_changed_old_or_unreadable_is_offered_candidates_to_pin_again(
        setup_stack, refusal, state):
    stack, found, verdicts = setup_stack()
    write_pins(stack.world.home, git={"path": GIT, "version": "2.30.0"})
    verdicts.refuse["git"] = refusal
    git = _tool(stack, "git")
    assert git["state"] == state
    assert git["candidates"] == found.offered("git", settled=False) != []


def test_a_pin_file_that_cannot_be_read_is_offered_no_candidate(setup_stack):
    stack, _found, _verdicts = setup_stack()
    (stack.world.home / "tools.json").write_bytes(b"{ not the schema")
    for tool in ("git", "gh"):
        entry = _tool(stack, tool)
        assert (entry["state"], entry["candidates"]) == ("unreadable", [])


def test_discovery_runs_in_a_background_thread_started_by_start_and_never_in_setup(
        tmp_path, setup_stack):
    fresh, probe = build(tmp_path / "fresh", which={"git": GIT}, files=(GIT,),
                         versions={GIT: "2.47.1"})
    stack, _found, _verdicts = setup_stack(candidates=fresh)
    for _ in range(100):
        stack.service.setup()
    assert probe.calls == [] and not _running("hub-tool-candidates")
    stack.service.start()
    deadline = time.monotonic() + 5
    while not stack.service.setup()["tools"]["git"]["candidates"]:
        assert time.monotonic() < deadline, "the background search never finished"
        time.sleep(0.01)
    assert _paths(probe) == [GIT]


def _running(name: str) -> bool:
    return any(thread.name == name and thread.is_alive() for thread in threading.enumerate())
