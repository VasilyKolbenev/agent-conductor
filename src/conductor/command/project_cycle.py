"""The project's pinned cycle: the one file the human writes with one button (spec 7.10).

`data_root/project-cycle.json` says which workflow a new task of the project starts on, who
pinned it and when. The old rule, "the cycle of the last run", quietly made a one-off cycle the
project's; a pin is an explicit act, and the wizard always says where its preselection came
from. The record is canonical JSON replaced atomically under the project owner's write guard,
and read through the same structural route check the other stores hold: a portal anywhere on the
way means the name is here and the bytes are somewhere else.

The store keeps no index of workflows and judges none: whether the pinned workflow has a
published revision is asked of the template store by the handler that pins.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..ownership import data_root, owned_write
from .authorization_terms import human_identity
from .containment import first_directory_violation
from .contract_values import ContractError, _id, _timestamp
from .run_files import _canonical_bytes, _fsync_dir, _json_object, _replace_bytes
from .run_store import _ROOT_TRANSACTION_STATE, _root_gate
from .store_errors import CorruptRun, StoreError
from .template_store import RouteNotOwned, _leaf_violation

#: The one file this store holds, beside `tasks`, `runs` and `templates`.
PIN_FILE = "project-cycle.json"
PIN_SCHEMA_VERSION = 1
_FIELDS = ("schema_version", "workflow_id", "set_by", "set_at")


class CorruptPin(StoreError):
    """The pin file is not a record of this contract; no path is named."""


@dataclass(frozen=True)
class PinRecord:
    """Which workflow is the project's cycle (`None`: none is pinned), by whom and when."""

    workflow_id: str | None
    set_by: str
    set_at: str

    def __post_init__(self) -> None:
        if self.workflow_id is not None:
            object.__setattr__(self, "workflow_id", _id("workflow_id", self.workflow_id))
        object.__setattr__(self, "set_by", human_identity("set_by", self.set_by))
        object.__setattr__(self, "set_at", _timestamp("set_at", self.set_at))

    def as_dict(self) -> dict[str, Any]:
        """The stored shape, self-describing, keys in the one fixed order."""
        return {"schema_version": PIN_SCHEMA_VERSION, "workflow_id": self.workflow_id,
                "set_by": self.set_by, "set_at": self.set_at}

    @classmethod
    def from_dict(cls, value: object) -> "PinRecord":
        """Admit one stored record: closed at every key, exact at the version.

        Raises:
            ContractError: Not an object, a key too many or too few, another schema version, or
                a value one of the fields refuses.
        """
        if not isinstance(value, Mapping) or set(value) != set(_FIELDS):
            raise ContractError(f"a pin record carries exactly {list(_FIELDS)!r}")
        version = value["schema_version"]
        if type(version) is not int or version != PIN_SCHEMA_VERSION:
            raise ContractError("a pin record speaks schema version 1")
        return cls(value["workflow_id"], value["set_by"], value["set_at"])


class ProjectCycleStore:
    """The pin file of one project, read and written under the project's root gate."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        # The gate every store of this root shares, held strongly: the module table is weak.
        self._root_gate = _root_gate(self.project_root)

    @property
    def path(self) -> Path:
        """Where the pin lives now: the data root can move when the project is activated."""
        return data_root(self.project_root) / PIN_FILE

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

    def _owned(self) -> Path:
        """The pin's path, after the route to it is judged: regular, local, singly named."""
        path = self.path
        if first_directory_violation((path.parent,)) or _leaf_violation(path) is not None:
            raise RouteNotOwned("the route of the project cycle pin is not this store's")
        return path

    def read(self) -> PinRecord | None:
        """The standing pin record, or `None` when the file is absent.

        Raises:
            CorruptPin: The file is unreadable or is not a record of this contract.
            RouteNotOwned: The route reaches state this store cannot account for.
        """
        with self.transaction():
            path = self._owned()
            if not path.exists():
                return None
            try:
                document = _json_object(path, PIN_FILE)
            except CorruptRun:
                raise CorruptPin("the project cycle pin is unreadable") from None
            try:
                return PinRecord.from_dict(document)
            except ContractError:
                raise CorruptPin("the project cycle pin violates its contract") from None

    @owned_write
    def write(self, record: PinRecord) -> None:
        """Replace the pin file with this record, all or nothing.

        Raises:
            RouteNotOwned: The route reaches state this store cannot account for.
            StoreError: The owner's guard refuses, or the bytes could not be written.
        """
        if type(record) is not PinRecord:
            raise StoreError("write takes exactly a PinRecord")
        with self.transaction():
            path = self._owned()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._owned()
            try:
                _replace_bytes(path, _canonical_bytes(record.as_dict()))
                _fsync_dir(path.parent)
            except OSError as error:
                raise StoreError(f"cannot write the project cycle pin: {error}") from error
