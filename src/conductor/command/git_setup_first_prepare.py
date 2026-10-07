"""Phase A of the first commit: what the owner cannot see, made without a lock (plan Task 6).

`prepare` turns the rows of a shown preview into objects in the repository and into the marked
bytes of the index to install. It writes objects and nothing else that belongs to the repository:
no ref, no index, no lock, no file of the product's records. The only other files it makes are
two private indexes of its own, removed again whatever happens.

Everything that decides what is committed comes from the preview and from nothing the files say
now. The tree is built from the object id and the Git mode each row was SHOWN with (review ruling
OD-7): this module makes no decision about a file's mode and looks at no file. The objects are
written once and their ids must equal the shown ids, else the folder is not what the person
confirmed (`paths_changed`). The refresh that fills in the stat data of the index looks at every
file a second time, which catches a file that changed between the object write and the refresh.

The bytes to install are built from the TREE, not from a commit, so the signing road, which has no
commit yet, builds them the same way. They are verified, marked with this operation's nonce and
terms (`git_setup_first_index`), and then read back by the product's own Git: `diff-index` must
exit 0 over them, and the file must be untouched afterwards. Every index command carries
`INDEX_PIN`, so a setting of the owner's repository cannot put an extension, a version or a split
index into bytes the format check would take for the product's own. The commit is made last, and
not at all when signing is required.
"""
from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .accept_plumbing import call, oid
from .accept_snapshot import _read
from .git_index import OwnedIndex, temporary_index
from .git_setup_first_index import INDEX_PIN, IndexFormatRefused, mark, terms_hash, verify
from .git_setup_first_records import INDEX_LIMIT
from .git_setup_records import SetupRefused
from .git_setup_snapshot import hash_rows
from .project_git import GitRead, GitReadFailed
from .project_git_state import _checked

_STDIN_LIMIT = 128 * 1024


@dataclass(frozen=True)
class Prepared:
    """What phase A made: the objects that exist and the bytes that will be installed."""

    nonce: str
    tree: str
    commit: str | None            # None exactly when signing is required (the signed road)
    install: bytes                # the MARKED bytes, ready to publish
    count: int


def prepare(root: Path, git: GitRead, shown: dict, message: bytes, mode: str,
            digest: str | None) -> Prepared:
    """Write the objects of a shown preview and build the marked index bytes for them.

    Args:
        root: The project folder.
        git: The product's Git reader, able to run commands over an owned index.
        shown: The preview, as shown: its rows carry `git_oid` and `git_mode`.
        message: The exact bytes of the commit message.
        mode: `snapshot` or `empty`.
        digest: The sealed `paths_digest` of the confirmation, None in mode `empty`.

    Returns:
        The nonce of this operation, the tree, the commit (None when signing is required), the
        marked install bytes and the number of files.

    Raises:
        SetupRefused: `paths_changed`, a file is not the one that was shown.
        GitReadFailed: Git failed, timed out, or the built bytes are outside the verified format.
    """
    nonce, fmt, rows = secrets.token_hex(8), shown["object_format"], shown["files"]
    tree = _tree(root, git, rows, fmt, nonce)
    terms = terms_hash(nonce=nonce, mode=mode, digest_version=shown["digest_version"],
                       paths_digest=digest, target_ref=shown["target_ref"], object_format=fmt,
                       expected_tree=tree, file_count=len(rows))
    install = _install_bytes(root, git, rows, tree, fmt, nonce, terms)
    commit = None if shown["signing"] else oid(call(
        root, git, "commit-tree", "--no-gpg-sign", tree, "-F", "-", stdin=message))
    return Prepared(nonce, tree, commit, install, len(rows))


def git_refresh(root: Path, git: GitRead, index: OwnedIndex) -> None:
    """Fill in the stat data of every entry of an owned index and look at each file once more.

    It runs without `-q`: with it a changed file would end in exit 0 and be missed. Exit 1 means a
    file no longer holds the bytes of its entry, which is `paths_changed`.
    """
    answer = git(["-C", str(root), f"--work-tree={root}", *INDEX_PIN, "update-index", "--refresh"],
                 True, index_file=index)
    if answer.exit_code == 1:
        raise SetupRefused("paths_changed")
    _checked(answer)


def _tree(root: Path, git: GitRead, rows: list[dict], fmt: str, nonce: str) -> str:
    """A2: write the objects, then build the tree from the SHOWN modes in a private index."""
    if hash_rows(root, git, rows, fmt, write=True) != [row["git_oid"] for row in rows]:
        raise SetupRefused("paths_changed")
    with temporary_index(root, f"first-{nonce}-a", fmt) as built:
        _enter(root, git, rows, built)
        return oid(call(root, git, *INDEX_PIN, "write-tree", index_file=built))


def _enter(root: Path, git: GitRead, rows: list[dict], built: OwnedIndex) -> None:
    """Put every row into the private index with the object and the mode it was shown with."""
    pending, size = [], 0
    for row in rows:
        line = f"{row['git_mode']} {row['git_oid']}\t{row['path']}\n".encode("utf-8")
        if pending and size + len(line) > _STDIN_LIMIT:
            _index_info(root, git, pending, built)
            pending, size = [], 0
        pending.append(line)
        size += len(line)
    if pending:
        _index_info(root, git, pending, built)


def _index_info(root: Path, git: GitRead, lines: list[bytes], built: OwnedIndex) -> None:
    call(root, git, *INDEX_PIN, "update-index", "--index-info", stdin=b"".join(lines),
         index_file=built)


@contextmanager
def _format_refusals() -> Iterator[None]:
    """Bytes outside the verified format are a failure of Git's, in the product's one word."""
    try:
        yield
    except IndexFormatRefused:
        raise GitReadFailed("git_failed") from None


def _install_bytes(root: Path, git: GitRead, rows: list[dict], tree: str, fmt: str,
                   nonce: str, terms: str) -> bytes:
    """A3 to A5: the base bytes by `read-tree` and a refresh, the marker, then the pinned read."""
    with temporary_index(root, f"first-{nonce}-b", fmt) as second:
        call(root, git, *INDEX_PIN, "read-tree", tree, index_file=second)
        if rows:
            git_refresh(root, git, second)
        with _format_refusals():
            base = _read(second.root, second.path, INDEX_LIMIT)
            verify(base, fmt, entries=len(rows))
            install = mark(base, fmt, nonce=nonce, terms=terms)
        _read_by_the_pinned_git(root, git, second, install, tree)
    return install


def _read_by_the_pinned_git(root: Path, git: GitRead, index: OwnedIndex, install: bytes,
                            tree: str) -> None:
    """A5: the marked bytes, in a private index, must hold the tree for the product's own Git.

    Only exit 0 passes; any other exit, a timeout, or a file that is not the installed bytes
    afterwards refuses. What Git prints about the marker is read by nobody.
    """
    _overwrite(index, install)
    call(root, git, "--no-optional-locks", *INDEX_PIN, "diff-index", "--cached", "--quiet", tree,
         index_file=index)
    if _read(index.root, index.path, INDEX_LIMIT) != install:
        raise GitReadFailed("git_failed")


def _overwrite(index: OwnedIndex, data: bytes) -> None:
    """Put `data` into the owned file itself, so that its identity stays the one that is held."""
    index.environment(index.root)            # the checks every command of an owned index makes
    with index.path.open("r+b") as stream:
        stream.write(data)
        stream.truncate()
