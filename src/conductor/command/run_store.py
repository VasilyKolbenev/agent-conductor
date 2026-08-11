"""Crash-aware, append-only storage for December Command runs.

The store records facts; it does not execute a Harness or infer success.  A
run directory is created as one staged snapshot, its configuration is frozen
by digest, journal records are canonical JSON lines, and Human decisions get
an additional exclusive-created receipt file.  Mutable projections belong in
later runtime code and must always be rebuildable from this store.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .contracts import (
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    DecisionReceipt,
    EvidenceRef,
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


class CorruptRun(StoreError):
    """Durable bytes contradict the contracts or one another."""


RecordValue = ActionRequest | ActionResultReceipt | EvidenceRef | DecisionReceipt


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
}

# A snapshot may name where the runtime should find a secret, never carry its
# value.  `*_env` and `*_env_var` are references and are deliberately allowed.
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
    fd: int | None = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)


def _append_bytes(path: Path, payload: bytes) -> None:
    fd: int | None = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND)
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


def _record_parts(value: RecordValue) -> tuple[str, str, str]:
    for kind, (contract, identity_field) in _RECORDS.items():
        if isinstance(value, contract):
            return kind, identity_field, getattr(value, identity_field)
    raise StoreError(f"unsupported record type {type(value).__name__}")


def _record_wrapper(kind: str, value: RecordValue) -> dict[str, Any]:
    return {"record": value.as_dict(), "record_type": kind}


class RunStore:
    """Single-writer store rooted at one project's `conductor/runs` directory."""

    def __init__(self, project_root: str | os.PathLike[str]) -> None:
        self.project_root = Path(project_root).resolve()
        self.runs_root = self.project_root / "conductor" / "runs"

    def run_path(self, run_id: str) -> Path:
        try:
            safe = _id("run_id", run_id)
        except ContractError as e:
            raise StoreError(str(e)) from e
        return self.runs_root / safe

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

    def append(self, value: RecordValue) -> bool:
        """Append one immutable record; return False for an identical retry."""
        kind, identity_field, identity = _record_parts(value)
        run_id = value.run_id
        recovered = self.recover(run_id)
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

    def recover(self, run_id: str) -> RecoveredRun:
        """Validate the frozen run and replay its durable journal."""
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

        records, warnings = self._read_journal(root / "records.jsonl", run_id)
        records, decision_warnings = self._reconcile_decisions(root, run_id, records)
        self._validate_records(envelope, records)
        return RecoveredRun(
            envelope=envelope,
            config=_freeze_json(config),
            records=tuple(records),
            warnings=tuple((*warnings, *decision_warnings)),
        )

    def _read_journal(
            self, path: Path, run_id: str) -> tuple[list[StoredRecord], list[str]]:
        try:
            payload = path.read_bytes()
        except OSError as e:
            raise CorruptRun(f"records.jsonl is unreadable: {e}") from e
        warnings: list[str] = []
        complete = payload
        if payload and not payload.endswith(b"\n"):
            cut = payload.rfind(b"\n") + 1
            complete = payload[:cut]
            try:
                _replace_bytes(path, complete)
            except OSError as e:
                raise CorruptRun(f"cannot remove incomplete records.jsonl tail: {e}") from e
            warnings.append(
                "records.jsonl ended with an incomplete record; the incomplete tail was ignored")

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
        if isinstance(value, ActionResultReceipt):
            action = next((row.value for row in recovered.records
                           if isinstance(row.value, ActionRequest)
                           and row.value.action_id == value.action_id), None)
            if action is None:
                raise StoreError(f"action result names unknown action {value.action_id!r}")
            for field in ("attempt_id", "instance_id"):
                if getattr(action, field) != getattr(value, field):
                    raise StoreError(
                        f"action result {field} does not match action {value.action_id!r}")
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
    def _validate_records(cls, envelope: RunEnvelope, records: list[StoredRecord]) -> None:
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
                envelope=envelope, config=MappingProxyType({}),
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
            self, root: Path, run_id: str, records: list[StoredRecord],
    ) -> tuple[list[StoredRecord], list[str]]:
        decisions = root / "decisions"
        if not decisions.is_dir():
            raise CorruptRun("decisions directory is missing")
        by_id = {
            row.value.receipt_id: row
            for row in records if isinstance(row.value, DecisionReceipt)
        }
        warnings: list[str] = []
        for path in sorted(decisions.glob("*.json"), key=lambda item: item.name):
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
            try:
                _append_bytes(root / "records.jsonl", _canonical_bytes(wrapper))
            except OSError as e:
                raise CorruptRun(
                    f"cannot recover decision receipt {decision.receipt_id!r}: {e}") from e
            row = StoredRecord("decision", decision)
            records.append(row)
            by_id[decision.receipt_id] = row
            warnings.append(
                f"decision receipt {decision.receipt_id!r} survived without its journal line; "
                "the line was recovered")
        journal_ids = set(by_id)
        file_ids = {path.stem for path in decisions.glob("*.json")}
        missing = sorted(journal_ids - file_ids)
        if missing:
            raise CorruptRun(f"decision receipts missing exclusive files: {missing}")
        return records, warnings
