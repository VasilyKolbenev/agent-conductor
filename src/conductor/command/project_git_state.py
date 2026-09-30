"""Read the Git facts shown by the task wizard, without changing the repository."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from .api_contracts import ApiRefusal
from .product_names import BLOCK_BEGIN, BLOCK_END, EXCLUDE_LINES, is_product_path
from .project_documents import read_head
from .project_git import GitReadFailed, has_git_entry, repository_admission
from .seed_plan import _is_instruction
from .seed_record import read_seed

_VERSION = re.compile(r"git version ([0-9]+\.[0-9]+\.[0-9]+(?:[.a-zA-Z0-9-]*))")
_REMOTE = re.compile(r"remote\.([A-Za-z0-9._-]{1,128})\.url\Z")
_GITHUB = re.compile(r"/?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?\Z")
_LIMIT = 4 * 1024 * 1024


def read_git(api):
    """GET /command/project/git; view-mode facts require no child process."""
    root = api._store.project_root
    include = _last_choice(api, root)
    if api._identity.mode == "view":
        state = "not_active" if os.path.lexists(root / ".git") else "not_git"
        return 200, {"git": _empty(state, include)}
    if not has_git_entry(root):
        return 200, {"git": _empty("not_git", include)}
    if api._project_git is None:
        return 200, {"git": _empty("unavailable", include)}
    try:
        return 200, {"git": _active(root, api._project_git, include)}
    except GitReadFailed as error:
        if error.code == "tool_unavailable":
            return 200, {"git": _empty("unavailable", include)}
        raise ApiRefusal.fixed("store_error") from None
    except OSError:
        raise ApiRefusal.fixed("store_error") from None


def _empty(state, include):
    return {"state": state, "unsupported": None, "head": None, "object_format": None,
            "dirty_paths": None, "exclude": None,
            "agent_instructions": {"found": None, "default_include": include},
            "remotes": None, "tools": None, "signing": None}


def _last_choice(api, root):
    records = [record for task in api._tasks.tasks()
               if (record := read_seed(root, task)) is not None]
    latest = max(records, key=lambda row: (row.staged_at, row.task_id), default=None)
    return False if latest is None else latest.include_agent_instructions


def _active(root, git, include):
    admission = repository_admission(root, git)
    result = _empty(admission.state, include)
    if admission.state != "repo":
        if admission.state == "unsupported":
            result["unsupported"] = {"reason": "tracks_product_dir",
                                     "names": list(admission.tracked)}
        return result
    head = read_head(root, git)
    form = _checked(git(["-C", str(root), "rev-parse", "--show-object-format"], True)).strip()
    if form not in (b"sha1", b"sha256"):
        raise GitReadFailed("git_failed")
    listing = b"" if head is None else _checked(git(
        ["-C", str(root), "ls-tree", "-r", "--name-only", "-z", head.commit], True,
        output_limit=_LIMIT))
    paths = _names(listing)
    version = _checked(git(["--version"], True)).decode("ascii", errors="replace").strip()
    match = _VERSION.fullmatch(version)
    if match is None:
        raise GitReadFailed("git_failed")
    result.update(state="unborn" if head is None else "repo",
                  head=None if head is None else {"ref": head.ref, "commit": head.commit},
                  object_format=form.decode("ascii"), dirty_paths=_dirty(root, git),
                  exclude=_exclude(root),
                  agent_instructions={"found": sum(_is_instruction(path) for path in paths
                                                   if not is_product_path(path)),
                                      "default_include": include},
                  remotes=_remotes(root, git),
                  tools={"git": {"version": match.group(1)}, "gh": None},
                  signing=_signing(root, git))
    return result


def _checked(answer, *, absent=False):
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if absent and answer.exit_code == 1 and not answer.output:
        return b""
    if answer.exit_code != 0 or answer.truncated:
        raise GitReadFailed("git_failed")
    return answer.output


def _names(raw):
    if raw and not raw.endswith(b"\0"):
        raise GitReadFailed("git_failed")
    return [part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\0") if part]


def _dirty(root, git):
    try:
        answer = git(["--no-optional-locks", "-C", str(root), "status", "--porcelain=v1",
                      "-z", "--untracked-files=all"], True, output_limit=_LIMIT)
    except GitReadFailed as error:
        if error.code == "git_timed_out":
            return None
        raise
    if answer.timed_out or answer.exit_code is None or answer.truncated:
        return None
    rows = iter(_names(_checked(answer)))
    count = 0
    for row in rows:
        if len(row) < 4 or row[2] != " ":
            raise GitReadFailed("git_failed")
        paths = [row[3:]]
        if "R" in row[:2] or "C" in row[:2]:
            previous = next(rows, None)
            if previous is None:
                raise GitReadFailed("git_failed")
            paths.append(previous)
        count += any(not is_product_path(path) for path in paths)
    return count


def _remotes(root, git):
    raw = _checked(git(["-C", str(root), "config", "-z", "--get-regexp",
                        r"^remote\..*\.url$"], True), absent=True)
    remotes = []
    for record in _names(raw):
        key, separator, value = record.partition("\n")
        match = _REMOTE.fullmatch(key)
        if separator and match is not None:
            github, credentials = _remote_target(value)
            remotes.append({"name": match.group(1), "github": github,
                            "url_has_credentials": credentials})
    return sorted(remotes, key=lambda row: (row["name"], row["github"] or ""))


def _remote_target(value):
    """Expose a GitHub owner/repo and a credential flag, never the remote URL."""
    if value.startswith("git@github.com:"):
        match = _GITHUB.fullmatch(value[len("git@github.com:"):])
        return (match.group(1) if match else None), False
    try:
        parsed = urlsplit(value)
        credentials = bool(parsed.password or parsed.query or parsed.fragment or
                           (parsed.username and not
                            (parsed.scheme == "ssh" and parsed.username == "git")))
        match = _GITHUB.fullmatch(parsed.path) if parsed.hostname == "github.com" else None
        allowed = parsed.scheme in ("https", "http", "ssh")
        return (match.group(1) if allowed and match else None), credentials
    except ValueError:
        return None, True


def _signing(root, git):
    value = _checked(git(["-C", str(root), "config", "--bool", "--get", "commit.gpgsign"],
                        True), absent=True).strip()
    if value not in (b"", b"true", b"false"):
        raise GitReadFailed("git_failed")
    return value == b"true"


def _exclude(root):
    """Inspect the local block without following a portal or writing an exclude file."""
    folder = Path(root) / ".git"
    for path in (folder, folder / "info"):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return "absent"
        if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_reparse_tag", 0):
            return "deferred"
    target = folder / "info" / "exclude"
    try:
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_reparse_tag", 0):
            return "absent"
        with target.open("rb") as stream:
            raw = stream.read(_LIMIT + 1)
    except FileNotFoundError:
        return "absent"
    if len(raw) > _LIMIT:
        return "absent"
    lines = [line.rstrip() for line in raw.splitlines()]
    begin, end = BLOCK_BEGIN.encode(), BLOCK_END.encode()
    if begin not in lines or end not in lines:
        return "absent"
    start = lines.index(begin)
    finish = lines.index(end)
    return "present" if start < finish and all(
        line.encode() in lines[start + 1:finish] for line in EXCLUDE_LINES) else "absent"
