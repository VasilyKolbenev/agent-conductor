"""What the OS-boundary checks say about their own host, so a red or slow run names the fact.

The Windows checks were written on a desktop and first ran on a CI runner of another kind (a
server edition, an administrator account). Each difference decides whether a check measures the
OS or only the host, and none of them is a product finding. The words for a difference are pure
and tested on every host; the measurement runs where the container is, and reports a
difference as a warning, because the same run must go on to judge the boundary.
"""
from __future__ import annotations

import os
import time
import warnings

import pytest

from tests.os_boundary_host import (
    SLOW_START_SECONDS,
    HostFacts,
    app_packages_may_read,
    differences,
)

if os.name == "nt":
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import container, implement_box, powershell_line  # noqa: F401

_DESKTOP = HostFacts(
    dotnet_answered=True, cmdlets_confined=True, cmdlets_unconfined=True, import_error="",
    start_seconds=0.6, modules_readable_by_containers=True,
    powershell_readable_by_containers=True)
_WITH_APP_PACKAGES = "D:PAI(A;;0x1200a9;;;BU)(A;;0x1200a9;;;AC)(A;;0x1200a9;;;S-1-15-2-2)"
_WITHOUT_APP_PACKAGES = "D:PAI(A;;0x1200a9;;;BU)(A;;0x1200a9;;;S-1-15-2-2)"
_DENYING_APP_PACKAGES = "D:PAI(A;;0x1200a9;;;BU)(D;;0x1200a9;;;AC)"


def test_a_host_like_the_desktop_the_checks_were_written_on_has_no_difference_to_name():
    assert differences(_DESKTOP) == []


def test_a_container_that_cannot_resolve_its_cmdlets_is_named_with_powershells_own_words():
    facts = HostFacts(**{**_DESKTOP.__dict__, "cmdlets_confined": False,
                         "import_error": "Access to the path is denied"})
    [named] = differences(facts)
    assert "utility cmdlets" in named and "Access to the path is denied" in named
    assert "the unconfined one can" in named


def test_a_host_that_loses_the_cmdlets_in_both_launches_says_so():
    facts = HostFacts(**{**_DESKTOP.__dict__, "cmdlets_confined": False,
                         "cmdlets_unconfined": False})
    [named] = differences(facts)
    assert "cannot either" in named and "nothing" in named


def test_a_slow_first_answer_is_named_with_its_seconds():
    facts = HostFacts(**{**_DESKTOP.__dict__, "start_seconds": SLOW_START_SECONDS + 7.5})
    [named] = differences(facts)
    assert "12.5 s" in named


def test_a_module_directory_and_a_shell_that_containers_may_not_read_are_named_apart():
    facts = HostFacts(**{**_DESKTOP.__dict__, "modules_readable_by_containers": False,
                         "powershell_readable_by_containers": False})
    modules, shell = differences(facts)
    assert "module directory" in modules and "powershell.exe" in shell


@pytest.mark.parametrize("sddl, allowed", [
    (_WITH_APP_PACKAGES, True), (_WITHOUT_APP_PACKAGES, False), (_DENYING_APP_PACKAGES, False)],
    ids=["allow-entry", "no-entry", "deny-entry"])
def test_only_an_allow_entry_for_all_application_packages_lets_containers_read(sddl, allowed):
    assert app_packages_may_read(sddl) is allowed


def test_a_difference_reaches_the_warnings_summary_that_a_quiet_run_still_prints():
    lost = HostFacts(**{**_DESKTOP.__dict__, "cmdlets_confined": False})
    with pytest.warns(UserWarning, match="host difference: the PowerShell in the container"):
        _report(lost)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _report(_DESKTOP)


@pytest.mark.skipif(os.name != "nt", reason="needs Windows: the container is an AppContainer")
def test_a_confined_powershell_answers_a_dotnet_call_and_each_difference_of_the_host_is_named(
        implement_box):
    facts = _measure(implement_box)
    assert facts.dotnet_answered, "the confined launch did not run a .NET call: nothing else holds"
    _report(facts)


class _FakeBox:
    """A box whose one answer is chosen by the test: what a confined PowerShell printed."""

    def __init__(self, result) -> None:
        self._result = result

    def run_script(self, script: str, **_ignored):
        self.script = script
        return self._result


@pytest.mark.skipif(os.name != "nt", reason="needs Windows: the container is an AppContainer")
@pytest.mark.parametrize("output, exit_code, problem", [
    ("started", 0, ""),
    ("Access is denied", 1, "Access is denied"),
    ("", 1, "the shell printed nothing and exited 1"),
    ("started extra", 0, "started extra"),
], ids=["starts", "refused-with-words", "silent", "not-exactly-started"])
def test_a_shell_start_problem_is_empty_only_when_the_child_shell_ran_and_said_started(
        output, exit_code, problem):
    from tests.os_boundary_box import StepResult, shell_start_problem

    box = _FakeBox(StepResult(True, exit_code, output))
    assert shell_start_problem(box) == problem
    assert "Diagnostics.Process]::Start" in box.script


@pytest.mark.skipif(os.name != "nt", reason="needs Windows: the container is an AppContainer")
def test_a_container_that_could_not_be_launched_at_all_is_a_shell_start_problem_with_its_words():
    from tests.os_boundary_box import StepResult, shell_start_problem

    box = _FakeBox(StepResult(False, None, "CreateProcessW failed: access denied"))
    assert shell_start_problem(box) == "CreateProcessW failed: access denied"


@pytest.mark.skipif(os.name != "nt", reason="needs Windows: the container is an AppContainer")
def test_a_missing_child_shell_skips_the_test_that_needs_it_and_names_the_fact():
    from tests.os_boundary_box import StepResult, require_child_shell

    box = _FakeBox(StepResult(True, 1, "Access is denied"))
    with pytest.warns(UserWarning, match="cannot start a PowerShell of its own"):
        with pytest.raises(pytest.skip.Exception, match="Access is denied"):
            require_child_shell(box)


@pytest.mark.skipif(os.name != "nt", reason="needs Windows: the container is an AppContainer")
def test_a_container_that_can_start_a_child_shell_lets_the_test_that_needs_it_run(implement_box):
    from tests.os_boundary_box import require_child_shell, shell_start_problem

    assert shell_start_problem(implement_box) == ""
    require_child_shell(implement_box)


def _report(facts: HostFacts) -> None:
    """One warning per difference: a quiet run still prints its warnings summary."""
    for difference in differences(facts):
        warnings.warn(f"OS-boundary host difference: {difference}", stacklevel=2)


def _measure(box) -> HostFacts:
    cmdlet = powershell_line("Write-Output 'cmdlet-ran'")
    import_probe = powershell_line(
        "try { Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop; "
        "[Console]::Out.Write('imported') } catch { [Console]::Out.Write($_.Exception.Message) }")
    modules = ac.SYSTEM32 / "WindowsPowerShell" / "v1.0" / "Modules"
    modules = modules / "Microsoft.PowerShell.Utility"
    started = time.monotonic()
    dotnet = box.run_line(powershell_line("[Console]::Out.Write('dotnet-ran')"))
    elapsed = time.monotonic() - started
    resolved = "cmdlet-ran" in box.run_line(cmdlet).output
    return HostFacts(
        dotnet_answered=dotnet.output == "dotnet-ran", cmdlets_confined=resolved,
        cmdlets_unconfined="cmdlet-ran" in box.run_line(cmdlet, confined=False).output,
        import_error="" if resolved else box.run_line(import_probe).output.strip()[:300],
        start_seconds=elapsed,
        modules_readable_by_containers=app_packages_may_read(ac.acl_text(modules)),
        powershell_readable_by_containers=app_packages_may_read(ac.acl_text(ac.POWERSHELL)))
