"""The tracked text documents of a project's HEAD, and of a seed's base tree (spec 6.2.2, 9.5).

The owner picks project documents for the materials of a task, so the server lists them and reads
one: the tracked files of HEAD with a text extension, at most 49 152 bytes (what one document of a
run can hold), at most 500 of them, less the product's own folders. Each is named by an id the
server derives from its path (`d-` and 32 hex of the SHA-256 of the path), so the desk never sends
a path back and the server finds the path itself.

Git is never run here: the reader of `project_git` is handed in, and every call it makes is a
read of an object (`rev-parse`, `symbolic-ref`, `ls-tree`, `cat-file`). What a listing may name
is only an object id: a tree is asked for by the id git itself gave, never by a string the
caller sent, so no argument can be an option. The bytes of a document are the blob's own, with no
filter, no line-ending change and no BOM removed; a blob that is not UTF-8 text is refused, and so
is one with a NUL.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from . import product_names, project_git
from .artifacts import ARTIFACT_CONTENT_LIMIT
from .project_git import GitAnswer, GitRead, GitReadFailed

DOCUMENT_EXTENSIONS = (".md", ".markdown", ".txt", ".rst", ".adoc", ".mmd")
#: What one document of a run can hold, so the most a copy could put into one.
DOCUMENT_BYTES = ARTIFACT_CONTENT_LIMIT
DOCUMENT_ENTRIES = 500
REFUSAL_REASONS = ("doc_unknown", "document_not_text")

_REGULAR_MODES = frozenset({"100644", "100755"})
_OID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_ROW = re.compile(r"(\d{6}) (\w+) ([0-9a-f]{40}(?:[0-9a-f]{24})?) +(\d+|-)\t(.+)", re.DOTALL)


class DocumentRefused(Exception):
    """The one document asked for cannot be given; `reason` is one of `REFUSAL_REASONS`."""

    def __init__(self, reason: str) -> None:
        if reason not in REFUSAL_REASONS:
            raise ValueError(f"{reason!r} is not a reason a document is refused for")
        super().__init__(reason)
        self.reason = reason


class Head(NamedTuple):
    """The commit HEAD names and the ref it stands on (`HEAD` itself when detached)."""

    commit: str
    ref: str


class TreeFile(NamedTuple):
    """One row of a recursive tree listing."""

    mode: str
    kind: str
    git_oid: str
    length: int | None
    path: str


class Document(NamedTuple):
    """One document a project offers."""

    doc_id: str
    path: str
    length: int
    git_oid: str

    def as_dict(self) -> dict[str, object]:
        return {"doc_id": self.doc_id, "path": self.path, "length": self.length,
                "git_oid": self.git_oid}


@dataclass(frozen=True)
class Listing:
    """The answer of `GET /command/project/documents`."""

    base: Head | None
    documents: tuple[Document, ...]
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        base = None if self.base is None else {"commit": self.base.commit, "ref": self.base.ref}
        return {"base": base, "documents": [row.as_dict() for row in self.documents],
                "truncated": self.truncated}


#: A project with nothing to list: no git, no commit, or a folder that may not be a project.
EMPTY = Listing(None, (), False)


def doc_id_of(path: str) -> str:
    """The id of the document at `path`: `d-` and the first 32 hex of the SHA-256 of the path."""
    return "d-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]


def list_documents(root: str | Path, git: GitRead) -> Listing:
    """The documents of the project at `root`, read from HEAD.

    Args:
        root: The project folder, absolute.
        git: The reader of `project_git`.

    Returns:
        The listing; `EMPTY` for a folder with no git, an admission that is not `repo`
        (a subfolder of another repository, a repository that tracks the product's folders, a
        folder git will not trust) and a repository with no commit. `truncated` is true when more
        than 500 documents stand, or when git cut its own listing short.

    Raises:
        ValueError: `root` is not absolute.
        GitReadFailed: git failed or ran out of time.
    """
    folder = Path(root)
    if project_git.repository_admission(folder, git).state != "repo":
        return EMPTY
    head = read_head(folder, git)
    if head is None:
        return EMPTY
    files, cut = list_tree(folder, git, head.commit)
    found = sorted((_document(file) for file in files if _is_document(file)),
                   key=lambda document: document.path)
    return Listing(head, tuple(found[:DOCUMENT_ENTRIES]), cut or len(found) > DOCUMENT_ENTRIES)


def read_document(root: str | Path, git: GitRead, doc_id: str) -> dict[str, object]:
    """One document of HEAD: `{doc_id, path, git_oid, content}`.

    Raises:
        DocumentRefused: `doc_unknown` when HEAD lists no such id; `document_not_text` when the
            blob is not UTF-8 text or holds a NUL.
        GitReadFailed: git failed or ran out of time.
    """
    found = next((row for row in list_documents(root, git).documents if row.doc_id == doc_id),
                 None)
    if found is None:
        raise DocumentRefused("doc_unknown")
    answer = git(["-C", str(root), "cat-file", "blob", found.git_oid], separate_stderr=True)
    _ran(answer)
    try:
        content = answer.output.decode("utf-8")
    except UnicodeDecodeError:
        raise DocumentRefused("document_not_text") from None
    if answer.truncated or "\x00" in content or len(answer.output) > DOCUMENT_BYTES:
        raise DocumentRefused("document_not_text")
    return {"doc_id": found.doc_id, "path": found.path, "git_oid": found.git_oid,
            "content": content}


def base_documents(root: str | Path, git: GitRead, tree: str) -> dict[str, Document]:
    """Every document of one tree, by id: what a seed's base tree holds.

    A tree cut short by git is a failed read and never a shorter tree, because the caller judges
    absence from this (a link to a document the base does not hold).

    Raises:
        ValueError: `tree` is not an object id.
        GitReadFailed: git failed, ran out of time, or cut the listing short.
    """
    files, cut = list_tree(Path(root), git, tree)
    if cut:
        raise GitReadFailed("git_failed")
    return {doc_id_of(file.path): _document(file) for file in files if _is_document(file)}


def read_head(root: Path, git: GitRead) -> Head | None:
    """The commit HEAD names and its ref, or None for a repository with no commit yet."""
    verify = git(["-C", str(root), "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
                 separate_stderr=True)
    _ran(verify, (0, 1))
    if verify.exit_code == 1:
        return None
    commit = verify.output.decode("ascii", errors="replace").strip()
    if _OID.fullmatch(commit) is None:
        raise GitReadFailed("git_failed", verify.exit_code)
    named = git(["-C", str(root), "symbolic-ref", "--quiet", "HEAD"], separate_stderr=True)
    _ran(named, (0, 1))
    ref = named.output.decode("utf-8", errors="replace").strip() if named.exit_code == 0 else ""
    return Head(commit, ref or "HEAD")


def list_tree(root: Path, git: GitRead, tree_ish: str) -> tuple[list[TreeFile], bool]:
    """Every file of a tree, recursively, and whether git cut its own answer short.

    Args:
        tree_ish: An object id (a commit or a tree) and nothing else.

    Raises:
        ValueError: `tree_ish` is not an object id.
        GitReadFailed: git failed, ran out of time, or printed a row this parser does not know.
    """
    if _OID.fullmatch(tree_ish) is None:
        raise ValueError("a tree is named by its object id")
    answer = git(["-C", str(root), "ls-tree", "-r", "-l", "-z", "--full-tree", tree_ish],
                 separate_stderr=True)
    _ran(answer)
    output = answer.output[:answer.output.rfind(b"\0") + 1] if answer.truncated else answer.output
    return _parse_tree(output), answer.truncated


def _parse_tree(output: bytes) -> list[TreeFile]:
    files = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue  # a path that is not text names no document
        found = _ROW.fullmatch(text)
        if found is None:
            raise GitReadFailed("git_failed")
        mode, kind, oid, size, path = found.groups()
        files.append(TreeFile(mode, kind, oid, None if size == "-" else int(size), path))
    return files


def _is_document(file: TreeFile) -> bool:
    return (file.mode in _REGULAR_MODES and file.kind == "blob" and file.length is not None
            and file.length <= DOCUMENT_BYTES
            and file.path.lower().endswith(DOCUMENT_EXTENSIONS)
            and not set(file.path) & {"\x00", "\n", "\r"}
            and not product_names.is_product_path(file.path))


def _document(file: TreeFile) -> Document:
    assert file.length is not None
    return Document(doc_id_of(file.path), file.path, file.length, file.git_oid)


def _ran(answer: GitAnswer, ok: tuple[int, ...] = (0,)) -> None:
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if answer.exit_code not in ok:
        raise GitReadFailed("git_failed", answer.exit_code)
