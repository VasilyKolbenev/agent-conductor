"""The materials and documents routes as a desk reaches them: a request into `CommandApi.handle`
(spec 6.2.2, 6.2.3, 6.2.5, 9.1.6, 9.5).

`test_command_materials_routes.py` and `test_command_project_documents_routes.py` call the
handlers. What is held here is what only the router adds: the three rows and the two dispatch
lines, the closed id grammar of a document, the verbs, the project claim that stands in front of
the handler, the wire form of the refusals, and the ended-run rules that the materials route has
because it ends in the artifacts door's own function. The spec's named cases of 6.2.5 that are the
server's are each walked once more on the wire.

A spy reader that fails when asked stands for "no git was run", as in the handler files.
"""
from __future__ import annotations

import pytest

from conductor.command.project_claim import HEADER
from conductor.command.project_documents import doc_id_of
from tests.git_repo_helpers import blob_oid, needs_git
from tests.test_command_http_api import (
    NOW, RUN_ID, api, decision_body, encode, get_headers, post, post_headers)
from tests.test_command_materials_routes import (
    FILES, PROJECT_ID, RUN, NoGit, Project, note)
from tests.test_command_run_terminal_doors import a_gated_plan, journal_bytes
from tests.test_command_schema_doubles import DeepDispatchAdapter

DOCS = "/command/project/documents"
MATERIALS = f"/command/runs/{RUN}/materials"
OTHER_ID = "cd" * 16
README = doc_id_of("README.md")


def request(project, method, path, body=None, *claims):
    """One request into the boundary the way a page makes it, with any number of claims."""
    if method == "POST":
        headers, raw = post_headers(body), encode(body)
    else:
        headers, raw = get_headers(), b""
    return project.api.handle(
        method, path, (*headers, *((HEADER, claim) for claim in claims)), raw)


def code_of(answer):
    return answer.status, answer.payload["error"]["code"]


def reason_of(answer):
    return answer.payload["error"]["detail"]["reason"]


def text_body(*items, lang="en"):
    return {"lang": lang, "items": list(items)}


# --- the rows: what each path answers ---------------------------------------------------------


@needs_git
def test_the_documents_of_head_are_listed_through_the_router(tmp_path):
    project = Project(tmp_path)
    answer = request(project, "GET", DOCS)
    assert answer.status == 200
    assert [row["path"] for row in answer.payload["documents"]] == sorted(
        path for path in FILES if path.endswith((".md", ".txt")))
    assert answer.payload["base"]["commit"] == project.head


@needs_git
def test_one_document_is_read_through_the_router_by_the_id_the_list_gave(tmp_path):
    project = Project(tmp_path)
    listed = request(project, "GET", DOCS).payload["documents"]
    spec = next(row for row in listed if row["path"] == "docs/spec.md")
    answer = request(project, "GET", f"{DOCS}/{spec['doc_id']}")
    assert answer.status == 200
    assert answer.payload == {"doc_id": spec["doc_id"], "path": "docs/spec.md",
                              "git_oid": blob_oid(project.root, "docs/spec.md"),
                              "content": "The spec.\n"}


@needs_git
def test_materials_are_published_through_the_router_as_a_document_of_the_run(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    answer = request(project, "POST", MATERIALS, text_body(note("Plan", "Do it.")))
    assert answer.status == 201
    assert (answer.payload["run_id"], answer.payload["artifact_ref"]) == (RUN, "artifact-materials")
    assert [row.artifact_id for row in project.artifacts()] == [answer.payload["artifact_id"]]


@needs_git
def test_a_get_of_the_materials_path_and_a_post_of_a_documents_path_are_method_not_allowed(
        tmp_path):
    project = Project(tmp_path, reader=NoGit())
    cases = [request(project, "GET", MATERIALS), request(project, "POST", DOCS, {}),
             request(project, "POST", f"{DOCS}/{README}", {})]
    assert [code_of(answer) for answer in cases] == [(405, "method_not_allowed")] * 3
    assert project.reader.asked == 0 and project.artifacts() == []


@needs_git
@pytest.mark.parametrize("path", [MATERIALS, DOCS, f"{DOCS}/{README}"])
def test_a_verb_the_table_never_names_is_method_not_allowed_on_a_path_it_does(tmp_path, path):
    project = Project(tmp_path, reader=NoGit())
    assert code_of(request(project, "DELETE", path)) == (405, "method_not_allowed")
    assert project.reader.asked == 0


# --- the id grammar of a document: a path no row names is not a route -------------------------


@needs_git
@pytest.mark.parametrize("tail", [
    "/", f"/{README}/", f"/{README}/content", f"/{README}/..", "/" + README.upper(),
    "/d-" + "a" * 31, "/d-" + "a" * 33, "/" + "a" * 34, "/d-" + "g" * 32, "/d_" + "a" * 32,
    "/d-" + "a" * 32 + ".md", "/../project/documents"], ids=str)
def test_a_documents_path_with_any_other_tail_than_d_and_32_lowercase_hex_is_route_not_found(
        tmp_path, tail):
    project = Project(tmp_path, reader=NoGit())
    for method in ("GET", "POST"):
        body = {} if method == "POST" else None
        assert code_of(request(project, method, f"{DOCS}{tail}", body)) == (
            404, "route_not_found"), (method, tail)
    assert project.reader.asked == 0


@needs_git
@pytest.mark.parametrize("path", [
    f"{MATERIALS}/", f"{MATERIALS}/x", f"/command/runs/{RUN}/material",
    f"/command/runs/{RUN}/materials/../artifacts"])
def test_a_materials_path_with_another_tail_is_route_not_found(tmp_path, path):
    project = Project(tmp_path, reader=NoGit())
    assert code_of(request(project, "POST", path, text_body())) == (404, "route_not_found")


# --- the project claim stands in front of the handler -----------------------------------------


@needs_git
def test_a_wrong_claim_on_a_documents_read_is_project_mismatch_and_git_is_never_asked(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    for path in (DOCS, f"{DOCS}/{README}"):
        assert code_of(request(project, "GET", path, None, OTHER_ID)) == (409, "project_mismatch")
    assert project.reader.asked == 0


@needs_git
def test_the_right_claim_reaches_the_documents_and_the_materials_handlers(tmp_path):
    project = Project(tmp_path)
    assert request(project, "GET", DOCS, None, PROJECT_ID).status == 200
    assert request(project, "POST", MATERIALS, text_body(note()), PROJECT_ID).status == 201


@needs_git
def test_a_wrong_claim_on_a_materials_post_is_project_mismatch_and_writes_nothing(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    before = project.journal()
    answer = request(project, "POST", MATERIALS, text_body(note()), OTHER_ID)
    assert code_of(answer) == (409, "project_mismatch")
    assert project.journal() == before and project.events == []


# --- the cases of 6.2.5 that are the server's, on the wire ------------------------------------


@needs_git
def test_materials_link_is_refused_when_the_seed_base_blob_differs_on_the_wire(tmp_path):
    project = Project(tmp_path)
    project.seed()
    before = project.journal()
    answer = request(project, "POST", MATERIALS, text_body(project.link("docs/spec.md", "f" * 40)))
    assert code_of(answer) == (409, "materials_refused")
    assert answer.payload["error"]["detail"] == {"reason": "materials_base_moved"}
    assert project.journal() == before and project.events == []


@needs_git
def test_materials_link_is_refused_for_a_path_the_seed_skipped_on_the_wire(tmp_path):
    project = Project(tmp_path)
    project.seed(skipped=[{"path": "docs/spec.md", "reason": "unportable_name"}])
    before = project.journal()
    answer = request(project, "POST", MATERIALS, text_body(project.link("docs/spec.md")))
    assert code_of(answer) == (409, "materials_refused")
    assert answer.payload["error"]["detail"] == {"reason": "doc_not_seeded"}
    assert project.journal() == before and project.events == []


@needs_git
def test_materials_retry_with_the_same_items_returns_the_standing_document_on_the_wire(tmp_path):
    project = Project(tmp_path)
    project.seed()
    body = text_body(project.link("docs/spec.md"), note("Idea", "Go."))
    first = request(project, "POST", MATERIALS, body)
    before = project.journal()
    again = request(project, "POST", MATERIALS, body)
    assert (first.status, again.status) == (201, 200) and again.payload == first.payload
    assert project.journal() == before and project.events == [RUN], "no second frame either"


@needs_git
def test_a_changed_list_is_a_new_document_and_a_new_frame(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    first = request(project, "POST", MATERIALS, text_body(note(content="one")))
    second = request(project, "POST", MATERIALS, text_body(note(content="two")))
    assert (first.status, second.status) == (201, 201)
    assert first.payload["artifact_id"] != second.payload["artifact_id"]
    assert project.events == [RUN, RUN]


@needs_git
@pytest.mark.parametrize("body", [
    {"items": []}, {"lang": "en"}, {"lang": "en", "items": [], "path": "x.md"},
    {"lang": "fr", "items": []}, {"lang": "en", "items": "none"},
    {"lang": "en", "items": [{"kind": "unknown"}]}])
def test_a_body_off_the_closed_shape_is_contract_invalid_on_the_wire_and_writes_nothing(
        tmp_path, body):
    project = Project(tmp_path, reader=NoGit())
    before = project.journal()
    answer = request(project, "POST", MATERIALS, body)
    assert code_of(answer) == (422, "contract_invalid")
    assert project.journal() == before and project.events == [] and project.reader.asked == 0


@needs_git
def test_a_read_of_the_documents_writes_nothing_and_publishes_nothing(tmp_path):
    project = Project(tmp_path)
    before = project.journal()
    request(project, "GET", DOCS)
    request(project, "GET", f"{DOCS}/{README}")
    assert project.journal() == before and project.events == []


@needs_git
def test_an_id_head_does_not_list_is_materials_refused_doc_unknown_on_the_wire(tmp_path):
    project = Project(tmp_path)
    answer = request(project, "GET", f"{DOCS}/{doc_id_of('docs/never-was.md')}")
    assert code_of(answer) == (409, "materials_refused") and reason_of(answer) == "doc_unknown"


# --- view mode: no git is asked (spec 9.1.6) --------------------------------------------------


@needs_git
@pytest.mark.parametrize("path", [DOCS, f"{DOCS}/{README}"])
def test_in_view_both_documents_reads_are_project_not_active_on_the_wire_and_no_git_is_asked(
        tmp_path, path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    assert code_of(request(project, "GET", path)) == (409, "project_not_active")
    assert project.reader.asked == 0


@needs_git
def test_in_view_a_materials_post_of_text_is_published_and_a_copy_of_a_project_document_is_not(
        tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    assert request(project, "POST", MATERIALS, text_body(note())).status == 201
    before = project.journal()
    copied = request(project, "POST", MATERIALS, text_body(project.copy("README.md")))
    assert code_of(copied) == (409, "project_not_active")
    assert project.journal() == before and project.reader.asked == 0


@needs_git
def test_in_view_a_link_is_seed_missing_with_no_base_and_project_not_active_with_one(tmp_path):
    bare = Project(tmp_path, name="bare", mode="view", reader=NoGit())
    based = Project(tmp_path, name="based", mode="view", reader=NoGit())
    based.seed()
    missing = request(bare, "POST", MATERIALS, text_body(bare.link("README.md")))
    waiting = request(based, "POST", MATERIALS, text_body(based.link("README.md")))
    assert (code_of(missing), reason_of(missing)) == ((409, "materials_refused"), "seed_missing")
    assert code_of(waiting) == (409, "project_not_active")
    assert bare.reader.asked == based.reader.asked == 0


# --- the run the materials are for: the artifacts door's own rules ----------------------------


def ended_run_with_materials(tmp_path, ticks):
    """A run that published its materials while open and then ended at its one gate.

    Every read of the clock is written to `ticks`: the artifacts door reads no instant for a
    request it refuses and none for an exact retry, and a materials route that appended by a road
    of its own would read one for both, which no status and no byte of the journal would show.
    """
    subject, store, events = api(
        tmp_path, adapters=[DeepDispatchAdapter()], clock=lambda: ticks.append(NOW) or NOW)
    store.append(a_gated_plan())
    body = text_body(note("Plan", "Do it."))
    published = post(subject, f"/command/runs/{RUN_ID}/materials", body)
    assert published.status == 201
    assert post(subject, f"/command/runs/{RUN_ID}/decisions", decision_body()).status == 201
    return subject, store, events, body, published


def test_materials_for_a_run_that_has_ended_are_refused_and_write_no_byte_and_read_no_instant(
        tmp_path):
    ticks = []
    subject, store, events, _, _ = ended_run_with_materials(tmp_path, ticks)
    before, frames, read = journal_bytes(store), list(events), len(ticks)
    answer = post(subject, f"/command/runs/{RUN_ID}/materials", text_body(note("Later", "New.")))
    assert code_of(answer) == (409, "run_terminal")
    assert journal_bytes(store) == before and events == frames and len(ticks) == read


def test_an_exact_retry_of_materials_after_the_run_ended_still_answers_200_and_reads_no_instant(
        tmp_path):
    ticks = []
    subject, store, events, body, published = ended_run_with_materials(tmp_path, ticks)
    before, frames, read = journal_bytes(store), list(events), len(ticks)
    again = post(subject, f"/command/runs/{RUN_ID}/materials", body)
    assert again.status == 200 and again.payload == published.payload
    assert journal_bytes(store) == before and events == frames and len(ticks) == read


def test_materials_for_a_run_the_store_does_not_hold_are_refused_as_an_artifact_for_it_is(
        tmp_path):
    subject, _, events = api(tmp_path)
    artifact = {"artifact_id": "doc-x", "artifact_ref": "artifact-materials",
                "media_type": "text/markdown", "content": "x"}
    asked = post(subject, "/command/runs/run-nobody/artifacts", artifact)
    answer = post(subject, "/command/runs/run-nobody/materials", text_body(note()))
    assert asked.status >= 400 and code_of(answer) == code_of(asked) and events == []
