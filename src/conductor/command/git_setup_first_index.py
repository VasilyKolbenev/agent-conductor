"""The index bytes a first commit installs: one verified format, and a marker for each operation.

Review ruling OD-11. The product installs an index it built itself, and later asks "is this
`index.lock` mine?" of bytes it meets in a repository. Bytes that equal the plain bytes of Git
prove nothing: the owner's own Git writes the very same file for an empty tree. So the bytes this
product installs carry an optional extension, `CNDT`, holding the nonce of the operation and a
hash of its terms, and ownership is the whole binding (`verify_binding`), never the marker alone.

This is not an editor of foreign indexes. It judges what the product builds, and refuses anything
else; it never rewrites a byte it did not add. The format it accepts is small and exact:

* a size of at most `INDEX_LIMIT`, `DIRC`, version 2, at most `MAX_ENTRIES` entries;
* every entry inside the data, with a name that fits, no NUL in it, stage 0, no extended flag,
  names strictly ascending, and the padding of NULs the layout asks for;
* the extensions `TREE` and `CNDT` only, each at most once, each inside the data, `CNDT` last;
* a checksum in the repository's hash format (SHA-1 or SHA-256) that is not zero and equals the
  hash of everything before it.

An end-of-entries extension (`EOIE`) is not handled: it is kept out. Settings of the owner's own
repository (threaded reads, an index version, a skipped hash, a split index, an untracked cache,
a file monitor) change the bytes Git writes, so every index command of the product carries
`INDEX_PIN` after the flags of every Git call (`project_git.GIT_FLAGS`), and `verify` refuses
every extension but the two above, `EOIE` and the monitor's `FSMN` included. A setting that the
pin does not name shows up as such a refusal, never as bytes that pass. A refusal is the
product's own `IndexFormatRefused`; the caller maps it to its closed refusal word.

The file monitor is switched off with an EMPTY value, never with `false`: Git 2.31 reads the value
of `core.fsmonitor` as the path of a hook program, so `false` names the program `false` and every
index it writes carries an `FSMN` extension (measured), where later Gits read `false` as a
boolean. The empty value is "off" in both. The flags of every Git call and the environment
(`tool_env`) say the same empty value, and the pin keeps its own copy after the flags, so a change
of those two cannot take the monitor out of the pin's keeping.

The marker costs one line on the standard error of a Git that does not know the extension, at each
read of the index until Git's next write. The product neither hides that line nor rewrites the
installed index to remove the marker.

Nothing here runs a process or touches a file: bytes in, a verdict out.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass

from .accept_manifest import sha256
from .git_setup_first_records import INDEX_LIMIT, Op
from .git_setup_snapshot import MAX_FILES

#: The settings of the repository that are measured to change the bytes Git writes for an index,
#: each set off on the command line of every index command the product runs (`-c key=value`
#: pairs; the pin goes after `project_git.GIT_FLAGS`). The monitor's value is empty, see above.
INDEX_PIN = ("-c", "core.splitIndex=false", "-c", "index.version=2", "-c", "index.skipHash=false",
             "-c", "index.recordEndOfIndexEntries=false", "-c", "index.threads=1",
             "-c", "core.untrackedCache=false", "-c", "index.sparse=false",
             "-c", "core.fsmonitor=")
#: The extension of the operation. A capital first letter makes it OPTIONAL: a lower-case one is
#: required, and every Git that reads such an index dies (measured, exit 128).
SIGNATURE = b"CNDT"
MAX_ENTRIES = MAX_FILES
REASONS = frozenset({
    "too_large", "too_short", "object_format", "checksum_zero", "checksum", "signature", "version",
    "entry_count", "entry_bounds", "name_length", "name_nul", "name_order", "stage",
    "extended_flag", "padding", "extension_header", "extension_bounds", "extension_duplicate",
    "extension_not_allowed", "marker_position", "marker_payload", "tree_extension"})

_HASH_SIZE = {"sha1": 20, "sha256": 32}
_HEADER = struct.Struct(">4sII")
_EXTENSION = struct.Struct(">4sI")
_STAT_BYTES = 40                  # ten 32-bit stat fields before the object name of an entry
_NAME_MASK, _STAGE_MASK, _EXTENDED = 0x0FFF, 0x3000, 0x4000
_ROOT = re.compile(rb"\x00(-1|[0-9]{1,10}) [0-9]{1,10}\n")
_MARKER = re.compile(rb"v1;nonce=([0-9a-f]{16});terms=([0-9a-f]{64})")
_NONCE, _TERMS = re.compile(r"[0-9a-f]{16}"), re.compile(r"[0-9a-f]{64}")


class IndexFormatRefused(Exception):
    """The bytes are outside the verified format; `reason` is one word of `REASONS`."""

    def __init__(self, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"not a reason of the index format: {reason!r}")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class IndexShape:
    """What a verified index holds: its entry count, its extensions in order, the root of its
    cache tree (None when that root is invalidated or absent) and its marker (nonce, terms)."""

    entries: int
    extensions: tuple[str, ...]
    tree_root: str | None
    marker: tuple[str, str] | None


@dataclass(frozen=True)
class Binding:
    """What makes bytes THIS operation's: every part must hold, the marker alone never does."""

    nonce: str
    install_sha256: str
    terms: str                    # sha256 hex of the canonical terms, see `terms_hash`
    expected_tree: str
    object_format: str
    file_count: int


def terms_hash(*, nonce: str, mode: str, digest_version: int, paths_digest: str | None,
               target_ref: str, object_format: str, expected_tree: str, file_count: int) -> str:
    """The hash the marker carries: the operation's terms, but not its commit (the signed road
    has no commit when the bytes are marked) and not its install bytes (it is inside them)."""
    row = dict(nonce=nonce, mode=mode, digest_version=digest_version, paths_digest=paths_digest,
               target_ref=target_ref, object_format=object_format, expected_tree=expected_tree,
               file_count=file_count)
    raw = json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def binding_of(op: Op) -> Binding:
    """The binding of a VERIFIED op record (`read_op` has already checked its install bytes)."""
    terms = terms_hash(nonce=op.nonce, mode=op.mode, digest_version=op.digest_version,
                       paths_digest=op.paths_digest, target_ref=op.target_ref,
                       object_format=op.object_format, expected_tree=op.expected_tree,
                       file_count=op.file_count)
    return Binding(op.nonce, op.install_sha256, terms, op.expected_tree, op.object_format,
                   op.file_count)


def _hash_size(object_format: str) -> int:
    if type(object_format) is not str or object_format not in _HASH_SIZE:
        raise IndexFormatRefused("object_format")
    return _HASH_SIZE[object_format]


def _end_of_body(data: bytes, object_format: str, size: int) -> int:
    """Judge the size and the checksum before anything is parsed; return where the trailer is."""
    if len(data) > INDEX_LIMIT:
        raise IndexFormatRefused("too_large")
    end = len(data) - size
    if end < _HEADER.size:
        raise IndexFormatRefused("too_short")
    if data[end:] == bytes(size):
        raise IndexFormatRefused("checksum_zero")
    if hashlib.new(object_format, memoryview(data)[:end]).digest() != data[end:]:
        raise IndexFormatRefused("checksum")
    return end


def _entry_count(data: bytes) -> int:
    signature, version, count = _HEADER.unpack_from(data)
    if signature != b"DIRC":
        raise IndexFormatRefused("signature")
    if version != 2:
        raise IndexFormatRefused("version")
    if count > MAX_ENTRIES:
        raise IndexFormatRefused("entry_count")
    return count


def _entry(data: bytes, offset: int, end: int, size: int,
           previous: bytes | None) -> tuple[int, bytes]:
    """Judge the entry at `offset`; return where the next one starts and this one's name."""
    fixed = _STAT_BYTES + size + 2
    if offset + fixed > end:
        raise IndexFormatRefused("entry_bounds")
    flags = int.from_bytes(data[offset + fixed - 2:offset + fixed], "big")
    if flags & _STAGE_MASK:
        raise IndexFormatRefused("stage")
    if flags & _EXTENDED:
        raise IndexFormatRefused("extended_flag")
    length, start = flags & _NAME_MASK, offset + fixed
    if length == _NAME_MASK:                      # the field cannot count it: the NUL ends it
        stop = data.find(b"\0", start, end)
        if stop < 0:
            raise IndexFormatRefused("entry_bounds")
        length = stop - start
        if length < _NAME_MASK:
            raise IndexFormatRefused("name_length")
    if length == 0:
        raise IndexFormatRefused("name_length")
    following = offset + ((fixed + length + 8) & ~7)
    if following > end:
        raise IndexFormatRefused("entry_bounds")
    name = data[start:start + length]
    if b"\0" in name:
        raise IndexFormatRefused("name_nul")
    if any(data[start + length:following]):
        raise IndexFormatRefused("padding")
    if previous is not None and name <= previous:
        raise IndexFormatRefused("name_order")
    return following, name


def _tree_root(payload: bytes, size: int) -> str | None:
    """The root of the cache tree. Only the root record is read: the bytes are Git's own, the
    checksum covers them, and what the product decides on is the root alone."""
    head = _ROOT.match(payload)
    if head is None:
        raise IndexFormatRefused("tree_extension")
    if head[1] == b"-1":
        return None
    name = payload[head.end():head.end() + size]
    if len(name) != size:
        raise IndexFormatRefused("tree_extension")
    return name.hex()


def _marker(payload: bytes) -> tuple[str, str]:
    found = _MARKER.fullmatch(payload)
    if found is None:
        raise IndexFormatRefused("marker_payload")
    return found[1].decode("ascii"), found[2].decode("ascii")


def _extensions(data: bytes, offset: int, end: int,
                size: int) -> tuple[tuple[str, ...], str | None, tuple[str, str] | None]:
    """Walk the extensions up to the trailer: (their names in order, tree root, marker)."""
    seen: list[str] = []
    root = marker = None
    while offset < end:
        if end - offset < _EXTENSION.size:
            raise IndexFormatRefused("extension_header")
        signature, length = _EXTENSION.unpack_from(data, offset)
        body = offset + _EXTENSION.size
        if body + length > end:
            raise IndexFormatRefused("extension_bounds")
        payload = data[body:body + length]
        if signature == b"TREE":
            if marker is not None:
                raise IndexFormatRefused("marker_position")
            if "TREE" in seen:
                raise IndexFormatRefused("extension_duplicate")
            root = _tree_root(payload, size)
        elif signature == SIGNATURE:
            if marker is not None:
                raise IndexFormatRefused("extension_duplicate")
            marker = _marker(payload)
        else:
            raise IndexFormatRefused("extension_not_allowed")
        seen.append(signature.decode("ascii"))
        offset = body + length
    return tuple(seen), root, marker


def verify(data: bytes, object_format: str, *, entries: int | None = None) -> IndexShape:
    """Judge the bytes, bounded, and say what they hold.

    Args:
        data: The whole index file.
        object_format: `sha1` or `sha256`, the hash format of the repository.
        entries: The entry count the caller expects, when it knows one.

    Raises:
        IndexFormatRefused: Naming the first thing that is wrong, as one word of `REASONS`.
    """
    size = _hash_size(object_format)
    end = _end_of_body(data, object_format, size)
    count = _entry_count(data)
    if entries is not None and count != entries:
        raise IndexFormatRefused("entry_count")
    offset, previous = _HEADER.size, None
    for _ in range(count):
        offset, previous = _entry(data, offset, end, size, previous)
    names, root, marker = _extensions(data, offset, end, size)
    return IndexShape(count, names, root, marker)


def mark(data: bytes, object_format: str, *, nonce: str, terms: str) -> bytes:
    """Add the marker extension before the trailer and recompute the trailer.

    The bytes are verified before and the result after; bytes that already carry a marker are
    refused, so an index is never marked twice. Every other byte is kept as it was.

    Args:
        data: A plain index the product built, outside the marker.
        object_format: `sha1` or `sha256`.
        nonce: 16 lower-case hex digits, the operation's nonce.
        terms: 64 lower-case hex digits, `terms_hash` of the operation.

    Raises:
        IndexFormatRefused: The bytes are outside the format, already marked, or too large once
            marked, or the nonce or terms are not of the marker's form.
    """
    shape = verify(data, object_format)
    if shape.marker is not None:
        raise IndexFormatRefused("extension_duplicate")
    if (type(nonce) is not str or _NONCE.fullmatch(nonce) is None or type(terms) is not str
            or _TERMS.fullmatch(terms) is None):
        raise IndexFormatRefused("marker_payload")
    payload = f"v1;nonce={nonce};terms={terms}".encode("ascii")
    body = data[:-_HASH_SIZE[object_format]] + SIGNATURE + struct.pack(">I", len(payload)) + payload
    marked = body + hashlib.new(object_format, body).digest()
    verify(marked, object_format, entries=shape.entries)
    return marked


def verify_binding(data: bytes, binding: Binding) -> bool:
    """True only when EVERY part of the binding holds; never raises on foreign bytes.

    The digest of the whole file is the verified op's, the bytes pass the format check, the
    marker carries this operation's nonce and terms hash, the cache-tree root is the expected
    tree, and the entry count is the file count. A right marker on other bytes is foreign, right
    unmarked bytes are foreign, and the header alone never decides.
    """
    try:
        shape = verify(data, binding.object_format, entries=binding.file_count)
    except IndexFormatRefused:
        return False
    return (sha256(data) == binding.install_sha256
            and shape.marker == (binding.nonce, binding.terms)
            and shape.tree_root == binding.expected_tree)
