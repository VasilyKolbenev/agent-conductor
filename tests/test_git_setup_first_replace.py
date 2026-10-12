"""A replacement ref cannot stand in for an object a first commit is judged by (review ruling F1).

Git reads `refs/replace/<oid>` by default: `cat-file`, `diff-index` and every tree-ish read answer
with the bytes of the REPLACEMENT while the name stays the original. The reads that prove the
first commit on this road read the real objects instead: the commit the owner made, the objects
the write relies on, the tree of a signature wait, and the tree the installed index is compared
with. Every test plants a real replacement with the Git that made the repository, then shows the
judgement that the replacement would have changed. Nothing here makes the product look at more
of the repository than before.

A repository can also switch replacement refs on for itself, and on Git 2.31 (the lowest the
product accepts) `core.useReplaceRefs=true` in its configuration outweighs
`--no-replace-objects`. The reads therefore also carry `-c core.useReplaceRefs=false`, which
outweighs the repository's own setting, and the four tests that replace an object the proof reads
(the commit, a blob, the tree of a wait, the tree of the index) run with that setting unset and
set to `true`.

One more way to judge the bytes of another object than the one that is recorded: `cat-file commit
<oid>` follows a tag object to the commit it points at. A branch that names a tag of the intended
signed commit (Git writes it only where a replacement ref stands for the tag; a hand-written ref
file does too) must not be recorded as that commit, so the bytes read are also required to hash
to the name they were read under.
"""
from __future__ import annotations

import shutil

import pytest

from conductor.command import git_setup_first_records as records
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE
from tests.git_first_bench import confirm, crashed, project, seal, terms_of
from tests.git_first_readers import READERS
from tests.git_first_signing import (  # noqa: F401
    FORMATS, owner_makes_the_commit, signing_key, signing_project, waits)
from tests.git_repo_helpers import git as current_git, needs_git, snapshot
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import (
    FILES as TWO_FILES, damage_after_prepare, no_receipt, own_leftovers, remove_object, text,
    trunk_exists)
from tests.test_git_setup_first_recognition import an_empty_tree
from tests.test_git_setup_first_recovery import FILES, git_path

pytestmark = needs_git
for_every_reader = pytest.mark.parametrize("which", READERS)
#: A repository can switch replacement refs on for itself: on Git 2.31 `core.useReplaceRefs=true`
#: in the repository's own configuration outweighs `--no-replace-objects` (a newer Git keeps to it).
with_the_repository_setting = pytest.mark.parametrize(
    "use_refs", [None, "true"], ids=["default_setting", "use_replace_refs_true"])


#: How a test reads an object as stored, whatever the repository's own setting is.
THE_OBJECT_ITSELF = ("-c", "core.useReplaceRefs=false", "--no-replace-objects")


def raw_commit(p, oid, *flags) -> str:
    return p.git(*flags, "cat-file", "commit", oid, cwd=p.root).stdout.decode("utf-8")


def replace(p, original: str, other: str, use_refs: str | None) -> None:
    """Make `refs/replace/<original>` name `other`; `use_refs` is the repository's own setting."""
    p.git("replace", original, other, cwd=p.root)
    if use_refs is not None:
        p.git("config", "core.useReplaceRefs", use_refs, cwd=p.root)


@for_every_reader
@with_the_repository_setting
@pytest.mark.parametrize("fmt", FORMATS)
def test_a_replacement_ref_does_not_let_an_unsigned_commit_pass_as_the_signed_one(
        tmp_path, signing_key, fmt, which, use_refs):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt, which=which)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    unsigned = owner_makes_the_commit(p, detail, unsigned=True)     # the branch stands at A
    signed = owner_makes_the_commit(p, detail, publish=False)       # B: the intended signed commit
    replace(p, unsigned, signed, use_refs)
    assert "gpgsig" in raw_commit(p, unsigned)                      # Git reads B where A is named
    assert "gpgsig" not in raw_commit(p, unsigned, *THE_OBJECT_ITSELF)
    refs = snapshot(p.root / ".git" / "refs")
    assert reason(confirm(p, digest=digest)) == "head_exists"
    assert snapshot(p.root / ".git" / "refs") == refs               # the branch and the replacement
    assert text(p, "rev-parse", "refs/heads/trunk") == unsigned
    assert text(p, "rev-parse", f"refs/replace/{unsigned}") == signed
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert records.read_op(p.root).stage == AWAITING_SIGNATURE and no_receipt(p)


def a_tag_of(p, commit: str) -> str:
    """The object id of an annotated tag object that points at `commit` (not the commit's own).

    Made by the current Git: Git 2.31 does not know the `ssh` signing format of the project and
    refuses to run `tag` at all, though it reads the tag it is given."""
    current_git("tag", "-a", "-m", "a tag object", "points-at-the-commit", commit, cwd=p.root)
    return text(p, "rev-parse", "refs/tags/points-at-the-commit")


def put_the_branch_on(p, tag: str, other: str, how: str) -> None:
    """Make `refs/heads/trunk` name the tag object itself.

    `replacement`: with `refs/replace/<tag>` standing for `other` (a commit), Git's own type check
    reads a commit where the tag is named and lets `update-ref` write the branch. `by_hand`: the
    loose ref file is written without Git, and no replacement ref exists."""
    if how == "replacement":
        p.git("update-ref", f"refs/replace/{tag}", other, cwd=p.root)
        p.git("update-ref", "refs/heads/trunk", tag, "0" * len(tag), cwd=p.root)
    else:
        git_path(p, "refs/heads").mkdir(parents=True, exist_ok=True)
        git_path(p, "refs/heads/trunk").write_bytes(tag.encode("ascii") + b"\n")


@for_every_reader
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("how", ["replacement", "by_hand"])
def test_a_branch_that_names_a_tag_of_the_signed_commit_is_head_exists_and_nothing_is_recorded(
        tmp_path, signing_key, fmt, which, how):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt, which=which)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    signed = owner_makes_the_commit(p, detail, publish=False)       # C: the intended signed commit
    unsigned = owner_makes_the_commit(p, detail, unsigned=True, publish=False)   # X: another one
    tag = a_tag_of(p, signed)                                       # T: an object of its own
    put_the_branch_on(p, tag, unsigned, how)
    assert "gpgsig" in raw_commit(p, tag, "--no-replace-objects")   # `cat-file` follows T to C
    refs = snapshot(p.root / ".git" / "refs")
    assert reason(confirm(p, digest=digest)) == "head_exists"       # T is not the commit C
    assert snapshot(p.root / ".git" / "refs") == refs               # the branch and any replacement
    assert text(p, "rev-parse", "refs/heads/trunk") == tag
    if how == "replacement":
        assert text(p, "rev-parse", f"refs/replace/{tag}") == unsigned
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert records.read_op(p.root).stage == AWAITING_SIGNATURE and no_receipt(p)


def object_file(p, oid: str):
    return p.root / ".git" / "objects" / oid[:2] / oid[2:]


@for_every_reader
@pytest.mark.parametrize("fmt", FORMATS)
def test_a_branch_whose_object_file_holds_the_signed_commit_under_another_name_is_head_exists(
        tmp_path, signing_key, fmt, which):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt, which=which)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    signed = owner_makes_the_commit(p, detail, publish=False)       # C: the intended signed commit
    other = owner_makes_the_commit(p, detail, unsigned=True, publish=False)      # X: another one
    remove_object(p, other)
    shutil.copyfile(object_file(p, signed), object_file(p, other))  # the file named X holds C
    git_path(p, "refs/heads").mkdir(parents=True, exist_ok=True)
    git_path(p, "refs/heads/trunk").write_bytes(other.encode("ascii") + b"\n")
    assert raw_commit(p, other) == raw_commit(p, signed)            # `cat-file` does not re-hash
    refs = snapshot(p.root / ".git" / "refs")
    assert reason(confirm(p, digest=digest)) == "head_exists"       # the bytes are not X's own
    assert snapshot(p.root / ".git" / "refs") == refs
    assert text(p, "rev-parse", "refs/heads/trunk") == other
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert records.read_op(p.root).stage == AWAITING_SIGNATURE and no_receipt(p)


@for_every_reader
@with_the_repository_setting
def test_a_replacement_ref_does_not_stand_in_for_a_blob_the_entry_check_found_gone(
        tmp_path, monkeypatch, which, use_refs):
    p = project(tmp_path, TWO_FILES, which=which)
    digest = seal(p)["paths_digest"]

    def replaced_and_gone(made):
        gone, other = (row["git_oid"] for row in made[0]["files"][:2])
        replace(p, gone, other, use_refs)                           # the name now reads as `other`
        remove_object(p, gone)

    damage_after_prepare(monkeypatch, replaced_and_gone)
    assert reason(confirm(p, digest=digest)) == "paths_changed"
    assert own_leftovers(p) == [] and no_receipt(p) and not trunk_exists(p)
    assert not git_path(p, "index").exists()


@for_every_reader
@with_the_repository_setting
def test_a_replacement_ref_does_not_stand_in_for_the_tree_of_a_wait(
        tmp_path, signing_key, which, use_refs):
    p = signing_project(tmp_path, signing_key, FILES, which=which)
    digest = terms_of(p)
    tree = waits(p, "snapshot", digest)["tree"]
    replace(p, tree, an_empty_tree(p), use_refs)                    # the tree now reads as empty
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
@with_the_repository_setting
def test_a_replacement_ref_does_not_let_an_index_of_another_tree_pass_as_installed(
        tmp_path, monkeypatch, which, use_refs):
    p = project(tmp_path, FILES, which=which)
    digest = terms_of(p, "snapshot")
    crashed(monkeypatch, p, "_do_mark_ref_moved", "snapshot", digest)
    git_path(p, "index.lock").unlink()
    p.git("add", "owner.txt", cwd=p.root)                           # an index of another tree
    theirs = trees_of_the_owners_index(p, tmp_path)
    committed = records.read_op(p.root).expected_tree
    assert theirs != committed
    replace(p, committed, theirs, use_refs)                         # the tree reads as theirs
    index = git_path(p, "index")
    before = (index.read_bytes(), index.stat().st_ino, index.stat().st_mtime_ns)
    assert reason(confirm(p, "snapshot", digest=digest)) == "index_exists"
    assert (index.read_bytes(), index.stat().st_ino, index.stat().st_mtime_ns) == before
    assert no_receipt(p) and not git_path(p, "index.lock").exists()
