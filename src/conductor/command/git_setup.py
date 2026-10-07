"""Explicit init/exclude and read-only first-commit preview (§9.8)."""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass

from conductor.ownership_errors import OwnerRefused
from . import git_setup_facts as facts
from . import git_setup_first as first
from .accept_manifest import SnapshotRefused
from .accept_records import _text as _one_line
from .adapters.harness_workspace import WorkspaceBusy, root_turn
from .adapters.process import OwnershipError, ProcessRunner
from .api_refusals import ApiRefusal
from .authorization_terms import human_identity
from .contract_values import ContractError, _digest
from .git_setup_records import SetupRefused, publish, receipt
from .git_setup_snapshot import preview
from .project_git import GitReadFailed, has_git_entry
from .project_routes import _hold_git_allowed
from .seed_record import read_seed

MODES = frozenset({"snapshot", "empty"})
#: Publication stays closed until the compatibility gate on the lowest supported Git is closed
#: (review ruling OD-11): while this is False the confirm shape is refused `contract_invalid`,
#: as it was before the writer existed. It is the one place an index of ours can reach an owner's
#: repository through the route, and a test, never a setting, opens it.
_CONFIRM_OPEN = False


@dataclass(frozen=True)
class Request:
    """One accepted body: `kind` is init, exclude, preview or confirm."""

    kind: str
    actor: str | None = None
    mode: str | None = None
    digest: str | None = None


def parse(body: object) -> Request:
    """The closed shapes of spec 9.5 for this route, and nothing else."""
    if type(body) is not dict:
        raise ContractError("Git setup needs one closed step")
    step = body.get("step")
    if type(step) is not str:
        raise ContractError("Git setup needs a named step")
    keys = set(body)
    if step in {"init", "exclude"} and keys == {"step", "actor"}:
        return Request(step, actor=human_identity("actor", body["actor"]))
    if (step == "first_commit" and keys == {"step", "mode", "preview"}
            and type(body["mode"]) is str and body["mode"] in MODES
            and body["preview"] is True):
        return Request("preview", mode=body["mode"])
    if (_CONFIRM_OPEN and step == "first_commit"
            and keys == {"step", "mode", "paths_digest", "actor"}):
        return _confirmation(body)
    raise ContractError("Git setup accepts init/exclude confirmation or first_commit preview")


def _confirmation(body: dict) -> Request:
    """The confirm body: `paths_digest` is null exactly for `empty` and the shown digest else."""
    mode, digest = body["mode"], body["paths_digest"]
    if type(mode) is not str or mode not in MODES:
        raise ContractError("first_commit mode must be snapshot or empty")
    if (digest is None) != (mode == "empty"):
        raise ContractError("paths_digest is null exactly for the empty mode")
    try:
        actor = _one_line(human_identity("actor", body["actor"]))
    except ValueError:
        raise ContractError("actor must be one line of text") from None
    return Request("confirm", actor=actor, mode=mode,
                   digest=None if digest is None else _digest("paths_digest", digest))


@contextmanager
def _refusals():
    """The one translation of the writers' failures into the closed refusal."""
    try:
        yield
    except WorkspaceBusy:
        raise ApiRefusal.git_setup_refused("task_run_active") from None
    except (OwnershipError, OwnerRefused):
        raise ApiRefusal.fixed("project_not_active") from None
    except SetupRefused as error:
        raise ApiRefusal.git_setup_refused(error.reason) from None
    except SnapshotRefused as error:
        known = error.reason == "git_identity_missing"
        raise ApiRefusal.git_setup_refused(
            "git_identity_missing" if known else "setup_damaged") from None
    except GitReadFailed as error:
        if error.code == "tool_unavailable":
            raise ApiRefusal.tool_unavailable("git", error.reason) from None
        raise ApiRefusal.git_setup_refused(error.code) from None
    except (OSError, UnicodeError):
        raise ApiRefusal.git_setup_refused("git_failed") from None


def setup(api, body):
    _hold_git_allowed(api)
    request = parse(body)
    root = api._store.project_root
    with _refusals(), ProcessRunner.project_write_guard(root):
        if request.kind == "preview":
            _reader(api)
            return 200, {"setup": preview(root, api._project_git, request.mode)}
        if request.kind == "confirm":
            _reader(api)
            return first.confirm(api, request)
        return _step(api, request)


def _step(api, request):
    root = api._store.project_root
    with root_turn(root, wait=0), api._store.transaction():
        standing = receipt(root, request.kind)
        if standing is not None:
            if standing["requested_by"] != request.actor:
                raise SetupRefused("setup_terms_changed")
            return 200, {"setup": standing}
        _reader(api)
        warnings = _init(api) if request.kind == "init" else []
        facts.admitted(root, api._project_git)
        form = facts.object_format(root, api._project_git)
        excluded = facts.exclude(root, api._project_git)
        row = publish(root, request.kind, request.actor, api._clock(), form, excluded, warnings)
        return 201, {"setup": row}


def _reader(api):
    if api._project_git is None:
        raise ApiRefusal.tool_unavailable("git", "not_pinned")


def _init(api):
    root, git = api._store.project_root, api._project_git
    if os.path.lexists(root / ".git"):
        raise SetupRefused("already_git")
    empty = False
    for task_id in api._tasks.tasks():
        seed = read_seed(root, task_id)
        if seed is not None:
            if seed.work_scope != api._tasks.read(task_id).work_scope:
                raise SetupRefused("setup_damaged")
            empty |= seed.source == "empty"
    nested = has_git_entry(root.parent)
    args = ["init", *(["--object-format=sha1"] if empty else []), str(root)]
    # Never pass -b: init.defaultBranch remains the owner's choice.
    facts.call(root, git, *args)
    return ["nested_repository"] if nested else []
