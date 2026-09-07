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

The RESIDUE half of this module opens no file. That judgement is names and
kinds, so a file this build does not recognise is not inspected to find out what
it is, and the credential is not read in order to decide whether it moved.

``credential_values`` is the one road that does read, and it reads for the
opposite reason: to protect the credential rather than to judge it. The leak
scan was built from the values of allowlisted environment names, because that is
where every credential this build ever handed a child came from. A vendor's own
login does not arrive that way -- it lives in a file -- so a child that echoed it
back would be publishing a secret the scan had never heard of. That was the
coverage gap the owner recorded on 2026-09-07 and what the login contract's D8
asks for.

What the reading road promises: it opens ONE declared name, bounded, and keeps
what it finds only as bytes to compare a child's output against. Nothing read
here is decoded into a message, returned to a caller, written to a receipt, put
in an exception or kept after the spawn it guarded. A file that is absent,
oversized, unreadable or not the shape expected contributes nothing at all,
because a login that cannot be read is a leak scan that cannot be widened, not a
reason to refuse a run the login preflight already admitted.

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

import json
import os
import stat
from pathlib import Path


def entries(home: str) -> frozenset[str] | None:
    """The TOP-LEVEL names standing in a login directory, read by name alone.

    Three answers, not two. A directory that is THERE answers with its names; an
    ABSENT one answers with the empty set, which is what a login preflight
    refuses over one seam earlier; and one this build could not read answers
    None. "I could not establish what is there" is not "nothing is there", and
    a build that flattened them would report a promise as kept because it had
    been unable to check it.

    It never raises. This is a measurement taken around a spawn that has already
    happened, and a failure to take it must not replace what the spawn did.
    """
    if not _pinned(home):
        return frozenset()
    try:
        with os.scandir(home) as rows:
            return frozenset(row.name for row in rows)
    except FileNotFoundError:
        return frozenset()
    except OSError:  # noqa: BLE001 -- unreadable is its own answer
        return None


#: The most a credential file may be read as. A login file is small -- a token,
#: an expiry, an account id -- and a bound is what stops a name in that
#: directory being read as a file at all.
CREDENTIAL_LIMIT = 64 * 1024


def credential_values(home: str, names: tuple[str, ...]) -> tuple[bytes, ...]:
    """Every string a provider's declared login file holds, as bytes to scan for.

    Read from the DECLARED names only, never by looking for what a directory
    happens to contain: a build that scanned every file it found would be
    reading an operator's unrelated documents to protect them.

    Values shorter than a plausible secret are dropped. A leak scan matches by
    substring, and a two-character value out of a JSON document would flag every
    output that happened to contain those characters, which would turn the whole
    scan into noise nobody could act on.
    """
    found: list[bytes] = []
    for name in names:
        for value in _strings(_read_json(Path(home) / name)):
            if len(value) >= 12:
                found.append(value.encode("utf-8"))
    return tuple(dict.fromkeys(found))


def _read_json(target: Path) -> object:
    """One bounded read of one named file; anything unreadable answers None."""
    if not _pinned(str(target.parent)):
        return None
    try:
        if target.is_symlink() or target.stat().st_size > CREDENTIAL_LIMIT:
            return None
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a widening, never a road
        return None


def _strings(value: object) -> list[str]:
    """Every string inside a JSON value, in no particular order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [row for item in value.values() for row in _strings(item)]
    if isinstance(value, list):
        return [row for item in value for row in _strings(item)]
    return []


def _pinned(home: str) -> bool:
    """Whether this is a directory an operator really pinned.

    An empty or relative value is not one, and both roads out of it are worse
    than doing nothing: an empty path resolves to the process's own working
    directory, and a relative one to whatever the child was standing in. The
    config door already refuses both, so this is closure rather than a check --
    the one place that DELETES may not depend on a door somewhere else.

    "Absolute" is asked of the SAME helper the config door and the pin ask, so a
    path admitted there cannot be silently un-measured and un-cleaned here: a
    POSIX pin read on Windows is absolute to both of them or to neither.
    """
    from .harness_profile import is_absolute

    return bool(home) and is_absolute(home)


def appeared(
        before: frozenset[str] | None,
        after: frozenset[str] | None) -> frozenset[str] | None:
    """What this spawn added to a login directory, or None if that is unknown.

    Either measurement missing makes the answer unknown rather than empty: a
    build that could not read the directory has nothing to say about what
    changed in it, and saying "nothing" would be saying the opposite.
    """
    if before is None or after is None:
        return None
    return after - before


def unexpected(
        added: frozenset[str] | None, declared: tuple[str, ...]) -> tuple[str, ...]:
    """Names this spawn left behind that no declaration accounts for.

    Only what APPEARED is judged. Whatever the operator's own login put there
    before this build ever ran is theirs, and a product that refused over it
    would be refusing over the credential it was pointed at.
    """
    return tuple(sorted((added or frozenset()) - frozenset(declared)))


def take_back(home: str, scratch: tuple[str, ...],
              added: frozenset[str] | None) -> None:
    """Remove the per-run names THIS SPAWN added, and follow nothing.

    Bounded to what appeared, and that bound is the whole safety of it. A login
    directory may be one a person also uses themselves: their own transcripts
    can be standing under a name this build calls per-run, and deleting those
    would be destroying an operator's work to keep a promise about this build's
    own leavings. What this spawn did not create, this build does not remove --
    and an unknown measurement removes nothing at all.

    A portal standing where a scratch name is expected is removed BY ITS OWN
    ENTRY and never walked through: deleting through a junction would reach
    whatever it points at, which is exactly the road every other delete in this
    build refuses.

    It cannot raise. It runs in the ``finally`` of an attempt, where an escaping
    exception would skip the attempt home's own discard and replace the outcome
    of a spawn that already happened -- and the workspace door it borrows
    refuses an unreadable name with a RuntimeError, not an OSError.
    """
    from ..containment import portal_violation
    from .harness_workspace import _leaf, _remove_portal, _remove_tree

    if not _pinned(home) or not added:
        return
    for name in sorted(added.intersection(scratch)):
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
        except Exception:  # noqa: BLE001 -- a cleanup may not become the outcome
            continue
