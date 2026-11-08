"""Stage and inspect the offline Windows Kimi candidate. Never install, sign in or run a tool."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import sys
from zipfile import BadZipFile, ZipFile

from conductor.ownership_native import NativeHold

ZIP = (56242443, "80e4de3f2bd7c33ba10cfe3c2282492b0758fae9887537f4ff79ec2022957004")
FILES = {
    "kimi.exe": (150901248, "b7e658d06176284384d1e9eb627d11e5a26627b3964bf8787f197915d1484b1e"),
    "shell/sh.exe": (2465552, "e769a06bace817d96a4448f985ea2b48526c6cab042417229665f6b446e038dd"),
    "shell/msys-2.0.dll": (
        3388816, "a4f38fafec60affc988a0ccc9a51255b86469326ead9730ec7b1af87ce95579e"),
}


class KitRefused(ValueError):
    """The named kit cannot establish the reviewed layout and contents."""


def _plain(path, *, directory):
    found = path.lstat()
    admissible = stat.S_ISDIR(found.st_mode) if directory else (
        stat.S_ISREG(found.st_mode) and found.st_nlink == 1)
    if not admissible or getattr(found, "st_file_attributes", 0) & 0x400:
        raise KitRefused("expected an ordinary directory or singly named file")
    return found


def _directory(path):
    if not path.is_absolute() or ".." in path.parts:
        raise KitRefused("an absolute directory without parent components is required")
    for p in (*reversed(path.parents), path):
        _plain(p, directory=True)


@contextmanager
def _held(path, *, directory=False, inheriting=False):
    _plain(path, directory=directory)
    hold = NativeHold(path, directory=directory)
    try:
        hold.check()
        if inheriting and os.name == "nt":
            from conductor.command.adapters import _winlaunch
            if _winlaunch.acl_snapshot(hold)[1]:
                raise KitRefused("kit item blocks inheritance of the install-folder grant")
        yield
        hold.check()
    finally:
        hold.close()


def _check(stream, expected):
    size, digest = expected
    if os.fstat(stream.fileno()).st_size != size:
        raise KitRefused("unexpected file size")
    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
        raise KitRefused("file digest does not match the pin")
    stream.seek(0)


def _layout(root):
    if {p.name for p in root.iterdir()} != {"kimi.exe", "shell"}:
        raise KitRefused("unexpected top-level layout")
    if {p.name for p in (root / "shell").iterdir()} != {"sh.exe", "msys-2.0.dll"}:
        raise KitRefused("unexpected shell layout")


@contextmanager
def verified_bundle(root):
    """Hold all three checked files during use. Windows denies write/delete on these handles.

    A production launch must also protect the directory tree against other writers. This
    tool only verifies the offline candidate and never creates a production reference.
    """
    root = Path(root)
    _directory(root)
    with ExitStack() as held:
        held.enter_context(_held(root, directory=True, inheriting=True))
        held.enter_context(_held(root / "shell", directory=True, inheriting=True))
        _layout(root)
        for rel, pin in FILES.items():
            file = root / rel
            held.enter_context(_held(file, inheriting=True))
            with file.open("rb") as stream:
                _check(stream, pin)
        _layout(root)
        yield {"version": "0.38.0", "executable": str(root / "kimi.exe"),
               "shell": str(root / "shell" / "sh.exe"),
               "files": {rel: {"size": n, "sha256": sha} for rel, (n, sha) in FILES.items()}}
        _layout(root)


def inspect(root):
    with verified_bundle(root) as receipt:
        return receipt


def _scratch_destination(dest):
    protected = Path.home() / "DecemberCommand"
    if dest == protected or protected in dest.parents:
        raise KitRefused("staging in the protected product tree is forbidden")
    if os.name != "nt":
        raise KitRefused("staging requires Windows no-replace directory publication")
    if str(dest).startswith("\\\\") or any(":" in part for part in dest.parts[1:]):
        raise KitRefused("a normal local drive path is required")
    _directory(dest.parent)
    if protected.is_dir() and any(p.samefile(protected) for p in dest.parents):
        raise KitRefused("staging in the protected product tree is forbidden")
    if os.path.lexists(dest):
        raise KitRefused("destination already exists")


def stage(archive, git_bin, destination):
    archive, git_bin, dest = map(Path, (archive, git_bin, destination))
    _scratch_destination(dest)
    _directory(archive.parent)
    _directory(git_bin)
    with _held(dest.parent, directory=True):
        # mkdtemp applies a protected DACL on modern Windows Python, which would block the
        # install-folder RX loan from reaching the shell and DLL after directory publication.
        temporary = dest.parent / (".kimi-kit-" + secrets.token_hex(16))
        temporary.mkdir()  # exclusive and inherits the parent's ACL
        original = temporary.stat()
        try:
            with _held(archive), archive.open("rb") as source:
                _check(source, ZIP)
                with ZipFile(source) as package:
                    members = package.infolist()
                    if (len(members) != 1 or members[0].filename != "kimi.exe"
                            or members[0].file_size != FILES["kimi.exe"][0]):
                        raise KitRefused("unexpected Kimi archive layout")
                    target = temporary / "kimi.exe"
                    with package.open(members[0]) as exe, target.open("xb") as out:
                        shutil.copyfileobj(exe, out)
            (temporary / "shell").mkdir()
            for name in ("sh.exe", "msys-2.0.dll"):
                file = git_bin / name
                with _held(file), file.open("rb") as source:
                    _check(source, FILES["shell/" + name])
                    with (temporary / "shell" / name).open("xb") as out:
                        shutil.copyfileobj(source, out)
            inspect(temporary)
            # Windows rename refuses a destination that appeared after our first check.
            temporary.rename(dest)
        except BaseException:
            # Only our fresh directory, never an old destination or a substituted name.
            try:
                current = temporary.lstat()
            except FileNotFoundError:
                current = None
            if current is not None and os.path.samestat(original, current):
                shutil.rmtree(temporary)
            raise
    return inspect(dest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="operation", required=True)
    build = subs.add_parser("stage")
    build.add_argument("archive", type=Path)
    build.add_argument("git_bin", type=Path)
    build.add_argument("destination", type=Path)
    check = subs.add_parser("verify")
    check.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    try:
        result = (inspect(args.root) if args.operation == "verify"
                  else stage(args.archive, args.git_bin, args.destination))
    except (OSError, BadZipFile, KitRefused) as error:
        print(f"Kit refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
