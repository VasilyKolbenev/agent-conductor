"""Durable ACL loans on EXISTING product-owned folders of one AppContainer attempt.

`process_acl` makes, grants and deletes FRESH folders. A loan is the other case: the attempt's work
folder, its per-spawn home and the pinned install folder already exist, are not this journal's to
delete, and are given back. Before anything changes a record names each folder, its identity and
its DACL; the grant adds entries for the attempt's profile only (explicit rights, never Full
Control, never WRITE_DAC or DELETE_CHILD, never a deny); the exit takes those entries away again,
which also takes the profile's inherited entries away from everything the attempt touched beneath
the folder.

A loan is returned by taking away ITS OWN entries from the DACL as it stands at the exit, never by
writing back the DACL that was read at the start. The pinned install folder is shared by every
attempt of a harness and by every project: a written-back DACL would give the entry of an attempt
that still runs away at the first exit, and would keep the entry of a finished one at the last.
The record keeps the prior DACL as evidence of what the folder was.

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
from .process_profile import ProfileRefused, _bytes, _plain, _replace, refusal_summary

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
_PHASES = frozenset({"planned", "applied", "retired", "abandoned"})
#: A record in one of these is finished: it is never acted on again.
_DONE = ("retired", "abandoned")


def _refused(detail: str) -> ProfileRefused:
    return ProfileRefused("profile_acl_invalid", detail)


def _entries(sid: str, rights: str) -> str:
    if rights == "rx":
        return f"(A;OICI;0x{_RX:x};;;{sid})"
    return f"(A;;0x{_RWX:x};;;{sid})(A;OICIIO;0x{_CHILD_RWX_DELETE:x};;;{sid})"


def _fields(ace: str) -> list[str]:
    """The six parts of one entry (type, flags, rights, two object ids, trustee)."""
    return ace[1:-1].split(";")


def _explicit(fields: list[str]) -> bool:
    return "ID" not in re.findall(r"..", fields[1])


def _explicit_deny(ace: str) -> bool:
    fields = _fields(ace)
    return len(fields) == 6 and fields[0] in ("D", "OD") and _explicit(fields)


def _entry_of(ace: str, sid: str) -> bool:
    """An explicit entry of one profile: what a loan adds, never what a parent hands down."""
    fields = _fields(ace)
    return len(fields) == 6 and fields[5] == sid and _explicit(fields)


def _split(text: str) -> tuple[str, list[str]]:
    found = _DACL.fullmatch(text) if type(text) is str else None
    if found is None:
        raise _refused("the DACL text of a loaned folder is not understood")
    head, body = found.groups()
    return head, _ACE.findall(body)


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
    if rights not in ("modify", "rx"):
        raise _refused("the DACL text of a loaned folder is not understood")
    head, aces = _split(before)
    split = 0
    while split < len(aces) and _explicit_deny(aces[split]):
        split += 1
    return head + "".join(aces[:split]) + _entries(sid, rights) + "".join(aces[split:])


def loan_returned_sddl(current: str, sid: str) -> str:
    """`current` without the explicit entries of one profile: what the return of a loan writes.

    Whatever else the DACL holds stays, including an entry another attempt or the owner added
    since the grant.

    Raises:
        ProfileRefused: `profile_acl_invalid` for text this does not understand.
    """
    head, aces = _split(current)
    return head + "".join(ace for ace in aces if not _entry_of(ace, sid))


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
        stack, holds, rows = self._observe(real, mode)
        self.holds = stack, holds
        record = {"schema": 1, "attempt": profile["attempt"],
                  "owner_nonce": self.profiles.owner_nonce,
                  "root_identity": self.profiles.root_identity,
                  "data_identity": self.profiles.data_identity, "profile_sid": sid, "mode": mode,
                  "phase": "planned", "loans": rows}
        path = self.directory / f"loan-{profile['attempt']}.json"
        _replace(path, record)  # every prior DACL durable before the first change, all or nothing
        self.record = path
        for key, hold in holds.items():
            self._change(hold, lambda now, rights=rows[key]["rights"]: loan_sddl(now, sid, rights))
        record["phase"] = "applied"
        _replace(self.record, record)
        return self.record

    def _observe(self, real, mode):
        """Hold every folder and note what it was; nothing is changed."""
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
        return stack, holds, rows

    def _change(self, hold, build) -> None:
        """Set the DACL `build` makes from the one the folder has NOW, and read it back.

        Read just before the write, so an entry another attempt or the owner added since the record
        was made stays. Protection and owner are kept as found.
        """
        current, protected, owner_sid = self.native.acl_snapshot(hold)
        proposed = build(current)
        self.native.acl_set(hold, proposed, protected=protected)
        readback, now_protected, now_owner = self.native.acl_snapshot(hold)
        if (now_protected != protected or now_owner != owner_sid
                or not self.native.acl_equal(readback, proposed)):
            raise _refused("native ACL readback differs from the change")

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
                or row["phase"] not in _PHASES
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

    def _reopen(self, record):
        """Hold each loaned folder that still exists and is the one that was granted.

        Returns the stack of holds, the holds by key, the keys of folders that exist but are another
        folder than the record names (left untouched), and the errors of folders that could not be
        opened. None of them keeps the others from being held.
        """
        stack, holds, strays, failures = ExitStack(), {}, [], []
        try:
            for key, facts in record["loans"].items():
                if not os.path.lexists(facts["path"]):
                    continue  # gone with its entries: nothing at this name can hold a grant
                try:
                    hold = self.hold_factory(Path(facts["path"]), directory=True, grants=True)
                except OSError as error:
                    failures.append(error)
                    continue
                stack.callback(hold.close)
                if list(hold.identity) == facts["identity"]:
                    holds[key] = hold
                else:
                    strays.append(key)
            return stack, holds, strays, failures
        except BaseException:
            stack.close()
            raise

    def _give_back(self, holds, record) -> list:
        """Take the profile's entries off every held folder; the errors of those that failed."""
        sid, failures = record["profile_sid"], []
        for key in record["loans"]:
            if key in holds:
                try:
                    self._change(holds[key], lambda now: loan_returned_sddl(now, sid))
                except (ProfileRefused, OSError) as error:
                    failures.append(error)
        return failures

    def restore(self, record_path: Path | None = None, *, abandon: bool = False) -> None:
        """Take the profile's entries off every loaned folder and retire the record.

        Every folder is tried. One that no longer exists has nothing to return. One that exists but
        is another folder than the record names is left untouched and the record stays `applied`,
        named again by every recovery, until the owner gives it up: with `abandon` the record ends
        `abandoned` instead. A folder that could not be returned is never given up.

        Raises:
            ProfileRefused: `profile_acl_invalid` for a folder that is not the one granted, or
                whose changed DACL reads back different. An error of the OS passes as it is.
        """
        record_path = record_path or self.record
        if record_path is None:
            return
        record = self._read(record_path)
        if record["phase"] in _DONE:
            return
        live = self.holds[1] if self.holds is not None and record_path == self.record else None
        stack, strays, failures = None, [], []
        holds = live
        if live is None:
            stack, holds, strays, failures = self._reopen(record)
        try:
            failures += self._give_back(holds, record)
        finally:
            if stack is not None:
                stack.close()
            self.close()
        if strays and not abandon:
            failures += [_refused(f"the {key} folder is not the one the record names")
                         for key in strays]
        if failures:
            raise refusal_summary(failures)
        record["phase"] = "abandoned" if strays else "retired"
        _replace(record_path, record)

    def recover(self, *, abandon: bool = False) -> None:
        """Return every loan a crash left: scratch of an interrupted replace is removed first.

        Every record is tried, and the errors are raised together at the end.
        """
        if not self.directory.exists():
            return
        for path in sorted(self.directory.iterdir()):
            if _LOAN_TEMP.fullmatch(path.name):
                _plain(path, False)
                path.unlink()
        failures = []
        for path in sorted(p for p in self.directory.iterdir() if _LOAN_NAME.fullmatch(p.name)):
            try:
                self.restore(path, abandon=abandon)
            except (ProfileRefused, OSError) as error:
                failures.append(error)
        if failures:
            raise refusal_summary(failures)
