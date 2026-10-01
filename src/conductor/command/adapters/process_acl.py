"""Durable ACL loan for three new, product-owned AppContainer attempt directories.

No caller-supplied path is accepted. Native security calls arrive only through
callbacks injected by the trusted runner; this module never launches a process.
"""
from __future__ import annotations

import json
import os
from contextlib import ExitStack
from pathlib import Path
import re
import stat

from ...ownership_native import NativeHold, boot_identity, identity
from .process_boundary import WindowsContainer
from .process_profile import ProfileRefused, _bytes, _plain, _replace, _write_new


_ACL_NAME = re.compile(r"acl-([0-9a-f]{32})\.json\Z")
_ACL_TEMP = re.compile(r"\.acl-[0-9a-f]{32}\.json\.[0-9a-f]{16}\.tmp\Z")
_RX = 0x1200A9
_RWX = 0x1201BF  # read + create/write/traverse, no DELETE or DELETE_CHILD
_CHILD_RWX_DELETE = 0x1301BF  # inheritable child rights; no DELETE_CHILD/WRITE_DAC
_LIMIT = 5000


def _grant(owner_sid, profile_sid, *, mode, leaf):
    if mode not in {"dispatch", "review"} or leaf not in {"parent", "work", "runtime", "login"}:
        raise ProfileRefused("profile_acl_invalid", "unknown ACL mode or leaf")
    base = f"O:{owner_sid}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{owner_sid})"
    if leaf == "parent":
        return base
    if leaf == "login" or (mode == "review" and leaf == "work"):
        return base + f"(A;OICI;0x{_RX:x};;;{profile_sid})"
    return (base + f"(A;;0x{_RWX:x};;;{profile_sid})"
            + f"(A;OICIIO;0x{_CHILD_RWX_DELETE:x};;;{profile_sid})")


def _walk_plain(directory: Path) -> list[Path]:
    """Inspect only the owned subtree, bounded, with no traversal through portals."""
    pending, seen = [directory], []
    while pending:
        here = pending.pop()
        _plain(here, True)
        seen.append(here)
        if len(seen) > _LIMIT:
            raise ProfileRefused("profile_acl_invalid", "owned attempt exceeds cleanup bound")
        try:
            with os.scandir(here) as children:
                for entry in children:
                    if len(seen) + len(pending) >= _LIMIT:
                        raise ProfileRefused("profile_acl_invalid", "owned attempt exceeds cleanup bound")
                    found = os.lstat(entry.path)
                    if (stat.S_ISLNK(found.st_mode) or getattr(found, "st_reparse_tag", 0)
                            or not (stat.S_ISDIR(found.st_mode) or stat.S_ISREG(found.st_mode))
                            or (stat.S_ISREG(found.st_mode) and found.st_nlink != 1)):
                        raise ProfileRefused("profile_acl_invalid", "owned attempt contains a portal or irregular entry")
                    if stat.S_ISDIR(found.st_mode):
                        pending.append(Path(entry.path))
                    else:
                        seen.append(Path(entry.path))
        except OSError as error:
            raise ProfileRefused("profile_acl_invalid", "owned attempt is unreadable") from error
    return seen


class AttemptAclJournal:
    """One ACL record bound to the ProfileJournal's immutable attempt identity."""

    def __init__(self, profiles, native, *, hold_factory=NativeHold):
        self.profiles, self.native = profiles, native
        self.directory = profiles.directory
        self.base = self.directory.parent / "container-attempts"
        self.hold_factory, self.holds = hold_factory, None

    def _hold_paths(self, paths):
        stack, holds = ExitStack(), {}
        try:
            for key, path in paths.items():
                hold = self.hold_factory(path, directory=True, security=True)
                stack.callback(hold.close)
                holds[key] = hold
            return stack, holds
        except BaseException:
            stack.close()
            raise

    def close(self):
        if self.holds is not None:
            self.holds[0].close()
            self.holds = None

    def _record_path(self, attempt):
        return self.directory / f"acl-{attempt}.json"

    def _paths(self, attempt):
        parent = self.base / attempt
        return {"parent": parent, "work": parent / "work", "runtime": parent / "runtime",
                "login": parent / "login"}

    def prepare(self, profile_path, sid, mode):
        profile = self.profiles._read(profile_path)
        if (profile["phase"] != "created" or profile["sid"] != sid
                or mode not in {"dispatch", "review"}):
            raise ProfileRefused("profile_acl_invalid", "ACL target is not a created owned profile")
        self.profiles._directory()
        try:
            self.base.mkdir()
        except FileExistsError:
            pass
        _plain(self.base, True)
        paths = self._paths(profile["attempt"])
        for path in paths.values():
            path.mkdir()  # exclusive: no adoption of a foreign or stale name
            _plain(path, True)
        stack, holds = self._hold_paths(paths)
        self.holds = stack, holds
        rows = {}
        for key, hold in holds.items():
            before, protected, owner_sid = self.native.acl_snapshot(hold)
            rows[key] = {"identity": list(hold.identity), "before": before,
                         "protected": protected, "owner_sid": owner_sid}
        record = {"schema": 1, "attempt": profile["attempt"],
                  "owner_nonce": self.profiles.owner_nonce,
                  "root_identity": self.profiles.root_identity,
                  "data_identity": self.profiles.data_identity,
                  "profile_sid": sid, "mode": mode, "boot": boot_identity(),
                  "phase": "planned", "paths": rows}
        record_path = self._record_path(profile["attempt"])
        _write_new(record_path, record)  # all prior DACLs/identities durable before grant
        for key, hold in holds.items():
            proposed = _grant(rows[key]["owner_sid"], sid, mode=mode, leaf=key)
            self.native.acl_set(hold, proposed, protected=True)
            readback, protected, owner_sid = self.native.acl_snapshot(hold)
            if (not protected or owner_sid != rows[key]["owner_sid"]
                    or not self.native.acl_equal(readback, proposed)):
                raise ProfileRefused("profile_acl_invalid", "native ACL readback differs from grant")
        record["phase"] = "applied"
        _replace(record_path, record)
        return record_path, paths

    def _read(self, path):
        if path.parent != self.directory or not _ACL_NAME.fullmatch(path.name):
            raise ProfileRefused("profile_acl_invalid", "ACL record escaped owned journal")
        _plain(path, False)
        with path.open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ProfileRefused("profile_acl_invalid", "ACL record exceeds bound")
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise ProfileRefused("profile_acl_invalid", "ACL record is malformed") from error
        try:
            canonical = _bytes(row)
        except (TypeError, ValueError) as error:
            raise ProfileRefused("profile_acl_invalid", "ACL record is malformed") from error
        if (type(row) is not dict or raw != canonical
                or set(row) != {"schema", "attempt", "owner_nonce",
                "root_identity", "data_identity", "profile_sid", "mode", "boot", "phase", "paths"}
                or type(row["schema"]) is not int or row["schema"] != 1
                or row["attempt"] != _ACL_NAME.fullmatch(path.name).group(1)
                or row["owner_nonce"] != self.profiles.owner_nonce
                or row["root_identity"] != self.profiles.root_identity
                or row["data_identity"] != self.profiles.data_identity
                or type(row["phase"]) is not str or row["phase"] not in {"planned", "applied", "retired"}
                or type(row["mode"]) is not str or row["mode"] not in {"dispatch", "review"}
                or type(row["profile_sid"]) is not str
                or type(row["boot"]) is not str
                or re.fullmatch(r"(?:windows|linux|darwin):[0-9a-f-]{36}", row["boot"]) is None
                or type(row["paths"]) is not dict
                or set(row["paths"]) != {"parent", "work", "runtime", "login"}):
            raise ProfileRefused("profile_acl_invalid", "ACL record does not bind this owner")
        profile = self.profiles._read(self.directory / f"profile-{row['attempt']}.json")
        if (profile["sid"] != row["profile_sid"]
                or (row["phase"] != "retired" and profile["phase"] != "created")):
            raise ProfileRefused("profile_acl_invalid", "ACL SID differs from owned profile")
        try:
            WindowsContainer(row["profile_sid"])
        except ValueError as error:
            raise ProfileRefused("profile_acl_invalid", "ACL SID is malformed") from error
        for key, facts in row["paths"].items():
            if (type(facts) is not dict
                    or set(facts) != {"identity", "before", "protected", "owner_sid"}
                    or type(facts["identity"]) is not list or len(facts["identity"]) != 2
                    or any(type(x) is not int or x < 0 for x in facts["identity"])
                    or type(facts["before"]) is not str
                    or type(facts["protected"]) is not bool
                    or type(facts["owner_sid"]) is not str):
                raise ProfileRefused("profile_acl_invalid", f"ACL facts for {key} are malformed")
        return row

    def retire(self, record_path, *, proven=False, after_restart=False):
        record = self._read(record_path)
        if record["phase"] == "retired":
            return
        if not proven and not (after_restart and record["boot"] != boot_identity()):
            raise ProfileRefused("profile_acl_unproven", "process group may still hold the ACL loan")
        paths = self._paths(record["attempt"])
        if self.holds is None:
            existing = {key: path for key, path in paths.items() if os.path.lexists(path)}
            self.holds = self._hold_paths(existing)
        stack, holds = self.holds
        for key, path in paths.items():
            if not os.path.lexists(path):
                continue
            _plain(path, True)
            if (key not in holds or list(holds[key].identity) != record["paths"][key]["identity"]
                    or list(identity(path)) != record["paths"][key]["identity"]):
                raise ProfileRefused("profile_acl_invalid", "owned attempt path identity changed")
        if os.path.lexists(paths["parent"]):
            _walk_plain(paths["parent"])  # parent restore may propagate into every child
            with os.scandir(paths["parent"]) as children:
                for entry in children:
                    if entry.name not in {"work", "runtime", "login"}:
                        raise ProfileRefused("profile_acl_invalid", "owned parent has an unexpected entry")
        # Empty own descendants while the pinned leaf still blocks replacement.
        for key in ("work", "runtime", "login"):
            path = paths[key]
            if os.path.lexists(path):
                for child in reversed(_walk_plain(path)):
                    if child == path:
                        continue
                    found = os.lstat(child)
                    if getattr(found, "st_reparse_tag", 0) or stat.S_ISLNK(found.st_mode):
                        raise ProfileRefused("profile_acl_invalid", "owned attempt changed during cleanup")
                    if stat.S_ISDIR(found.st_mode):
                        child.rmdir()
                    elif stat.S_ISREG(found.st_mode) and found.st_nlink == 1:
                        child.unlink()
                    else:
                        raise ProfileRefused("profile_acl_invalid", "owned attempt changed during cleanup")
        # Parent inheritance is restored before each now-empty leaf's exact DACL.
        for key in ("parent", "work", "runtime", "login"):
            path = paths[key]
            if os.path.lexists(path):
                facts, hold = record["paths"][key], holds[key]
                self.native.acl_set(hold, facts["before"], protected=facts["protected"])
                restored, protected, owner_sid = self.native.acl_snapshot(hold)
                if (protected != facts["protected"] or owner_sid != facts["owner_sid"]
                        or not self.native.acl_equal(restored, facts["before"])):
                    raise ProfileRefused("profile_acl_invalid", "native ACL restore readback differs")
        # Holds pin the four names without FILE_SHARE_DELETE through leaf removal.
        for key in ("work", "runtime", "login"):
            if os.path.lexists(paths[key]):
                holds[key].delete()
        if os.path.lexists(paths["parent"]):
            holds["parent"].delete()
        self.close()
        record["phase"] = "retired"
        _replace(record_path, record)

    def recover(self):
        if not self.directory.exists():
            return
        for path in sorted(self.directory.iterdir()):
            if _ACL_TEMP.fullmatch(path.name):
                _plain(path, False)
                path.unlink()
        for path in sorted(self.directory.glob("acl-*.json")):
            try:
                self.retire(path, after_restart=True)
            finally:
                self.close()
