"""The folders below `.git` that a first commit writes through are plain ones (ruling R1).

Git writes the objects, the ref and its reflogs below `.git` by paths of its own choosing, and the
write guard of the project does not cover them. A link, a junction or another portal on such a path
sends the write outside the project, so the product looks at the actual destinations before it asks
Git to write, and again before the one write a resume still has to make. Every witness makes a real
portal (a symlink wherever the host allows one, a junction on Windows) and judges the folder the
portal leads to, not only the answer. A structural check, not isolation from a process that swaps
a folder between the check and the write.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, project, seal, terms_of)
from tests.git_repo_helpers import needs_git
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import FILES, no_receipt, own_leftovers

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
