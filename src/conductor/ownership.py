"""Explicit process owner for activated projects; ownership grants no action."""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path
import secrets
import threading

from .ownership_records import (ACTIVE, ANCHOR, HOME, LEGACY, RECORDS, TREE,
    OwnerRefused, chain, publish, state, validate_live)
from .ownership_layout import init_target


_OWNERS = {}
_GUARD = threading.RLock()
_REGISTRY_PID = os.getpid()


def _same_process():
    if os.getpid() != _REGISTRY_PID:
        raise OwnerRefused("owner_required", "ownership registry belongs to another process; use a fresh executable")


def data_root(project_root):
    root, head = state(project_root)
    return root / (LEGACY if head is None or head["phase"] == "rolled_back" else ACTIVE)


def is_activated(project_root):
    """Read-only classification; an incomplete/conflicting layout still refuses."""
    _, head = state(project_root)
    return head is not None and head["phase"] != "rolled_back"


@contextmanager
def provider_write_guard(target, project_root):
    target = Path(target).resolve()
    if project_root is None:
        if any(os.path.lexists(parent / HOME) or os.path.lexists(parent / ACTIVE)
               for parent in target.parents):
            raise OwnerRefused("project_context_required", "owned provider writes require the actual project root")
        yield
        return
    root = Path(project_root).resolve()
    if target != data_root(root) / "providers.json":
        raise OwnerRefused("wrong_project_route", "provider target does not belong to this project context")
    with write_guard(root):
        yield


def require_owner(project_root):
    _same_process()
    root = Path(project_root).resolve()
    with _GUARD:
        owner = _OWNERS.get(root)
    if owner is None:
        _, head = state(root)
        code = "activation_required" if head is None or head["phase"] == "rolled_back" else "owner_required"
        raise OwnerRefused(code, "explicit activation and a live project owner are required")
    owner.check()
    return owner


@contextmanager
def write_guard(project_root):
    root, head = state(project_root)
    if head is None or head["phase"] == "rolled_back":
        yield
        return
    with require_owner(root).borrow():
        yield


def owned_write(method):
    """Store-facing translation preserves the existing typed StoreError door."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        from .command.store_errors import StoreError
        try:
            with write_guard(self.project_root):
                return method(self, *args, **kwargs)
        except OwnerRefused as error:
            raise StoreError(str(error)) from error
    return guarded


def acquire_owner(project_root):
    _same_process()
    root, head = state(project_root)
    if head is None or head["phase"] == "rolled_back":
        raise OwnerRefused("activation_required", "run the explicit ownership activate command first")
    with _GUARD:
        if root in _OWNERS:
            raise OwnerRefused("owner_busy", "this process already has a project owner")
        owner = ProjectOwner(root, head)
        _OWNERS[root] = owner
        return owner


class ProjectOwner:
    def __init__(self, root, expected):
        from .ownership_native import boot_identity
        self.root, self.pid = root, os.getpid()
        self._lock = threading.RLock()
        self._holds, self._loans, self._borrowers = [], 0, 0
        self._released, self._uncertain = False, False
        self._scope = None
        try:
            self._pin(root / HOME / ANCHOR, exclusive=True)
            head = chain(root)
            if head != expected:
                raise OwnerRefused("transition_conflict", "ownership state changed during acquisition")
            if head["phase"] == "opened":
                raise OwnerRefused("recovery_required", "previous owner did not close; recover explicitly after OS restart")
            if head["phase"] not in {"active", "closed", "recovered"}:
                raise OwnerRefused("recovery_required", "ownership transition is incomplete")
            for path in (root, root / HOME, root / HOME / RECORDS, root / ACTIVE):
                self._pin(path, directory=True)
            for path in sorted((root / HOME / RECORDS).iterdir()):
                self._pin(path)
            self._pin(root / LEGACY)
            self._tree = self._pin(root / HOME / TREE, tree=True)
            validate_live(root, head)
            self._head = publish(root, head, phase="opened", session_id=secrets.token_hex(16),
                boot_id=boot_identity(), recovered_session=None)
            self._pin(root / HOME / RECORDS / f"gen-{self._head['generation']:08d}.json")
            self._install_scope()
        except BaseException:
            self._close_holds()
            raise

    def _pin(self, path, **options):
        from .ownership_native import NativeHold
        try:
            hold = NativeHold(path, **options)
        except OSError as error:
            raise OwnerRefused("owner_busy", "native ownership hold is unavailable") from error
        self._holds.append(hold)
        return hold

    def _install_scope(self):
        from .command.adapters.process import ProcessRunner
        from .command.adapters.process_ownership_values import ProcessOwnership
        from .ownership_login import LoginScopes
        self._logins = LoginScopes()
        self._scope = ProcessOwnership(self.check, self._claim_process, self.borrow, self.borrow_login)
        ProcessRunner.ownership_scopes.install(self.root, self._scope)

    def check(self):
        if self.pid != os.getpid():
            raise OwnerRefused("owner_required", "owner belongs to another process")
        with self._lock:
            if self.pid != os.getpid() or self._released:
                raise OwnerRefused("owner_required", "owner belongs to another process or was released")
            if self._head["phase"] != "opened":
                raise OwnerRefused("owner_required", "owner session is no longer open")
            if self._uncertain:
                raise OwnerRefused("recovery_required", "a process loan did not prove retirement")
            try:
                for hold in self._holds:
                    hold.check()
                if chain(self.root) != self._head:
                    raise OwnerRefused("ownership_lost", "ownership generation changed during the session")
                validate_live(self.root, self._head)
            except OSError as error:
                raise OwnerRefused("ownership_lost", "a bound ownership object is unavailable") from error

    @contextmanager
    def borrow(self):
        self.check()
        with self._lock:
            self.check()
            self._borrowers += 1
        try:
            yield self
        finally:
            with self._lock:
                self._borrowers -= 1

    @contextmanager
    def borrow_login(self, auth_home):
        from .command.adapters.process import OwnershipError
        try:
            with self.borrow(), self._logins.borrow(auth_home):
                self.check()
                yield
        except OwnerRefused as error:
            raise OwnershipError(str(error)) from error

    def _claim_process(self):
        from .command.adapters.process_ownership_values import ProcessLease
        from .ownership_native import close_inherited
        with self._lock:
            self.check()
            extra = self._logins.claim()
            try:
                handle = self._tree.duplicate()
            except BaseException:
                if extra is not None:
                    extra.retire(True)
                raise
            self._loans += 1
        standing = [True]

        def retire(proven):
            with self._lock:
                if not standing[0]:
                    return
                standing[0] = False
                close_inherited(handle)
                if extra is not None:
                    extra.retire(proven)
                self._loans -= 1
                if proven is not True:
                    self._uncertain = True

        handles = (handle,) + (() if extra is None else extra.handles)
        return ProcessLease(handles, retire)

    def release(self):
        from .command.adapters.process import ProcessRunner
        _same_process()
        with _GUARD, self._lock:
            if self._released:
                return
            self.check()
            if self._loans or self._borrowers:
                raise OwnerRefused("owner_busy", "owner still has writers or process loans")
            self._head = publish(self.root, self._head, phase="closed")
            ProcessRunner.ownership_scopes.remove(self.root, self._scope)
            _OWNERS.pop(self.root, None)
            self._released = True
            self._close_holds()

    def _close_holds(self):
        for hold in reversed(self._holds):
            hold.close()
        self._holds.clear()

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()
