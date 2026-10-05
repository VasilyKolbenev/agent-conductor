"""One shared login-directory lease; no credential is read or copied here."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import threading

from . import boot_witness, ownership_boot
from .boot_witness import BootRefused
from .ownership_errors import OwnerRefused
from .ownership_native import NativeHold, identity, stream_identity
from .ownership_records import canonical, digest, exclusive, plain

_FORMAT = {"protocol", "home", "parent", "box", "anchor"}
_LEASE = {"protocol", "format_digest", "boot", "nonce", "identity"}
_RECEIPT = {"protocol", "format_digest", "lease_nonce", "lease_identity", "lease_digest",
            "lease_boot", "prepared_boot"}
LEASE_V1 = "conduct.login-lease.v1"
#: A lease that holds the counter witness: the closed v1 record cannot carry it.
LEASE_V2 = "conduct.login-lease.v2"
RECEIPT = "conduct.login-recovery-prepared.v1"
_OLD_BOOT = re.compile(r"(?:windows|linux|darwin):[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _read(path, fields, protocol):
    allowed = (protocol,) if isinstance(protocol, str) else tuple(protocol)
    plain(path, directory=False)
    with open(path, "rb") as stream:
        payload = stream.read(8193)
    if len(payload) > 8192:
        raise OwnerRefused("login_ownership_invalid", "resource record exceeds its byte bound")
    try:
        value = json.loads(payload)
        if type(value) is not dict or set(value) != fields or value["protocol"] not in allowed:
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


def _lease_boot(value):
    if value["protocol"] == LEASE_V2:
        return boot_witness.is_counter(value["boot"])
    return type(value["boot"]) is str and _OLD_BOOT.fullmatch(value["boot"]) is not None


def _standing(box, bound):
    value = _read(box / "active.json", _LEASE, (LEASE_V1, LEASE_V2))
    if (value["format_digest"] != bound or type(value["identity"]) is not list
            or len(value["identity"]) != 2
            or any(type(part) is not int or part < 0 for part in value["identity"])
            or tuple(value["identity"]) != identity(box / "active.json")
            or type(value["nonce"]) is not str
            or re.fullmatch(r"[0-9a-f]{32}", value["nonce"]) is None
            or not _lease_boot(value)):
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
            boot = ownership_boot.measured("shared login lease")
            self.record = {"protocol": LEASE_V2 if boot_witness.is_counter(boot) else LEASE_V1,
                           "format_digest": self.bound, "boot": boot,
                           "nonce": secrets.token_hex(16)}
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


def _hold_standing(stack, auth_home):
    """The box under its lock, its standing lease read and held by identity."""
    home, box = _route(auth_home)
    _, bound = _bind(stack, home, box)
    record = _standing(box, bound)
    held = _pin(stack, box / "active.json", movable=True)
    if held.identity != tuple(record["identity"]) or held.read_bytes() != canonical(record):
        raise OwnerRefused("login_ownership_invalid",
                           "recovery lease changed before its native hold")
    return home, box, bound, record, held


def _busy():
    return OwnerRefused("login_owner_busy", "shared login recovery cannot hold its resource")


def _measure(consequence):
    try:
        return ownership_boot.current_boot()
    except BootRefused as error:
        raise OwnerRefused("login_recovery_required",
                           f"the OS boot cannot be measured, so {consequence}: {error}") from error


def _receipt_path(box, record):
    return box / ("prepared-" + record["nonce"] + ".json")


def _receipt_facts(bound, record):
    return {"format_digest": bound, "lease_nonce": record["nonce"],
            "lease_identity": record["identity"], "lease_digest": digest(canonical(record)),
            "lease_boot": record["boot"]}


def _receipt(stack, box, bound, record):
    """The preparation of this very lease, held; `None` when there is none.

    Refuses a receipt that is damaged, partial or bound to anything else than this lease's
    format, nonce, identity, canonical bytes and recorded boot.
    """
    path = _receipt_path(box, record)
    if not os.path.lexists(path):
        return None
    _pin(stack, path)
    value = _read(path, _RECEIPT, RECEIPT)
    for key, wanted in _receipt_facts(bound, record).items():
        if value[key] != wanted:
            raise OwnerRefused("login_ownership_invalid",
                               f"the recovery preparation does not belong to this lease ({key})")
    if not boot_witness.is_counter(value["prepared_boot"]):
        raise OwnerRefused("login_ownership_invalid", "the recovery preparation holds no counter")
    return value


def _write_receipt(stack, box, bound, record, current):
    path = _receipt_path(box, record)
    value = {"protocol": RECEIPT, **_receipt_facts(bound, record), "prepared_boot": current}
    exclusive(path, canonical(value))
    _pin(stack, path)
    if path.read_bytes() != canonical(value):
        raise OwnerRefused("login_ownership_invalid", "created recovery preparation was replaced")
    return value


def _not_proven(error, record_is_legacy):
    if error.code == "same_boot":
        return OwnerRefused("login_recovery_required", (
            "restart the OS before recovering the shared login lease (a full Restart: sleep, "
            "hibernate and a Fast Startup shutdown keep the same boot)"))
    if record_is_legacy:
        return OwnerRefused("login_recovery_required", (
            "the lease predates the boot counter and cannot prove a restart; run `ownership "
            "recover-login --prepare-restart`, restart the OS (a full Restart, not a shutdown), "
            "then run `ownership recover-login` again"))
    return OwnerRefused("login_recovery_required", f"no restart is proven: {error.detail}")


def _prove(record, receipt, current):
    recorded = record["boot"] if receipt is None else receipt["prepared_boot"]
    try:
        boot_witness.prove_restart(recorded, current)
    except BootRefused as error:
        raise _not_proven(error, boot_witness.is_legacy(recorded)) from error


def recover_login(auth_home):
    """A measured reboot can retire an abandoned resource; never run a login.

    A lease from before the boot counter stands on the receipt `prepare_login_recovery` wrote.
    """
    try:
        with ExitStack() as stack:
            home, box, bound, record, held = _hold_standing(stack, auth_home)
            current = _measure("no restart can be proven")
            legacy = boot_witness.is_legacy(record["boot"])
            receipt = _receipt(stack, box, bound, record) if legacy else None
            _prove(record, receipt, current)
            held.rename(box / ("recovered-" + record["nonce"] + ".json"))
            return {"state": "recovered", "resource": digest(canonical(list(identity(home))))}
    except OSError as error:
        raise _busy() from error


def prepare_login_recovery(auth_home):
    """Write the receipt a later recovery of an old lease stands on; release nothing.

    The receipt is created exclusively under the box lock and the hold on `active.json`; no token
    or auth file is read. A second call returns the first receipt's facts and writes nothing.
    """
    try:
        with ExitStack() as stack:
            home, box, bound, record, _ = _hold_standing(stack, auth_home)
            if not boot_witness.is_legacy(record["boot"]):
                raise OwnerRefused("login_recovery_required", (
                    "this lease already holds a comparable boot, so no preparation is needed: "
                    "restart the OS, then run `ownership recover-login`"))
            receipt = _receipt(stack, box, bound, record)
            created = receipt is None
            if created:
                current = _measure("no restart can be prepared")
                if not boot_witness.is_counter(current):
                    raise OwnerRefused("login_recovery_required",
                                       "this OS gives no boot counter to prepare a restart with")
                receipt = _write_receipt(stack, box, bound, record, current)
            return {"state": "recovery_prepared", "released": False, "created": created,
                    "resource": digest(canonical(list(identity(home)))),
                    "prepared_boot": receipt["prepared_boot"]}
    except OSError as error:
        raise _busy() from error
