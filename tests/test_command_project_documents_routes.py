"""The documents of a project as the two GET routes answer them (spec 6.2.2, 9.1.6, 9.5).

`project_documents` is tested on its own; what is tested here is what the handlers add to it: the
wire shape, the refusals in the words of the vocabulary, a server that has no git reader, and the
rule of `view` that no git is asked. As for the materials, the spy reader stands for "no git was
run". The door tests of the two routes (paths, verbs, the id grammar) are in
`test_command_project_doors.py`.
"""
from __future__ import annotations

import pytest

from conductor.command import project_routes
from conductor.command.api_refusals import ApiRefusal
from conductor.command.project_documents import EMPTY, doc_id_of
from tests.git_repo_helpers import Script, blob_oid, commit, needs_git, said
from tests.test_command_materials_routes import FILES, NoGit, Project

DOCS = ["CLAUDE.md", "README.md", "docs/spec.md", "notes/idea.txt"]


@needs_git
def test_the_documents_answer_is_the_base_the_documents_and_the_flag_and_nothing_else(tmp_path):
    project = Project(tmp_path)
    status, payload = project_routes.read_documents(project.api)
    assert status == 200 and set(payload) == {"base", "documents", "truncated"}
    assert payload["base"] == {"commit": project.head, "ref": payload["base"]["ref"]}
    assert [row["path"] for row in payload["documents"]] == DOCS
    assert set(payload["documents"][0]) == {"doc_id", "path", "length", "git_oid"}
    assert payload["truncated"] is False
    assert all(len(FILES[row["path"]].encode()) == row["length"] for row in payload["documents"])


@needs_git
def test_the_documents_of_a_project_with_no_commit_are_the_empty_answer(tmp_path):
    project = Project(tmp_path, files={"notes.txt": "x"})
    project.root.joinpath(".git", "refs", "heads").joinpath("master").unlink(missing_ok=True)
    project.root.joinpath(".git", "refs", "heads", "main").unlink(missing_ok=True)
    assert project_routes.read_documents(project.api) == (200, EMPTY.as_dict())


@needs_git
def test_a_server_with_no_git_reader_offers_no_documents_and_says_so_like_an_empty_project(
        tmp_path):
    project = Project(tmp_path, reader=None)
    assert project_routes.read_documents(project.api) == (200, EMPTY.as_dict())


@needs_git
def test_one_document_is_answered_with_its_id_path_blob_and_text(tmp_path):
    project = Project(tmp_path)
    status, payload = project_routes.read_document(project.api, doc_id_of("docs/spec.md"))
    assert status == 200
    assert payload == {"doc_id": doc_id_of("docs/spec.md"), "path": "docs/spec.md",
                       "git_oid": blob_oid(project.root, "docs/spec.md"),
                       "content": "The spec.\n"}


@needs_git
def test_an_id_head_does_not_list_is_materials_refused_doc_unknown(tmp_path):
    project = Project(tmp_path)
    with pytest.raises(ApiRefusal) as caught:
        project_routes.read_document(project.api, doc_id_of("docs/never-was.md"))
    assert (caught.value.status, caught.value.code) == (409, "materials_refused")
    assert dict(caught.value.detail) == {"reason": "doc_unknown"}


@needs_git
def test_a_document_that_is_not_utf8_text_is_materials_refused_document_not_text(tmp_path):
    project = Project(tmp_path, files={"docs/binary.md": b"\xff\xfe\x00 not text"})
    with pytest.raises(ApiRefusal) as caught:
        project_routes.read_document(project.api, doc_id_of("docs/binary.md"))
    assert dict(caught.value.detail) == {"reason": "document_not_text"}


@needs_git
def test_a_server_with_no_git_reader_holds_no_document_to_read(tmp_path):
    project = Project(tmp_path, reader=None)
    with pytest.raises(ApiRefusal) as caught:
        project_routes.read_document(project.api, doc_id_of("README.md"))
    assert dict(caught.value.detail) == {"reason": "doc_unknown"}


@needs_git
@pytest.mark.parametrize("read", [
    lambda api: project_routes.read_documents(api),
    lambda api: project_routes.read_document(api, doc_id_of("README.md"))], ids=["list", "one"])
def test_git_failing_is_store_error_and_not_an_empty_project(tmp_path, read):
    project = Project(tmp_path, reader=Script(said(b"fatal: broken\n", code=128)))
    with pytest.raises(ApiRefusal) as caught:
        read(project.api)
    assert (caught.value.status, caught.value.code) == (500, "store_error")


@needs_git
@pytest.mark.parametrize("read", [
    lambda api: project_routes.read_documents(api),
    lambda api: project_routes.read_document(api, doc_id_of("README.md"))], ids=["list", "one"])
def test_in_view_both_routes_are_project_not_active_and_git_is_never_asked(tmp_path, read):
    project = Project(tmp_path, mode="view", reader=NoGit())
    with pytest.raises(ApiRefusal) as caught:
        read(project.api)
    assert (caught.value.status, caught.value.code) == (409, "project_not_active")
    assert project.reader.asked == 0


@needs_git
def test_the_list_follows_the_repository_when_a_document_is_committed_later(tmp_path):
    project = Project(tmp_path)
    commit(project.root, {"docs/later.md": "Later.\n"})
    payload = project_routes.read_documents(project.api)[1]
    assert "docs/later.md" in [row["path"] for row in payload["documents"]]
    assert payload["base"]["commit"] != project.head
