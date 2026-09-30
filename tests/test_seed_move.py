"""The move of a staged seed under `work/`: one rename, under the root gate (spec 9.1.4).

A seed is prepared in `<root>/.conduct-seed/s-<8 hex>/` and moved, by one `rename`, to
`work/_tasks/<scope>/<item>` while the root's turn is held, so no other dispatch sees a change
outside its own subtree. The target must be absent; an empty folder there is removed first; anything
else is `work_not_empty`. This file judges the move itself, then the door that attempts it (201
`seeded`, 202 `staged` while another turn holds the gate, 409 `work_not_empty`), then the driver
that owes it before the first action of a run (`seed_blocked`, and the request a view server left).
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from conductor.command import seed_stage
from conductor.command.adapters.harness_workspace import WorkspaceBusy, root_turn
from conductor.command.adapters.process import ProcessRunner
from conductor.command.product_names import SEED_STAGING_DIR
from conductor.command.seed_plan import SeedRefusal
from conductor.command.seed_record import read_seed, seed_state
from conductor.command.template_store import RouteNotOwned
from tests.git_repo_helpers import needs_git
from tests.test_command_materials_routes import TASK, NoGit, Project
from tests.test_command_project_doors import code_of
from tests.test_seed_routes import preparation, reason_of, seed, serving

SCOPE, ITEM, AT = "scope-move-1", "work-001", "2026-09-30T12:00:00Z"


def staged(root, files=None):
    """An empty seed's staging folder, holding `files` (path to bytes), and its record."""
    record = seed_stage.stage_empty(root, task_id="task-move-1", work_scope=SCOPE,
                                    work_item_id=ITEM, staged_at=AT)
    folder = Path(root) / SEED_STAGING_DIR / record.staging
    for relative, data in (files or {"a.txt": b"alpha\n"}).items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_bytes(data)
    return record


@contextmanager
def gate_held(root):
    """The root's turn, held by another thread for the length of the block."""
    held, release = threading.Event(), threading.Event()

    def hold():
        with root_turn(root):
            held.set()
            release.wait(30)

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    assert held.wait(10)
    try:
        yield
    finally:
        release.set()
        thread.join(10)


def target_of(root):
    return Path(root) / "work" / "_tasks" / SCOPE / ITEM


def tree_of(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in sorted(Path(folder).rglob("*")) if path.is_file()}


# --- the move ------------------------------------------------------------------------------


def test_seed_stages_outside_work_and_moves_into_the_task_folder_in_one_rename(
        tmp_path, monkeypatch):
    record = staged(tmp_path, {"a.txt": b"alpha\n", "d/e/b.bin": bytes(range(9))})
    staging = tmp_path / SEED_STAGING_DIR / record.staging
    assert not (tmp_path / "work").exists(), "nothing is written under work/ while staging"
    renamed = []
    real = os.rename
    monkeypatch.setattr(seed_stage.os, "rename",
                        lambda source, target: (renamed.append((Path(source), Path(target))),
                                                real(source, target))[1])
    seed_stage.move_staged(tmp_path, record)
    assert renamed == [(staging.resolve(), target_of(tmp_path).resolve())]
    assert tree_of(target_of(tmp_path)) == {"a.txt": b"alpha\n", "d/e/b.bin": bytes(range(9))}
    assert not staging.exists() and not (tmp_path / SEED_STAGING_DIR).exists()
    assert seed_state(tmp_path, record) == "seeded"


def test_the_move_is_made_under_the_root_turn_and_the_projects_write_guard_in_that_order(
        tmp_path, monkeypatch):
    record = staged(tmp_path)
    events = []
    real_turn = seed_stage.root_turn

    class Spy:
        def __init__(self, name, inner):
            self.name, self.inner = name, inner

        def __enter__(self):
            events.append(f"enter {self.name}")
            return self.inner.__enter__()

        def __exit__(self, *exc):
            events.append(f"leave {self.name}")
            return self.inner.__exit__(*exc)

    monkeypatch.setattr(seed_stage, "root_turn",
                        lambda root, wait=None: Spy("turn", real_turn(root, wait=wait)))
    real_guard = ProcessRunner.project_write_guard
    monkeypatch.setattr(ProcessRunner, "project_write_guard", classmethod(
        lambda cls, root: Spy("guard", real_guard(root))))
    real_rename = os.rename
    monkeypatch.setattr(seed_stage.os, "rename",
                        lambda a, b: (events.append("rename"), real_rename(a, b))[1])
    seed_stage.move_staged(tmp_path, record)
    assert events == ["enter turn", "enter guard", "rename", "leave guard", "leave turn"]


def test_an_empty_task_folder_is_removed_and_the_seed_takes_its_place(tmp_path):
    record = staged(tmp_path)
    target_of(tmp_path).mkdir(parents=True)
    seed_stage.move_staged(tmp_path, record)
    assert tree_of(target_of(tmp_path)) == {"a.txt": b"alpha\n"}


@pytest.mark.parametrize("what", ["file", "folder holding a file", "folder holding a folder"])
def test_the_move_refuses_a_task_folder_that_holds_anything_and_changes_nothing(tmp_path, what):
    record = staged(tmp_path)
    target = target_of(tmp_path)
    target.parent.mkdir(parents=True)
    if what == "file":
        target.write_bytes(b"already here")
    else:
        (target / "inner").mkdir(parents=True)
        if what == "folder holding a file":
            (target / "inner" / "x.txt").write_bytes(b"x")
    before = sorted(Path(tmp_path).rglob("*"))
    with pytest.raises(SeedRefusal) as refused:
        seed_stage.move_staged(tmp_path, record)
    assert refused.value.reason == "work_not_empty"
    assert sorted(Path(tmp_path).rglob("*")) == before
    assert (tmp_path / SEED_STAGING_DIR / record.staging / "a.txt").exists()


def test_a_move_while_another_turn_holds_the_root_waits_then_says_busy_and_keeps_the_staging(
        tmp_path):
    record = staged(tmp_path)
    with gate_held(tmp_path):
        started = time.monotonic()
        with pytest.raises(WorkspaceBusy):
            seed_stage.move_staged(tmp_path, record, wait=0.3)
        assert 0.25 <= time.monotonic() - started < 10
    assert (tmp_path / SEED_STAGING_DIR / record.staging / "a.txt").exists()
    assert not (tmp_path / "work").exists()
    seed_stage.move_staged(tmp_path, record, wait=1)
    assert seed_state(tmp_path, record) == "seeded"


def test_a_staging_that_is_gone_is_a_seed_lost_and_not_a_move_of_nothing(tmp_path):
    record = staged(tmp_path)
    seed_stage.remove_staging(tmp_path, record.staging)
    with pytest.raises(SeedRefusal) as refused:
        seed_stage.move_staged(tmp_path, record)
    assert refused.value.reason == "seed_lost" and not (tmp_path / "work").exists()


def test_a_staging_that_is_a_link_is_not_moved(tmp_path):
    record = staged(tmp_path)
    folder = tmp_path / SEED_STAGING_DIR / record.staging
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"keep")
    seed_stage.remove_staging(tmp_path, record.staging)
    (tmp_path / SEED_STAGING_DIR).mkdir()
    try:
        os.symlink(outside, folder, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a link")
    with pytest.raises(SeedRefusal) as refused:
        seed_stage.move_staged(tmp_path, record)
    assert refused.value.reason == "seed_lost" and (outside / "keep.txt").exists()
    assert not (tmp_path / "work").exists()


def test_a_work_folder_that_is_a_file_or_a_link_is_not_written_through(tmp_path):
    record = staged(tmp_path)
    (tmp_path / "work").write_bytes(b"not a folder")
    with pytest.raises(RouteNotOwned):
        seed_stage.move_staged(tmp_path, record)
    assert (tmp_path / SEED_STAGING_DIR / record.staging / "a.txt").exists()


def test_the_seed_folder_goes_with_the_last_staging_and_stays_for_a_neighbours(tmp_path):
    record = staged(tmp_path)
    other = seed_stage.stage_empty(tmp_path, task_id="task-move-2", work_scope="scope-move-2",
                                   work_item_id=ITEM, staged_at=AT)
    seed_stage.move_staged(tmp_path, record)
    assert (tmp_path / SEED_STAGING_DIR / other.staging).is_dir()
    seed_stage.move_staged(tmp_path, other)
    assert not (tmp_path / SEED_STAGING_DIR).exists()


def test_a_free_target_is_said_before_anything_is_staged_and_a_taken_one_is_refused(tmp_path):
    seed_stage.hold_target_free(tmp_path, SCOPE, ITEM)
    target_of(tmp_path).mkdir(parents=True)
    seed_stage.hold_target_free(tmp_path, SCOPE, ITEM)
    (target_of(tmp_path) / "x").write_bytes(b"x")
    with pytest.raises(SeedRefusal) as refused:
        seed_stage.hold_target_free(tmp_path, SCOPE, ITEM)
    assert refused.value.reason == "work_not_empty"
    assert not (tmp_path / SEED_STAGING_DIR).exists()


# --- the door attempts the move ------------------------------------------------------------


@needs_git
def test_a_seed_made_while_the_gate_is_free_is_moved_at_once_and_answers_201_seeded(tmp_path):
    project = Project(tmp_path)
    answer = seed(project)
    record = read_seed(project.root, TASK)
    assert answer.status == 201 and answer.payload == {**record.as_dict(), "state": "seeded"}
    work = Path(project.root) / "work" / "_tasks" / TASK / ITEM
    assert tree_of(work)["README.md"] == b"# Project\n"
    assert not (Path(project.root) / SEED_STAGING_DIR).exists()


@needs_git
def test_seed_stays_staged_while_another_task_holds_the_root_gate(tmp_path, monkeypatch):
    project = Project(tmp_path)
    monkeypatch.setattr(seed_stage, "MOVE_WAIT_SECONDS", 0.2)
    with gate_held(project.root):
        busy = seed(project)
        record = read_seed(project.root, TASK)
        assert busy.status == 202 and busy.payload["state"] == "staged"
        assert (Path(project.root) / SEED_STAGING_DIR / record.staging).is_dir()
        assert not (Path(project.root) / "work" / "_tasks").exists()
    again = seed(project)
    assert again.status == 200 and again.payload == {**record.as_dict(), "state": "seeded"}
    assert not (Path(project.root) / SEED_STAGING_DIR).exists()


@needs_git
def test_seed_refuses_a_non_empty_task_folder(tmp_path):
    project = Project(tmp_path)
    folder = Path(project.root) / "work" / "_tasks" / TASK / ITEM
    folder.mkdir(parents=True)
    (folder / "made-before-v1.txt").write_bytes(b"an agent wrote this")
    answer = seed(project)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "work_not_empty"
    assert read_seed(project.root, TASK) is None
    assert not (Path(project.root) / SEED_STAGING_DIR).exists()
    assert (folder / "made-before-v1.txt").read_bytes() == b"an agent wrote this"


@needs_git
def test_a_seed_whose_task_folder_filled_after_the_record_answers_work_not_empty_until_it_empties(
        tmp_path, monkeypatch):
    project = Project(tmp_path)
    monkeypatch.setattr(seed_stage, "MOVE_WAIT_SECONDS", 0.2)
    folder = Path(project.root) / "work" / "_tasks" / TASK / ITEM
    with gate_held(project.root):
        assert seed(project).status == 202
    folder.mkdir(parents=True)
    (folder / "late.txt").write_bytes(b"late")
    blocked = seed(project)
    assert code_of(blocked) == (409, "seed_refused") and reason_of(blocked) == "work_not_empty"
    assert read_seed(project.root, TASK) is not None
    (folder / "late.txt").unlink()
    assert seed(project).payload["state"] == "seeded"


@needs_git
def test_a_seed_that_was_lost_is_refused_seed_lost_where_it_is_asked_again(tmp_path):
    project = Project(tmp_path)
    seed(project)
    shutil.rmtree(Path(project.root) / "work" / "_tasks" / TASK / ITEM)
    answer = seed(project)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "seed_lost"
    assert preparation(project)["state"] == "seed_lost"


@needs_git
def test_a_view_server_reads_a_staged_seed_and_moves_nothing(tmp_path, monkeypatch):
    active = Project(tmp_path)
    monkeypatch.setattr(seed_stage, "MOVE_WAIT_SECONDS", 0.2)
    with gate_held(active.root):
        assert seed(active).status == 202
    viewing = serving(active, "view", NoGit())
    answer = seed(viewing)
    assert answer.status == 200 and answer.payload["state"] == "staged"
    assert not (Path(active.root) / "work" / "_tasks").exists()
