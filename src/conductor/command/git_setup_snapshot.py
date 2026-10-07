"""Read-only first-commit paths: raw seals and the owner's actual clean-filter OIDs."""
from __future__ import annotations

import hashlib
import json
import os
import stat

from .accept_manifest import SnapshotRefused, _path
from .containment import first_directory_violation, portal_violation
from .git_setup_facts import call, first_facts
from .git_setup_modes import DIGEST_VERSION, core_filemode, effective_git_mode, paths_digest
from .git_setup_records import SetupRefused
from .product_names import is_product_path
from .project_git_state import _names
from .seed_plan import shown

MAX_FILES = 5000
LISTING_LIMIT = 4 * 1024 * 1024


def preview(root, git, mode):
    facts = first_facts(root, git)
    files, manual, warnings, sealed = [], [], [], {}
    if facts["signing"]:
        warnings.append("signing_required")
    if mode == "snapshot":
        filemode = core_filemode(root, git)
        names = _names(call(root, git, "ls-files", "--others", "--exclude-standard", "-z",
                            output_limit=LISTING_LIMIT))
        names = sorted(path for path in names if not is_product_path(path))
        if len(names) > MAX_FILES:
            raise SetupRefused("too_many_files")
        for name in names:
            problem = _manual(root, name)
            if problem is not None:
                manual.append({"path": shown(name), "reason": problem})
                continue
            sealed[name] = _raw(root, name)
            length, digest, found = sealed[name]
            files.append(dict(path=name, length=length, sha256=digest,
                              git_mode=effective_git_mode(filemode, found)))
            if any(word in name.casefold()
                   for word in ("secret", ".env", "credential", "private", ".pem")):
                warnings.append("suspicious_name")
        _filtered(root, git, files, facts["object_format"])
        for row in files:
            if _raw(root, row["path"]) != sealed[row["path"]]:
                raise SetupRefused("paths_changed")
    if first_facts(root, git) != facts:
        raise SetupRefused("paths_changed")
    return dict(step="first_commit", mode=mode, **facts, files=files, manual=manual,
                warnings=sorted(set(warnings)), digest_version=DIGEST_VERSION,
                paths_digest=paths_digest(files))


def _manual(root, name):
    try:
        name.encode("utf-8")
        _path(name)
    except (UnicodeError, SnapshotRefused):
        return "unportable_name"
    path = root.joinpath(*name.split("/"))
    ancestors = [root.joinpath(*name.split("/")[:i]) for i in range(len(name.split("/")))]
    violation = first_directory_violation(ancestors)
    if violation is not None:
        return violation.code.value
    entry = os.lstat(path)
    violation = portal_violation(path, entry)
    if violation is not None:
        return violation.code.value
    if not stat.S_ISREG(entry.st_mode):
        return "irregular_file"
    return "hard_link" if entry.st_nlink != 1 else None


def _raw(root, name):
    if _manual(root, name) is not None:
        raise SetupRefused("paths_changed")
    path = root.joinpath(*name.split("/"))
    before = os.lstat(path)
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        found = os.fstat(stream.fileno())
        if _open_stamp(found) != _open_stamp(before):
            raise SetupRefused("paths_changed")
        while count < before.st_size:
            chunk = stream.read(min(128 * 1024, before.st_size - count))
            if not chunk:
                raise SetupRefused("paths_changed")
            digest.update(chunk)
            count += len(chunk)
        if stream.read(1) or _open_stamp(os.fstat(stream.fileno())) != _open_stamp(before):
            raise SetupRefused("paths_changed")
    if (_manual(root, name) is not None or _stamp(os.lstat(path)) != _stamp(before)
            or count != before.st_size):
        raise SetupRefused("paths_changed")
    return count, "sha256:" + digest.hexdigest(), before.st_mode


def _stamp(found):
    """The path-based look at a file: what `_open_stamp` holds, and its mode."""
    return (*_open_stamp(found), found.st_mode)


def _open_stamp(found):
    """What a look by path and a look by open handle must agree on. The mode is left out: on
    Windows a handle reports no execute bit, while the same file looked at by its path carries
    it when the name ends in `.bat`, `.cmd`, `.com` or `.exe`. The mode is compared between
    two looks by path, never between a path and a handle."""
    return found.st_dev, found.st_ino, found.st_size, found.st_mtime_ns, found.st_nlink


def _filtered(root, git, files, object_format):
    pending, rows, size = [], [], 0
    for row in files:
        quoted = json.dumps((root / row["path"]).as_posix(), ensure_ascii=False)
        line = (quoted + "\n").encode("utf-8")
        if size + len(line) > 128 * 1024:
            _batch(root, git, rows, pending, object_format)
            pending, rows, size = [], [], 0
        pending.append(line)
        rows.append(row)
        size += len(line)
    if pending:
        _batch(root, git, rows, pending, object_format)


def _batch(root, git, rows, lines, object_format):
    raw = call(root, git, f"--work-tree={root}", "hash-object", "--stdin-paths",
               stdin=b"".join(lines))
    ids = raw.decode("ascii").splitlines()
    length = 40 if object_format == "sha1" else 64
    hexadecimal = "0123456789abcdef"
    if len(ids) != len(rows) or any(
            len(oid) != length or any(c not in hexadecimal for c in oid) for oid in ids):
        raise SetupRefused("git_failed")
    for row, oid in zip(rows, ids):
        row["git_oid"] = oid
