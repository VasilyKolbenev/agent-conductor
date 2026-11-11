"""Materialize only the selected initial source-context policy, never model-authored paths."""
from .codex_patch import PatchRefused
from .codex_patch_sources import source_section

SOURCE_REF = "source-context"
SOURCE_TOKEN = "conduct.review-sources.v1"
SOURCE_MARKER = "\n\n" + SOURCE_TOKEN + "\n"


def materialize(transport, args, inputs, task):
    """The returned tree belongs to these source bytes and survives the version preflight."""
    eligible = [doc for doc in inputs if doc.artifact_ref == SOURCE_REF
                and doc.source_action_id is None]
    if not eligible:
        return task, None
    if len(eligible) != 1:
        raise PatchRefused("ambiguous review source context")
    document, = eligible
    if SOURCE_TOKEN not in document.content:
        return task, None
    if (document.content.count(SOURCE_TOKEN) != 1
            or document.content.count(SOURCE_MARKER) != 1):
        raise PatchRefused("invalid initial review source context")
    work = transport._workspace.work_dir(args.work_item_id, args.task_scope)
    before = transport._workspace.digest_work_tree()
    section = source_section(transport._workspace, args, work, before, document,
        lambda: (*transport._sensitive_values(), *transport._login_seen), marker=SOURCE_MARKER)
    return task + section, before
