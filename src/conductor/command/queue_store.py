"""The project's queue of runs, and the receipts of the runs it started (spec 4.4.3).

`data_root/queue/queue.json` is the queue: canonical JSON replaced atomically under the project
owner's write guard and the root gate every store of the root shares, at most 32 entries, one per
run, and a `revision` that grows with every write. An entry is the human's advance permission for
ONE thing: to start a run (`start`, the body of an authorize) or to resume a paused grant
(`resume`, the body of a control). When the pump withdraws that permission the entry keeps its
place and says why (`dropped`); a new confirmation fills the same entry again.

`queue/started/<run_id>/<kind>/<record_id>.json` is the receipt of a start, created before the
grant or the control it names is written. `kind` is the journal kind of that record, because the
identity of a journal record is local to a run and to its kind: two runs may both hold a
`grant-1`, and a grant and a control may share a name.

Neither file is a permission. The run's journal is the only source of the fact that a grant or a
control was accepted, and what these files say is judged against it by `queue_reading` and the
pump. This module knows shape, the route to the bytes, and how they are written; it reads no
journal, starts nothing and judges nothing about time.
"""
from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..ownership import data_root, owned_write
from .authorization_terms import (
    NodeLimit, closed_fields, human_identity, optional_id, positive_integer)
from .containment import first_directory_violation
from .contract_values import ContractError, _digest, _id, _timestamp
from .path_admission import admit_file, admit_name
from .policy_preview import PREVIEW_FIELDS
from .run_files import (
    _canonical_bytes, _exclusive_bytes, _fsync_dir, _json_object, _replace_bytes)
from .run_store import _ROOT_TRANSACTION_STATE, _root_gate
from .store_errors import CorruptRun, StoreError
from .template_store import RouteNotOwned, _leaf_violation

QUEUE_DIR = "queue"
QUEUE_FILE = "queue.json"
STARTED_DIR = "started"
SCHEMA_VERSION = 1
#: Entries the queue holds at most (spec 4.4.3).
MAX_QUEUE = 32
KINDS = ("start", "resume")
#: The journal kind of the record each kind of entry makes the pump write.
JOURNAL_KIND = {"start": "run_authorization", "resume": "run_authorization_control"}
#: Why the pump withdrew a preauthorization; `server_restarted` is read, never written.
DROP_REASONS = ("terms_changed", "grant_expired", "grant_changed", "preview_refused")
ADMISSIONS = ("confirmation", "auto_continue")
_ENTRY_KEYS = ("run_id", "kind", "enqueued_at", "enqueued_by", "preauthorization", "dropped")
_FILE_KEYS = ("schema_version", "revision", "entries")
_RECEIPT_KEYS = ("schema_version", "run_id", "kind", "record_id", "authorized_by",
                 "preauthorized_at", "digest", "record_digest", "started_at", "admission")
_FLAG_KEYS = ("flag_id", "transition_id")


class CorruptQueue(StoreError):
    """The queue file is not a record of this contract; no path is named."""


class CorruptReceipt(StoreError):
    """A receipt file is not a record of this contract or of its own path; no path is named."""


class ReceiptExists(StoreError):
    """Exclusive creation found a receipt under this key."""


def _closed(value: object, keys: tuple[str, ...], what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ContractError(f"{what} carries exactly {list(keys)!r}")
    return value


def _schema(value: object, what: str) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise ContractError(f"{what} speaks schema version {SCHEMA_VERSION}")


def _asked(value: object) -> dict[str, Any]:
    """The five fields the human asked for, as a fresh structure nobody else holds."""
    asked = closed_fields(value, PREVIEW_FIELDS, "the asked terms")
    for key in PREVIEW_FIELDS - {"node_limits"}:
        positive_integer(key, asked[key])
    if type(asked["node_limits"]) is not list:
        raise ContractError("node_limits must be a list")
    limits = [NodeLimit.from_dict(row).as_dict() for row in asked["node_limits"]]
    return {**asked, "node_limits": limits}


@dataclass(frozen=True)
class StartPreauth:
    """What the human confirmed to start a run: the body of an authorize, and what it was made of.

    `asked` is the five fields of the preview and `preview_digest` the digest of the terms they
    made; `source_prefix_digest` is the run's journal prefix in those terms (spec 4.4.6 reads a
    change at once from it, which a digest of the whole terms cannot say after a restart).
    """

    authorization_id: str
    preview_digest: str
    source_prefix_digest: str
    asked: dict[str, Any]
    supersedes: str | None
    authorized_by: str
    preauthorized_at: str

    _KEYS = ("authorization_id", "preview_digest", "source_prefix_digest", "asked", "supersedes",
             "authorized_by", "preauthorized_at")

    def __post_init__(self) -> None:
        _id("authorization_id", self.authorization_id)
        _digest("preview_digest", self.preview_digest)
        _digest("source_prefix_digest", self.source_prefix_digest)
        optional_id("supersedes", self.supersedes)
        human_identity("authorized_by", self.authorized_by)
        _timestamp("preauthorized_at", self.preauthorized_at)
        object.__setattr__(self, "asked", _asked(self.asked))

    @property
    def record_id(self) -> str:
        return self.authorization_id

    @property
    def digest(self) -> str:
        """What the human preauthorized: the digest of the terms he reviewed."""
        return self.preview_digest

    @property
    def human(self) -> str:
        return self.authorized_by

    def as_dict(self) -> dict[str, Any]:
        return {key: copy.deepcopy(getattr(self, key)) for key in self._KEYS}

    @classmethod
    def from_dict(cls, value: object) -> "StartPreauth":
        return cls(**_closed(value, cls._KEYS, "a start preauthorization"))


@dataclass(frozen=True)
class ResumePreauth:
    """What the human confirmed to resume a grant: the body of a control, without its action."""

    control_id: str
    authorization_id: str
    authorization_digest: str
    expected_control_id: str | None
    actor: str
    preauthorized_at: str

    _KEYS = ("control_id", "authorization_id", "authorization_digest", "expected_control_id",
             "actor", "preauthorized_at")

    def __post_init__(self) -> None:
        _id("control_id", self.control_id)
        _id("authorization_id", self.authorization_id)
        _digest("authorization_digest", self.authorization_digest)
        optional_id("expected_control_id", self.expected_control_id)
        human_identity("actor", self.actor)
        _timestamp("preauthorized_at", self.preauthorized_at)

    @property
    def record_id(self) -> str:
        return self.control_id

    @property
    def digest(self) -> str:
        """What the human preauthorized: the grant he was looking at."""
        return self.authorization_digest

    @property
    def human(self) -> str:
        return self.actor

    def as_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self._KEYS}

    @classmethod
    def from_dict(cls, value: object) -> "ResumePreauth":
        return cls(**_closed(value, cls._KEYS, "a resume preauthorization"))


_PREAUTH = {"start": StartPreauth, "resume": ResumePreauth}


@dataclass(frozen=True)
class Dropped:
    """Why and when the pump withdrew an entry's preauthorization."""

    reason_code: str
    at: str

    def __post_init__(self) -> None:
        if type(self.reason_code) is not str or self.reason_code not in DROP_REASONS:
            raise ContractError(f"a drop reason is one of {list(DROP_REASONS)!r}")
        _timestamp("at", self.at)

    def as_dict(self) -> dict[str, str]:
        return {"reason_code": self.reason_code, "at": self.at}

    @classmethod
    def from_dict(cls, value: object) -> "Dropped":
        return cls(**_closed(value, ("reason_code", "at"), "a drop"))


@dataclass(frozen=True)
class QueueEntry:
    """One run's place in the queue, with the permission it stands on or the reason it lost it."""

    run_id: str
    kind: str
    enqueued_at: str
    enqueued_by: str
    preauthorization: StartPreauth | ResumePreauth | None
    dropped: Dropped | None

    def __post_init__(self) -> None:
        _id("run_id", self.run_id)
        if type(self.kind) is not str or self.kind not in KINDS:
            raise ContractError(f"an entry is a start or a resume, not {self.kind!r}")
        _timestamp("enqueued_at", self.enqueued_at)
        human_identity("enqueued_by", self.enqueued_by)
        if (self.preauthorization is None) == (self.dropped is None):
            raise ContractError("an entry holds a preauthorization or the reason it lost it")
        if self.preauthorization is not None and type(
                self.preauthorization) is not _PREAUTH[self.kind]:
            raise ContractError("the body of an entry is the body of its kind")
        if self.dropped is not None and type(self.dropped) is not Dropped:
            raise ContractError("dropped is a Dropped")

    @property
    def key(self) -> tuple[str, str, str] | None:
        """`(run_id, journal kind, record_id)`, or None once the preauthorization is gone."""
        if self.preauthorization is None:
            return None
        return (self.run_id, JOURNAL_KIND[self.kind], self.preauthorization.record_id)

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "kind": self.kind, "enqueued_at": self.enqueued_at,
                "enqueued_by": self.enqueued_by,
                "preauthorization": None if self.preauthorization is None
                else self.preauthorization.as_dict(),
                "dropped": None if self.dropped is None else self.dropped.as_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "QueueEntry":
        data = _closed(value, _ENTRY_KEYS, "a queue entry")
        kind, body, dropped = data["kind"], data["preauthorization"], data["dropped"]
        if type(kind) is not str or kind not in KINDS:
            raise ContractError(f"an entry is a start or a resume, not {kind!r}")
        return cls(data["run_id"], kind, data["enqueued_at"], data["enqueued_by"],
                   None if body is None else _PREAUTH[kind].from_dict(body),
                   None if dropped is None else Dropped.from_dict(dropped))


@dataclass(frozen=True)
class QueueFile:
    """The file as a whole: its revision and its entries, in the order the human gave them."""

    revision: int
    entries: tuple[QueueEntry, ...]

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision < 0:
            raise ContractError("revision must be a non-negative integer")
        entries = tuple(self.entries)
        object.__setattr__(self, "entries", entries)
        if len(entries) > MAX_QUEUE:
            raise ContractError(f"the queue holds at most {MAX_QUEUE} entries")
        if any(type(row) is not QueueEntry for row in entries):
            raise ContractError("entries are QueueEntry values")
        if len({row.run_id for row in entries}) != len(entries):
            raise ContractError("the queue holds one entry per run")

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "revision": self.revision,
                "entries": [row.as_dict() for row in self.entries]}

    @classmethod
    def from_dict(cls, value: object) -> "QueueFile":
        data = _closed(value, _FILE_KEYS, "the queue file")
        _schema(data["schema_version"], "the queue file")
        if not isinstance(data["entries"], list):
            raise ContractError("entries must be a list")
        return cls(data["revision"], tuple(QueueEntry.from_dict(row) for row in data["entries"]))


@dataclass(frozen=True)
class Receipt:
    """The record that a start was about to be written, and on whose permission (spec 4.4.3).

    `digest` is what the human preauthorized and `record_digest` the digest of the journal record
    the pump is about to append, which covers the person and the time of that record; the two
    times, `preauthorized_at` and `started_at`, stay apart so the history shows both. A start by
    the continue-after flag names the flag and the transition as well.
    """

    run_id: str
    kind: str
    record_id: str
    authorized_by: str
    preauthorized_at: str
    digest: str
    record_digest: str
    started_at: str
    admission: str
    flag_id: str | None = None
    transition_id: str | None = None

    def __post_init__(self) -> None:
        _id("run_id", self.run_id)
        if self.kind not in JOURNAL_KIND.values():
            raise ContractError("a receipt names the journal kind of the record it precedes")
        _id("record_id", self.record_id)
        human_identity("authorized_by", self.authorized_by)
        _timestamp("preauthorized_at", self.preauthorized_at)
        _digest("digest", self.digest)
        _digest("record_digest", self.record_digest)
        _timestamp("started_at", self.started_at)
        if self.admission not in ADMISSIONS:
            raise ContractError(f"an admission is one of {list(ADMISSIONS)!r}")
        flagged = self.admission == "auto_continue"
        if flagged != (self.flag_id is not None) or flagged != (self.transition_id is not None):
            raise ContractError("a flag and a transition belong to an auto_continue receipt, "
                                "and to it alone")
        if flagged:
            _id("flag_id", self.flag_id)
            _id("transition_id", self.transition_id)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
        out.update({key: getattr(self, key) for key in _RECEIPT_KEYS[1:]})
        if self.admission == "auto_continue":
            out.update({key: getattr(self, key) for key in _FLAG_KEYS})
        return out

    @classmethod
    def from_dict(cls, value: object) -> "Receipt":
        if not isinstance(value, Mapping):
            raise ContractError("a receipt is an object")
        keys = _RECEIPT_KEYS + (_FLAG_KEYS if value.get("admission") == "auto_continue" else ())
        data = dict(_closed(value, keys, "a receipt"))
        _schema(data.pop("schema_version"), "a receipt")
        return cls(**data)


class QueueStore:
    """The queue file and the receipts of one project, under the project's root gate."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        # The gate every store of this root shares, held strongly: the module table is weak.
        self._root_gate = _root_gate(self.project_root)

    @property
    def queue_dir(self) -> Path:
        """Where the queue lives now: the data root can move when the project is activated."""
        return data_root(self.project_root) / QUEUE_DIR

    @property
    def path(self) -> Path:
        return self.queue_dir / QUEUE_FILE

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """One process-local transaction for this root, the depth `RunStore` keeps included."""
        with self._root_gate.lock:
            depth = getattr(_ROOT_TRANSACTION_STATE, "depth", 0)
            _ROOT_TRANSACTION_STATE.depth = depth + 1
            try:
                yield
            finally:
                _ROOT_TRANSACTION_STATE.depth = depth

    @staticmethod
    def _owned(path: Path, directories: tuple[Path, ...]) -> Path:
        """`path` after the route to it is judged: local directories, a lone regular file."""
        if first_directory_violation(directories) or _leaf_violation(path) is not None:
            raise RouteNotOwned("the route of the project queue is not this store's")
        return path

    def read(self) -> QueueFile:
        """The standing file, or revision 0 and no entries when it is absent.

        Raises:
            CorruptQueue: The file is unreadable or is not a record of this contract.
            RouteNotOwned: The route reaches state this store cannot account for.
        """
        with self.transaction():
            return self._read()

    def _read(self) -> QueueFile:
        path = self._owned(self.path, (self.queue_dir.parent, self.queue_dir))
        if not path.exists():
            return QueueFile(0, ())
        try:
            return QueueFile.from_dict(_json_object(path, QUEUE_FILE))
        except (CorruptRun, ContractError):
            raise CorruptQueue("the project queue is unreadable or violates its contract") from None

    @owned_write
    def write(self, entries: tuple[QueueEntry, ...]) -> QueueFile:
        """Replace the file with these entries at the next revision, all or nothing.

        Raises:
            ContractError: More than 32 entries, or two for one run.
            RouteNotOwned: The route reaches state this store cannot account for.
            StoreError: The owner's guard refuses, or the bytes could not be written.
        """
        if type(entries) is not tuple or any(type(row) is not QueueEntry for row in entries):
            raise StoreError("write takes a tuple of QueueEntry")
        with self.transaction():
            written = QueueFile(self._read().revision + 1, entries)
            directory = self.queue_dir
            directory.mkdir(parents=True, exist_ok=True)
            path = self._owned(self.path, (directory.parent, directory))
            try:
                _replace_bytes(path, _canonical_bytes(written.as_dict()))
                _fsync_dir(directory)
            except OSError as error:
                raise StoreError(f"cannot write the project queue: {error}") from error
            return written

    def receipt_path(self, run_id: str, kind: str, record_id: str) -> Path:
        """Where the receipt of this key lives, the three names judged before any join."""
        try:
            parts = (_id("run_id", run_id), _id("record_id", record_id))
        except ContractError as error:
            raise StoreError(str(error)) from error
        if kind not in JOURNAL_KIND.values():
            raise StoreError("a receipt is kept under the journal kind of its record")
        return self.queue_dir / STARTED_DIR / parts[0] / kind / f"{parts[1]}.json"

    def _receipt_route(self, path: Path) -> Path:
        chain = tuple(reversed(path.parents[:5]))
        return self._owned(path, chain)

    def read_receipt(self, run_id: str, kind: str, record_id: str) -> Receipt | None:
        """The receipt of this key, or None when there is none.

        Raises:
            CorruptReceipt: The file is not a record, or names another key than its path.
            RouteNotOwned: The route reaches state this store cannot account for.
        """
        with self.transaction():
            path = self._receipt_route(self.receipt_path(run_id, kind, record_id))
            if not path.exists():
                return None
            try:
                found = Receipt.from_dict(_json_object(path, "a receipt"))
            except (CorruptRun, ContractError):
                raise CorruptReceipt("a start receipt is unreadable or violates its contract") \
                    from None
            if (found.run_id, found.kind, found.record_id) != (run_id, kind, record_id):
                raise CorruptReceipt("a start receipt names another key than its place")
            return found

    @owned_write
    def write_receipt(self, receipt: Receipt) -> None:
        """Create the receipt exclusively; a key that already has one is `ReceiptExists`."""
        self._write_receipt(receipt, replace=False)

    @owned_write
    def replace_receipt(self, receipt: Receipt) -> None:
        """Replace a receipt that no journal record pairs with: the caller has judged that.

        The store reads no journal and cannot tell an orphan from a paired receipt; the pump
        reconciles the key first and only ever calls this for a receipt nothing pairs with.
        """
        self._write_receipt(receipt, replace=True)

    def put_receipt(self, receipt: Receipt) -> None:
        """Create the receipt; one that already stands is an orphan and is replaced.

        The caller reconciled the key first and found no journal record under it, so a receipt
        that stands is the leftover of a start that never reached the journal: a retry replaces it
        and is not poisoned by it. A receipt a journal record pairs with is never passed here.
        """
        try:
            self.write_receipt(receipt)
        except ReceiptExists:
            self.replace_receipt(receipt)

    def _write_receipt(self, receipt: Receipt, *, replace: bool) -> None:
        if type(receipt) is not Receipt:
            raise StoreError("a receipt write takes exactly a Receipt")
        admit_name(receipt.record_id, "record_id")
        path = self.receipt_path(receipt.run_id, receipt.kind, receipt.record_id)
        admit_file(path, "queue receipt")
        with self.transaction():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._receipt_route(path)
            payload = _canonical_bytes(receipt.as_dict())
            try:
                if replace:
                    _replace_bytes(path, payload)
                else:
                    _exclusive_bytes(path, payload)
                _fsync_dir(path.parent)
            except FileExistsError:
                raise ReceiptExists("a start receipt already stands under this key") from None
            except OSError as error:
                raise StoreError(f"cannot write the start receipt: {error}") from error
