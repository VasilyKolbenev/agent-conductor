"""The names the product owns at the top of a project folder, and how they are kept out of git.

Every name is imported from the constant that owns it and never spelled a second time, so a name
the product renames moves here by itself. The harness folders come from the harness modules; a
guard rebuilds the expected list from the provider catalog, so a harness that is added and not
listed here turns a test red (spec 9.2, L14).
"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from ..ownership_records import ACTIVE, HOME, LEGACY
from .adapters import claude_code, codex_cli, dsh_harness, grok_build, kimi_code
from .adapters.harness_workspace import INSTRUCTION_DIR
from .work_layout import WORK_DIR

#: The staging folder a task's seed is prepared in before it moves under `work/` (spec 9.1.2).
SEED_STAGING_DIR = ".conduct-seed"
#: What a retired ownership folder is renamed to; `ownership_transition` appends a nonce to it.
RETIRED_PATTERN = f"{HOME}-retired-*"
#: The harness modules whose own home folder and marker sit beneath a project root, in the order
#: the exclude block lists them.
_HARNESSES = (claude_code, codex_cli, grok_build, kimi_code, dsh_harness)
_HARNESS_NAMES = tuple((module.HOME_DIR, module.MARKER_DIR) for module in _HARNESSES)

#: One constant for every top-level name a project folder holds because of the product.
PRODUCT_TOP_NAMES = (
    HOME, LEGACY, ACTIVE, RETIRED_PATTERN, SEED_STAGING_DIR, WORK_DIR, INSTRUCTION_DIR,
    *(name for pair in _HARNESS_NAMES for name in pair),
)

#: Files and folders that carry instructions for an agent. A trailing slash marks a folder. Found
#: at any depth and compared without regard to case (spec 6.2.1); never copied by default.
AGENT_INSTRUCTION_NAMES = ("AGENTS.md", "CLAUDE.md", ".claude/", ".codex/", ".grok/", ".kimi/")

#: The lines of the block written into `.git/info/exclude`: the single spelling of spec 9.2.
#: Folders end in a slash; a harness marker has none, so it is excluded whatever it is.
EXCLUDE_LINES = (
    f"/{LEGACY}/", f"/{ACTIVE}/", f"/{HOME}*", f"/{WORK_DIR}/", f"/{INSTRUCTION_DIR}/",
    *(line for home, marker in _HARNESS_NAMES for line in (f"/{home}/", f"/{marker}")),
)

#: The two lines that mark the block, matched exactly (a trailing space or carriage return is
#: tolerated), so a later change of the note line still finds a block an older build wrote.
BLOCK_BEGIN = "# conduct"
BLOCK_END = "# /conduct"
#: Between the markers, before the names: what a person reading the file is told.
BLOCK_NOTE = "# Folders the product keeps in this project. Local only; this file is not committed."


class ExcludeWriteError(Exception):
    """The exclude file could not be written; nothing was changed and no path is named."""

    code = "git_exclude_failed"


def write_exclude_block(git_dir: str | os.PathLike[str]) -> str:
    """Put the product's marked block into `<git_dir>/info/exclude`, without running git.

    Args:
        git_dir: The `.git` entry of a project folder.

    Returns:
        `not_git` when there is no such entry; `deferred` when it is not a plain folder (a linked
        worktree keeps its exclude elsewhere, and a visible step of the child writes it);
        `present` when the block is already there and equal; otherwise `written`. The owner's
        lines are kept byte for byte and only the marked block is replaced.

    Raises:
        ExcludeWriteError: The block could not be written, or the file is a shape this writer will
            not follow (a link, a folder where a file belongs, a block with no end marker).
    """
    git = Path(git_dir)
    kind = _kind(git)
    if kind is None:
        return "not_git"
    if kind != stat.S_IFDIR:
        return "deferred"
    info = git / "info"
    _plain_folder(info)
    target = info / "exclude"
    current = _read_plain_file(target)
    updated = _with_block(current)
    if updated == current:
        return "present"
    _replace_file(target, updated)
    return "written"


def _kind(path: Path) -> int | None:
    """The file type of `path` without following a link, or None when nothing is there."""
    try:
        return stat.S_IFMT(os.lstat(path).st_mode)
    except FileNotFoundError:
        return None
    except OSError:
        raise ExcludeWriteError("the git folder could not be read") from None


def _plain_folder(path: Path) -> None:
    """`path` is a real folder, made now when it is missing (one level, never a route)."""
    kind = _kind(path)
    if kind is None:
        try:
            os.mkdir(path)
        except OSError:
            raise ExcludeWriteError("the info folder could not be made") from None
    elif kind != stat.S_IFDIR:
        raise ExcludeWriteError("the info entry is not a plain folder")


def _read_plain_file(path: Path) -> bytes:
    """The bytes of a regular file, empty when it is absent, a refusal for anything else."""
    kind = _kind(path)
    if kind is None:
        return b""
    if kind != stat.S_IFREG:
        raise ExcludeWriteError("the exclude entry is not a plain file")
    try:
        return path.read_bytes()
    except OSError:
        raise ExcludeWriteError("the exclude file could not be read") from None


def _with_block(current: bytes) -> bytes:
    """`current` with the block inserted, or with the existing block replaced by this one."""
    newline = b"\r\n" if b"\r\n" in current else b"\n"
    lines = [BLOCK_BEGIN, BLOCK_NOTE, *EXCLUDE_LINES, BLOCK_END]
    block = newline.join(line.encode("ascii") for line in lines) + newline
    rows = current.splitlines(keepends=True)
    start = _marker(rows, BLOCK_BEGIN, 0)
    if start is None:
        gap = newline if current and not current.endswith((b"\n", b"\r")) else b""
        return current + gap + block
    end = _marker(rows, BLOCK_END, start + 1)
    if end is None:
        raise ExcludeWriteError("the block has no end marker; the file was left as it is")
    return b"".join(rows[:start]) + block + b"".join(rows[end + 1:])


def _marker(rows: list[bytes], marker: str, first: int) -> int | None:
    """The index of the first row from `first` on that is exactly `marker`."""
    wanted = marker.encode("ascii")
    return next((n for n in range(first, len(rows)) if rows[n].rstrip(b"\r\n \t") == wanted), None)


def _replace_file(target: Path, content: bytes) -> None:
    """Write `content` beside `target` and swap it in, so a reader sees the old or the new file."""
    scratch = target.with_name(f"exclude.{secrets.token_hex(4)}.tmp")
    try:
        with open(scratch, "xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(scratch, target)
    except OSError:
        raise ExcludeWriteError("the exclude file could not be written") from None
    finally:
        try:
            os.unlink(scratch)
        except OSError:
            pass
