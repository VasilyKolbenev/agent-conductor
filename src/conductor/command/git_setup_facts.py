"""Pinned Git admission and structurally plain metadata routes for setup."""
from __future__ import annotations

import os
from pathlib import Path

from .accept_git import PreviewGit
from .containment import first_directory_violation
from .git_setup_records import SetupRefused
from .product_names import ExcludeWriteError, write_exclude_block
from .project_documents import read_head
from .project_git import GitReadFailed, repository_admission
from .project_git_state import _checked, _signing
from .template_store import _leaf_violation


def call(root, git, *args, **keywords):
    return _checked(git(["--no-optional-locks", "-C", str(root), *args], True, **keywords))


def admitted(root, git):
    result = repository_admission(root, git)
    if result.state != "repo":
        raise SetupRefused({"not_git": "not_a_git_repository", "not_repo_root": "project_not_repo_root",
                            "unsupported": "tracks_product_dir"}.get(result.state, result.state))


def object_format(root, git):
    raw = call(root, git, "rev-parse", "--show-object-format").strip()
    if raw not in (b"sha1", b"sha256"):
        raise GitReadFailed("git_failed")
    return raw.decode("ascii")


def git_dir(root, git, *, common=False):
    command = ("--path-format=absolute", "--git-common-dir") if common else ("--absolute-git-dir",)
    raw = call(root, git, "rev-parse", *command).decode("utf-8").rstrip("\r\n")
    path = Path(raw)
    if not path.is_absolute() or any(c in raw for c in "\r\n\0"):
        raise SetupRefused("unsafe_git_route")
    # A linked worktree legitimately keeps its common dir outside this root. The
    # pinned Git names it, but no symlink/junction along that route grants a write.
    if first_directory_violation((*reversed(path.parents), path)):
        raise SetupRefused("unsafe_git_route")
    return path


def exclude(root, git):
    common = git_dir(root, git, common=True)
    target = common / "info" / "exclude"
    if first_directory_violation((common, common / "info")) or _leaf_violation(target):
        raise SetupRefused("unsafe_git_route")
    try:
        result = write_exclude_block(common)
    except ExcludeWriteError:
        raise SetupRefused("git_exclude_failed") from None
    if result not in {"written", "present"}:
        raise SetupRefused("git_exclude_failed")
    return result


def first_facts(root, git):
    admitted(root, git)
    if read_head(root, git) is not None:
        raise SetupRefused("head_exists")
    folder = git_dir(root, git)
    if os.path.lexists(folder / "index"):
        raise SetupRefused("index_exists")
    if os.path.lexists(folder / "index.lock"):
        raise SetupRefused("index_locked")
    target = call(root, git, "symbolic-ref", "HEAD").decode("utf-8").strip()
    if not target.startswith("refs/heads/"):
        raise SetupRefused("head_exists")
    call(root, git, "check-ref-format", target)
    author = PreviewGit(root, git, None, "", "", "").author()
    return dict(head=None, target_ref=target, object_format=object_format(root, git),
                author=author, signing=_signing(root, git))
