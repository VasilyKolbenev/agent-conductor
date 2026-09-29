"""Throwaway layout, tree snapshot and write-operation table for the OS-boundary checks.

Shared by the Windows AppContainer probe and the macOS Seatbelt probe. Nothing here
touches an OS mechanism: it builds directories, reads them back, and names the
operations a confined child is asked to attempt. The PARENT judges by the snapshot,
never by what the child says about itself.

An operation is a sequence of steps, each run by a small tool: ``ps`` (Windows
PowerShell, .NET calls), ``cmd`` (only for ``mklink``), ``icacls``, or ``sh``. Bodies
carry ``@TOKEN@`` markers that ``render`` replaces with real paths, so no script has
to expand an environment variable inside the confined process.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

SOURCE_FILE = "original source\n"
_GIT_FILES = {
    "HEAD": "ref: refs/heads/main\n",
    "config": "[core]\n\tbare = false\n",
    "index": "INDEX-BYTES",
    "refs/heads/main": "0123456789abcdef0123456789abcdef01234567\n",
    "objects/ab/cdef0123": "loose-object-bytes",
}


@dataclass(frozen=True)
class Layout:
    """Six sibling directories under one base: nothing granted to anyone yet."""

    base: Path
    source: Path
    work: Path
    tmp: Path
    home: Path
    vendor_home: Path

    def root(self, name: str) -> Path:
        """The root an operation targets: ``source``, ``work`` or ``vendor``."""
        return {"source": self.source, "work": self.work, "vendor": self.vendor_home}[name]

    def tokens(self, root_name: str = "source") -> dict[str, str]:
        """The values ``render`` substitutes, with ROOT pointing at the chosen root."""
        return {
            "ROOT": str(self.root(root_name)), "SRC": str(self.source),
            "WORK": str(self.work), "TMPD": str(self.tmp), "HOMED": str(self.home),
            "VENDOR": str(self.vendor_home),
        }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _tree(root: Path, *, with_git: bool) -> None:
    _write(root / "file.txt", SOURCE_FILE)
    _write(root / "sub" / "inner.txt", "inner\n")
    if with_git:
        for name, text in _GIT_FILES.items():
            _write(root / ".git" / name, text)


def make_layout(base: Path) -> Layout:
    """Create the throwaway directories: a source tree with a fake Git store, a work copy."""
    layout = Layout(base, base / "source", base / "work", base / "tmp", base / "home",
                    base / "vendor_home")
    _tree(layout.source, with_git=True)
    _tree(layout.work, with_git=False)
    for directory in (layout.tmp, layout.home, layout.vendor_home):
        directory.mkdir(parents=True, exist_ok=True)
    _write(layout.vendor_home / "auth.json", '{"token": "old"}')
    return layout


@dataclass(frozen=True)
class Entry:
    """What one entry of a tree is, without its timestamps."""

    kind: str
    digest: str
    links: int
    mode: int | None
    acl: str | None


def _digest(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()[:16]
    except OSError:
        return "<unreadable>"


def _entry(path: str, acl) -> Entry:
    facts = os.lstat(path)
    listed = acl(path) if acl is not None else None
    mode = None if os.name == "nt" else stat.S_IMODE(facts.st_mode)
    if stat.S_ISLNK(facts.st_mode) or getattr(facts, "st_reparse_tag", 0):
        target = os.readlink(path) if stat.S_ISLNK(facts.st_mode) else "<reparse>"
        return Entry("link", target, 0, mode, listed)
    if stat.S_ISDIR(facts.st_mode):
        return Entry("dir", "", 0, mode, listed)
    return Entry("file", _digest(path), facts.st_nlink, mode, listed)


def _walk(top: str, path: str, found: dict[str, Entry], acl) -> None:
    entry = _entry(path, acl)
    found[os.path.relpath(path, top).replace(os.sep, "/")] = entry
    if entry.kind == "dir":
        for name in sorted(os.listdir(path)):
            _walk(top, os.path.join(path, name), found, acl)


def snapshot(root: Path, *, acl=None) -> dict[str, Entry]:
    """The tree under ``root`` by name, kind, content digest, link count and mode.

    A hard link made to a file changes that file's link count, so the second name is
    noticed even before anything is written through it. A link (symbolic or reparse
    point) is recorded and never followed. ``acl`` is an optional callable that returns
    the access-control text of a path; it is folded into every entry.
    """
    top = str(root)
    if not os.path.lexists(top):
        return {".": Entry("absent", "", 0, None, None)}
    found: dict[str, Entry] = {}
    _walk(top, top, found, acl)
    return found


@dataclass(frozen=True)
class Step:
    """One tool invocation: ``tool`` is ps, cmd, icacls or sh; ``body`` its script or args."""

    tool: str
    body: str


@dataclass(frozen=True)
class Operation:
    """A write the confined child attempts, for both OS families, on named roots."""

    name: str
    roots: tuple[str, ...]
    windows: tuple[Step, ...]
    posix: tuple[Step, ...]


def render(body: str, tokens: dict[str, str]) -> str:
    """Replace every ``@KEY@`` marker the tokens name; the caller checks none is left."""
    for key, value in tokens.items():
        body = body.replace(f"@{key}@", value)
    return body


def _op(name, roots, windows, posix) -> Operation:
    return Operation(name, tuple(roots), tuple(windows), tuple(posix))


def _ps(body: str) -> Step:
    return Step("ps", body)


def _sh(body: str) -> Step:
    return Step("sh", body)


_BOTH = ("source", "work")
_SOURCE = ("source",)

OPERATIONS: tuple[Operation, ...] = (
    _op("create_file", _BOTH,
        [_ps("[IO.File]::WriteAllText('@ROOT@\\new.txt','x')")],
        [_sh('printf x > "@ROOT@/new.txt"')]),
    _op("overwrite_file", _BOTH,
        [_ps("[IO.File]::WriteAllText('@ROOT@\\file.txt','x')")],
        [_sh('printf x > "@ROOT@/file.txt"')]),
    _op("append_file", _BOTH,
        [_ps("[IO.File]::AppendAllText('@ROOT@\\file.txt','x')")],
        [_sh('printf x >> "@ROOT@/file.txt"')]),
    _op("delete_file", _BOTH,
        [_ps("[IO.File]::Delete('@ROOT@\\file.txt')")],
        [_sh('rm -f "@ROOT@/file.txt"')]),
    _op("rename_file", _BOTH,
        [_ps("[IO.File]::Move('@ROOT@\\file.txt','@ROOT@\\moved.txt')")],
        [_sh('mv "@ROOT@/file.txt" "@ROOT@/moved.txt"')]),
    _op("create_directory", _BOTH,
        [_ps("[void][IO.Directory]::CreateDirectory('@ROOT@\\newdir')")],
        [_sh('mkdir "@ROOT@/newdir"')]),
    _op("delete_nested_file", _BOTH,
        [_ps("[IO.File]::Delete('@ROOT@\\sub\\inner.txt')")],
        [_sh('rm -f "@ROOT@/sub/inner.txt"')]),
    _op("delete_directory", _BOTH,
        [_ps("[IO.Directory]::Delete('@ROOT@\\sub',$true)")],
        [_sh('rm -rf "@ROOT@/sub"')]),
    _op("rename_directory", _BOTH,
        [_ps("[IO.Directory]::Move('@ROOT@\\sub','@ROOT@\\sub2')")],
        [_sh('mv "@ROOT@/sub" "@ROOT@/sub2"')]),
    _op("rename_root", _BOTH,
        [_ps("[IO.Directory]::Move('@ROOT@','@ROOT@-moved')")],
        [_sh('mv "@ROOT@" "@ROOT@-moved"')]),
    _op("git_overwrite_head", _SOURCE,
        [_ps("[IO.File]::WriteAllText('@ROOT@\\.git\\HEAD','x')")],
        [_sh('printf x > "@ROOT@/.git/HEAD"')]),
    _op("git_delete_head", _SOURCE,
        [_ps("[IO.File]::Delete('@ROOT@\\.git\\HEAD')")],
        [_sh('rm -f "@ROOT@/.git/HEAD"')]),
    _op("git_rename_head", _SOURCE,
        [_ps("[IO.File]::Move('@ROOT@\\.git\\HEAD','@ROOT@\\.git\\HEAD2')")],
        [_sh('mv "@ROOT@/.git/HEAD" "@ROOT@/.git/HEAD2"')]),
    _op("git_delete_object", _SOURCE,
        [_ps("[IO.File]::Delete('@ROOT@\\.git\\objects\\ab\\cdef0123')")],
        [_sh('rm -f "@ROOT@/.git/objects/ab/cdef0123"')]),
    _op("git_delete_store", _SOURCE,
        [_ps("[IO.Directory]::Delete('@ROOT@\\.git',$true)")],
        [_sh('rm -rf "@ROOT@/.git"')]),
    _op("git_rename_store", _SOURCE,
        [_ps("[IO.Directory]::Move('@ROOT@\\.git','@ROOT@\\.git2')")],
        [_sh('mv "@ROOT@/.git" "@ROOT@/.git2"')]),
    _op("hard_link_then_write_through", _BOTH,
        [Step("cmd", 'mklink /H "@TMPD@\\hl.txt" "@ROOT@\\file.txt"'),
         _ps("[IO.File]::AppendAllText('@TMPD@\\hl.txt','pwn')")],
        [_sh('ln "@ROOT@/file.txt" "@TMPD@/hl.txt"'), _sh('printf pwn >> "@TMPD@/hl.txt"')]),
    _op("link_to_the_root_then_write_through", _BOTH,
        [Step("cmd", 'mklink /J "@TMPD@\\jn" "@ROOT@"'),
         _ps("[IO.File]::WriteAllText('@TMPD@\\jn\\new.txt','pwn')")],
        [_sh('ln -s "@ROOT@" "@TMPD@/jn"'), _sh('printf pwn > "@TMPD@/jn/new.txt"')]),
    _op("copy_over_from_tmp", _BOTH,
        [_ps("[IO.File]::WriteAllText('@TMPD@\\c.txt','c'); "
             "[IO.File]::Copy('@TMPD@\\c.txt','@ROOT@\\file.txt',$true)")],
        [_sh('printf c > "@TMPD@/c.txt" && cp "@TMPD@/c.txt" "@ROOT@/file.txt"')]),
    _op("change_permissions", _BOTH,
        [Step("icacls", '"@ROOT@" /grant *S-1-1-0:(OI)(CI)F')],
        [_sh('chmod -R a+w "@ROOT@"')]),
)


def operations_for(root_name: str) -> tuple[Operation, ...]:
    """The operations that apply to one protected root."""
    return tuple(op for op in OPERATIONS if root_name in op.roots)
