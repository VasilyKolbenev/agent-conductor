"""The confirmed first commit through the route: the happy path and what it may write (plan Task 7).

Every test runs with the route's confirm door held open (`confirm_door`): the door opens for real
only after the compatibility gate on the lowest supported Git is closed (Task 8.7). Each one takes
the preview the desk would show, confirms exactly that, and looks at the repository with the
reader's own Git. Recovery at every boundary is Task 8's; here the driver runs once, start to end.
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

import pytest

from conductor.command import git_setup, git_setup_first
from conductor.command.adapters import AdapterRegistry
from conductor.command.git_setup_first_index import terms_hash, verify
from conductor.command.git_setup_first_pending import describe
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.run_store import RunStore, StoreError
from conductor.ownership import data_root
from tests.git_first_bench import confirm, confirm_door, op_file, project, seal  # noqa: F401
from tests.git_first_readers import READERS
from tests.git_first_scratch import NOTICE, notice_lines
from tests.git_repo_helpers import git, needs_git, real_reader, repository, snapshot
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, ids
from tests.test_command_materials_routes import PROJECT_ID
from tests.test_command_project_doors import request
from tests.test_git_setup import PATH, reason
from tests.test_git_setup_modes import legacy_digest

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
FILES = {"a.txt": b"one\n", "docs/b.md": b"two\n"}
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
NO_SUCH = "sha256:" + "0" * 64
FORMATS = ["sha1", "sha256"]
for_both_modes = pytest.mark.parametrize("mode", ["snapshot", "empty"])
for_every_reader = pytest.mark.parametrize("which", READERS)


def text(p, *args):
    return p.git(*args, cwd=p.root).stdout.decode().strip()


def own_leftovers(p):
    """Every file of the first commit that must be gone once it is finished (or refused)."""
    folder, setup = p.root / ".git", data_root(p.root) / "git" / "setup"
    found = [path.name for path in folder.glob("conduct-first-index-*")]
    found += [path.name for path in setup.glob("first_commit.index-*")]
    found += [path.name for path in (data_root(p.root) / "git").glob("index-first-*")]
    found += [name for name in ("index.lock",) if (folder / name).exists()]
    return found + ([op_file(p).name] if op_file(p).exists() else [])


def install_files(p):
    return list((data_root(p.root) / "git" / "setup").glob("first_commit.index-*"))


def no_receipt(p):
    return not (data_root(p.root) / "git" / "setup" / "first_commit.json").exists()


def trunk_exists(p):
    return p.git("rev-parse", "--verify", "-q", "refs/heads/trunk", cwd=p.root,
                 check=False).returncode == 0


def owner_ref(p, name="trunk"):
    """The owner's own commit of the empty tree, made by plumbing, on `refs/heads/<name>`."""
    made = text(p, "commit-tree", "-m", "owner", EMPTY_TREE)
    p.git("update-ref", f"refs/heads/{name}", made, cwd=p.root)
    return made


def commit_body(p):
    raw = p.git("cat-file", "commit", "HEAD", cwd=p.root).stdout.decode("utf-8")
    return raw.split("\n\n", 1)[1]


@for_every_reader
def test_first_commit_snapshot_makes_head_index_and_status_agree(tmp_path, which):
    p = project(tmp_path, FILES, which=which)
    answer = confirm(p)
    assert answer.status == 201, answer.payload
    receipt = answer.payload["setup"]
    assert receipt["step"] == "first_commit" and receipt["file_count"] == 2
    assert receipt["target_ref"] == "refs/heads/trunk" and receipt["mode"] == "snapshot"
    assert text(p, "rev-parse", "HEAD") == receipt["commit"]
    assert text(p, "rev-list", "--count", "HEAD") == "1"
    assert text(p, "status", "--porcelain") == ""
    assert text(p, "ls-tree", "-r", "--name-only", "HEAD").splitlines() == ["a.txt", "docs/b.md"]
    assert commit_body(p) == "Первый коммит: 2 файлов (Conduct)\n\nConduct-Setup: first-commit\n"
    assert own_leftovers(p) == []


@for_every_reader
def test_first_commit_empty_commits_the_empty_tree_and_leaves_untracked_files_untracked(
        tmp_path, which):
    p = project(tmp_path, FILES, which=which)
    answer = confirm(p, "empty")
    assert answer.status == 201, answer.payload
    assert answer.payload["setup"]["file_count"] == 0
    assert text(p, "ls-tree", "HEAD") == ""
    assert text(p, "status", "--porcelain").splitlines() == ["?? a.txt", "?? docs/"]
    assert commit_body(p) == "Начало проекта (Conduct)\n\nConduct-Setup: first-commit\n"
    assert own_leftovers(p) == []


def test_first_commit_receipt_is_201_then_200_for_the_exact_repeat_without_a_git_call(tmp_path):
    p = project(tmp_path, FILES)
    first = confirm(p)
    assert first.status == 201, first.payload
    calls, before = len(p.spy.calls), snapshot(p.root / ".git")
    again = confirm(p, digest=first.payload["setup"]["paths_digest"])
    assert again.status == 200 and again.payload == first.payload
    assert len(p.spy.calls) == calls and snapshot(p.root / ".git") == before


def test_first_commit_with_other_actor_or_terms_after_a_receipt_is_setup_terms_changed(tmp_path):
    p = project(tmp_path, FILES)
    done = confirm(p).payload["setup"]
    before = snapshot(p.root / ".git")
    other = [confirm(p, digest=done["paths_digest"], actor="Another"),
             confirm(p, "empty"), confirm(p, digest=NO_SUCH)]
    assert [reason(answer) for answer in other] == ["setup_terms_changed"] * 3
    assert snapshot(p.root / ".git") == before


def test_first_commit_requires_the_shown_paths_digest(tmp_path):
    p = project(tmp_path, FILES)
    shown = seal(p)["paths_digest"]
    before = snapshot(p.root / ".git")
    assert reason(confirm(p, digest=NO_SUCH)) == "paths_changed"
    body = dict(step="first_commit", mode="snapshot", paths_digest=shown, actor="Owner")
    bad = [{**body, "paths_digest": None}, {**body, "mode": "empty"},
           {key: value for key, value in body.items() if key != "actor"},
           {**body, "extra": 1}, {**body, "mode": "full"}, {**body, "paths_digest": "sha256:x"},
           {**body, "actor": "Owner\nsecond line"}, {**body, "actor": " "}]
    for sent in bad:
        answer = request(p, "POST", PATH, sent)
        assert (answer.status, answer.payload["error"]["code"]) == (422, "contract_invalid"), sent
    assert snapshot(p.root / ".git") == before


def test_first_commit_with_required_signing_is_refused_before_any_object_is_written(tmp_path):
    p = project(tmp_path, FILES)
    p.git("config", "commit.gpgsign", "true", cwd=p.root)
    shown = seal(p)
    assert shown["signing"] is True and shown["warnings"] == ["signing_required"]
    before = snapshot(p.root / ".git")
    assert reason(confirm(p, digest=shown["paths_digest"])) == "signing_required"
    assert snapshot(p.root / ".git") == before and not op_file(p).exists() and no_receipt(p)


def test_first_commit_refuses_an_old_digest_as_paths_changed(tmp_path):
    p = project(tmp_path, FILES)
    shown = seal(p)
    before = snapshot(p.root / ".git")
    old = legacy_digest(shown["files"])
    assert old != shown["paths_digest"]
    assert reason(confirm(p, digest=old)) == "paths_changed"
    assert snapshot(p.root / ".git") == before


def an_owner_index(p, tmp_path):
    """The bytes of a valid index of the owner's own, made beside the repository by `git add`."""
    scratch = tmp_path / "foreign-index"
    p.git("add", "owner.txt", cwd=p.root, env={"GIT_INDEX_FILE": str(scratch)})
    return scratch.read_bytes()


@for_every_reader
def test_first_commit_takes_index_lock_before_checking_for_an_index(tmp_path, monkeypatch, which):
    p = project(tmp_path, {**FILES, "owner.txt": b"mine\n"}, which=which)
    planted, real = an_owner_index(p, tmp_path), git_setup_first._do_take_lock

    def then_a_writer_that_ignores_the_lock(api, op):
        made = real(api, op)
        (p.root / ".git" / "index").write_bytes(planted)
        return made

    monkeypatch.setattr(git_setup_first, "_do_take_lock", then_a_writer_that_ignores_the_lock)
    assert reason(confirm(p)) == "index_exists"
    assert (p.root / ".git" / "index").read_bytes() == planted
    assert not (p.root / ".git" / "index.lock").exists() and not trunk_exists(p)
    assert no_receipt(p) and not list((p.root / ".git").glob("conduct-first-index-*"))


@for_every_reader
def test_an_index_that_appears_before_the_install_is_index_exists_and_is_never_replaced(
        tmp_path, monkeypatch, which):
    p = project(tmp_path, {**FILES, "owner.txt": b"mine\n"}, which=which)
    planted, real = an_owner_index(p, tmp_path), git_setup_first._do_install_index

    def the_owner_writes_first(api, op):
        (p.root / ".git" / "index").write_bytes(planted)
        return real(api, op)

    monkeypatch.setattr(git_setup_first, "_do_install_index", the_owner_writes_first)
    assert reason(confirm(p)) == "index_exists"
    assert (p.root / ".git" / "index").read_bytes() == planted
    assert not (p.root / ".git" / "index.lock").exists()
    assert not list((p.root / ".git").glob("conduct-first-index-*"))
    assert op_file(p).exists() and len(install_files(p)) == 1      # a refusal retires nothing
    assert trunk_exists(p) and no_receipt(p)           # the ref is published; the index is not ours


@for_every_reader
def test_first_commit_moves_the_ref_only_by_compare_and_swap(tmp_path, monkeypatch, which):
    p = project(tmp_path, FILES, which=which)
    done = confirm(p)
    assert done.status == 201
    moves, commit = p.spy.argv("update-ref"), done.payload["setup"]["commit"]
    assert len(moves) == 1 and moves[0][-3:] == ("refs/heads/trunk", commit, "0" * len(commit))
    racing = project(tmp_path, FILES, name="racing", which=which)
    real, owner = git_setup_first._do_move_ref, []

    def owner_wins_the_race(api, op):
        owner.append(owner_ref(racing))
        return real(api, op)

    monkeypatch.setattr(git_setup_first, "_do_move_ref", owner_wins_the_race)
    assert reason(confirm(racing)) == "head_exists"
    assert text(racing, "rev-parse", "refs/heads/trunk") == owner[0]
    assert not (racing.root / ".git" / "index.lock").exists() and no_receipt(racing)
    assert len(racing.spy.argv("update-ref")) == 1


def test_first_commit_runs_no_hook_and_writes_only_the_listed_places(tmp_path):
    p = project(tmp_path, FILES)
    marker, hooks = tmp_path / "hook-ran", p.root / ".git" / "hooks"
    for name in ("reference-transaction", "post-index-change", "pre-commit", "commit-msg",
                 "post-commit"):
        (hooks / name).write_bytes(f'#!/bin/sh\necho ran > "{marker.as_posix()}"\n'.encode())
    before = snapshot(p.root / ".git")
    assert confirm(p).status == 201
    after = snapshot(p.root / ".git")
    changed = {name for name in {*before, *after} if before.get(name) != after.get(name)}
    allowed = {"refs/heads/trunk", "index"}
    assert not marker.exists() and not set(before) - set(after)
    assert all(name.startswith(("objects/", "logs/")) or name in allowed for name in changed)
    assert allowed <= changed
    for name in ("HEAD", "config", "info/exclude", *(n for n in before if n.startswith("hooks/"))):
        assert after[name] == before[name], name


def test_first_commit_never_runs_a_writing_command_without_an_owned_index_file(tmp_path):
    p = project(tmp_path, FILES)
    assert confirm(p).status == 201
    for args, keywords in p.spy.calls:
        if any(word in args for word in ("read-tree", "update-index", "write-tree")):
            assert keywords.get("index_file") is not None, args
        if "diff-index" in args and keywords.get("index_file") is None:
            assert "--no-optional-locks" in args, args       # the one read of the owner's index
        assert not {"add", "reset", "checkout-index", "checkout", "commit"} & set(args), args
        assert "-d" not in args and "--delete" not in args, args
        if "symbolic-ref" in args:
            operands = [word for word in args[args.index("symbolic-ref") + 1:]
                        if not word.startswith("-")]
            assert operands == ["HEAD"], args


def test_first_commit_refuses_a_git_dir_that_is_a_link(tmp_path):
    p = project(tmp_path, FILES)
    digest = seal(p)["paths_digest"]
    moved = tmp_path / "moved-git"
    (p.root / ".git").rename(moved)
    try:
        (p.root / ".git").symlink_to(moved, target_is_directory=True)
    except OSError as error:
        moved.rename(p.root / ".git")
        pytest.skip(str(error))
    before = snapshot(moved)
    assert reason(confirm(p, digest=digest)) == "unsafe_git_route"
    assert snapshot(moved) == before and no_receipt(p) and not op_file(p).exists()


def linked_project(tmp_path):
    """An unborn branch checked out in a linked worktree of another repository."""
    main = repository(tmp_path)
    git("config", "user.name", "Main", cwd=main)
    git("config", "user.email", "main@example.invalid", cwd=main)
    git("commit", "-q", "--allow-empty", "-m", "owner", cwd=main)
    linked = tmp_path / "linked"
    made = git("worktree", "add", "--orphan", "-b", "trunk", str(linked), cwd=main, check=False)
    if made.returncode != 0:
        pytest.skip("this git cannot make an orphan worktree")
    (linked / "a.txt").write_bytes(b"one\n")
    (main / ".git" / "worktrees" / "linked" / "index").unlink()    # `add --orphan` leaves one
    api = CommandApi(RunStore(linked), AdapterRegistry([FakeAdapter()]),
                     session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
                     clock=lambda: NOW, ids=ids(), publish_run=lambda _run: None,
                     project_git=real_reader(tmp_path),
                     identity=ProjectIdentity(PROJECT_ID, None, False, "active", None, None))
    return SimpleNamespace(root=linked, api=api, main=main)


def test_first_commit_refuses_a_linked_worktree_and_writes_nothing_outside_the_project(tmp_path):
    p = linked_project(tmp_path)
    shown = request(p, "POST", PATH, dict(step="first_commit", mode="snapshot", preview=True))
    assert shown.status == 200, shown.payload
    digest = shown.payload["setup"]["paths_digest"]
    before = snapshot(p.main / ".git")
    assert reason(confirm(p, digest=digest)) == "unsafe_git_route"
    assert snapshot(p.main / ".git") == before
    assert not (data_root(p.root) / "git" / "setup" / "first_commit.op.json").exists()


def test_a_foreign_lock_before_the_write_is_index_locked_and_nothing_is_written(tmp_path):
    p = project(tmp_path, FILES)
    digest = seal(p)["paths_digest"]
    (p.root / ".git" / "index.lock").write_bytes(b"")
    before = snapshot(p.root / ".git")
    assert reason(confirm(p, digest=digest)) == "index_locked"
    assert snapshot(p.root / ".git") == before and own_leftovers(p) == ["index.lock"]
    assert not op_file(p).exists() and no_receipt(p)


def test_a_lock_that_appears_just_before_the_copy_is_moved_is_index_locked_and_leaves_no_copy(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    real, lock_path = git_setup_first._do_take_lock, p.root / ".git" / "index.lock"

    def another_process_takes_the_lock_first(api, op):
        lock_path.write_bytes(b"")                  # after the read that said "no lock"
        return real(api, op)

    monkeypatch.setattr(git_setup_first, "_do_take_lock", another_process_takes_the_lock_first)
    assert reason(confirm(p)) == "index_locked"
    assert lock_path.read_bytes() == b"" and not list((p.root / ".git").glob("conduct-first-*"))
    assert op_file(p).exists() and len(install_files(p)) == 1     # a refusal retires nothing
    assert not trunk_exists(p) and no_receipt(p)


def test_first_commit_prepares_outside_the_store_transaction_and_writes_inside_it(tmp_path):
    p = project(tmp_path, FILES)
    held, inner = {"hash-object": [], "update-ref": []}, p.api._project_git

    def watching(args, *positional, **keywords):
        for word in held:
            if word in args:
                held[word].append(RunStore.current_thread_holds_transaction())
        return inner(args, *positional, **keywords)

    p.api._project_git = watching
    assert confirm(p).status == 201
    assert held["hash-object"] and not any(held["hash-object"])
    assert held["update-ref"] == [True]


def test_first_commit_of_five_thousand_files_batches_every_call_under_the_stdin_bound(tmp_path):
    p = project(tmp_path, {f"d{n % 50}/f{n:04d}.txt": b"0123456789" for n in range(5000)})
    started = time.perf_counter()
    answer = confirm(p)
    seconds = time.perf_counter() - started
    assert answer.status == 201, answer.payload
    assert answer.payload["setup"]["file_count"] == 5000
    assert text(p, "rev-list", "--count", "HEAD") == "1"
    sizes = [len(keywords.get("stdin") or b"") for _, keywords in p.spy.calls]
    assert max(sizes) <= 128 * 1024 and len(p.spy.argv("update-ref")) == 1
    print(f"seal and confirm of 5000 files: {seconds:.1f} s, {len(p.spy.calls)} git calls")


@pytest.mark.skipif(os.name == "nt", reason="the execute bit is read from a real chmod")
@pytest.mark.parametrize("change", ["chmod", "core.filemode"])
def test_first_commit_after_a_mode_only_change_is_paths_changed_before_any_object(
        tmp_path, change):
    p = project(tmp_path, FILES)
    if change == "core.filemode":
        (p.root / "a.txt").chmod(0o755)
    digest = seal(p)["paths_digest"]
    if change == "chmod":
        (p.root / "a.txt").chmod(0o755)
    else:
        p.git("config", "core.filemode", "false", cwd=p.root)
    before = snapshot(p.root / ".git")
    assert reason(confirm(p, digest=digest)) == "paths_changed"
    assert snapshot(p.root / ".git") == before


def damage_after_prepare(monkeypatch, damage):
    """Let the preparation finish, then change the world once before the write begins."""
    real = git_setup_first._prepare

    def prepared(api, request_):
        made = real(api, request_)
        damage(made)
        return made

    monkeypatch.setattr(git_setup_first, "_prepare", prepared)


def remove_object(p, name):
    path = p.root / ".git" / "objects" / name[:2] / name[2:]
    path.chmod(0o666)
    path.unlink()


def make_the_git_dir_a_link(p):
    moved = p.root.parent / "moved-git"
    (p.root / ".git").rename(moved)
    try:
        (p.root / ".git").symlink_to(moved, target_is_directory=True)
    except OSError as error:
        moved.rename(p.root / ".git")
        pytest.skip(str(error))


@pytest.mark.parametrize("what, refusal", [
    ("author", "paths_changed"), ("tree", "paths_changed"), ("blob", "paths_changed"),
    ("route", "unsafe_git_route")])
def test_first_commit_checks_the_frozen_terms_and_objects_at_the_entry_of_the_write(
        tmp_path, monkeypatch, what, refusal):
    p = project(tmp_path, FILES)
    damage = {
        "author": lambda made: p.git("config", "user.name", "Someone Else", cwd=p.root),
        "tree": lambda made: remove_object(p, made[1].tree),
        "blob": lambda made: remove_object(p, made[0]["files"][0]["git_oid"]),
        "route": lambda made: make_the_git_dir_a_link(p),
    }[what]
    digest = seal(p)["paths_digest"]
    damage_after_prepare(monkeypatch, damage)
    assert reason(confirm(p, digest=digest)) == refusal
    assert own_leftovers(p) == [] and no_receipt(p) and not (p.root / ".git" / "index").exists()
    assert not trunk_exists(p)


@for_every_reader
@pytest.mark.parametrize("fmt", FORMATS)
@for_both_modes
def test_the_installed_index_carries_the_marker_and_costs_one_ignored_line_per_read(
        tmp_path, mode, fmt, which):
    p = project(tmp_path, FILES, fmt=fmt, which=which)
    receipt = confirm(p, mode).payload["setup"]
    data = (p.root / ".git" / "index").read_bytes()
    marker = verify(data, fmt, entries=receipt["file_count"]).marker
    assert marker is not None and len(data) not in (65, 89)
    assert marker[1] == terms_hash(
        nonce=marker[0], mode=mode, digest_version=receipt["digest_version"],
        paths_digest=receipt["paths_digest"], target_ref=receipt["target_ref"],
        object_format=fmt, expected_tree=receipt["tree"], file_count=receipt["file_count"])
    for _ in range(2):
        for command in (("status", "--porcelain"), ("diff-index", "--cached", "--quiet", "HEAD")):
            done = p.git(*command, cwd=p.root)
            assert done.returncode == 0 and notice_lines(done) == [NOTICE], command
    (p.root / "a.txt").write_bytes(b"changed\n")
    p.git("add", "a.txt", cwd=p.root)
    assert notice_lines(p.git("status", "--porcelain", cwd=p.root)) == []


def test_a_continue_body_built_from_the_pending_description_is_accepted_by_the_parser(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest, real = seal(p)["paths_digest"], git_setup_first._do_take_lock

    def interrupted(api, op):
        real(api, op)
        raise StoreError("simulated interruption after take_lock")

    monkeypatch.setattr(git_setup_first, "_do_take_lock", interrupted)
    assert confirm(p, digest=digest).status == 500
    monkeypatch.setattr(git_setup_first, "_do_take_lock", real)
    terms = describe(p.root)["terms"]
    body = dict(step="first_commit", mode=terms["mode"], paths_digest=terms["paths_digest"],
                actor="Owner")
    assert git_setup.parse(body) == git_setup.Request(
        "confirm", actor="Owner", mode="snapshot", digest=digest)
    for key in set(terms) - {"mode", "paths_digest"}:
        with pytest.raises(ValueError):
            git_setup.parse({**body, key: terms[key]})
    assert request(p, "POST", PATH, body).status == 201 and describe(p.root) is None
