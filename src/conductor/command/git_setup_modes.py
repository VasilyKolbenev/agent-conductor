"""One decision of the Git mode of a file, and the versioned digest of what the person is shown.

The executable bit is part of what the first-commit preview shows and seals (review ruling OD-7).
`effective_git_mode` is called by the preview and nowhere else; the value it returns travels with
the row to the tree build, which never looks at the file's mode or at `core.filemode` again, so
there is no second place that could disagree with what the person was shown.
"""
from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .accept_manifest import sha256
from .project_git import GitReadFailed
from .project_git_state import _checked

#: The scope of `paths_digest`. Version 1 sealed the bare list of rows; version 2 seals the
#: versioned object that also carries each row's Git mode, so no digest of the old scope can ever
#: equal a digest of this one.
DIGEST_VERSION = 2


def effective_git_mode(filemode: bool, st_mode: int, *, posix: bool = os.name != "nt") -> str:
    """The mode `git add` stores for a new regular file.

    `100755` exactly when `core.filemode` is not false and the owner execute bit is set; every
    other permission bit and every other attribute of the file stays out. Where the platform has
    no execute bit of its own (`posix` false: Windows), the bit in `st_mode` is not read at all:
    CPython invents it from a `.bat`, `.cmd`, `.com` or `.exe` name, while Git for Windows
    stores `100644` for those names under every `core.filemode` setting (measured).
    """
    return "100755" if filemode and posix and st_mode & stat.S_IXUSR else "100644"


def core_filemode(root: Path, git: Callable[..., Any]) -> bool:
    """The repository's `core.filemode`; an absent setting is true, as Git treats it.

    Raises:
        GitReadFailed: Git refused the question or gave an answer that is not a boolean.
    """
    answer = git(["--no-optional-locks", "-C", str(root), "config", "--bool", "--get",
                  "core.filemode"], True)
    value = _checked(answer, absent=True).strip()
    if value not in (b"", b"true", b"false"):
        raise GitReadFailed("git_failed")
    return value != b"false"


def canonical(files: list[dict]) -> bytes:
    """The string `paths_digest` is taken over: the version is part of it."""
    body = {"digest_version": DIGEST_VERSION, "files": files}
    raw = json.dumps(body, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return raw.encode("ascii")


def paths_digest(files: list[dict]) -> str:
    """`sha256:<hex>` of the canonical versioned list of rows."""
    return sha256(canonical(files))
