"""The closed `first_commit_pending` read of `GET /command/project/git` (spec 9.8, ruling OD-9).

A page that was closed in the middle of the first commit finds the stored terms again here. The
description is a READ and never a permission: these tests judge what it says for every stored
stage, that a record it cannot prove is `damaged` and never a crash, and that reading it writes
nothing, starts nothing, and is not even attempted where the answer is `null`. The ops are made
by `records.start`; the confirm that will write them is a later task of this lane.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

from conductor import ownership_transition
from conductor.command import git_setup_first_records as records
from conductor.command.contracts import canonical_json
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE
from conductor.command.git_setup_first_resume import LOCKED, PREPARED, REF_MOVED
from conductor.command.project_git import GitReadFailed
from tests.git_repo_helpers import Script, git, needs_git, real_reader, said
from tests.test_command_materials_routes import NoGit, Project
from tests.test_git_setup_first_records import (
    COMMIT, DAMAGE, DATA, DIGEST, NOW, TREE, an_op, install_file, op_file, plant, setup_dir)
from tests.test_project_git_state import read
from tests.test_seed_routes import Folder

TERMS = {"mode": "snapshot", "paths_digest": DIGEST, "digest_version": 2,
         "requested_by": "Owner", "file_count": 2, "target_ref": "refs/heads/trunk",
         "author": {"name": "First Author", "email": "first@example.invalid"}}
EMPTY_TERMS = {**TERMS, "mode": "empty", "paths_digest": None, "file_count": 0}
DAMAGED = {"state": "damaged"}
#: The first 32 hex of this digest differ from its last 32: the file is named by the first.
MESSAGE = "sha256:" + "0123456789abcdef" * 2 + "fedcba9876543210" * 2
MESSAGE_PATH = re.compile(r"conductor(?:\.v3)?/git/msg-first-[0-9a-f]{32}\.txt")


def pending():
    """The module under test, imported late: until it exists each test fails by itself."""
    from conductor.command import git_setup_first_pending
    return git_setup_first_pending


def op_at(root, stage, **changes):
    """Start an op and walk it to `stage` the way the driver will."""
    op = records.start(root, an_op(**changes), DATA)
    for step in {PREPARED: (), LOCKED: (LOCKED,), REF_MOVED: (LOCKED, REF_MOVED)}[stage]:
        op = records.advance(root, op, step)
    return op


def waiting(root, **changes):
    """An op that waits for the owner's signature: no commit yet, the signing flag frozen."""
    fields = dict(stage=AWAITING_SIGNATURE, commit=None, signing=True, message_sha256=MESSAGE)
    return records.start(root, an_op(**{**fields, **changes}), DATA)


def stamped(folder):
    """Every entry under `folder`: its kind, the bytes of a file, and its modification time."""
    found = {}
    for path in sorted(folder.rglob("*")):
        found[path.relative_to(folder).as_posix()] = (
            path.is_dir(), None if path.is_dir() else path.read_bytes(), path.lstat().st_mtime_ns)
    return found


# --- null: nothing to continue ---------------------------------------------------------------


def test_pending_is_null_without_an_op_and_when_a_receipt_stands(tmp_path):
    assert pending().describe(tmp_path) is None
    op = op_at(tmp_path, REF_MOVED)
    assert pending().describe(tmp_path) is not None
    records.write_receipt(tmp_path, records.receipt_of(op, NOW))
    assert pending().describe(tmp_path) is None          # the receipt is authoritative
    records.retire(tmp_path, op)
    assert pending().describe(tmp_path) is None          # and so it is once the op is gone


def test_pending_ignores_a_receipt_it_cannot_read_when_no_op_stands(tmp_path):
    setup_dir(tmp_path).mkdir(parents=True)
    (setup_dir(tmp_path) / records.RECEIPT_NAME).write_bytes(b"torn\n")
    assert pending().describe(tmp_path) is None          # nothing is pending, so nothing to mend


# --- unfinished: the stored terms and nothing else -------------------------------------------


@pytest.mark.parametrize("mode", ["snapshot", "empty"])
@pytest.mark.parametrize("stage", [PREPARED, LOCKED, REF_MOVED])
def test_pending_names_the_stored_terms_of_an_unfinished_op_and_nothing_else(
        tmp_path, stage, mode):
    changes = {} if mode == "snapshot" else dict(mode="empty", paths_digest=None, file_count=0)
    op = op_at(tmp_path, stage, **changes)
    answer = pending().describe(tmp_path)
    assert answer == {"state": "unfinished", "terms": TERMS if mode == "snapshot" else EMPTY_TERMS}
    assert set(answer) == {"state", "terms"} and set(answer["terms"]) == set(TERMS)
    text = json.dumps(answer)
    for private in (op.nonce, op.expected_tree, op.commit, op.install_sha256, op.message_sha256,
                    PREPARED, LOCKED, REF_MOVED):
        assert private not in text


def test_pending_is_the_same_description_at_every_unfinished_stage(tmp_path):
    op = records.start(tmp_path, an_op(), DATA)
    seen = [pending().describe(tmp_path)]
    for stage in (LOCKED, REF_MOVED):
        op = records.advance(tmp_path, op, stage)
        seen.append(pending().describe(tmp_path))
    assert seen[0] == {"state": "unfinished", "terms": TERMS} and seen[0] == seen[1] == seen[2]


def test_pending_hands_out_copies_so_a_caller_cannot_change_what_the_next_read_says(tmp_path):
    op_at(tmp_path, PREPARED)
    first = pending().describe(tmp_path)
    first["terms"]["author"]["name"] = "Someone Else"
    first["terms"]["mode"] = "empty"
    assert pending().describe(tmp_path) == {"state": "unfinished", "terms": TERMS}


# --- a wait for the owner's signature --------------------------------------------------------


def test_pending_of_a_signature_wait_carries_the_three_facts_of_the_refusal(tmp_path):
    waiting(tmp_path)
    answer = pending().describe(tmp_path)
    assert answer == {
        "state": "awaiting_signature", "terms": TERMS,
        "signing": {"tree": TREE, "target_ref": "refs/heads/trunk",
                    "message_path": "conductor/git/msg-first-0123456789abcdef0123456789abcdef.txt"}}
    assert set(answer) == {"state", "terms", "signing"}
    assert set(answer["signing"]) == {"tree", "target_ref", "message_path"}
    assert MESSAGE_PATH.fullmatch(answer["signing"]["message_path"])
    assert COMMIT not in json.dumps(answer)


def test_pending_names_the_message_file_inside_the_namespace_the_project_is_in(tmp_path):
    legacy, active = tmp_path / "legacy", tmp_path / "active"
    (active / "conductor").mkdir(parents=True)
    legacy.mkdir()
    ownership_transition.activate(active, legacy_writers_stopped=True)
    for root, namespace in ((legacy, "conductor"), (active, "conductor.v3")):
        waiting(root)
        path = pending().describe(root)["signing"]["message_path"]
        assert path == f"{namespace}/git/msg-first-0123456789abcdef0123456789abcdef.txt"
        assert MESSAGE_PATH.fullmatch(path)


def test_pending_of_a_signed_op_whose_ref_moved_is_unfinished_without_signing_facts(tmp_path):
    op = waiting(tmp_path)
    records.advance(tmp_path, op, REF_MOVED, commit=COMMIT)
    assert pending().describe(tmp_path) == {"state": "unfinished", "terms": TERMS}


# --- damaged: closed, never a crash, nothing touched -----------------------------------------


@pytest.mark.parametrize("case", DAMAGE)
def test_pending_of_an_op_with_any_damaged_field_is_damaged(tmp_path, case):
    plant(tmp_path, DAMAGE[case])
    before = stamped(tmp_path)
    assert pending().describe(tmp_path) == DAMAGED
    assert stamped(tmp_path) == before


def spell(row, spelling):
    """The bytes of a record `row`: a lone surrogate as a JSON escape, or as raw bytes that the
    decoder reads back with `surrogatepass`."""
    if spelling == "raw bytes":
        return json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8", "surrogatepass")
    return json.dumps(row, sort_keys=True).encode("ascii")


@pytest.mark.parametrize("spelling", ["a json escape", "raw bytes"])
@pytest.mark.parametrize("where", ["name", "email", "target_ref"])
def test_pending_of_an_op_with_a_lone_surrogate_is_damaged_and_its_answer_encodes(
        tmp_path, where, spelling):
    records.start(tmp_path, an_op(), DATA)
    row = json.loads(op_file(tmp_path).read_bytes())
    if where == "target_ref":
        row["target_ref"] = "refs/heads/\ud800"
    else:
        row["author"][where] = "\ud800"
    op_file(tmp_path).write_bytes(spell(row, spelling))
    answer = pending().describe(tmp_path)
    canonical_json({"first_commit_pending": answer}).encode("utf-8")   # the server's own step
    assert answer == DAMAGED


BROKEN = {
    "a duplicate key": lambda good: good.replace(
        b'"stage":"prepared"', b'"stage":"prepared","stage":"prepared"'),
    "a stage outside the four": lambda good: good.replace(
        b'"stage":"prepared"', b'"stage":"finished"'),
    "a list": lambda good: b"[]\n",
    "text that is not JSON": lambda good: b"not json\n",
    "bytes that are not UTF-8": lambda good: b"\xff\xfe\n",
    "an empty file": lambda good: b"",
    "a record over its limit": lambda good: good + b" " * records.OP_LIMIT,
    "brackets nested far deeper than any op": lambda good: b"[" * 8000 + b"]" * 8000,
}


@pytest.mark.parametrize("what", BROKEN)
def test_pending_of_a_record_that_is_not_one_op_is_damaged(tmp_path, what):
    records.start(tmp_path, an_op(), DATA)
    op_file(tmp_path).write_bytes(BROKEN[what](op_file(tmp_path).read_bytes()))
    before = stamped(tmp_path)
    assert pending().describe(tmp_path) == DAMAGED
    assert stamped(tmp_path) == before


def test_pending_of_an_op_whose_install_bytes_are_other_or_gone_is_damaged(tmp_path):
    records.start(tmp_path, an_op(), DATA)
    install_file(tmp_path).write_bytes(DATA[:-1] + b"x")
    assert pending().describe(tmp_path) == DAMAGED
    install_file(tmp_path).unlink()
    assert pending().describe(tmp_path) == DAMAGED


def test_pending_of_a_record_that_is_a_directory_or_a_link_is_damaged(tmp_path):
    records.start(tmp_path, an_op(), DATA)
    op_file(tmp_path).unlink()
    op_file(tmp_path).mkdir()
    assert pending().describe(tmp_path) == DAMAGED
    op_file(tmp_path).rmdir()
    try:
        op_file(tmp_path).symlink_to(install_file(tmp_path))
    except (OSError, NotImplementedError) as error:
        pytest.skip(str(error))
    assert pending().describe(tmp_path) == DAMAGED


def test_pending_of_a_wait_for_a_signature_that_was_never_required_is_damaged(tmp_path):
    waiting(tmp_path, signing=False)
    assert pending().describe(tmp_path) == DAMAGED


def test_pending_of_an_op_beside_a_receipt_it_cannot_read_is_damaged(tmp_path):
    op_at(tmp_path, REF_MOVED)
    (setup_dir(tmp_path) / records.RECEIPT_NAME).write_bytes(b"torn\n")
    assert pending().describe(tmp_path) == DAMAGED


def test_pending_of_a_project_whose_ownership_cannot_be_read_is_damaged(tmp_path):
    (tmp_path / "conductor.v3").mkdir()           # an owned namespace with no history behind it
    assert pending().describe(tmp_path) == DAMAGED


# --- a read: nothing written, nothing started ------------------------------------------------


def torn(root):
    op_at(root, PREPARED)
    op_file(root).write_bytes(b"torn\n")


MAKERS = {"no op": lambda root: None, "an unfinished op": lambda root: op_at(root, LOCKED),
          "a signature wait": waiting, "a torn record": torn}


@pytest.mark.parametrize("what", MAKERS)
def test_reading_the_pending_description_writes_nothing_and_starts_no_process(
        tmp_path, monkeypatch, what):
    MAKERS[what](tmp_path)
    before = stamped(tmp_path)

    def refuse(*args, **keywords):
        raise AssertionError("a process was started by a read")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    pending().describe(tmp_path)
    assert stamped(tmp_path) == before


def test_the_witnesses_of_the_read_notice_what_they_judge(tmp_path, monkeypatch):
    stored = tmp_path / "file"
    stored.write_bytes(b"same")
    before = stamped(tmp_path)
    stored.write_bytes(b"same")
    os.utime(stored, ns=(1, stored.stat().st_mtime_ns + 5_000_000_000))
    assert stamped(tmp_path) != before                  # equal bytes, a later time: still seen

    def refuse(*args, **keywords):
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    with pytest.raises(AssertionError, match="started"):
        subprocess.Popen(["never"])


# --- through the route -----------------------------------------------------------------------


def a_project(tmp_path, where):
    """A project whose Git state is `unborn` (a repository with no commit) or `repo`."""
    if where == "repo":
        return Project(tmp_path)
    project = Folder(tmp_path)
    git("init", "-q", cwd=project.root)
    return project


@needs_git
@pytest.mark.parametrize("where", ["unborn", "repo"])
def test_the_get_carries_the_description_in_an_unborn_and_in_a_born_repository(tmp_path, where):
    project = a_project(tmp_path, where)
    baseline = read(project)
    assert baseline["state"] == where and baseline["first_commit_pending"] is None
    op_at(project.root, REF_MOVED)
    facts = read(project)
    assert facts["first_commit_pending"] == {"state": "unfinished", "terms": TERMS}
    assert {**facts, "first_commit_pending": None} == baseline


@needs_git
def test_the_get_still_answers_200_for_a_signature_wait_and_for_a_damaged_record(tmp_path):
    project = a_project(tmp_path, "unborn")
    baseline = read(project)
    waiting(project.root)
    waited = read(project)["first_commit_pending"]
    assert waited["state"] == "awaiting_signature" and waited["signing"]["tree"] == TREE
    op_file(project.root).write_bytes(b"not json\n")
    facts = read(project)                                # `read` itself asserts the 200
    assert facts["first_commit_pending"] == DAMAGED
    assert {**facts, "first_commit_pending": None} == baseline


@needs_git
def test_the_get_of_a_record_whose_text_is_not_utf8_is_damaged_and_still_encodes_for_the_wire(
        tmp_path):
    project = a_project(tmp_path, "unborn")
    plant(project.root, lambda body: body.update(author={**body["author"], "name": "\ud800"}))
    facts = read(project)
    canonical_json({"git": facts}).encode("utf-8")      # the step server.py takes for every GET
    assert facts["first_commit_pending"] == DAMAGED


class Spy:
    """A Git reader that remembers every argv it was asked."""

    def __init__(self, reader):
        self.reader, self.calls = reader, []

    def __call__(self, args, *positional, **keywords):
        self.calls.append(tuple(args))
        return self.reader(args, *positional, **keywords)


@needs_git
def test_reading_the_pending_description_writes_nothing_and_starts_no_git_process_for_it(
        tmp_path):
    spy = Spy(real_reader(tmp_path))
    project = Folder(tmp_path, reader=spy)
    git("init", "-q", cwd=project.root)
    read(project)
    without_an_op = list(spy.calls)
    spy.calls.clear()
    op_at(project.root, REF_MOVED)
    before = stamped(project.root)
    assert read(project)["first_commit_pending"]["state"] == "unfinished"
    assert without_an_op and spy.calls == without_an_op
    assert stamped(project.root) == before


@pytest.fixture
def asked(monkeypatch):
    """The roots the description was asked for; it answers `None` and records the question."""
    roots = []

    def record(root):
        roots.append(root)
        return None

    monkeypatch.setattr(pending(), "describe", record)
    return roots


@pytest.mark.parametrize("entry", ["absent", "directory"])
def test_pending_is_null_in_view_mode_and_is_not_even_asked_for(tmp_path, asked, entry):
    project = Folder(tmp_path, mode="view", reader=NoGit())
    if entry == "directory":
        (project.root / ".git").mkdir()
    op_at(project.root, PREPARED)
    assert read(project)["first_commit_pending"] is None
    assert project.reader.asked == 0 and asked == []


def raises_unavailable(*args, **keywords):
    raise GitReadFailed("tool_unavailable", reason="missing")


def scripted(state, root):
    """The reader that makes the wizard's Git read answer `state` (`None`: no reader at all)."""
    return {
        "unavailable": None,
        "tool_unavailable": raises_unavailable,
        "not_repo_root": Script(said(str(root.parent).encode() + b"\n")),
        "unsupported": Script(said(str(root).encode() + b"\n"),
                              said(b"work/result.txt\0instructions/step.md\0")),
        "unsafe_directory": Script(said(b"fatal: detected dubious ownership\n", code=128)),
    }[state]


@pytest.mark.parametrize("state", ["not_git", "unavailable", "tool_unavailable", "not_repo_root",
                                   "unsupported", "unsafe_directory"])
def test_pending_is_null_in_every_state_without_a_repository_and_is_not_even_asked_for(
        tmp_path, asked, state):
    project = Folder(tmp_path, reader=NoGit())
    if state != "not_git":
        (project.root / ".git").mkdir()
        project.api._project_git = scripted(state, project.root)
    op_at(project.root, PREPARED)
    facts = read(project)
    assert facts["first_commit_pending"] is None and asked == []
    assert facts["state"] == ("unavailable" if state == "tool_unavailable" else state)


@needs_git
def test_the_seam_that_keeps_the_description_out_of_those_states_is_on_the_path_of_the_others(
        tmp_path, asked):
    project = a_project(tmp_path, "unborn")
    assert read(project)["first_commit_pending"] is None
    assert asked == [project.root]
