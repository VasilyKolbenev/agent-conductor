"""The five adapters launch their task attempts through the execution boundary entry (R5).

The entry is ``ProcessRunner.container_profile`` (H's contract, ``H-to-L-execution-boundary``).
This file proves lane L's half over a recording double of it (``tests/_fakeboundary.py``) and the
harness fakes, which are real executables that log every spawn they receive:

- a confined adapter starts its TASK attempt inside the entry, and only that attempt: the version
  preflight, the login status and the quota reads are handed no project folder and stay outside;
- it asks the entry for the attempt's own folders, the network and its mode, and puts the
  runtime variables and the launch value into the spec it runs;
- when the boundary is not provided it refuses BEFORE anything is created, so the harness fake
  logs no spawn at all, not even a version print;
- when the entry itself refuses, on the way in or on the way out, the attempt does not fall back
  to a plain launch, and a refusal on the way out never becomes a success.

The native witness, that an agent started this way cannot write the project root or the owner's
``.git``, is the host's and needs the host's folders call; it is not claimed here.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from conductor.command.adapters.grok_build import GROK_PROTOCOL, GROK_PROVIDER_ID
from conductor.command.adapters.harness_attempt import (
    RUNTIME_ENV, AttemptFolders, AttemptLaunch)
from conductor.command.adapters.harness_profile import boundary_detail
from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.execution_boundary import BoundaryUnavailable
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers
from conductor.ownership_errors import OwnerRefused

from tests import _fakeclaude, _fakecodex, _fakedsh, _fakegrok, _fakekimi
from tests import test_command_claude_transport as claude_t
from tests import test_command_codex_transport as codex_t
from tests import test_command_dsh_harness as dsh_t
from tests import test_command_grok_transport as grok_t
from tests import test_command_kimi_transport as kimi_t
from tests._fakeboundary import confined

HARNESSES = [
    pytest.param((claude_t, _fakeclaude), id="claude-code"),
    pytest.param((codex_t, _fakecodex), id="codex"),
    pytest.param((grok_t, _fakegrok), id="grok-build"),
    pytest.param((kimi_t, _fakekimi), id="kimi-code"),
    pytest.param((dsh_t, _fakedsh), id="deepseek-harness"),
]


def _pinned_file(adapter) -> str:
    """The file the child starts from: a binary's executable, an interpreter's entrypoint."""
    return getattr(adapter._pin, "entrypoint", None) or adapter._pin.executable


def _no_home_left(root: Path, adapter) -> bool:
    homes = root / adapter.profile.home_dir
    return not homes.exists() or not list(homes.iterdir())


# -- 1. the launch goes through the entry -------------------------------------


@pytest.mark.parametrize("harness", HARNESSES)
def test_each_adapter_starts_its_task_attempt_inside_the_boundary_entry(harness, tmp_path):
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch")

    receipt = module.run_once(adapter, module.a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    (entry,) = runner.entries
    assert (entry.mode, entry.internet_client) == ("dispatch", True)
    assert runner.events[-3:] == ["enter", "run-inside", "exit"]
    assert set(runner.events[:-3]) == {"run-outside"}, runner.events
    task = runner.runs[-1]
    assert task.inside and isinstance(task.boundary, WindowsContainer)
    assert len(fake.spawns(log)) == len(runner.runs) >= 2
    assert _no_home_left(root, adapter)


@pytest.mark.parametrize("harness", HARNESSES)
def test_each_adapter_asks_the_entry_for_the_attempts_own_folders(harness, tmp_path):
    module, _fake = harness
    adapter, root, _log = module.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch")

    module.run_once(adapter, module.a_request())

    (entry,) = runner.entries
    folders = entry.folders
    assert isinstance(folders, AttemptFolders)
    assert folders.work == "work/work-001"
    assert folders.home.startswith(adapter.profile.home_dir + "/")
    assert not Path(folders.home).is_absolute() and ".." not in Path(folders.home).parts
    assert folders.install == str(Path(_pinned_file(adapter)).parent)
    assert Path(folders.install).is_absolute()
    assert entry.paths["home"] == root / folders.home


@pytest.mark.parametrize("harness", HARNESSES)
def test_each_adapter_hands_the_spawn_the_runtime_variables_and_the_launch_value(
        harness, tmp_path):
    module, _fake = harness
    adapter, _root, _log = module.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch")

    module.run_once(adapter, module.a_request())

    (entry,) = runner.entries
    task = runner.runs[-1]
    runtime = str(entry.paths["runtime"])
    assert {name: task.env[name] for name in RUNTIME_ENV} == dict.fromkeys(RUNTIME_ENV, runtime)
    assert task.cwd == "work/work-001"
    assert task.argv[0] == adapter._argv_prefix()[0]
    for outside in runner.runs[:-1]:
        assert outside.boundary is None and not outside.inside
        assert not set(RUNTIME_ENV) & set(outside.env)


def test_every_catalogued_adapter_carries_the_launch_the_boundary_judges():
    """The registry answers True for an adapter with no boundary seam, so none may lack it."""
    assert set(PROVIDER_CATALOG) == {
        "claude-code", "codex", "grok-build", "kimi-code", "deepseek-harness"}
    for provider_id, entry in PROVIDER_CATALOG.items():
        assert issubclass(entry.adapter_class, AttemptLaunch), provider_id


def test_the_folders_of_an_attempt_are_the_three_the_contract_names():
    names = [field.name for field in dataclasses.fields(AttemptFolders)]

    assert names == ["work", "home", "install"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        AttemptFolders("work/work-001", None, "C:/install").work = "elsewhere"


# -- 2. a boundary that is not provided spawns nothing ------------------------


@pytest.mark.parametrize("platform", ["linux", "darwin"])
@pytest.mark.parametrize("harness", HARNESSES)
def test_a_refused_boundary_spawns_nothing_for_each_adapter(harness, platform, tmp_path):
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform=platform)
    request = module.a_request()

    receipt = module.run_once(adapter, request)

    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert fake.spawns(log) == [], "a child was started although the boundary is refused"
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert _no_home_left(root, adapter)
    assert not adapter._workspace.is_claimed(request.run_id, request.action_id)


def test_an_action_an_earlier_attempt_claimed_stays_unknown_when_the_boundary_is_gone(tmp_path):
    adapter, _root, log = grok_t.a_harness(tmp_path)
    confined(adapter, tmp_path / "scratch", platform="win32")
    request = grok_t.a_request()
    assert grok_t.run_once(adapter, request).outcome == "succeeded"
    spawned = len(_fakegrok.spawns(log))
    adapter.confine("linux")

    again = grok_t.run_once(adapter, request)

    assert again.outcome == "unknown", "the earlier attempt may have run; failed would deny it"
    assert len(_fakegrok.spawns(log)) == spawned


def test_the_refusal_sentence_carries_no_platform_path_or_vendor_detail():
    sentence = boundary_detail("Grok Build")

    assert sentence == ("the execution boundary is not provided for this Grok Build attempt on "
                        "this build, so no task was spawned")


def test_a_confined_attempt_that_reaches_the_spawn_unrefused_still_starts_no_child(
        tmp_path, monkeypatch):
    adapter, root, log = grok_t.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="linux")
    guards = []
    monkeypatch.setattr(ProcessRunner, "login_write_guard",
                        classmethod(lambda cls, *args: guards.append(args)))

    with pytest.raises(BoundaryUnavailable) as raised:
        adapter._attempt(("--version",), "work/work-001", timeout=30, mode="dispatch")

    assert (raised.value.platform, raised.value.mode) == ("linux", "dispatch")
    assert runner.runs == [] and _fakegrok.spawns(log) == []
    assert guards == [], "the login write guard was entered before the boundary was judged"
    assert _no_home_left(root, adapter)


def test_an_unknown_attempt_mode_is_refused_on_every_platform_before_a_spawn(tmp_path):
    adapter, _root, log = grok_t.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")

    with pytest.raises(ValueError, match="attempt mode"):
        adapter._attempt(("--version",), "work/work-001", timeout=30, mode="plan")

    assert runner.runs == [] and _fakegrok.spawns(log) == []


def test_the_subscription_road_is_not_provided_and_is_refused_before_it_spawns(tmp_path):
    login = tmp_path / "login"
    login.mkdir()
    adapter, _root, log = claude_t.a_harness(
        tmp_path, auth="subscription", auth_home=str(login))
    runner = confined(adapter, tmp_path / "scratch", platform="win32")

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert adapter.boundary_provided("dispatch") is False
    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakeclaude.spawns(log) == [] and runner.runs == []


# -- 3. the preflights stay on the plain road ---------------------------------


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_a_preflight_is_not_a_task_attempt_and_never_reaches_the_entry(platform, tmp_path):
    adapter, _root, log = grok_t.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform=platform)
    adapter._workspace.work_root()

    outcome = adapter._attempt(("--version",), "work", timeout=30)

    assert outcome.status == "completed"
    assert runner.events == ["run-outside"] and runner.entries == []
    assert len(_fakegrok.spawns(log)) == 1


# -- 4. a refused entry is never a plain launch --------------------------------


ENTRY_REFUSALS = [
    pytest.param(OwnerRefused("owner_required", "no live owner"), id="no-owner"),
    pytest.param(ProfileRefused("profile_acl_invalid", "not the recorded object"), id="profile"),
    pytest.param(OSError(203, "CreateProcessW failed"), id="launch"),
]


@pytest.mark.parametrize("refusal", ENTRY_REFUSALS)
@pytest.mark.parametrize("harness", HARNESSES)
def test_a_refused_entry_starts_no_task_and_never_falls_back_to_a_plain_launch(
        harness, refusal, tmp_path):
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", enter_error=refusal)

    with pytest.raises(adapter.error, match="could not start the pinned build") as raised:
        module.run_once(adapter, module.a_request())

    assert runner.events[-1] == "enter" and "run-inside" not in runner.events
    assert runner.runs and not any(run.inside for run in runner.runs), "only preflights ran"
    assert len(fake.spawns(log)) == len(runner.runs), "a task child ran without the boundary"
    assert str(refusal) not in str(raised.value)
    assert _no_home_left(root, adapter)


@pytest.mark.parametrize("harness", HARNESSES)
def test_a_refusal_on_the_way_out_is_an_error_and_never_a_success(harness, tmp_path):
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    refusal = ProfileRefused("profile_acl_unproven", "a token is still alive")
    runner = confined(adapter, tmp_path / "scratch", exit_error=refusal)

    with pytest.raises(adapter.error, match="could not start the pinned build"):
        module.run_once(adapter, module.a_request())

    assert runner.events[-2:] == ["run-inside", "exit"]
    assert len(fake.spawns(log)) == len(runner.runs), "the child ran, so the attempt is unknown"
    assert _no_home_left(root, adapter)


# -- 5. what confine promises ---------------------------------------------------


@pytest.mark.parametrize("platform", ["", None, 3])
def test_a_transport_is_confined_only_for_a_named_platform(platform, tmp_path):
    adapter, _root, _log = grok_t.a_harness(tmp_path)

    with pytest.raises(adapter.error, match="platform its boundary is judged for"):
        adapter.confine(platform)

    assert adapter.boundary_provided("dispatch") is False


def test_a_transport_never_confined_reports_no_boundary_on_any_platform(tmp_path):
    adapter, _root, _log = grok_t.a_harness(tmp_path)

    assert [adapter.boundary_provided(mode) for mode in ("dispatch", "review")] == [False, False]
    with pytest.raises(ValueError, match="attempt mode"):
        adapter.boundary_provided("plan")


@pytest.mark.parametrize("platform,expected", [("win32", True), ("linux", False)])
def test_a_confined_transport_reports_what_the_predicate_says_for_its_platform(
        platform, expected, tmp_path):
    adapter, _root, _log = grok_t.a_harness(tmp_path)
    confined(adapter, tmp_path / "scratch", platform=platform)

    assert [adapter.boundary_provided(mode) for mode in ("dispatch", "review")] == [expected] * 2
    with pytest.raises(ValueError, match="attempt mode"):
        adapter.boundary_provided("plan")


# -- 6. the provider door is the one place an adapter is confined -------------


def _grok_through_the_provider_door(tmp_path, platform):
    """The Grok adapter as `resolve_providers` builds it, with the platform named or not."""
    exe = grok_t._executable(tmp_path)
    root = tmp_path / "root"
    (root / INSTRUCTION_DIR).mkdir(parents=True)
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        grok_t.INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    log = tmp_path / "spawns.log"
    environ = {_fakegrok.SPAWN_LOG: str(log)}
    config = ProviderConfig(
        provider_id=GROK_PROVIDER_ID, executable=str(exe), protocol=GROK_PROTOCOL,
        env_allow=tuple(sorted(environ)))
    resolution = resolve_providers(
        [config], root=root, clock=lambda: grok_t.NOW, ids=grok_t._Ids(), environ=environ,
        confine_platform=platform)
    return resolution.registry, resolution.registry.resolve(GROK_PROVIDER_ID), log


def test_the_provider_door_builds_an_unconfined_adapter_when_no_platform_is_named(tmp_path):
    registry, adapter, log = _grok_through_the_provider_door(tmp_path, None)

    receipt = grok_t.run_once(adapter, grok_t.a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert registry.execution_boundary(GROK_PROVIDER_ID, "dispatch") is False
    assert len(_fakegrok.spawns(log)) == 2, "the launch is the one that existed before R5"


@pytest.mark.parametrize("platform,provided", [("win32", True), ("linux", False)])
def test_the_provider_door_confines_the_adapter_for_the_platform_it_is_given(
        platform, provided, tmp_path):
    registry, adapter, _log = _grok_through_the_provider_door(tmp_path, platform)

    assert [registry.execution_boundary(GROK_PROVIDER_ID, mode)
            for mode in ("dispatch", "review")] == [provided, provided]


def test_an_adapter_the_provider_door_confined_for_a_platform_without_a_boundary_does_not_run(
        tmp_path):
    _registry, adapter, log = _grok_through_the_provider_door(tmp_path, "linux")

    receipt = grok_t.run_once(adapter, grok_t.a_request())

    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakegrok.spawns(log) == []
