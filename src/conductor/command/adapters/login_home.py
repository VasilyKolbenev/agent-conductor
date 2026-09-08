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

Two roads DO read, and both read for a reason the residue half does not have.
``config_grants`` reads a vendor's own configuration file to find out whether it
gives the isolation away, because refusing that file by NAME would refuse the
directory the vendor's own login command produced. ``credential_values`` reads
the credential itself for the opposite reason again: to protect it rather than
to judge it. The leak
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
    found: set[str] = set()
    try:
        with os.scandir(home) as rows:
            for row in rows:
                found.add(row.name)
                if len(found) > MEASURE_LIMIT:
                    # Bounded HERE too, and for the same reason as the walk: a
                    # directory this build cannot finish reading is one it
                    # cannot vouch for.
                    return None
    except FileNotFoundError:
        return frozenset()
    except OSError:  # noqa: BLE001 -- unreadable is its own answer
        return None
    return frozenset(found)


#: The most a credential file may be read as. A login file is small -- a token,
#: an expiry, an account id -- and a bound is what stops a name in that
#: directory being read as a file at all.
CREDENTIAL_LIMIT = 64 * 1024


def config_grants(home: str, name: str, keys: tuple[str, ...]) -> tuple[str, ...]:
    """Which configuration KEYS a named file in a login directory declares.

    Read rather than merely named, because the name alone is the wrong question.
    A vendor writes its own configuration file beside its own login, and a build
    that refused the NAME would refuse the directory its own login command had
    just produced -- permanently, with a sentence blaming the operator for a file
    the vendor wrote.

    What is refused is the CONTENT that gives something away: the trust map that
    re-admits a work tree's own configuration, and a provider override. Anything
    else in that file is the operator's business.

    A file this build cannot read or parse answers with every key it was asked
    about: a configuration whose contents cannot be established is not one this
    build can say is harmless.
    """
    import tomllib

    target = Path(home) / name
    if not _pinned(home) or _is_portal(target):
        return keys
    try:
        if target.stat().st_size > CREDENTIAL_LIMIT:
            return keys
        held = tomllib.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except Exception:  # noqa: BLE001 -- unreadable is refused, never admitted
        return keys
    return tuple(key for key in keys if _declares(held, key))


def _declares(held: object, key: str) -> bool:
    """Whether a parsed configuration names this key at ANY depth.

    The top level is not where a format that nests keeps its authority. This
    vendor's own documentation puts a provider override inside a profile table,
    so a rule that read only the top level would call
    `profile = "x"` with `[profiles.x] model_provider = ...` harmless -- and it
    is the same authority, one line lower.
    """
    if isinstance(held, dict):
        return key in held or any(_declares(row, key) for row in held.values())
    if isinstance(held, list):
        return any(_declares(row, key) for row in held)
    return False


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


#: The most names a login directory may be measured as holding. A directory
#: this build cannot finish reading is one it cannot vouch for, which is the
#: same answer it gives for a directory it cannot read at all.
MEASURE_LIMIT = 5000


def measure(home: str, scratch: tuple[str, ...]) -> frozenset[str] | None:
    """What stands in a login directory: its top-level names AND, inside each
    declared per-run directory, the paths beneath it.

    Top-level names alone were not enough, and the gap was not theoretical: a
    `sessions` directory that already existed hid every file a spawn wrote into
    it, so an attempt could leave its own session state -- carrying the work
    directory it ran in -- behind a name that had not changed. What is compared
    has to be as fine as what a spawn can add.

    Only the DECLARED per-run directories are walked. The rest of the directory
    is the operator's, and reading it name by name is neither this build's
    business nor bounded by anything it controls.
    """
    top = entries(home)
    if top is None:
        return None
    found = set(top)
    for name in scratch:
        if name not in top:
            continue
        target = Path(home) / name
        if _is_portal(target):
            # A portal standing where a per-run directory belongs is not a
            # directory this build can account for. Walking it would measure --
            # and then remove -- whatever it points at, and NOT walking it would
            # leave a spawn writing through it unseen. So the measurement is
            # unknown, which is the answer that refuses the run.
            return None
        for row in _walk(target, name):
            if row is None or len(found) > MEASURE_LIMIT:
                return None
            found.add(row)
    return frozenset(found)


def _is_portal(target: Path) -> bool:
    """Whether this name is a door to somewhere else rather than a directory."""
    from ..containment import portal_violation
    from .harness_workspace import _leaf

    try:
        found = _leaf(target)
    except Exception:  # noqa: BLE001 -- unreadable is treated as a door
        return True
    return found is not None and portal_violation(target, found) is not None


def _walk(target: Path, prefix: str) -> "list[str | None]":
    """Every path beneath one declared directory, as `name/rest`, or [None].

    It descends nothing this build would refuse to delete. A junction is not a
    symlink to `pathlib` -- `is_symlink()` answers False for one -- so a walk
    that asked only that question would descend a reparse point, and the caller
    would then remove files inside whatever it points at, which is precisely the
    road `containment.portal_violation` exists to close. Every step is judged by
    that same function, and a portal is reported as a name without being opened.

    Bounded as it goes, not after: a directory this build cannot finish reading
    is one it cannot vouch for, and materialising the listing first would make
    the bound a description of a walk that had already happened.
    """
    rows: list[str | None] = []
    stack = [(target, prefix)]
    while stack:
        here, said = stack.pop()
        try:
            if not here.is_dir():
                # A declared per-run NAME can be an ordinary file, and a file
                # has no paths beneath it. Its own name was already measured.
                continue
            children = _children(here, MEASURE_LIMIT - len(rows))
        except OSError:  # noqa: BLE001 -- unreadable is its own answer
            return [None]
        if children is None:
            return [None]
        for row in children:
            name = f"{said}/{row.name}"
            rows.append(name)
            deeper = _descend(row)
            if deeper is None:
                return [None]
            if deeper:
                stack.append((row, name))
    return rows


def _descend(row: Path) -> "bool | None":
    """Whether the walk should go into this name; None if it must not judge it.

    A door one level down is still a door. Not walking it would leave whatever
    a spawn wrote THROUGH it unmeasured, and this build would then report a
    retention promise it had not checked; walking it would measure -- and later
    remove -- somebody else's files. So it answers None, and unknown refuses.
    """
    from ..containment import portal_violation
    from .harness_workspace import _leaf

    try:
        found = _leaf(row)
    except Exception:  # noqa: BLE001 -- unreadable is its own answer
        return None
    if found is None:
        return False
    if portal_violation(row, found) is not None:
        return None
    return bool(stat.S_ISDIR(found.st_mode))


def _children(here: Path, room: int) -> "list[Path] | None":
    """This directory's entries, consuming AT MOST ``room`` of them.

    The bound is on the reading, not on the answer. An earlier version sorted
    the whole listing first and checked the count afterwards, which is a
    description of an unbounded read rather than a limit on one: a directory
    with a million entries was fully enumerated before anything said stop.

    Sorted only after the bound, so the order a caller sees is still stable.
    """
    if room <= 0:
        return None
    found: list[Path] = []
    with os.scandir(here) as rows:
        for row in rows:
            found.append(Path(row.path))
            if len(found) > room:
                return None
    return sorted(found)


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
    kept = frozenset(declared)
    return tuple(sorted(
        row for row in (added or frozenset())
        if row not in kept and row.split("/", 1)[0] not in kept))


def take_back(home: str, scratch: tuple[str, ...],
              added: frozenset[str] | None) -> tuple[str, ...]:
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
    build refuses. What this does NOT close is a name that changes KIND between
    the measurement and the removal -- a directory that becomes a portal in
    between. `containment` states that component swaps are out of scope for this
    build's route judgements, and this inherits that boundary rather than
    claiming to have closed it.

    It cannot raise. It runs in the ``finally`` of an attempt, where an escaping
    exception would skip the attempt home's own discard and replace the outcome
    of a spawn that already happened -- and the workspace door it borrows
    refuses an unreadable name with a RuntimeError, not an OSError.

    What it could not remove is RETURNED rather than swallowed. A cleanup that
    failed silently is a promise reported as kept because nothing checked it,
    and the caller has to be able to say so.
    """
    if not _pinned(home) or not added:
        return ()
    wanted = [name for name in sorted(added)
              if name.split("/", 1)[0] in scratch]
    return tuple(name for name in wanted if _take_one(Path(home) / name))


def _take_one(target: Path) -> bool:
    """Remove one name, following nothing; True if it is still standing after."""
    from ..containment import portal_violation
    from .harness_workspace import _leaf, _remove_portal, _remove_tree

    try:
        found = _leaf(target)
        if found is None:
            return False
        if portal_violation(target, found) is not None:
            _remove_portal(target, found)
        elif stat.S_ISDIR(found.st_mode):
            _remove_tree(target)
        else:
            target.unlink()
    except Exception:  # noqa: BLE001 -- a cleanup may not become the outcome
        return True
    return _leaf_stands(target)


def _leaf_stands(target: Path) -> bool:
    """Whether something is still there after this build tried to remove it."""
    try:
        return target.is_symlink() or target.exists()
    except OSError:  # noqa: BLE001 -- unreadable is still standing
        return True
