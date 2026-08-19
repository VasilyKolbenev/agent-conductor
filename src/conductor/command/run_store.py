"""Crash-aware, append-only storage for December Command runs.

The store records facts; it does not execute a Harness or infer success. A
run directory is created as one staged snapshot, its configuration is frozen
by digest, journal records are canonical JSON lines, and Human decisions get
an additional exclusive-created receipt file.  Mutable projections belong in
later runtime code and must always be rebuildable from this store. Store
transactions serialize resolved project roots inside this process only; they
claim no cross-process filesystem exclusion.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from threading import Lock, RLock, local
from typing import Any
from weakref import WeakValueDictionary

from .attempt_replay import (
    AttemptRelationError,
    action_request_for,
    attempt_events_for,
    validate_attempt_event,
    validate_event_result,
)
from .attempts import AttemptEvent
from .graph_definition import GraphDefinition
from .contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    DecisionReceipt,
    EvidenceRef,
    ObservationRecord,
    RunEnvelope,
    _freeze_json,
    _id,
    canonical_json,
)


class StoreError(RuntimeError):
    """The run store cannot safely complete the requested operation."""


class RunExists(StoreError):
    """Exclusive run creation found an existing identity."""


class RecordConflict(StoreError):
    """An immutable identity or idempotency key was reused with new meaning."""


class _RootGate:
    """One weakly indexed, strongly store-owned process-local root gate."""

    __slots__ = ("lock", "__weakref__")

    def __init__(self) -> None:
        self.lock = RLock()


_ROOT_GATES_GUARD = Lock()
_ROOT_GATES: WeakValueDictionary[Path, _RootGate] = WeakValueDictionary()
_ROOT_TRANSACTION_STATE = local()


def _root_gate(root: Path) -> _RootGate:
    with _ROOT_GATES_GUARD:
        gate = _ROOT_GATES.get(root)
        if gate is None:
            gate = _RootGate()
            _ROOT_GATES[root] = gate
        return gate


def _transactional(method):
    """Hold one process-local root writer transaction for a store operation."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.transaction():
            return method(self, *args, **kwargs)
    return wrapped


class CorruptRun(StoreError):
    """Durable bytes contradict the contracts or one another."""


RecordValue = (
    ActionRequest | ActionResultReceipt | EvidenceRef | DecisionReceipt
    | ActionProposal | ObservationRecord | AttemptEvent | GraphDefinition
)


@dataclass(frozen=True)
class StoredRecord:
    """One validated record in durable append order."""

    kind: str
    value: RecordValue


@dataclass(frozen=True)
class RecoveredRun:
    """The replayable facts recovered from one run directory."""

    envelope: RunEnvelope
    config: Mapping[str, Any]
    records: tuple[StoredRecord, ...]
    warnings: tuple[str, ...]


_RECORDS: dict[str, tuple[type[RecordValue], str]] = {
    "action_request": (ActionRequest, "action_id"),
    "action_result": (ActionResultReceipt, "receipt_id"),
    "evidence": (EvidenceRef, "evidence_id"),
    "decision": (DecisionReceipt, "receipt_id"),
    "action_proposal": (ActionProposal, "proposal_id"),
    "adapter_observation": (ObservationRecord, "observation_id"),
    "attempt_event": (AttemptEvent, "event_id"),
    "graph_definition": (GraphDefinition, "graph_id"),
}

# A named-key screen, not a proof that the snapshot is secret-free: a key is
# refused when its compact spelling IS one of these parts or it ends in `_<part>`.
# Prefix and infix forms (`private_key`, `password_hash`, `secret_value`,
# `token_value`, `apikeys`, `github_pat`, `authorization_header`) and every
# secret carried in a VALUE pass through, so this raises the cost of the common
# mistake and is not a containment boundary.  `*_env` and `*_env_var` name where
# the runtime should find a secret and are deliberately allowed.
_SECRET_PARTS = frozenset({
    "api_key", "authorization", "cookie", "credential", "password", "secret", "token",
})
_SECRET_COMPACT = frozenset(part.replace("_", "") for part in _SECRET_PARTS)
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    """Digest the canonical JSON shape of a configuration snapshot."""
    if not isinstance(snapshot, Mapping):
        raise StoreError("configuration snapshot must be a JSON object")
    try:
        encoded = canonical_json(dict(snapshot)).encode("utf-8")
    except ContractError as e:
        raise StoreError(f"configuration snapshot is not canonical JSON: {e}") from e
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _secret_field(value: object, path: tuple[str, ...] = ()) -> str | None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                return ".".join((*path, repr(raw_key)))
            key = re.sub(r"[-. ]+", "_", raw_key.casefold())
            reference = key.endswith("_env") or key.endswith("_env_var")
            if reference and (not isinstance(item, str) or _ENV_NAME.fullmatch(item) is None):
                return ".".join((*path, raw_key))
            compact = key.replace("_", "")
            if not reference and (
                    compact in _SECRET_COMPACT
                    or any(key.endswith("_" + part) for part in _SECRET_PARTS)):
                return ".".join((*path, raw_key))
            found = _secret_field(item, (*path, raw_key))
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _secret_field(item, (*path, str(index)))
            if found is not None:
                return found
    return None


def _canonical_bytes(value: object) -> bytes:
    try:
        return (canonical_json(value) + "\n").encode("utf-8")
    except ContractError as e:
        raise StoreError(f"value is not canonical JSON: {e}") from e


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise OSError("write returned no progress")
        offset += written


def _exclusive_bytes(path: Path, payload: bytes) -> None:
    """Publish `payload` at `path` all-or-nothing, and only if `path` is unclaimed.

    The content is staged under a private name and fsynced first, so a crash can
    never publish a half-written or zero-length file; `os.link` then refuses an
    already-claimed name on every supported platform, which keeps exclusivity the
    arbiter between two writers racing for the same identity.
    """
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    stage = Path(raw)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(stage, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            stage.unlink()
        except FileNotFoundError:
            pass


#: Windows opens a descriptor in text mode unless told otherwise, and the CRT
#: then translates every LF written through it into CRLF. `tempfile.mkstemp`
#: already sets this flag for the staged writes, so without it here the two
#: durable spellings of one record would differ by a CR each: the journal line is
#: appended, while `run.json`, `config.json` and every `decisions/*.json` are
#: staged. Absent on POSIX, where `getattr` supplies the no-op 0.
_O_BINARY = getattr(os, "O_BINARY", 0)


def _append_bytes(path: Path, payload: bytes) -> None:
    fd: int | None = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | _O_BINARY)
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)


def _replace_bytes(path: Path, payload: bytes) -> None:
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temp, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _fsync_dir(path: Path) -> None:
    """Best-effort directory durability; Windows cannot open directories this way."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise CorruptRun(f"{description} is unreadable: {e}") from e
    if not isinstance(value, dict):
        raise CorruptRun(f"{description} must be a JSON object")
    return value


def _one_graph_per_run(recovered: "RecoveredRun", value: GraphDefinition) -> None:
    """A run follows ONE graph, which identity alone would never have said.

    Two graphs with different ids are two different identities, so the store
    would take both and leave every reader to guess which plan the run is
    actually following. Editing, versioning and templates are a later slice;
    until they land, a second graph is a question this product cannot answer,
    and the refusal NAMES the plan already standing so an operator knows which.
    """
    standing = next((row.value for row in recovered.records
                     if row.kind == "graph_definition"), None)
    if standing is not None and standing.graph_id != value.graph_id:
        raise RecordConflict(
            f"run {recovered.envelope.run_id!r} already follows graph "
            f"{standing.graph_id!r}; one run carries one graph")


def _record_parts(value: RecordValue) -> tuple[str, str, str]:
    for kind, (contract, identity_field) in _RECORDS.items():
        if isinstance(value, contract):
            return kind, identity_field, getattr(value, identity_field)
    raise StoreError(f"unsupported record type {type(value).__name__}")


def _record_wrapper(kind: str, value: RecordValue) -> dict[str, Any]:
    return {"record": value.as_dict(), "record_type": kind}


def _causal_order(
        orphans: list[DecisionReceipt], journalled: set[str]) -> list[DecisionReceipt]:
    """Rejoin orphan receipts when they were decided, and after what they supersede.

    Filename order is not causal order, so a supersedes chain whose receipt ids
    sort against it would otherwise be unreplayable.  A receipt whose predecessor
    is nowhere to be found is emitted anyway, so replay validation names the real
    break instead of this function hiding it in an arbitrary order.
    """
    pending = sorted(orphans, key=lambda row: (row.decided_at, row.receipt_id))
    ordered: list[DecisionReceipt] = []
    placed = set(journalled)
    while pending:
        index = next(
            (spot for spot, row in enumerate(pending)
             if row.supersedes is None or row.supersedes in placed),
            0)
        row = pending.pop(index)
        placed.add(row.receipt_id)
        ordered.append(row)
    return ordered


class RunStore:
    """Single-writer store rooted at one project's `conductor/runs` directory.

    Repair belongs to that one writer: `recover` may truncate a crash tail and
    rejoin an orphan receipt, so a second process calling it would rewrite the
    journal the writer is appending to.  Any other process reads with `read`,
    which returns the same replayed history and touches no durable byte.
    """

    def __init__(
            self, project_root: str | os.PathLike[str], *,
            on_warning: Callable[[str], None] | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.runs_root = self.project_root / "conductor" / "runs"
        self._on_warning = on_warning
        self._root_gate = _root_gate(self.project_root)

    def run_path(self, run_id: str) -> Path:
        try:
            safe = _id("run_id", run_id)
        except ContractError as e:
            raise StoreError(str(e)) from e
        return self.runs_root / safe

    @contextmanager
    def transaction(self):
        """Serialize one process-local transaction for this resolved project root."""
        with self._root_gate.lock:
            depth = getattr(_ROOT_TRANSACTION_STATE, "depth", 0)
            _ROOT_TRANSACTION_STATE.depth = depth + 1
            try:
                yield
            finally:
                _ROOT_TRANSACTION_STATE.depth = depth

    @staticmethod
    def current_thread_holds_transaction() -> bool:
        """Report a root lock held by this thread, independent of its project."""
        return bool(getattr(_ROOT_TRANSACTION_STATE, "depth", 0))

    @_transactional
    def create_run(self, envelope: RunEnvelope, snapshot: Mapping[str, Any]) -> Path:
        """Exclusively create a complete run envelope and frozen configuration."""
        if not isinstance(envelope, RunEnvelope):
            raise StoreError("envelope must be a validated RunEnvelope")
        if not isinstance(snapshot, Mapping):
            raise StoreError("configuration snapshot must be a JSON object")
        secret = _secret_field(snapshot)
        if secret is not None:
            raise StoreError(
                f"configuration snapshot contains secret-bearing field {secret!r}; "
                "store an *_env reference instead")
        digest = snapshot_digest(snapshot)
        if digest != envelope.config_digest:
            raise StoreError(
                f"config_digest does not match the frozen snapshot: "
                f"envelope has {envelope.config_digest}, computed {digest}")

        final = self.run_path(envelope.run_id)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        if final.exists():
            raise RunExists(f"run {envelope.run_id!r} already exists")
        stage = Path(tempfile.mkdtemp(prefix=f".{envelope.run_id}.", dir=self.runs_root))
        try:
            _exclusive_bytes(stage / "run.json", _canonical_bytes(envelope))
            _exclusive_bytes(stage / "config.json", _canonical_bytes(dict(snapshot)))
            _exclusive_bytes(stage / "records.jsonl", b"")
            (stage / "decisions").mkdir()
            _fsync_dir(stage)
            try:
                os.rename(stage, final)
            except FileExistsError as e:
                raise RunExists(f"run {envelope.run_id!r} already exists") from e
            except OSError as e:
                if final.exists():
                    raise RunExists(f"run {envelope.run_id!r} already exists") from e
                raise StoreError(f"cannot publish run {envelope.run_id!r}: {e}") from e
            _fsync_dir(self.runs_root)
            return final
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    @_transactional
    def append(self, value: RecordValue) -> bool:
        """Append one immutable record; return False for an identical retry."""
        kind, identity_field, identity = _record_parts(value)
        run_id = value.run_id
        recovered = self.recover(run_id)
        if self._on_warning is not None:
            for warning in recovered.warnings:
                self._on_warning(warning)
        existing = [row for row in recovered.records if row.kind == kind]
        for row in existing:
            if getattr(row.value, identity_field) == identity:
                if row.value == value:
                    return False
                raise RecordConflict(
                    f"{kind} identity {identity!r} already records different facts")
        if isinstance(value, ActionRequest):
            for row in recovered.records:
                if (isinstance(row.value, ActionRequest)
                        and row.value.idempotency_key == value.idempotency_key):
                    raise RecordConflict(
                        f"idempotency_key {value.idempotency_key!r} already belongs to "
                        f"action {row.value.action_id!r}")
        self._validate_new_relation(recovered, value)

        wrapper = _record_wrapper(kind, value)
        if isinstance(value, DecisionReceipt):
            self._ensure_decision_file(value, wrapper)
        try:
            _append_bytes(self.run_path(run_id) / "records.jsonl", _canonical_bytes(wrapper))
        except OSError as e:
            raise StoreError(f"cannot append {kind} {identity!r}: {e}") from e
        return True

    @_transactional
    def read(self, run_id: str) -> RecoveredRun:
        """Validate and replay a run without editing one durable byte."""
        return self._replay(run_id, repair=False)

    @_transactional
    def recover(self, run_id: str) -> RecoveredRun:
        """Replay a run and repair what a crash left behind; only the writer may."""
        return self._replay(run_id, repair=True)

    def _replay(self, run_id: str, *, repair: bool) -> RecoveredRun:
        root = self.run_path(run_id)
        if not root.is_dir():
            raise StoreError(f"run {run_id!r} does not exist")
        try:
            envelope = RunEnvelope.from_dict(_json_object(root / "run.json", "run.json"))
        except ContractError as e:
            raise CorruptRun(f"run.json violates the run contract: {e}") from e
        if envelope.run_id != run_id:
            raise CorruptRun(
                f"run directory {run_id!r} contains envelope {envelope.run_id!r}")
        config = _json_object(root / "config.json", "config.json")
        if snapshot_digest(config) != envelope.config_digest:
            raise CorruptRun("frozen config digest does not match run.json")
        secret = _secret_field(config)
        if secret is not None:
            raise CorruptRun(f"frozen config contains secret-bearing field {secret!r}")

        records, warnings = self._read_journal(root / "records.jsonl", run_id, repair)
        # _reconcile_decisions validates the final record set once, early enough that
        # an unreconcilable receipt leaves records.jsonl byte-identical; _replay does
        # not re-validate the same records a second time.
        records, decision_warnings = self._reconcile_decisions(
            root, envelope, config, records, repair)
        return RecoveredRun(
            envelope=envelope,
            config=_freeze_json(config),
            records=tuple(records),
            warnings=tuple((*warnings, *decision_warnings)),
        )

    def _read_journal(
            self, path: Path, run_id: str,
            repair: bool) -> tuple[list[StoredRecord], list[str]]:
        try:
            payload = path.read_bytes()
        except OSError as e:
            raise CorruptRun(f"records.jsonl is unreadable: {e}") from e
        warnings: list[str] = []
        complete = payload
        if payload and not payload.endswith(b"\n"):
            cut = payload.rfind(b"\n") + 1
            complete = payload[:cut]
            if not repair:
                warnings.append(
                    "records.jsonl ends with an incomplete record; the incomplete tail "
                    "was ignored and left in place")
            else:
                try:
                    _replace_bytes(path, complete)
                except OSError as e:
                    raise CorruptRun(
                        f"cannot remove incomplete records.jsonl tail: {e}") from e
                warnings.append(
                    "records.jsonl ended with an incomplete record; "
                    "the incomplete tail was ignored")

        records: list[StoredRecord] = []
        identities: set[tuple[str, str]] = set()
        for number, raw in enumerate(complete.splitlines(), 1):
            try:
                wrapper = json.loads(raw.decode("utf-8"))
                kind = wrapper["record_type"]
                record = wrapper["record"]
                contract, identity_field = _RECORDS[kind]
                value = contract.from_dict(record)
            except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ContractError) as e:
                raise CorruptRun(f"records.jsonl line {number} is invalid: {e}") from e
            if value.run_id != run_id:
                raise CorruptRun(
                    f"records.jsonl line {number} belongs to run {value.run_id!r}")
            if raw + b"\n" != _canonical_bytes(_record_wrapper(kind, value)):
                raise CorruptRun(
                    f"records.jsonl line {number} is not canonical JSON")
            identity = (kind, getattr(value, identity_field))
            if identity in identities:
                raise CorruptRun(
                    f"records.jsonl line {number} duplicates {kind} identity {identity[1]!r}")
            identities.add(identity)
            records.append(StoredRecord(kind, value))
        return records, warnings

    @staticmethod
    def _validate_new_relation(recovered: RecoveredRun, value: RecordValue) -> None:
        prior_values = tuple(row.value for row in recovered.records)
        if isinstance(value, GraphDefinition):
            _one_graph_per_run(recovered, value)
        if isinstance(value, ActionProposal):
            if value.config_digest != recovered.envelope.config_digest:
                raise StoreError("proposal config_digest does not match the frozen run")
        if isinstance(value, ActionResultReceipt):
            action = action_request_for(prior_values, value.action_id)
            if action is None:
                raise StoreError(f"action result names unknown action {value.action_id!r}")
            for field in ("attempt_id", "instance_id"):
                if getattr(action, field) != getattr(value, field):
                    raise StoreError(
                        f"action result {field} does not match action {value.action_id!r}")
            events = attempt_events_for(prior_values, value.action_id)
            if events:
                try:
                    validate_event_result(prior_values, value, events)
                except AttemptRelationError as e:
                    raise StoreError(str(e)) from e
        if isinstance(value, AttemptEvent):
            try:
                validate_attempt_event(recovered.config, prior_values, value)
            except AttemptRelationError as e:
                raise StoreError(str(e)) from e
        if isinstance(value, DecisionReceipt):
            if value.config_digest != recovered.envelope.config_digest:
                raise StoreError("decision config_digest does not match the frozen run")
            if value.supersedes is not None:
                prior = next((row.value for row in recovered.records
                              if isinstance(row.value, DecisionReceipt)
                              and row.value.receipt_id == value.supersedes), None)
                if prior is None:
                    raise StoreError(
                        f"decision {value.receipt_id!r} supersedes unknown receipt "
                        f"{value.supersedes!r}")
                if prior.gate_id != value.gate_id:
                    raise StoreError(
                        f"decision {value.receipt_id!r} cannot supersede a different gate")

    @classmethod
    def _validate_records(
            cls, envelope: RunEnvelope, config: Mapping[str, Any],
            records: list[StoredRecord]) -> None:
        """Hold causal relations even when bytes were written outside this process."""
        seen: list[StoredRecord] = []
        idempotency: dict[str, str] = {}
        for row in records:
            if isinstance(row.value, ActionRequest):
                previous = idempotency.get(row.value.idempotency_key)
                if previous is not None:
                    raise CorruptRun(
                        f"idempotency_key {row.value.idempotency_key!r} belongs to both "
                        f"{previous!r} and {row.value.action_id!r}")
                idempotency[row.value.idempotency_key] = row.value.action_id
            recovered = RecoveredRun(
                envelope=envelope, config=_freeze_json(config),
                records=tuple(seen), warnings=())
            try:
                cls._validate_new_relation(recovered, row.value)
            except StoreError as e:
                raise CorruptRun(f"{row.kind} breaks replay causality: {e}") from e
            seen.append(row)

    def _ensure_decision_file(
            self, decision: DecisionReceipt, wrapper: Mapping[str, Any]) -> None:
        path = self.run_path(decision.run_id) / "decisions" / f"{decision.receipt_id}.json"
        payload = _canonical_bytes(wrapper)
        try:
            _exclusive_bytes(path, payload)
        except FileExistsError:
            try:
                existing = path.read_bytes()
            except OSError as e:
                raise CorruptRun(
                    f"decision receipt {decision.receipt_id!r} is unreadable: {e}") from e
            if existing != payload:
                raise RecordConflict(
                    f"decision receipt {decision.receipt_id!r} already records different facts")
        except OSError as e:
            raise StoreError(
                f"cannot create decision receipt {decision.receipt_id!r}: {e}") from e

    def _reconcile_decisions(
            self, root: Path, envelope: RunEnvelope, config: Mapping[str, Any],
            records: list[StoredRecord], repair: bool,
    ) -> tuple[list[StoredRecord], list[str]]:
        orphans, by_id = self._collect_decision_files(root, envelope.run_id, records)
        if not orphans:
            self._validate_records(envelope, config, records)
            return records, []
        rejoined, prospective = self._decide_rejoined_history(
            envelope, config, records, orphans, by_id)
        return self._publish_rejoined_history(root, rejoined, prospective, repair)

    def _collect_decision_files(
            self, root: Path, run_id: str,
            records: list[StoredRecord]) -> tuple[list[DecisionReceipt], set[str]]:
        """Validate every exclusive receipt file and return the ones with no journal line."""
        decisions = root / "decisions"
        if not decisions.is_dir():
            raise CorruptRun("decisions directory is missing")
        by_id = {
            row.value.receipt_id: row
            for row in records if isinstance(row.value, DecisionReceipt)
        }
        files = sorted(decisions.glob("*.json"), key=lambda item: item.name)
        orphans: list[DecisionReceipt] = []
        for path in files:
            wrapper = _json_object(path, f"decision receipt {path.name}")
            try:
                if wrapper.get("record_type") != "decision":
                    raise ContractError("record_type must be 'decision'")
                decision = DecisionReceipt.from_dict(wrapper["record"])
            except (KeyError, ContractError) as e:
                raise CorruptRun(f"decision receipt {path.name} is invalid: {e}") from e
            if wrapper != _record_wrapper("decision", decision):
                raise CorruptRun(
                    f"decision receipt {decision.receipt_id!r} has non-canonical or "
                    "uncontracted fields")
            if decision.run_id != run_id:
                raise CorruptRun(
                    f"decision receipt {decision.receipt_id!r} belongs to another run")
            if path.stem != decision.receipt_id:
                raise CorruptRun(
                    f"decision filename {path.stem!r} disagrees with {decision.receipt_id!r}")
            journal_row = by_id.get(decision.receipt_id)
            if journal_row is not None:
                if journal_row.value != decision:
                    raise CorruptRun(
                        f"decision receipt {decision.receipt_id!r} disagrees with records.jsonl")
                continue
            orphans.append(decision)
        missing = sorted(set(by_id) - {path.stem for path in files})
        if missing:
            raise CorruptRun(f"decision receipts missing exclusive files: {missing}")
        return orphans, set(by_id)

    def _decide_rejoined_history(
            self, envelope: RunEnvelope, config: Mapping[str, Any],
            records: list[StoredRecord],
            orphans: list[DecisionReceipt],
            journalled: set[str]) -> tuple[list[DecisionReceipt], list[StoredRecord]]:
        """Order the orphans and prove the whole history replays BEFORE anything is written.

        Validating here, before `_publish_rejoined_history` appends, is what leaves
        records.jsonl byte-identical when a receipt cannot be reconciled, so the
        operator can remove the stray file and retry.
        """
        rejoined = _causal_order(orphans, journalled)
        prospective = [*records, *(StoredRecord("decision", row) for row in rejoined)]
        self._validate_records(envelope, config, prospective)
        return rejoined, prospective

    def _publish_rejoined_history(
            self, root: Path, rejoined: list[DecisionReceipt],
            prospective: list[StoredRecord],
            repair: bool) -> tuple[list[StoredRecord], list[str]]:
        if not repair:
            return prospective, [
                f"decision receipt {decision.receipt_id!r} survived without its journal "
                "line; the line was replayed but not written"
                for decision in rejoined
            ]
        for decision in rejoined:
            try:
                _append_bytes(
                    root / "records.jsonl",
                    _canonical_bytes(_record_wrapper("decision", decision)))
            except OSError as e:
                raise CorruptRun(
                    f"cannot recover decision receipt {decision.receipt_id!r}: {e}") from e
        return prospective, [
            f"decision receipt {decision.receipt_id!r} survived without its journal line; "
            "the line was recovered"
            for decision in rejoined
        ]
