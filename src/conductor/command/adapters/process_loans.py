"""Durable ACL loans on EXISTING product-owned folders of one AppContainer attempt.

`process_acl` makes, grants and deletes FRESH folders. A loan is the other case: the attempt's work
folder, its per-spawn home and the pinned install folder already exist, are not this journal's to
delete, and are returned as they were. Before anything changes a record names each folder, its
identity and its DACL; the grant adds entries for the attempt's profile only (explicit rights, never
Full Control, never WRITE_DAC or DELETE_CHILD, never a deny); the exit puts the DACL back, which
also takes the profile's inherited entries away from everything the attempt touched beneath it.

The hold of a loaned folder asks for WRITE_DAC and NOT for DELETE. Measured 13.10.2026: with DELETE
in the hold, setting a DACL on the folder does not propagate an inheritable entry to its existing
children, nor take it away again, and reports success; without DELETE it does both.

The leased login home is not a loan (it waits for a ruling), and nothing here widens an ACL beyond
the three kinds of folder `AttemptFolders` names.
"""
from __future__ import annotations

import json
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path

from ...ownership_native import NativeHold
from ...ownership_records import ACTIVE, HOME, LEGACY
from ..work_layout import WORK_DIR
from .process_acl import _CHILD_RWX_DELETE, _RWX, _RX
from .process_boundary import WindowsContainer
from .process_profile import ProfileRefused, _bytes, _plain, _replace, _write_new

_LOAN_NAME = re.compile(r"loan-([0-9a-f]{32})\.json\Z")
_LOAN_TEMP = re.compile(r"\.loan-[0-9a-f]{32}\.json\.[0-9a-f]{16}\.tmp\Z")
_KEYS = ("work", "home", "install")
_DACL = re.compile(r"(O:[^()]*?D:[A-Z]*)((?:\([^()]*\))*)")
_ACE = re.compile(r"\([^()]*\)")
#: Where no folder of an attempt may lie: the owner's repository (at any depth) and, at the top of
#: the project, the product's own data.
_REPOSITORY = ".git"
_PRODUCT_TOP = (ACTIVE, LEGACY, HOME)
_LIMIT = 16384
_FIELDS = frozenset({"schema", "attempt", "owner_nonce", "root_identity", "data_identity",
                     "profile_sid", "mode", "phase", "loans"})
_FACTS = frozenset({"path", "rights", "identity", "before", "protected", "owner_sid"})


def _refused(detail: str) -> ProfileRefused:
    return ProfileRefused("profile_acl_invalid", detail)


def _entries(sid: str, rights: str) -> str:
    if rights == "rx":
        return f"(A;OICI;0x{_RX:x};;;{sid})"
    return f"(A;;0x{_RWX:x};;;{sid})(A;OICIIO;0x{_CHILD_RWX_DELETE:x};;;{sid})"


def _explicit_deny(ace: str) -> bool:
    fields = ace[1:-1].split(";")
    return fields[0] in ("D", "OD") and "ID" not in re.findall(r"..", fields[1])


def loan_sddl(before: str, sid: str, rights: str) -> str:
    """`before` plus the entries of one profile, after any explicit deny and before the rest.

    Args:
        before: The DACL text the native read gave (`O:...D:flags(ace)...`).
        sid: The attempt's AppContainer profile SID.
        rights: `modify` (read, write, create, traverse on the folder, and those plus DELETE on what
            is inside it) or `rx` (read and execute, inheritable).

    Raises:
        ProfileRefused: `profile_acl_invalid` for text this does not understand (a security
            descriptor with a group or an audit part, a conditional entry, unbalanced brackets) or
            an unknown right. Nothing is guessed.
    """
    found = _DACL.fullmatch(before) if type(before) is str else None
    if found is None or rights not in ("modify", "rx"):
        raise _refused("the DACL text of a loaned folder is not understood")
    head, body = found.groups()
    aces = _ACE.findall(body)
    split = 0
    while split < len(aces) and _explicit_deny(aces[split]):
        split += 1
    return head + "".join(aces[:split]) + _entries(sid, rights) + "".join(aces[split:])


def _inside(path: Path, parent: Path) -> bool:
    """Whether `path` is `parent` or lies beneath it, by components (Windows folds case)."""
    return path == parent or parent in path.parents


def _plain_directory(path: Path) -> Path:
    """The real location of an existing directory that is neither a link nor another portal."""
    if not path.is_absolute() or os.pardir in path.parts:
        raise _refused("a loaned folder is not an absolute, normal path")
    try:
        found = os.lstat(path)
    except OSError as error:
        raise _refused("a loaned folder cannot be read") from error
    if (not stat.S_ISDIR(found.st_mode) or stat.S_ISLNK(found.st_mode)
            or getattr(found, "st_reparse_tag", 0)):
        raise _refused("a loaned folder is not a plain directory")
    return Path(os.path.realpath(path))


def _system_places(environ) -> list[Path]:
    names = ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")
    return [Path(os.path.realpath(environ[name])) for name in names if environ.get(name)]


def _refuse_install(install: Path, root: Path, environ) -> None:
    """The pinned install folder: never the project, the user's profile, or a system program."""
    if _inside(root, install) or _inside(install, root):
        raise _refused("the install folder overlaps the project")
    profile = environ.get("USERPROFILE")
    if profile and _inside(Path(os.path.realpath(profile)), install):
        raise _refused("the install folder is the user profile or contains it")
    for place in _system_places(environ):
        if _inside(install, place) or _inside(place, install):
            raise _refused("the install folder is a system program folder or contains one")


def _refuse_attempt_folder(name: str, path: Path, root: Path) -> None:
    """The work folder and the home: beneath the project, away from its repository and its data."""
    if root not in path.parents:
        raise _refused(f"the {name} folder is not beneath the project")
    route = path.relative_to(root).parts
    if (any(part.casefold() == _REPOSITORY for part in route)
            or route[0].casefold() in _PRODUCT_TOP):
        raise _refused(f"the {name} folder lies in the owner's repository or the product's data")
    if name == "work" and (len(route) < 2 or route[0] != WORK_DIR):
        raise _refused("the work folder is not a folder of the work tree")


class FolderLoans:
    """The loans of one attempt, journalled in `loan-<attempt>.json` beside its profile record."""

    def __init__(self, profiles, native, *, hold_factory=NativeHold, environ=None):
        self.profiles, self.native = profiles, native
        self.directory = profiles.directory
        self.hold_factory = hold_factory
        self.environ = os.environ if environ is None else environ
        self.record, self.holds, self.paths = None, None, {}

    def targets(self, folders) -> dict[str, Path]:
        """The folders of a loan, checked and in their real places; nothing is held or changed.

        Raises:
            ProfileRefused: `profile_acl_invalid` for a missing or foreign key, a folder that is not
                a plain directory, one that overlaps another, or one the rules above forbid.
        """
        if self.profiles.owner_root is None:
            raise _refused("trusted ACL callbacks are absent")
        if (type(folders) is not dict or not set(folders) <= set(_KEYS)
                or not {"work", "install"} <= set(folders)):
            raise _refused("a loan names a work folder, an install folder and at most a home")
        root = Path(os.path.realpath(self.profiles.owner_root))
        real = {key: _plain_directory(Path(path)) for key, path in folders.items()}
        for name in ("work", "home"):
            if name in real:
                _refuse_attempt_folder(name, real[name], root)
        _refuse_install(real["install"], root, self.environ)
        home, work = real.get("home"), real["work"]
        if home is not None and (_inside(home, work) or _inside(work, home)):
            raise _refused("the home and the work folder overlap")
        return real

    def grant(self, profile_path, sid, mode, folders) -> Path:
        """Journal every folder's prior DACL and identity, then add the profile's entries.

        Returns:
            The record's path. `restore()` returns the loan, also after a failure part way.
        """
        profile = self.profiles._read(profile_path)
        if (profile["phase"] != "created" or profile["sid"] != sid
                or mode not in {"dispatch", "review"}):
            raise _refused("ACL target is not a created owned profile")
        real = self.targets(folders)
        self.paths = real
        stack, holds, rows = ExitStack(), {}, {}
        try:
            for key, path in real.items():
                hold = self.hold_factory(path, directory=True, grants=True)
                stack.callback(hold.close)
                holds[key] = hold
                before, protected, owner_sid = self.native.acl_snapshot(hold)
                rows[key] = {"path": str(path), "rights": self._rights(key, mode),
                             "identity": list(hold.identity), "before": before,
                             "protected": protected, "owner_sid": owner_sid}
        except BaseException:
            stack.close()
            raise
        self.holds = stack, holds
        record = {"schema": 1, "attempt": profile["attempt"],
                  "owner_nonce": self.profiles.owner_nonce,
                  "root_identity": self.profiles.root_identity,
                  "data_identity": self.profiles.data_identity, "profile_sid": sid, "mode": mode,
                  "phase": "planned", "loans": rows}
        self.record = self.directory / f"loan-{profile['attempt']}.json"
        _write_new(self.record, record)  # every prior DACL durable before the first change
        for key, hold in holds.items():
            proposed = loan_sddl(rows[key]["before"], sid, rows[key]["rights"])
            self.native.acl_set(hold, proposed, protected=rows[key]["protected"])
            readback, protected, owner_sid = self.native.acl_snapshot(hold)
            if (protected != rows[key]["protected"] or owner_sid != rows[key]["owner_sid"]
                    or not self.native.acl_equal(readback, proposed)):
                raise _refused("native ACL readback differs from the loan")
        record["phase"] = "applied"
        _replace(self.record, record)
        return self.record

    @staticmethod
    def _rights(key: str, mode: str) -> str:
        """Install is read-and-execute; work is modify in a dispatch and read-only in a review;
        a home is the vendor's own state and is written in both."""
        return "rx" if key == "install" or (key == "work" and mode == "review") else "modify"

    def close(self) -> None:
        if self.holds is not None:
            self.holds[0].close()
            self.holds = None

    def _read(self, path: Path) -> dict:
        if path.parent != self.directory or not _LOAN_NAME.fullmatch(path.name):
            raise _refused("loan record escaped the owned journal")
        _plain(path, False)
        with path.open("rb") as stream:
            raw = stream.read(_LIMIT + 1)
        if len(raw) > _LIMIT:
            raise _refused("loan record exceeds its bound")
        try:
            row = json.loads(raw.decode("utf-8"))
            canonical = _bytes(row)
        except (UnicodeError, ValueError, TypeError) as error:
            raise _refused("loan record is malformed") from error
        if (type(row) is not dict or raw != canonical or set(row) != _FIELDS
                or row["schema"] != 1 or type(row["schema"]) is not int
                or row["attempt"] != _LOAN_NAME.fullmatch(path.name).group(1)
                or row["owner_nonce"] != self.profiles.owner_nonce
                or row["root_identity"] != self.profiles.root_identity
                or row["data_identity"] != self.profiles.data_identity
                or row["phase"] not in {"planned", "applied", "retired"}
                or row["mode"] not in {"dispatch", "review"}
                or type(row["loans"]) is not dict or not {"work", "install"} <= set(row["loans"])
                or not set(row["loans"]) <= set(_KEYS)):
            raise _refused("loan record does not bind this owner")
        try:
            WindowsContainer(row["profile_sid"])
        except ValueError as error:
            raise _refused("loan SID is malformed") from error
        for key, facts in row["loans"].items():
            if (type(facts) is not dict or set(facts) != _FACTS
                    or type(facts["path"]) is not str or facts["rights"] not in ("modify", "rx")
                    or type(facts["identity"]) is not list or len(facts["identity"]) != 2
                    or any(type(x) is not int or x < 0 for x in facts["identity"])
                    or type(facts["before"]) is not str or type(facts["protected"]) is not bool
                    or type(facts["owner_sid"]) is not str):
                raise _refused(f"loan facts for {key} are malformed")
        return row

    def _reopen(self, record) -> tuple[ExitStack, dict]:
        """Hold each loaned folder that still exists, proven to be the one that was granted."""
        stack, holds = ExitStack(), {}
        try:
            for key, facts in record["loans"].items():
                if not os.path.lexists(facts["path"]):
                    continue  # gone with its entries: nothing at this name can hold a grant
                hold = self.hold_factory(Path(facts["path"]), directory=True, grants=True)
                stack.callback(hold.close)
                if list(hold.identity) != facts["identity"]:
                    raise _refused("a loaned folder is not the one the record names")
                holds[key] = hold
            return stack, holds
        except BaseException:
            stack.close()
            raise

    def _give_back(self, hold, facts) -> None:
        self.native.acl_set(hold, facts["before"], protected=facts["protected"])
        restored, protected, owner_sid = self.native.acl_snapshot(hold)
        if (protected != facts["protected"] or owner_sid != facts["owner_sid"]
                or not self.native.acl_equal(restored, facts["before"])):
            raise _refused("native ACL restore readback differs")

    def restore(self, record_path: Path | None = None) -> None:
        """Put every loaned folder's DACL back and retire the record.

        Every folder is tried; the first refusal is raised after the others were returned, and the
        record then stays `applied` for the recovery. A folder that no longer exists has nothing to
        return; one that exists but is another folder than the record names is left untouched.

        Raises:
            ProfileRefused: `profile_acl_invalid` for a folder that is not the one granted, or
                whose restored DACL reads back different.
        """
        record_path = record_path or self.record
        if record_path is None:
            return
        record = self._read(record_path)
        if record["phase"] == "retired":
            return
        holds = self.holds[1] if self.holds is not None and record_path == self.record else None
        stack = None
        if holds is None:
            stack, holds = self._reopen(record)
        try:
            failures = []
            for key, facts in record["loans"].items():
                if key in holds:
                    try:
                        self._give_back(holds[key], facts)
                    except (ProfileRefused, OSError) as error:
                        failures.append(error)
            if failures:
                raise failures[0]
        finally:
            if stack is not None:
                stack.close()
            self.close()
        record["phase"] = "retired"
        _replace(record_path, record)

    def recover(self) -> None:
        """Return every loan a crash left: scratch of an interrupted replace is removed first."""
        if not self.directory.exists():
            return
        for path in sorted(self.directory.iterdir()):
            if _LOAN_TEMP.fullmatch(path.name):
                _plain(path, False)
                path.unlink()
        failures = []
        for path in sorted(p for p in self.directory.iterdir() if _LOAN_NAME.fullmatch(p.name)):
            try:
                self.restore(path)
            except (ProfileRefused, OSError) as error:
                failures.append(error)
        if failures:
            raise failures[0]
