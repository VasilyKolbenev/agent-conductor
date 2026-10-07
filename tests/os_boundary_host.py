"""The facts about a host that decide whether an OS-boundary check measures the OS.

Test support, pure: it holds the facts a measuring test collects and the words for each way a
host departs from the desktop the checks were written on, and it starts nothing. The first CI
run of the Windows checks showed why this exists: on a server edition under an administrator
account the container's PowerShell could not resolve its own utility cmdlets, and the run said
only "not recognized".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: A confined PowerShell that needs longer than this to answer one .NET call is slow enough for
#: a timeout written on a desktop to expire before the child has run a line.
SLOW_START_SECONDS = 5.0
_APP_PACKAGES_ALLOW = re.compile(r"\(A;[^)]*;;;AC\)")


def app_packages_may_read(sddl: str) -> bool:
    """True when the ACL text carries an allow entry for ALL APPLICATION PACKAGES."""
    return _APP_PACKAGES_ALLOW.search(sddl) is not None


@dataclass(frozen=True)
class HostFacts:
    """What one host did when the same small launches were made on it."""

    dotnet_answered: bool
    cmdlets_confined: bool
    cmdlets_unconfined: bool
    import_error: str
    start_seconds: float
    cmdlet_seconds: float
    modules_readable_by_containers: bool
    powershell_readable_by_containers: bool


def differences(facts: HostFacts) -> list[str]:
    """Each way the host departs from the desktop, in words a CI log can carry."""
    found: list[str] = []
    if not facts.cmdlets_confined:
        control = ("the unconfined one can" if facts.cmdlets_unconfined
                   else "the unconfined one cannot either")
        found.append(
            f"the PowerShell in the container cannot resolve its utility cmdlets ({control}); "
            f"Import-Module said: {facts.import_error or 'nothing'}")
    if facts.start_seconds > SLOW_START_SECONDS:
        found.append(
            f"a confined PowerShell took {facts.start_seconds:.1f} s to answer one .NET call "
            f"(more than {SLOW_START_SECONDS:.0f} s)")
    if facts.cmdlet_seconds > SLOW_START_SECONDS:
        found.append(
            f"one cmdlet lookup in the container took {facts.cmdlet_seconds:.1f} s "
            "(a command the session does not know starts the module search)")
    if not facts.modules_readable_by_containers:
        found.append("ALL APPLICATION PACKAGES has no allow entry on PowerShell's module "
                     "directory, so a container may not read its modules")
    if not facts.powershell_readable_by_containers:
        found.append("ALL APPLICATION PACKAGES has no allow entry on powershell.exe, so a "
                     "container may not start a shell of its own")
    return found
