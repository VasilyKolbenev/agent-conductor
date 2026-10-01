"""Pinned, read-only Git facts for an acceptance preview; no process door of its own."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .accept_manifest import SnapshotRefused, blob_oid
from .project_documents import read_head
from .project_git import GitReadFailed, repository_admission
from .project_git_state import _checked, _names
from .seed_stage import _listing

_IDENT = re.compile(r"([^\r\n<>]+) <([^\r\n<>]+)> -?\d+ [+-]\d{4}\Z")


@dataclass(frozen=True)
class PreviewGit:
    root: object
    git: object
    head: object
    object_format: str
    commit: str
    source: str

    def call(self, *args, absent=False, **kwargs):
        return _checked(self.git(["--no-optional-locks", "-C", str(self.root), *args], True, **kwargs),
                        absent=absent)

    def listing(self):
        return {row.path: row for row in _listing(self.root, self.git, self.commit)}

    def blob(self, row):
        # Each blob is independently bounded; callers only ask for selected transfer paths.
        if row.kind != "blob" or row.mode not in {"100644", "100755"}:
            raise SnapshotRefused("reserved_path")
        if row.size > 64 * 1024 * 1024:
            raise SnapshotRefused("result_too_large")
        data = self.call("cat-file", "blob", row.oid, output_limit=row.size + 1)
        if len(data) != row.size or blob_oid(data, self.object_format) != row.oid:
            raise SnapshotRefused("snapshot_damaged")
        return data

    def author(self):
        authors = []
        for variable in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
            answer = self.git(["--no-optional-locks", "-C", str(self.root), "var", variable], True)
            if answer.timed_out or answer.exit_code is None:
                raise GitReadFailed("git_timed_out")
            if answer.exit_code != 0:
                raise SnapshotRefused("git_identity_missing")
            text = _checked(answer).decode("utf-8", errors="strict").strip()
            match = _IDENT.fullmatch(text)
            if match is None:
                raise SnapshotRefused("git_identity_missing")
            authors.append({"name": match[1], "email": match[2]})
        return authors[0]

    def branch(self, name):
        if not name.startswith("conduct/") or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise SnapshotRefused("branch_name_invalid")
        answer = self.git(["-C", str(self.root), "check-ref-format", "--branch", name], True)
        if answer.timed_out or answer.exit_code is None:
            raise GitReadFailed("git_timed_out")
        if answer.exit_code != 0 or answer.truncated:
            raise SnapshotRefused("branch_name_invalid")
        refs = self.call("for-each-ref", "--format=%(refname)", "refs/heads/conduct").decode("utf-8").splitlines()
        asked = "refs/heads/" + name
        if asked in refs:
            raise SnapshotRefused("branch_exists")
        if any(asked.startswith(ref + "/") or ref.startswith(asked + "/") for ref in refs):
            raise SnapshotRefused("branch_namespace_blocked")
        return name

    def head_facts(self, paths, seed):
        overlap, ahead = [], 0
        if self.head.commit != self.commit:
            ahead_raw = self.call("rev-list", "--count", f"{self.commit}..{self.head.commit}").strip()
            if not ahead_raw.isdigit():
                raise GitReadFailed("git_failed")
            ahead = int(ahead_raw)
            moved = _names(self.call("diff", "--name-only", "-z", self.commit, self.head.commit, "--"))
            overlap = sorted(set(moved) & set(paths))
        return {"commit": self.commit, "source": self.source,
                "seeded_at": None if seed is None else seed.staged_at,
                "head_now": self.head.commit, "head_ref": self.head.ref,
                "head_ahead": ahead, "overlap": overlap}

    def ignored(self, paths, work):
        if sum(len(path.encode("utf-8")) + 1 for path in paths) > 128 * 1024:
            middle = len(paths) // 2
            if not middle:
                raise SnapshotRefused("unportable_name")
            return self.ignored(paths[:middle], work) | self.ignored(paths[middle:], work)
        if not paths:
            return set()
        # NUL-free, admitted paths, so one LF-delimited path per stdin line is unambiguous.
        raw = self.git(["--no-optional-locks", "-c", "core.quotepath=false", "-C", str(self.root), f"--work-tree={work}",
                        "check-ignore", "--no-index", "--stdin"], True,
                       stdin=("\n".join(paths) + "\n").encode("utf-8"))
        if raw.exit_code == 1 and not raw.output and not raw.timed_out and not raw.truncated:
            return set()
        names = _checked(raw).decode("utf-8").splitlines()
        if not set(names) <= set(paths):
            raise GitReadFailed("git_failed")
        return set(names)


def read_git(root, git, seed):
    admission = repository_admission(root, git)
    if admission.state != "repo":
        reason = {"not_git": "not_a_git_repository", "not_repo_root": "project_not_repo_root",
                  "unsupported": "tracks_product_dir", "unsafe_directory": "unsafe_directory"}[admission.state]
        raise SnapshotRefused(reason)
    head = read_head(root, git)
    if head is None:
        raise SnapshotRefused("unborn_head")
    fmt = _checked(git(["-C", str(root), "rev-parse", "--show-object-format"], True)).decode("ascii").strip()
    if fmt not in {"sha1", "sha256"} or seed is not None and seed.source == "git" and fmt != seed.object_format:
        raise SnapshotRefused("object_format_changed")
    commit = seed.base_commit if seed is not None and seed.source == "git" else head.commit
    answer = git(["-C", str(root), "cat-file", "-e", commit + "^{commit}"], True)
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if answer.exit_code != 0:
        raise SnapshotRefused("base_missing")
    _checked(answer)
    return PreviewGit(root, git, head, fmt, commit, "seed" if commit != head.commit or
                      seed is not None and seed.source == "git" else "head")
