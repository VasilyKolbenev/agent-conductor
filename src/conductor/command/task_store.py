"""Durable storage for tasks: one directory per task, written once.

Project -> Task -> Run, and this is the middle. A task outlives any run of it
and is valid with no run at all, so it cannot live inside a run directory: it
gets its own root, ``conductor/tasks``, beside ``runs`` and ``templates``. The
shape follows the record's own rule. A task is an identity, so it is written
EXCLUSIVELY -- staged in a private directory, fsynced, renamed into place --
and never rewritten; two writers racing for one id cannot both believe they
created it, and a crash between the first byte and the rename publishes
nothing. `RunStore.create_run` is the model, line for line in spirit.

No run list is kept here. Which runs belong to a task is DERIVED, at
projection time, from the binding each run froze into its own configuration;
a list written here would be an index of somebody else's facts and could come
to disagree with them.

No new lock system either. The store takes the SAME process-local root gate
`RunStore` takes for the resolved project root, and bumps the same thread-local
depth, so a route that reads a task and then creates a run inside one
transaction holds one lock and `current_thread_holds_transaction` stays
truthful. Reads take the gate too -- `RunStore`'s choice rather than
`TemplateStore`'s, and not because a reader could see half a record: a task
directory appears atomically. The create door is read-then-write (look for the
standing record, then publish), and the read half must hold the gate the write
half holds or the pair is not one transaction. The gate is reentrant, so the
doors nest.

The route is judged on the way in and on the way out with `containment`'s own
walker and `TemplateStore`'s own leaf rule: a portal anywhere on it means the
name is here and the content is somewhere else. A refusal names the KIND and
never the path, for `TemplateStore._owned`'s reason.

The LISTING is the one door that does not refuse for such an entry. It names
it and reads nothing, so one task whose content lives elsewhere costs the
caller that task and not every sound task beside it -- the refusal still
happens, at `read`, where it is about the entry the caller asked for.
"""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..ownership import data_root, owned_write
from .path_admission import admit_directory, admit_name
from types import MappingProxyType
from typing import NoReturn

from .containment import (
    RouteViolation,
    RouteViolationCode,
    first_directory_violation,
    portal_violation,
    _optional_lstat,
)
from .contracts import ContractError
from .run_files import _canonical_bytes, _exclusive_bytes, _fsync_dir, _json_object
from .run_store import _ROOT_TRANSACTION_STATE, _root_gate, _transactional
from .store_errors import CorruptRun, StoreError
from .task_contracts import TaskRecord, _bounded_id
from .template_store import RouteNotOwned, _leaf_violation

#: The one file a task directory holds.
TASK_FILE = "task.json"

#: One fixed sentence per structural reason a route is not this store's to
#: use, none of them naming a path -- `template_store._ROUTE_REFUSAL`'s rule,
#: in this store's words.
_ROUTE_REFUSAL = MappingProxyType({
    RouteViolationCode.SYMLINK:
        "a component of the task store is a symbolic link",
    RouteViolationCode.JUNCTION:
        "a component of the task store is a directory junction",
    RouteViolationCode.REPARSE_POINT:
        "a component of the task store is a reparse point",
    RouteViolationCode.HARD_LINK:
        "a stored task record carries more than one name",
    RouteViolationCode.IRREGULAR_FILE:
        "a stored task record is not a regular file",
    RouteViolationCode.NOT_DIRECTORY:
        "a component of the task store is not a directory",
    RouteViolationCode.UNREADABLE:
        "a component of the task store cannot be read",
    RouteViolationCode.MISSING:
        "a component of the task store cannot be read",
})


class TaskExists(StoreError):
    """Exclusive task creation found an existing identity."""


class CorruptTask(StoreError):
    """A stored task record contradicts the contract or its own directory."""


class TaskStore:
    """Single-writer store rooted at one project's ``conductor/tasks``."""

    def __init__(self, project_root: str | os.PathLike[str]) -> None:
        self.project_root = Path(project_root).resolve()
        self.tasks_root = data_root(self.project_root) / "tasks"
        # The run store's gate for this root, held STRONGLY here for the same
        # reason `RunStore` holds it: the module table is weak.
        self._root_gate = _root_gate(self.project_root)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Serialize one process-local transaction for this resolved project root.

        The same gate and the same thread-local depth as `RunStore.transaction`,
        so `RunStore.current_thread_holds_transaction` reports this store's
        transaction too. Cross-process exclusion is out of scope exactly as it
        is there.
        """
        with self._root_gate.lock:
            depth = getattr(_ROOT_TRANSACTION_STATE, "depth", 0)
            _ROOT_TRANSACTION_STATE.depth = depth + 1
            try:
                yield
            finally:
                _ROOT_TRANSACTION_STATE.depth = depth

    def task_path(self, task_id: str) -> Path:
        """Where one task lives, with the name validated before any join.

        Through the contract's own id rule AND the task bound, so the set of
        names this store addresses is the set the record admits -- and a
        caller cannot reach a directory by naming one.
        """
        try:
            safe = _bounded_id("task_id", task_id)
        except ContractError as error:
            raise StoreError(str(error)) from error
        return self.tasks_root / safe

    @staticmethod
    def _refuse(violation: RouteViolation) -> NoReturn:
        raise RouteNotOwned(_ROUTE_REFUSAL[violation.code])

    def _owned(self, directory: Path) -> None:
        """Refuse a route that reaches bytes this store cannot account for.

        Every directory written THROUGH is walked with `containment`'s walker
        (absent is admissible: this store may own its creation), and the record
        written AT is judged by `TemplateStore`'s leaf rule -- regular, local,
        singly named -- because the two fail differently. See
        `TemplateStore._owned`.
        """
        violation = first_directory_violation((
            self.tasks_root.parent, self.tasks_root, directory,
        )) or _leaf_violation(directory / TASK_FILE)
        if violation is not None:
            self._refuse(violation)

    def admit_task_creation(self, task_id: str) -> None:
        self.task_path(task_id)  # retain the historical grammar first
        admit_directory(self.tasks_root, task_id, (TASK_FILE,), "task_id")

    @owned_write
    @_transactional
    def create_task(self, record: TaskRecord) -> Path:
        """Exclusively create one task; a second create under its id is `TaskExists`.

        Staged in a private directory beside the final name, fsynced, renamed
        into place. The rename arbitrates: a name already taken -- by a
        concurrent writer or a standing task -- is `TaskExists` whatever the
        other record says; the store never compares content. Whether two
        requests under one id AGREE is the create route's question, asked of
        `standing` under this same transaction before this door is reached.

        Raises:
            TaskExists: A task already stands under this id.
            RouteNotOwned: The route reaches state this store cannot account for.
            StoreError: A lookalike record, or the record could not be written.
        """
        if type(record) is not TaskRecord:
            raise StoreError("create_task takes exactly a TaskRecord")
        final = self.task_path(record.task_id)
        if final.is_dir():
            self._owned(final)
            raise TaskExists(f"task {record.task_id!r} already exists")
        self.admit_task_creation(record.task_id)
        admit_name(record.work_scope, "work_scope")
        self._owned(final)
        self.tasks_root.mkdir(parents=True, exist_ok=True)
        self._owned(final)
        if final.exists():
            raise TaskExists(f"task {record.task_id!r} already exists")
        payload = _canonical_bytes(record.as_dict())
        stage = Path(tempfile.mkdtemp(prefix=f".{record.task_id}.", dir=self.tasks_root))
        try:
            try:
                _exclusive_bytes(stage / TASK_FILE, payload)
                _fsync_dir(stage)
            except OSError as error:
                raise StoreError(
                    f"cannot write task {record.task_id!r}: {error}") from error
            self._publish(stage, final, record.task_id)
            _fsync_dir(self.tasks_root)
            return final
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    @staticmethod
    def _publish(stage: Path, final: Path, task_id: str) -> None:
        """Rename the staged directory into place; the name is the arbiter."""
        try:
            os.rename(stage, final)
        except FileExistsError as error:
            raise TaskExists(f"task {task_id!r} already exists") from error
        except OSError as error:
            if final.exists():
                raise TaskExists(f"task {task_id!r} already exists") from error
            raise StoreError(f"cannot publish task {task_id!r}: {error}") from error

    @_transactional
    def standing(self, task_id: str) -> TaskRecord | None:
        """The task under this id, or ``None`` when none stands.

        Absent is the one answer that is not a refusal here: the create route
        asks this to tell a retry from a first request. Everything else a
        directory that IS there can be wrong about is `read`'s refusal.
        """
        directory = self.task_path(task_id)
        self._owned(directory)
        if not directory.is_dir():
            return None
        return self._record(directory, task_id)

    @_transactional
    def read(self, task_id: str) -> TaskRecord:
        """One task, through the contract, without editing one durable byte.

        Raises:
            StoreError: No task stands under this id.
            CorruptTask: The record is unreadable, not an object, refused by
                the contract, or names a task other than its directory.
            RouteNotOwned: The route reaches state this store cannot account for.
        """
        record = self.standing(task_id)
        if record is None:
            raise StoreError(f"task {task_id!r} does not exist")
        return record

    @staticmethod
    def _record(directory: Path, task_id: str) -> TaskRecord:
        try:
            document = _json_object(directory / TASK_FILE, TASK_FILE)
        except CorruptRun as error:
            raise CorruptTask(f"task {task_id!r}: {error}") from error
        try:
            record = TaskRecord.from_dict(document)
        except ContractError as error:
            raise CorruptTask(
                f"task {task_id!r} violates the task contract: {error}") from error
        if record.task_id != task_id:
            raise CorruptTask(
                f"task directory {task_id!r} contains task {record.task_id!r}")
        return record

    @_transactional
    def tasks(self) -> tuple[str, ...]:
        """Every task this store holds a record for, ascending by id.

        Read off the directory rather than an index, for `TemplateStore.workflows`'
        reason: the files ARE the record. It judges no content -- a corrupt
        record is still a task by name, and `read` is where it is refused --
        and touches no durable byte.

        It refuses for the SHARED root alone: a ``conductor`` or a ``tasks``
        that is a portal or is not a directory means nothing here can be
        enumerated at all. One ENTRY it cannot account for is never a refusal
        over its neighbours; see `_listed`.
        """
        violation = first_directory_violation(
            (self.tasks_root.parent, self.tasks_root))
        if violation is not None:
            self._refuse(violation)
        try:
            entries = list(self.tasks_root.iterdir())
        except FileNotFoundError:
            return ()
        except OSError:
            self._refuse(RouteViolation(RouteViolationCode.UNREADABLE, self.tasks_root))
        return tuple(sorted(
            name for name in map(self._listed, entries) if name is not None))

    def _listed(self, entry: Path) -> str | None:
        """One directory entry as the task id it names, or ``None`` if it names none.

        Skipped: a staging leftover (its dot-name fails the grammar), a name
        that is not an id or is longer than a task id may be (no call on this
        store could address it), a plain file, a directory holding no record.

        NAMED, never refused and never read: an entry whose content lives
        somewhere else, or whose own state cannot be established. The listing
        answers what is THERE; `read` is what refuses it, and the route turns
        that refusal into one unreadable row beside its healthy neighbours.
        This function used to refuse instead, which cost a caller every sound
        task in the project for one broken entry -- the opposite of what a list
        is for, and of the contract the route states. Refusing for the SHARED
        root is a different fact and stays in `tasks`: there, nothing at all
        can be enumerated.

        Nothing here follows a link. The entry is judged by its OWN lstat, so a
        portal aimed at a plain file is named rather than quietly dropped for
        not looking like a directory, and a portal aimed at a directory is
        named without its far side ever being opened.
        """
        state, failure = _optional_lstat(entry)
        try:
            name = _bounded_id("task_id", entry.name)
        except ContractError:
            return None
        if failure is not None:
            return name
        if state is None:
            return None
        if portal_violation(entry, state) is not None:
            return name
        if not stat.S_ISDIR(state.st_mode):
            return None
        leaf, failure = _optional_lstat(entry / TASK_FILE)
        if failure is not None:
            return name
        return None if leaf is None else name
