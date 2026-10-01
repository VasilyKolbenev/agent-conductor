"""Explicit human commit confirmation, with durable intent and local ref recovery."""
from __future__ import annotations

from .accept_context import read_context
from .accept_manifest import SnapshotRefused
from .accept_plumbing import SigningRequired, materialize, ref_oid
from .accept_preview import plan_preview
from .accept_records import read_records
from .accept_snapshot import read_snapshot
from .accept_store import intents, write_commit, write_intent
from .adapters.harness_workspace import WorkspaceBusy, root_turn
from .adapters.process import ProcessRunner
from .api_refusals import ApiRefusal
from .authorization_terms import human_identity
from .contract_values import ContractError, _digest
from .project_git import GitReadFailed
from .project_routes import _hold_git_allowed
from .seed_stage import SeedRefusal


def commit(api, run_id, body):
    _hold_git_allowed(api)
    if type(body) is not dict or set(body) != {"accept_digest", "actor"}:
        raise ContractError("accept commit needs exactly accept_digest and actor")
    digest = _digest("accept_digest", body["accept_digest"])
    actor = human_identity("actor", body["actor"])
    try:
        return _confirmed(api, run_id, digest, actor)
    except WorkspaceBusy:
        raise ApiRefusal.accept_refused("task_run_active") from None
    except SigningRequired as error:
        raise ApiRefusal.signing_required(**error.detail) from None
    except SnapshotRefused as error:
        raise ApiRefusal.accept_refused(error.reason) from None
    except SeedRefusal as error:
        raise ApiRefusal.accept_refused("result_too_large" if error.reason == "seed_too_large" else error.reason) from None
    except GitReadFailed as error:
        if error.code == "tool_unavailable":
            raise ApiRefusal.tool_unavailable("git", error.reason) from None
        raise ApiRefusal.accept_refused(error.code) from None
    except (OSError, UnicodeError):
        raise ApiRefusal.accept_refused("git_failed") from None


def _record(api, context, digest, actor):
    records = read_records(api._store.project_root, context.recovered.envelope.run_id,
                           task_id=context.task.task_id, kind=context.basis.kind)
    record = records["commit"]
    if record is not None and (record["accept_digest"] != digest or record["requested_by"] != actor):
        raise SnapshotRefused("acceptance_exists")
    return record


def _basis(context):
    if context.basis.refused:
        raise SnapshotRefused(context.basis.refused)


def _confirmed(api, run_id, digest, actor):
    root = api._store.project_root
    context = read_context(api, run_id)
    if context.task is None:
        raise SnapshotRefused("run_has_no_task")
    record = _record(api, context, digest, actor)
    if record is not None:
        return 200, {"commit": record}
    _basis(context)
    if api._project_git is None:
        raise ApiRefusal.tool_unavailable("git", "not_pinned")
    with api._store.transaction():
        prior = intents(root, run_id, context.task.task_id)
    intent = next((row for row in prior if row["accept_digest"] == digest), None)
    if intent is not None and intent["requested_by"] != actor:
        raise SnapshotRefused("accept_terms_changed")
    options = intent["options"] if intent is not None else api._accept_previews.read(run_id, digest)
    if options is None:
        raise SnapshotRefused("accept_terms_changed")
    # This complete read includes the live tree, and is deliberately outside the store gate.
    view, contents = plan_preview(api, context, options, allow_existing=intent is not None)
    if view["accept_digest"] != digest:
        raise SnapshotRefused("accept_terms_changed")
    with root_turn(root, wait=0), api._store.transaction(), ProcessRunner.project_write_guard(root):
        current = read_context(api, run_id)
        record = _record(api, current, digest, actor)
        if record is not None:
            return 200, {"commit": record}
        _basis(current)
        if (current.basis, current.task, current.workflow, current.seed) != (
                context.basis, context.task, context.workflow, context.seed):
            raise SnapshotRefused("accept_terms_changed")
        # Protect against another confirmation publishing a ref before its receipt.
        for older in intents(root, run_id, current.task.task_id):
            if older["accept_digest"] != digest:
                branch = older["options"].get("branch", f"conduct/{run_id}")
                if ref_oid(root, api._project_git, branch) is not None:
                    raise SnapshotRefused("acceptance_exists")
        if current.basis.kind == "files":
            fmt = "sha1" if len(view["base"]["commit"]) == 40 else "sha256"
            read_snapshot(root, run_id, current.basis.accept_manifest_digest, object_format=fmt)
        write_intent(root, run_id, current.task.task_id, digest, options, actor, api._clock())
        identity, tree, object_id = materialize(root, api._project_git, view, contents)
        record = {"schema_version": 1, "acceptance_id": identity, "run_id": run_id,
                  "task_id": current.task.task_id, "kind": current.basis.kind,
                  "base_commit": view["base"]["commit"], "commit": object_id, "tree": tree,
                  "branch": view["branch"], "accept_digest": digest,
                  "accept_manifest_digest": current.basis.accept_manifest_digest,
                  "file_count": len(view["files"]), "requested_by": actor, "recorded_at": api._clock()}
        return 201, {"commit": write_commit(root, record)}
