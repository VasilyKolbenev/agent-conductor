"""The pure plan of a seed: what a tree listing becomes before any byte is read (spec 9.1.2, 9.1.3).

`git ls-tree -r -l -z --full-tree <commit>` names every path of the base with its mode, type, object
id and size. From that alone this module decides what is copied, what is left out and why, which
bases the product will not seed at all, and how the bytes are asked for: in batches whose stdin the
runner accepts and whose answer cannot be cut. It touches no disk and runs no process, so every rule
of 9.1.3 is judged here without git; the staging that uses it is tested on a real repository.

The refusals are judged in one fixed order, cheapest and most structural first: a base that tracks a
name the product owns, paths that collide on a volume that folds case, too many skips, a base too
large to copy. Each is a `SeedRefusal` carrying one word of the closed list of `seed_refused`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath
from typing import NamedTuple

from .adapters.agent_instructions import AGENT_INSTRUCTION_NAMES
from .adapters.process import STDIN_LIMIT
from .api_refusals import SEED_REASONS
from .path_admission import WindowsNameError, WindowsPathError, admit_file, admit_name
from .product_names import is_product_path
from .seed_record import MAX_PATH_CHARS, Skip

SEED_MAX_FILES = 5000
SEED_MAX_BYTES = 64 * 1024 * 1024
#: Skips beyond this (instruction files not counted) refuse the seed.
MAX_SKIPS = 200
#: What one `cat-file --batch` answer may hold, and what each object adds beyond its bytes: a
#: header of at most 40 + 1 + 4 + 1 + 20 + 1 characters (more for a 64-digit id) and a trailing
#: line feed, so 128 covers both object formats.
BATCH_OUTPUT_CEILING = 16 * 1024 * 1024
OBJECT_OVERHEAD = 128
#: The characters no path component of a seeded file may hold (a Windows volume refuses them).
_FORBIDDEN = frozenset(':*?"<>|\\')
_OID = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
_META = re.compile(rb"([0-7]{6}) (blob|commit) (" + _OID.encode() + rb") +(\d+|-)\Z")
_HEADER = re.compile(rb"(" + _OID.encode() + rb") (\w+) (\d+)\Z")
_LFS_LINES = (re.compile(rb"version https://git-lfs\.github\.com/spec/v1\Z"),
              re.compile(rb"oid sha256:[0-9a-f]{64}\Z"), re.compile(rb"size \d+\Z"))
_LFS_POINTER_MAX = 1024
_INSTRUCTION_FILES = frozenset(name.casefold() for name in AGENT_INSTRUCTION_NAMES
                               if not name.endswith("/"))
_INSTRUCTION_FOLDERS = frozenset(name.rstrip("/").casefold() for name in AGENT_INSTRUCTION_NAMES
                                 if name.endswith("/"))


class SeedRefusal(Exception):
    """The base cannot be seeded; `reason` is one word of the closed list of `seed_refused`.

    `commit` names the commit that explains `base_moved` and `seed_exists` and nothing else.
    """

    def __init__(self, reason: str, commit: str | None = None) -> None:
        if reason not in SEED_REASONS:
            raise ValueError(f"a seed refusal names one of the closed list, not {reason!r}")
        super().__init__(reason)
        self.reason, self.commit = reason, commit


class TreeRow(NamedTuple):
    """One path of the base: its mode, git's type, object id, size (None for a submodule), path."""

    mode: str
    kind: str
    oid: str
    size: int | None
    path: str


@dataclass(frozen=True)
class SeedPlan:
    """What the seed will do: the rows to copy, and the paths left out, each in listing order."""

    copy: tuple[TreeRow, ...]
    skipped: tuple[Skip, ...]
    instructions_skipped: tuple[str, ...]
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class Batch:
    """One `cat-file --batch` call: the distinct objects, the stdin that names them, the limit."""

    rows: tuple[TreeRow, ...]
    stdin: bytes
    output_limit: int


def parse_listing(data: bytes) -> tuple[TreeRow, ...]:
    """The rows of `ls-tree -r -l -z` output; a row that is not the shape git prints is a refusal.

    Raises:
        SeedRefusal: `git_failed`, for output that is not a whole list of well-formed rows.
    """
    if data and not data.endswith(b"\0"):
        raise SeedRefusal("git_failed")
    return tuple(_row(raw) for raw in data.split(b"\0")[:-1])


def _row(raw: bytes) -> TreeRow:
    meta, tab, path = raw.partition(b"\t")
    found = _META.match(meta) if tab and path else None
    if found is None:
        raise SeedRefusal("git_failed")
    mode, kind, oid, size = (part.decode("ascii") for part in found.groups())
    regular = kind == "blob" and mode[:3] in ("100", "120")
    if not (regular and size != "-" or kind == "commit" and mode == "160000" and size == "-"):
        raise SeedRefusal("git_failed")
    return TreeRow(mode, kind, oid, None if size == "-" else int(size),
                   path.decode("utf-8", "surrogateescape"))


def shown(path: str) -> str:
    """`path` as the seed record keeps it: one line, control characters and surrogates escaped."""
    text = "".join(_escaped(char) for char in path)
    return text if len(text) <= MAX_PATH_CHARS else text[:MAX_PATH_CHARS - 1] + "~"


def _escaped(char: str) -> str:
    if 0xD800 <= ord(char) <= 0xDFFF:
        return f"\\u{ord(char):04x}"
    return f"\\x{ord(char):02x}" if unicodedata.category(char) == "Cc" else char


def plan_seed(rows: tuple[TreeRow, ...] | list[TreeRow], *, include_agent_instructions: bool,
              budget_roots: tuple[PurePath, ...] = (), case_insensitive: bool = False) -> SeedPlan:
    """Sort the rows of a base into copied, skipped and instruction files, or refuse the base.

    Args:
        rows: The base, from `parse_listing`.
        include_agent_instructions: Copy the instruction files and folders too (L31).
        budget_roots: The folders a copied path is measured from on Windows (the task's work
            folder and the staging folder); a `PureWindowsPath` root judges the path budget, any
            other root judges nothing.
        case_insensitive: The volume folds case (Windows, macOS): paths that differ only in case
            would land on one file.

    Raises:
        SeedRefusal: `tracks_product_dir`, `case_collision`, `too_many_skips` or `seed_too_large`.
    """
    if any(is_product_path(row.path) for row in rows):
        raise SeedRefusal("tracks_product_dir")
    copy, skipped, instructions = [], [], []
    for row in rows:
        reason = _skip_reason(row, budget_roots)
        if reason is not None:
            skipped.append(Skip(shown(row.path), reason))
        elif not include_agent_instructions and _is_instruction(row.path):
            instructions.append(shown(row.path))
        else:
            copy.append(row)
    if case_insensitive and _collides(copy):
        raise SeedRefusal("case_collision")
    if len(skipped) > MAX_SKIPS:
        raise SeedRefusal("too_many_skips")
    total = sum(row.size for row in copy)
    if (len(copy) > SEED_MAX_FILES or total > SEED_MAX_BYTES
            or any(row.size > BATCH_OUTPUT_CEILING - OBJECT_OVERHEAD for row in copy)):
        raise SeedRefusal("seed_too_large")
    return SeedPlan(tuple(copy), tuple(skipped), tuple(instructions), len(copy), total)


def _skip_reason(row: TreeRow, roots: tuple[PurePath, ...]) -> str | None:
    if row.mode == "120000":
        return "symlink"
    if row.mode == "160000":
        return "submodule"
    if not _portable(row.path):
        return "unportable_name"
    return "path_budget" if not _fits(row.path, roots) else None


def _portable(path: str) -> bool:
    """Whether every component is a name a Windows volume and a result manifest can carry."""
    for part in path.split("/"):
        if not part or part in (".", ".."):
            return False
        if any(char in _FORBIDDEN or unicodedata.category(char) == "Cc"
               or 0xD800 <= ord(char) <= 0xDFFF for char in part):
            return False
        try:
            admit_name(part, "path component")
        except WindowsNameError:
            return False
    return True


def _fits(path: str, roots: tuple[PurePath, ...]) -> bool:
    try:
        for root in roots:
            admit_file(root / path, "seeded path")
    except WindowsPathError:
        return False
    return True


def _is_instruction(path: str) -> bool:
    *folders, name = (part.casefold() for part in path.split("/"))
    return name in _INSTRUCTION_FILES or any(part in _INSTRUCTION_FOLDERS for part in folders)


def _collides(copy: list[TreeRow]) -> bool:
    """Whether two spellings of one folded prefix exist among the paths that will be written."""
    seen: dict[str, str] = {}
    for row in copy:
        parts = row.path.split("/")
        for count in range(1, len(parts) + 1):
            prefix = "/".join(parts[:count])
            if seen.setdefault(prefix.casefold(), prefix) != prefix:
                return True
    return False


def blob_batches(plan: SeedPlan) -> tuple[Batch, ...]:
    """The calls that read the bytes of a plan, each distinct object once, in listing order.

    A batch names at most `STDIN_LIMIT` bytes of ids and expects at most `BATCH_OUTPUT_CEILING`
    bytes back, each object counted at its size and `OBJECT_OVERHEAD`; a plan carries no file that
    would not fit a batch alone (`plan_seed` refuses it), so a cut answer is never a plan's fault.
    """
    distinct = list({row.oid: row for row in plan.copy}.values())
    batches: list[Batch] = []
    held: list[TreeRow] = []
    stdin = expected = 0
    for row in distinct:
        line, cost = len(row.oid) + 1, row.size + OBJECT_OVERHEAD
        if held and (stdin + line > STDIN_LIMIT or expected + cost > BATCH_OUTPUT_CEILING):
            batches.append(_batch(held, expected))
            held, stdin, expected = [], 0, 0
        held.append(row)
        stdin, expected = stdin + line, expected + cost
    return (*batches, _batch(held, expected)) if held else tuple(batches)


def _batch(rows: list[TreeRow], expected: int) -> Batch:
    stdin = "".join(f"{row.oid}\n" for row in rows).encode("ascii")
    return Batch(tuple(rows), stdin, expected)


def parse_batch(output: bytes, batch: Batch) -> dict[str, bytes]:
    """The bytes of each object of `batch` from its `cat-file --batch` answer, checked whole.

    The answer is read by the sizes it declares, never by its lines, so a blob that holds
    something shaped like a header is only bytes.

    Raises:
        SeedRefusal: `git_failed`, for an answer that is cut, reordered, carries another object,
            another type or another size than asked for, or ends in anything else.
    """
    found: dict[str, bytes] = {}
    at = 0
    for row in batch.rows:
        end = output.find(b"\n", at)
        header = _HEADER.match(output[at:end]) if end >= 0 else None
        if header is None or header.group(1).decode() != row.oid or header.group(2) != b"blob":
            raise SeedRefusal("git_failed")
        size, start = int(header.group(3)), end + 1
        if size != row.size or output[start + size:start + size + 1] != b"\n":
            raise SeedRefusal("git_failed")
        found[row.oid] = output[start:start + size]
        at = start + size + 1
    if at != len(output):
        raise SeedRefusal("git_failed")
    return found


def is_lfs_pointer(blob: bytes) -> bool:
    """Whether `blob` is exactly a Git LFS pointer: the three lines, in order, and small."""
    if len(blob) > _LFS_POINTER_MAX or not blob.endswith(b"\n"):
        return False
    lines = blob[:-1].split(b"\n")
    return len(lines) == 3 and all(pattern.match(line) for pattern, line in zip(_LFS_LINES, lines))
