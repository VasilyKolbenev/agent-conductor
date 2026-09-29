"""Seatbelt profile builder and command wrapper for the macOS OS-boundary checks.

Test support, not product code, and pure: it builds text and an argv and starts nothing,
so its shape is unit-tested on every POSIX host. The boundary on macOS needs no change
to the runner at all: ``sandbox-exec -p <profile> <command...>`` applies the profile and
then EXECS the command, so the child keeps the pid and the session the runner already
tracks, and the runner's process-group stop reaches it and everything it starts.

Seatbelt matches the RESOLVED path of what a process touches, and a later rule wins over
an earlier one. So the profile denies every write, allows the attempt's own directories,
then denies the protected paths after the allow that would cover them. A protected path
need not exist for its deny to hold (an absent name stays uncreatable), and a directory
that holds a protected entry is itself made unremovable so the whole subtree cannot be
moved away and recreated. Whether the OS enforces all of this is what the darwin tests
run natively on macOS to find out; nothing here claims it.
"""
from __future__ import annotations

import os
from collections.abc import Iterable, Sequence

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
#: Printed by the sandboxed shell before anything else. It can only appear if the profile
#: was applied and the command then started, which is the witness that policy was applied.
APPLIED = "APPLIED"
_UNQUOTABLE = ('"', "\\", "\n", "\r", "\x00")


class ProfileError(ValueError):
    """A path that cannot be written into a profile safely."""


class PolicyNotApplied(RuntimeError):
    """The sandbox wrapper did not apply the profile, so nothing may be trusted to hold."""


def _real(path) -> str:
    text = os.fspath(path)
    if not os.path.isabs(text):
        raise ProfileError(f"a profile names absolute paths only, not {text!r}")
    if any(char in text for char in _UNQUOTABLE):
        raise ProfileError(f"the path {text!r} cannot be quoted in a profile")
    resolved = os.path.realpath(text)
    if any(char in resolved for char in _UNQUOTABLE):
        raise ProfileError(f"the resolved path {resolved!r} cannot be quoted in a profile")
    return resolved


def _filters(kind: str, paths: Iterable[str]) -> str:
    return " ".join(f'({kind} "{path}")' for path in paths)


def seatbelt_profile(*, writable: Sequence, protected: Sequence = (),
                     unreadable: Sequence = (), deny_links: Sequence = ()) -> str:
    """The profile text: writes denied everywhere, allowed in ``writable``, denied again in
    ``protected``; each writable directory made unremovable; optional read and link denies."""
    roots = [_real(path) for path in writable]
    lines = ["(version 1)", "(allow default)", "(deny file-write*)",
             "(allow file-write* " + _filters("subpath", roots) + ' (literal "/dev/null"))']
    if protected:
        lines.append("(deny file-write* "
                     + _filters("subpath", (_real(path) for path in protected)) + ")")
    lines += [f'(deny file-write-unlink (literal "{root}"))' for root in roots]
    if unreadable:
        lines.append("(deny file-read* "
                     + _filters("subpath", (_real(path) for path in unreadable)) + ")")
    if deny_links:
        lines.append("(deny file-link "
                     + _filters("subpath", (_real(path) for path in deny_links)) + ")")
    return "\n".join(lines) + "\n"


def sandbox_argv(profile: str, command: Sequence[str]) -> list[str]:
    """The argv that applies ``profile`` and then execs ``command``."""
    return [SANDBOX_EXEC, "-p", profile, *command]


def require_applied(output: str) -> None:
    """Raise PolicyNotApplied unless the sandboxed shell reported the profile applied."""
    first = output.lstrip().splitlines()[0].strip() if output.strip() else ""
    if first != APPLIED:
        raise PolicyNotApplied(
            f"the sandbox wrapper did not report {APPLIED!r} first (saw {first[:60]!r})")
