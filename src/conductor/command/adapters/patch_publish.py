"""Publish validated task-file images under the workspace turn; never rerun a patch on recovery."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ... import atomic_replace
from ..long_path import extended
from .codex_patch import PatchRefused, file_image, remaining
from .harness_workspace import WorkspaceNotContained


class PublishUnknown(Exception):
    """The protected task tree could not be proved restored. Keep its action claimed."""


def _replace_existing(staged, target):
    if os.name != "nt":
        os.replace(staged, target)
        return
    # ReplaceFile keeps the destination DACL on Windows. os.replace would install the
    # temp file's inherited ACL, losing any file-specific restrictions in the work item.
    import ctypes
    from ctypes import wintypes
    replace = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR] * 3 + [wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL
    if not replace(str(target), str(staged), None, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def _change(workspace, args, name, expected, desired):
    path, seen = file_image(workspace, args, name)
    if seen != expected:
        raise PatchRefused("task file changed before publication")
    path = Path(extended(path))
    if desired is None:
        path.unlink()
        return

    def install(staged, target):
        current, image = file_image(workspace, args, name)
        if Path(extended(current)) != target or image != expected:
            raise PatchRefused("task file changed during publication")
        mode, _ = desired
        staged.chmod(mode)
        if expected is None:
            os.link(staged, target)  # atomic no-clobber publication
        else:
            _replace_existing(staged, target)

    atomic_replace.replace_bytes(path, desired[1], replace=install)


def _take_deleted(workspace, args, name, expected):
    path, image = file_image(workspace, args, name)
    if image != expected:
        raise PatchRefused("task file changed before deletion")
    path = Path(extended(path))
    fd, raw = tempfile.mkstemp(prefix=".do-delete-", dir=path.parent)
    os.close(fd)
    backup = Path(raw)
    try:
        os.replace(path, backup)
    except OSError:
        backup.unlink()
        raise
    return backup


def publish(workspace, args, originals, proposed, deadline):
    changed = [name for name in originals if originals[name] != proposed[name]]
    if not changed:
        raise PatchRefused("patch made no changes")
    attempted = []
    deleted = {}
    try:
        for name in changed:
            remaining(deadline)
            attempted.append(name)
            if proposed[name] is None:
                deleted[name] = _take_deleted(workspace, args, name, originals[name])
            else:
                _change(workspace, args, name, originals[name], proposed[name])
        if any(file_image(workspace, args, name)[1] != proposed[name] for name in changed):
            raise PatchRefused("published bytes could not be confirmed")
        remaining(deadline)
    except (OSError, WorkspaceNotContained, PatchRefused):
        try:
            for name in reversed(attempted):
                path, current = file_image(workspace, args, name)
                if name in deleted:
                    # No clobber on rollback. Restore the same file object, including its DACL.
                    os.link(deleted[name], extended(path))
                    deleted[name].unlink()
                elif current != originals[name]:
                    _change(workspace, args, name, proposed[name], originals[name])
                if file_image(workspace, args, name)[1] != originals[name]:
                    raise PublishUnknown()
        except (OSError, WorkspaceNotContained, PatchRefused):
            raise PublishUnknown() from None
        raise PatchRefused("patch publication failed; no proposed changes remain") from None
    try:
        for backup in deleted.values():
            backup.unlink()
    except OSError:
        raise PublishUnknown() from None
