"""Reading a project folder's git, read-only, through the one execution door (spec 9.2, 9.3).

`repository_admission` is the first thing of this module and it is called before a project is
added: it asks git two questions, changes nothing, and answers a closed state. The git it runs is
handed in as a reader, not found here. The pinned executable and the environment it runs under
belong to the tool pins (8.8, 8.9), and the product never searches PATH for one (9.3); so the
caller builds the reader once, with `process_git_read` over its own `ProcessRunner`.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .adapters.process import CommandSpec, ProcessRunner
from .product_names import PRODUCT_TOP_NAMES

#: Flags every git call of the product carries (spec 9.3). Hooks are switched off by the
#: environment, never by a flag.
GIT_FLAGS = ("-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false")
READ_TIMEOUT_SECONDS = 60
#: What one read may bring back; a longer answer is cut and says so.
READ_OUTPUT_LIMIT = 1024 * 1024
#: The words git prints when it will not trust a folder that another account owns. The probe runs
#: with `LC_ALL=C` (8.9), so they are the English ones.
_DUBIOUS_OWNERSHIP = b"detected dubious ownership"
#: The state of each refusal of spec 9.2, and the code a caller refuses with.
_REFUSALS = {"not_repo_root": "project_not_repo_root", "unsupported": "tracks_product_dir"}


@dataclass(frozen=True)
class GitAnswer:
    """What one git call said: its exit code (None when it was cut short) and its output."""

    exit_code: int | None
    output: bytes
    truncated: bool = False
    timed_out: bool = False


#: One call: `git(args, separate_stderr=False)`. `separate_stderr` keeps the child's diagnostics
#: out of `output`, for a caller that parses stdout as data.
GitRead = Callable[..., GitAnswer]


class GitReadFailed(Exception):
    """git itself failed; `code` is `git_failed`, `git_timed_out` or `tool_unavailable`.

    No text is kept. `reason` is set only with `tool_unavailable` (spec 9.3): `not_pinned`,
    `version_changed` or `missing`.
    """

    def __init__(self, code: str, exit_code: int | None = None,
                 reason: str | None = None) -> None:
        super().__init__(code)
        self.code, self.exit_code, self.reason = code, exit_code, reason


@dataclass(frozen=True)
class RepositoryAdmission:
    """The verdict on a project folder.

    `state` is one of `repo`, `not_git`, `not_repo_root`, `unsupported`, `unsafe_directory`
    (the words of spec 6.2.1). `tracked` names the top-level product names a repository tracks
    when it is `unsupported`.
    """

    state: str
    tracked: tuple[str, ...] = ()

    @property
    def refusal(self) -> str | None:
        """The refusal code of spec 9.2 when the folder may not be a project, else None."""
        return _REFUSALS.get(self.state)


def process_git_read(runner: ProcessRunner, git_path: str, cwd: str, *,
                     env_allow: Sequence[str] = (),
                     env: Mapping[str, str] | None = None) -> GitRead:
    """A reader that runs the pinned `git_path` through `runner`, in `cwd`.

    The runner refuses a `cwd` that is not strictly beneath its own root, so the caller chooses a
    folder of its own for it; the repository is named by `-C` in each call, not by `cwd`.
    """
    def read(args: Sequence[str], separate_stderr: bool = False) -> GitAnswer:
        outcome = runner.run(CommandSpec(
            argv=(git_path, *GIT_FLAGS, *args), cwd=cwd, env_allow=tuple(env_allow),
            env=dict(env or {}), output_limit=READ_OUTPUT_LIMIT,
            timeout_seconds=READ_TIMEOUT_SECONDS, separate_stderr=separate_stderr))
        return GitAnswer(exit_code=outcome.exit_code, output=outcome.output,
                         truncated=outcome.output_truncated,
                         timed_out=outcome.status == "timed_out")
    return read


def repository_admission(root: str | os.PathLike[str], git: GitRead) -> RepositoryAdmission:
    """Say whether `root` may become a project, reading and never writing.

    A folder with no `.git` entry at itself or above is `not_git` and no process runs. Otherwise
    `rev-parse --show-toplevel` must name `root` itself (else `not_repo_root`: a subfolder of a
    larger repository), and `ls-files -z` over the product's top names must find nothing tracked
    (else `unsupported`: activation would move a folder the repository tracks).

    Raises:
        ValueError: `root` is not absolute. A relative path has no ancestors to search for a
            `.git` entry and git would read it against the working folder, so it is a fault of
            the caller and not an answer about a folder.
        GitReadFailed: git failed or ran out of time.
    """
    folder = Path(root)
    if not folder.is_absolute():
        raise ValueError("repository_admission needs an absolute root")
    if not _under_git(folder):
        return RepositoryAdmission("not_git")
    probe = git(["-C", str(folder), "rev-parse", "--show-toplevel"], separate_stderr=False)
    _raise_unless_ran(probe)
    if probe.exit_code != 0:
        if _DUBIOUS_OWNERSHIP in probe.output:
            return RepositoryAdmission("unsafe_directory")
        raise GitReadFailed("git_failed", probe.exit_code)
    if not _same_folder(folder, _last_line(probe.output)):
        return RepositoryAdmission("not_repo_root")
    listing = git(["-C", str(folder), "ls-files", "-z", "--", *PRODUCT_TOP_NAMES],
                  separate_stderr=True)
    _raise_unless_ran(listing)
    if listing.exit_code != 0:
        raise GitReadFailed("git_failed", listing.exit_code)
    tracked = _top_names(listing.output)
    return RepositoryAdmission("unsupported", tracked) if tracked else RepositoryAdmission("repo")


def _under_git(folder: Path) -> bool:
    """Whether `folder` or an ancestor holds a `.git` entry (looked at, never followed)."""
    return any(os.path.lexists(place / ".git") for place in (folder, *folder.parents))


def _raise_unless_ran(answer: GitAnswer) -> None:
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")


def _last_line(output: bytes) -> str:
    lines = [line for line in output.decode("utf-8", errors="replace").splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


def _same_folder(folder: Path, other: str) -> bool:
    """Whether two spellings name one folder: by identity, else by resolved path."""
    if not other:
        return False
    try:
        return os.path.samefile(folder, other)
    except OSError:
        return os.path.normcase(os.path.realpath(folder)) == os.path.normcase(
            os.path.realpath(other))


def _top_names(output: bytes) -> tuple[str, ...]:
    """The first path component of every listed path, once each, in order."""
    paths = (raw.decode("utf-8", errors="replace") for raw in output.split(b"\0") if raw)
    return tuple(sorted({path.split("/", 1)[0] for path in paths}))
