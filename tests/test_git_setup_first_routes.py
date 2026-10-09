"""The folders below `.git` that a first commit writes through are plain ones (rulings R1 and R2).

Git writes the objects, the ref and its reflogs below `.git` by paths of its own choosing, and the
write guard of the project does not cover them. A link, a junction or another portal on such a path
sends the write outside the project, so the product looks at the actual destinations before it asks
Git to write, and again before the one write a resume still has to make. Every witness makes a real
portal (a symlink wherever the host allows one, a junction on Windows) and judges the folder the
portal leads to, not only the answer. `exclude` is the other writer into `.git`: it judges the NAME
`.git` before the git dir that Git names follows it. A structural check, not isolation from a
process that swaps a folder between the check and the write.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from conductor.command.git_setup_facts import exclude
from conductor.command.git_setup_records import SetupRefused
from conductor.command.product_names import BLOCK_BEGIN, ExcludeWriteError, write_exclude_block
from conductor.ownership import data_root
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, project, seal, terms_of)
from tests.git_repo_helpers import commit, git, needs_git, real_reader, repository
from tests.test_git_setup import reason, step
from tests.test_git_setup_first_commit import FILES, no_receipt, own_leftovers
from tests.test_seed_routes import Folder

pytestmark = [needs_git]
with_the_door = pytest.mark.usefixtures("confirm_door")
KINDS = ["symlink", *(["junction"] if os.name == "nt" else [])]
for_every_portal = pytest.mark.parametrize("kind", KINDS)
NESTED = "feature/deep"
EMPTY_TREE_FOLDER = "objects/4b"                  # the folder the empty tree is written into
BLOB_FOLDER = "@blob"                             # the folder of the first shown blob
#: Where the portal stands, the mode, and the branch HEAD names, one row per kind of destination.
DESTINATIONS = [
    pytest.param("objects", "snapshot", "trunk", id="objects"),
    pytest.param(EMPTY_TREE_FOLDER, "empty", "trunk", id="fan_out_of_the_tree"),
    pytest.param(BLOB_FOLDER, "snapshot", "trunk", id="fan_out_of_a_blob"),
    pytest.param("refs/heads/feature", "snapshot", NESTED, id="nested_folder_of_the_ref"),
    pytest.param("logs/refs/heads/feature", "snapshot", NESTED, id="nested_folder_of_the_reflog"),
]


def make_portal(link: Path, target: Path, kind: str) -> None:
    """A real portal named `link` that leads to the folder `target`."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if kind == "junction":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(str(error))


def divert(folder: Path, relative: str, outside: Path, kind: str) -> None:
    """Move what stands at `folder/relative` out to `outside` (an empty `outside` when nothing
    stands there) and leave a portal behind: the folder Git would write into is now elsewhere."""
    link = folder / relative
    if os.path.lexists(link):
        link.rename(outside)
    else:
        outside.mkdir(parents=True)
    make_portal(link, outside, kind)


def commondir_stub(p, outside: Path) -> None:
    """Move the repository to `outside`; leave a plain `.git` whose `commondir` file names it.

    The stub holds only `HEAD` and `commondir`: Git then keeps its objects, refs and reflogs in the
    folder `outside`, though the git dir it names is still `<root>/.git`."""
    dot = p.root / ".git"
    dot.rename(outside)
    dot.mkdir()
    (dot / "HEAD").write_bytes((outside / "HEAD").read_bytes())
    (dot / "commondir").write_text(str(outside), encoding="utf-8")


def remove_portal(link: Path) -> None:
    try:
        os.rmdir(link)                    # a junction, and a directory symlink on Windows
    except OSError:
        os.unlink(link)


def listing(folder: Path) -> dict[str, bytes | None]:
    """Every name below `folder` (a folder as None) with the bytes of each file."""
    return {path.relative_to(folder).as_posix(): path.read_bytes() if path.is_file() else None
            for path in sorted(folder.rglob("*"))}


def verdict(answer, outside: Path, before: dict) -> tuple:
    """What the answer was and whether the folder outside is exactly as it was."""
    word = reason(answer) if answer.status == 409 else answer.status
    return word, listing(outside) == before


def ref_exists(p, branch: str) -> bool:
    found = p.git("rev-parse", "--verify", "-q", f"refs/heads/{branch}", cwd=p.root, check=False)
    return found.returncode == 0


@with_the_door
@for_every_portal
@pytest.mark.parametrize("relative, mode, branch", DESTINATIONS)
def test_first_commit_refuses_a_portal_on_a_write_path_and_writes_nothing_outside(
        tmp_path, kind, relative, mode, branch):
    p = project(tmp_path, FILES, branch=branch)
    digest = terms_of(p, mode)
    if relative == BLOB_FOLDER:
        relative = f"objects/{seal(p)['files'][0]['git_oid'][:2]}"
    outside = tmp_path / "outside"
    divert(p.root / ".git", relative, outside, kind)
    before = listing(outside)
    answer = confirm(p, mode, digest=digest)
    assert verdict(answer, outside, before) == ("unsafe_git_route", True)
    assert own_leftovers(p) == [] and no_receipt(p) and not ref_exists(p, branch)


@with_the_door
def test_first_commit_refuses_a_reflog_that_is_a_link_to_a_file_and_leaves_that_file_alone(
        tmp_path):
    p = project(tmp_path, FILES)
    digest = terms_of(p, "snapshot")
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "reflog"
    target.write_bytes(b"the owner's own file\n")
    (p.root / ".git" / "logs").mkdir()
    try:
        (p.root / ".git" / "logs" / "HEAD").symlink_to(target)
    except OSError as error:
        pytest.skip(str(error))
    before = listing(outside)
    answer = confirm(p, "snapshot", digest=digest)
    assert verdict(answer, outside, before) == ("unsafe_git_route", True)
    assert own_leftovers(p) == [] and no_receipt(p) and not ref_exists(p, "trunk")


@with_the_door
@for_every_portal
def test_a_resume_refuses_a_portal_that_appeared_before_the_ref_moves_and_goes_on_without_it(
        tmp_path, monkeypatch, kind):
    p = project(tmp_path, FILES, branch=NESTED)
    digest = terms_of(p, "snapshot")
    crashed(monkeypatch, p, "_do_mark_locked", digest=digest)
    outside = tmp_path / "outside"
    divert(p.root / ".git", "refs/heads/feature", outside, kind)
    before = listing(outside)
    assert verdict(confirm(p, digest=digest), outside, before) == ("unsafe_git_route", True)
    assert not ref_exists(p, NESTED) and no_receipt(p)
    remove_portal(p.root / ".git" / "refs" / "heads" / "feature")
    answer = confirm(p, digest=digest)
    assert answer.status == 201, answer.payload
    assert ref_exists(p, NESTED) and own_leftovers(p) == []


@with_the_door
def test_first_commit_refuses_a_plain_dot_git_whose_commondir_sends_objects_and_refs_outside(
        tmp_path):
    p = project(tmp_path, FILES)
    digest = terms_of(p, "snapshot")
    outside = tmp_path / "outside.git"
    commondir_stub(p, outside)
    before = listing(outside)
    answer = confirm(p, "snapshot", digest=digest)
    assert verdict(answer, outside, before) == ("unsafe_git_route", True)
    assert own_leftovers(p) == [] and no_receipt(p) and not ref_exists(p, "trunk")


@with_the_door
def test_a_resume_refuses_a_dot_git_that_gained_a_commondir_while_it_waited(tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p, "snapshot")
    crashed(monkeypatch, p, "_do_mark_locked", digest=digest)
    outside = tmp_path / "outside.git"
    commondir_stub(p, outside)
    before = listing(outside)
    assert verdict(confirm(p, digest=digest), outside, before) == ("unsafe_git_route", True)
    assert not ref_exists(p, "trunk") and no_receipt(p)


def reftable_project(tmp_path, how: str):
    """A project whose refs are kept by the reftable backend, made by `init` or by `refs migrate`;
    it skips where the Git has no reftable."""
    if how == "init":
        return project(tmp_path, FILES, ref_format="reftable")
    p = project(tmp_path, FILES)
    moved = p.git("refs", "migrate", "--ref-format=reftable", cwd=p.root, check=False)
    if moved.returncode != 0:
        pytest.skip("this git has no reftable")
    return p


@with_the_door
@for_every_portal
@pytest.mark.parametrize("how", ["init", "migrate"])
def test_first_commit_refuses_a_reftable_folder_that_is_a_portal_and_writes_nothing_outside(
        tmp_path, kind, how):
    p = reftable_project(tmp_path, how)
    digest = terms_of(p, "snapshot")
    outside = tmp_path / "outside"
    divert(p.root / ".git", "reftable", outside, kind)
    before = listing(outside)
    answer = confirm(p, "snapshot", digest=digest)
    assert verdict(answer, outside, before) == ("unsafe_git_route", True)
    assert own_leftovers(p) == [] and no_receipt(p) and not ref_exists(p, "trunk")


@with_the_door
@pytest.mark.parametrize("how", ["init", "migrate"])
def test_first_commit_refuses_a_reftable_repository_and_writes_nothing_below_dot_git(
        tmp_path, how):
    p = reftable_project(tmp_path, how)
    digest = terms_of(p, "snapshot")
    dot = p.root / ".git"
    before = listing(dot)
    answer = confirm(p, "snapshot", digest=digest)
    assert verdict(answer, dot, before) == ("unsafe_git_route", True)
    assert own_leftovers(p) == [] and no_receipt(p) and not ref_exists(p, "trunk")


def project_with_a_large_blob(tmp_path):
    """A project whose file `big.bin` is above `core.bigFileThreshold`: Git streams such a blob
    into a pack under `objects/pack` instead of writing a loose object."""
    p = project(tmp_path, {**FILES, "big.bin": b"x" * 4096})
    p.git("config", "core.bigFileThreshold", "1k", cwd=p.root)
    return p


@with_the_door
@for_every_portal
def test_first_commit_refuses_a_portal_at_objects_pack_where_git_streams_a_large_blob(
        tmp_path, kind):
    p = project_with_a_large_blob(tmp_path)
    digest = terms_of(p, "snapshot")
    outside = tmp_path / "outside"
    divert(p.root / ".git", "objects/pack", outside, kind)
    before = listing(outside)
    answer = confirm(p, "snapshot", digest=digest)
    assert verdict(answer, outside, before) == ("unsafe_git_route", True)
    assert own_leftovers(p) == [] and no_receipt(p) and not ref_exists(p, "trunk")


@with_the_door
def test_first_commit_streams_a_blob_above_the_big_file_threshold_into_the_plain_pack_folder(
        tmp_path):
    p = project_with_a_large_blob(tmp_path)
    pack_folder = p.root / ".git" / "objects" / "pack"
    assert list(pack_folder.glob("pack-*")) == []
    answer = confirm(p, "snapshot")
    assert answer.status == 201, answer.payload
    assert len(list(pack_folder.glob("pack-*.pack"))) == 1 and ref_exists(p, "trunk")


@with_the_door
def test_first_commit_writes_through_plain_nested_folders_of_the_ref_the_reflog_and_the_objects(
        tmp_path):
    p = project(tmp_path, {}, branch=NESTED)
    folder = p.root / ".git"
    for relative in ("refs/heads/feature", "logs/refs/heads/feature", EMPTY_TREE_FOLDER):
        (folder / relative).mkdir(parents=True)
    answer = confirm(p, "empty")
    assert answer.status == 201, answer.payload
    receipt = answer.payload["setup"]
    assert (folder / "refs/heads/feature/deep").is_file() and ref_exists(p, NESTED)
    assert p.git("rev-parse", "HEAD", cwd=p.root).stdout.decode().strip() == receipt["commit"]
    assert (folder / "objects/4b/825dc642cb6eb9a060e54bf8d69288fbee4904").is_file()
    assert (folder / "logs/refs/heads/feature/deep").is_file()


@for_every_portal
def test_exclude_refuses_a_dot_git_that_is_a_portal_and_leaves_its_target_as_it_was(
        tmp_path, kind):
    repo = repository(tmp_path, "real")
    outside = tmp_path / "elsewhere"
    divert(repo, ".git", outside, kind)
    before = listing(outside)
    try:
        outcome = exclude(repo, real_reader(tmp_path))
    except SetupRefused as refused:
        outcome = refused.reason
    assert (outcome, listing(outside) == before) == ("unsafe_git_route", True)


@for_every_portal
def test_the_exclude_step_refuses_a_dot_git_that_is_a_portal_and_publishes_no_receipt(
        tmp_path, kind):
    folder = Folder(tmp_path)
    git("init", "-q", cwd=folder.root)
    outside = tmp_path / "elsewhere"
    divert(folder.root, ".git", outside, kind)
    before = listing(outside)
    answer = step(folder, "exclude")
    assert verdict(answer, outside, before) == ("unsafe_git_route", True)
    assert not (data_root(folder.root) / "git" / "setup" / "exclude.json").exists()


@for_every_portal
def test_the_block_writer_defers_a_dot_git_that_is_a_portal_and_leaves_its_target_alone(
        tmp_path, kind):
    repo = repository(tmp_path, "real")
    outside = tmp_path / "elsewhere"
    divert(repo, ".git", outside, kind)
    before = listing(outside)
    answer = write_exclude_block(repo / ".git")
    assert (answer, listing(outside) == before) == ("deferred", True)


@for_every_portal
def test_the_block_writer_refuses_an_info_folder_that_is_a_portal_and_leaves_its_target_alone(
        tmp_path, kind):
    repo = repository(tmp_path, "real")
    outside = tmp_path / "elsewhere"
    divert(repo / ".git", "info", outside, kind)
    before = listing(outside)
    try:
        answer = write_exclude_block(repo / ".git")
    except ExcludeWriteError as refused:
        answer = refused.code
    assert (answer, listing(outside) == before) == ("git_exclude_failed", True)


def test_exclude_writes_a_plain_dot_git_once_and_then_finds_its_block_present(tmp_path):
    repo = repository(tmp_path, "plain")
    reader = real_reader(tmp_path)
    assert exclude(repo, reader) == "written"
    assert exclude(repo, reader) == "present"
    assert BLOCK_BEGIN in (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")


def test_exclude_still_writes_the_common_dir_of_a_linked_worktree_whose_dot_git_is_a_file(
        tmp_path):
    main = repository(tmp_path)
    commit(main, {"owner.txt": "keep\n"})
    linked = tmp_path / "linked"
    git("worktree", "add", "--detach", str(linked), "HEAD", cwd=main)
    assert (linked / ".git").is_file()
    assert exclude(linked, real_reader(tmp_path)) == "written"
    assert BLOCK_BEGIN in (main / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert not (linked / "info").exists()
