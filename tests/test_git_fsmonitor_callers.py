"""The file monitor is off through every real caller, on every Git the pin accepts.

Git 2.31 reads the value of `core.fsmonitor` as the path of a hook program: `false` names the
program `false`, every index command then starts it twice, and every index such a command writes
carries an `FSMN` extension. Later Gits read `false` as a boolean and do neither. The empty value
is "off" on both (measured in `reports/2026-10-06-L-fsmonitor-evidence.txt`). The product says it
in two places: `project_git.GIT_FLAGS` (each `process_git_read`) and the literals of `tool_env`
(every git and gh process). Each witness goes through the real caller of those places, never
through an argument list written here: the reader of an active child (`server_git`), the admission
of a new project (`hub.projects_add`) and the environment `hub.clone` hands `gh`.

What is observed is what Git did, and never what a string says: the programs it started (its own
`GIT_TRACE`), the runs of a monitor program the owner's repository names, and the `FSMN` extension
in an index it wrote. The calibration shows each observation can fire, with nothing switching the
monitor off. The isolated Git 2.31 is the one that misbehaves with `false`: its ids are skipped,
with the reason, while `CONDUCT_OLD_GIT` is unset (gate G-old).
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import server_git, tool_env, tool_pins
from conductor.command import project_git
from conductor.command.accept_plumbing import call, oid
from conductor.command.adapters.process import ProcessRunner
from conductor.command.git_index import temporary_index
from conductor.hub import clone, projects_add
from tests.git_first_readers import READERS, reader_binary
from tests.git_repo_helpers import empty_home_environment, git
from tests.test_hub_clone import Finished, Group, bound  # noqa: F401
from tests.test_store import good_lane, write_project

for_every_reader = pytest.mark.parametrize("which", READERS)
for_every_owner = pytest.mark.parametrize("owner", ["owner_names_no_monitor",
                                                    "owner_names_a_monitor_program"])
LABEL = "acc-" + "a" * 32
NOBODY = {"started": [], "owner_runs": 0, "monitor_extension": False}


@dataclass(frozen=True)
class Scene:
    """One project repository made by the Git under test, and what Git wrote about its runs."""

    binary: str
    root: Path
    home: Path
    source: dict
    trace: Path
    log: Path
    blob: str

    def owner_runs(self) -> int:
        return len(self.log.read_bytes().splitlines()) if self.log.exists() else 0

    def started(self) -> list[str]:
        """The programs Git started: one entry per `run_command` line of its trace."""
        if not self.trace.exists():
            return []
        return [line.split("run_command:", 1)[1].strip()
                for line in self.trace.read_text(errors="replace").splitlines()
                if "run_command" in line]

    def tracing(self):
        """A runner class that is the real one, with every child's Git trace in one file."""
        trace = self.trace

        class Tracing(ProcessRunner):
            def run(self, spec):
                variables = {**spec.env, "GIT_TRACE": str(trace), "GIT_CONFIG_NOSYSTEM": "1"}
                return super().run(dataclasses.replace(spec, env=variables))

        return Tracing


def source_of(home: Path) -> dict:
    """What the owner's environment gives `tool_env`: no account configuration, one empty home."""
    names = ("SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG")
    kept = {name: value for name in names if (value := os.environ.get(name))}
    return {**kept, "HOME": str(home), "USERPROFILE": str(home), "XDG_CONFIG_HOME": str(home)}


def make_hook(folder: Path) -> tuple[Path, Path]:
    """A monitor program of the owner's: it logs each run and answers with the root as changed."""
    hook, log = folder / "owner-hook.sh", folder / "owner-hook.log"
    hook.write_bytes(b"#!/bin/sh\necho ran >> " + log.as_posix().encode()
                     + b"\nprintf 'tok1\\0/\\0'\n")
    hook.chmod(0o755)
    return hook, log


def scene_of(tmp_path, monkeypatch, which, owner) -> Scene:
    binary = reader_binary(which)
    home = tmp_path / "conduct-home"
    home.mkdir()
    quiet = empty_home_environment()
    for name, value in quiet.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    root = tmp_path / "project"
    root.mkdir()
    git("init", "-q", cwd=root, binary=binary)
    write_project(root, lanes={"claude": good_lane()})
    for name, body in {"README.md": "# Project\n", "docs/spec.md": "The spec.\n"}.items():
        (root / name).parent.mkdir(exist_ok=True)
        (root / name).write_bytes(body.encode())
    git("add", "--", "README.md", "docs", cwd=root, binary=binary)
    git("commit", "-q", "-m", "first", cwd=root, binary=binary)
    blob = git("rev-parse", "HEAD:README.md", cwd=root, binary=binary).stdout.decode().strip()
    hook, log = make_hook(tmp_path)
    if owner == "owner_names_a_monitor_program":
        git("config", "--local", "core.fsmonitor", hook.as_posix(), cwd=root, binary=binary)
    return Scene(binary, root, home, source_of(home), tmp_path / "trace.log", log, blob)


def pinned(scene: Scene) -> None:
    tool_pins.pin_tool("git", scene.binary, folder=scene.home, source=scene.source)


def observed(scene: Scene, monitor_extension: bool) -> dict:
    return {"started": scene.started(), "owner_runs": scene.owner_runs(),
            "monitor_extension": monitor_extension}


def index_commands(scene: Scene, read) -> bool:
    """The tree build of an acceptance (`accept_plumbing.materialize`): a private index, three
    commands; True when the private index carries the monitor's extension."""
    entry = f"100644 {scene.blob}\tz.txt\n".encode()
    with temporary_index(scene.root, LABEL, "sha1") as index:
        call(scene.root, read, "read-tree", "HEAD", index_file=index)
        call(scene.root, read, "update-index", "--index-info", stdin=entry, index_file=index)
        oid(call(scene.root, read, "write-tree", index_file=index))
        return b"FSMN" in index.path.read_bytes()


def project_reads(scene: Scene, read) -> bool:
    """What an active child asks of its project: the admission, the state's status, the first
    commit's `diff-index`, then the tree build."""
    assert project_git.repository_admission(scene.root, read).state == "repo"
    call(scene.root, read, "--no-optional-locks", "status", "--porcelain=v1", "-z",
         "--untracked-files=all")
    call(scene.root, read, "--no-optional-locks", "diff-index", "--cached", "--quiet", "HEAD")
    return index_commands(scene, read)


@for_every_reader
@for_every_owner
def test_the_reader_of_an_active_child_starts_no_monitor_program_and_leaves_no_extension(
        tmp_path, monkeypatch, which, owner):
    scene = scene_of(tmp_path, monkeypatch, which, owner)
    pinned(scene)
    read = server_git.project_git_reader(
        scene.root, source=scene.source, folder=scene.home, runner_class=scene.tracing())
    extension = project_reads(scene, read)
    assert observed(scene, extension) == NOBODY


@for_every_reader
@for_every_owner
def test_the_admission_of_a_new_project_starts_no_monitor_program(
        tmp_path, monkeypatch, which, owner):
    scene = scene_of(tmp_path, monkeypatch, which, owner)
    pinned(scene)
    for name, value in scene.source.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(projects_add, "ProcessRunner", scene.tracing())
    answer = projects_add._git(scene.root, scene.home)
    assert answer.state == "repo"
    assert observed(scene, False) == NOBODY


@for_every_reader
@for_every_owner
def test_the_environment_the_clone_hands_gh_starts_no_monitor_program_in_the_git_it_runs(
        tmp_path, monkeypatch, which, owner, bound):  # noqa: F811
    scene = scene_of(tmp_path, monkeypatch, which, owner)
    home, ticket = bound
    spawned = []

    def launch(argv, **options):
        spawned.append(options["env"])
        (ticket.path / ".git").mkdir()
        return Finished()

    clones = clone.Clones(home, source=scene.source, popen=launch, make_group=Group)
    clones.clone("operation-" + "d" * 32, "owner/app", ticket)
    env = {**spawned[0], "GIT_TRACE": str(scene.trace), "GIT_CONFIG_NOSYSTEM": "1"}
    private = tmp_path / "private.index"
    runs = [(["-C", str(scene.root), "status", "--porcelain=v1"], {}),
            (["-C", str(scene.root), "read-tree", "HEAD"], {"GIT_INDEX_FILE": str(private)}),
            (["-C", str(scene.root), "update-index", "--index-info"],
             {"GIT_INDEX_FILE": str(private)})]
    for args, extra in runs:
        done = subprocess.run([scene.binary, *args], env={**env, **extra}, capture_output=True,
                              input=f"100644 {scene.blob}\tz.txt\n".encode(), check=False)
        assert done.returncode == 0, done.stderr
    assert observed(scene, b"FSMN" in private.read_bytes()) == NOBODY


@for_every_reader
def test_with_nothing_switching_it_off_the_owners_monitor_program_runs_and_leaves_its_extension(
        tmp_path, monkeypatch, which):
    """Calibration of the three observations: each one fires when the product's value is absent."""
    scene = scene_of(tmp_path, monkeypatch, which, "owner_names_a_monitor_program")
    env = {**source_of(scene.home), "GIT_TRACE": str(scene.trace), "GIT_CONFIG_NOSYSTEM": "1"}
    (scene.root / "c.txt").write_bytes(b"three\n")
    for args in (["status", "--porcelain=v1"], ["add", "c.txt"]):
        done = subprocess.run([scene.binary, "-C", str(scene.root), *args], env=env,
                              capture_output=True, check=False)
        assert done.returncode == 0, done.stderr
    assert scene.owner_runs() > 0 and scene.started()
    assert b"FSMN" in (scene.root / ".git" / "index").read_bytes()


def test_the_flags_and_the_environment_say_the_monitor_off_with_one_empty_value():
    flags = project_git.GIT_FLAGS
    pairs = [flags[at + 1] for at in range(0, len(flags), 2) if flags[at] == "-c"]
    assert [pair for pair in pairs if pair.startswith("core.fsmonitor")] == ["core.fsmonitor="]
    env = tool_env.tool_env({}, SimpleNamespace(git=None, gh=None), "/home", platform="linux")
    assert (env["GIT_CONFIG_KEY_1"], env["GIT_CONFIG_VALUE_1"]) == ("core.fsmonitor", "")


def test_the_pin_of_gh_reads_its_version_with_the_empty_value_in_its_environment(tmp_path):
    """The environment pin_tool hands `gh --version` switches the file monitor off with the
    empty value. A stand-in runner reads that environment: a real gh never reads Git's settings
    for its version, so running it proved nothing of this, and on a cold Windows runner its first
    start outlasted the probe's timeout and wrote its state into the checkout (CI 37603275329)."""
    seen: list[tuple[list[str], dict[str, str]]] = []

    def run(argv: list[str], env) -> str:
        seen.append((list(argv), dict(env)))
        return "gh version 2.63.2 (2026-01-01)\n"

    path = str(tmp_path / ("gh.exe" if os.name == "nt" else "gh"))
    pin = tool_pins.pin_tool("gh", path, folder=tmp_path, run=run,
                             source={"HOME": str(tmp_path)})
    assert (pin.tool, pin.version) == ("gh", "2.63.2")
    [(argv, env)] = seen
    assert argv == [path, "--version"]
    assert (env["GIT_CONFIG_KEY_1"], env["GIT_CONFIG_VALUE_1"]) == ("core.fsmonitor", "")
