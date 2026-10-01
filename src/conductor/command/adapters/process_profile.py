"""Journal of AppContainer profiles owned by one activated project.

This module has no OS profile API. The runner supplies the four native callbacks;
the journal never infers ownership from a SID alone or searches installed profiles.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
import re
import secrets
import stat

from ... import ownership
from ...ownership_records import state
from .process_boundary import WindowsContainer


_NAME = re.compile(r"profile-([0-9a-f]{32})\.json\Z")
_TEMP = re.compile(r"\.profile-[0-9a-f]{32}\.json\.[0-9a-f]{16}\.tmp\Z")
_FIELDS = frozenset({"schema", "attempt", "owner_nonce", "root_identity",
                     "data_identity", "moniker", "display", "sid", "phase"})
_PHASES = frozenset({"planned", "created", "retired"})


class ProfileRefused(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def _plain(path: Path, directory: bool) -> None:
    found = os.lstat(path)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(found.st_mode) or stat.S_ISLNK(found.st_mode)
            or getattr(found, "st_reparse_tag", 0)
            or (not directory and found.st_nlink != 1)):
        raise ProfileRefused("profile_record_invalid", "profile journal route is not plain")


def _bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _write_new(path: Path, value: dict) -> None:
    with open(path, "xb") as out:
        out.write(_bytes(value))
        out.flush()
        os.fsync(out.fileno())
    _sync_directory(path.parent)


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _replace(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        _write_new(temporary, value)
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


class ProfileJournal:
    """Bound to a caller-verified project root, data identity and owner nonce."""

    @classmethod
    def for_project(cls, project_root, native):
        root, head = state(project_root)
        if head is None or head["phase"] != "opened":
            raise ProfileRefused("profile_owner_required", "project owner is not opened")
        ownership.require_owner(root)
        return cls(ownership.data_root(root), owner_nonce=head["nonce"],
                   root_identity=head["root_identity"], data_identity=head["data_identity"],
                   derive=native.derive_profile_sid, create=native.create_profile,
                   inspect=native.inspect_profile, delete=native.delete_profile)

    def __init__(self, data_root: Path, *, owner_nonce: str, root_identity,
                 data_identity, derive, create, inspect, delete):
        if not re.fullmatch(r"[0-9a-f]{32}", owner_nonce):
            raise ProfileRefused("profile_owner_invalid", "owner nonce is invalid")
        self.directory = Path(data_root) / "process-profiles"
        self.owner_nonce = owner_nonce
        self.root_identity = list(root_identity)
        self.data_identity = list(data_identity)
        self.derive, self.create = derive, create
        self.inspect, self.delete = inspect, delete

    def _directory(self) -> None:
        _plain(self.directory.parent, True)
        try:
            self.directory.mkdir()
        except FileExistsError:
            pass
        _plain(self.directory, True)

    def _read(self, path: Path) -> dict:
        if path.parent != self.directory:
            raise ProfileRefused("profile_record_invalid", "profile record is outside owned journal")
        _plain(path, False)
        with path.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ProfileRefused("profile_record_invalid", "profile record exceeds limit")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise ProfileRefused("profile_record_invalid", "profile record is malformed") from error
        match = _NAME.fullmatch(path.name)
        if (type(value) is not dict or set(value) != _FIELDS
                or type(value["schema"]) is not int or value["schema"] != 1
                or not match or value["attempt"] != match.group(1)
                or value["owner_nonce"] != self.owner_nonce
                or value["root_identity"] != self.root_identity
                or value["data_identity"] != self.data_identity
                or value["phase"] not in _PHASES
                or value["moniker"] != f"conduct-{self.owner_nonce[:12]}-{value['attempt']}"
                or value["display"] != f"Conduct owned profile {self.owner_nonce}:{value['attempt']}"
                or type(value["sid"]) is not str):
            raise ProfileRefused("profile_record_invalid", "profile record does not bind this owner")
        return value

    def plan(self) -> tuple[Path, dict]:
        self._directory()
        attempt = secrets.token_hex(16)
        moniker = f"conduct-{self.owner_nonce[:12]}-{attempt}"
        display = f"Conduct owned profile {self.owner_nonce}:{attempt}"
        sid = self.derive(moniker)
        value = {"schema": 1, "attempt": attempt, "owner_nonce": self.owner_nonce,
                 "root_identity": self.root_identity, "data_identity": self.data_identity,
                 "moniker": moniker, "display": display, "sid": sid, "phase": "planned"}
        path = self.directory / f"profile-{attempt}.json"
        _write_new(path, value)  # durable evidence before any OS mutation
        return path, value

    def create_profile(self) -> tuple[Path, str]:
        path, value = self.plan()
        if self.inspect(value["sid"]) is not None:
            raise ProfileRefused("profile_conflict", "planned profile name already exists")
        created_sid = self.create(value["moniker"], value["display"])
        if created_sid != value["sid"]:
            raise ProfileRefused("profile_ambiguous", "created profile SID differs from plan")
        value["phase"] = "created"
        _replace(path, value)
        return path, created_sid

    def retire(self, path: Path) -> None:
        value = self._read(path)
        if value["phase"] == "retired":
            return
        if self.derive(value["moniker"]) != value["sid"]:
            raise ProfileRefused("profile_ambiguous", "derived profile SID changed")
        mapping = self.inspect(value["sid"])
        if mapping is not None and mapping != (value["moniker"], value["display"]):
            raise ProfileRefused("profile_ambiguous", "profile mapping does not prove ownership")
        if mapping == (value["moniker"], value["display"]):
            self.delete(value["moniker"])
        value["phase"] = "retired"
        _replace(path, value)

    def recover(self) -> None:
        self._directory()
        for path in sorted(self.directory.iterdir()):
            if _TEMP.fullmatch(path.name):
                _plain(path, False)
                path.unlink()  # stale atomic-replace scratch, not an OS profile
                continue
            if not _NAME.fullmatch(path.name):
                raise ProfileRefused("profile_record_invalid", "unexpected profile journal entry")
            self.retire(path)

    @contextmanager
    def container(self, *, internet_client: bool = False):
        path, sid = self.create_profile()
        try:
            yield WindowsContainer(sid, internet_client=internet_client)
        finally:
            self.retire(path)
