"""The relay home: where a subscription attempt keeps its login state, outside the project.

A subscription harness keeps its state in a login home. The attempt must not stand on the
operator's real login home (that grant is closed, `process_boundary.LOGIN_LOAN_OPEN`), so it works
on a RELAY home instead: a fresh folder `<relay>/<key>/<name>` beside the logins folder, which the
runner loans like any per-spawn home (`process_loans`, rights `modify`) and which holds only what
the product copied in. This module is the runner's half of that: the one shape every layer judges
(`relay_home_shape`), the one DACL the relay folder must have (`ensure_relay_root`) and the one
reading of an entry that would let a container reach a folder (`ace_refusal`). It copies nothing
and starts nothing; the transport that fills a relay home is another layer.

The relay folder is the sibling of `logins` in `DecemberCommand`, derived from the login home the
caller names and from nothing else (no environment variable, no home of the process), so a test on
a throw-away login home never touches the folders of the person who runs it. Its DACL is protected
and names SYSTEM and its owner only. A key folder and a relay home beneath it carry only entries
they inherit. A container is given access to a folder by an entry for its own profile (the loan) or
by one for ALL APPLICATION PACKAGES, a package or a capability; the last three are refused on every
folder this module reads, because they would open it to an attempt that was never lent it.

The shape of a relay home is checked on the spelled path (an lstat walk of the four names
`DecemberCommand`, `relay`, the key and the name, each a plain directory) and against the real
paths (the same folder as the relay folder of a configured login home, no overlap with the
project, the work folder, the install folder or a login home). The walk must see the spelled path:
a real path has no link left in it.

A home written as an absolute path is a relay home and nothing else (`absolute_home`): a folder of
the project is a route, walked from the project root, never an absolute path.
"""
from __future__ import annotations

import hashlib
import itertools
import os
import re
import secrets
import stat
from contextlib import ExitStack
from pathlib import Path, PurePath

from ... import ownership
from ...ownership_errors import OwnerRefused
from ...ownership_native import NativeHold, identity
from ..containment import contained_directory, portal_violation
from ..long_path import extended
from .process_boundary import LOGIN_PARENTS, login_home_named
from .process_loans import _explicit, _fields, _inside, _refused, _split
from .process_profile import ProfileRefused

#: The folder beside `logins` that holds the relay homes of every project of the product.
RELAY_DIR = "relay"
#: `c` for Claude Code or `x` for Codex, then 16 hex. Short on purpose: the child's paths are long.
HOME_NAME = re.compile(r"[cx]-[0-9a-f]{16}\Z")
_ALLOW = ("A", "OA")
_PLAIN = ("A", "OA", "D", "OD")
#: ALL APPLICATION PACKAGES, and the prefixes of a package SID and of a capability SID.
_PACKAGE_ALIAS = "AC"
_PACKAGE_SIDS = ("S-1-15-2-", "S-1-15-3-")
#: A folder made for the relay folder and not yet published (`ensure_relay_root`).
_STAGE = re.compile(r"\.relay\.[0-9a-f]{16}\.tmp\Z")
#: The entries at the top of the real login home that are read, at most. A container reaches a file
#: by its full path whatever the folders above it say (the token bypasses traverse checking), so
#: each entry's own DACL counts; a login home holds a dozen, and one that holds more is refused.
LOGIN_ENTRIES = 512
#: What a refusal names the relay folder by, and what the person can do about it.
_RELAY = "the relay folder (DecemberCommand/relay)"
_REMOVE = "remove it when no attempt runs, and the product makes it again"


def relay_root_for(auth_home: object) -> Path | None:
    """The relay folder of a login home: `...\\DecemberCommand\\relay` for
    `...\\DecemberCommand\\logins\\<name>`, or None for any other form.

    A fact of the written place only (names compared case folded, as `login_home_named` does);
    it reads no file. The caller names the REAL login home, so a link above it is already gone.
    """
    if isinstance(auth_home, PurePath):
        text = str(auth_home)
    elif type(auth_home) is str:
        text = auth_home
    else:
        return None
    home = Path(text)
    if (not login_home_named(text) or not home.is_absolute() or len(home.parents) < 2
            or os.pardir in home.parts):
        return None
    top, logins = home.parent.parent, home.parent
    if (top.name.casefold(), logins.name.casefold()) != LOGIN_PARENTS:
        return None
    return top / RELAY_DIR


def relay_key(identity) -> str:
    """The key folder of one project: 16 hex of its root's native identity (volume, file id).

    Serialised like the name of a folder's ACL mutex (`_winlaunch.acl_mutex_name`): the volume and
    the file id, joined by a colon. The key names the project and no path.

    Raises:
        ValueError: `identity` is not two non-negative integers.
    """
    try:
        volume, file_id = identity
    except (TypeError, ValueError):
        raise ValueError("a project identity is a volume and a file id") from None
    if any(type(part) is not int or part < 0 for part in (volume, file_id)):
        raise ValueError("a project identity is a volume and a file id")
    return hashlib.sha256(f"{volume}:{file_id}".encode("ascii")).hexdigest()[:16]


def project_key(root: object) -> str:
    """The key folder of the project whose root folder is `root` (`relay_key` of its identity).

    Raises:
        OSError: the root folder cannot be identified.
    """
    return relay_key(identity(Path(root).resolve()))


def mint_home(auth_home: object, root: object, kind: str) -> Path | None:
    """A new, empty relay home `<relay>/<key>/<kind>-<16 hex>` of a project, or None if none can be.

    The relay folder is the one `ensure_relay_root` proved and it must still stand: it is never
    made here, because a folder made here would have no DACL of its own. The key folder is made
    when it is absent and inherits what the relay folder hands down; the home is made new
    (`exist_ok=False`), so a name that stands is never reused. Nothing is copied into it.

    Args:
        auth_home: The REAL login home the relay is for.
        root: The project root, whose identity is the key.
        kind: The harness's letter (`RelaySpec.kind`).
    """
    relay = relay_root_for(auth_home)
    if relay is None or HOME_NAME.fullmatch(f"{kind}-{'0' * 16}") is None:
        return None
    try:
        home = relay / project_key(root) / f"{kind}-{secrets.token_hex(8)}"
        home.parent.mkdir(exist_ok=True)
        home.mkdir()
    except OSError:
        return None
    return home


def lease_names(root: object, auth_home: object) -> bool:
    """Whether the standing login lease of the calling thread, in the project at `root`, is the
    lease of `auth_home`: the folder the lease recorded, by its identity and not its spelling.

    Anything else is no: no live owner, no lease, an uncertain one, or a lease of another folder.
    The relay is copied from the real login home only under the lease that holds it, so a copy
    for a login the lease does not name is never made.
    """
    try:
        leased = ownership.require_owner(root).leased_login()
        return leased is not None and tuple(leased.identity) == tuple(
            identity(Path(auth_home).resolve()))
    except (OwnerRefused, OSError):
        return False


def leaf_kind(home: object, name: str) -> str:
    """What stands at one plain name in a relay home, as the closed word of a home leaf.

    The same answer `HarnessWorkspace.home_leaf_kind` gives for a home of the project, for a home
    outside it: from `lstat` alone, nothing followed and nothing read. A home that is not a plain
    folder, and a name that is a portal, a folder, a second hard link or anything not a regular
    file, is `other`.
    """
    from . import harness_workspace as words  # deferred: it imports the runner, which imports this

    target = Path(home) / name
    try:
        top = os.lstat(extended(home))
    except OSError:
        return words.HOME_LEAF_OTHER
    if not stat.S_ISDIR(top.st_mode) or portal_violation(Path(home), top) is not None:
        return words.HOME_LEAF_OTHER
    try:
        found = os.lstat(extended(target))
    except FileNotFoundError:
        return words.HOME_LEAF_ABSENT
    except OSError:
        return words.HOME_LEAF_OTHER
    if (portal_violation(target, found) is not None or not stat.S_ISREG(found.st_mode)
            or found.st_nlink != 1):
        return words.HOME_LEAF_OTHER
    return words.HOME_LEAF_EMPTY if found.st_size == 0 else words.HOME_LEAF_FILE


def _spelled(path: object) -> Path | None:
    """`path` as an absolute path with no `.` or `..` written in it, else None."""
    if not isinstance(path, (str, PurePath)):
        return None
    text = str(path)
    found = Path(text)
    if ("\x00" in text or not found.is_absolute()
            or any(part in (".", "..") for part in re.split(r"[\\/]+", text))):
        return None
    return found


def _real(path: object) -> str:
    return os.path.normcase(os.path.realpath(path))


def absolute_home(path: object, root: Path) -> Path:
    """The home of an attempt written as an absolute path: a relay home, never the project's own.

    A folder of the project is a route, walked from the project root link by link
    (`ProcessRunner._resolve_cwd`); an absolute path skips that walk. So an absolute home that
    stands in the project, as written or in its real place (a junction outside the project that
    leads into it), is refused here and is not taken for a project home. Where else it stands is
    the loan's judgement (`relay_home_shape`), which wants exactly the relay home.

    Args:
        path: The absolute home as it was written.
        root: The project root.

    Raises:
        ProfileRefused: `profile_acl_invalid` for a home in the project.
    """
    home = Path(path)
    if _inside(home, root) or _inside(Path(os.path.realpath(home)), Path(os.path.realpath(root))):
        raise _refused("the relay home is refused: an absolute home is a relay home, and this "
                       "one lies in the project; a folder of the project is written as a route")
    return home


def relay_home_shape(auth_homes, root, root_identity, path, work, install) -> str | None:
    """Why `path` is not the relay home of this project's attempt, or None when it is.

    The one judgement of the shape, for the runner's loan, the transport's readiness and the test
    double of the boundary alike. The path is exactly `<relay>/<key>/<name>`: `<relay>` is the
    relay folder of one of the project's login homes, `<key>` is this project's (`relay_key`),
    `<name>` is `c-` or `x-` and 16 hex. Each of the four names is a plain directory that exists
    (lstat, no link followed), and the folder overlaps neither the project, nor the work folder,
    the install folder or any login home.

    Args:
        auth_homes: The REAL login homes the project holds.
        root: The project root; `root_identity` is its native identity.
        path: The relay home as it is written, not resolved.
        work: The attempt's work folder.
        install: The attempt's install folder.
    """
    auth_homes = tuple(auth_homes)
    home = _spelled(path)
    if home is None or len(home.parents) < 4:
        return "the relay home is not an absolute path of the relay folder"
    key, relay, top = home.parent, home.parent.parent, home.parent.parent.parent
    try:
        wanted = relay_key(root_identity)
    except ValueError:
        return "the identity of the project is not a volume and a file id"
    if HOME_NAME.fullmatch(home.name) is None:
        return "the relay home is not named c-<16 hex> or x-<16 hex>"
    if key.name != wanted:  # exactly: the product writes the key in lower case, as it names a home
        return "the relay home stands in the key folder of another project"
    if (relay.name.casefold(), top.name.casefold()) != (RELAY_DIR, LOGIN_PARENTS[0]):
        return f"the relay home does not stand in {LOGIN_PARENTS[0]}/{RELAY_DIR}/<key>/<name>"
    roots = {_real(found) for found in map(relay_root_for, auth_homes) if found is not None}
    if _real(relay) not in roots:
        return "the relay home is not in the relay folder of a login home the project holds"
    _, violation = contained_directory(
        top.parent, Path(top.name, relay.name, key.name, home.name))
    if violation is not None:
        return violation
    real = Path(os.path.realpath(home))
    for label, other in (("project", root), ("work", work), ("install", install),
                         *(("login", login) for login in auth_homes)):
        found = Path(os.path.realpath(other))
        if _inside(real, found) or _inside(found, real):
            return f"the relay home overlaps the {label} folder"
    return None


def relay_root_sddl(owner_sid: str) -> str:
    """The DACL of the relay folder: protected, SYSTEM and the owner, handed down to everything.

    The same base as the parent folder of an attempt (`process_acl._grant`): no entry for a
    container, so a container reaches nothing here unless a loan names a home beneath it.
    """
    return f"O:{owner_sid}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{owner_sid})"


def ace_refusal(sddl: str) -> str | None:
    """Why a DACL could open its folder to a container nobody lent it, or None when it cannot.

    The entries of type allow (`A`, `OA`) are read through the loan's own parser
    (`process_loans._split`, `_fields`): a trustee `AC` (ALL APPLICATION PACKAGES), or a SID that
    begins `S-1-15-2-` (a package) or `S-1-15-3-` (a capability, `S-1-15-3-1` is internet client),
    refuses. A deny entry changes nothing here. A conditional entry, any other type, a DACL that
    does not parse: refused, because what is not understood is not shown to be safe.

    Returns:
        A phrase that continues "the folder ...", or None.
    """
    try:
        _head, aces = _split(sddl)
    except ProfileRefused:
        return "has a DACL this build does not understand"
    for ace in aces:
        fields = _fields(ace)
        if len(fields) != 6 or fields[0] not in _PLAIN:
            return "has an entry that is conditional or not understood"
        trustee = fields[5].strip().upper()
        container = trustee == _PACKAGE_ALIAS or trustee.startswith(_PACKAGE_SIDS)
        if fields[0] in _ALLOW and container:
            return "has an entry for ALL APPLICATION PACKAGES, a package or a capability"
    return None


def _inherited_only(sddl: str) -> str | None:
    try:
        _head, aces = _split(sddl)
    except ProfileRefused:
        return "has a DACL this build does not understand"
    if any(len(_fields(ace)) != 6 or _explicit(_fields(ace)) for ace in aces):
        return "has an entry of its own: it may hold only what it inherits"
    return None


def _acl_of(native, hold_factory, path: Path, *, directory: bool = True):
    """(DACL text, protected, owner) of a folder or file held for reading only; None if unreadable.

    A link, a file with another name or one that is held for writing is not readable here: the
    hold refuses it, and what is refused is not shown to be safe.
    """
    try:
        hold = hold_factory(path, directory=directory, grants=False)
        try:
            return native.acl_snapshot(hold)
        finally:
            hold.close()
    except (OSError, ProfileRefused):
        return None


def relay_root_refusal(native, root, *, hold_factory=NativeHold) -> str | None:
    """Why the relay folder does not have exactly its DACL, or None when it does.

    Protected, SYSTEM and its owner, and no other entry (`relay_root_sddl`); the DACL bytes are
    compared by the OS (`native.acl_equal`), not by the spelling of the text. The owner is the
    folder's own, as for every folder this runner makes: a folder another principal made has a
    DACL that names that principal and SYSTEM, so the person reaches nothing in it and the first
    key folder is refused by the OS, and nothing is exposed. Each refusal names the folder and what
    the person does: nothing is repaired here, because who added an entry is not known.
    """
    found = _acl_of(native, hold_factory, Path(root))
    if found is None:
        return f"{_RELAY} cannot be read; {_REMOVE}"
    sddl, protected, owner = found
    try:
        same = native.acl_equal(sddl, relay_root_sddl(owner))
    except OSError:
        return f"the DACL of {_RELAY} cannot be compared; {_REMOVE}"
    if not protected or not same:
        return (f"{_RELAY} is not protected with SYSTEM and its owner as its only entries; "
                f"{_REMOVE}")
    return None


def _folder_refusal(native, hold_factory, path: Path, what: str, *, inherited: bool,
                    directory: bool = True):
    found = _acl_of(native, hold_factory, path, directory=directory)
    if found is None:
        return f"the {what} cannot be read"
    reason = ace_refusal(found[0]) or (_inherited_only(found[0]) if inherited else None)
    return None if reason is None else f"the {what} {reason}"


def relay_side_refusal(native, relay_home, *, hold_factory=NativeHold) -> str | None:
    """Why the relay folder, the key folder or the relay home is not as the loan needs it.

    The relay folder has exactly its DACL; the key folder and the relay home hold only inherited
    entries, none of them for a container as a whole. Read before the loan adds its own entry.
    """
    key = Path(relay_home).parent
    return (relay_root_refusal(native, key.parent, hold_factory=hold_factory)
            or _folder_refusal(native, hold_factory, key, "key folder", inherited=True)
            or _folder_refusal(native, hold_factory, Path(relay_home), "relay home",
                               inherited=True))


def _entries_refusal(native, hold_factory, home: Path) -> str | None:
    """Why an entry at the top of the REAL login home could be read by a container, or None.

    The token of a container bypasses traverse checking: it reads a file by its full path though
    the folders above it refuse a listing (measured 23.10.2026: a child read a leaf of a login
    home that had its own entry for ALL APPLICATION PACKAGES, while the home and `logins` were
    closed to it). So the DACL of each entry counts, the credentials among them. Their names are
    the vendor's and not this module's, so every entry is read, not a list of names; those below
    the top are not credentials.
    """
    try:
        with os.scandir(home) as scan:
            found = [(item.name, item.is_dir(follow_symlinks=False))
                     for item in itertools.islice(scan, LOGIN_ENTRIES + 1)]
    except OSError:
        return "the login home cannot be listed"
    if len(found) > LOGIN_ENTRIES:
        return f"the login home holds more than {LOGIN_ENTRIES} entries, which are not all read"
    for name, directory in sorted(found):
        reason = _folder_refusal(native, hold_factory, home / name, f"login home entry {name}",
                                 inherited=False, directory=directory)
        if reason is not None:
            return reason
    return None


def login_side_refusal(native, auth_home, *, hold_factory=NativeHold) -> str | None:
    """Why the REAL login home could be opened to a container, or None.

    The home, its parent `logins` and every entry at the top of the home: none may have an entry
    for ALL APPLICATION PACKAGES, a package or a capability (the leaves are what a container would
    read, `_entries_refusal`). Read only, by a hold that cannot change anything. Their DACLs are
    the operator's and are never set here; such an entry would let a container read the real
    credentials, so the attempt is refused instead.
    """
    home = Path(auth_home)
    return (_folder_refusal(native, hold_factory, home, "login home", inherited=False)
            or _folder_refusal(native, hold_factory, home.parent, "logins folder",
                               inherited=False)
            or _entries_refusal(native, hold_factory, home))


def logins_refusal(native, auth_homes, relay_home, *, hold_factory=NativeHold) -> str | None:
    """`login_side_refusal` for each existing login home beside the relay folder of `relay_home`.

    The loan asks it at the grant, so the facts the transport proved at its readiness are proved
    again by the runner, which cannot tell which of the project's logins the attempt works from
    (the relay folder is shared by all of them): a container must reach none. A login home that
    does not exist holds no credential.
    """
    relay = _real(Path(relay_home).parent.parent)
    for login in auth_homes:
        found = relay_root_for(login)
        if found is not None and _real(found) == relay and os.path.lexists(login):
            reason = login_side_refusal(native, login, hold_factory=hold_factory)
            if reason is not None:
                return reason
    return None


def relay_acl_refusal(native, auth_home, relay_home=None, *, hold_factory=NativeHold):
    """Every fact about DACLs a subscription attempt rests on, or the first that fails.

    For the readiness of the transport, which asks it before it claims anything: the relay folder
    of `auth_home` (and, once they exist, the key folder and `relay_home`) and the real login home
    with its parent and the entries at its top (`login_side_refusal`).
    """
    root = relay_root_for(auth_home)
    if root is None:
        return "the login home does not stand in DecemberCommand/logins/<name>"
    if relay_home is None:
        first = relay_root_refusal(native, root, hold_factory=hold_factory)
    elif _real(Path(relay_home).parent.parent) != _real(root):
        return "the relay home is not in the relay folder of this login home"
    else:
        first = relay_side_refusal(native, relay_home, hold_factory=hold_factory)
    return first or login_side_refusal(native, auth_home, hold_factory=hold_factory)


def ensure_relay_root(auth_home, *, native, hold_factory=NativeHold) -> Path:
    """Make the relay folder of a login home if it is absent, and prove its DACL either way.

    Under the cross-process mutex of `DecemberCommand` (`acl_exclusive`): a folder that already
    exists is only compared, and a DACL that is not exactly `relay_root_sddl` is refused, never
    repaired, because who added the entry is not known. A folder that does not exist is made
    beside it under a staging name (`.relay.<16 hex>.tmp`), given that DACL with the inheritance
    cut, read back and compared, and only then renamed to `relay` (Windows does not replace a
    folder). So `relay` never stands without its DACL, whatever stops the process in between; a
    staging folder that is left is swept, if empty, by the next call.

    The OS calls are the runner's: this module never imports the native helper (only
    `process.py` may), so a caller reaches them through `ProcessRunner.ensure_relay_root`.

    Args:
        auth_home: The REAL login home, `.../DecemberCommand/logins/<name>`.
        native: The helper's `acl_exclusive`, `acl_snapshot`, `acl_set` and `acl_equal`.
        hold_factory: The hold of a folder (`NativeHold`).

    Returns:
        The relay folder.

    Raises:
        ProfileRefused: `profile_acl_invalid` for a login home of another form, a folder that
            cannot be held, or a DACL that is not exactly the one above.
    """
    root = relay_root_for(auth_home)
    if root is None:
        raise _refused("the login home does not stand in DecemberCommand/logins/<name>")
    try:
        with ExitStack() as stack:
            top = hold_factory(root.parent, directory=True)
            stack.callback(top.close)
            with native.acl_exclusive(top):
                _publish(root, native, hold_factory)
    except OSError as error:
        raise _refused(f"the relay folder cannot be made ({type(error).__name__})") from error
    return root


def _sweep(top: Path) -> None:
    """Remove the staging folders an earlier call left; an empty one only, and nothing else."""
    with os.scandir(top) as scan:
        stale = [Path(item.path) for item in scan
                 if _STAGE.fullmatch(item.name) and item.is_dir(follow_symlinks=False)]
    for folder in stale:
        try:
            folder.rmdir()
        except OSError:
            pass  # not empty or held: it is not the relay folder, and harms nothing


def _publish(root: Path, native, hold_factory) -> None:
    """The relay folder as it must be: the one that stands, or one made whole and renamed."""
    if os.path.lexists(root):
        reason = relay_root_refusal(native, root, hold_factory=hold_factory)
        if reason is not None:
            raise _refused(reason)
        return
    _sweep(root.parent)
    stage, placed = root.parent / f".relay.{secrets.token_hex(8)}.tmp", False
    stage.mkdir()
    try:
        hold = hold_factory(stage, directory=True, grants=True)
        try:
            native.acl_set(hold, relay_root_sddl(native.acl_snapshot(hold)[2]), protected=True)
        finally:
            hold.close()  # a held folder cannot be renamed
        reason = relay_root_refusal(native, stage, hold_factory=hold_factory)
        if reason is None:
            os.rename(stage, root)  # `root` is absent under the mutex, and Windows never replaces
            placed = True
            reason = relay_root_refusal(native, root, hold_factory=hold_factory)
        if reason is not None:
            raise _refused(reason)
    except BaseException:
        try:
            (root if placed else stage).rmdir()  # empty: nothing is put in it before this returns
        except OSError:
            pass  # a stage that is left is swept by the next call; `root` is refused by its DACL
        raise
