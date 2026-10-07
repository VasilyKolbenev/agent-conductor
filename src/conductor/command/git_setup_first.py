"""The confirmed first commit and its recovery: one driver for the first write and every retry.

A confirmation first prepares what the owner cannot see (objects and the marked index bytes, no
lock, outside the store transaction), then, inside it, publishes the records and walks the decision
table one action at a time: read the ref, the lock and the index, perform ONE effect, read again.
The order of effects is fixed (review ruling OD-4): the install bytes, then the verified op record,
then the copy in `.git`, then the lock; the ref moves once, by compare-and-swap from absent, under
the product's own lock; the index is installed by moving that proven lock without replacing.

A retry of the same terms by the same actor walks the same table from whatever the repository
shows, so no path can skip a check another path makes. Whether an index is the product's is never
judged by its tree: an equivalent index of the owner is left exactly as it is (OD-3).

The performers `_do_<action>` are looked up by name on every turn: they are the seams the tests
patch to make a crash happen between two named effects.
"""
from __future__ import annotations

import os
import stat
import sys

from . import git_setup_first_lock as lock
from . import git_setup_first_records as records
from .accept_plumbing import ref_oid
from .adapters.harness_workspace import root_turn
from .containment import portal_violation
from .git_setup_facts import author_now, call, first_facts, plain_git_dir
from .git_setup_first_index import binding_of
from .git_setup_first_prepare import prepare
from .git_setup_first_resume import (
    Act, Index, LOCKED, Lock, REF_MOVED, Ref, Refuse, next_action)
from .git_setup_records import SetupRefused
from .git_setup_snapshot import preview
from .project_git import GitReadFailed

MAX_TURNS = 12
REFLOG = "conduct: first commit"
TITLES = {"empty": "Начало проекта (Conduct)",
          "snapshot": "Первый коммит: {count} файлов (Conduct)"}
#: The facts a confirmation freezes. One projection for the first write and for a resume (the
#: preview's `head` is not among them: `first_facts` refuses a repository with a commit).
_FROZEN = ("target_ref", "object_format", "author", "signing")
#: Object names per `cat-file --batch-check` call: one line is at most 64 hex digits and a newline,
#: so a call stays under the 128 KiB the runner is given for standard input.
_PER_BATCH = 128 * 1024 // 65
_ODD = "odd"


def _frozen(row: dict) -> tuple:
    """The frozen facts of a shown preview, of `frozen_facts`, or of a stored op."""
    return tuple(row[name] for name in _FROZEN)


def message(mode: str, count: int) -> bytes:
    """The fixed commit message of 9.8; the trailer is the only machine-readable part."""
    title = TITLES[mode].format(count=count)
    return f"{title}\n\nConduct-Setup: first-commit\n".encode("utf-8")


def confirm(api, request) -> tuple[int, dict]:
    """Complete the first commit for these terms: 201 with the receipt, 200 for an exact repeat.

    Raises:
        SetupRefused: A closed reason: the terms changed, the folder is not what was shown, or the
            repository holds a ref, an index or a lock that is not this operation's.
    """
    root = api._store.project_root
    with root_turn(root, wait=0):
        row = records.read_receipt(root)
        if row is not None:
            return _repeat(row, request)
        op = records.read_op(root)
        if op is not None:
            if _stored_terms_hold(api, op, request):
                return _resume(api, op)
            _supersede(api, op)
        prepared = _prepare(api, request)               # outside the store transaction (OD-10)
        with api._store.transaction():
            return 201, {"setup": _write(api, request, prepared)}


def _repeat(row: dict, request) -> tuple[int, dict]:
    """The receipt answers an exact repeat; any other actor or terms refuse."""
    if (row["mode"], row["paths_digest"], row["requested_by"]) != (
            request.mode, request.digest, request.actor):
        raise SetupRefused("setup_terms_changed")
    return 200, {"setup": row}


def _stored_terms_hold(api, op, request) -> bool:
    """May this request continue the stored op, judged now?

    The body, the actor and the CURRENT author must be the stored ones; another one inherits
    nothing (OD-8, OD-9)."""
    root, git = api._store.project_root, api._project_git
    return (op.mode, op.paths_digest, op.requested_by, op.author) == (
        request.mode, request.digest, request.actor, author_now(root, git))


def _supersede(api, op) -> None:
    """Changed terms never replace a stored op yet: they refuse and nothing is undone."""
    raise SetupRefused("setup_terms_changed")


def _prepare(api, request) -> tuple[dict, object, bytes]:
    """Phase A: the preview again, its digest against the body's, then the objects and bytes."""
    root, git = api._store.project_root, api._project_git
    shown = preview(root, git, request.mode)
    if request.mode == "snapshot" and shown["paths_digest"] != request.digest:
        raise SetupRefused("paths_changed")             # an old (version 1) digest lands here
    if shown["signing"]:
        raise SetupRefused("signing_required")
    plain_git_dir(root, git)                            # objects go into `.git`: check it first
    text = message(request.mode, len(shown["files"]))
    return shown, prepare(root, git, shown, text, request.mode, request.digest), text


def _write(api, request, prepared) -> dict:
    """The entry check of the write (OD-10), the records, then the driver."""
    shown, made, text = prepared
    root, git = api._store.project_root, api._project_git
    if _frozen(first_facts(root, git)) != _frozen(shown):
        raise SetupRefused("paths_changed")
    plain_git_dir(root, git)                            # the route may have changed since A1
    _objects_present(root, git, shown, made)
    op = records.new_op(request.mode, request.digest, request.actor, shown, made,
                        api._clock(), text)
    return drive(api, records.start(root, op, made.install))


def _resume(api, op) -> tuple[int, dict]:
    """Walk the table for an op that `_stored_terms_hold` has just cleared."""
    with api._store.transaction():
        return 201, {"setup": drive(api, op)}


def _objects_present(root, git, shown: dict, made) -> None:
    """The tree, the commit and every blob the rows name must be in the object store now."""
    wanted = {made.tree: "tree"}
    if made.commit is not None:
        wanted[made.commit] = "commit"
    wanted.update({row["git_oid"]: "blob" for row in shown["files"]})
    names = list(wanted)
    for start in range(0, len(names), _PER_BATCH):
        batch = names[start:start + _PER_BATCH]
        raw = call(root, git, "cat-file", "--batch-check",
                   stdin="".join(f"{name}\n" for name in batch).encode("ascii"))
        found = [line.split(" ") for line in raw.decode("ascii").splitlines()]
        if [(row[0], row[1]) for row in found if len(row) == 3] != [
                (name, wanted[name]) for name in batch]:
            raise SetupRefused("paths_changed")


def drive(api, op) -> dict:
    """Walk the decision table until the receipt stands or a refusal is raised.

    Returns:
        The receipt of the finished operation.

    Raises:
        SetupRefused: A closed reason from the table; `setup_damaged` when it does not end.
        GitReadFailed: Git failed, timed out, or answered something this driver cannot judge.
    """
    module = sys.modules[__name__]
    for _ in range(MAX_TURNS):
        step = next_action(op.stage, *read_facts(api, op))
        if isinstance(step, Refuse):
            _refuse(api, op, step)
        done = getattr(module, f"_do_{step.value}")(api, op)
        if step is Act.FINISH:
            return done
        op = done
    raise SetupRefused("setup_damaged")


def read_facts(api, op) -> tuple[Ref, Lock, Index]:
    """The three facts the table reads: the ref, the lock and the index, each read afresh."""
    root, git = api._store.project_root, api._project_git
    folder = plain_git_dir(root, git)
    return (ref_state(root, git, op), lock.lock_state(folder, binding_of(op)),
            index_state(root, git, op.expected_tree, folder))


def ref_state(root, git, op) -> Ref:
    """The target ref against this operation's commit: absent, at it, or somebody else's."""
    found = ref_oid(root, git, op.target_ref.removeprefix("refs/heads/"))
    if found is None:
        return Ref.ABSENT
    return Ref.AT_COMMIT if found == op.commit else Ref.OTHER


def index_state(root, git, tree: str, folder) -> Index:
    """Whether the owner's index is equivalent to `tree`, and nothing about whose file it is.

    The existence and the type of the file are judged first and apart: an absent index also
    compares equal to the empty tree, so `diff-index` alone would read "nothing there" as
    "installed". Only exit 0 of one `diff-index --cached --quiet` over a plain file that did not
    change under the read is `MATCHES` (review ruling OD-3); exit 1 is another tree. An error, a
    timeout, a cut answer and a file that changed under the read are refusals, never success.

    Raises:
        GitReadFailed: `git_timed_out`, or `git_failed` for every answer that cannot be judged.
    """
    path = folder / "index"
    before = _look(path)
    if before is None:
        return Index.ABSENT
    if before == _ODD:
        return Index.OTHER
    answer = git(["--no-optional-locks", "-C", str(root), "diff-index", "--cached", "--quiet",
                  tree], True)
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if answer.truncated or _look(path) != before:
        raise GitReadFailed("git_failed")
    if answer.exit_code in (0, 1):
        return Index.MATCHES if answer.exit_code == 0 else Index.OTHER
    raise GitReadFailed("git_failed")


def _look(path):
    """None for no such name, the stamp of a plain regular file, `_ODD` for anything else."""
    try:
        found = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        return _ODD
    if portal_violation(path, found) is not None or not stat.S_ISREG(found.st_mode):
        return _ODD
    return found.st_dev, found.st_ino, found.st_size, found.st_mtime_ns


def _refuse(api, op, step: Refuse) -> None:
    """Undo only what a refusal names and the stored bytes prove, then raise its reason.

    A refusal retires neither the op nor its install bytes: a later repeat lays the copy again
    from them. When the bytes cannot be read nothing is removed and the refusal is
    `setup_damaged` (`read_install` raises it).
    """
    root, git = api._store.project_root, api._project_git
    if step.release_own_lock or step.drop_copy:
        data = records.read_install(root, op)
        folder = plain_git_dir(root, git)
        if step.release_own_lock:
            lock.release_own_lock(folder, binding_of(op))
        if step.drop_copy:
            lock.drop_copy(folder, op.nonce, data)
    raise SetupRefused(step.reason)


def _do_take_lock(api, op):
    root, git = api._store.project_root, api._project_git
    try:
        lock.take_lock(plain_git_dir(root, git), op.nonce, records.read_install(root, op))
    except lock.NameTaken:
        pass                                  # the next read names who holds it
    except lock.MoveRefused:
        raise GitReadFailed("git_failed") from None       # nothing was moved
    return op


def _do_mark_locked(api, op):
    return records.advance(api._store.project_root, op, LOCKED)


def _do_move_ref(api, op):
    root, git = api._store.project_root, api._project_git
    answer = git(["-C", str(root), "update-ref", "-m", REFLOG, op.target_ref, op.commit,
                  "0" * len(op.commit)], True)
    if answer.exit_code != 0 and ref_state(root, git, op) is Ref.ABSENT:
        raise GitReadFailed("git_timed_out" if answer.timed_out else "git_failed")
    return op                                 # judged by the ref on the next turn, never by this


def _do_mark_ref_moved(api, op):
    return records.advance(api._store.project_root, op, REF_MOVED)


def _do_install_index(api, op):
    root, git = api._store.project_root, api._project_git
    try:
        lock.install_index(plain_git_dir(root, git), binding_of(op), records.read_install(root, op))
    except lock.NameTaken:
        pass                                  # an index appeared: the next read judges it
    except lock.MoveRefused:
        raise GitReadFailed("git_failed") from None
    return op


def _do_release_lock(api, op):
    root, git = api._store.project_root, api._project_git
    lock.release_own_lock(plain_git_dir(root, git), binding_of(op))
    return op


def _do_finish(api, op) -> dict:
    """The receipt, then the own copy, then the op record, and only after it its install bytes."""
    root, git = api._store.project_root, api._project_git
    row = records.write_receipt(root, records.receipt_of(op, api._clock()))
    lock.drop_copy(plain_git_dir(root, git), op.nonce, records.read_install(root, op))
    records.retire(root, op)
    return row
