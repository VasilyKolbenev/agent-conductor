"""Real pinned Git reads; accepted bytes come from the immutable R6 snapshot."""
from dataclasses import replace
import json
import os
from types import SimpleNamespace

import pytest

from conductor.command.accept_capture import tree_digest
from conductor.command.accept_manifest import FileImage, build_snapshot
from conductor.command.accept_manifest import SnapshotRefused
from conductor.command.acceptance_basis import AcceptanceBasis
from conductor.command.accept_material import documents
from conductor.command.accept_snapshot import write_snapshot
from conductor.command.accept_terms import PATCH_LIMIT, patch, seal_terms
from conductor.command.artifacts import ArtifactDocument
from conductor.command.graph_template import GraphTemplate, TemplateNode
from conductor.command.project_claim import ProjectIdentity
from conductor.command.run_terminal import RunTerminal
from conductor.command.seed_record import SeedRecord
from conductor.ownership import data_root
from tests.git_repo_helpers import commit, git, needs_git, real_reader, repository, snapshot
from tests.test_accept_context import RUN, TASK, SCOPE, prepared
from tests.test_command_http_api import post
from tests.test_command_run_store import NOW, a_decision
from tests.test_seed_record import a_git_seed, an_empty_seed

PATH = f"/command/runs/{RUN}/accept/preview"


def project(tmp_path, *, empty=False):
    root = repository(tmp_path)
    base_files = {"old.txt": b"original\n", "gone.txt": b"delete me\n", "same.txt": b"unchanged\n"}
    head = commit(root, base_files)
    git("config", "user.name", "Preview Author", cwd=root)
    git("config", "user.email", "author@example.invalid", cwd=root)
    git("config", "core.autocrlf", "false", cwd=root)
    fmt = git("rev-parse", "--show-object-format", cwd=root).stdout.decode().strip()
    current = {"old.txt": b"reviewed\n", "new.txt": b"new bytes\n", "same.txt": b"unchanged\n",
               ".gitignore": b"ignored.txt\n", "ignored.txt": b"not transferred\n"}
    base = {} if empty else {path: FileImage(data) for path, data in base_files.items()}
    images = {path: FileImage(data) for path, data in current.items()}
    saved = build_snapshot(base, images, object_format=fmt)
    digest = write_snapshot(root, RUN, saved, object_format=fmt)
    record = SeedRecord.from_dict((an_empty_seed if empty else a_git_seed)(
        task_id=TASK, work_scope=SCOPE, base_commit=None if empty else head,
        base_tree=None if empty else git("rev-parse", "HEAD^{tree}", cwd=root).stdout.decode().strip(),
        object_format=None if empty else fmt, skipped=[], agent_instructions_skipped=[]))
    api = prepared(root, seed_record=record, proof_extra={
        "work_tree_digest": tree_digest(images), "accept_manifest_digest": digest})
    api._identity = ProjectIdentity("a" * 32, None, False, "active", None, None)
    api._project_git = real_reader(tmp_path)
    work = root / "work" / "_tasks" / SCOPE / "work-001"
    for path, data in current.items():
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return api, root, work, saved


@needs_git
def test_preview_transfers_saved_bytes_and_keeps_all_git_metadata_and_journal_unchanged(tmp_path):
    api, root, work, saved = project(tmp_path)
    before = snapshot(root / ".git")
    journal = (api._store.run_path(RUN) / "records.jsonl").read_bytes()
    answer = post(api, PATH, {})
    assert answer.status == 200, answer.payload
    view = answer.payload["accept"]
    assert view["github"] is None
    assert view["author"] == {"name": "Preview Author", "email": "author@example.invalid"}
    assert {(row["path"], row["state"]) for row in view["files"]} == {
        ("old.txt", "modified"), ("new.txt", "added"), ("gone.txt", "deleted"), (".gitignore", "added")}
    assert view["skipped"] == [{"path": "ignored.txt", "reason": "ignored_by_project"}]
    assert "+reviewed" in view["patch"]["text"]
    assert view["basis"]["accept_manifest_digest"] == saved.digest
    assert view["basis"]["manifest_rows"] == len(saved.rows)
    assert "Conduct-Acceptance: acc-" in view["message"]
    assert snapshot(root / ".git") == before
    assert (api._store.run_path(RUN) / "records.jsonl").read_bytes() == journal
    assert post(api, PATH, {}).payload == answer.payload


@needs_git
@pytest.mark.parametrize("damage", ["work", "blob", "alias"])
def test_moved_work_missing_blob_or_alias_never_becomes_transfer_bytes(tmp_path, damage):
    api, root, work, saved = project(tmp_path)
    if damage == "work":
        (work / "old.txt").write_bytes(b"unreviewed\n")
    elif damage == "blob":
        digest = saved.rows[0].sha256.removeprefix("sha256:")
        (data_root(root) / "accept" / RUN / "blobs" / digest).unlink()
    else:
        os.link(work / "old.txt", work / "alias.txt")
    before = snapshot(root / ".git")
    answer = post(api, PATH, {})
    assert answer.status == 409
    assert answer.payload["error"]["detail"]["reason"] == {
        "work": "work_changed_since_verification", "blob": "snapshot_damaged", "alias": "irregular_result"}[damage]
    assert snapshot(root / ".git") == before


@needs_git
def test_owner_head_change_updates_warning_without_changing_seed_based_acceptance_terms(tmp_path):
    api, root, work, saved = project(tmp_path)
    first = post(api, PATH, {}).payload["accept"]
    commit(root, {"old.txt": b"owner moved it\n"})
    second = post(api, PATH, {}).payload["accept"]
    assert first["accept_digest"] == second["accept_digest"]
    assert second["base"]["overlap"] == ["old.txt"]
    assert {"base_behind_head", "overlap_with_head"} <= set(second["warnings"])


@needs_git
def test_empty_seed_overlays_head_without_deleting_owner_files(tmp_path):
    api, root, work, saved = project(tmp_path, empty=True)
    answer = post(api, PATH, {})
    assert answer.status == 200, answer.payload
    view = answer.payload["accept"]
    assert view["base"]["source"] == "head" and "overlay_base" in view["warnings"]
    assert all(row["state"] != "deleted" for row in view["files"])
    assert next(row for row in view["files"] if row["path"] == "old.txt")["state"] == "modified"


@needs_git
@pytest.mark.parametrize("failure", ["author", "branch", "namespace", "invalid"])
def test_git_admission_refuses_without_writes(tmp_path, failure):
    api, root, work, saved = project(tmp_path)
    body = {}
    if failure == "author":
        git("config", "user.email", "", cwd=root)
    elif failure == "branch":
        git("branch", f"conduct/{RUN}", cwd=root)
    elif failure == "namespace":
        git("branch", "conduct", cwd=root)
    else:
        body["branch"] = "conduct/../bad"
    before = snapshot(root / ".git")
    answer = post(api, PATH, body)
    assert answer.status == 409
    assert answer.payload["error"]["detail"]["reason"] == {
        "author": "git_identity_missing", "branch": "branch_exists",
        "namespace": "branch_namespace_blocked", "invalid": "branch_name_invalid"}[failure]
    assert snapshot(root / ".git") == before


def test_view_and_body_admission_never_ask_git(tmp_path):
    api = prepared(tmp_path)
    assert post(api, PATH, {}).payload["error"]["code"] == "project_not_active"
    api._identity = replace(api._identity, mode="active")
    for body in ({"unknown": 1}, {"documents": ["one", "one"]}, {"title": "\n"}):
        assert post(api, PATH, body).payload["error"]["code"] == "contract_invalid"


def test_patch_may_truncate_display_but_not_acceptance_terms():
    files = [{"path": "large.txt", "state": "added"}]
    shown = patch(files, {}, {"large.txt": b"x\n" * PATCH_LIMIT})
    assert shown["truncated"] and len(shown["text"].encode()) <= PATCH_LIMIT
    ending = patch(files, {"large.txt": b"old"}, {"large.txt": b"new"})
    assert "-old\n\\ No newline at end of file\n+new\n" in ending["text"]


@needs_git
def test_starter_human_brief_comes_from_immutable_journal_and_never_walks_work(tmp_path, monkeypatch):
    root = repository(tmp_path)
    commit(root, {"docs/idea.md": b"prior idea\n"})
    git("config", "user.name", "Author", cwd=root)
    git("config", "user.email", "author@example.invalid", cwd=root)
    api = prepared(root, files=False, finish=False, workflow=("desk-starter-docs", 1))
    api._templates.save(GraphTemplate("desk-starter-docs", 1, "Starter",
                                      (TemplateNode("finish", "gate", "Accept", gate_id="release"),)))
    # Starter paths are fixed .md names even when the immutable human brief is text/plain.
    document = ArtifactDocument("idea-one", "artifact-brief", RUN, NOW, "text/plain", "# Saved idea\n")
    api._store.append(document)
    api._store.append(a_decision(config_digest=api._store.read(RUN).envelope.config_digest))
    api._store.append(RunTerminal("ended", RUN, "graph-one", "complete", ("finish",), (), NOW))
    api._identity = replace(api._identity, mode="active")
    api._project_git = real_reader(tmp_path)
    from conductor.command.adapters import work_seed
    monkeypatch.setattr(work_seed, "capture_work_tree", lambda *a, **k: pytest.fail("documents walked work"))
    before = snapshot(root / ".git")
    answer = post(api, PATH, {"documents": ["artifact-brief"]})
    assert answer.status == 200, answer.payload
    view = answer.payload["accept"]
    assert view["kind"] == "documents" and view["basis"]["accept_manifest_digest"] is None
    assert view["documents"] == [{"artifact_ref": "artifact-brief", "artifact_id": "idea-one",
                                  "path": "docs/idea.md", "state": "modified"}]
    assert "+# Saved idea" in view["patch"]["text"]
    assert snapshot(root / ".git") == before and not (root / "work").exists()


def test_reason_vocabulary_is_closed_and_has_both_languages():
    from pathlib import Path
    from conductor.command.api_refusals import ACCEPT_REASONS, ApiRefusal
    copy = (Path(__file__).parents[1] / "src/conductor/panel/studio-notice-copy.js").read_text(encoding="utf-8")
    for reason in ACCEPT_REASONS:
        refusal = ApiRefusal.accept_refused(reason)
        assert refusal.status == 409 and refusal.as_dict()["error"]["detail"] == {"reason": reason}
        assert f'"accept.reason.{reason}": [' in copy
    with pytest.raises(ValueError):
        ApiRefusal.accept_refused("untrusted text")


@pytest.mark.parametrize("change", [None, "digest", "producer", "after_approval", "late_proof"])
def test_selected_review_document_must_bind_its_latest_bytes_and_producing_node(change):
    from tests.test_acceptance_basis import journal
    plan, values = journal("review")
    plan = replace(plan, nodes=(replace(plan.nodes[0], arguments={"result_artifact_ref": "artifact-plan"}),
                               plan.nodes[1]))
    document = ArtifactDocument("doc-one", "artifact-plan", RUN, NOW, "text/markdown",
                                "# Verified bytes", "action-001")
    proof = replace(values[1], digest=document.digest())
    values = [values[0], document, proof, values[2], values[3]]
    if change == "digest":
        values[1] = replace(document, content="# Other bytes")
    elif change == "producer":
        values[0] = replace(values[0], node_id="foreign-node")
    elif change == "after_approval":
        values.pop(1)
        values.insert(3, document)
    elif change == "late_proof":
        values[2], values[3] = values[3], values[2]
    context = SimpleNamespace(definition=plan, workflow=None,
        recovered=SimpleNamespace(records=[SimpleNamespace(value=row) for row in values]),
        basis=AcceptanceBasis("documents", decision_id="decision-001"), task=None)
    if change is None:
        assert documents(context, None) == [("docs/plan.md", document)]
    else:
        with pytest.raises(SnapshotRefused):
            documents(context, None)
