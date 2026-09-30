"""The materials of a run, composed against the seed and HEAD and published (spec 6.2.3).

The pure composition is lane D2's (`test_command_materials_compose.py`); what is tested here is
what the server adds to it. It reads the seed record of the run's task and the documents of a real
repository, judges a link against what the seed really copied and a copy against HEAD, refuses in
the words of `materials_refused`, and publishes the result as `artifact-materials` through the
door the artifacts route uses, so a repeat finds the document standing. Nothing here goes through
the router: the handler `http_writes.write_materials` is the function the route calls, and the
door tests of the route are in `test_command_project_routes.py`.

A spy reader that fails when it is asked anything stands for "no git was run", which is the
claim of every list that needs none and of every request in `view`.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from conductor.command import http_writes
from conductor.command.adapters import AdapterRegistry
from conductor.command.api_refusals import ApiRefusal
from conductor.command.artifacts import latest_artifacts
from conductor.command.contract_values import ContractError
from conductor.command.contracts import RunEnvelope
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.materials import MAX_MATERIALS
from conductor.command.project_claim import ProjectIdentity
from conductor.command.project_documents import doc_id_of
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.seed_record import CorruptSeed
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from conductor.ownership import data_root
from tests.git_repo_helpers import (
    Script, blob_oid, commit, git, needs_git, real_reader, repository, said)
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, ids
from tests.test_seed_record import a_git_seed, an_empty_seed

TASK = "task-materials-1"
RUN = f"{TASK}-r1"
PROJECT_ID = "ab" * 16
FILES = {"README.md": "# Project\n", "docs/spec.md": "The spec.\n", "CLAUDE.md": "Rules.\n",
         "src/main.py": "print()\n", "notes/idea.txt": "An idea.\n"}


class Asked(AssertionError):
    """The spy reader was asked something."""


class NoGit:
    """A reader that fails on any use, and counts the uses it was refused."""

    def __init__(self):
        self.asked = 0

    def __call__(self, args, separate_stderr=False):
        self.asked += 1
        raise Asked(f"git was asked: {args[:4]}")


class Project:
    """A real repository, a task, a run bound to it, and the boundary over them."""

    def __init__(self, tmp_path, *, name="project", mode="active", reader="real", bound=True,
                 files=None):
        self.root = repository(tmp_path, name)
        self.head = commit(self.root, FILES if files is None else files)
        self.tree = git("rev-parse", "HEAD^{tree}", cwd=self.root).stdout.decode().strip()
        self.store, self.tasks = RunStore(self.root), TaskStore(self.root)
        self.tasks.create_task(TaskRecord(task_id=TASK, title="Materials", work_scope=TASK,
                                          created_at=NOW))
        config = {"cycle": {"id": RUN}, "instances": [{"id": "doer", "adapter": "claude-code"}],
                  "workflow": {"id": "desk-standard", "revision": 1},
                  "automation_contract": "bounded-run-v1"}
        if bound:
            config["task"] = {"id": TASK, "work_scope": TASK}
        self.store.create_run(RunEnvelope(RUN, RUN, NOW, snapshot_digest(config),
                                          mode="policy"), config)
        self.events = []
        self.reader = real_reader(tmp_path) if reader == "real" else reader
        self.api = CommandApi(
            self.store, AdapterRegistry([FakeAdapter()]), session=CommandSession(PORT, TOKEN),
            budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
            publish_run=self.events.append, project_git=self.reader,
            identity=ProjectIdentity(PROJECT_ID, None, False, mode, None, None))

    def seed(self, **changes):
        """The record the seed step would have written for this task and its base tree."""
        base = {"task_id": TASK, "work_scope": TASK, "base_commit": self.head,
                "base_tree": self.tree, "skipped": [], "agent_instructions_skipped": []}
        self.write_seed(a_git_seed(**{**base, **changes}))

    def write_seed(self, record):
        path = data_root(self.root) / "seeds" / TASK / "work-001.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record), encoding="utf-8")

    def link(self, path, oid=None):
        return {"kind": "project_doc", "doc_id": doc_id_of(path),
                "git_oid": oid or blob_oid(self.root, path), "mode": "link"}

    def copy(self, path, content="Edited by the owner.\n"):
        return {"kind": "project_doc", "doc_id": doc_id_of(path),
                "git_oid": blob_oid(self.root, path), "mode": "copy", "content": content}

    def publish(self, items, lang="en"):
        return http_writes.write_materials(self.api, RUN, {"lang": lang, "items": items})

    def artifacts(self):
        return [row.value for row in self.store.read(RUN).records if row.kind == "artifact"]

    def journal(self):
        return (self.store.run_path(RUN) / "records.jsonl").read_bytes()


def note(title="A note", content="Some text."):
    return {"kind": "note", "title": title, "content": content}


def refused(project, items, **more):
    """The refusal a publication ends in, and the proof that it wrote nothing."""
    before = project.journal()
    with pytest.raises(ApiRefusal) as caught:
        project.publish(items, **more)
    assert project.journal() == before and project.events == []
    return caught.value


def reason(refusal):
    assert (refusal.status, refusal.code) == (409, "materials_refused")
    return refusal.detail["reason"]


# --- a list that needs no git -----------------------------------------------------------------


@needs_git
def test_text_materials_are_published_as_artifact_materials_and_run_no_git(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    status, document = project.publish([
        note("Plan", "Do it."), {"kind": "scheme", "title": "Flow", "content": "flowchart TD"}])
    assert status == 201
    assert (document["artifact_ref"], document["media_type"]) == (
        "artifact-materials", "text/markdown")
    assert "## 1. Plan · note" in document["content"] and "```mermaid" in document["content"]
    spelled = "\0".join([RUN, "artifact-materials", "text/markdown", document["content"]])
    assert document["artifact_id"] == "doc-" + hashlib.sha256(spelled.encode()).hexdigest()[:32]
    assert project.reader.asked == 0 and project.events == [RUN]


@needs_git
def test_a_list_of_no_materials_still_publishes_the_document_that_says_so(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    status, document = project.publish([])
    assert status == 201 and "No materials" in document["content"]


@needs_git
def test_the_same_items_again_return_the_standing_document_and_append_nothing(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    first = project.publish([note()])
    before = project.journal()
    again = project.publish([note()])
    assert (first[0], again[0]) == (201, 200) and again[1] == first[1]
    assert project.journal() == before and project.events == [RUN], "no second frame either"


@needs_git
def test_changed_items_are_a_new_version_and_the_last_is_the_one_the_run_reads(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    project.publish([note(content="first")])
    status, second = project.publish([note(content="second")])
    assert status == 201
    latest = latest_artifacts(project.artifacts(), ["artifact-materials"])[0]
    assert latest.artifact_id == second["artifact_id"] and "second" in latest.content
    assert len(project.artifacts()) == 2


@needs_git
def test_a_list_past_twelve_materials_is_refused_before_any_git_is_asked(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    project.seed()  # so that a link WOULD be judged against the base tree, with git
    items = [note(str(number)) for number in range(MAX_MATERIALS)] + [project.link("README.md")]
    seen = refused(project, items)
    assert reason(seen) == "too_many_materials" and project.reader.asked == 0


@needs_git
def test_materials_over_the_document_limit_are_refused_and_publish_nothing(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    assert reason(refused(project, [note(content="x" * 49_200)])) == "materials_too_large"


@pytest.mark.parametrize("body", [
    {"items": []}, {"lang": "en"}, {"lang": "en", "items": [], "path": "docs/a.md"}, [], None])
@needs_git
def test_a_body_of_other_keys_is_contract_invalid_and_writes_nothing(tmp_path, body):
    project = Project(tmp_path, reader=NoGit())
    before = project.journal()
    with pytest.raises(ApiRefusal) as caught:
        http_writes.write_materials(project.api, RUN, body)
    assert caught.value.code == "contract_invalid" and project.journal() == before


@pytest.mark.parametrize("items,lang", [
    ([{"kind": "note", "title": "A", "content": "b", "path": "docs/a.md"}], "en"),
    ([{"kind": "unknown"}], "en"), ("not a list", "en"), ([note()], "fr")])
@needs_git
def test_an_item_or_a_language_off_the_closed_shape_is_a_contract_error(tmp_path, items, lang):
    project = Project(tmp_path, reader=NoGit())
    before = project.journal()
    with pytest.raises(ContractError):
        project.publish(items, lang=lang)
    assert project.journal() == before and project.reader.asked == 0


# --- a link, judged against what the seed copied ----------------------------------------------


@needs_git
def test_a_link_to_a_document_the_seed_copied_names_its_path_and_blob_and_not_its_text(tmp_path):
    project = Project(tmp_path)
    project.seed()
    status, document = project.publish([project.link("docs/spec.md")])
    oid = blob_oid(project.root, "docs/spec.md")
    assert status == 201
    assert f"`docs/spec.md` (git blob `{oid}`), text not copied" in document["content"]
    assert "The spec." not in document["content"]


@needs_git
def test_materials_link_is_refused_when_the_seed_base_blob_differs(tmp_path):
    project = Project(tmp_path)
    project.seed()
    stale = project.link("docs/spec.md", oid="f" * 40)
    assert reason(refused(project, [stale])) == "materials_base_moved"


@needs_git
def test_materials_link_is_refused_for_a_path_the_seed_skipped(tmp_path):
    project = Project(tmp_path)
    project.seed(skipped=[{"path": "docs/spec.md", "reason": "unportable_name"}])
    assert reason(refused(project, [project.link("docs/spec.md")])) == "doc_not_seeded"


@needs_git
def test_a_link_to_an_instruction_file_the_seed_left_out_is_doc_not_seeded(tmp_path):
    project = Project(tmp_path)
    project.seed(agent_instructions_skipped=["CLAUDE.md"])
    assert reason(refused(project, [project.link("CLAUDE.md")])) == "doc_not_seeded"


@needs_git
def test_a_skipped_path_does_not_spoil_a_link_to_a_document_the_seed_did_copy(tmp_path):
    project = Project(tmp_path)
    project.seed(agent_instructions_skipped=["CLAUDE.md"])
    assert project.publish([project.link("README.md")])[0] == 201


@needs_git
def test_a_link_to_a_document_the_base_tree_never_held_is_doc_unknown(tmp_path):
    project = Project(tmp_path)
    project.seed()
    commit(project.root, {"docs/later.md": "Added after the seed.\n"})
    assert reason(refused(project, [project.link("docs/later.md")])) == "doc_unknown"


@needs_git
def test_a_link_with_no_seed_record_is_seed_missing_and_no_git_is_asked(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    assert reason(refused(project, [project.link("README.md")])) == "seed_missing"
    assert project.reader.asked == 0


@needs_git
def test_a_link_to_an_empty_seed_or_from_a_run_bound_to_no_task_is_seed_missing(tmp_path):
    empty = Project(tmp_path, name="empty", reader=NoGit())
    empty.write_seed(an_empty_seed(task_id=TASK, work_scope=TASK))
    assert reason(refused(empty, [empty.link("README.md")])) == "seed_missing"
    unbound = Project(tmp_path, name="unbound", reader=NoGit(), bound=False)
    unbound.seed()
    assert reason(refused(unbound, [unbound.link("README.md")])) == "seed_missing"
    assert empty.reader.asked == unbound.reader.asked == 0


@needs_git
def test_a_corrupt_seed_record_is_a_store_fault_and_never_a_missing_seed(tmp_path):
    project = Project(tmp_path)
    project.write_seed({"schema_version": 1})
    with pytest.raises(CorruptSeed):
        project.publish([project.link("README.md")])
    assert project.artifacts() == []


# --- a copy, judged against HEAD alone --------------------------------------------------------


@needs_git
def test_a_copy_needs_no_seed_and_is_headed_with_the_path_and_blob_it_was_read_from(tmp_path):
    project = Project(tmp_path)
    status, document = project.publish([project.copy("docs/spec.md", "The owner's version.\n")])
    oid = blob_oid(project.root, "docs/spec.md")
    assert status == 201
    assert f"## 1. docs/spec.md@{oid} · project_doc" in document["content"]
    assert "The owner's version." in document["content"]


@needs_git
def test_a_copy_of_a_file_the_seed_left_out_is_still_the_owners_text(tmp_path):
    project = Project(tmp_path)
    project.seed(agent_instructions_skipped=["CLAUDE.md"])
    assert project.publish([project.copy("CLAUDE.md", "Rules, as edited.\n")])[0] == 201


@needs_git
def test_a_copy_of_a_document_head_does_not_list_is_doc_unknown(tmp_path):
    project = Project(tmp_path)
    gone = {**project.copy("README.md"), "doc_id": doc_id_of("docs/never-was.md")}
    assert reason(refused(project, [gone])) == "doc_unknown"


@needs_git
def test_a_copy_whose_text_holds_a_nul_is_document_not_text(tmp_path):
    project = Project(tmp_path)
    assert reason(refused(project, [project.copy("README.md", "bad\x00text")])
                  ) == "document_not_text"


@needs_git
def test_a_copy_and_a_link_in_one_list_are_each_judged_by_their_own_rule(tmp_path):
    project = Project(tmp_path)
    project.seed(agent_instructions_skipped=["CLAUDE.md"])
    status, document = project.publish([
        project.copy("CLAUDE.md", "Copied.\n"), project.link("README.md"), note("Idea", "Go.")])
    assert status == 201
    assert document["content"].count("· project_doc") == 2 and "· note" in document["content"]


@needs_git
def test_git_failing_under_a_copy_is_a_store_error_and_publishes_nothing(tmp_path):
    script = Script(said(b"fatal: broken\n", code=128))
    project = Project(tmp_path, reader=script)
    seen = refused(project, [project.copy("README.md")])
    assert (seen.status, seen.code) == (500, "store_error")


@needs_git
def test_a_project_with_no_git_reader_cannot_resolve_a_copy_and_says_doc_unknown(tmp_path):
    project = Project(tmp_path, reader=None)
    assert reason(refused(project, [project.copy("README.md")])) == "doc_unknown"


@needs_git
def test_a_project_with_no_git_reader_cannot_judge_a_link_against_a_seed_that_has_a_base(
        tmp_path):
    project = Project(tmp_path, reader=None)
    project.seed()
    seen = refused(project, [project.link("README.md")])
    assert (seen.status, seen.code) == (500, "store_error")


# --- view mode: no git is asked (spec 9.1.6) --------------------------------------------------


@needs_git
def test_in_view_text_materials_are_published_and_git_is_never_asked(tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    assert project.publish([note(), note("Second", "More.")])[0] == 201
    assert project.reader.asked == 0


@needs_git
def test_in_view_a_copy_of_a_project_document_is_project_not_active_and_git_is_never_asked(
        tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    seen = refused(project, [project.copy("README.md")])
    assert (seen.status, seen.code) == (409, "project_not_active") and project.reader.asked == 0


@needs_git
def test_in_view_a_link_to_a_task_with_no_base_is_seed_missing_and_git_is_never_asked(tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    assert reason(refused(project, [project.link("README.md")])) == "seed_missing"
    assert project.reader.asked == 0


@needs_git
def test_in_view_a_link_to_a_task_that_has_a_base_is_project_not_active_and_git_is_never_asked(
        tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    project.seed()
    seen = refused(project, [project.link("README.md")])
    assert (seen.status, seen.code) == (409, "project_not_active") and project.reader.asked == 0
