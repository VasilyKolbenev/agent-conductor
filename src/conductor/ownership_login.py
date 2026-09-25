"""One shared login-directory lease; no credential is read or copied here."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import threading

from .ownership_errors import OwnerRefused
from .ownership_native import NativeHold, boot_identity, identity, stream_identity
from .ownership_records import canonical, digest, exclusive, plain

_FORMAT = {"protocol", "home", "parent", "box", "anchor"}
_LEASE = {"protocol", "format_digest", "boot", "nonce", "identity"}


def _read(path, fields, protocol):
    plain(path, directory=False)
    with open(path, "rb") as stream:
        payload = stream.read(8193)
    if len(payload) > 8192:
        raise OwnerRefused("login_ownership_invalid", "resource record exceeds its byte bound")
    try:
        value = json.loads(payload)
        if type(value) is not dict or set(value) != fields or value["protocol"] != protocol:
            raise ValueError("closed record shape")
        if canonical(value) != payload:
            raise ValueError("canonical record")
    except (ValueError, UnicodeError, TypeError) as error:
        raise OwnerRefused("login_ownership_invalid", "resource record is incomplete or malformed") from error
    return value


def _route(auth_home):
    home = Path(auth_home)
    if not home.is_absolute():
        raise OwnerRefused("login_context_required", "resource hold requires an absolute configured login directory")
    home = home.resolve()
    plain(home, directory=True)
    key = digest(canonical(list(identity(home)))).split(":")[1]
    return home, home.parent / (".conduct-login-" + key)


def _prepare(home, box):
    try:
        box.mkdir()
    except FileExistsError:
        plain(box, directory=True)
    else:
        exclusive(box / "anchor", b"")
        facts = {"protocol": "conduct.login-owner.v1", "home": list(identity(home)),
                 "parent": list(identity(home.parent)), "box": list(identity(box)),
                 "anchor": list(identity(box / "anchor"))}
        exclusive(box / "format.json", canonical(facts))


def _pin(stack, path, **options):
    hold = NativeHold(path, **options)
    stack.callback(hold.close)
    return hold


def _bind(stack, home, box):
    for path in (home.parent, home, box):
        _pin(stack, path, directory=True)
    anchor = _pin(stack, box / "anchor", exclusive=True, tree=True)
    _pin(stack, box / "format.json")
    facts = _read(box / "format.json", _FORMAT, "conduct.login-owner.v1")
    expected = {"protocol": "conduct.login-owner.v1", "home": list(identity(home)),
                "parent": list(identity(home.parent)), "box": list(identity(box)),
                "anchor": list(anchor.identity)}
    if facts != expected:
        raise OwnerRefused("login_ownership_invalid", "shared resource identities changed")
    return anchor, digest(canonical(facts))


def _standing(box, bound):
    value = _read(box / "active.json", _LEASE, "conduct.login-lease.v1")
    if (value["format_digest"] != bound or type(value["identity"]) is not list
            or len(value["identity"]) != 2
            or any(type(part) is not int or part < 0 for part in value["identity"])
            or tuple(value["identity"]) != identity(box / "active.json")
            or type(value["nonce"]) is not str
            or re.fullmatch(r"[0-9a-f]{32}", value["nonce"]) is None
            or type(value["boot"]) is not str
            or re.fullmatch(r"(?:windows|linux|darwin):[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value["boot"]) is None):
        raise OwnerRefused("login_ownership_invalid", "shared resource lease lost its subject")
    return value


class LoginLease:
    def __init__(self, auth_home):
        self.stack, self._lock = ExitStack(), threading.RLock()
        self.loans, self.uncertain = 0, False
        self.home, self.box = _route(auth_home)
        try:
            _prepare(self.home, self.box)
            self.anchor, self.bound = _bind(self.stack, self.home, self.box)
            if os.path.lexists(self.box / "active.json"):
                _standing(self.box, self.bound)
                raise OwnerRefused("login_recovery_required", "shared login has an unclosed lease; recover explicitly after OS restart")
            self.record = {"protocol": "conduct.login-lease.v1", "format_digest": self.bound,
                           "boot": boot_identity(), "nonce": secrets.token_hex(16)}
            self._publish()
        except BaseException:
            self.stack.close()
            raise

    def _publish(self):
        target = self.box / "active.json"
        with open(target, "xb") as stream:
            created = stream_identity(stream)
            self.record["identity"] = list(created)
            stream.write(canonical(self.record))
            stream.flush()
            os.fsync(stream.fileno())
        self.active = _pin(self.stack, target, movable=True)
        if self.active.identity != created or self.active.read_bytes() != canonical(self.record):
            raise OwnerRefused("login_ownership_invalid", "created resource lease was replaced")

    def claim(self):
        from .command.adapters.process_ownership_values import ProcessLease
        from .ownership_native import close_inherited
        with self._lock:
            self.check()
            handle = self.anchor.duplicate()
            self.loans += 1
        standing = [True]

        def retire(proven):
            with self._lock:
                if not standing[0]:
                    return
                standing[0] = False
                close_inherited(handle)
                self.loans -= 1
                if proven is not True:
                    self.uncertain = True

        return ProcessLease((handle,), retire)

    def check(self):
        self.anchor.check()
        self.active.check()
        if (self.uncertain or self.active.read_bytes() != canonical(self.record)
                or list(identity(self.home)) != _read(
                    self.box / "format.json", _FORMAT, "conduct.login-owner.v1")["home"]):
            raise OwnerRefused("login_recovery_required", "shared resource lease is uncertain")

    def close(self):
        try:
            with self._lock:
                self.check()
                if self.loans:
                    raise OwnerRefused("login_recovery_required", "shared resource still has native process loans")
                self.active.rename(self.box / ("closed-" + self.record["nonce"] + ".json"))
        finally:
            self.stack.close()


class LoginScopes:
    """One resource for the current attempt thread; no global provider routing."""
    def __init__(self):
        self.local = threading.local()

    @contextmanager
    def borrow(self, auth_home):
        if getattr(self.local, "lease", None) is not None:
            raise OwnerRefused("login_owner_busy", "nested login lifetimes are not supported")
        lease = None
        try:
            lease = LoginLease(auth_home)
            self.local.lease = lease
            try:
                yield
            except BaseException:
                lease.uncertain = True
                raise
            finally:
                lease.close()
        except OSError as error:
            raise OwnerRefused("login_owner_busy", "native shared login resource hold is unavailable") from error
        finally:
            self.local.lease = None

    def claim(self):
        lease = getattr(self.local, "lease", None)
        return None if lease is None else lease.claim()


def recover_login(auth_home):
    """A measured reboot can retire an abandoned resource; never run a login."""
    try:
        home, box = _route(auth_home)
        with ExitStack() as stack:
            _, bound = _bind(stack, home, box)
            record = _standing(box, bound)
            held = _pin(stack, box / "active.json", movable=True)
            if held.identity != tuple(record["identity"]) or held.read_bytes() != canonical(record):
                raise OwnerRefused("login_ownership_invalid", "recovery lease changed before its native hold")
            if record["boot"] == boot_identity():
                raise OwnerRefused("login_recovery_required", "restart the OS before recovering the shared login lease")
            held.rename(box / ("recovered-" + record["nonce"] + ".json"))
            return {"state": "recovered", "resource": digest(canonical(list(identity(home))))}
    except OSError as error:
        raise OwnerRefused("login_owner_busy", "shared login recovery cannot hold its resource") from error
