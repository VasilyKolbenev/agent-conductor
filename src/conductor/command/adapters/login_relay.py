"""The relay login: what a subscription attempt is given instead of the real login home.

A subscription harness keeps its login in a directory of its own, and an attempt must not stand on
the operator's real one (`process_boundary.LOGIN_LOAN_OPEN` stays closed). The attempt works on a
RELAY home instead, a fresh folder (`relay_home`) that holds only what this module copies in: the
credential with no refresh token, and the few files the vendor needs beside it. Nothing is ever
copied back. The vendor's own CLI refreshes the real login, outside the boundary and under the same
login lease, with the calls the product already makes (the owner's decision of 23.10.2026,
`H5-SUB-R5-V2-REVIEW-REPORT`: access-only, no copy-out).

This module is the content half of that. It reads the real credential file as strictly as a file
that something else could have written (`read_leaf`), says whether the login is ready for an
attempt of a given length (`ready`), copies the access-only credential into an empty relay home
(`copy_in`), and takes a relay home away again (`discard`, `sweep`). What a vendor's login looks
like, and what is left out of the copy, is a `RelaySpec` declared in the vendor's own module
(`claude_relay`, `codex_relay`). The OS half, the DACLs of the folders, is `relay_home`'s and the
runner's; the order of it all around a claim is the transport's.

**Nothing here raises for an expected refusal.** A login that is not ready, a file that changed
after it was checked, a relay home that is not empty and a write that failed all come back as a
`Refused` value with a closed code. The caller refuses before anything is claimed; an exception
inside the login lease would poison the lease (`ownership_login`, F3 of the design), so the only
things raised are faults of the caller: a clock without a zone, a key or a kind this build never
makes, a spec that contradicts itself.

**Nothing here carries a value out.** A refusal is a code and a fixed sentence: no path, no key
name, no byte of a credential. `Ready.secrets` and `Ticket.secrets` are the values the leak scan
must hold, and they are for the scan and nowhere else: they, and the document a `Leaf` holds,
are kept out of every `repr` (`repr=False`), so a value cannot leave in an f-string, an assertion
message or an exception text that merely named the object.

Windows details that are not obvious. A path longer than 260 characters is removed through the
extended-length form (`\\\\?\\`), because a child inside the boundary can make one and the plain
form cannot name it. A link, a junction or any other reparse point is removed as the entry it is
and never walked through, so a link a child made cannot lead the removal out of the relay home. A
file is read through one handle that is checked after it is opened, against what was looked at
before: a name swapped in between is refused.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import stat
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

from .login_home import CREDENTIAL_LIMIT

#: Every reason a login or an attempt home is refused, with the sentence that says it. A sentence
#: names no path and no value: it reaches a receipt, a journal and the API.
REFUSALS = MappingProxyType({
    "leaf_absent": "the login holds no credential file this build can copy",
    "leaf_unsafe": "the credential file is not an ordinary file with a single name",
    "leaf_too_large": "the credential file is larger than a credential file is",
    "leaf_malformed": "the credential file is not one JSON object in UTF-8",
    "foreign_credentials": "the credential file holds credentials this build does not copy",
    "unknown_shape": "the credential file is not in a shape this build was reviewed against",
    "no_access_token": "the credential file holds no access token",
    "api_key": "the login holds an API key, which is not a subscription",
    "plan_unknown": "the login does not say which plan it is on",
    "console_plan": "the login is on the API-billing plan, which is not a subscription",
    "account_unknown": "the account of the login could not be established",
    "credman": "the vendor would keep the refreshed login in the Windows credential manager",
    "credman_unknown": "whether the vendor uses the Windows credential manager is not known",
    "expiry_unknown": "when the access token expires could not be established",
    "expiry_short": "the access token expires before the attempt would end",
    "changed": "the credential file changed after it was checked",
    "refresh_leak": "the copy would carry a refresh token",
    "relay_unusable": "the attempt home is not a folder this build can copy into",
    "not_empty": "the attempt home is not empty",
    "write_failed": "the credential could not be written into the attempt home",
})
#: A value shorter than this is not scanned for: a two-character value out of a document would
#: flag every output that happened to hold those characters. The same bound as the leak scan's
#: (`login_home.credential_values`).
MIN_SECRET = 12
#: The vendor's profile file is no credential and is large (projects, history): a bound of its own.
PROFILE_LIMIT = 4 * 1024 * 1024
#: How much longer than an attempt's own timeout its access token must live: ten minutes.
MARGIN_SECONDS = 600
#: Seconds from 1970 to the start of the year 10000: no instant after it is an expiry.
_LATEST = 253402300800
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_KIND = re.compile(r"[a-z]\Z")
_KEY = re.compile(r"[0-9a-f]{16}\Z")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True)
class Refused:
    """A refusal as a value: a code of `REFUSALS`, and nothing the code does not say."""

    code: str

    def __post_init__(self) -> None:
        if self.code not in REFUSALS:
            raise ValueError("a refusal is one of the codes of REFUSALS")

    @property
    def phrase(self) -> str:
        return REFUSALS[self.code]


@dataclass(frozen=True)
class Leaf:
    """A credential file as read: the JSON object, and the SHA-256 of the bytes it came from.

    The document holds the real tokens, so it is not in the `repr`.
    """

    doc: dict = field(repr=False)
    digest: str


@dataclass(frozen=True)
class Ready:
    """A login that can be copied for an attempt of the length asked.

    Attributes:
        digest: SHA-256 of what a copy is made of: the real credential file's bytes and, when the
            vendor needs files beside it, the bytes `bootstrap` returns (`_seal`). `copy_in`
            copies exactly that or nothing.
        secrets: Every secret value of the real credential, as bytes, for the leak scan. Not in
            the `repr`.
        account: The account of the login, for the evidence, read from what the copy is made of.
            An identifier, not a secret.
        expires_at: When the access token ends (timezone-aware).
    """

    digest: str
    secrets: tuple[bytes, ...] = field(repr=False)
    account: str | None
    expires_at: datetime


@dataclass(frozen=True)
class Ticket:
    """What was written into a relay home.

    Attributes:
        leaf: The credential file written, as a path string.
        names: Every file written, the credential first.
        secrets: The secret values of the copy, as bytes, for the leak scan. Not in the `repr`.
        account: The account of what was written (the one `Ready` named, or the copy was refused).
    """

    leaf: str
    names: tuple[str, ...]
    secrets: tuple[bytes, ...] = field(repr=False)
    account: str | None


def _bare(name: object) -> bool:
    """Whether this is one plain name: no separator, no drive, no stream, no parent segment."""
    return (type(name) is str and bool(name) and name not in (".", "..")
            and not set(name) & set("/\\:\x00"))


def _texts(value: object, what: str) -> tuple[str, ...]:
    if type(value) is not tuple or any(type(row) is not str or not row for row in value):
        raise ValueError(f"{what} is a tuple of non-empty text")
    if len(set(value)) != len(value):
        raise ValueError(f"{what} names nothing twice")
    return value


@dataclass(frozen=True)
class RelaySpec(ABC):
    """What one harness's relay is: declared facts, and the readings of the vendor's own files.

    The fields are plain data and nothing else, because a profile that carries a spec is frozen
    into the digest an approved plan is bound to (`policy_providers`, canonical JSON): a changed
    form of the copy is a changed digest, and an old grant is refused. The behaviour is in methods.

    Attributes:
        kind: The letter that names this harness's relay homes (`c-<16 hex>`, `x-<16 hex>`).
        credential: The name of the credential file in the login home.
        files: Every file name the relay may be given, the credential among them. What a spec
            returns from `bootstrap` is among them, and `discard` and `sweep` take these first.
        secret_fields: The keys whose values are secrets, at any depth, for the leak scan.
        refresh_fields: The keys that carry a refresh token or its deadline. The copy may change
            these and nothing else, and no value of them reaches the relay.
        section: The key of the object that holds the refresh fields.
        form: The ONE declaration of the access-only copy: `(key, None)` takes a key of the
            section away, `(key, text)` sets it to the text. The pinned CLI may need the key
            present (Codex refuses a file without `refresh_token`), and that is this one value to
            change, after the live measurement of what each CLI accepts.
        forbidden_env: The names the environment of a task may not carry (`relay_env`).
    """

    kind: str
    credential: str
    files: tuple[str, ...]
    secret_fields: tuple[str, ...]
    refresh_fields: tuple[str, ...]
    section: str
    form: tuple[tuple[str, str | None], ...]
    forbidden_env: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.kind) is not str or _KIND.fullmatch(self.kind) is None:
            raise ValueError("kind is one lower-case letter")
        if not _bare(self.credential):
            raise ValueError("credential is one plain file name")
        if not all(_bare(name) for name in _texts(self.files, "files")):
            raise ValueError("files are plain file names")
        if self.credential not in self.files:
            raise ValueError("the credential is one of the files")
        _texts(self.secret_fields, "secret_fields")
        _texts(self.refresh_fields, "refresh_fields")
        if type(self.section) is not str or not self.section:
            raise ValueError("section is the key of an object")
        self._check_form()
        if not all(_ENV_NAME.fullmatch(name) for name in _texts(
                self.forbidden_env, "forbidden_env")):
            raise ValueError("forbidden_env holds environment variable names")

    def _check_form(self) -> None:
        if type(self.form) is not tuple or any(
                type(row) is not tuple or len(row) != 2 or type(row[0]) is not str
                or not (row[1] is None or type(row[1]) is str) for row in self.form):
            raise ValueError("form is a tuple of (key, None or text)")
        keys = [key for key, _value in self.form]
        if len(set(keys)) != len(keys) or not set(keys) <= set(self.refresh_fields):
            raise ValueError("the form changes refresh fields, each once, and nothing else")

    @abstractmethod
    def admit(self, doc: dict) -> str | None:
        """The code of `REFUSALS` for a credential file this build does not copy, or None."""

    @abstractmethod
    def bootstrap(self, real_home: Path) -> dict[str, bytes] | Refused:
        """The other files the vendor needs, from the real login home, or why there are none."""

    @abstractmethod
    def account(self, doc: dict, material: dict[str, bytes]) -> str | None:
        """The account of the login, for the evidence, or None.

        Read from what the copy is made of: the admitted credential document and the files
        `bootstrap` returned. It is never a second reading of the real home, so the account that is
        named is the one that is written.
        """

    @abstractmethod
    def expires_at(self, doc: dict) -> datetime | None:
        """When the access token of this credential ends (timezone-aware), or None if unknown."""

    def credman_refusal(self, real_home: Path) -> str | None:
        """The code of `REFUSALS` if the vendor would take the login out of its file, or None."""
        return None

    def strip(self, doc: dict) -> dict:
        """The access-only copy of a credential document; the document itself is not changed."""
        copied = copy.deepcopy(doc)
        body = copied.get(self.section)
        if type(body) is dict:
            for key, value in self.form:
                if value is None:
                    body.pop(key, None)
                else:
                    body[key] = value
        return copied

    def forbids(self, name: str) -> bool:
        """Whether a task's environment may not carry this name, whatever its case."""
        folded = name.casefold()
        return any(folded == own.casefold() for own in self.forbidden_env)


# --- instants ---------------------------------------------------------------------------------


def from_epoch_seconds(value: object) -> datetime | None:
    """An instant from seconds since 1970 (a number, not a flag), or None if it is no instant."""
    if type(value) not in (int, float) or not 0 < value < _LATEST:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def from_epoch_ms(value: object) -> datetime | None:
    """An instant from whole milliseconds since 1970, or None if it is no instant."""
    if type(value) is not int or not 0 < value < _LATEST * 1000:
        return None
    return _EPOCH + timedelta(milliseconds=value)


def jwt_expiry(token: object) -> datetime | None:
    """The `exp` of a JWT's payload as an instant, or None. The signature is not looked at.

    The payload is decoded as the base64url text it is, strictly, and read as JSON; the time is
    all that is taken. It is a deadline and no proof of anything, least of all of whose token this
    is.
    """
    parts = token.split(".") if type(token) is str else []
    if len(parts) != 3 or not parts[1]:
        return None
    segment = parts[1]
    try:
        raw = base64.b64decode(
            segment.replace("-", "+").replace("_", "/") + "=" * (-len(segment) % 4), validate=True)
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_refuse_constant)
    except (ValueError, RecursionError):
        return None
    return from_epoch_seconds(payload.get("exp")) if type(payload) is dict else None


# --- reading ----------------------------------------------------------------------------------


def _object(pairs):
    found: dict = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("two values for one key")
        found[key] = value
    return found


def _refuse_constant(name):
    raise ValueError(name)


def _plain(info) -> bool:
    """Whether a stat answer is an ordinary file with one name: no link, no reparse point."""
    return (stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and getattr(info, "st_reparse_tag", 0) == 0 and info.st_nlink == 1)


def _read_up_to(descriptor: int, size: int) -> bytes:
    chunks: list[bytes] = []
    while size > 0:
        chunk = os.read(descriptor, min(size, 1 << 16))
        if not chunk:
            break
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def read_leaf(path: str | os.PathLike, limit: int = CREDENTIAL_LIMIT) -> Leaf | Refused:
    """Read one credential file: an ordinary single-name file holding one strict JSON object.

    Refused, never raised: a name that is not there; a link, a junction, a reparse point, a folder
    or a file with a second hard link (`leaf_unsafe`); a file larger than `limit`; anything that is
    not UTF-8 JSON with an object at the top, two values for one key, `NaN` or `Infinity`, or
    nesting past the recursion limit. The file is looked at (`lstat`), opened, and looked at again
    through the open handle: a name swapped in between is not the file that was looked at.

    Args:
        path: The credential file.
        limit: The most it may hold, in bytes.
    """
    target = os.fspath(path)
    try:
        before = os.lstat(target)
    except (FileNotFoundError, NotADirectoryError):
        return Refused("leaf_absent")
    except (OSError, ValueError):
        return Refused("leaf_unsafe")
    if not _plain(before):
        return Refused("leaf_unsafe")
    try:
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                             | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return Refused("leaf_unsafe")
    try:
        held = os.fstat(descriptor)
        if not _plain(held) or (held.st_ino, held.st_dev) != (before.st_ino, before.st_dev):
            return Refused("leaf_unsafe")
        data = _read_up_to(descriptor, limit + 1)
    except OSError:
        return Refused("leaf_unsafe")
    finally:
        os.close(descriptor)
    if len(data) > limit:
        return Refused("leaf_too_large")
    try:
        doc = json.loads(
            data.decode("utf-8"), object_pairs_hook=_object, parse_constant=_refuse_constant)
    except (ValueError, RecursionError):
        return Refused("leaf_malformed")
    if type(doc) is not dict:
        return Refused("leaf_malformed")
    return Leaf(doc, hashlib.sha256(data).hexdigest())


def secret_values(doc: object, fields: tuple[str, ...]) -> tuple[bytes, ...]:
    """The text values of the named keys at any depth, as sorted distinct bytes for a leak scan."""
    wanted, found, pending = set(fields), set(), [doc]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key in wanted and type(value) is str and len(value) >= MIN_SECRET:
                    found.add(value.encode("utf-8", "surrogatepass"))
                if isinstance(value, (dict, list)):
                    pending.append(value)
        elif isinstance(item, list):
            pending.extend(item)
    return tuple(sorted(found))


def every_text(doc: object) -> tuple[bytes, ...]:
    """Every text value at any depth that is long enough to be a secret, as sorted distinct bytes.

    For a credential document whose shape is no longer known: which of its texts is a token cannot
    be said, so all of them are looked for.
    """
    found, pending = set(), [doc]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif type(item) is str and len(item) >= MIN_SECRET:
            found.add(item.encode("utf-8", "surrogatepass"))
    return tuple(sorted(found))


# --- readiness and the copy -------------------------------------------------------------------


def _seal(leaf_digest: str, material: dict[str, bytes]) -> str:
    """The digest of what a copy is made of: the credential and the files beside it.

    With no other file it is the credential's own digest, SHA-256 of its bytes. With files (the
    account profile of Claude) it is the SHA-256 of the credential's digest and, for each file in
    name order, the name and the SHA-256 of the bytes `bootstrap` returned. A change of what would
    be written is therefore a change of the digest, and the account named by `Ready` is the one that
    `copy_in` writes, or the copy is refused.
    """
    if not material:
        return leaf_digest
    rows = [leaf_digest, *(f"{name}\0{hashlib.sha256(data).hexdigest()}"
                           for name, data in sorted(material.items()))]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def ready(auth_home: str | os.PathLike, spec: RelaySpec, now: datetime,
          horizon: timedelta) -> Ready | Refused:
    """Whether the real login can be copied for an attempt that needs `horizon` of token life.

    The credential file is read and admitted by the spec, the vendor's credential manager and the
    account are looked at, and the access token must outlast `now + horizon`; an expiry that is not
    known is a refusal and never a guess that the token is fresh. Nothing is written or changed.
    The token is judged at the moment of the call and the answer is not kept for a cycle: an
    attempt asks again before each step.

    Args:
        auth_home: The REAL login home.
        spec: The harness's relay.
        now: The present, timezone-aware.
        horizon: How long the token must still live: the step's timeout and a margin.

    Raises:
        ValueError: `now` has no time zone, which is a fault of the caller.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    home = Path(auth_home)
    leaf = read_leaf(home / spec.credential)
    if isinstance(leaf, Refused):
        return leaf
    refused = spec.admit(leaf.doc) or spec.credman_refusal(home)
    if refused is not None:
        return Refused(refused)
    material = spec.bootstrap(home)
    if isinstance(material, Refused):
        return material
    expires = spec.expires_at(leaf.doc)
    if expires is None:
        return Refused("expiry_unknown")
    if expires - now < horizon:
        return Refused("expiry_short")
    return Ready(_seal(leaf.digest, material), secret_values(leaf.doc, spec.secret_fields),
                 spec.account(leaf.doc, material), expires)


def clock_instant(text: object) -> datetime | None:
    """The timezone-aware instant a clock text of the product names, or None.

    The product's clock is RFC 3339 text in UTC, written with a `Z`; any other offset is read as
    it is. Text that is not a time, or a time with no zone, is no instant: the caller refuses on it
    and does not guess "now".
    """
    if type(text) is not str:
        return None
    try:
        found = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError:
        return None
    return found if found.utcoffset() is not None else None


def ready_for(auth_home: str | os.PathLike, spec: RelaySpec, clock_text: str,
              timeout_seconds: int | float) -> Ready | Refused:
    """`ready` for ONE attempt: the token must outlast its timeout by `MARGIN_SECONDS`.

    Judged at the instant the product's clock names now. A clock that names no instant is a refusal
    (`expiry_unknown`), never a token taken to be fresh. The answer is for this attempt alone: the
    caller asks again before every attempt, the step after a human gate and the checker included.
    """
    now = clock_instant(clock_text)
    if now is None:
        return Refused("expiry_unknown")
    return ready(auth_home, spec, now, timedelta(seconds=timeout_seconds + MARGIN_SECONDS))


def _relay_refusal(relay: Path) -> str | None:
    """Why this is not an empty folder to copy into, or None when it is."""
    try:
        info = os.lstat(relay)
    except OSError:
        return "relay_unusable"
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_reparse_tag", 0) != 0):
        return "relay_unusable"
    try:
        with os.scandir(relay) as rows:
            return "not_empty" if any(True for _ in rows) else None
    except OSError:
        return "relay_unusable"


def _leaks_a_refresh(spec: RelaySpec, doc: dict, files: dict[str, bytes]) -> bool:
    """Whether a real refresh value stands in anything about to be written, raw or JSON-escaped."""
    for value in secret_values(doc, spec.refresh_fields):
        text = value.decode("utf-8", "surrogatepass")
        spellings = (value, json.dumps(text)[1:-1].encode("ascii"))
        if any(spelling in data for spelling in spellings for data in files.values()):
            return True
    return False


def _write_exclusively(relay: Path, files: dict[str, bytes]) -> bool:
    """Create each file new, in order. If one fails, the ones made are taken away: False."""
    written: list[str] = []
    try:
        for name, data in files.items():
            target = os.fspath(relay / name)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | getattr(os, "O_BINARY", 0), 0o600)
            written.append(target)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
    except OSError:
        for target in written:
            _try(_force, os.unlink, target)
        return False
    return True


def copy_in(auth_home: str | os.PathLike, relay_home: str | os.PathLike, spec: RelaySpec,
            digest: str) -> Ticket | Refused:
    """Write the access-only credential and the vendor's other files into an EMPTY relay home.

    The real credential file is read again, admitted again (the copy does not rest on the caller
    having asked), and what is to be written must be what `ready` saw: the credential's bytes and
    the files `bootstrap` returns, as `digest` (`_seal`; a change of spelling alone is a change).
    The relay credential is `spec.strip` of it, and the real refresh values are looked for in every
    byte about to be written, so a form that let one through is a refusal and not a leak. The files
    are created new (`O_EXCL`) in a folder that is empty, and inherit the folder's DACL. A write
    that fails takes away what was written and comes back as `write_failed`. The account of the
    `Ticket` is read from the same bytes that are written.

    The shape and the DACLs of the relay home are the runner's judgement (`relay_home`), not this
    function's: the caller proved them before it came here.

    Args:
        auth_home: The REAL login home, read and never changed.
        relay_home: The attempt's relay home: an existing empty folder.
        spec: The harness's relay.
        digest: `Ready.digest`.
    """
    home, relay = Path(auth_home), Path(relay_home)
    leaf = read_leaf(home / spec.credential)
    if isinstance(leaf, Refused):
        return leaf
    refused = spec.admit(leaf.doc)
    if refused is not None:
        return Refused(refused)
    material = spec.bootstrap(home)
    if isinstance(material, Refused):
        return material
    if spec.credential in material or not set(material) <= set(spec.files):
        raise ValueError("a spec bootstraps files it declared, and not its credential")
    if _seal(leaf.digest, material) != digest:
        return Refused("changed")
    stripped = spec.strip(leaf.doc)
    files = {spec.credential: json.dumps(stripped, separators=(",", ":")).encode("utf-8"),
             **material}
    if _leaks_a_refresh(spec, leaf.doc, files):
        return Refused("refresh_leak")
    refused = _relay_refusal(relay)
    if refused is not None:
        return Refused(refused)
    if not _write_exclusively(relay, files):
        return Refused("write_failed")
    return Ticket(str(relay / spec.credential), tuple(files),
                  secret_values(stripped, spec.secret_fields), spec.account(leaf.doc, material))


# --- taking a relay home away -----------------------------------------------------------------


def _long(path: str) -> str:
    """The absolute extended-length form on Windows (so a deep path has a name), else absolute."""
    absolute = os.path.abspath(path)
    if os.name != "nt" or absolute.startswith("\\\\?\\"):
        return absolute
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def _is_link(info) -> bool:
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) != 0


def _force(call, path: str) -> None:
    """Run a removal; if the file is read-only, make it writable once and run it again."""
    try:
        call(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        call(path)


def _try(function, *arguments) -> bool:
    """Run a cleanup step that may not become the outcome; whether it completed."""
    try:
        function(*arguments)
    except Exception:  # noqa: BLE001 -- a cleanup step may not raise past the cleanup
        return False
    return True


def _remove_link(path: str) -> None:
    """Remove a link or junction as the entry it is. Nothing it leads to is touched."""
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)


def _remove_tree(top: str) -> None:
    """Remove a name and everything under it, without recursion and without following a link."""
    pending = [(top, False)]
    while pending:
        path, listed = pending.pop()
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            continue
        if _is_link(info):
            _remove_link(path)
        elif stat.S_ISDIR(info.st_mode):
            if listed:
                _force(os.rmdir, path)
            else:
                pending.append((path, True))
                with os.scandir(path) as rows:
                    pending.extend((row.path, False) for row in rows)
        else:
            _force(os.unlink, path)


def discard(relay_home: str | os.PathLike, names: tuple[str, ...] = ()) -> bool:
    """Remove a relay home: the named credential files first, then the whole tree.

    The credentials go first so that a tree that cannot be removed (a file the child still holds)
    leaves no credential behind. `names` are plain file names in the relay home, normally
    `RelaySpec.files`; a name that is not one plain name is not followed. A link, a junction or a
    reparse point, at the home or inside it, is removed as itself and never walked through. A path
    past the classic limit is removed through its extended-length form.

    Never raises.

    Returns:
        True if nothing stands at the relay home any more, False if anything was left.
    """
    try:
        top = _long(os.fspath(relay_home))
        try:
            info = os.lstat(top)
        except FileNotFoundError:
            return True
        if _is_link(info):
            _remove_link(top)
            return not os.path.lexists(top)
        for name in names:
            if _bare(name):
                _try(_remove_tree, os.path.join(top, name))
        _remove_tree(top)
        return not os.path.lexists(top)
    except Exception:  # noqa: BLE001 -- the caller is told "not removed", it is not handed an error
        return False


def sweep(relay_root: str | os.PathLike, key: str, kind: str,
          names: tuple[str, ...] = ()) -> list[str]:
    """Remove the leftover relay homes of one project and one harness; name those that stay.

    The homes under `<relay_root>/<key>` named `<kind>-<16 hex>` are what an earlier attempt left
    (a crash, a retained home). Anything else in the key folder is not this build's to remove. A
    key folder that is not there has nothing to sweep; one that is a link or not a folder, or that
    cannot be listed, is named itself and nothing is followed.

    Args:
        relay_root: The relay folder (`DecemberCommand/relay`).
        key: The project's key folder name: 16 lower-case hex (`relay_home.relay_key`).
        kind: The harness's letter (`RelaySpec.kind`).
        names: The credential file names to take first from a home that cannot be removed.

    Returns:
        The names of the homes that were not removed, sorted; empty when all are gone.

    Raises:
        ValueError: `key` or `kind` is not a form this build makes.
    """
    if type(key) is not str or _KEY.fullmatch(key) is None:
        raise ValueError("key is 16 lower-case hex digits")
    if type(kind) is not str or _KIND.fullmatch(kind) is None:
        raise ValueError("kind is one lower-case letter")
    homes = re.compile(rf"{kind}-[0-9a-f]{{16}}\Z")
    try:
        base = os.path.join(_long(os.fspath(relay_root)), key)
        try:
            info = os.lstat(base)
        except FileNotFoundError:
            return []
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            return [key]
        with os.scandir(base) as rows:
            found = [row.name for row in rows if homes.fullmatch(row.name)]
    except Exception:  # noqa: BLE001 -- an unlistable key folder is reported, not raised
        return [key]
    return sorted(name for name in found if not discard(os.path.join(base, name), names))
