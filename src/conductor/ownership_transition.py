"""Explicit non-executing namespace activation, rollback and crash recovery."""
from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
import secrets

from .ownership_records import (ACTIVE, ANCHOR, HOME, LEGACY, RECORDS, TREE,
    OwnerRefused, canonical, chain, digest, exclusive, fence_bytes, identity,
    plain, publish, state, validate_live)


def _stopped(confirmed):
    if confirmed is not True:
        raise OwnerRefused("legacy_writers_must_stop", "explicitly stop all legacy writers before maintenance")


def _hold(stack, path, **options):
    from .ownership_native import NativeHold
    held = NativeHold(path, **options)
    stack.callback(held.close)
    return held


def _inventory(directory):
    """A bounded exact default-stream inventory, not proof that no writer exists."""
    found, size = [], 0
    for parent, directories, files in os.walk(directory, followlinks=False):
        for name in sorted(directories):
            plain(Path(parent) / name, directory=True)
            found.append([str((Path(parent) / name).relative_to(directory)).replace("\\", "/"), "directory"])
            if len(found) > 50_000:
                raise OwnerRefused("inventory_bound", "maintenance inventory exceeds its directory bound")
        for name in sorted(files):
            path = Path(parent) / name
            facts = plain(path, directory=False)
            remaining = 512 * 1024 * 1024 - size
            if len(found) >= 50_000 or facts.st_size > remaining:
                raise OwnerRefused("inventory_bound", "maintenance inventory exceeds its explicit file/byte bound")
            with open(path, "rb") as stream:
                payload = stream.read(remaining + 1)
            if len(payload) > remaining:
                raise OwnerRefused("inventory_bound", "maintenance data grew beyond its byte bound")
            size += len(payload)
            found.append([str(path.relative_to(directory)).replace("\\", "/"), digest(payload)])
    return digest(canonical(sorted(found)))


def _settled(root):
    from .command.contracts import ActionRequest, ActionResultReceipt
    from .command.run_store import RunStore
    store = RunStore(root)
    if not store.runs_root.exists():
        return
    for folder in sorted(store.runs_root.iterdir()):
        plain(folder, directory=True)
        run = store.read(folder.name)
        if run.warnings:
            raise OwnerRefused("recovery_required", "resolve journal warnings before ownership activation")
        results = {r.value.action_id for r in run.records if type(r.value) is ActionResultReceipt}
        if any(type(r.value) is ActionRequest and r.value.action_id not in results for r in run.records):
            raise OwnerRefused("unsettled_action", "settle outstanding actions before ownership activation")


def activate(project_root, *, legacy_writers_stopped=False):
    """No automatic caller invokes this maintenance operation."""
    _stopped(legacy_writers_stopped)
    root = Path(project_root).resolve()
    try:
        plain(root, directory=True)
        if os.path.lexists(root / HOME):
            return resume_activation(root, legacy_writers_stopped=True)
        if os.path.lexists(root / ACTIVE):
            raise OwnerRefused("transition_conflict", "owned destination already exists; both sets are preserved")
        plain(root / LEGACY, directory=True)
        _settled(root)
        with ExitStack() as stack:
            _hold(stack, root, directory=True)
            source = _hold(stack, root / LEGACY, directory=True, movable=True)
            before = _inventory(root / LEGACY)
            (root / HOME).mkdir()
            (root / HOME / RECORDS).mkdir()
            exclusive(root / HOME / ANCHOR, b"")
            exclusive(root / HOME / TREE, b"")
            _hold(stack, root / HOME / ANCHOR, exclusive=True)
            nonce = secrets.token_hex(16)
            head = publish(root, None, phase="prepared", nonce=nonce,
                root_identity=list(identity(root)), data_identity=list(source.identity),
                fence_identity=None, fence_digest=digest(fence_bytes(nonce)), data_digest=before,
                session_id=None, boot_id=None, recovered_session=None)
            source.rename(root / ACTIVE)
            head = publish(root, head, phase="moved")
            return _finish_activation(root, head, stack)
    except OSError as error:
        raise OwnerRefused("transition_conflict", "activation stopped; preserve existing transition objects") from error


def resume_activation(project_root, *, legacy_writers_stopped=False):
    _stopped(legacy_writers_stopped)
    root = Path(project_root).resolve()
    try:
        with ExitStack() as stack:
            _hold(stack, root / HOME / ANCHOR, exclusive=True)
            _hold(stack, root, directory=True)
            head = chain(root)
            if identity(root) != tuple(head["root_identity"]):
                raise OwnerRefused("ownership_lost", "activation root identity changed")
            if head["phase"] == "prepared":
                head = _resume_move(root, head, stack)
            if head["phase"] != "moved":
                raise OwnerRefused("transition_conflict", "activation is not awaiting its fence")
            _hold(stack, root / ACTIVE, directory=True)
            return _finish_activation(root, head, stack)
    except OSError as error:
        raise OwnerRefused("transition_conflict", "activation cannot resume without a conflict") from error


def _resume_move(root, head, stack):
    old, new = root / LEGACY, root / ACTIVE
    if os.path.lexists(old) and not os.path.lexists(new):
        source = _hold(stack, old, directory=True, movable=True)
        if source.identity != tuple(head["data_identity"]) or _inventory(old) != head["data_digest"]:
            raise OwnerRefused("transition_conflict", "prepared source changed")
        source.rename(new)
        source.close()
    elif not os.path.lexists(old) and os.path.lexists(new):
        if identity(new) != tuple(head["data_identity"]):
            raise OwnerRefused("transition_conflict", "moved directory has another identity")
    else:
        raise OwnerRefused("transition_conflict", "ambiguous activation names; preserve both sets")
    return publish(root, head, phase="moved")


def _finish_activation(root, head, stack):
    from .ownership_native import stream_identity
    if identity(root / ACTIVE) != tuple(head["data_identity"]):
        raise OwnerRefused("ownership_lost", "moved directory identity changed")
    if _inventory(root / ACTIVE) != head["data_digest"]:
        raise OwnerRefused("transition_conflict", "data changed during maintenance")
    target = root / LEGACY
    # An existing file, even with identical nonce bytes, gives no provenance.
    with open(target, "xb") as stream:
        stream.write(fence_bytes(head["nonce"]))
        stream.flush()
        os.fsync(stream.fileno())
        created = stream_identity(stream)
    fence = _hold(stack, target)
    if fence.identity != created:
        raise OwnerRefused("transition_conflict", "newly created fence was replaced; preserve both objects")
    return publish(root, head, phase="active", fence_identity=list(created))


def rollback(project_root, *, legacy_writers_stopped=False):
    _stopped(legacy_writers_stopped)
    root = Path(project_root).resolve()
    try:
        with ExitStack() as stack:
            _hold(stack, root / HOME / ANCHOR, exclusive=True)
            _hold(stack, root / HOME / TREE, tree=True)
            _hold(stack, root, directory=True)
            head = chain(root)
            if identity(root) != tuple(head["root_identity"]):
                raise OwnerRefused("rollback_refused", "rollback root identity changed")
            if head["phase"] == "active":
                validate_live(root, head)
                if _inventory(root / ACTIVE) != head["data_digest"]:
                    raise OwnerRefused("rollback_refused", "activation data changed")
                head = publish(root, head, phase="rollback_prepared")
            if head["phase"] not in {"rollback_prepared", "fence_retired", "rolled_back"}:
                raise OwnerRefused("rollback_refused", "rollback requires no owner session or new writes")
            head = _resume_rollback(root, head, stack)
        # No session ever existed; keep the complete evidence under a unique
        # retired namespace so a later explicit activation can start afresh.
        with ExitStack() as stack:
            metadata = _hold(stack, root / HOME, directory=True, movable=True)
            metadata.rename(root / (HOME + "-retired-" + head["nonce"]))
        return head
    except OSError as error:
        raise OwnerRefused("rollback_refused", "rollback stopped without overwriting an occupied name") from error


def _rollback_fence(root, head, stack):
    target = root / HOME / "retired-fence"
    standing = target if os.path.lexists(target) else root / LEGACY
    fence = _hold(stack, standing, movable=True)
    if (fence.identity != tuple(head["fence_identity"])
            or fence.read_bytes() != fence_bytes(head["nonce"])):
        raise OwnerRefused("rollback_refused", "standing fence is foreign; preserve both names")
    if standing != target:
        fence.rename(target)
    elif os.path.lexists(root / LEGACY):
        raise OwnerRefused("rollback_refused", "legacy name occupied before data restore")
    result = publish(root, head, phase="fence_retired")
    fence.close()
    return result


def _resume_rollback(root, head, stack):
    if head["phase"] == "rollback_prepared":
        head = _rollback_fence(root, head, stack)
    retired = root / HOME / "retired-fence"
    fence = _hold(stack, retired)
    if (fence.identity != tuple(head["fence_identity"])
            or fence.read_bytes() != fence_bytes(head["nonce"])):
        raise OwnerRefused("rollback_refused", "retired fence lost its recorded identity")
    source = root / ACTIVE if os.path.lexists(root / ACTIVE) else root / LEGACY
    held = _hold(stack, source, directory=True, movable=True)
    if held.identity != tuple(head["data_identity"]) or _inventory(source) != head["data_digest"]:
        raise OwnerRefused("rollback_refused", "rollback data changed; preserve both names")
    if head["phase"] == "rolled_back":
        if source != root / LEGACY:
            raise OwnerRefused("rollback_refused", "completed rollback names another layout")
        return head
    if source != root / LEGACY:
        held.rename(root / LEGACY)
    return publish(root, head, phase="rolled_back")


def recover(project_root):
    """Close an abandoned owner only across a verified different OS boot."""
    from .ownership_native import boot_identity
    root, head = state(project_root)
    if head is None or head["phase"] != "opened":
        raise OwnerRefused("recovery_refused", "there is no abandoned owner session to recover")
    try:
        with ExitStack() as stack:
            _hold(stack, root / HOME / ANCHOR, exclusive=True)
            _hold(stack, root / HOME / TREE, tree=True)
            for path in (root, root / HOME, root / HOME / RECORDS, root / ACTIVE):
                _hold(stack, path, directory=True)
            _hold(stack, root / LEGACY)
            for path in sorted((root / HOME / RECORDS).iterdir()):
                _hold(stack, path)
            current = boot_identity()
            if current == head["boot_id"]:
                raise OwnerRefused("recovery_required", "restart the OS before recovering an uncertain writer session")
            if chain(root) != head:
                raise OwnerRefused("transition_conflict", "owner history changed during recovery")
            validate_live(root, head)
            return publish(root, head, phase="recovered", boot_id=current,
                           recovered_session=head["session_id"])
    except OSError as error:
        raise OwnerRefused("recovery_refused", "native recovery hold is unavailable") from error
