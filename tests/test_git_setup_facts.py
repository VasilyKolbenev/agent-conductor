"""The facts a first-commit confirmation freezes, and the one route a first commit may write to.

`first_facts` refuses on exactly the states a resume has to walk: the product's own lock, the ref it
published and the index it installed. `frozen_facts` reads the four terms without those refusals,
so the decision table, and not a precondition of reading, judges the three states. `plain_git_dir`
answers the project's own `.git` directory or refuses `unsafe_git_route` before anything is written.
"""
from __future__ import annotations

import pytest

from conductor.command.accept_manifest import SnapshotRefused
from conductor.command.git_setup_facts import first_facts, frozen_facts, plain_git_dir
from conductor.command.git_setup_records import SetupRefused
from tests.git_repo_helpers import commit, git, needs_git, real_reader, repository
from tests.test_git_setup import Trace, unborn

TERMS = {"target_ref", "object_format", "author", "signing"}
#: The state of the repository and the word `first_facts` refuses it with.
REFUSED = [("lock", "index_locked"), ("ref", "head_exists"), ("index", "index_exists")]
#: What the preview asked of Git, in order, before the split of the frozen facts out of it.
ORDER = ["rev-parse", "ls-files", "rev-parse", "rev-parse", "symbolic-ref", "check-ref-format",
         "var", "var", "rev-parse", "config"]


def plant(project, state):
    """Put an unborn repository into the state that `first_facts` refuses."""
    root, folder = project.root, project.root / ".git"
    if state == "lock":
        (folder / "index.lock").write_bytes(b"")
    elif state == "ref":
        tree = git("write-tree", cwd=root).stdout.decode().strip()
        made = git("commit-tree", "-m", "owner", tree, cwd=root).stdout.decode().strip()
        target = git("symbolic-ref", "HEAD", cwd=root).stdout.decode().strip()
        git("update-ref", target, made, cwd=root)
    else:
        (root / "owner.txt").write_bytes(b"owner\n")
        git("add", "owner.txt", cwd=root)


def verbs(calls):
    """The Git command of each call: the first word after the global options."""
    names = []
    for args, _keywords in calls:
        words = list(args)
        while words and words[0] in ("--no-optional-locks", "-C"):
            words = words[2:] if words[0] == "-C" else words[1:]
        names.append(words[0])
    return names


@needs_git
@pytest.mark.parametrize("state, refusal", REFUSED)
def test_frozen_facts_read_the_four_terms_where_first_facts_refuses(tmp_path, state, refusal):
    project = unborn(tmp_path)
    root, reader = project.root, project.api._project_git
    clean = first_facts(root, reader)
    assert set(frozen_facts(root, reader)) == TERMS
    assert clean == {"head": None, **frozen_facts(root, reader)}
    plant(project, state)
    with pytest.raises(SetupRefused) as caught:
        first_facts(root, reader)
    assert caught.value.reason == refusal
    assert frozen_facts(root, reader) == {name: clean[name] for name in TERMS}


@needs_git
def test_first_facts_asks_git_in_the_order_it_did_before_the_frozen_facts_were_split_out(tmp_path):
    project = unborn(tmp_path)
    reader = Trace(project.api._project_git)
    first_facts(project.root, reader)
    assert verbs(reader.calls) == ORDER


@needs_git
def test_frozen_facts_refuse_a_missing_identity_and_a_head_that_names_no_branch(tmp_path):
    project = unborn(tmp_path)
    root, reader = project.root, project.api._project_git
    with pytest.raises(SnapshotRefused) as caught:     # the route words it as it does a preview's
        frozen_facts(root, Trace(reader, "-c", "user.name=", "-c", "user.email="))
    assert caught.value.reason == "git_identity_missing"
    git("symbolic-ref", "HEAD", "refs/tags/not-a-branch", cwd=root)
    with pytest.raises(SetupRefused) as caught:
        frozen_facts(root, reader)
    assert caught.value.reason == "head_exists"


@needs_git
def test_plain_git_dir_names_the_projects_own_dot_git(tmp_path):
    project = unborn(tmp_path)
    assert plain_git_dir(project.root, project.api._project_git) == project.root / ".git"


@needs_git
def test_plain_git_dir_refuses_a_linked_worktree(tmp_path):
    main = repository(tmp_path)
    commit(main, {"owner.txt": "keep\n"})
    linked = tmp_path / "linked"
    git("worktree", "add", "--detach", str(linked), "HEAD", cwd=main)
    with pytest.raises(SetupRefused) as caught:
        plain_git_dir(linked, real_reader(tmp_path))
    assert caught.value.reason == "unsafe_git_route"


@needs_git
def test_plain_git_dir_refuses_a_dot_git_that_is_a_link_to_a_directory(tmp_path):
    repo = repository(tmp_path, "real")
    moved = tmp_path / "elsewhere"
    (repo / ".git").rename(moved)
    try:
        (repo / ".git").symlink_to(moved, target_is_directory=True)
    except OSError as error:
        pytest.skip(str(error))
    with pytest.raises(SetupRefused) as caught:
        plain_git_dir(repo, real_reader(tmp_path))
    assert caught.value.reason == "unsafe_git_route"
