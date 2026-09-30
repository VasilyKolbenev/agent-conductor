"""The door of a task's seed: `POST /command/tasks/<task_id>/seed` (spec 9.1.1 to 9.1.6).

The desk asks for the code of the project to be copied into the folder of a task, once per task and
work item, with the conditions the owner chose: a source (`git` or `empty`), the commit the desk
showed (`expect_commit`), and whether the instruction files of the project come along. The answer is
the record that stands with its state read off the disk.

- A record that stands decides first: the same conditions answer 200 with it, other conditions are
  `seed_exists` naming its base. Conditions are equal when the source and the switch are, and the
  expected commit is none or the standing base (so a repeat after HEAD moved still agrees).
- In a project served to view, git is never asked (9.1.6): a git seed leaves a request (201) and
  reads back `requested`, an exact repeat is 200, other conditions are `seed_exists`, and no
  expected commit is taken. An empty seed needs no git and works as in an active project.
- In an active project a fresh seed admits the repository, reads the base, checks the expected
  commit (`base_moved`), stages the tree outside `work/`, writes the record, and tries the move
  under `work/` (9.1.4): 201 `seeded` when it is made, 202 `staged` while another turn holds the
  root. A repeat of a staged seed tries the move again; a task folder that holds anything is
  `work_not_empty` (asked before anything is staged, and again at the move); a seed whose staging
  and folder are both gone is `seed_lost`. A view server moves nothing.

One seed is made at a time per project, so two requests for one task cannot stage over each other.
Git failures and the plan's refusals are the words of `seed_refused`; a pinned git that cannot be
used is `tool_unavailable`.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from . import seed_stage
from .api_contracts import ApiRefusal
from .api_refusals import TOOL_REASONS
from .project_git import GitReadFailed, has_git_entry, repository_admission
from .seed_plan import SeedRefusal
from .adapters.harness_workspace import WorkspaceBusy
from .seed_record import (
    SOURCES, WORK_ITEM_ID, SeedRecord, SeedRecordTooLarge, SeedRequest, read_request, read_seed,
    seed_state, write_request, write_seed)
from .store_errors import StoreError
from .task_contracts import frozen_config_task
from .task_routes import resolve_task_binding

if TYPE_CHECKING:  # pragma: no cover - the boundary this module is called by, never built here
    from .http_api import CommandApi

_Reply = tuple[int, dict[str, Any]]
_T = TypeVar("_T")
_KEYS = frozenset({"work_item_id", "source", "expect_commit", "include_agent_instructions"})
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
#: The reason of a repository state that is not `repo` (spec 9.1.3). A folder git will not trust
#: is a git that failed, for the desk's purpose: it cannot read the base.
_STATE_REASON = {"not_git": "not_a_git_repository", "not_repo_root": "project_not_repo_root",
                 "unsupported": "tracks_product_dir", "unsafe_directory": "git_failed"}
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[Path, threading.Lock] = {}


@dataclass(frozen=True)
class _Asked:
    """The conditions of one request: what the owner chose, and nothing the server decides."""

    source: str
    expect_commit: str | None
    include: bool


def seed_task(api: CommandApi, task_id: str, body: object) -> _Reply:
    """`POST /command/tasks/<task_id>/seed`: make the seed, or say what stands, or what refuses.

    Raises:
        ApiRefusal: `contract_invalid`; `service_refused` for a task this build does not hold;
            `seed_refused` with one word of 9.1.3; `tool_unavailable` for a pinned git that
            cannot be used; `project_not_active` is never raised here (a view server answers).
    """
    viewing = api._identity.mode == "view"
    asked = _parse(body, viewing)
    binding = resolve_task_binding(api._tasks, task_id)
    assert binding is not None
    root = api._store.project_root
    with _one_at_a_time(root):
        standing = read_seed(root, task_id)
        if standing is not None:
            return _standing(root, standing, asked, viewing)
        if viewing and asked.source == "git":
            return _requested(root, task_id, asked, api._clock())
        return _made(api, root, binding.work_scope, task_id, asked)


def _parse(body: object, viewing: bool) -> _Asked:
    """The four keys of 9.1.1, closed and typed; a view server takes no expected commit."""
    if not isinstance(body, Mapping) or set(body) != _KEYS:
        raise ApiRefusal.fixed("contract_invalid")
    source, commit = body["source"], body["expect_commit"]
    include = body["include_agent_instructions"]
    lawful = (body["work_item_id"] == WORK_ITEM_ID and isinstance(source, str)
              and source in SOURCES and type(include) is bool
              and (commit is None or (type(commit) is str and _OBJECT_ID.match(commit))))
    if not lawful or (commit is not None and (source != "git" or viewing)):
        raise ApiRefusal.fixed("contract_invalid")
    return _Asked(source, commit, include)


def _standing(root: Path, standing: SeedRecord, asked: _Asked, viewing: bool) -> _Reply:
    same = (standing.source == asked.source and standing.include_agent_instructions == asked.include
            and asked.expect_commit in (None, standing.base_commit))
    if not same:
        raise ApiRefusal.seed_refused("seed_exists", standing.base_commit)
    state = seed_state(root, standing)
    if state == "seed_lost":
        raise ApiRefusal.seed_refused("seed_lost")
    if state == "staged" and not viewing:
        state = _moved(root, standing)
    return 200, {**standing.as_dict(), "state": state}


def _requested(root: Path, task_id: str, asked: _Asked, now: str) -> _Reply:
    """In a project served to view: leave the request, or agree with the one that stands."""
    stored = read_request(root, task_id)
    created = stored is None
    if created:
        write_request(root, SeedRequest(task_id, WORK_ITEM_ID, asked.include, now))
        stored = read_request(root, task_id)
    assert stored is not None
    if stored.include_agent_instructions != asked.include:
        raise ApiRefusal.seed_refused("seed_exists")
    return (201 if created else 200), {**stored.as_dict(), "state": "requested"}


def _made(api: CommandApi, root: Path, scope: str, task_id: str, asked: _Asked) -> _Reply:
    """A fresh seed in an active project, or an empty one anywhere: stage it, record it."""
    request = read_request(root, task_id)
    if request is not None and request.include_agent_instructions != asked.include:
        raise ApiRefusal.seed_refused("seed_exists")
    now = api._clock()
    _translated(lambda: seed_stage.hold_target_free(root, scope, WORK_ITEM_ID))
    if asked.source == "empty":
        record = _staged_empty(root, scope, task_id, asked, now)
    else:
        record = _staged_from_git(api, root, scope, task_id, asked, now)
    _record(root, record)
    state = _moved(root, record)
    return (201 if state == "seeded" else 202), {**record.as_dict(), "state": state}


def _moved(root: Path, record: SeedRecord) -> str:
    """Try the move under `work/`; the state after it. A busy root leaves the seed staged."""
    try:
        _translated(lambda: seed_stage.move_staged(root, record))
    except WorkspaceBusy:
        pass
    return seed_state(root, record)


def _staged_empty(root: Path, scope: str, task_id: str, asked: _Asked, now: str) -> SeedRecord:
    if has_git_entry(root):
        raise ApiRefusal.seed_refused("empty_not_allowed")
    return seed_stage.stage_empty(
        root, task_id=task_id, work_scope=scope, work_item_id=WORK_ITEM_ID, staged_at=now,
        include_agent_instructions=asked.include)


def _staged_from_git(api: CommandApi, root: Path, scope: str, task_id: str, asked: _Asked,
                     now: str) -> SeedRecord:
    git = api._project_git
    if git is None:
        raise ApiRefusal.seed_refused("git_failed")

    def stage() -> SeedRecord:
        state = repository_admission(root, git).state
        if state != "repo":
            raise SeedRefusal(_STATE_REASON[state])
        base = seed_stage.read_base(root, git)
        if base is None:
            raise SeedRefusal("unborn_head")
        if asked.expect_commit not in (None, base.commit):
            raise SeedRefusal("base_moved", base.commit)
        return seed_stage.stage_from_git(
            root, git, task_id=task_id, work_scope=scope, work_item_id=WORK_ITEM_ID, base=base,
            include_agent_instructions=asked.include, staged_at=now)

    return _translated(stage)


def _record(root: Path, record: SeedRecord) -> None:
    """Write the record: the point of commitment; if it cannot be, nothing staged is kept."""
    try:
        write_seed(root, record)
    except SeedRecordTooLarge:
        seed_stage.remove_staging(root, record.staging)
        raise ApiRefusal.seed_refused("seed_too_large") from None
    except BaseException:
        seed_stage.remove_staging(root, record.staging)
        raise


def _translated(call: Callable[[], _T]) -> _T:
    """Run what asks git or the disk, saying a refusal or a failure in the vocabulary's words."""
    try:
        return call()
    except OSError:
        raise ApiRefusal.fixed("store_error") from None
    except SeedRefusal as refused:
        raise ApiRefusal.seed_refused(refused.reason, refused.commit) from None
    except GitReadFailed as failed:
        if failed.code == "tool_unavailable" and failed.reason in TOOL_REASONS:
            raise ApiRefusal.tool_unavailable("git", failed.reason) from None
        raise ApiRefusal.seed_refused(
            "git_timed_out" if failed.code == "git_timed_out" else "git_failed") from None


@contextmanager
def _one_at_a_time(root: Path) -> Iterator[None]:
    """One seed of this project at a time: two requests for a task never stage over each other."""
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(root, threading.Lock())
    with lock:
        yield


def make_seeds(api: CommandApi) -> SeedSettler:
    """The settler of this API's project, for the driver to ask (spec 9.1.4)."""
    return SeedSettler(api)


class SeedSettler:
    """What the driver asks before the first action of a run: is the seed of its task in place?

    `settle(run_id)` is True when nothing of the seed keeps the run from acting: the run has no
    task, performs no dispatch (its review steps never read the work folder), or its task was
    never seeded and nobody asked for a seed (it starts from its folder as before). Otherwise it
    sees to it: a request a view server left is made into a seed from HEAD at this moment, a
    staged seed is moved under the root's turn. It is False while it cannot, and says no more:
    the reason is learned by asking the seed door again, which answers it in `detail.reason`.
    """

    def __init__(self, api: CommandApi) -> None:
        self._api = api

    def settle(self, run_id: str) -> bool:
        """See the class text. Runs only in an active project, where the driver lives."""
        api = self._api
        recovered = api._store.read(run_id)
        graph = next((row.value for row in recovered.records
                      if row.kind == "graph_definition"), None)
        binding = frozen_config_task(recovered.config)
        if binding is None or graph is None or not any(
                node.capability == "dispatch" for node in graph.nodes):
            return True
        root = api._store.project_root
        with _one_at_a_time(root):
            try:
                return self._settled(root, binding.task_id, binding.work_scope)
            except (WorkspaceBusy, SeedRefusal, ApiRefusal, StoreError, OSError):
                return False

    def _settled(self, root: Path, task_id: str, scope: str) -> bool:
        record = read_seed(root, task_id)
        if record is None:
            request = read_request(root, task_id)
            if request is None:
                return True
            asked = _Asked("git", None, request.include_agent_instructions)
            _translated(lambda: seed_stage.hold_target_free(root, scope, WORK_ITEM_ID))
            record = _staged_from_git(self._api, root, scope, task_id, asked, self._api._clock())
            _record(root, record)
        state = seed_state(root, record)
        if state == "staged":
            seed_stage.move_staged(root, record)
            state = seed_state(root, record)
        return state == "seeded"
