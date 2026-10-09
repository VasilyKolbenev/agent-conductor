"""A replacement ref cannot stand in for an object a first commit is judged by (review ruling F1).

Git reads `refs/replace/<oid>` by default: `cat-file`, `diff-index` and every tree-ish read answer
with the bytes of the REPLACEMENT while the name stays the original. The reads that prove the
first commit on this road read the real objects instead: the commit the owner made, the objects
the write relies on, the tree of a signature wait, and the tree the installed index is compared
with. Every test plants a real replacement with the Git that made the repository, then shows the
judgement that the replacement would have changed. Nothing here makes the product look at more
of the repository than before.
"""
from __future__ import annotations

import shutil

import pytest

from conductor.command import git_setup_first_records as records
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, project, seal, terms_of)
from tests.git_first_readers import READERS
from tests.git_first_signing import (  # noqa: F401
    FORMATS, owner_makes_the_commit, signing_key, signing_project, waits)
from tests.git_repo_helpers import needs_git, snapshot
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import (
    FILES as TWO_FILES, damage_after_prepare, no_receipt, own_leftovers, remove_object, text,
    trunk_exists)
from tests.test_git_setup_first_recognition import an_empty_tree
from tests.test_git_setup_first_recovery import FILES, git_path

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
for_every_reader = pytest.mark.parametrize("which", READERS)


def raw_commit(p, oid, *flags) -> str:
    return p.git(*flags, "cat-file", "commit", oid, cwd=p.root).stdout.decode("utf-8")


@for_every_reader
@pytest.mark.parametrize("fmt", FORMATS)
def test_a_replacement_ref_does_not_let_an_unsigned_commit_pass_as_the_signed_one(
        tmp_path, signing_key, fmt, which):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt, which=which)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    unsigned = owner_makes_the_commit(p, detail, unsigned=True)     # the branch stands at A
    signed = owner_makes_the_commit(p, detail, publish=False)       # B: the intended signed commit
    p.git("replace", unsigned, signed, cwd=p.root)
    assert "gpgsig" in raw_commit(p, unsigned)                      # Git reads B where A is named
    assert "gpgsig" not in raw_commit(p, unsigned, "--no-replace-objects")
    refs = snapshot(p.root / ".git" / "refs")
    assert reason(confirm(p, digest=digest)) == "head_exists"
    assert snapshot(p.root / ".git" / "refs") == refs               # the branch and the replacement
    assert text(p, "rev-parse", "refs/heads/trunk") == unsigned
    assert text(p, "rev-parse", f"refs/replace/{unsigned}") == signed
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert records.read_op(p.root).stage == AWAITING_SIGNATURE and no_receipt(p)


@for_every_reader
def test_a_replacement_ref_does_not_stand_in_for_a_blob_the_entry_check_found_gone(
        tmp_path, monkeypatch, which):
    p = project(tmp_path, TWO_FILES, which=which)
    digest = seal(p)["paths_digest"]

    def replaced_and_gone(made):
        gone, other = (row["git_oid"] for row in made[0]["files"][:2])
        p.git("replace", gone, other, cwd=p.root)                   # the name now reads as `other`
        remove_object(p, gone)

    damage_after_prepare(monkeypatch, replaced_and_gone)
    assert reason(confirm(p, digest=digest)) == "paths_changed"
    assert own_leftovers(p) == [] and no_receipt(p) and not trunk_exists(p)
    assert not git_path(p, "index").exists()


@for_every_reader
def test_a_replacement_ref_does_not_stand_in_for_the_tree_of_a_wait(tmp_path, signing_key, which):
    p = signing_project(tmp_path, signing_key, FILES, which=which)
    digest = terms_of(p)
    tree = waits(p, "snapshot", digest)["tree"]
    p.git("replace", tree, an_empty_tree(p), cwd=p.root)            # the tree now reads as empty
    remove_object(p, tree)
    stored = snapshot(p.root / ".git" / "refs")
    assert reason(confirm(p, digest=digest)) == "setup_damaged"
    assert snapshot(p.root / ".git" / "refs") == stored and no_receipt(p)


def trees_of_the_owners_index(p, tmp_path) -> str:
    """The tree of the index standing in `.git`, written from a copy: the file is not touched."""
    scratch = tmp_path / "copy-of-the-owners-index"
    shutil.copyfile(git_path(p, "index"), scratch)
    made = p.git("write-tree", cwd=p.root, env={"GIT_INDEX_FILE": str(scratch)})
    return made.stdout.decode().strip()


@for_every_reader
def test_a_replacement_ref_does_not_let_an_index_of_another_tree_pass_as_installed(
        tmp_path, monkeypatch, which):
    p = project(tmp_path, FILES, which=which)
    digest = terms_of(p, "snapshot")
    crashed(monkeypatch, p, "_do_mark_ref_moved", "snapshot", digest)
    git_path(p, "index.lock").unlink()
    p.git("add", "owner.txt", cwd=p.root)                           # an index of another tree
    theirs = trees_of_the_owners_index(p, tmp_path)
    committed = records.read_op(p.root).expected_tree
    assert theirs != committed
    p.git("replace", committed, theirs, cwd=p.root)                 # the tree reads as theirs
    index = git_path(p, "index")
    before = (index.read_bytes(), index.stat().st_ino, index.stat().st_mtime_ns)
    assert reason(confirm(p, "snapshot", digest=digest)) == "index_exists"
    assert (index.read_bytes(), index.stat().st_ino, index.stat().st_mtime_ns) == before
    assert no_receipt(p) and not git_path(p, "index.lock").exists()
