"""Read-only acceptance preview: journal authority, saved bytes, live seal and pinned Git."""
from __future__ import annotations

import re

from . import accept_material, accept_terms
from .accept_context import read_context
from .accept_git import read_git
from .accept_manifest import MAX_BYTES, MAX_FILES, SnapshotRefused
from .api_refusals import ApiRefusal
from .project_git import GitReadFailed
from .project_routes import _hold_git_allowed
from .seed_stage import SeedRefusal
from .seed_plan import is_lfs_pointer


def preview(api, run_id, body):
    _hold_git_allowed(api)
    options = accept_terms.asked(body)
    context = read_context(api, run_id)
    if context.basis.refused:
        raise ApiRefusal.accept_refused(context.basis.refused)
    if api._project_git is None:
        raise ApiRefusal.tool_unavailable("git", "not_pinned")
    try:
        result = _preview(api, context, options)
        # No root gate is held during Git/work reads. Recheck admission after those reads;
        # a newly queued/started/later task run invalidates this projection immediately.
        current = read_context(api, run_id)
        if current.basis.refused:
            raise SnapshotRefused(current.basis.refused)
        if (current.basis, current.task, current.workflow, current.seed) != (
                context.basis, context.task, context.workflow, context.seed):
            raise SnapshotRefused("accept_terms_changed")
        return 200, {"accept": result}
    except SnapshotRefused as error:
        raise ApiRefusal.accept_refused(error.reason) from None
    except SeedRefusal as error:
        reason = "result_too_large" if error.reason == "seed_too_large" else error.reason
        raise ApiRefusal.accept_refused(reason) from None
    except GitReadFailed as error:
        if error.code == "tool_unavailable":
            raise ApiRefusal.tool_unavailable("git", error.reason) from None
        raise ApiRefusal.accept_refused(error.code) from None
    except (OSError, UnicodeError):
        raise ApiRefusal.accept_refused("git_failed") from None


def _preview(api, context, options):
    facts = read_git(api._store.project_root, api._project_git, context.seed)
    run_id, kind = context.recovered.envelope.run_id, context.basis.kind
    branch = facts.branch(options.get("branch", f"conduct/{run_id}"))
    author = facts.author()
    listing = facts.listing()
    rows, after, skipped, count = ([], {}, [], 0)
    if kind == "files":
        rows, after, skipped, count = accept_material.files(context, facts, listing)
    docs = accept_material.documents(context, options.get("documents"))
    overlay = kind == "files" and context.seed.source == "empty"
    rows, before = accept_material.overlay(rows, after, listing, facts, overlay_base=overlay)
    documents = accept_material.add_documents(rows, after, docs, listing, facts)
    accept_material.hold_overlay_paths(rows, listing)
    for row in documents:
        if row["path"] in listing:
            before[row["path"]] = facts.blob(listing[row["path"]])
    if not rows:
        raise SnapshotRefused("nothing_to_accept")
    if len(rows) > MAX_FILES or sum(row.length for row in rows) > MAX_BYTES:
        raise SnapshotRefused("result_too_large")
    if len({row.path.casefold() for row in rows}) != len(rows):
        raise SnapshotRefused("case_collision")
    basis, message = accept_terms.basis_and_message(context, options.get("title", context.task.title))
    basis["manifest_rows"] = count
    files = [{**row.as_dict(), "binary": accept_terms.binary(after.get(row.path, before.get(row.path, b"")))}
             for row in sorted(rows, key=lambda row: row.path)]
    base = facts.head_facts((row["path"] for row in files), context.seed)
    warnings = _warnings(facts, files, before, after, base, overlay)
    result = {"run_id": run_id, "task_id": context.task.task_id, "kind": kind,
              "basis": basis, "base": base, "branch": branch, "author": author,
              "message": message, "files": files, "skipped": sorted(skipped, key=lambda row: row["path"]),
              "documents": documents, "patch": accept_terms.patch(files, before, after),
              "warnings": warnings, "github": None}
    accept_terms.seal_terms(result)
    return result


def _warnings(facts, files, before, after, base, overlay):
    warnings = ["hooks_not_run"]
    sign = facts.call("config", "--get", "--type=bool", "commit.gpgSign", absent=True).strip()
    if sign == b"true":
        warnings.append("signing_required")
    elif sign not in (b"", b"false"):
        raise GitReadFailed("git_failed")
    if overlay:
        warnings.append("overlay_base")
    if base["head_now"] != base["commit"]:
        warnings.append("base_behind_head")
    if base["overlap"]:
        warnings.append("overlap_with_head")
    for row in files:
        path, data = row["path"], after.get(row["path"], b"")
        name = path.rsplit("/", 1)[-1].casefold()
        if name.startswith((".env", "id_rsa")) or name.endswith((".pem", ".key")):
            warnings.append("suspicious_name")
        if len(str(facts.root / path)) >= 260:
            warnings.append("long_path_checkout")
        if is_lfs_pointer(data):
            warnings.append("lfs_pointer")
        old = before.get(path)
        if old is not None and not row["binary"] and not accept_terms.binary(old):
            endings = lambda value: set(re.findall(rb"\r\n|(?<!\r)\n|\r(?!\n)", value))
            if endings(old) != endings(data):
                warnings.append("line_endings_changed")
    return list(dict.fromkeys(warnings))
