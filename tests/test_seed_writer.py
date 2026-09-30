"""The writing half of the seed record, the request a view process leaves, and the state of a seed.

The record is written once (9.1.5): exclusively and all-or-nothing, so two requests racing for one
task cannot both believe they made it, and a reader never sees half of it. A server in `view` mode
starts no git, so it leaves a request instead (9.1.6): a small closed record of the conditions the
owner chose, read as strictly as the record. The state of a seed is not stored: it is read off the
disk layout, the staging folder first, then the task's folder (9.1.4).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from conductor.command import seed_record
from conductor.command.path_admission import WindowsPathError
from conductor.command.seed_record import (
    CorruptSeed, SeedExists, SeedRecord, SeedRecordTooLarge, SeedRequest, Skip, read_request,
    read_seed, seed_state, write_request, write_seed)
from conductor.command.template_store import RouteNotOwned
from conductor.ownership import data_root
from tests.test_seed_record import TASK, a_git_seed, an_empty_seed, seed_path, stand

AT = "2026-09-30T10:00:00Z"
ITEM = "work-001"


def record(**changes):
    return SeedRecord.from_dict(a_git_seed(**changes))


def request(**changes):
    return SeedRequest(**{"task_id": TASK, "work_item_id": ITEM,
                          "include_agent_instructions": False, "requested_at": AT, **changes})


def files_under(root):
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*")
                  if path.is_file())


# --- the record ----------------------------------------------------------------------------


def test_a_written_record_reads_back_equal_at_the_place_the_spec_names(tmp_path):
    one = record()
    write_seed(tmp_path, one)
    assert read_seed(tmp_path, TASK) == one
    assert seed_path(tmp_path).is_file()
    assert files_under(data_root(tmp_path)) == [f"seeds/{TASK}/work-001.json"]


def test_an_empty_seed_is_written_and_read_the_same_way(tmp_path):
    empty = SeedRecord.from_dict(an_empty_seed())
    write_seed(tmp_path, empty)
    assert read_seed(tmp_path, TASK) == empty


def test_the_stored_bytes_are_one_line_of_ascii_json_in_the_order_of_the_spec(tmp_path):
    write_seed(tmp_path, record(skipped=[{"path": "café/中.md", "reason": "symlink"}]))
    raw = seed_path(tmp_path).read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1 and raw.isascii()
    assert list(json.loads(raw)) == list(a_git_seed())
    assert read_seed(tmp_path, TASK).skipped == (Skip("café/中.md", "symlink"),)


def test_a_second_write_for_the_same_task_is_refused_and_changes_nothing(tmp_path):
    write_seed(tmp_path, record())
    before = seed_path(tmp_path).read_bytes()
    with pytest.raises(SeedExists):
        write_seed(tmp_path, record())
    with pytest.raises(SeedExists):
        write_seed(tmp_path, record(file_count=1))
    assert seed_path(tmp_path).read_bytes() == before


def test_two_work_items_and_two_tasks_do_not_meet(tmp_path):
    write_seed(tmp_path, record())
    write_seed(tmp_path, record(work_item_id="work-002"))
    write_seed(tmp_path, record(task_id="task-other", work_scope="task-other"))
    assert files_under(data_root(tmp_path)) == [
        "seeds/task-other/work-001.json", f"seeds/{TASK}/work-001.json",
        f"seeds/{TASK}/work-002.json"]


def test_writers_racing_for_one_task_leave_exactly_one_record_and_no_leftover(tmp_path):
    outcomes, gate = [], threading.Barrier(8)

    def race(number):
        gate.wait()
        try:
            write_seed(tmp_path, record(file_count=number))
            outcomes.append("won")
        except SeedExists:
            outcomes.append("lost")

    threads = [threading.Thread(target=race, args=(number,)) for number in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert sorted(outcomes) == ["lost"] * 7 + ["won"]
    assert files_under(data_root(tmp_path)) == [f"seeds/{TASK}/work-001.json"]
    assert read_seed(tmp_path, TASK).file_count in range(8)


def test_no_temporary_file_is_left_after_a_write_or_a_refused_write(tmp_path):
    write_seed(tmp_path, record())
    with pytest.raises(SeedExists):
        write_seed(tmp_path, record())
    assert [name for name in os.listdir(seed_path(tmp_path).parent)] == ["work-001.json"]


def test_a_record_its_own_reader_could_not_hold_is_refused_before_it_is_written(tmp_path):
    many = [f"docs/{number:05d}/{'x' * 200}.md" for number in range(6000)]
    big = record(agent_instructions_skipped=many)
    with pytest.raises(SeedRecordTooLarge):
        write_seed(tmp_path, big)
    assert not (data_root(tmp_path) / "seeds").exists()


def test_a_large_record_the_reader_admits_is_written_and_read(tmp_path):
    many = [f"docs/{number:05d}/{'x' * 100}.md" for number in range(4000)]
    write_seed(tmp_path, record(agent_instructions_skipped=many))
    assert len(read_seed(tmp_path, TASK).agent_instructions_skipped) == 4000


def test_a_seed_folder_that_is_a_link_is_not_written_through(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "project"
    root.mkdir()
    data_root(root).mkdir(parents=True)
    try:
        os.symlink(outside, data_root(root) / "seeds", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a link")
    with pytest.raises(RouteNotOwned):
        write_seed(root, record())
    assert list(outside.iterdir()) == []


def test_a_record_whose_path_could_not_be_made_on_windows_is_refused_before_a_byte(
        tmp_path, monkeypatch):
    def too_long(path, label):
        raise WindowsPathError(f"{label} exceeds the Windows path budget")
    monkeypatch.setattr(seed_record, "admit_file", too_long)
    with pytest.raises(WindowsPathError):
        write_seed(tmp_path, record())
    assert not (data_root(tmp_path) / "seeds").exists()


def test_a_value_that_is_not_a_seed_record_is_not_written(tmp_path):
    with pytest.raises(TypeError):
        write_seed(tmp_path, a_git_seed())
    assert not (data_root(tmp_path) / "seeds").exists()


# --- the request a view process leaves -----------------------------------------------------


def test_a_request_reads_back_equal_and_is_not_a_seed(tmp_path):
    asked = request(include_agent_instructions=True)
    write_request(tmp_path, asked)
    assert read_request(tmp_path, TASK) == asked
    assert read_seed(tmp_path, TASK) is None
    assert files_under(data_root(tmp_path)) == [f"seeds/{TASK}/work-001.request.json"]


def test_a_task_with_no_request_reads_none(tmp_path):
    assert read_request(tmp_path, TASK) is None


def test_the_stored_request_is_exactly_the_five_keys_of_the_spec(tmp_path):
    write_request(tmp_path, request())
    stored = json.loads((seed_path(tmp_path, suffix=".request.json")).read_bytes())
    assert stored == {"schema_version": 1, "task_id": TASK, "work_item_id": ITEM,
                      "include_agent_instructions": False, "requested_at": AT}
    assert list(stored) == ["schema_version", "task_id", "work_item_id",
                            "include_agent_instructions", "requested_at"]


def test_a_request_is_written_once_and_a_second_is_refused_and_changes_nothing(tmp_path):
    write_request(tmp_path, request())
    before = seed_path(tmp_path, suffix=".request.json").read_bytes()
    with pytest.raises(SeedExists):
        write_request(tmp_path, request(include_agent_instructions=True))
    assert seed_path(tmp_path, suffix=".request.json").read_bytes() == before


@pytest.mark.parametrize("document", [
    {"schema_version": 1, "task_id": TASK, "work_item_id": ITEM, "requested_at": AT},
    {"schema_version": 1, "task_id": TASK, "work_item_id": ITEM, "requested_at": AT,
     "include_agent_instructions": False, "extra": 1},
    {"schema_version": 2, "task_id": TASK, "work_item_id": ITEM, "requested_at": AT,
     "include_agent_instructions": False},
    {"schema_version": 1, "task_id": TASK, "work_item_id": ITEM, "requested_at": "yesterday",
     "include_agent_instructions": False},
    {"schema_version": 1, "task_id": TASK, "work_item_id": ITEM, "requested_at": AT,
     "include_agent_instructions": "no"},
    {"schema_version": 1, "task_id": "other", "work_item_id": ITEM, "requested_at": AT,
     "include_agent_instructions": False},
    {"schema_version": 1, "task_id": TASK, "work_item_id": "work-009", "requested_at": AT,
     "include_agent_instructions": False},
    [], "text", 7])
def test_a_request_that_is_not_exactly_the_schema_and_its_place_is_corrupt(tmp_path, document):
    stand(tmp_path, document, suffix=".request.json")
    with pytest.raises(CorruptSeed):
        read_request(tmp_path, TASK)


def test_a_request_that_is_unreadable_or_has_a_key_twice_is_corrupt(tmp_path):
    stand(tmp_path, "{not json", suffix=".request.json")
    with pytest.raises(CorruptSeed):
        read_request(tmp_path, TASK)
    stand(tmp_path, '{"schema_version": 1, "schema_version": 1}', suffix=".request.json")
    with pytest.raises(CorruptSeed):
        read_request(tmp_path, TASK)


def test_a_request_file_that_is_a_link_is_not_read(tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}", encoding="utf-8")
    path = seed_path(tmp_path, suffix=".request.json")
    path.parent.mkdir(parents=True)
    try:
        os.symlink(outside, path)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a link")
    with pytest.raises(RouteNotOwned):
        read_request(tmp_path, TASK)


# --- the state of a seed: read off the disk layout -----------------------------------------


def layout(root, one):
    return (Path(root) / ".conduct-seed" / one.staging,
            Path(root) / "work" / "_tasks" / one.work_scope / one.work_item_id)


def test_a_seed_with_its_staging_folder_standing_is_staged(tmp_path):
    one = record()
    layout(tmp_path, one)[0].mkdir(parents=True)
    assert seed_state(tmp_path, one) == "staged"


def test_a_seed_whose_staging_moved_and_whose_task_folder_stands_is_seeded(tmp_path):
    one = record()
    layout(tmp_path, one)[1].mkdir(parents=True)
    assert seed_state(tmp_path, one) == "seeded"


def test_a_seed_with_neither_folder_is_lost(tmp_path):
    assert seed_state(tmp_path, record()) == "seed_lost"


def test_both_folders_standing_reads_staged_because_the_move_is_not_done(tmp_path):
    one = record()
    for folder in layout(tmp_path, one):
        folder.mkdir(parents=True)
    assert seed_state(tmp_path, one) == "staged"


def test_a_file_or_a_link_where_a_folder_belongs_is_not_a_folder(tmp_path):
    one = record()
    staging, task = layout(tmp_path, one)
    staging.parent.mkdir(parents=True)
    staging.write_bytes(b"not a folder")
    task.parent.mkdir(parents=True)
    task.write_bytes(b"not a folder either")
    assert seed_state(tmp_path, one) == "seed_lost"
    staging.unlink()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, staging, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a link")
    assert seed_state(tmp_path, one) == "seed_lost"


def test_an_empty_seed_is_judged_by_the_same_layout(tmp_path):
    one = SeedRecord.from_dict(an_empty_seed())
    layout(tmp_path, one)[0].mkdir(parents=True)
    assert seed_state(tmp_path, one) == "staged"
