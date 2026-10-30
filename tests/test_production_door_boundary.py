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
- the road: a Grok review through ``server.build`` starts inside the boundary entry; a dispatch is
  refused with the harness fake's spawn log empty. It never starts on the plain runner.

The host platform is read through ``providers.host_platform``, so each test names the platform it
asks about instead of depending on the machine it runs on.
"""
from __future__ import annotations

import ast
import dataclasses
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
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.execution_boundary import ATTEMPT_MODES
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, Confirmation, ControlRuntime

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
        expected = [False, provided] if provider_id == "grok-build" else [provided] * 2
        assert [resolution.registry.execution_boundary(provider_id, mode)
                for mode in ATTEMPT_MODES] == expected, provider_id


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
        expected = [False, takes] if provider_id == "grok-build" else [takes] * 2
        assert [resolution.registry.execution_boundary(provider_id, mode)
                for mode in ATTEMPT_MODES] == expected, provider_id


def _subscription_pins(
        tmp_path: Path, *, kept=("DecemberCommand", "logins")) -> list[ProviderConfig]:
    """The five pins, the four harnesses that sign in pinned to a subscription login (DSH: none).

    ``kept`` is the folder the logins are kept in: where the product keeps them by default
    (``<anything>/DecemberCommand/logins/<id>``), which a relay is derived from.
    """
    return [pin if pin.provider_id == "deepseek-harness" else dataclasses.replace(
        pin, auth="subscription", auth_home=str(tmp_path.joinpath(*kept, pin.provider_id)))
        for pin in _five_pins(tmp_path)]


#: Which harness has a relay (`HarnessProfile.login_relay`): the subscription road is covered there.
RELAYED = {"claude-code": True, "codex": True, "grok-build": True, "kimi-code": False}


@pytest.mark.parametrize("provider_id", sorted(RELAYED))
def test_the_production_door_over_subscription_pins_provides_the_boundary_where_there_is_a_relay(
        provider_id, tmp_path, monkeypatch):
    monkeypatch.setattr(provider_factory, "host_platform", lambda: "win32")
    recording_runners(monkeypatch, tmp_path / "scratch")

    resolution = resolve_providers(
        _subscription_pins(tmp_path), root=tmp_path, clock=lambda: grok_t.NOW, ids=grok_t._Ids())

    expected = [False, True] if provider_id == "grok-build" else [RELAYED[provider_id]] * 2
    assert [resolution.registry.execution_boundary(provider_id, mode)
            for mode in ATTEMPT_MODES] == expected


@pytest.mark.parametrize("kept", [("logins",), ("DecemberCommand",), ("DecemberCommand", "other")],
                         ids=["logins-alone", "product-folder-alone", "beside-logins"])
@pytest.mark.parametrize("provider_id", sorted(RELAYED))
def test_the_production_door_refuses_a_subscription_pin_kept_outside_the_product_logins_folder(
        provider_id, kept, tmp_path, monkeypatch):
    """A relay is derived from `<anything>/DecemberCommand/logins/<id>` alone, so a pin kept
    anywhere else is not provided the boundary for any harness, with a relay or without."""
    monkeypatch.setattr(provider_factory, "host_platform", lambda: "win32")
    recording_runners(monkeypatch, tmp_path / "scratch")

    resolution = resolve_providers(
        _subscription_pins(tmp_path, kept=kept), root=tmp_path, clock=lambda: grok_t.NOW,
        ids=grok_t._Ids())

    assert [resolution.registry.execution_boundary(provider_id, mode)
            for mode in ATTEMPT_MODES] == [False, False]


@pytest.mark.parametrize("provider_id", sorted(RELAYED))
def test_the_door_over_the_shipped_runner_and_subscription_pins_follows_its_entry_and_relay_loans(
        provider_id, tmp_path, monkeypatch):
    """No double: a harness with a relay is provided only if the shipped runner's entry takes the
    call and says it lends a relay home, both read off the runner this build ships."""
    monkeypatch.setattr(provider_factory, "host_platform", lambda: "win32")
    wanted = RELAYED[provider_id] and takes_the_call(ProcessRunner.container_profile) and (
        ProcessRunner.RELAY_HOME_LOANS is True)

    resolution = resolve_providers(
        _subscription_pins(tmp_path), root=tmp_path, clock=lambda: grok_t.NOW, ids=grok_t._Ids())

    expected = [False, wanted] if provider_id == "grok-build" else [wanted] * 2
    assert [resolution.registry.execution_boundary(provider_id, mode)
            for mode in ATTEMPT_MODES] == expected


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


# -- 3. the roads: Grok review and refused dispatch through the production build --


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
    knobs = {_fakegrok.SPAWN_LOG: str(log), WRITE_KNOB: EDIT,
             _fakegrok.EMIT_REVIEW: "enabled-fixed-review"}
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


def test_a_grok_review_through_the_production_build_starts_inside_the_boundary_entry(
        tmp_path, monkeypatch):
    served, made, root, log = _served_grok(tmp_path, monkeypatch, "win32")
    try:
        store = RunStore(root)
        config = {"cycle": {"id": "grok-review", "phases": ["diagnose"]},
                  "instances": [{"id": "reviewer", "adapter": "grok-build"}]}
        digest = snapshot_digest(config)
        store.create_run(RunEnvelope(run_id="run-grok", cycle_id="grok-review",
            created_at=grok_t.NOW, config_digest=digest, mode="confirm"), config)
        store.append(ArtifactDocument(artifact_id="seed-1", artifact_ref="candidate",
            run_id="run-grok", created_at=grok_t.NOW, media_type="text/markdown",
            content="Review this candidate through the production door."))
        proposal = ActionProposal(proposal_id="proposal-review", run_id="run-grok",
            attempt_id="attempt-review", instance_id="reviewer", capability="review",
            arguments={"work_item_id": "work-001", "target_artifact_refs": ["candidate"],
                       "result_artifact_ref": "diagnosis", "review_profile": "quality"},
            scope=("work",), proposed_by="lane", proposed_at=grok_t.NOW, timeout_seconds=60,
            rationale="review the candidate", config_digest=digest, input_binding="proposal-v1")
        store.append(proposal)
        runtime = ControlRuntime(store, served.command_registry,
                                 clock=lambda: grok_t.NOW, ids=grok_t._Ids())
        confirmation = Confirmation(confirmation_id="confirmation-review", run_id="run-grok",
            proposal_id=proposal.proposal_id, preview_digest=proposal.preview_digest,
            capability="review", scope=("work",), config_digest=digest,
            confirmed_by="test-owner", confirmed_at=grok_t.NOW)
        attempt = runtime.execute(runtime.authorize(confirmation, budget=Budget(
            max_actions=1, max_action_seconds=60, max_confirmation_age_seconds=60)))
        records = store.read("run-grok").records
    finally:
        served.server_close()

    (runner,) = made
    assert attempt.state is AttemptState.SUCCEEDED
    outputs = [row.value for row in records if row.kind == "artifact"
               and row.value.source_action_id is not None]
    assert len(outputs) == 1
    assert outputs[0].content == "# Diagnosis\nThe fake review read the supplied candidate.\n"
    assert outputs[0].input_artifact_ids == ("seed-1",)
    assert [served.command_registry.execution_boundary(GROK_PROVIDER_ID, mode)
            for mode in ATTEMPT_MODES] == [False, True]
    assert runner.events[-3:] == ["enter", "run-inside", "exit"]
    granted = [run for run in runner.runs if "--allow" in run.argv]
    assert len(granted) == 1 and granted[0].inside, "the review ran outside the entry"
    assert [entry.mode for entry in runner.entries] == ["review"]
    assert _fakegrok.allowed_tools(list(granted[0].argv)) == {"Read", "Grep", "Glob"}
    assert len(_fakegrok.spawns(log)) == len(runner.runs)
    assert not (root / "work" / "work-001" / "guard.py").exists()


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
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
