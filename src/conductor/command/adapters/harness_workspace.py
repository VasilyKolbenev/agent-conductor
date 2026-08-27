"""The durability and evidence door every headless harness passes, in one module.

A harness adapter needs a handful of filesystem facts and nothing else: a FRESH
profile home per spawn, a marker that survives a crash so a task is never run
twice, the instruction TEXT the task is actually asked to do, content digests of
the authorized work tree so verification can read what actually changed instead
of believing what the task said, and -- for a vendor that is TOLD to write an
artefact into the home it was given -- what became of that one name. They live
here, apart from the
adapter's value logic, for the same reason the owned-process runner lives apart
from the adapters that use it: a door should be one small module a reviewer can
read whole.

The door is PROVIDER-NEUTRAL and holds no provider identity at all: it compares
no id, imports no adapter, and branches on nothing about who is calling. What
differs between harnesses is two NAMES -- the home a vendor's tool keeps its
profile in and the marker namespace an attempt is claimed in -- and both are
handed in by the calling adapter, so each provider's names live in that
provider's own module. That is why the containment guarantees below are stated
about "this workspace's home root" rather than about one spelled directory: the
bound is exactly one fixed root per workspace, and which root that is is decided
where the provider is, not here.

This is a durability door, NOT an execution door. It imports no subprocess, no
socket and no import machinery, and the package-wide door guard checks that here
exactly as it checks every other module -- the exemption this module carries is
only from the adapters' value-core import allowlist, never from the execution
ban.

EVERY name this door writes through is proved CONTAINED first, with the same
typed relation `conductor.command.containment` already holds for the preview's
run route and for the owned runner's cwd: `os.lstat` alone, following nothing,
classifying a symbolic link, an NTFS junction and any other reparse point by its
own tag, and refusing a store-owned file that is not regular or that carries a
second hard link. The root itself is a component of that route, because a portal
standing AT a container adopts external state exactly as one standing inside it
does. Without that walk a portal planted at this workspace's home, its marker
namespace, `instructions` or `work` made this door create durable state outside
the project root it is bound to -- which is what it did before this walk existed.

The evidence walk is the same relation read rather than written. It never
follows a name: a portal is recorded by its typed kind, a file whose bytes also
answer to another name is recorded as `hard_link`, and neither is ever read for
content. Evidence cannot be forged by pointing a name inside the tree at bytes
outside it.

Cleanup is the same relation again, and it is the one place where getting it
wrong is worse than the leak it fixes. Every delete is bounded to ONE fixed
root -- `<project>/<home_dir>`, the single home name this workspace was built
with -- and to a container this workspace itself minted. A portal met inside
such a container is removed by its OWN entry, so whatever it named keeps every
byte. The home ROOT is the same case once a child
replaces the directory this process minted: the entry is one this workspace
created and still remembers, so it too goes by its own entry and never through
it. A portal standing at a home name this workspace never minted is refused and
named, never touched, because this door cannot say whose it is. A name whose
kind cannot be established at all refuses rather than being guessed at.

Two properties stay mechanical rather than advisory. A home is created with
``exist_ok=False``, so reusing one is an error rather than a silent overwrite.
And the containment walk reads and then acts, so a writer that swaps a component
between the check and the write is not stopped: within one project this door is
single-writer by contract, and against a concurrent adversary the boundary is
best-effort, exactly as the preview's route gate states of itself.
"""
from __future__ import annotations

import hashlib
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, RLock
from weakref import WeakValueDictionary

from ..containment import (
    RouteViolation,
    RouteViolationCode,
    first_directory_violation,
    portal_violation,
    render_route_violation,
)

#: The subtrees this door owns beneath the project root that belong to the RUN
#: rather than to any one harness. The work tree is the authorized subtree a
#: task may change and verification reads; the instruction directory is where
#: the task's own text is read from. Both are facts about the run, so every
#: provider driving that run reads and writes the SAME two, and neither is a
#: name a provider may choose.
WORK_DIR = "work"
INSTRUCTION_DIR = "instructions"
#: The two names a PROVIDER brings instead: see ``HarnessWorkspace``. They are
#: not defaulted anywhere, because a default would let two harnesses share one
#: home root by saying nothing, and the whole retention promise below is that a
#: home belongs to exactly one attempt of exactly one provider.
_RESERVED_DIRS = frozenset({WORK_DIR, INSTRUCTION_DIR})
#: The one name shape an instruction is read from, and the bound on its size: a
#: task is a task, not a payload, and an unbounded read is an unbounded prompt.
INSTRUCTION_SUFFIX = ".md"
INSTRUCTION_LIMIT = 64 * 1024
#: Windows marks a reparse DIRECTORY here; removing its own entry needs rmdir.
_DIRECTORY_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_DIRECTORY", 0x10)
#: What ONE name inside an attempt home turned out to be. A CLOSED vocabulary,
#: and the door's own rather than any provider's: it answers what STANDS there,
#: never what it means. A provider that asked its vendor to write an artefact at
#: that name reads its own conclusion off these four words.
#:
#: `empty` is told apart from `file` because for at least one vendor those are
#: two different reports rather than a degree of the same one -- Codex CLI writes
#: its last-message file EMPTY when a run produced no final agent message -- and
#: a door that collapsed them would force every caller to reopen the question by
#: reading the file, which is the one thing this door exists to avoid.
#:
#: `other` covers a portal, a directory, a device, and a file whose bytes also
#: answer to another name. None of them is read, followed, or guessed at: the
#: contents of an attempt home are written by a child this build does not trust.
HOME_LEAF_ABSENT = "absent"
HOME_LEAF_EMPTY = "empty"
HOME_LEAF_FILE = "file"
HOME_LEAF_OTHER = "other"
HOME_LEAF_KINDS = (
    HOME_LEAF_ABSENT, HOME_LEAF_EMPTY, HOME_LEAF_FILE, HOME_LEAF_OTHER)


class WorkspaceNotContained(RuntimeError):
    """A name this door must write or read through is not locally contained."""


def _refuse(violation: RouteViolation) -> WorkspaceNotContained:
    return WorkspaceNotContained(render_route_violation(violation))


#: Every mark a route component may never carry, decided ONCE for every system
#: this build runs on rather than read from the one it happens to be running on.
#:
#: `os.sep` and `os.altsep` are values of the CURRENT platform, and reading them
#: meant POSIX accepted `a\b` -- a name that is a two-part ROUTE the moment the
#: same configuration is read on Windows. A name may not mean one thing here and
#: another there: an operator's `providers.json` travels, and so does a run.
#:
#: `:` stays for the drive-letter and stream forms Windows reads it as, on every
#: platform for the same reason.
_COMPONENT_MARKS = frozenset({"/", "\\", ":"})
#: The highest code point this door refuses outright. NUL alone used to be
#: checked, so a name carrying a backspace, an escape or a newline passed --
#: reaching a filesystem, a receipt and a log, where a control character is not
#: something a reader can see, compare or type back. Windows refused several of
#: them at the filesystem instead, which made the hole invisible there and left
#: it open on POSIX.
_LAST_CONTROL = 0x1F


def _component(name: object) -> str:
    """Prove one route part names a child, never a route of its own.

    Held by CONSTRUCTION rather than by this platform's separators, and not by
    `Path(name).name` either: that is the same platform semantics wearing a
    different hat, and it answers `a\\b` differently on the two systems for the
    very reason this function exists.
    """
    if type(name) is not str or not name or name in (".", ".."):
        raise WorkspaceNotContained(f"{name!r} is not a single route component")
    if any(mark in name for mark in _COMPONENT_MARKS):
        raise WorkspaceNotContained(f"{name!r} is not a single route component")
    if any(ord(character) <= _LAST_CONTROL for character in name):
        raise WorkspaceNotContained(f"{name!r} is not a single route component")
    return name


def _leaf(path: Path) -> os.stat_result | None:
    """Read one name without following it; absence is None, unreadable refuses.

    Absence and unreadability are deliberately told apart here, unlike in the
    shared ``lstat_or_none``: this door decides whether to CREATE at the name, so
    "nothing is there" and "I could not establish what is there" cannot share an
    answer.
    """
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _refuse(
            RouteViolation(RouteViolationCode.UNREADABLE, path)) from error


def _remove_portal(path: Path, found: os.stat_result) -> None:
    """Remove a portal's OWN entry, never anything it names."""
    directory = bool(
        stat.S_ISDIR(found.st_mode)
        or getattr(found, "st_file_attributes", 0) & _DIRECTORY_ATTRIBUTE)
    if directory:
        path.rmdir()
    else:
        path.unlink()


def _remove_tree(root: Path) -> None:
    """Delete everything beneath ``root`` and then ``root``, following nothing."""
    directories: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        directories.append(current)
        for path in sorted(current.iterdir()):
            found = _leaf(path)
            if found is None:
                continue
            if portal_violation(path, found) is not None:
                _remove_portal(path, found)
            elif stat.S_ISDIR(found.st_mode):
                stack.append(path)
            else:
                path.unlink()
    for path in reversed(directories):
        path.rmdir()


class _RootGate:
    """One weakly indexed, workspace-owned process-local harness root gate."""

    __slots__ = ("lock", "__weakref__")

    def __init__(self) -> None:
        self.lock = RLock()


# Process-local only, and keyed by the RESOLVED root, so two workspaces reached
# by different names for one tree take the same gate and a second tree takes its
# own. The weak table releases a root nothing holds. This is the same shape the
# run store's root gate and the runtime's operation lock already use; it is
# deliberately NOT either of them -- a dispatch must not hold a store
# transaction across a child process.
#
# The key was briefly the root TOGETHER WITH the two names a provider owns,
# reasoning that two providers own different homes and markers and so have no
# state to contend over. That reasoning was WRONG and the change was a race:
# they also share `work` and `instructions`, and the evidence snapshot spans the
# WHOLE work tree. A neighbour writing its own work item during another
# provider's dispatch lands in that provider's before/after diff, where it reads
# as a change outside the authorized subtree -- a mismatch pinned on a child
# that did nothing wrong. Reproduced, before the revert, as:
#     wrote_while_one_owned_root=True
#     foreign_change=['b/foreign.txt']
#
# The prose above this gate had claimed for a long time that one harness's root
# must not stop "another provider". That claim was aspirational and the CODE was
# right; the correction was to fix the sentence, not the key. A comment is not a
# specification, and a guarantee is not safe to invert because a comment nearby
# describes a nicer world.
#
# Serializing providers on one root is the cost, and it is the honest one: they
# are writing into one tree and reading evidence from all of it.
_ROOT_GATES_GUARD = Lock()
_ROOT_GATES: WeakValueDictionary[Path, _RootGate] = WeakValueDictionary()


def _root_gate(key: Path) -> _RootGate:
    with _ROOT_GATES_GUARD:
        gate = _ROOT_GATES.get(key)
        if gate is None:
            gate = _RootGate()
            _ROOT_GATES[key] = gate
        return gate


@dataclass(frozen=True)
class HarnessWorkspace:
    """Every filesystem effect a harness is allowed, bound to one project root.

    Bound to two NAMES as well, and they are required rather than defaulted.
    ``home_dir`` is the single root every cleanup below is bounded to, and
    ``marker_dir`` is the namespace an attempt is claimed in; a provider hands
    both in, so no harness inherits another's. Both are proved to be single
    route components here, at construction, rather than at each use -- a
    workspace that exists at all has already been proved to own two local names.
    """

    root: Path
    home_dir: str
    marker_dir: str
    #: The home names THIS workspace minted and has not yet discarded. It is the
    #: only ground on which cleanup may remove a name whose kind is a portal:
    #: this process created that entry, so removing the entry alone destroys
    #: nothing it did not make. A name absent from here is somebody else's.
    minted: set[str] = field(default_factory=set, compare=False, repr=False)

    def __post_init__(self) -> None:
        home = _component(self.home_dir)
        marker = _component(self.marker_dir)
        if home == marker:
            raise WorkspaceNotContained(
                "a harness's home and marker names must differ, or discarding a "
                "home would delete the markers that prove what already ran")
        for name in (home, marker):
            if name in _RESERVED_DIRS:
                # The work tree and the instruction directory belong to the RUN.
                # A home pointed at either one turns `discard_home` -- a bounded,
                # deliberate, recursive delete -- into the destruction of the
                # task's own evidence or of the text it was asked to do.
                raise WorkspaceNotContained(
                    f"{name!r} is a run-owned subtree and cannot be a harness's "
                    "home or marker name")

    @classmethod
    def at(cls, root: str | os.PathLike[str], *, home_dir: str,
           marker_dir: str) -> "HarnessWorkspace":
        return cls(
            root=Path(root).resolve(), home_dir=home_dir, marker_dir=marker_dir)

    def _gate_key(self) -> Path:
        """What this workspace serializes over: the ROOT, and nothing narrower.

        Not the provider's own names. Two providers under one root share `work`
        and `instructions`, and the evidence snapshot spans the whole work tree,
        so a narrower key lets a neighbour's ordinary dispatch appear in another
        provider's evidence as a change outside its authorized subtree. The
        comment above ``_root_gate`` records the reproduction.
        """
        return self.root

    @contextmanager
    def owned(self):
        """Hold this ROOT for one whole dispatch: sweep, homes, task and cleanup.

        The cycle below is not a set of independent doors, it is one owner's
        turn over one tree. A sweep decides what to delete by reading the home
        root; a preflight and a task each mint a home under it and must take it
        back; and what a cleanup failed to remove is exactly what the next
        sweep must refuse over. Interleave two dispatches on one root and each
        of those readings is about the other's state: a sweep meets a home a
        live dispatch is still using, and a dispatch's own record of a broken
        cleanup is reset under it by a neighbour that has nothing to do with it.

        So the gate is the whole dispatch, keyed by the resolved root. Two
        adapters reached through different names for one tree serialize, because
        the key is what the path resolved to and not what it was spelled. Two
        different roots do not meet at all. Two PROVIDERS sharing one root DO
        meet, and must: they write into one `work` tree and read evidence from
        all of it, so a turn that let them overlap would put one provider's
        ordinary work into the other's evidence.

        Holding the gate is necessary and it is not sufficient on its own. The
        gate spans one dispatch, and a verification that re-read the tree AFTER
        the dispatch released it would read a tree a neighbour may have changed
        in between -- the runtime's own lock is keyed per ACTION, so two
        providers really do run at once. That is why the transport takes BOTH
        evidence snapshots inside this turn and verification judges the pair it
        was handed. What is judged is what was read here.

        The gate is bound to a NAME here, and that binding is load-bearing: the
        table indexes gates weakly, so holding only the lock lets the gate itself
        be collected, the next caller mint a second one for the same root, and
        both run at once. A holder must keep the gate alive for as long as it
        holds its turn.
        """
        gate = _root_gate(self._gate_key())
        with gate.lock:
            yield

    # -- the one containment relation every road below goes through -------------

    def _directory_route(self, *parts: str) -> Path:
        """Prove the whole route, root included, is a local directory route."""
        walked, route = self.root, [self.root]
        for part in parts:
            walked = walked / _component(part)
            route.append(walked)
        violation = first_directory_violation(route)
        if violation is not None:
            raise _refuse(violation)
        return walked

    def _file_route(self, *parts: str) -> tuple[Path, os.stat_result | None]:
        """Prove the route to a FILE: local directories, a local, singly named leaf."""
        parent = self._directory_route(*parts[:-1])
        path = parent / _component(parts[-1])
        found = _leaf(path)
        if found is None:
            return path, None
        violation = portal_violation(path, found)
        if violation is None and not stat.S_ISREG(found.st_mode):
            violation = RouteViolation(RouteViolationCode.IRREGULAR_FILE, path)
        elif violation is None and found.st_nlink != 1:
            violation = RouteViolation(
                RouteViolationCode.HARD_LINK, path, link_count=found.st_nlink)
        if violation is not None:
            raise _refuse(violation)
        return path, found

    # -- the isolated, single-use profile home --------------------------------

    def homes_root(self) -> Path:
        """The ONE root every home cleanup below is bounded to."""
        return self.root / self.home_dir

    def mint_home(self, name: str) -> Path:
        """A fresh home. ``exist_ok=False`` makes reuse a hard error, not a merge."""
        home = self._directory_route(self.home_dir, name)
        home.mkdir(parents=True, exist_ok=False)
        self.minted.add(home.name)
        return home

    def discard_home(self, home: str | os.PathLike[str]) -> None:
        """Delete ONE attempt home, bounded to the fixed homes root, or refuse.

        The owner is this workspace and the root is ``<project>/<home_dir>``:
        a path that does not stand directly beneath it is refused without a
        single entry being read, so this cleanup cannot reach outside its own
        root even when it is handed a path that does.

        A child may REPLACE the directory this process minted with a portal, and
        the home root is then exactly the case the contained-route walk was built
        to refuse. For a name this workspace minted the refusal is the wrong
        answer: the entry is ours, so it is removed by its OWN entry -- the same
        idiom already used for a portal met INSIDE a home -- and whatever it
        named keeps every byte. For any other name the refusal stands.
        """
        path = Path(home)
        if path.parent != self.homes_root():
            raise WorkspaceNotContained(
                f"{str(path)!r} is not a home beneath this workspace's fixed root")
        target = self._directory_route(self.home_dir) / _component(path.name)
        found = _leaf(target)
        if found is None:
            self.minted.discard(target.name)
            return
        if portal_violation(target, found) is not None or not stat.S_ISDIR(
                found.st_mode):
            self._discard_replaced_home(target, found)
            return
        _remove_tree(target)
        self.minted.discard(target.name)

    def _discard_replaced_home(self, target: Path, found: os.stat_result) -> None:
        """Remove a minted home's own entry once its kind is no longer a directory."""
        if target.name not in self.minted:
            raise _refuse(RouteViolation(RouteViolationCode.NOT_DIRECTORY, target))
        _remove_portal(target, found)
        self.minted.discard(target.name)

    def home_leaf_kind(self, home: str | os.PathLike[str], name: str) -> str:
        """What stands at ONE name inside ONE attempt home, as a closed word.

        A vendor may be TOLD to write an artefact into the home it was handed --
        Codex CLI's ``--output-last-message`` is the first -- and the caller then
        has one question about it: what became of the name it named. That
        question is a filesystem fact, so it is answered here rather than in a
        provider's value module, where it would be a second place this package
        touches a disk.

        NOTHING IS READ. The answer comes from ``lstat`` and the same typed
        containment relation every other road here uses: the whole route is
        proved local first, the leaf is classified without being followed, and a
        portal, a directory or a second hard link is reported as ``other``
        rather than opened. So a caller can learn that an artefact arrived
        without a byte of it entering this process -- which is the difference
        between an observation this build may repeat in a receipt and model text
        it promised not to keep.

        Bounded to a home beneath this workspace's own fixed root, like every
        other home road, and refusing rather than guessing when the route or the
        name cannot be established. A caller that must not raise catches that
        refusal and reports its own word for "I could not establish this"; the
        refusal carries a path, so it is a value to catch and never to forward.
        """
        path = Path(home)
        if path.parent != self.homes_root():
            raise WorkspaceNotContained(
                f"{str(path)!r} is not a home beneath this workspace's fixed root")
        target = self._directory_route(
            self.home_dir, path.name) / _component(name)
        found = _leaf(target)
        if found is None:
            return HOME_LEAF_ABSENT
        if portal_violation(target, found) is not None:
            return HOME_LEAF_OTHER
        if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
            return HOME_LEAF_OTHER
        return HOME_LEAF_EMPTY if found.st_size == 0 else HOME_LEAF_FILE

    def sweep_homes(self) -> tuple[str, ...]:
        """Discard every home a crashed attempt left, naming what it refused.

        A portal or a non-directory standing where a home would stand was never
        minted here, so it is named and left exactly as found; the names returned
        are the whole account of what this sweep declined to touch.
        """
        homes = self._directory_route(self.home_dir)
        found = _leaf(homes)
        if found is None:
            return ()
        if not stat.S_ISDIR(found.st_mode):
            raise _refuse(RouteViolation(RouteViolationCode.NOT_DIRECTORY, homes))
        refused: list[str] = []
        for path in sorted(homes.iterdir()):
            entry = _leaf(path)
            if entry is None:
                continue
            if (portal_violation(path, entry) is not None
                    or not stat.S_ISDIR(entry.st_mode)):
                refused.append(path.name)
                continue
            _remove_tree(path)
            self.minted.discard(path.name)
        return tuple(refused)

    # -- the crash-proof marker -----------------------------------------------

    def _marker_parts(self, run_id: str, action_id: str) -> tuple[str, str, str]:
        """The ONE spelling of a marker's route, so no two readers can disagree.

        This existed three times before, and one of the three was a path built
        straight from the fields with no containment walk behind it. Two
        spellings of one route is the same defect as judging one value and
        writing another: whichever is wrong, nothing tells you which. The route
        is computed here and every reader below is handed it.

        A marker's identity is ``(run_id, action_id)`` and not the action alone.
        An action id is unique WITHIN a run and nothing makes it unique across
        runs -- a runtime mints ``action-1`` for the first action of every run it
        serves -- so a flat namespace made the second run to use an id a replay
        of the first. Observed: two runs, one adapter, and run B came back
        `unknown` about work it had never done.

        The run is a DIRECTORY rather than part of the file name, so a run's
        markers can be read, counted and reasoned about as a set, and so a run id
        that happens to contain a dot cannot collide with the ``.marker`` suffix.
        """
        return (self.marker_dir, run_id, f"{action_id}.marker")

    def _legacy_marker_parts(self, action_id: str) -> tuple[str, str]:
        """Where a marker written before the run joined the identity still lies.

        Read, never written. A flat marker names an action whose run this door
        cannot recover, so it cannot be attributed and it cannot be dismissed --
        and of the two, dismissing is the one that repeats an action that may
        already have run. It is therefore read as a claim by whichever run asks,
        which is conservative in exactly the direction that costs nothing but a
        refusal an operator can clear.
        """
        return (self.marker_dir, f"{action_id}.marker")

    def marker_path(self, run_id: str, action_id: str) -> Path:
        """The marker's NAME, and it is a NAME: nothing is established until read.

        Deliberately still the unvalidated form, because that is what a name is.
        What changed is that it can no longer say a different name than the one
        ``claim`` writes and ``is_claimed`` reads -- all three take the same
        parts -- so a caller that trusts this path is trusting the route the door
        will actually walk.
        """
        return self.root.joinpath(*self._marker_parts(run_id, action_id))

    def is_claimed(self, run_id: str, action_id: str) -> bool:
        """True once a marker exists, which outlives the process that wrote it.

        Two names are read, and the second one is the migration: this run's own
        marker, and a flat one left by a build that filed markers under the
        action alone. Either is a claim.
        """
        _path, found = self._file_route(*self._marker_parts(run_id, action_id))
        if found is not None:
            return True
        _legacy, stale = self._file_route(*self._legacy_marker_parts(action_id))
        return stale is not None

    def claim(self, run_id: str, action_id: str) -> None:
        """Claim the action BEFORE its task spawns, so a crash cannot un-claim it.

        Written under the run, always. Nothing writes the flat name any more, so
        the legacy namespace can only shrink.
        """
        marker, _found = self._file_route(*self._marker_parts(run_id, action_id))
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(action_id, encoding="utf-8", newline="\n")

    # -- the instruction the task is actually asked to do ----------------------

    def read_instruction(self, instruction_ref: str) -> str:
        """The instruction TEXT, read from ONE contained name, or refuse.

        A dispatch that cannot read the instruction is refused by the caller
        rather than sent a sentence built from the reference alone: a prompt that
        is not the task is worse than no prompt at all.
        """
        path, found = self._file_route(
            INSTRUCTION_DIR, f"{_component(instruction_ref)}{INSTRUCTION_SUFFIX}")
        if found is None:
            raise WorkspaceNotContained(f"no instruction stands at {str(path)!r}")
        if found.st_size > INSTRUCTION_LIMIT:
            raise WorkspaceNotContained(
                f"the instruction at {str(path)!r} is past the "
                f"{INSTRUCTION_LIMIT} byte bound this door reads")
        failed = False
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError):  # noqa: BLE001 -- keep no decoder graph
            failed = True
            text = ""
        if failed or not text.strip() or "\x00" in text:
            raise WorkspaceNotContained(
                f"the instruction at {str(path)!r} is not readable task text")
        return text

    # -- the authorized work tree and its evidence ----------------------------

    def work_root(self) -> Path:
        root = self._directory_route(WORK_DIR)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def work_dir(self, work_item_id: str) -> Path:
        self.work_root()
        work = self._directory_route(WORK_DIR, work_item_id)
        work.mkdir(parents=True, exist_ok=True)
        return work

    def digest_work_tree(self) -> dict[str, str]:
        """Content digests of every LOCAL regular file under the work tree.

        A portal and an aliased file are recorded by their typed kind and never
        by content: a change of kind is still a change, while bytes that lie
        elsewhere -- or that answer to a second name -- are never read as this
        task's evidence.
        """
        base = self._directory_route(WORK_DIR)
        rows: dict[str, str] = {}
        found = _leaf(base)
        if found is None or not stat.S_ISDIR(found.st_mode):
            return rows
        stack = [base]
        while stack:
            for path in sorted(stack.pop().iterdir()):
                relative = path.relative_to(base).as_posix()
                entry = _leaf(path)
                if entry is None:
                    continue
                violation = portal_violation(path, entry)
                if violation is not None:
                    rows[relative] = violation.code.value
                elif stat.S_ISDIR(entry.st_mode):
                    stack.append(path)
                elif not stat.S_ISREG(entry.st_mode):
                    rows[relative] = RouteViolationCode.IRREGULAR_FILE.value
                elif entry.st_nlink != 1:
                    rows[relative] = RouteViolationCode.HARD_LINK.value
                else:
                    rows[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return rows
