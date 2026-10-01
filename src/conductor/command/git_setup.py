"""Explicit init/exclude and read-only first-commit preview (§9.8)."""
from __future__ import annotations

import os

from conductor.ownership_errors import OwnerRefused
from . import git_setup_facts as facts
from .accept_manifest import SnapshotRefused
from .adapters.harness_workspace import WorkspaceBusy, root_turn
from .adapters.process import OwnershipError, ProcessRunner
from .api_refusals import ApiRefusal
from .authorization_terms import human_identity
from .contract_values import ContractError
from .git_setup_records import SetupRefused, publish, receipt
from .git_setup_snapshot import preview
from .project_git import GitReadFailed, has_git_entry
from .project_routes import _hold_git_allowed
from .seed_record import read_seed


def setup(api, body):
    _hold_git_allowed(api)
    if type(body) is not dict:
        raise ContractError("Git setup needs one closed step")
    step = body.get("step")
    if type(step) is not str:
        raise ContractError("Git setup needs a named step")
    if step in {"init", "exclude"} and set(body) == {"step", "actor"}:
        actor = human_identity("actor", body["actor"])
    elif (step == "first_commit" and set(body) == {"step", "mode", "preview"}
          and type(body["mode"]) is str and body["mode"] in {"snapshot", "empty"} and body["preview"] is True):
        actor = None
    else:
        raise ContractError("Git setup accepts init/exclude confirmation or first_commit preview")
    root = api._store.project_root
    try:
        with ProcessRunner.project_write_guard(root):
            if step == "first_commit":
                _reader(api)
                return 200, {"setup": preview(root, api._project_git, body["mode"])}
            with root_turn(root, wait=0), api._store.transaction():
                standing = receipt(root, step)
                if standing is not None:
                    if standing["requested_by"] != actor:
                        raise SetupRefused("setup_terms_changed")
                    return 200, {"setup": standing}
                _reader(api)
                warnings = _init(api) if step == "init" else []
                facts.admitted(root, api._project_git)
                form = facts.object_format(root, api._project_git)
                excluded = facts.exclude(root, api._project_git)
                row = publish(root, step, actor, api._clock(), form, excluded, warnings)
                return 201, {"setup": row}
    except WorkspaceBusy:
        raise ApiRefusal.git_setup_refused("task_run_active") from None
    except (OwnershipError, OwnerRefused):
        raise ApiRefusal.fixed("project_not_active") from None
    except SetupRefused as error:
        raise ApiRefusal.git_setup_refused(error.reason) from None
    except SnapshotRefused as error:
        reason = "git_identity_missing" if error.reason == "git_identity_missing" else "setup_damaged"
        raise ApiRefusal.git_setup_refused(reason) from None
    except GitReadFailed as error:
        if error.code == "tool_unavailable":
            raise ApiRefusal.tool_unavailable("git", error.reason) from None
        raise ApiRefusal.git_setup_refused(error.code) from None
    except (OSError, UnicodeError):
        raise ApiRefusal.git_setup_refused("git_failed") from None


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
