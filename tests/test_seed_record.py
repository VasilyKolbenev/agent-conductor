"""The seed record of a task's work folder, read strictly (spec 9.1.5).

The record is what the seed step writes once, `<data_root>/seeds/<task_id>/work-001.json`, and
what the materials of a run are judged against: the tree the folder was copied from, and every path
it did not copy. This reader is closed at every key and every type, because a record that reads
loosely is a base the materials check would trust; and it walks the route with the same `lstat`
rules as the other stores, because a seed reached through a link is bytes somebody else owns.
"""
from __future__ import annotations

import json
import os

import pytest

from conductor.command import seed_record
from conductor.command.seed_record import CorruptSeed, SeedRecord, read_seed
from conductor.command.store_errors import StoreError
from conductor.command.template_store import RouteNotOwned
from conductor.ownership import data_root

TASK = "task-seed-1"
SHA1 = "a" * 40
SHA256 = "b" * 64


def a_git_seed(**changes):
    record = {
        "schema_version": 1, "task_id": TASK, "work_scope": TASK, "work_item_id": "work-001",
        "source": "git", "base_commit": SHA1, "base_tree": "c" * 40, "object_format": "sha1",
        "base_ref": "refs/heads/main", "file_count": 412, "total_bytes": 3145728,
        "include_agent_instructions": False, "staging": "s-1a2b3c4d",
        "skipped": [{"path": "assets/link.md", "reason": "symlink"}],
        "agent_instructions_skipped": ["CLAUDE.md", ".claude/settings.json"],
        "warnings": [{"path": "big.bin", "code": "lfs_pointer"}],
        "staged_at": "2026-09-30T09:00:00Z"}
    return {**record, **changes}


def an_empty_seed(**changes):
    empty = {"source": "empty", "base_commit": None, "base_tree": None, "object_format": None,
             "base_ref": None, "file_count": 0, "total_bytes": 0, "skipped": [],
             "agent_instructions_skipped": [], "warnings": []}
    return a_git_seed(**{**empty, **changes})


def seed_path(root, task=TASK, item="work-001", suffix=".json"):
    return data_root(root) / "seeds" / task / f"{item}{suffix}"


def stand(root, document, **where):
    path = seed_path(root, **where)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document),
                    encoding="utf-8")
    return path


# --- what reads ----------------------------------------------------------------------------------


def test_a_task_that_has_no_seed_reads_none_with_or_without_its_folder(tmp_path):
    assert read_seed(tmp_path, TASK) is None
    seed_path(tmp_path).parent.mkdir(parents=True)
    assert read_seed(tmp_path, TASK) is None


def test_a_request_file_alone_is_not_a_seed(tmp_path):
    stand(tmp_path, {"schema_version": 1, "task_id": TASK}, suffix=".request.json")
    assert read_seed(tmp_path, TASK) is None


def test_a_git_seed_reads_back_field_for_field(tmp_path):
    stand(tmp_path, a_git_seed())
    record = read_seed(tmp_path, TASK)
    assert isinstance(record, SeedRecord) and record.as_dict() == a_git_seed()
    assert (record.source, record.base_tree, record.object_format) == ("git", "c" * 40, "sha1")


def test_a_sha256_repository_seed_reads(tmp_path):
    stand(tmp_path, a_git_seed(base_commit=SHA256, base_tree=SHA256, object_format="sha256"))
    assert read_seed(tmp_path, TASK).object_format == "sha256"


def test_an_empty_seed_has_a_null_base_and_reads(tmp_path):
    stand(tmp_path, an_empty_seed())
    record = read_seed(tmp_path, TASK)
    assert record.source == "empty" and record.base_tree is None
    assert record.as_dict() == an_empty_seed()


def test_the_paths_a_seed_did_not_copy_are_its_skips_and_the_instruction_files_it_left_out(
        tmp_path):
    stand(tmp_path, a_git_seed())
    assert read_seed(tmp_path, TASK).not_copied() == frozenset(
        {"assets/link.md", "CLAUDE.md", ".claude/settings.json"})


# --- what does not: the record is closed at every key and every type -------------------------


def a_record_without(key):
    record = a_git_seed()
    del record[key]
    return record


CORRUPT = {
    "an unknown key": a_git_seed(extra=1),
    "a missing key": a_record_without("staging"),
    "another schema version": a_git_seed(schema_version=2),
    "a boolean schema version": a_git_seed(schema_version=True),
    "a source that is neither": a_git_seed(source="clone"),
    "a git seed with no base commit": a_git_seed(base_commit=None),
    "an empty seed that names a base": an_empty_seed(base_commit=SHA1),
    "an oid that is not hex": a_git_seed(base_tree="Z" * 40),
    "an oid of no length git has": a_git_seed(base_tree="a" * 41),
    "a sha256 oid under sha1": a_git_seed(base_tree=SHA256),
    "a negative count": a_git_seed(file_count=-1),
    "a boolean count": a_git_seed(total_bytes=True),
    "a switch that is not a boolean": a_git_seed(include_agent_instructions=1),
    "a staging name off the grammar": a_git_seed(staging="s-XYZ"),
    "a skip reason off the list": a_git_seed(skipped=[{"path": "a.md", "reason": "big"}]),
    "a skip row with another key": a_git_seed(
        skipped=[{"path": "a.md", "reason": "symlink", "why": "x"}]),
    "a skipped path of two lines": a_git_seed(
        skipped=[{"path": "a\nb.md", "reason": "symlink"}]),
    "a skipped path with a NUL": a_git_seed(
        skipped=[{"path": "a\x00.md", "reason": "symlink"}]),
    "an instruction path that is not text": a_git_seed(agent_instructions_skipped=[3]),
    "a warning code off the list": a_git_seed(warnings=[{"path": "a", "code": "odd"}]),
    "a time that is not an instant": a_git_seed(staged_at="yesterday"),
    "another task in this folder": a_git_seed(task_id="task-other"),
    "another work item in this file": a_git_seed(work_item_id="work-002"),
}


@pytest.mark.parametrize("why", sorted(CORRUPT))
def test_a_record_that_is_not_exactly_the_schema_is_refused_as_corrupt(tmp_path, why):
    stand(tmp_path, CORRUPT[why])
    with pytest.raises(CorruptSeed):
        read_seed(tmp_path, TASK)


@pytest.mark.parametrize("document", [
    "", "not json", "[]", "3", "null", '{"schema_version": 1, "schema_version": 1}',
    '{"file_count": NaN}'])
def test_a_document_that_is_not_one_json_object_is_refused_as_corrupt(tmp_path, document):
    stand(tmp_path, document)
    with pytest.raises(CorruptSeed):
        read_seed(tmp_path, TASK)


def test_a_record_of_bytes_that_are_not_utf8_is_refused_as_corrupt(tmp_path):
    seed_path(tmp_path).parent.mkdir(parents=True)
    seed_path(tmp_path).write_bytes(b'{"task_id": "\xff"}')
    with pytest.raises(CorruptSeed):
        read_seed(tmp_path, TASK)


def test_a_corrupt_seed_is_a_store_fault_and_never_a_missing_one(tmp_path):
    assert issubclass(CorruptSeed, StoreError)
    stand(tmp_path, "{}")
    with pytest.raises(StoreError):
        read_seed(tmp_path, TASK)


@pytest.mark.parametrize("task", ["../escape", "a/b", "", "x" * 300, ".hidden"])
def test_a_task_id_the_store_cannot_address_is_refused_before_a_path_is_built(tmp_path, task):
    with pytest.raises(StoreError):
        read_seed(tmp_path, task)


def test_a_work_item_id_off_the_id_grammar_is_refused(tmp_path):
    with pytest.raises(StoreError):
        read_seed(tmp_path, TASK, "../work-001")


# --- what the route may be -----------------------------------------------------------------------


def test_a_seed_record_that_is_a_directory_is_not_a_route_this_store_owns(tmp_path):
    seed_path(tmp_path).mkdir(parents=True)
    with pytest.raises(RouteNotOwned):
        read_seed(tmp_path, TASK)


def test_a_seed_record_with_a_second_name_is_not_a_route_this_store_owns(tmp_path):
    path = stand(tmp_path, a_git_seed())
    os.link(path, path.with_name("elsewhere.json"))
    with pytest.raises(RouteNotOwned):
        read_seed(tmp_path, TASK)


def test_a_seed_record_that_is_a_symbolic_link_is_not_a_route_this_store_owns(tmp_path):
    real = tmp_path / "real.json"
    real.write_text(json.dumps(a_git_seed()), encoding="utf-8")
    path = seed_path(tmp_path)
    path.parent.mkdir(parents=True)
    try:
        os.symlink(real, path)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symbolic links")
    with pytest.raises(RouteNotOwned):
        read_seed(tmp_path, TASK)


def test_a_seed_folder_that_is_a_symbolic_link_is_not_a_route_this_store_owns(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = seed_path(tmp_path).parent
    folder.parent.mkdir(parents=True)
    try:
        os.symlink(outside, folder, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symbolic links")
    with pytest.raises(RouteNotOwned):
        read_seed(tmp_path, TASK)


def test_the_module_names_the_work_item_every_task_has():
    assert seed_record.WORK_ITEM_ID == "work-001"
