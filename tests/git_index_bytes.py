"""Index files made by hand in the version 2 layout, so a test can judge exactly one fact.

`build` writes the header, the entries, the extensions and the checksum itself, and each part can
be broken on purpose: a count that lies, a flag that must not be set, padding that is not NUL, a
checksum that is wrong or zero. The layout is the published index format (the fixed stat words,
the object name, two flag bytes, the path, then NUL padding up to a multiple of eight bytes).
"""
from __future__ import annotations

import hashlib
import struct

SIZE = {"sha1": 20, "sha256": 32}
#: A tree id of the right length for each object format; nothing here reads a repository.
DEFAULT_TREE = {"sha1": "a" * 40, "sha256": "a" * 64}
_STAT_WORDS = struct.pack(">10I", 1, 2, 3, 4, 5, 6, 0o100644, 7, 8, 9)


def digest(fmt: str, data: bytes) -> bytes:
    """The checksum of `data` in the repository's hash format."""
    return hashlib.new(fmt, data).digest()


def entry(name, fmt: str = "sha1", *, flags: int | None = None, dirty_pad: bool = False) -> bytes:
    """One version 2 entry. `flags` replaces the flag word (name length, stage, extended bit);
    `dirty_pad` puts a non-NUL byte first in the padding."""
    raw = name.encode() if isinstance(name, str) else name
    word = min(len(raw), 0xFFF) if flags is None else flags
    body = _STAT_WORDS + digest(fmt, raw) + struct.pack(">H", word) + raw
    pad = bytearray(8 - len(body) % 8)
    if dirty_pad:
        pad[0] = 1
    return body + bytes(pad)


def extension(signature: bytes, payload: bytes, size: int | None = None) -> bytes:
    """One extension; `size` overrides the length the header declares."""
    declared = len(payload) if size is None else size
    return signature + struct.pack(">I", declared) + payload


def tree_extension(root: str | None, count: int, fmt: str = "sha1") -> bytes:
    """A `TREE` extension holding only the root record; `count` of -1 is an invalidated root."""
    record = b"\0" + f"{count} 0\n".encode()
    if count >= 0:
        record += bytes.fromhex(root or DEFAULT_TREE[fmt])
    return extension(b"TREE", record)


def marker(nonce: str, terms: str) -> bytes:
    """The operation marker as it must stand on disk (the wire form the product writes)."""
    return extension(b"CNDT", f"v1;nonce={nonce};terms={terms}".encode("ascii"))


def build(entries=(), extensions=(), fmt: str = "sha1", *, version: int = 2,
          count: int | None = None, signature: bytes = b"DIRC",
          trailer: bytes | None = None) -> bytes:
    """A whole index; every argument after `fmt` exists to break one part of it on purpose."""
    declared = len(entries) if count is None else count
    body = struct.pack(">4sII", signature, version, declared)
    body += b"".join(entries) + b"".join(extensions)
    return body + (digest(fmt, body) if trailer is None else trailer)


def plain(names, fmt: str = "sha1", *, tree: str | None = None, extensions=None) -> bytes:
    """What the product builds: sorted entries and a `TREE` extension (or the given ones)."""
    ordered = sorted(name.encode() if isinstance(name, str) else name for name in names)
    wanted = [tree_extension(tree, len(ordered), fmt)] if extensions is None else extensions
    return build([entry(name, fmt) for name in ordered], wanted, fmt)


def rechecksum(data: bytes, fmt: str) -> bytes:
    """`data` with its trailer recomputed over everything before it."""
    body = data[:-SIZE[fmt]]
    return body + digest(fmt, body)
