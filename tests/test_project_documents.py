"""The tracked text documents of a project's HEAD, and of a seed's base tree (spec 6.2.2, 9.5).

Two kinds of witness, as for `project_git`: a scripted reader answers from a table and records
every call, so each branch of the parsing and each argument is judged without git; real
repositories in a temporary folder then confirm that the answers are the ones git gives, that
a symlink or a submodule is never offered, and that reading writes nothing into `.git`.
"""
from __future__ import annotations

import hashlib

import pytest

from conductor.command import project_documents as docs
from conductor.command.artifacts import ARTIFACT_CONTENT_LIMIT
from conductor.command.project_documents import (
    DocumentRefused, GitReadFailed, Head, doc_id_of, list_documents, read_document)
from tests.git_repo_helpers import (
    Script, blob_oid, commit, git, needs_git, real_reader, repository, said, snapshot)

COMMIT = "d" * 40
TREE = "e" * 40
BLOB = "1" * 40


@pytest.fixture
def root(tmp_path):
    """A folder with a `.git` entry, which is all a scripted reader needs to be asked."""
    folder = tmp_path / "project"
    (folder / ".git").mkdir(parents=True)
    return folder


def toplevel(folder):
    return str(folder).replace("\\", "/").encode() + b"\n"


def row(path, *, oid=BLOB, size=10, mode="100644", kind="blob"):
    """One record of `ls-tree -r -l -z`: the size is padded to seven places, `-` for a non-blob."""
    shown = "-" if kind != "blob" else str(size)
    return f"{mode} {kind} {oid} {shown:>7}\t{path}".encode("utf-8") + b"\0"


def listing_script(root, tree, *, ref=b"refs/heads/main\n", **flags):
    """The five answers of a listing: admission (two), HEAD (two), then the tree."""
    return Script(said(toplevel(root)), said(b""), said(COMMIT.encode() + b"\n"), said(ref),
                  said(tree, **flags))


def paths(listing):
    return [document.path for document in listing.documents]


# --- the id of a document ---------------------------------------------------------------------


def test_a_document_id_is_d_and_32_hex_of_the_sha256_of_its_path():
    assert doc_id_of("docs/spec.md") == "d-d7d183da3129291ef1210410b2898ac6"
    assert doc_id_of("README.md") == "d-" + hashlib.sha256(b"README.md").hexdigest()[:32]
    assert doc_id_of("docs/spéc.md") != doc_id_of("docs/spec.md")


# --- which files of a tree are documents ------------------------------------------------------


@pytest.mark.parametrize("path", [
    "a.md", "a.markdown", "a.txt", "a.rst", "a.adoc", "a.mmd", "docs/A.MD", "deep/er/notes.Txt"])
def test_a_regular_file_with_a_document_extension_is_offered(root, path):
    listing = list_documents(root, listing_script(root, row(path)))
    assert paths(listing) == [path]


@pytest.mark.parametrize("path", [
    "a.py", "a.md.bak", "README", "a.mdx", "notes.text", "docs/.md.png", "Makefile"])
def test_a_file_without_a_document_extension_is_not_offered(root, path):
    assert list_documents(root, listing_script(root, row(path))).documents == ()


def test_a_document_is_offered_up_to_49152_bytes_and_not_a_byte_beyond(root):
    assert ARTIFACT_CONTENT_LIMIT == 49_152
    tree = row("fits.md", size=49_152) + row("too-big.md", size=49_153)
    assert paths(list_documents(root, listing_script(root, tree))) == ["fits.md"]


def test_a_symlink_and_a_submodule_are_never_offered_and_an_executable_is(root):
    tree = (row("link.md", mode="120000") + row("sub.md", mode="160000", kind="commit")
            + row("run.md", mode="100755") + row("plain.md"))
    assert paths(list_documents(root, listing_script(root, tree))) == ["plain.md", "run.md"]


@pytest.mark.parametrize("path", [
    "work/plan.md", "instructions/a.md", ".claude-home/a.md", ".conduct-retired-1a2b/a.md",
    "conductor/a.md", "Work/a.md"])
def test_a_file_under_a_product_folder_is_not_offered(root, path):
    assert list_documents(root, listing_script(root, row(path))).documents == ()


def test_a_folder_that_is_only_named_like_a_product_folder_below_the_top_is_offered(root):
    tree = row("docs/work/plan.md") + row("workspace/a.md")
    assert paths(list_documents(root, listing_script(root, tree))) == [
        "docs/work/plan.md", "workspace/a.md"]


def test_a_path_of_two_lines_is_not_offered_because_no_heading_can_carry_it(root):
    assert list_documents(root, listing_script(root, row("a\nb.md"))).documents == ()


def test_a_path_that_is_not_utf8_is_skipped_and_the_rest_are_listed(root):
    broken = b"100644 blob " + BLOB.encode() + b"      10\t\xff.md\0"
    assert paths(list_documents(root, listing_script(root, broken + row("ok.md")))) == ["ok.md"]


def test_a_row_the_parser_does_not_know_is_a_failed_read_and_never_a_guess(root):
    with pytest.raises(GitReadFailed) as failed:
        list_documents(root, listing_script(root, b"this is not a tree row\0"))
    assert failed.value.code == "git_failed"


# --- the list: order, bound, what it says of itself -------------------------------------------


def test_the_documents_come_back_ordered_by_path_with_their_ids_lengths_and_oids(root):
    tree = row("z.md", oid="2" * 40, size=5) + row("docs/a.md", oid="3" * 40, size=7)
    listing = list_documents(root, listing_script(root, tree))
    assert [(d.doc_id, d.path, d.length, d.git_oid) for d in listing.documents] == [
        (doc_id_of("docs/a.md"), "docs/a.md", 7, "3" * 40),
        (doc_id_of("z.md"), "z.md", 5, "2" * 40)]
    assert listing.base == Head(COMMIT, "refs/heads/main") and listing.truncated is False


def test_the_list_holds_500_documents_and_says_truncated_only_beyond_them(root):
    def tree(count):
        return b"".join(row(f"d{number:04}.md") for number in range(count))
    exactly = list_documents(root, listing_script(root, tree(500)))
    beyond = list_documents(root, listing_script(root, tree(501)))
    assert (len(exactly.documents), exactly.truncated) == (500, False)
    assert (len(beyond.documents), beyond.truncated) == (500, True)
    assert paths(beyond)[-1] == "d0499.md", "the cut is at the end of the ordered list"


def test_a_listing_git_cut_short_drops_its_partial_row_and_says_truncated(root):
    cut = row("a.md") + b"100644 blob " + BLOB.encode() + b"      1"
    listing = list_documents(root, listing_script(root, cut, truncated=True))
    assert paths(listing) == ["a.md"] and listing.truncated is True


def test_the_wire_shape_is_the_base_the_documents_and_the_flag(root):
    listing = list_documents(root, listing_script(root, row("a.md", size=3)))
    assert listing.as_dict() == {
        "base": {"commit": COMMIT, "ref": "refs/heads/main"},
        "documents": [{"doc_id": doc_id_of("a.md"), "path": "a.md", "length": 3,
                       "git_oid": BLOB}],
        "truncated": False}
    assert docs.EMPTY.as_dict() == {"base": None, "documents": [], "truncated": False}


def test_a_detached_head_names_itself_head(root):
    script = Script(said(toplevel(root)), said(b""), said(COMMIT.encode() + b"\n"),
                    said(b"", code=1), said(row("a.md")))
    assert list_documents(root, script).base == Head(COMMIT, "HEAD")


# --- states in which there is nothing to list -------------------------------------------------


def test_a_folder_with_no_git_entry_has_no_documents_and_no_process_runs(tmp_path, monkeypatch):
    folder = tmp_path / "plain"
    folder.mkdir()
    monkeypatch.setattr(docs.project_git.os.path, "lexists", lambda path: False)
    script = Script()
    assert list_documents(folder, script) == docs.EMPTY and script.calls == []


@pytest.mark.parametrize("answers", [
    [lambda root: said(toplevel(root.parent))],                                   # not the root
    [lambda root: said(toplevel(root)), lambda root: said(b"work/a.txt\0")],      # tracks work/
    [lambda root: said(b"fatal: detected dubious ownership in repository\n", code=128)],
], ids=["not repo root", "unsupported", "unsafe directory"])
def test_a_folder_admission_refuses_has_no_documents_and_its_tree_is_never_listed(
        root, answers):
    script = Script(*(answer(root) for answer in answers))
    assert list_documents(root, script) == docs.EMPTY
    assert all(args[2] != "ls-tree" for args, _ in script.calls)


def test_a_repository_with_no_commit_has_no_documents(root):
    script = Script(said(toplevel(root)), said(b""), said(b"", code=1))
    assert list_documents(root, script) == docs.EMPTY
    assert len(script.calls) == 3


@pytest.mark.parametrize("answer", [
    said(b"fatal: not a git repository\n", code=128), said(b"", code=None, timed_out=True)])
def test_git_failing_to_name_head_is_a_failed_read_and_not_an_empty_project(root, answer):
    script = Script(said(toplevel(root)), said(b""), answer)
    with pytest.raises(GitReadFailed):
        list_documents(root, script)


def test_a_head_git_names_with_no_object_id_is_a_failed_read(root):
    script = Script(said(toplevel(root)), said(b""), said(b"not-an-oid\n"))
    with pytest.raises(GitReadFailed):
        list_documents(root, script)


# --- what git is asked ------------------------------------------------------------------------


def test_the_commands_are_read_only_and_the_tree_is_named_by_the_head_oid_alone(root):
    script = listing_script(root, row("a.md"))
    list_documents(root, script)
    verbs = [args[2] for args, _ in script.calls]
    assert verbs == ["rev-parse", "ls-files", "rev-parse", "symbolic-ref", "ls-tree"]
    assert script.calls[2][0] == ("-C", str(root), "rev-parse", "--verify", "--quiet",
                                  "HEAD^{commit}")
    assert script.calls[4][0] == ("-C", str(root), "ls-tree", "-r", "-l", "-z", "--full-tree",
                                  COMMIT)
    assert all(separate for (args, separate) in script.calls[2:])


def test_a_relative_root_is_refused_before_git_is_asked(tmp_path):
    script = Script()
    with pytest.raises(ValueError, match="absolute"):
        list_documents("project", script)
    assert script.calls == []


# --- reading one document ---------------------------------------------------------------------


def read_script(root, blob, *, path="docs/spec.md", size=None):
    tree = row(path, oid=BLOB, size=len(blob) if size is None else size)
    return Script(*listing_script(root, tree).answers, said(blob))


def test_one_document_is_its_id_path_blob_and_text_read_by_the_blob_and_not_the_path(root):
    script = read_script(root, "# Spec\n\nLogin.\n".encode("utf-8"))
    document = read_document(root, script, doc_id_of("docs/spec.md"))
    assert document == {"doc_id": doc_id_of("docs/spec.md"), "path": "docs/spec.md",
                        "git_oid": BLOB, "content": "# Spec\n\nLogin.\n"}
    assert script.calls[-1][0] == ("-C", str(root), "cat-file", "blob", BLOB)
    assert script.calls[-1][1] is True


def test_the_text_is_kept_byte_for_byte_including_a_bom_and_carriage_returns(root):
    text = "﻿line one\r\nline two\r\n"
    script = read_script(root, text.encode("utf-8"))
    assert read_document(root, script, doc_id_of("docs/spec.md"))["content"] == text


def test_an_id_the_head_does_not_list_is_doc_unknown_and_no_blob_is_read(root):
    script = listing_script(root, row("docs/spec.md"))
    with pytest.raises(DocumentRefused) as refused:
        read_document(root, script, doc_id_of("docs/other.md"))
    assert refused.value.reason == "doc_unknown"
    assert all(args[2] != "cat-file" for args, _ in script.calls)


@pytest.mark.parametrize("blob", [b"\xff\xfe binary", b"text\x00with a nul", b"\xc3\x28 bad"])
def test_a_document_that_is_not_utf8_text_is_document_not_text(root, blob):
    with pytest.raises(DocumentRefused) as refused:
        read_document(root, read_script(root, blob), doc_id_of("docs/spec.md"))
    assert refused.value.reason == "document_not_text"


def test_a_blob_git_does_not_give_is_a_failed_read(root):
    script = Script(*listing_script(root, row("docs/spec.md")).answers,
                    said(b"fatal: bad object\n", code=128))
    with pytest.raises(GitReadFailed):
        read_document(root, script, doc_id_of("docs/spec.md"))


# --- the files of a seed's base tree ----------------------------------------------------------


def test_the_base_tree_is_listed_by_its_oid_and_every_document_of_it_is_keyed_by_id(root):
    tree = row("docs/a.md", oid="2" * 40) + row("src/main.py") + row("CLAUDE.md", oid="3" * 40)
    script = Script(said(tree))
    found = docs.base_documents(root, script, TREE)
    assert sorted(found) == sorted([doc_id_of("docs/a.md"), doc_id_of("CLAUDE.md")])
    assert found[doc_id_of("docs/a.md")].git_oid == "2" * 40
    assert script.calls[0][0] == ("-C", str(root), "ls-tree", "-r", "-l", "-z", "--full-tree",
                                  TREE)


def test_a_base_listing_git_cut_short_is_a_failed_read_because_absence_cannot_be_judged(root):
    with pytest.raises(GitReadFailed):
        docs.base_documents(root, Script(said(row("a.md"), truncated=True)), TREE)


@pytest.mark.parametrize("tree", ["--output=x", "HEAD", "", "e" * 39, "E" * 40])
def test_only_an_object_id_names_a_tree_so_no_option_can_be_smuggled_in(root, tree):
    script = Script()
    with pytest.raises(ValueError):
        docs.base_documents(root, script, tree)
    assert script.calls == []


# --- real repositories ------------------------------------------------------------------------


@needs_git
def test_a_real_repository_lists_its_documents_at_the_oids_and_sizes_git_gives(tmp_path):
    folder = repository(tmp_path)
    head = commit(folder, {"README.md": "# Hi\n", "docs/spec.md": "spec\n", "src/a.py": "x = 1\n",
                           "notes/todo.txt": "todo\n"})
    listing = list_documents(folder, real_reader(tmp_path))
    assert listing.base.commit == head and listing.base.ref.startswith("refs/heads/")
    assert paths(listing) == ["README.md", "docs/spec.md", "notes/todo.txt"]
    for document in listing.documents:
        assert document.git_oid == blob_oid(folder, document.path)
        assert document.doc_id == doc_id_of(document.path)
    assert [d.length for d in listing.documents] == [5, 5, 5]


@needs_git
def test_a_real_symlink_entry_and_a_submodule_entry_are_never_offered(tmp_path):
    folder = repository(tmp_path)
    commit(folder, {"a.md": "a\n"})
    target = blob_oid(folder, "a.md")
    git("update-index", "--add", "--cacheinfo", f"120000,{target},link.md", cwd=folder)
    git("update-index", "--add", "--cacheinfo", f"160000,{'9' * 40},sub.md", cwd=folder)
    git("commit", "-q", "-m", "links", cwd=folder)
    assert paths(list_documents(folder, real_reader(tmp_path))) == ["a.md"]


@needs_git
def test_a_real_repository_with_no_commit_and_a_real_subfolder_have_no_documents(tmp_path):
    folder = repository(tmp_path)
    assert list_documents(folder, real_reader(tmp_path)) == docs.EMPTY
    commit(folder, {"docs/a.md": "a\n"})
    assert list_documents(folder / "docs", real_reader(tmp_path)) == docs.EMPTY


@needs_git
def test_a_real_detached_head_is_listed_under_the_name_head(tmp_path):
    folder = repository(tmp_path)
    head = commit(folder, {"a.md": "a\n"})
    git("checkout", "-q", "--detach", cwd=folder)
    listing = list_documents(folder, real_reader(tmp_path))
    assert listing.base == Head(head, "HEAD") and paths(listing) == ["a.md"]


@needs_git
def test_a_real_document_is_read_as_the_text_of_the_blob_and_a_binary_one_is_refused(tmp_path):
    folder = repository(tmp_path)
    commit(folder, {"docs/spec.md": "# Spec\r\nkept\r\n", "docs/blob.md": b"\xff\xfe\x00 bin"})
    reader = real_reader(tmp_path)
    document = read_document(folder, reader, doc_id_of("docs/spec.md"))
    assert document["content"] == "# Spec\r\nkept\r\n"
    assert document["git_oid"] == blob_oid(folder, "docs/spec.md")
    with pytest.raises(DocumentRefused) as refused:
        read_document(folder, reader, doc_id_of("docs/blob.md"))
    assert refused.value.reason == "document_not_text"


@needs_git
def test_a_real_base_tree_lists_the_documents_it_holds_by_id(tmp_path):
    folder = repository(tmp_path)
    commit(folder, {"docs/a.md": "a\n", "CLAUDE.md": "rules\n", "src/x.py": "x\n"})
    tree = git("rev-parse", "HEAD^{tree}", cwd=folder).stdout.decode().strip()
    found = docs.base_documents(folder, real_reader(tmp_path), tree)
    assert sorted(found) == sorted([doc_id_of("docs/a.md"), doc_id_of("CLAUDE.md")])


@needs_git
def test_reading_the_documents_of_a_real_repository_writes_nothing_into_git(tmp_path):
    folder = repository(tmp_path)
    commit(folder, {"docs/a.md": "a\n", "b.txt": "b\n"})
    before = snapshot(folder / ".git")
    reader = real_reader(tmp_path)
    list_documents(folder, reader)
    read_document(folder, reader, doc_id_of("b.txt"))
    assert snapshot(folder / ".git") == before
