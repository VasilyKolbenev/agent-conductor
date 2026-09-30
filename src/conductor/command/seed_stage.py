"""Stage a seed: write a base commit into a folder of its own, byte for byte (spec 9.1.2).

A task's work folder is seeded from a commit of the project. The bytes are prepared here first, in
`<root>/.conduct-seed/s-<8 hex>/`, outside `work/`, so no other dispatch of the project sees a
change outside its own subtree and the request does not wait for one (9.1.2 step 3). The move under
`work/` is a separate step under the root gate (9.1.4).

The bytes are the blobs' own, read by `cat-file --batch`: no attribute, no filter, no line-ending
setting, none of the substitutions `git archive` applies, because the acceptance that diffs the
task's folder against the base would otherwise see deletions that never happened. The plan (what is
copied, what is left out, what refuses) is `seed_plan`'s and is judged before a byte is written; a
folder is made only for a plan that passed, and is removed again if anything after it fails.

Every directory and file is made by this module, exclusively, never through a link: a name that
already exists is a fault and not an overwrite. The whole of it runs under `project_write_guard`.
This is not `adapters/work_seed.py`, where 9.1.2 names it: that module is imported by the workspace
door and this one needs `product_names`, which imports the workspace door (a cycle), and the
adapters package admits only value modules and its reviewed doors (`test_command_adapters`).

Git failures are refusals with the closed words of `seed_refused` (`git_failed`, `git_timed_out`);
an unusable tool is not one, and the reader's own exception for it passes through untouched.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .adapters.harness_workspace import root_turn
from .adapters.process import ProcessRunner
from .containment import first_directory_violation, lstat_or_none, portal_violation
from .product_names import SEED_STAGING_DIR
from .project_documents import read_head
from .project_git import GitAnswer, GitRead, GitReadFailed
from .seed_plan import (
    Batch, SeedPlan, SeedRefusal, blob_batches, is_lfs_pointer, parse_batch, parse_listing,
    plan_seed, shown)
from .seed_record import SeedRecord, SeedWarning
from .template_store import RouteNotOwned
from .work_layout import TASKS_DIR, WORK_DIR, work_parts

#: A base whose listing is longer than this is too large to seed, whatever its count of files.
LISTING_LIMIT = 4 * 1024 * 1024
#: How long a move waits for the root's turn before it leaves the seed staged (spec 9.1.4).
MOVE_WAIT_SECONDS = 2
_NAME = re.compile(r"s-[0-9a-f]{8}\Z")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_FORMATS = ("sha1", "sha256")
_EXECUTABLE = 0o100


@dataclass(frozen=True)
class BaseFacts:
    """The commit a seed is made from, its tree, the object format of the repository and the ref."""

    commit: str
    tree: str
    object_format: str
    ref: str


def staging_name(task_id: str, work_item_id: str) -> str:
    """`s-` and the first eight hex of the SHA-256 of `task/item`: one folder per pair.

    One name per pair is what lets the next seed of a task remove the preparations it abandoned
    by an exact name, without a marker file that would travel with the tree into the task.
    """
    digest = hashlib.sha256(f"{task_id}/{work_item_id}".encode("utf-8")).hexdigest()
    return "s-" + digest[:8]


def read_base(root: str | os.PathLike[str], git: GitRead) -> BaseFacts | None:
    """The commit HEAD names with its tree, object format and ref; None before the first commit.

    Raises:
        SeedRefusal: `git_failed` or `git_timed_out`.
        GitReadFailed: The tool is not usable (`tool_unavailable`); nothing is translated.
    """
    folder = Path(root)
    head = _translated(lambda: read_head(folder, git))
    if head is None:
        return None
    tree = _single(git(["-C", str(folder), "rev-parse", f"{head.commit}^{{tree}}"], True), _OID)
    form = _single(git(["-C", str(folder), "rev-parse", "--show-object-format"], True), None)
    if form not in _FORMATS:
        raise SeedRefusal("git_failed")
    return BaseFacts(head.commit, tree, form, head.ref)


def stage_from_git(root: str | os.PathLike[str], git: GitRead, *, task_id: str, work_scope: str,
                   work_item_id: str, base: BaseFacts, include_agent_instructions: bool,
                   staged_at: str, case_insensitive: bool | None = None) -> SeedRecord:
    """Write the base into the staging folder of this task and work item; return its record.

    The record is not written here (the caller makes it the point of commitment, 9.1.2 step 4).
    A leftover preparation of the same pair is removed first; a failure removes what it began.

    Raises:
        SeedRefusal: The plan refuses the base, or git failed or ran out of time.
        RouteNotOwned: The seed folder is not a plain folder of this project.
        OSError: A file could not be written; nothing of the staging is left.
    """
    folder = Path(root).resolve()
    name = staging_name(task_id, work_item_id)
    staging = folder / SEED_STAGING_DIR / name
    plan = plan_seed(
        _listing(folder, git, base.commit), include_agent_instructions=include_agent_instructions,
        budget_roots=(folder / WORK_DIR / TASKS_DIR / work_scope / work_item_id, staging),
        case_insensitive=sys.platform in ("win32", "darwin") if case_insensitive is None
        else case_insensitive)
    with ProcessRunner.project_write_guard(folder):
        _begin(folder, name)
        try:
            warnings = _fill(folder, git, plan, staging)
        except BaseException:
            _discard(folder, name)
            raise
    return SeedRecord(
        task_id=task_id, work_scope=work_scope, work_item_id=work_item_id, source="git",
        base_commit=base.commit, base_tree=base.tree, object_format=base.object_format,
        base_ref=base.ref, file_count=plan.file_count, total_bytes=plan.total_bytes,
        include_agent_instructions=include_agent_instructions, staging=name,
        skipped=plan.skipped, agent_instructions_skipped=plan.instructions_skipped,
        warnings=warnings, staged_at=staged_at)


def stage_empty(root: str | os.PathLike[str], *, task_id: str, work_scope: str,
                work_item_id: str, staged_at: str,
                include_agent_instructions: bool = False) -> SeedRecord:
    """An empty staging folder and the record of a seed that has no base (`source: empty`)."""
    folder = Path(root).resolve()
    name = staging_name(task_id, work_item_id)
    with ProcessRunner.project_write_guard(folder):
        _begin(folder, name)
    return SeedRecord(
        task_id=task_id, work_scope=work_scope, work_item_id=work_item_id, source="empty",
        base_commit=None, base_tree=None, object_format=None, base_ref=None, file_count=0,
        total_bytes=0, include_agent_instructions=include_agent_instructions, staging=name,
        skipped=(), agent_instructions_skipped=(), warnings=(), staged_at=staged_at)


def remove_staging(root: str | os.PathLike[str], name: str) -> None:
    """Remove one staging folder of the grammar `s-<8 hex>`, following nothing, if it is there.

    The seed folder goes with it when nothing else is in it. Removing what is not there is fine.

    Raises:
        ValueError: `name` is not a staging name.
        RouteNotOwned: The seed folder is not a plain folder of this project.
    """
    if _NAME.match(name) is None:
        raise ValueError("a staging folder is named s- and eight lower-case hex digits")
    folder = Path(root).resolve()
    with ProcessRunner.project_write_guard(folder):
        _discard(folder, name)


def hold_target_free(root: str | os.PathLike[str], work_scope: str, work_item_id: str) -> None:
    """Say `work_not_empty` when the task's folder already holds anything, changing nothing.

    Asked before a seed is staged, so a record is never written for a seed that cannot be moved
    (a task that worked in its folder before seeds existed).

    Raises:
        SeedRefusal: `work_not_empty`.
    """
    folder = Path(root).resolve()
    _hold_free(folder.joinpath(*work_parts(work_item_id, work_scope)), remove=False)


def move_staged(root: str | os.PathLike[str], record: SeedRecord, *,
                wait: float | None = None) -> None:
    """Move a staged seed into the task's folder with one rename, under the root's turn.

    The staging folder must stand as a plain folder; the target must be absent, or an empty folder
    (which is removed); the parents under `work/` are made as needed, each judged not to be a link
    or a file. The turn is the one a dispatch takes, so no proof sees the change as foreign; it is
    waited for `wait` seconds (`MOVE_WAIT_SECONDS` by default), after which the seed stays staged.
    The seed folder goes with the last staging.

    Raises:
        WorkspaceBusy: The turn did not come in time; nothing changed.
        SeedRefusal: `seed_lost` (no staging folder), `work_not_empty` (the target holds anything).
        RouteNotOwned: The route to the target reaches a file or a link where a folder belongs.
    """
    folder = Path(root).resolve()
    staging = folder / SEED_STAGING_DIR / record.staging
    target = folder.joinpath(*work_parts(record.work_item_id, record.work_scope))
    turn = root_turn(folder, wait=MOVE_WAIT_SECONDS if wait is None else wait)
    with turn, ProcessRunner.project_write_guard(folder):
        if not _plain_folder(staging):
            raise SeedRefusal("seed_lost")
        _make_parents(folder, target)
        _hold_free(target, remove=True)
        os.rename(staging, target)
        _drop_empty_seed_folder(folder)


def _plain_folder(path: Path) -> bool:
    found = lstat_or_none(path)
    return (found is not None and portal_violation(path, found) is None
            and stat.S_ISDIR(found.st_mode))


def _make_parents(folder: Path, target: Path) -> None:
    chain = [folder / WORK_DIR, folder / WORK_DIR / TASKS_DIR, target.parent]
    for number, directory in enumerate(chain, 1):
        try:
            os.mkdir(directory)
        except FileExistsError:
            pass
        if first_directory_violation((folder, *chain[:number])) is not None:
            raise RouteNotOwned("the work folder has a component this build cannot account for")


def _hold_free(target: Path, *, remove: bool) -> None:
    """The target is absent, or an empty folder (removed when `remove`); all else is refused."""
    found = lstat_or_none(target)
    if found is None:
        return
    if not _plain_folder(target) or any(True for _ in os.scandir(target)):
        raise SeedRefusal("work_not_empty")
    if remove:
        os.rmdir(target)


def _drop_empty_seed_folder(folder: Path) -> None:
    try:
        os.rmdir(folder / SEED_STAGING_DIR)
    except OSError:
        pass  # another pair's staging is in it


# -- reading git -----------------------------------------------------------------------------------


def _translated(call):
    """Run a read of `project_documents`, saying a failed or late git in the words of a refusal."""
    try:
        return call()
    except GitReadFailed as failed:
        if failed.code in ("git_failed", "git_timed_out"):
            raise SeedRefusal(failed.code) from None
        raise


def _ran(answer: GitAnswer) -> GitAnswer:
    if answer.timed_out or answer.exit_code is None:
        raise SeedRefusal("git_timed_out")
    if answer.exit_code != 0:
        raise SeedRefusal("git_failed")
    return answer


def _single(answer: GitAnswer, grammar: re.Pattern[str] | None) -> str:
    text = _ran(answer).output.decode("ascii", errors="replace").strip()
    if not text or (grammar is not None and grammar.match(text) is None):
        raise SeedRefusal("git_failed")
    return text


def _listing(folder: Path, git: GitRead, commit: str):
    answer = git(["-C", str(folder), "ls-tree", "-r", "-l", "-z", "--full-tree", commit], True,
                 output_limit=LISTING_LIMIT)
    if answer.truncated:
        raise SeedRefusal("seed_too_large")
    return parse_listing(_ran(answer).output)


def _read_batch(folder: Path, git: GitRead, batch: Batch) -> dict[str, bytes]:
    answer = git(["-C", str(folder), "cat-file", "--batch"], True, stdin=batch.stdin,
                 output_limit=batch.output_limit)
    if answer.truncated:
        raise SeedRefusal("git_failed")
    return parse_batch(_ran(answer).output, batch)


# -- writing the staging ---------------------------------------------------------------------


def _begin(folder: Path, name: str) -> None:
    """Make the seed folder if it is missing, remove this pair's leftover, make the staging."""
    seeds = folder / SEED_STAGING_DIR
    _plain_seed_folder(folder, seeds, make=True)
    _remove_entry(seeds / name)
    os.mkdir(seeds / name)


def _plain_seed_folder(folder: Path, seeds: Path, *, make: bool) -> None:
    if make:
        try:
            os.mkdir(seeds)
        except FileExistsError:
            pass
    if first_directory_violation((folder, seeds)) is not None:
        raise RouteNotOwned("the seed folder has a component this build cannot account for")


def _discard(folder: Path, name: str) -> None:
    seeds = folder / SEED_STAGING_DIR
    _plain_seed_folder(folder, seeds, make=False)
    _remove_entry(seeds / name)
    try:
        os.rmdir(seeds)
    except OSError:
        pass  # another pair's staging is in it, or it is not there


def _fill(folder: Path, git: GitRead, plan: SeedPlan, staging: Path) -> tuple[SeedWarning, ...]:
    """Read the bytes in batches and write every copied row; the warnings, in listing order."""
    sites: dict[str, list] = defaultdict(list)
    for row in plan.copy:
        sites[row.oid].append(row)
    made, pointers = {staging}, set()
    for batch in blob_batches(plan):
        objects = _read_batch(folder, git, batch)
        for wanted in batch.rows:
            for row in sites[wanted.oid]:
                _place(staging, made, row.path, objects[wanted.oid], int(row.mode, 8))
                if is_lfs_pointer(objects[wanted.oid]):
                    pointers.add(row.path)
    return tuple(SeedWarning(shown(row.path), "lfs_pointer") for row in plan.copy
                 if row.path in pointers)


def _place(staging: Path, made: set[Path], path: str, data: bytes, mode: int) -> None:
    parts = path.split("/")
    for count in range(1, len(parts)):
        directory = staging.joinpath(*parts[:count])
        if directory not in made:
            os.mkdir(directory)
            made.add(directory)
    _write_file(staging.joinpath(*parts), data, bool(mode & _EXECUTABLE))


def _write_file(path: Path, data: bytes, executable: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o755 if executable else 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    if os.name == "posix":
        os.chmod(path, 0o755 if executable else 0o644)


# -- removing what is ours -------------------------------------------------------------------


def _remove_entry(path: Path) -> None:
    """Delete `path` and everything beneath it by walking with lstat; a link is removed, never
    followed. A name that is not there is fine."""
    found = lstat_or_none(path)
    if found is None:
        return
    if portal_violation(path, found) is not None or not stat.S_ISDIR(found.st_mode):
        _unlink(path)
        return
    directories, pending = [], [path]
    while pending:
        current = pending.pop()
        directories.append(current)
        with os.scandir(current) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            child = current / name
            entry = os.lstat(child)
            if portal_violation(child, entry) is None and stat.S_ISDIR(entry.st_mode):
                pending.append(child)
            else:
                _unlink(child)
    for directory in reversed(directories):
        os.rmdir(directory)


def _unlink(path: Path) -> None:
    """Remove one name that is not a real folder: a file, a link, or a folder-shaped link."""
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)  # a Windows junction or directory link is a folder that unlink refuses
