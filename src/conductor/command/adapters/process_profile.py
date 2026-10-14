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
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def refusal_summary(failures: list) -> Exception:
    """The error of a step that did several things: one failure as it is, several as one refusal.

    The refusal carries the code of the first refusal among them, and names every failure.
    """
    if len(failures) == 1:
        return failures[0]
    parts = [f"[{e.code}] {e.detail}" if isinstance(e, ProfileRefused) else f"[{type(e).__name__}]"
             for e in failures]
    code = next((e.code for e in failures if isinstance(e, ProfileRefused)), "profile_acl_invalid")
    return ProfileRefused(code, "; ".join(parts))


def _attempt(failures: list, step, *args, **options) -> bool:
    """Run one recovery step; its error is kept for the end. True when it ended clean."""
    try:
        step(*args, **options)
    except (ProfileRefused, OSError) as error:
        failures.append(error)
        return False
    return True


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
        found = cls(ownership.data_root(root), owner_nonce=head["nonce"],
                   root_identity=head["root_identity"], data_identity=head["data_identity"],
                   derive=native.derive_profile_sid, create=native.create_profile,
                   inspect=native.inspect_profile, delete=native.delete_profile)
        found.native, found.owner_root = native, root
        return found

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
        self.native, self.owner_root = None, None

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
        try:
            canonical = _bytes(value)
        except (TypeError, ValueError) as error:
            raise ProfileRefused("profile_record_invalid", "profile record is malformed") from error
        match = _NAME.fullmatch(path.name)
        if (type(value) is not dict or raw != canonical or set(value) != _FIELDS
                or type(value["schema"]) is not int or value["schema"] != 1
                or not match or value["attempt"] != match.group(1)
                or value["owner_nonce"] != self.owner_nonce
                or value["root_identity"] != self.root_identity
                or value["data_identity"] != self.data_identity
                or type(value["phase"]) is not str or value["phase"] not in _PHASES
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

    def recover(self, *, abandon_loans: bool = False) -> None:
        """Return the loans, retire the attempts and delete the profiles a crash left.

        The loans are recovered apart from the rest: a loan is returned without any restart proof,
        so what stops it must not stop the fresh folders or the profiles, and what stops those must
        not keep a loan out. The profiles wait for the same restart proof as the fresh folders. The
        errors of what ran are raised together, at the end.

        Args:
            abandon_loans: The owner gives up a loan whose folder is no longer the one it granted
                (`FolderLoans.restore`).
        """
        self._directory()
        from .process_acl import AttemptAclJournal, _ACL_NAME, _ACL_PREP, _ACL_TEMP
        from .process_loans import FolderLoans, _LOAN_NAME, _LOAN_TEMP
        failures: list = []
        if self.native is not None:
            _attempt(failures, FolderLoans(self, self.native).recover, abandon=abandon_loans)
            if not _attempt(failures, AttemptAclJournal(self, self.native).recover):
                raise refusal_summary(failures)
        for path in sorted(self.directory.iterdir()):
            if self.native is not None and (_ACL_NAME.fullmatch(path.name)
                                            or _ACL_PREP.fullmatch(path.name)
                                            or _ACL_TEMP.fullmatch(path.name)
                                            or _LOAN_NAME.fullmatch(path.name)
                                            or _LOAN_TEMP.fullmatch(path.name)):
                continue
            if _TEMP.fullmatch(path.name):
                _plain(path, False)
                path.unlink()  # stale atomic-replace scratch, not an OS profile
                continue
            if not _NAME.fullmatch(path.name):
                raise ProfileRefused("profile_record_invalid", "unexpected profile journal entry")
            _attempt(failures, self.retire, path)
        if failures:
            raise refusal_summary(failures)

    def prepare_restarts(self) -> list[dict]:
        """The explicit action for attempt loans from before the boot counter: prepare each one.

        Writes one restart preparation per record that needs one and cleans nothing; a recovery
        never does this by itself. Returns one row per record that is not retired.
        """
        from .process_acl import AttemptAclJournal
        if self.native is None:
            return []
        return AttemptAclJournal(self, self.native).prepare_restarts()

    def _loans(self, mode, folders):
        """The loans of a block that names folders, checked before any profile exists."""
        if folders is None:
            return None
        if mode is None or self.native is None:
            raise ProfileRefused("profile_acl_invalid", "loaned folders need an attempt mode")
        from .process_loans import FolderLoans
        loans = FolderLoans(self, self.native)
        loans.targets(folders)
        return loans

    @contextmanager
    def container(self, *, internet_client: bool = False, mode=None, active_tokens=None,
                  folders=None):
        """One AppContainer profile for one attempt, and what the attempt may stand on.

        Args:
            folders: None, or a mapping of `work`, `install` and optionally `home` to existing
                folders (`process_loans`), which are loaned instead of the fresh work and login
                folders. The block then yields `parent`, `runtime` and these, in their real places.
        """
        if mode not in (None, "dispatch", "review"):
            raise ProfileRefused("profile_acl_invalid", "unknown trusted attempt mode")
        loans = self._loans(mode, folders)
        path, sid = self.create_profile()
        acl = None
        try:
            if mode is None:
                yield WindowsContainer(sid, internet_client=internet_client)
            else:
                if self.native is None or active_tokens is None:
                    raise ProfileRefused("profile_acl_invalid", "trusted ACL callbacks are absent")
                from .process_acl import AttemptAclJournal
                acl = AttemptAclJournal(self, self.native)
                _, paths = acl.prepare(path, sid, mode, folders=loans is not None)
                if loans is not None:
                    loans.grant(path, sid, mode, folders)
                    paths = {**paths, **loans.paths}
                yield WindowsContainer(sid, internet_client=internet_client), paths
        finally:
            try:
                if active_tokens is not None and active_tokens():
                    raise ProfileRefused("profile_acl_unproven", "native children still hold attempt loan")
                if self.owner_root is not None:
                    ownership.require_owner(self.owner_root).check()
                if loans is not None:
                    loans.restore()
                if acl is not None:
                    record = acl._record_path(self._read(path)["attempt"])
                    if record.exists():
                        acl.retire(record, proven=True)
                self.retire(path)
            finally:
                if loans is not None:
                    loans.close()
                if acl is not None:
                    acl.close()
