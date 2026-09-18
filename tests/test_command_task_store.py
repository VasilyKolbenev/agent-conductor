"""Where a task lives, and what the store refuses to make of one.

The seam is ``conductor.command.task_store.TaskStore`` over a real directory,
through the real contract. The claims: a task is created exclusively and
all-or-nothing (a crash mid-write publishes nothing, a second create under one
id is `TaskExists`); a name the contract refuses never reaches a path; absent
and corrupt are two different refusals; the listing is read off the directory,
skips what no call could address, touches no byte, and NAMES an entry whose
content lives elsewhere rather than refusing every healthy task beside it; the
store holds the
SAME process-local root gate `RunStore` holds and bumps the same thread-local
depth; a read edits no byte; the create door takes exactly a `TaskRecord`; the
record on disk is canonical JSON ending in exactly one newline; and a route
whose content lives somewhere else is refused rather than read.

Every damage witness names the mutation that would turn it red.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from conductor.command import run_files
from conductor.command.containment import RouteViolationCode
from conductor.command.run_store import RunStore
from conductor.command.store_errors import StoreError
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import CorruptTask, TaskExists, TaskStore
from conductor.command.template_store import RouteNotOwned

NOW = "2026-09-15T12:00:00Z"


def a_task(**changes) -> TaskRecord:
    values = {
        "task_id": "task-001",
        "title": "Ship the task store",
        "work_scope": "task-001",
        "created_at": NOW,
    }
    values.update(changes)
    return TaskRecord(**values)


def canonical_bytes(document: dict) -> bytes:
    """The one JSON spelling the store writes, spelled by hand in the test."""
    return (json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def durable_bytes(root: Path) -> dict[str, bytes]:
    """Every file below `root` as {relative posix path -> bytes}, dotfiles included."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def write_record(directory: Path, document: object) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "task.json").write_bytes(canonical_bytes(document))


# -- creation -------------------------------------------------------------------


def test_create_task_is_exclusive_and_the_record_reads_back_through_the_contract(tmp_path):
    store = TaskStore(tmp_path)
    published = store.create_task(a_task())

    assert published == tmp_path / "conductor" / "tasks" / "task-001"
    assert (published / "task.json").is_file()
    assert store.read("task-001") == a_task()
    assert store.standing("task-001") == a_task()
    assert store.tasks() == ("task-001",)

    before = durable_bytes(store.tasks_root)
    with pytest.raises(TaskExists, match="task-001"):
        store.create_task(a_task())
    with pytest.raises(TaskExists, match="task-001"):
        store.create_task(a_task(title="A different title under one id"))
    assert durable_bytes(store.tasks_root) == before
    assert [entry.name for entry in store.tasks_root.iterdir()] == ["task-001"]


def test_a_crash_mid_write_publishes_no_task(tmp_path, monkeypatch):
    """The staging directory is the whole of what a torn write leaves, and it is removed.

    Patched where the writer LIVES (`run_files._write_all`), because the staging
    call resolves the name in its own module's globals -- a patch on the store's
    namespace would tear nothing. Mutation: write `task.json` at the final path
    instead of staging -> a half-written record is published -> red.
    """
    store = TaskStore(tmp_path)

    def tear(fd, payload):
        os.write(fd, payload[:12])
        raise OSError("the machine lost power mid-write")

    monkeypatch.setattr(run_files, "_write_all", tear)
    with pytest.raises(StoreError, match="cannot write task 'task-001'"):
        store.create_task(a_task())
    assert list(store.tasks_root.iterdir()) == []
    assert store.standing("task-001") is None
    assert store.tasks() == ()

    monkeypatch.undo()
    assert store.create_task(a_task()) == store.task_path("task-001")
    assert store.read("task-001") == a_task()


def test_the_rename_and_not_the_pre_check_is_what_refuses_a_task_that_appears_late(
        tmp_path, monkeypatch):
    """`final.exists()` before staging is advice; the rename onto the final name
    is the arbiter. A competitor that publishes between the check and the
    rename is refused as `TaskExists`, and its record is the one that stands.

    Patched at `tempfile.mkdtemp`, the one call between the pre-check and the
    rename: the competitor lands while the stage is minted, so the pre-check
    saw nothing and only the rename can refuse. Mutation: write `task.json` at
    the final path with no stage and no rename -> the stage is never minted,
    the competitor never appears, and the late create is published -> red.
    """
    from conductor.command import task_store as module
    store = TaskStore(tmp_path)
    competitor = a_task(title="The record that got there first")
    real_mkdtemp = module.tempfile.mkdtemp

    def publish_the_competitor_then_stage(*args, **kwargs):
        write_record(store.task_path("task-001"), competitor.as_dict())
        return real_mkdtemp(*args, **kwargs)

    monkeypatch.setattr(module.tempfile, "mkdtemp", publish_the_competitor_then_stage)
    with pytest.raises(TaskExists, match="task-001"):
        store.create_task(a_task())
    assert store.read("task-001") == competitor
    assert [entry.name for entry in store.tasks_root.iterdir()] == ["task-001"]


@pytest.mark.parametrize("name", ["../outside", "has space", "", "a/b", ".dot", "t" * 65])
def test_a_name_the_contract_refuses_never_reaches_a_path(tmp_path, name):
    """One rule, the contract's, at every door -- and no directory is made to ask it."""
    store = TaskStore(tmp_path)
    with pytest.raises(StoreError):
        store.task_path(name)
    with pytest.raises(StoreError):
        store.standing(name)
    with pytest.raises(StoreError):
        store.read(name)
    assert not store.tasks_root.exists()
    # Where "../outside" would land if the join had happened: beside the
    # tasks root, inside the project's own conductor directory.
    assert not (tmp_path / "conductor" / "outside").exists()


def test_a_sixty_five_character_id_is_refused_by_the_bound_and_not_by_the_grammar(tmp_path):
    """The grammar admits 128; the task bound refuses here. Mutation: `_id` alone -> red."""
    store = TaskStore(tmp_path)
    assert store.task_path("t" * 64) == store.tasks_root / ("t" * 64)
    with pytest.raises(StoreError, match="64"):
        store.task_path("t" * 65)


def test_create_task_takes_a_task_record_and_no_lookalike(tmp_path):
    """A subclass may answer `as_dict` for itself; this door does not accept one."""
    class Sneaky(TaskRecord):
        pass

    store = TaskStore(tmp_path)
    with pytest.raises(StoreError, match="exactly a TaskRecord"):
        store.create_task(Sneaky("task-001", "Sneaky", "task-001", NOW))
    with pytest.raises(StoreError, match="exactly a TaskRecord"):
        store.create_task(a_task().as_dict())
    assert not store.tasks_root.exists()


def test_the_record_on_disk_is_canonical_json_ending_in_exactly_one_newline(tmp_path):
    store = TaskStore(tmp_path)
    store.create_task(a_task(title="Задача — v2"))
    stored = (store.task_path("task-001") / "task.json").read_bytes()

    assert stored == canonical_bytes(a_task(title="Задача — v2").as_dict())
    assert stored.endswith(b"\n") and not stored.endswith(b"\n\n")
    assert b"\r" not in stored
    assert list(json.loads(stored)) == sorted(a_task().as_dict())


# -- reading ---------------------------------------------------------------------


def test_absent_and_corrupt_are_two_different_refusals(tmp_path):
    """Absent: `None` from `standing`, a plain `StoreError` from `read`; never `CorruptTask`."""
    store = TaskStore(tmp_path)
    store.create_task(a_task())

    assert store.standing("task-none") is None
    with pytest.raises(StoreError, match="task 'task-none' does not exist") as absent:
        store.read("task-none")
    assert not isinstance(absent.value, CorruptTask)

    (store.task_path("task-001") / "task.json").write_bytes(b"{not json\n")
    with pytest.raises(CorruptTask):
        store.read("task-001")
    with pytest.raises(CorruptTask):
        store.standing("task-001")


def damage_not_json(directory: Path) -> str:
    (directory / "task.json").write_bytes(b"{not json\n")
    return "unreadable"


def damage_a_json_list(directory: Path) -> str:
    (directory / "task.json").write_bytes(b"[]\n")
    return "must be a JSON object"


def damage_a_missing_key(directory: Path) -> str:
    document = {key: value for key, value in a_task().as_dict().items() if key != "title"}
    write_record(directory, document)
    return "violates the task contract"


def damage_an_extra_key(directory: Path) -> str:
    write_record(directory, {**a_task().as_dict(), "runs": []})
    return "violates the task contract"


def damage_a_schema_version_this_build_does_not_speak(directory: Path) -> str:
    write_record(directory, {**a_task().as_dict(), "schema_version": 2})
    return "violates the task contract"


def damage_a_title_with_a_control_character(directory: Path) -> str:
    write_record(directory, {**a_task().as_dict(), "title": "a\x01b"})
    return "violates the task contract"


def damage_a_record_naming_another_task(directory: Path) -> str:
    write_record(directory, a_task(task_id="task-002", work_scope="task-002").as_dict())
    return "task directory 'task-001' contains task 'task-002'"


@pytest.mark.parametrize("damage", [
    damage_not_json,
    damage_a_json_list,
    damage_a_missing_key,
    damage_an_extra_key,
    damage_a_schema_version_this_build_does_not_speak,
    damage_a_title_with_a_control_character,
    damage_a_record_naming_another_task,
], ids=lambda call: call.__name__.removeprefix("damage_"))
def test_a_record_that_contradicts_the_contract_or_its_directory_is_corrupt(tmp_path, damage):
    """Written by us is not a reason to trust it back: `from_dict`, then the directory name.

    Mutation: read the record without `from_dict`, or skip the directory-name
    check -> the matching row goes green with a record that lies.
    """
    store = TaskStore(tmp_path)
    store.create_task(a_task())
    expected = damage(store.task_path("task-001"))
    before = durable_bytes(tmp_path)

    with pytest.raises(CorruptTask, match=expected):
        store.read("task-001")
    with pytest.raises(CorruptTask, match=expected):
        store.standing("task-001")
    # The listing judges no content, so the directory is still a task by name.
    assert store.tasks() == ("task-001",)
    assert durable_bytes(tmp_path) == before


def test_a_directory_holding_no_record_is_corrupt_to_read_and_absent_from_the_list(tmp_path):
    store = TaskStore(tmp_path)
    store.create_task(a_task())
    (store.task_path("task-001") / "task.json").unlink()

    with pytest.raises(CorruptTask, match="unreadable"):
        store.read("task-001")
    with pytest.raises(CorruptTask):
        store.standing("task-001")
    assert store.tasks() == ()


def test_reading_a_task_edits_no_durable_byte(tmp_path):
    """The whole project root, and the file SET: a leaked staging file fails this too."""
    store = TaskStore(tmp_path)
    store.create_task(a_task())
    before = durable_bytes(tmp_path)

    assert store.read("task-001") == a_task()
    assert store.standing("task-001") == a_task()
    assert store.standing("task-none") is None
    assert store.tasks() == ("task-001",)
    assert durable_bytes(tmp_path) == before


# -- the listing -------------------------------------------------------------------


def test_tasks_lists_sorted_ids_and_skips_what_no_call_could_address(tmp_path):
    """Read off the directory, in name order, and never off an index.

    Skipped: a staging leftover (a dot-name fails the grammar), a name that is
    not an id, a name over the task bound, a plain file, a directory holding no
    record. Mutation: list every directory -> the leftover and the 65-character
    name appear -> red.
    """
    store = TaskStore(tmp_path)
    store.create_task(a_task(task_id="b-task", work_scope="b-task"))
    store.create_task(a_task(task_id="a-task", work_scope="a-task"))
    write_record(store.tasks_root / ".b-task.k3j2x1", a_task().as_dict())   # staging leftover
    write_record(store.tasks_root / "has space", a_task().as_dict())
    write_record(store.tasks_root / ("t" * 65), a_task().as_dict())
    (store.tasks_root / "c-task").mkdir()                                    # no record
    (store.tasks_root / "notes.txt").write_text("x", encoding="utf-8", newline="\n")
    before = durable_bytes(tmp_path)

    assert store.tasks() == ("a-task", "b-task")
    assert durable_bytes(tmp_path) == before
    assert TaskStore(tmp_path / "nobody").tasks() == ()


def test_a_portal_at_one_entry_is_listed_and_never_followed_and_never_hides_a_neighbour(
        tmp_path):
    """One entry whose content lives elsewhere may not cost the whole listing.

    The contract the route promises is "task-a readable + task-b unreadable",
    and a listing that refused for one entry hid every healthy task behind the
    broken one. Three entries stand here: ``task-a`` is whole, ``task-b`` holds
    a ``task.json`` that is a portal to a file OUTSIDE the store, and
    ``task-c`` IS a portal, aimed at that same plain file -- so a listing that
    FOLLOWED it would decide it is not a directory and drop it silently. All
    three are named; only ``task-a`` reads; the bytes outside are not touched.

    Mutations: refuse on the portal inside `_listed` again -> `tasks()` raises
    and task-a is hidden behind task-b -> red; judge the entry by following it
    (`entry.is_dir()`) -> task-c vanishes from the listing -> red.
    """
    store = TaskStore(tmp_path)
    store.create_task(a_task(task_id="task-a", work_scope="task-a"))
    store.create_task(a_task(task_id="task-b", work_scope="task-b"))
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    record = outside / "record.json"
    record.write_bytes(canonical_bytes(a_task(
        task_id="task-b", work_scope="task-b").as_dict()))
    (store.tasks_root / "task-b" / "task.json").unlink()
    if not (_portal(store.tasks_root / "task-b" / "task.json", record,
                    directory=False)
            and _portal(store.tasks_root / "task-c", record, directory=False)):
        pytest.skip("this machine does not permit creating a symbolic link")
    before = record.read_bytes()

    assert store.tasks() == ("task-a", "task-b", "task-c")
    assert store.read("task-a") == a_task(task_id="task-a", work_scope="task-a")
    for portal in ("task-b", "task-c"):
        with pytest.raises(RouteNotOwned) as refusal:
            store.read(portal)
        assert str(tmp_path) not in str(refusal.value)
    assert record.read_bytes() == before


# -- the gate ----------------------------------------------------------------------


def test_the_task_store_holds_the_run_stores_gate_for_one_root_and_its_aliases(tmp_path):
    """No new lock system: one gate per resolved root, shared by both stores.

    Held three ways: identity of the gate object, the run store's thread-local
    depth reporting the task store's transaction, and a second thread finding
    the RUN store's lock taken while the TASK store's transaction stands.
    Mutation: give `TaskStore` its own `RLock` -> the thread acquires -> red.
    """
    root = tmp_path / "project"
    runs = RunStore(root)
    tasks = TaskStore(root)
    alias = TaskStore(root / ".." / "project")

    assert tasks._root_gate is runs._root_gate
    assert alias._root_gate is runs._root_gate
    assert RunStore.current_thread_holds_transaction() is False

    acquired: list[bool] = []

    def probe() -> None:
        taken = runs._root_gate.lock.acquire(blocking=False)
        acquired.append(taken)
        if taken:
            runs._root_gate.lock.release()

    with tasks.transaction():
        assert RunStore.current_thread_holds_transaction() is True
        with runs.transaction():                # reentrant, so the doors nest
            assert tasks.standing("task-001") is None
        assert RunStore.current_thread_holds_transaction() is True
        worker = threading.Thread(target=probe)
        worker.start()
        worker.join()
    assert acquired == [False]
    assert RunStore.current_thread_holds_transaction() is False
    worker = threading.Thread(target=probe)
    worker.start()
    worker.join()
    assert acquired == [False, True]


# -- the route this store writes through, and what it refuses to reach ---------------


def _portal(link: Path, target: Path, *, directory: bool) -> bool:
    """Make one symlink, or report that this machine will not let us."""
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        return False
    return True


def test_a_route_component_that_is_a_file_is_refused_as_a_route(tmp_path):
    project = tmp_path / "project"
    (project / "conductor").mkdir(parents=True)
    (project / "conductor" / "tasks").write_text("x", encoding="utf-8", newline="\n")
    store = TaskStore(project)

    for door in (lambda: store.create_task(a_task()),
                 lambda: store.standing("task-001"),
                 lambda: store.tasks()):
        with pytest.raises(RouteNotOwned) as refusal:
            door()
        assert "not a directory" in str(refusal.value)
        assert str(tmp_path) not in str(refusal.value)


def test_a_portal_on_the_route_is_refused_without_naming_the_path(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    project = tmp_path / "project"
    (project / "conductor").mkdir(parents=True)
    if not _portal(project / "conductor" / "tasks", elsewhere, directory=True):
        pytest.skip("this machine does not permit creating a symbolic link")
    store = TaskStore(project)
    with pytest.raises(RouteNotOwned) as refusal:
        store.create_task(a_task())
    assert "symbolic link" in str(refusal.value)
    for secret in (str(tmp_path), str(elsewhere), str(store.tasks_root)):
        assert secret not in str(refusal.value)
    assert not list(elsewhere.iterdir()), "it wrote through the portal anyway"
    with pytest.raises(RouteNotOwned):
        store.tasks()


def test_a_record_that_carries_a_second_name_is_refused_on_the_way_out(tmp_path):
    """`os.rename` arbitrates the NAME and says nothing about the bytes behind it."""
    store = TaskStore(tmp_path)
    store.create_task(a_task())
    twin = tmp_path / "twin.json"
    try:
        os.link(store.task_path("task-001") / "task.json", twin)
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not permit creating a hard link")
    with pytest.raises(RouteNotOwned) as refusal:
        store.read("task-001")
    assert "more than one name" in str(refusal.value)
    assert str(tmp_path) not in str(refusal.value)
    with pytest.raises(RouteNotOwned):
        store.standing("task-001")


def test_every_structural_reason_has_a_sentence_that_names_no_path():
    """Derived from the store's own table: a code with no sentence is a KeyError mid-refusal.

    The table covers exactly the codes the template store's does: the two stores
    walk the same containment and can meet the same violations, so a row dropped
    from this one is a KeyError the other store never has. Mutation: drop any
    row of `task_store._ROUTE_REFUSAL` -> red.
    """
    from conductor.command import task_store, template_store

    assert task_store._ROUTE_REFUSAL, "the refusal table is empty"
    assert set(task_store._ROUTE_REFUSAL) == set(template_store._ROUTE_REFUSAL)
    for code, sentence in task_store._ROUTE_REFUSAL.items():
        assert isinstance(code, RouteViolationCode)
        assert sentence and not any(mark in sentence for mark in ("/", "\\", ":")), (
            code, sentence)
