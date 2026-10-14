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
  to a plain launch, and a refusal on the way out never becomes a success;
- the fact that the boundary is provided follows the entry of the runner this build ships: a
  runner whose entry cannot take the call the adapters make is refused before a spawn, not
  called (``TypeError``, an attempt recorded ``unknown``).

The native witness, that an agent started this way cannot write the project root or the owner's
``.git``, is the host's and needs the host's folders call; it is not claimed here.
"""
from __future__ import annotations

import dataclasses
import os
import shutil
from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.grok_build import GROK_PROTOCOL, GROK_PROVIDER_ID
from conductor.command.adapters.dsh_harness import DshPin
from conductor.command.adapters.harness_attempt import (
    RUNTIME_ENV, AttemptFolders, AttemptLaunch, install_folder)
from conductor.command.adapters.harness_profile import boundary_detail
from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR
from conductor.command.adapters.process import ProcessRunner, ProcessRunnerError
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.boundary_entry import entry_call, entry_takes_the_call
from conductor.command.execution_boundary import ATTEMPT_MODES, BoundaryUnavailable
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers
from conductor.ownership_errors import OwnerRefused

from tests import _fakeclaude, _fakecodex, _fakedsh, _fakegrok, _fakekimi
from tests import test_command_claude_transport as claude_t
from tests import test_command_codex_transport as codex_t
from tests import test_command_dsh_harness as dsh_t
from tests import test_command_grok_transport as grok_t
from tests import test_command_kimi_transport as kimi_t
from tests._fakeboundary import (
    LAYOUT, NODE_FLAGS, confined, pin_dir, recording, recording_runners, takes_the_call,
    version_folder)

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
    assert folders.install == str(version_folder(tmp_path, adapter.manifest.adapter_id))
    assert Path(folders.install).is_absolute()
    assert Path(_pinned_file(adapter)).is_relative_to(folders.install)
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


class _EntryWithoutFolders(ProcessRunner):
    """The runner's entry as it stood before it could take the attempt's own folders."""

    def container_profile(self, *, internet_client=False, mode=None):
        raise AssertionError("the entry was called by an attempt that cannot name its folders")


def _on_runner(adapter, runner_class):
    """The adapter, spawning through a ``runner_class`` that shares its root and environment."""
    old = adapter._runner
    adapter._runner = runner_class(
        old._root, environ=old._environ, spawns_allowed=old._spawns_allowed)


def test_a_confined_adapter_is_provided_over_the_shipped_runner_only_if_its_entry_takes_the_call(
        tmp_path):
    """The fact is tied to the runner this build ships, not to what the adapters assume of it.

    Before the runner's entry takes the attempt's own folders the fact is no; once it does, the
    same assertion holds with yes. Either way a build never says yes to a call it cannot make.
    """
    adapter, _root, _log = grok_t.a_harness(tmp_path)
    adapter.confine("win32")
    takes = takes_the_call(ProcessRunner.container_profile)

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [takes, takes]
    assert [AdapterRegistry([adapter]).execution_boundary(GROK_PROVIDER_ID, mode)
            for mode in ATTEMPT_MODES] == [takes, takes]


def test_an_attempt_over_a_runner_whose_entry_cannot_take_the_folders_is_refused_before_a_spawn(
        tmp_path):
    adapter, root, log = grok_t.a_harness(tmp_path)
    _on_runner(adapter, _EntryWithoutFolders)
    adapter.confine("win32")

    receipt = grok_t.run_once(adapter, grok_t.a_request())

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [False, False]
    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakegrok.spawns(log) == [], "a child was started although the entry cannot be asked"
    assert _no_home_left(root, adapter)


def test_a_road_that_skips_the_question_still_cannot_call_an_entry_without_the_folders(tmp_path):
    adapter, root, log = grok_t.a_harness(tmp_path)
    _on_runner(adapter, _EntryWithoutFolders)
    adapter.confine("win32")

    with pytest.raises(BoundaryUnavailable) as raised:
        adapter._attempt(("--version",), "work/work-001", timeout=30, mode="dispatch")

    assert (raised.value.platform, raised.value.mode) == ("win32", "dispatch")
    assert _fakegrok.spawns(log) == [] and _no_home_left(root, adapter)


class _CountingEntry:
    """A runner whose entry takes the call and counts every time it is really called."""

    calls = 0

    def container_profile(self, *, internet_client=False, mode=None, folders=None):
        type(self).calls += 1
        raise AssertionError("the check called the entry")


@pytest.mark.parametrize("mode", ATTEMPT_MODES)
def test_the_entry_check_binds_the_call_and_never_makes_it(mode):
    assert entry_takes_the_call(_CountingEntry(), mode) is True
    assert entry_takes_the_call(_EntryWithoutFolders("."), mode) is False
    assert entry_takes_the_call(object(), mode) is False
    assert _CountingEntry.calls == 0


def test_the_call_the_adapters_make_is_the_call_the_fact_is_judged_by(tmp_path):
    adapter, _root, _log = grok_t.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch")

    grok_t.run_once(adapter, grok_t.a_request())

    (entry,) = runner.entries
    assert entry_call(entry.mode, entry.folders) == {
        "mode": entry.mode, "internet_client": entry.internet_client, "folders": entry.folders}
    assert takes_the_call(type(runner).container_profile)


def test_a_confined_adapter_over_the_shipped_runner_starts_no_task_child(tmp_path):
    """No double: whatever the shipped runner answers, nothing falls back to the plain launch.

    A runner whose entry cannot take the call is refused before the version print; one that can,
    off Windows or without a live owner, refuses at the entry, after the version print. Either
    way the harness fake never receives a task.
    """
    adapter, root, log = grok_t.a_harness(tmp_path)
    adapter.confine("win32")

    try:
        grok_t.run_once(adapter, grok_t.a_request())
    except adapter.error:
        pass  # the entry was reached and refused: no live owner on this host

    assert _fakegrok.prompt_spawns(log) == [], "a task child ran on the shipped runner"
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


def _grok_through_the_provider_door(tmp_path, platform, monkeypatch):
    """The Grok adapter as `resolve_providers` builds it, with the platform named or not.

    The door builds a recording boundary entry in place of the shipped runner, whose entry
    answers for itself (see ``recording_runners``).
    """
    recording_runners(monkeypatch, tmp_path / "scratch")
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


def test_the_provider_door_builds_an_unconfined_adapter_only_when_the_caller_names_none(
        tmp_path, monkeypatch):
    registry, adapter, log = _grok_through_the_provider_door(tmp_path, None, monkeypatch)

    receipt = grok_t.run_once(adapter, grok_t.a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert registry.execution_boundary(GROK_PROVIDER_ID, "dispatch") is False
    assert len(_fakegrok.spawns(log)) == 2, "the launch is the one that existed before R5"


@pytest.mark.parametrize("platform,provided", [("win32", True), ("linux", False)])
def test_the_provider_door_confines_the_adapter_for_the_platform_it_is_given(
        platform, provided, tmp_path, monkeypatch):
    registry, adapter, _log = _grok_through_the_provider_door(tmp_path, platform, monkeypatch)

    assert [registry.execution_boundary(GROK_PROVIDER_ID, mode)
            for mode in ("dispatch", "review")] == [provided, provided]


def test_an_adapter_the_provider_door_confined_for_a_platform_without_a_boundary_does_not_run(
        tmp_path, monkeypatch):
    _registry, adapter, log = _grok_through_the_provider_door(tmp_path, "linux", monkeypatch)

    receipt = grok_t.run_once(adapter, grok_t.a_request())

    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakegrok.spawns(log) == []


# -- 7. the install folder is the version folder ---------------------------------


@pytest.mark.parametrize("provider_id", sorted(LAYOUT))
def test_the_install_folder_is_the_version_folder_at_whatever_depth_the_pinned_file_sits(
        provider_id, tmp_path):
    pinned = pin_dir(tmp_path, provider_id) / "pinned-file"

    assert install_folder(str(pinned)) == str(version_folder(tmp_path, provider_id))


def test_the_install_tree_is_found_by_name_whatever_case_the_disk_keeps(tmp_path):
    pinned = tmp_path / "Harnesses" / "tool" / "1.2.3" / "deeper" / "tool.exe"

    assert install_folder(str(pinned)) == str(tmp_path / "Harnesses" / "tool" / "1.2.3")


@pytest.mark.parametrize("parts", [
    pytest.param(("harnesses", "tool", "tool.exe"), id="no-version-folder"),
    pytest.param(("harnesses", "tool.exe"), id="no-name-folder"),
    pytest.param(("elsewhere", "tool", "1.2.3", "tool.exe"), id="no-install-tree"),
])
def test_a_pinned_file_outside_a_version_folder_of_the_install_tree_has_no_install_folder(
        parts, tmp_path):
    with pytest.raises(ProcessRunnerError, match="not installed under"):
        install_folder(str(tmp_path.joinpath(*parts)))


def test_a_confined_attempt_for_a_build_installed_outside_the_tree_starts_no_task(tmp_path):
    adapter, root, log = grok_t.a_harness(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    moved = elsewhere / Path(adapter._pin.executable).name
    shutil.copy2(adapter._pin.executable, moved)
    adapter._pin = dataclasses.replace(adapter._pin, executable=str(moved))
    runner = confined(adapter, tmp_path / "scratch")

    with pytest.raises(adapter.error, match="could not start the pinned build"):
        grok_t.run_once(adapter, grok_t.a_request())

    assert runner.entries == [] and not any(run.inside for run in runner.runs)
    assert len(_fakegrok.spawns(log)) == len(runner.runs), "a task child ran without the boundary"
    assert _no_home_left(root, adapter)


# -- 8. DSH starts inside the boundary on its real entry ---------------------------


def _dsh_pinned_by_a_wandering_path(tmp_path):
    """The DSH adapter whose pinned entry is not its own real path, as a pnpm link is not."""
    adapter, root, log = dsh_t.a_harness(tmp_path)
    entry = Path(adapter._pin.entrypoint)
    wandering = str(entry.parent / ".." / entry.parent.name / entry.name)
    adapter._pin = DshPin(
        node_executable=adapter._pin.node_executable, entrypoint=wandering,
        env_allow=adapter._pin.env_allow)
    assert os.path.realpath(wandering) != wandering
    return adapter, root, log


def test_dsh_starts_its_task_inside_the_boundary_on_the_real_entry_with_symlinks_kept(tmp_path):
    adapter, _root, _log = _dsh_pinned_by_a_wandering_path(tmp_path)
    runner = confined(adapter, tmp_path / "scratch")

    receipt = dsh_t.run_once(adapter, dsh_t.a_request())

    node, pinned = adapter._pin.node_executable, adapter._pin.entrypoint
    assert receipt.outcome == "succeeded", receipt.detail
    task = runner.runs[-1]
    assert task.inside
    assert task.argv[:4] == (
        node, "--preserve-symlinks", "--preserve-symlinks-main", os.path.realpath(pinned))
    assert task.argv[4:6] == ("--profile", "headless")
    for outside in runner.runs[:-1]:
        assert outside.argv[:3] == (node, pinned, "--version") and not outside.inside


def test_dsh_keeps_the_pin_as_the_operator_wrote_it_on_the_plain_road(tmp_path):
    adapter, _root, _log = _dsh_pinned_by_a_wandering_path(tmp_path)
    runner = recording(adapter, tmp_path / "scratch")

    receipt = dsh_t.run_once(adapter, dsh_t.a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    node, pinned = adapter._pin.node_executable, adapter._pin.entrypoint
    assert runner.runs[-1].argv[:2] == (node, pinned) and not runner.runs[-1].inside
    assert not set(NODE_FLAGS) & {token for run in runner.runs for token in run.argv}


@pytest.mark.parametrize("harness", [pytest.param(row.values[0], id=row.id)
                                     for row in HARNESSES if row.id != "deepseek-harness"])
def test_the_four_native_binaries_start_inside_the_boundary_on_the_pin_as_written(
        harness, tmp_path):
    module, _fake = harness
    adapter, _root, _log = module.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch")

    module.run_once(adapter, module.a_request())

    prefix = adapter._argv_prefix()
    assert runner.runs[-1].inside and runner.runs[-1].argv[:len(prefix)] == prefix
    assert not set(NODE_FLAGS) & set(runner.runs[-1].argv)
