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
import shlex
from collections.abc import Iterable, Sequence

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
#: Printed by the sandboxed shell only AFTER a write the profile must refuse was refused.
#: Starting the command proves nothing (a wrapper that execs it with no profile starts it
#: too); a refused write to the canary shows the shell is confined.
APPLIED = "APPLIED"
#: Printed instead, before the body runs, when that write WENT THROUGH: no profile confines
#: the shell, whatever the wrapper did or claimed.
UNCONFINED = "UNCONFINED"
_UNCONFINED_EXIT = 97
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
                     unreadable: Sequence = (), deny_links: Sequence = (),
                     removable: Sequence = ()) -> str:
    """The profile text: writes denied everywhere, allowed in ``writable``, denied again in
    ``protected``; each writable directory made unremovable unless it is named ``removable``
    (the control profile: without it nothing shows that this rule is what stops a rename of
    the directory that holds the protected entries); optional read and link denies."""
    roots = [_real(path) for path in writable]
    exempt = [_real(path) for path in removable]
    if any(path not in roots for path in exempt):
        raise ProfileError("a directory named removable but not writable: "
                           + ", ".join(path for path in exempt if path not in roots))
    lines = ["(version 1)", "(allow default)", "(deny file-write*)",
             "(allow file-write* " + _filters("subpath", roots) + ' (literal "/dev/null"))']
    if protected:
        lines.append("(deny file-write* "
                     + _filters("subpath", (_real(path) for path in protected)) + ")")
    lines += [f'(deny file-write-unlink (literal "{root}"))'
              for root in roots if root not in exempt]
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


def witnessed_script(canary, body: str) -> str:
    """The shell text a sandboxed launch runs: prove the profile confines it, then ``body``.

    The shell first tries to create ``canary``, a path in a directory no profile makes
    writable. If the write is refused it prints ``APPLIED`` and runs ``body``. If it works
    it prints ``UNCONFINED`` and exits before ``body``, so a launch without the policy runs
    none of the command's code. The witness observes one denied path: it shows the profile
    confined the shell, not that every rule in it holds (the darwin tests judge each rule
    by the tree). It is made in-band by this preamble, so it guards against a missing or
    misconfigured wrapper, not against a hostile child.
    """
    path = os.fspath(canary)
    if not os.path.isabs(path):
        raise ValueError(f"a witness names an absolute path only, not {path!r}")
    return (f"if ( printf x > {shlex.quote(path)} ) 2>/dev/null; "
            f"then echo {UNCONFINED}; exit {_UNCONFINED_EXIT}; fi; echo {APPLIED}; {body}")


def require_applied(output: str, canary=None) -> None:
    """Raise PolicyNotApplied unless the shell reported APPLIED first and left no canary.

    The first line is the shell's word (see ``witnessed_script``); the parent's own look at
    ``canary`` is the other half: a file there means a write the profile must refuse was made.
    """
    first = output.lstrip().splitlines()[0].strip() if output.strip() else ""
    if first != APPLIED:
        raise PolicyNotApplied(
            f"the sandboxed shell did not report {APPLIED!r} first (saw {first[:60]!r})")
    if canary is not None and os.path.lexists(canary):
        raise PolicyNotApplied(
            f"the canary {os.fspath(canary)!r} exists: a write the profile must refuse was made")
