"""The production door starts no harness outside the execution boundary (R5, TL merge gate).

The gate (``TL-merge-gate-grok-grant``) holds the Grok write grant until the door production builds
its adapters through confines every task attempt where the boundary is provided and refuses it
before a spawn everywhere else, whatever the plan says. Production has one such door,
``resolve_providers``, and ``server.build`` calls it without naming a platform, so what the door
does when it is told nothing IS the production behaviour. These tests hold that default, from the
three sides that can drift apart:

- the door itself: asked for nothing, it confines each catalogued harness for the host it runs on;
- the callers: no code under ``src`` names the unconfined launch, which exists for the harness
  fakes of the test suite and for nothing else;
- the road: a Grok dispatch through ``server.build`` either starts inside the boundary entry or is
  refused with the harness fake's spawn log empty. It never starts on the plain runner.

The host platform is read through ``providers.host_platform``, so each test names the platform it
asks about instead of depending on the machine it runs on.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from conductor import server
from conductor.command import providers as provider_factory
from conductor.command.adapters.grok_build import GROK_PROTOCOL, GROK_PROVIDER_ID
from conductor.command.adapters.harness_profile import boundary_detail
from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.execution_boundary import ATTEMPT_MODES
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers

from tests import _fakegrok
from tests import test_command_grok_transport as grok_t
from tests._fakeboundary import pin_dir, recording_runners, takes_the_call
from tests.test_store import good_lane, write_project

SRC = Path(provider_factory.__file__).resolve().parents[1]
PLATFORMS = [("win32", True), ("linux", False), ("darwin", False)]
WRITE_KNOB = "FAKEGROK_WRITE_FILE"
EDIT = "guard.py:# a real change\n"


def _five_pins(tmp_path: Path) -> list[ProviderConfig]:
    """One pinned config per catalogued harness, installed at its layout; nothing runs the files.

    The install folder is a fact of the pin's path, and a build outside the install tree is not
    provided the boundary, so each file stands where the owner's install tree keeps it.
    """
    pins = []
    for provider_id, entry in PROVIDER_CATALOG.items():
        folder = pin_dir(tmp_path, provider_id)
        folder.mkdir(parents=True)
        executable = folder / f"{provider_id}.exe"
        executable.write_text("", encoding="utf-8")
        entrypoint = ""
        if provider_id == "deepseek-harness":
            entrypoint = str(folder / "dsh.js")
            Path(entrypoint).write_text("", encoding="utf-8")
        pins.append(ProviderConfig(
            provider_id=provider_id, executable=str(executable), protocol=entry.protocol,
            env_allow=(), entrypoint=entrypoint))
    return pins


# -- 1. the door, asked for nothing --------------------------------------------


@pytest.mark.parametrize("platform,provided", PLATFORMS)
def test_the_provider_door_asked_for_nothing_confines_each_harness_for_the_host_it_runs_on(
        platform, provided, tmp_path, monkeypatch):
    monkeypatch.setattr(provider_factory, "host_platform", lambda: platform)
    recording_runners(monkeypatch, tmp_path / "scratch")

    resolution = resolve_providers(
        _five_pins(tmp_path), root=tmp_path, clock=lambda: grok_t.NOW, ids=grok_t._Ids())

    assert len(resolution.registry.manifests()) == len(PROVIDER_CATALOG) == 5
    for provider_id in PROVIDER_CATALOG:
        assert [resolution.registry.execution_boundary(provider_id, mode)
                for mode in ATTEMPT_MODES] == [provided] * 2, provider_id


def test_the_door_over_the_shipped_runner_says_yes_only_if_the_runners_entry_takes_the_call(
        tmp_path, monkeypatch):
    """No double: the answer of the production door follows the runner this build ships.

    A tree whose runner cannot take the attempt's own folders says no for all five at the doors,
    so no Windows task is sent to an entry that would raise (and be recorded ``unknown``); a tree
    whose runner can, says yes. The expectation is read off the shipped runner, not assumed.
    """
    monkeypatch.setattr(provider_factory, "host_platform", lambda: "win32")
    takes = takes_the_call(ProcessRunner.container_profile)

    resolution = resolve_providers(
        _five_pins(tmp_path), root=tmp_path, clock=lambda: grok_t.NOW, ids=grok_t._Ids())

    for provider_id in PROVIDER_CATALOG:
        assert [resolution.registry.execution_boundary(provider_id, mode)
                for mode in ATTEMPT_MODES] == [takes] * 2, provider_id


def test_the_host_platform_is_the_one_the_interpreter_reports():
    assert provider_factory.host_platform() == sys.platform


# -- 2. the callers -------------------------------------------------------------


def _source_calls(name: str):
    """Every call of ``name`` (a function or a method) under ``src``, with its file."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            if getattr(callee, "id", None) == name or getattr(callee, "attr", None) == name:
                found.append((path.name, node))
    return found


def test_production_calls_the_provider_door_once_and_never_names_the_unconfined_launch():
    doors = [(file, call) for file, call in _source_calls("resolve_providers")]

    assert [file for file, _call in doors] == ["server.py"]
    for _file, call in doors:
        for keyword in call.keywords:
            assert keyword.arg != "confine_platform" or not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is None)


def test_no_code_under_src_spells_the_unconfined_launch():
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "confine_platform":
                assert not (isinstance(node.value, ast.Constant) and node.value.value is None), (
                    f"{path.name} builds an unconfined harness")


def test_only_the_provider_door_confines_an_adapter():
    assert {file for file, _call in _source_calls("confine")} == {"providers.py"}


# -- 3. the road: a Grok dispatch through the production build ------------------


def _served_grok(tmp_path, monkeypatch, platform):
    """``server.build`` over a project with the Grok fake pinned, and the runner it builds.

    The runner the provider door builds is replaced by the recording boundary double, so what the
    adapter asks of the entry is read off the entry. Nothing else about the build is changed: the
    default platform is the one the production door gets, and it is named here only through the
    host seam.
    """
    project = tmp_path / "project"
    project.mkdir()
    root = Path(write_project(project, lanes={"claude": good_lane()}))
    (root / INSTRUCTION_DIR).mkdir()
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        grok_t.INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    log = tmp_path / "spawns.log"
    knobs = {_fakegrok.SPAWN_LOG: str(log), WRITE_KNOB: EDIT}
    for name, value in knobs.items():
        monkeypatch.setenv(name, value)
    made = recording_runners(monkeypatch, tmp_path / "scratch")
    monkeypatch.setattr(provider_factory, "host_platform", lambda: platform)
    config = ProviderConfig(
        provider_id=GROK_PROVIDER_ID, executable=str(grok_t._executable(tmp_path)),
        protocol=GROK_PROTOCOL, env_allow=tuple(sorted(knobs)))
    served = server.build(root, 0, providers=[config], clock=lambda: grok_t.NOW,
                          ids=grok_t._Ids())
    return served, made, root, log


def test_a_grok_dispatch_through_the_production_build_starts_inside_the_boundary_entry(
        tmp_path, monkeypatch):
    served, made, root, log = _served_grok(tmp_path, monkeypatch, "win32")
    try:
        adapter = served.command_registry.resolve(GROK_PROVIDER_ID)
        receipt = grok_t.run_once(adapter, grok_t.a_request())
    finally:
        served.server_close()

    (runner,) = made
    assert receipt.outcome == "succeeded", receipt.detail
    assert [served.command_registry.execution_boundary(GROK_PROVIDER_ID, mode)
            for mode in ATTEMPT_MODES] == [True, True]
    assert runner.events[-3:] == ["enter", "run-inside", "exit"]
    granted = [run for run in runner.runs if "--allow" in run.argv]
    assert len(granted) == 1 and granted[0].inside, "the write grant ran outside the entry"
    assert len(_fakegrok.spawns(log)) == len(runner.runs)
    assert (root / "work" / "work-001" / "guard.py").read_text(encoding="utf-8") == (
        "# a real change\n")


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_grok_dispatch_through_the_production_build_is_refused_before_it_spawns(
        platform, tmp_path, monkeypatch):
    served, made, root, log = _served_grok(tmp_path, monkeypatch, platform)
    try:
        adapter = served.command_registry.resolve(GROK_PROVIDER_ID)
        receipt = grok_t.run_once(adapter, grok_t.a_request())
    finally:
        served.server_close()

    (runner,) = made
    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakegrok.spawns(log) == [], "a child was started for a dispatch with no boundary"
    assert (runner.runs, runner.entries, runner.events) == ([], [], [])
    assert not (root / "work" / "work-001" / "guard.py").exists()
