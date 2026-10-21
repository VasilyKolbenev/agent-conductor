"""Durable ACL loans on EXISTING product-owned folders of one AppContainer attempt.

`process_acl` makes, grants and deletes FRESH folders. A loan is the other case: the attempt's work
folder, its per-spawn home (or the login home its lease names) and the pinned install folder
already exist, are not this journal's to delete, and are given back. Before anything changes a
record names each folder, its identity and its DACL; the grant adds entries for the attempt's
profile only (explicit rights, never Full Control, never WRITE_DAC or DELETE_CHILD, never a deny);
the exit takes those entries away again, which also takes the profile's inherited entries away
from everything the attempt touched beneath the folder.

A loan is returned by taking away ITS OWN entries from the DACL as it stands at the exit, never by
writing back the DACL that was read at the start. The pinned install folder is shared by every
attempt of a harness and by every project: a written-back DACL would give the entry of an attempt
that still runs away at the first exit, and would keep the entry of a finished one at the last.
The record keeps the prior DACL as evidence of what the folder was.

The hold of a loaned folder asks for WRITE_DAC and NOT for DELETE. Measured 13.10.2026: with DELETE
in the hold, setting a DACL on the folder does not propagate an inheritable entry to its existing
children, nor take it away again, and reports success; without DELETE it does both.

The leased login home is the one loan that is not a product folder of the attempt: it is the
operator's dedicated login directory, rewritten in place when a credential is refreshed. It is
granted only to the attempt that holds the shared login lease on exactly that folder (proved by the
identity the lease recorded, not by the spelling of a path), for the attempt's life, and only with
what a credential refresh needs: the folder itself can be read, written into and traversed but not
deleted, a nested directory the same, a nested regular file read, written and deleted and nothing
else. The grant counts against the lease, so the lease cannot end before the rights are back.

That grant is CLOSED as shipped (`process_boundary.LOGIN_LOAN_OPEN`, `login_loan_provided`): the
rights of a refresh let the attempt create files in the home and overwrite every file beneath it,
and the vendor's executable configuration lives there. A login home is refused, before anything
exists. In V1 it stays closed (the owner's decision H5-V1 of 21.10.2026), and no transport names
one: the subscription road is refused by the transport before any claim.

Nothing here widens an ACL beyond the four kinds of folder `AttemptFolders` names. That is a law of
this runner and not a manner of its callers: an install folder is the version folder of a pinned
harness and never a login folder or a folder that holds one, a home is a minted folder of a
catalogued harness home root, a work folder is one item of the work tree, the login home is the
folder the attempt's own lease names, and a spawn on a loan starts a program that stands in the
loaned install folder (`holds_entry`).
"""
from __future__ import annotations

import json
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path

from ... import ownership
from ...ownership_errors import OwnerRefused
from ...ownership_native import NativeHold, identity
from ...ownership_records import ACTIVE, HOME, LEGACY
from ..work_layout import TASKS_DIR, work_parts
from .process_acl import _CHILD_RWX_DELETE, _RWX, _RX
from .process_boundary import LOGIN_SHAPE, WindowsContainer, login_home_named, login_loan_provided
from .process_profile import ProfileRefused, _bytes, _plain, _replace, refusal_summary

_LOAN_NAME = re.compile(r"loan-([0-9a-f]{32})\.json\Z")
_LOAN_TEMP = re.compile(r"\.loan-[0-9a-f]{32}\.json\.[0-9a-f]{16}\.tmp\Z")
_KEYS = ("work", "home", "install", "login")
#: What a nested regular file of the login home is given: read, write, append, extended attributes,
#: attributes, READ_CONTROL, SYNCHRONIZE and DELETE (`_CHILD_RWX_DELETE` without FILE_EXECUTE). That
#: is what a credential refresh does to a file: write it in place, rename another over it, delete
#: it and move another into its place. Nothing here runs a file, changes an ACL or an owner.
_REFRESH = _CHILD_RWX_DELETE & ~0x20
#: Grok keeps a directory `hooks` and a file `hooks-paths` in its home and loads what they name.
#: The login loan hands rights down to nested objects, so it is made only while each of these that
#: exists has its inheritance cut: nothing is handed down to it, and nothing can replace it.
HOOK_NAMES = frozenset({"hooks", "hooks-paths"})
_DACL = re.compile(r"(O:[^()]*?D:[A-Z]*)((?:\([^()]*\))*)")
_ACE = re.compile(r"\([^()]*\)")
#: Where no folder of an attempt may lie: the owner's repository (at any depth) and, at the top of
#: the project, the product's own data.
_REPOSITORY = ".git"
_PRODUCT_TOP = (ACTIVE, LEGACY, HOME)
#: A pinned harness stands in `<anything>/harnesses/<name>/<version>`: the shape of an install
#: folder (the version folder), whichever cache the pins live in.
PIN_ROOT = "harnesses"
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
    if rights == "login":
        return (f"(A;;0x{_RWX:x};;;{sid})(A;CIIO;0x{_RWX:x};;;{sid})"
                f"(A;OIIO;0x{_REFRESH:x};;;{sid})")
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
            is inside it), `rx` (read and execute, inheritable) or `login` (the folder and a nested
            directory read, written into and traversed but never deleted; a nested regular file
            read, written and deleted, never run).

    Raises:
        ProfileRefused: `profile_acl_invalid` for text this does not understand (a security
            descriptor with a group or an audit part, a conditional entry, unbalanced brackets) or
            an unknown right. Nothing is guessed.
    """
    if rights not in ("modify", "rx", "login"):
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


def _identity_of(path: Path) -> tuple[int, int]:
    """The native identity of an existing folder: the volume and the file id, not its spelling."""
    try:
        return tuple(identity(path))
    except OSError as error:
        raise _refused("a loaned folder cannot be identified") from error


def _system_places(environ) -> list[Path]:
    names = ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")
    return [Path(os.path.realpath(environ[name])) for name in names if environ.get(name)]


def configured_login_homes(data_root: Path) -> tuple[Path, ...]:
    """The `auth_home` of every provider the project holds, in their real places.

    The project's own `providers.json` is where its attempts find their logins: the operator's
    shared profile reaches a project only as an explicit copy of its rows.

    Raises:
        ProfileRefused: `profile_acl_invalid` when the file cannot be read, so a loan is not made
            on a promise about logins that cannot be checked.
    """
    from .. import operator_config  # deferred: it reaches the provider door and the run store
    path = operator_config.provider_config_path(data_root)
    try:
        rows = operator_config.load_provider_configs(path)
    except operator_config.OperatorConfigError as error:
        raise _refused("the login folders of the project cannot be established") from error
    return tuple(Path(os.path.realpath(row.auth_home)) for row in rows if row.auth_home)


def _refuse_install(install: Path, root: Path, environ) -> None:
    """The install folder: the version folder of one pinned harness, and nothing wider.

    Never the project, the user's profile or a system program; and of what is left, only
    `<pin root>/<name>/<version>`, so the folder above a pin (the profile's application data, a
    vendor's own dot folder) cannot be named by a wiring that took the wrong ancestor.
    """
    if _inside(root, install) or _inside(install, root):
        raise _refused("the install folder overlaps the project")
    profile = environ.get("USERPROFILE")
    if profile and _inside(Path(os.path.realpath(profile)), install):
        raise _refused("the install folder is the user profile or contains it")
    for place in _system_places(environ):
        if _inside(install, place) or _inside(place, install):
            raise _refused("the install folder is a system program folder or contains one")
    if install.parent.parent.name.casefold() != PIN_ROOT:
        raise _refused(f"the install folder is not the version folder of a pinned harness "
                       f"({PIN_ROOT}/<name>/<version>)")


def catalogued_home_roots() -> frozenset[str]:
    """The folder each catalogued harness keeps its per-spawn homes in, case folded."""
    from .. import product_names  # deferred: it imports every adapter module
    return frozenset(home.casefold() for home, _marker in product_names._HARNESS_NAMES)


def _work_item(route: tuple[str, ...]) -> bool:
    """Whether `route` is exactly what `work_parts` gives one work item: `work/<id>`, or
    `work/_tasks/<scope>/<id>`. The container name is not an item of the tree."""
    if len(route) == 2:
        return route == work_parts(route[1]) and route[1].casefold() != TASKS_DIR.casefold()
    return len(route) == 4 and route == work_parts(route[3], route[2])


def _minted_home(route: tuple[str, ...]) -> bool:
    """`<home root>/<minted name>`: exactly two levels, the first a catalogued harness home root."""
    return len(route) == 2 and route[0].casefold() in catalogued_home_roots()


def _refuse_attempt_folder(name: str, path: Path, root: Path) -> None:
    """The work folder and the home: beneath the project, in the shape the product gives them."""
    if root not in path.parents:
        raise _refused(f"the {name} folder is not beneath the project")
    route = path.relative_to(root).parts
    if (any(part.casefold() == _REPOSITORY for part in route)
            or route[0].casefold() in _PRODUCT_TOP):
        raise _refused(f"the {name} folder lies in the owner's repository or the product's data")
    if name == "work" and not _work_item(route):
        raise _refused("the work folder is not one item of the work tree")
    if name == "home" and not _minted_home(route):
        raise _refused("the home is not a minted folder of a catalogued harness home root")


def change_dacl(native, hold, build) -> None:
    """Set the DACL `build` makes from the one the folder has NOW, and read it back, under the
    folder's cross-process mutex.

    The OS has no compare-and-swap on a DACL, and a pinned install folder is shared by every
    project server, so the read, the write and the read back of ONE change are taken as a whole
    under the mutex the folder's identity names (`native.acl_exclusive`), at the grant and at the
    return alike. The mutex is held for this change only, never while an agent works. The DACL is
    read inside it, so an entry another attempt or the owner added before then stays, and nothing
    is assumed of what an owner that died holding the mutex had done. Protection and owner are
    kept as found.

    Raises:
        ProfileRefused: `profile_acl_invalid` when the DACL reads back different from the change.
        TimeoutError: another process kept the folder's mutex too long; nothing was changed.
    """
    with native.acl_exclusive(hold):
        current, protected, owner_sid = native.acl_snapshot(hold)
        proposed = build(current)
        native.acl_set(hold, proposed, protected=protected)
        readback, now_protected, now_owner = native.acl_snapshot(hold)
        if (now_protected != protected or now_owner != owner_sid
                or not native.acl_equal(readback, proposed)):
            raise _refused("native ACL readback differs from the change")


def holds_entry(argv, install: str | None, environ=None) -> bool:
    """Whether the program `argv` starts stands in the install folder loaned to its attempt.

    The program is `argv[0]`. A runtime that lives in a system program folder (the `node` a script
    runs on) is not the program: the first absolute path after it is. Without an install folder
    nothing is bound.
    """
    if install is None:
        return True
    system = _system_places(os.environ if environ is None else environ)
    entry = Path(os.path.realpath(argv[0]))
    if any(_inside(entry, place) for place in system):
        entry = next((Path(os.path.realpath(a)) for a in argv[1:] if os.path.isabs(a)), None)
    return entry is not None and _inside(entry, Path(os.path.realpath(install)))


class FolderLoans:
    """The loans of one attempt, journalled in `loan-<attempt>.json` beside its profile record."""

    def __init__(self, profiles, native, *, hold_factory=NativeHold, environ=None,
                 login_homes=None, leased_login=None):
        self.profiles, self.native = profiles, native
        self.directory = profiles.directory
        self.hold_factory = hold_factory
        self.environ = os.environ if environ is None else environ
        self.login_homes = login_homes  # a callable of no argument; None: the project's providers
        self.leased_login = leased_login  # a callable of no argument; None: the project's owner
        self.record, self.holds, self.paths = None, None, {}
        self.lease_retire = None  # retires the loan against the login lease the grant counts as

    def _logins(self) -> tuple[Path, ...]:
        if self.login_homes is None:
            return configured_login_homes(self.directory.parent)
        return tuple(Path(os.path.realpath(path)) for path in self.login_homes())

    def _leased(self):
        """The login folder the calling thread's standing lease holds (`LeasedLogin`), or None."""
        try:
            if self.leased_login is not None:
                return self.leased_login()
            return ownership.require_owner(self.profiles.owner_root).leased_login()
        except OwnerRefused as error:
            raise _refused("the login lease of the attempt is not standing") from error

    def _refuse_login(self, real: dict[str, Path]) -> None:
        """The login home is the folder the attempt's own lease holds, proved by its identity, in
        the place the product keeps a login home, and it is no part of the attempt's other folders
        nor of the project. No lease, no loan."""
        login = real["login"]
        if "home" in real:
            raise _refused("a loan names a home or a login home, never both")
        leased = self._leased()
        if leased is None:
            raise _refused("the attempt holds no login lease")
        if _identity_of(login) != tuple(leased.identity):
            raise _refused("the login home is a folder the attempt's lease does not name")
        if not login_home_named(str(login)):
            raise _refused(f"the login home does not stand in {LOGIN_SHAPE}")
        root = Path(os.path.realpath(self.profiles.owner_root))
        for key, other in (("work", real["work"]), ("install", real["install"]), ("project", root)):
            if _inside(other, login) or _inside(login, other):
                raise _refused(f"the login home overlaps the {key} folder")
        self._refuse_hooks(login)

    def targets(self, folders) -> dict[str, Path]:
        """The folders of a loan, checked and in their real places; nothing is held or changed.

        Raises:
            ProfileRefused: `profile_acl_invalid` for a missing or foreign key, a folder that is not
                a plain directory, one that overlaps another or a login folder, a login home the
                attempt's lease does not name, or one the rules above forbid.
        """
        if self.profiles.owner_root is None:
            raise _refused("trusted ACL callbacks are absent")
        if (type(folders) is not dict or not set(folders) <= set(_KEYS)
                or not {"work", "install"} <= set(folders)):
            raise _refused("a loan names a work folder, an install folder and at most a home "
                           "or a login home")
        if "login" in folders and not login_loan_provided():
            raise _refused("the login home is not loaned: the attempt could write the vendor's "
                           "executable configuration in it (a review ruling is open)")
        root = Path(os.path.realpath(self.profiles.owner_root))
        real = {key: _plain_directory(Path(path)) for key, path in folders.items()}
        for name in ("work", "home"):
            if name in real:
                _refuse_attempt_folder(name, real[name], root)
        _refuse_install(real["install"], root, self.environ)
        home, work = real.get("home"), real["work"]
        if home is not None and (_inside(home, work) or _inside(work, home)):
            raise _refused("the home and the work folder overlap")
        if "login" in real:
            self._refuse_login(real)
        product = [path for key, path in real.items() if key != "login"]
        for login in self._logins():
            if any(_inside(path, login) or _inside(login, path) for path in product):
                raise _refused("a loaned folder is a login folder, lies in one or holds one")
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
        leased = self._login_lease(real)
        stack, holds, rows = self._observe(real, mode, leased)
        self.holds = stack, holds
        self.lease_retire = self._hold_lease(leased)
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
        if "login" in real:
            self._refuse_hooks(real["login"])  # and again, now that the rights are handed down
        record["phase"] = "applied"
        _replace(self.record, record)
        return self.record

    def _login_lease(self, real):
        """The lease the login home rests on (None when the loan has no login home)."""
        if "login" not in real:
            return None
        leased = self._leased()
        if leased is None:
            raise _refused("the attempt holds no login lease")
        return leased

    @staticmethod
    def _hold_lease(leased):
        """Count the grant against the lease it rests on; the callable that retires the count.

        While the count stands the lease cannot be released as clean, so the rights are back
        (`restore`) before the lease ends, whatever order the caller's blocks end in."""
        if leased is None or leased.hold is None:
            return None
        try:
            return leased.hold()
        except OwnerRefused as error:
            raise _refused("the login lease of the attempt is not standing") from error

    def _release_lease(self, proven: bool) -> None:
        retire, self.lease_retire = self.lease_retire, None
        if retire is not None:
            retire(proven)

    def _refuse_hooks(self, login: Path) -> None:
        """Each hook object of the login home that exists has its inheritance cut.

        The login loan hands the refresh rights down to nested objects by inheritance, so a hook
        object that inherits would be handed a way to be written into or replaced. Nothing is
        changed here. An object that is absent is the vendor's own rule (its checks before and
        after each spawn), not the loan's.
        """
        try:
            found = [login / name for name in os.listdir(login) if name.casefold() in HOOK_NAMES]
            for path in found:
                self._require_protected(path)
        except OSError as error:
            raise _refused("a hook object of the login home cannot be read") from error

    def _require_protected(self, path: Path) -> None:
        shape = os.lstat(path)
        if (stat.S_ISLNK(shape.st_mode) or getattr(shape, "st_reparse_tag", 0)
                or not (stat.S_ISDIR(shape.st_mode) or stat.S_ISREG(shape.st_mode))):
            raise _refused(f"the login home holds {path.name!r}, which is not a plain object")
        hold = self.hold_factory(path, directory=stat.S_ISDIR(shape.st_mode), grants=False)
        try:
            protected = self.native.acl_snapshot(hold)[1]
        finally:
            hold.close()
        if not protected:
            raise _refused(f"the login home holds {path.name!r}, which inherits its rights")

    def _observe(self, real, mode, leased=None):
        """Hold every folder and note what it was; nothing is changed."""
        stack, holds, rows = ExitStack(), {}, {}
        try:
            for key, path in real.items():
                hold = self.hold_factory(path, directory=True, grants=True)
                stack.callback(hold.close)
                holds[key] = hold
                if key == "login" and tuple(hold.identity) != tuple(leased.identity):
                    raise _refused("the login home is a folder the attempt's lease does not name")
                before, protected, owner_sid = self.native.acl_snapshot(hold)
                rows[key] = {"path": str(path), "rights": self._rights(key, mode),
                             "identity": list(hold.identity), "before": before,
                             "protected": protected, "owner_sid": owner_sid}
        except BaseException:
            stack.close()
            raise
        return stack, holds, rows

    def _change(self, hold, build) -> None:
        change_dacl(self.native, hold, build)

    @staticmethod
    def _rights(key: str, mode: str) -> str:
        """Install is read-and-execute; work is modify in a dispatch and read-only in a review;
        a home is the vendor's own state and is written in both; the login home is refreshed in
        both, with the narrower rights of a credential refresh (`login`)."""
        if key == "login":
            return "login"
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
                    or type(facts["path"]) is not str
                    or facts["rights"] not in ("modify", "rx", "login")
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

        The grant counted against the login lease (if there was one) is retired when this attempt's
        own loan ends: as proven when every entry is back, as unproven when it is not.

        Raises:
            ProfileRefused: `profile_acl_invalid` for a folder that is not the one granted, or
                whose changed DACL reads back different. An error of the OS passes as it is.
        """
        record_path = record_path or self.record
        if record_path is None:
            self._release_lease(True)  # no record, so nothing was changed
            return
        own = record_path == self.record
        try:
            self._restore(record_path, abandon=abandon)
        except BaseException:
            if own:
                self._release_lease(False)
            raise
        if own:
            self._release_lease(True)

    def _restore(self, record_path: Path, *, abandon: bool) -> None:
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
