"""What a persistent login directory may hold, and what is taken back after a spawn.

The API-key road keeps its retention promise by DELETING: a config directory is
minted for one spawn and destroyed when it returns, so whatever the vendor wrote
under it -- prompt, session, tool output, model text -- has a lifetime of one
attempt and nothing here has to read a byte of it to say so.

A subscription cannot be kept that way. The credential the vendor's own login
command wrote has to survive, and be REWRITTEN in place when it is refreshed, so
the directory outlives every attempt by construction. The promise there has to
be made differently, and this module is where it is made: the names a spawn may
leave behind are declared per provider and MEASURED at the pinned version, the
per-run ones are taken back after every spawn, and a name outside both lists is
reported rather than deleted or ignored.

Nothing here opens a file. The whole judgement is names and kinds, so a
credential is never read in order to protect it, and a file this build does not
recognise is not inspected to find out what it is.

MEASURED at the pinned versions, with a fresh directory and one real spawn:

- Claude Code 2.1.239 writes ``.claude.json`` and a ``backups`` directory beside
  it, and -- even under ``--no-session-persistence`` -- a ``sessions`` directory
  holding one JSON file per process, carrying that process's own working
  directory, and a ``.last-cleanup`` stamp. The first two are the profile the
  login lives beside; the last two are per-run and are taken back.
- Codex CLI 0.112.0 unpacks a ``skills`` tree on its first real ``exec`` and
  writes a ``tmp`` directory holding one lock and two batch files per spawn. The
  skills tree is a cache the vendor rebuilds if it is removed, so it is expected
  and left alone; ``tmp`` is per-run and is taken back.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


def entries(home: str) -> frozenset[str]:
    """The TOP-LEVEL names standing in a login directory, read by name alone.

    An unreadable or absent directory answers with nothing rather than raising:
    this is a measurement taken around a spawn that has already happened, and a
    failure to take it must not replace what the spawn did. A directory that is
    not there is refused earlier, by the login preflight, which is the seam whose
    job is to say a login is missing.
    """
    if not _pinned(home):
        return frozenset()
    try:
        with os.scandir(home) as rows:
            return frozenset(row.name for row in rows)
    except OSError:  # noqa: BLE001 -- a measurement, never a road
        return frozenset()


def _pinned(home: str) -> bool:
    """Whether this is a directory an operator really pinned.

    An empty or relative value is not one, and both roads out of it are worse
    than doing nothing: an empty path resolves to the process's own working
    directory, and a relative one to whatever the child was standing in. The
    config door already refuses both, so this is closure rather than a check --
    the one place that DELETES may not depend on a door somewhere else.
    """
    return bool(home) and Path(home).is_absolute()


def unexpected(
        before: frozenset[str], after: frozenset[str],
        declared: tuple[str, ...]) -> tuple[str, ...]:
    """Names this spawn left behind that no declaration accounts for.

    Only what APPEARED is judged. Whatever the operator's own login put there
    before this build ever ran is theirs, and a product that refused over it
    would be refusing over the credential it was pointed at.
    """
    return tuple(sorted(after - before - frozenset(declared)))


def take_back(home: str, scratch: tuple[str, ...]) -> None:
    """Remove the per-run names this provider declares, and follow nothing.

    A portal standing where a scratch name is expected is removed BY ITS OWN
    ENTRY and never walked through: deleting through a junction would reach
    whatever it points at, which is exactly the road every other delete in this
    build refuses. Anything that cannot be removed is left standing; the caller
    already reports what appeared, and a cleanup that raised here would replace
    the outcome of the spawn it followed.
    """
    from ..containment import portal_violation
    from .harness_workspace import _leaf, _remove_portal, _remove_tree

    if not _pinned(home):
        return
    for name in scratch:
        target = Path(home) / name
        try:
            found = _leaf(target)
            if found is None:
                continue
            if portal_violation(target, found) is not None:
                _remove_portal(target, found)
            elif stat.S_ISDIR(found.st_mode):
                _remove_tree(target)
            else:
                target.unlink()
        except OSError:  # noqa: BLE001 -- a cleanup, never a road
            continue
