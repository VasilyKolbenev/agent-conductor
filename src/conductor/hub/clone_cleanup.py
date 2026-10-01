"""No-follow cleanup of a clone under a caller-held, admitted parent chain."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from conductor import ownership_native


class CleanupRefused(Exception):
    pass


LIMIT = 100000
_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def _facts(found, *, directory):
    if (stat.S_ISLNK(found.st_mode) or getattr(found, "st_reparse_tag", 0)
            or (not stat.S_ISDIR(found.st_mode) if directory else
                not stat.S_ISREG(found.st_mode) or found.st_nlink != 1)):
        raise CleanupRefused("portal, hardlink or irregular entry")
    return found.st_dev, found.st_ino


def remove_posix(parent_fd: int, target: Path, expected: tuple[int, int]) -> None:
    """Walk relative to pinned directory descriptors; never follow an entry name."""
    directory = os.open(target.name, _FLAGS | os.O_DIRECTORY, dir_fd=parent_fd)
    try:
        if _facts(os.fstat(directory), directory=True) != expected:
            raise CleanupRefused("target identity changed")
        remaining = [LIMIT]
        _contents(directory, remaining)
        if _facts(os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False),
                  directory=True) != expected:
            raise CleanupRefused("target identity changed")
        os.rmdir(target.name, dir_fd=parent_fd)
    finally:
        os.close(directory)


def _contents(directory: int, remaining: list[int]) -> None:
    names = []
    with os.scandir(directory) as entries:
        for entry in entries:
            remaining[0] -= 1
            if remaining[0] < 0:
                raise CleanupRefused("clone cleanup bound exceeded")
            names.append(entry.name)
    for name in names:
        found = os.stat(name, dir_fd=directory, follow_symlinks=False)
        is_dir = stat.S_ISDIR(found.st_mode)
        expected = _facts(found, directory=is_dir)
        child = os.open(name, _FLAGS | (os.O_DIRECTORY if is_dir else 0), dir_fd=directory)
        try:
            if _facts(os.fstat(child), directory=is_dir) != expected:
                raise CleanupRefused("child identity changed")
            if is_dir:
                _contents(child, remaining)
            if _facts(os.stat(name, dir_fd=directory, follow_symlinks=False),
                      directory=is_dir) != expected:
                raise CleanupRefused("child identity changed")
            if is_dir:
                os.rmdir(name, dir_fd=directory)
            else:
                os.unlink(name, dir_fd=directory)
        finally:
            os.close(child)


def remove_windows(root: Path, expected: tuple[int, int]) -> None:
    """Pin each exact object before deletion; the caller holds every ancestor."""
    root_hold = ownership_native.NativeHold(root, directory=True, movable=True)
    try:
        if tuple(root_hold.identity) != expected:
            raise CleanupRefused("target identity changed")
        _walk_windows(root, root_hold)
    finally:
        root_hold.close()


def _walk_windows(root: Path, root_hold) -> None:
    pending, count = [(root, root_hold, os.scandir(root))], 0
    try:
        while pending:
            path, hold, entries = pending[-1]
            hold.check()
            entry = next(entries, None)
            if entry is None:
                entries.close()
                hold.delete()
                pending.pop()
                continue
            child = Path(entry.path)
            found = os.lstat(child)
            directory = stat.S_ISDIR(found.st_mode)
            _facts(found, directory=directory)
            expected = tuple(ownership_native.identity(child))
            count += 1
            if count > LIMIT:
                raise CleanupRefused("clone cleanup bound exceeded")
            child_hold = ownership_native.NativeHold(child, directory=directory, movable=True)
            try:
                if (tuple(child_hold.identity) != expected
                        or tuple(child_hold.identity) != tuple(ownership_native.identity(child))):
                    raise CleanupRefused("child identity changed")
                if directory:
                    pending.append((child, child_hold, os.scandir(child)))
                else:
                    child_hold.delete()
            except BaseException:
                child_hold.close()
                raise
    finally:
        for _path, hold, entries in reversed(pending):
            entries.close()
            hold.close()
