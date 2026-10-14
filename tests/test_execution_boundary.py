"""The pure fact "the execution boundary is provided" and its one typed refusal (R5).

The fact is a table over (platform, attempt mode). It opens nothing, so these tests need no
OS: each names the platform it asks about. Two of them tie the table to the code it speaks for,
the ACL journal's mode vocabulary and the runner's launch, so a row cannot be added or kept
without the mechanism behind it.
"""
import sys

import pytest

from conductor.command.adapters.process import CommandSpec, CommandSpecError, ProcessRunner
from conductor.command.adapters.process_acl import _grant
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.api_contracts import ApiRefusal
from conductor.command.execution_boundary import (
    ATTEMPT_MODES, BOUNDARY_ROUTE, BoundaryUnavailable, boundary_provided, require_boundary)
from conductor.command.graph_definition import GraphResource

SID = "S-1-15-2-1-2-3-4-5-6-7"
OWNER = "S-1-5-21-1-2-3-1000"


def test_the_attempt_modes_are_the_two_the_acl_journal_can_grant_for():
    assert ATTEMPT_MODES == ("dispatch", "review")
    for mode in ATTEMPT_MODES:
        assert _grant(OWNER, SID, mode=mode, leaf="work")
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        _grant(OWNER, SID, mode="plan", leaf="work")


@pytest.mark.parametrize("mode", ATTEMPT_MODES)
def test_windows_provides_the_boundary_for_both_attempt_modes(mode):
    assert boundary_provided("win32", mode) is True


@pytest.mark.parametrize("platform", ["linux", "darwin"])
@pytest.mark.parametrize("mode", ATTEMPT_MODES)
def test_linux_and_macos_report_no_boundary_for_both_attempt_modes(platform, mode):
    assert boundary_provided(platform, mode) is False


@pytest.mark.parametrize("platform", ["cygwin", "msys", "freebsd14", "aix", "", "WIN32", "windows"])
def test_a_platform_that_is_not_exactly_win32_has_no_boundary(platform):
    assert boundary_provided(platform, "dispatch") is False


@pytest.mark.parametrize("platform", ["win32", "linux"])
@pytest.mark.parametrize("mode", ["plan", "Dispatch", "", None, 3])
def test_an_unknown_attempt_mode_is_a_value_error_on_every_platform(platform, mode):
    with pytest.raises(ValueError, match="attempt mode"):
        boundary_provided(platform, mode)
    with pytest.raises(ValueError, match="attempt mode"):
        require_boundary(platform, mode)


@pytest.mark.parametrize("mode", ATTEMPT_MODES)
def test_require_boundary_returns_nothing_where_the_boundary_is_provided(mode):
    assert require_boundary("win32", mode) is None


@pytest.mark.parametrize("platform", ["linux", "darwin", "freebsd14"])
@pytest.mark.parametrize("mode", ATTEMPT_MODES)
def test_require_boundary_refuses_with_the_route_platform_and_mode(platform, mode):
    with pytest.raises(BoundaryUnavailable) as raised:
        require_boundary(platform, mode)
    refusal = raised.value
    assert (refusal.route, refusal.platform, refusal.mode) == (BOUNDARY_ROUTE, platform, mode)
    assert platform in str(refusal) and mode in str(refusal)


def test_the_refusal_route_is_a_sandbox_resource_name_the_r5_answer_can_carry():
    resource = GraphResource(kind="sandbox", name=BOUNDARY_ROUTE)
    assert resource.name == BOUNDARY_ROUTE
    refusal = ApiRefusal.plan_sandbox_unprovidable("run-1", "step-1", BOUNDARY_ROUTE)
    assert refusal.code == "service_refused"
    assert refusal.detail == {"run_id": "run-1", "node_id": "step-1", "sandbox": BOUNDARY_ROUTE}


def test_the_refusal_is_not_a_runner_error_so_no_spawn_catch_swallows_it():
    refusal = BoundaryUnavailable("linux", "dispatch")
    assert not isinstance(refusal, (CommandSpecError, ProfileRefused, OSError))
    assert isinstance(refusal, RuntimeError)


def test_the_predicate_agrees_with_the_runner_on_the_platform_the_test_runs_on(tmp_path):
    spec = CommandSpec(("not-started",), "work", boundary=WindowsContainer(SID))
    if boundary_provided(sys.platform, "dispatch"):
        from conductor.command.adapters import _winlaunch
        assert callable(_winlaunch.launch)
        return
    with pytest.raises(CommandSpecError, match="unavailable on this platform"):
        ProcessRunner._launch(spec, tmp_path, {}, None, None)
