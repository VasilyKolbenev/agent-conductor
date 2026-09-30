"""The one snapshot rule of the hub (spec 4.1.9), and `limits.json` by the same rule.

A snapshot is written only by the hub, whole and atomically, only when what it holds changed (the
moment it was taken is not content) and not more than once in 5 s for a project; it keeps at most
the 200 newest tasks and at most 512 KiB, losing `attention.journal` first; it outlives the stop of
its project; a broken one is absent and is not repaired by a read; and the registry is never written
on the way. `limits.json` is the same rule over the quotas answer of the active project, in the
exact form `HubLimitsView` (the reader of a `view` child) admits.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conductor.command.quota_snapshot_view import HubLimitsView
from conductor.hub import registry, snapshots

A = "a" * 32
B = "b" * 32
TAKEN = "2026-09-30T10:00:00Z"
FILE_KEYS = {"schema_version", "project_id", "taken_at", "tasks", "task_queue", "auto_continue",
             "quotas"}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _row(n: int, *, journal: int = 0, title: str | None = None) -> dict:
    attention = None if not journal else {
        "reasons": [{"reason": "confirmation", "count": 1, "sources": ["p1"]}], "gates": [],
        "runtime": [], "observed_at": TAKEN, "unreadable": False,
        "journal": [{"record_type": "action_request", "instant": TAKEN,
                     "action_id": f"a{k}", "node_id": "do", "proposal_id": None}
                    for k in range(journal)]}
    return {"task": {"task_id": f"task-{n:04d}", "title": title or f"Task {n}",
                     "created_at": f"2026-09-30T08:{n // 60:02d}:{n % 60:02d}Z",
                     "unreadable": False},
            "run": None, "automation": None, "attention": attention}


def _put(store: snapshots.SnapshotStore, project_id: str = A, *, rows=None, taken: str = TAKEN,
         queue=None, flag=None, quotas=None) -> str:
    return store.put(project_id, taken_at=taken, tasks=rows if rows is not None else [_row(1)],
                     task_queue=queue, auto_continue=flag, quotas=quotas)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path, clock) -> snapshots.SnapshotStore:
    return snapshots.SnapshotStore(tmp_path, clock=clock)


def _file(tmp_path: Path, project_id: str = A) -> Path:
    return tmp_path / "snapshots" / f"{project_id}.json"


def test_a_snapshot_is_written_whole_with_the_keys_of_the_spec_and_read_back(tmp_path, store):
    queue, flag = {"revision": 3, "entries": []}, {"enabled": True, "flag_id": "f"}
    assert _put(store, rows=[_row(1), _row(2)], queue=queue, flag=flag,
                quotas={"as_of": TAKEN}) == "written"
    document = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    assert set(document) == FILE_KEYS and document["schema_version"] == 1
    assert document["project_id"] == A and document["taken_at"] == TAKEN
    got = store.get(A)
    assert (got.project_id, got.taken_at, got.task_queue, got.auto_continue, got.quotas) == (
        A, TAKEN, queue, flag, {"as_of": TAKEN})
    assert [row["task"]["task_id"] for row in got.tasks] == ["task-0001", "task-0002"]
    assert [path.name for path in (tmp_path / "snapshots").iterdir()] == [f"{A}.json"], \
        "a staged file was left beside the snapshot"


def test_a_snapshot_is_rewritten_only_when_its_content_changed_and_the_time_is_not_content(
        tmp_path, store, clock):
    assert _put(store) == "written"
    before = _file(tmp_path).read_bytes()
    clock.now += 60
    assert _put(store, taken="2026-09-30T10:01:00Z") == "unchanged"
    assert _file(tmp_path).read_bytes() == before, "the moment alone rewrote the file"
    assert _put(store, rows=[_row(1, title="Changed")], taken="2026-09-30T10:01:00Z") == "written"
    assert store.get(A).taken_at == "2026-09-30T10:01:00Z"


def test_a_snapshot_of_a_project_is_written_at_most_once_in_five_seconds(tmp_path, store, clock):
    assert _put(store, rows=[_row(1)]) == "written"
    clock.now += 4.9
    assert _put(store, rows=[_row(2)]) == "too_soon"
    assert store.get(A).tasks[0]["task"]["task_id"] == "task-0001"
    assert _put(store, B, rows=[_row(9)]) == "written", "another project has its own clock"
    clock.now += 0.1
    assert _put(store, rows=[_row(2)]) == "written"
    assert store.get(A).tasks[0]["task"]["task_id"] == "task-0002"
    assert snapshots.MIN_INTERVAL_SECONDS == 5


def test_a_snapshot_keeps_the_200_newest_tasks_in_their_order(store):
    rows = [_row(n) for n in range(250)]
    assert _put(store, rows=rows) == "written"
    kept = [row["task"]["task_id"] for row in store.get(A).tasks]
    assert kept == [f"task-{n:04d}" for n in range(50, 250)] and len(kept) == 200
    assert snapshots.MAX_TASKS == 200


def test_a_snapshot_over_512_kib_loses_the_journal_and_one_still_too_big_is_not_written(
        tmp_path, store, clock):
    heavy = [_row(n, journal=256) for n in range(60)]
    assert _put(store, rows=heavy) == "written"
    written = _file(tmp_path).stat().st_size
    assert written <= 512 * 1024, written
    kept = store.get(A).tasks
    assert len(kept) == 60 and all(row["attention"]["journal"] == [] for row in kept)
    assert all(row["attention"]["reasons"] for row in kept), "only the journal may fall out"
    clock.now += 10
    before = _file(tmp_path).read_bytes()
    huge = [_row(n, title="x" * 4000) for n in range(200)]
    assert _put(store, rows=huge) == "too_large"
    assert _file(tmp_path).read_bytes() == before, "an oversize snapshot replaced the good one"
    assert snapshots.MAX_BYTES == 512 * 1024


@pytest.mark.parametrize("damage", ["not json", "[]", '{"schema_version": 1}', "", "null",
                                    '{"schema_version": 2}'])
def test_a_broken_snapshot_reads_as_absent_and_a_read_does_not_repair_it(tmp_path, store, damage):
    _put(store)
    _file(tmp_path).write_text(damage, encoding="utf-8")
    assert store.get(A) is None
    assert _file(tmp_path).read_text(encoding="utf-8") == damage


def test_a_snapshot_that_is_not_the_form_is_absent(tmp_path, store):
    _put(store)
    good = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    for change in ({"project_id": B}, {"taken_at": "yesterday"}, {"extra": 1},
                   {"tasks": "no"}, {"tasks": [{"task": {}}]}, {"task_queue": "x"},
                   {"schema_version": True}):
        _file(tmp_path).write_text(json.dumps({**good, **change}), encoding="utf-8")
        assert store.get(A) is None, change
    missing = {k: v for k, v in good.items() if k != "quotas"}
    _file(tmp_path).write_text(json.dumps(missing), encoding="utf-8")
    assert store.get(A) is None
    _file(tmp_path).write_bytes(b" " * (512 * 1024 + 1))
    assert store.get(A) is None, "a file over the cap is not the hub's"


def test_the_next_good_cycle_replaces_a_broken_snapshot(tmp_path, store, clock):
    _put(store)
    _file(tmp_path).write_text("broken", encoding="utf-8")
    clock.now += 10
    assert _put(store) == "written", "the content is the same, but the file is not the content"
    assert store.get(A) is not None


def test_the_last_snapshot_outlives_the_hub_and_nothing_here_can_delete_it(tmp_path, store):
    _put(store, rows=[_row(1), _row(2)])
    assert not [name for name in dir(store) if "delete" in name or "remove" in name]
    again = snapshots.SnapshotStore(tmp_path)
    assert [row["task"]["task_id"] for row in again.get(A).tasks] == ["task-0001", "task-0002"]
    assert again.get(B) is None, "a project that never had one has none"


def test_a_restarted_hub_does_not_rewrite_a_snapshot_whose_content_it_reads_again(tmp_path, clock):
    first = snapshots.SnapshotStore(tmp_path, clock=clock)
    assert _put(first) == "written"
    after = snapshots.SnapshotStore(tmp_path, clock=clock)
    assert _put(after) == "unchanged"


def test_a_snapshot_never_writes_the_registry(tmp_path, store):
    registry.add_project(project_id=A, root=str(tmp_path / "p"), root_identity=(1, 1), name="p",
                         folder=tmp_path, now="2026-09-30T09:00:00Z")
    own = {"snapshots", "limits.json"}

    def beside() -> dict[str, bytes]:
        return {path.name: path.read_bytes() for path in tmp_path.iterdir()
                if path.is_file() and path.name not in own}

    before = beside()
    assert registry.FILE_NAME in before
    _put(store)
    _put(store, B)
    store.put_limits(A, taken_at=TAKEN, quotas=_quotas())
    assert beside() == before, "a snapshot changed, made or removed a file of the registry"


def test_a_project_id_that_is_not_32_hex_is_refused_before_any_path_is_made(tmp_path, store):
    for bad in ("", "../x", "A" * 32, "a" * 31, "a" * 33):
        with pytest.raises(ValueError):
            _put(store, bad)
        with pytest.raises(ValueError):
            store.get(bad)
    assert not (tmp_path / "snapshots").exists() or not list((tmp_path / "snapshots").iterdir())


# -- limits.json -----------------------------------------------------------------------------


def _quotas(as_of: str = TAKEN, rows=None) -> dict:
    return {"as_of": as_of, "max_age_seconds": 300, "providers": [], "snapshots": rows or []}


def test_limits_are_written_in_the_exact_form_the_view_child_reads_and_read_back_whole(tmp_path):
    store = snapshots.SnapshotStore(tmp_path)
    rows = [{"account": None, "state": "missing", "binding_ids": ["glm-1"]}]
    assert store.put_limits(A, taken_at=TAKEN, quotas=_quotas(rows=rows)) == "written"
    document = json.loads((tmp_path / "limits.json").read_text(encoding="utf-8"))
    assert set(document) == {"schema_version", "project_id", "taken_at", "quotas"}
    assert document == {"schema_version": 1, "project_id": A, "taken_at": TAKEN,
                        "quotas": _quotas(rows=rows)}
    answer = HubLimitsView(tmp_path / "limits.json").payload((), "2026-09-30T10:00:05Z")
    assert answer["hub_snapshot"] == {"project_id": A, "taken_at": TAKEN}
    assert answer["snapshots"] == rows and answer["max_age_seconds"] == 300
    got = store.get_limits()
    assert (got.project_id, got.taken_at, got.quotas["snapshots"]) == (A, TAKEN, rows)


def test_limits_follow_the_same_rule_unchanged_not_rewritten_and_once_in_five_seconds(
        tmp_path, clock):
    store = snapshots.SnapshotStore(tmp_path, clock=clock)
    assert store.put_limits(A, taken_at=TAKEN, quotas=_quotas()) == "written"
    before = (tmp_path / "limits.json").read_bytes()
    clock.now += 60
    assert store.put_limits(A, taken_at="2026-09-30T10:01:00Z", quotas=_quotas()) == "unchanged"
    assert (tmp_path / "limits.json").read_bytes() == before
    changed = _quotas(rows=[{"state": "observed", "binding_ids": ["x"]}])
    assert store.put_limits(A, taken_at="2026-09-30T10:01:00Z", quotas=changed) == "written"
    clock.now += 4
    again = _quotas(rows=[{"state": "missing", "binding_ids": ["x"]}])
    assert store.put_limits(A, taken_at="2026-09-30T10:01:04Z", quotas=again) == "too_soon"


def test_a_limits_file_that_is_not_the_form_is_no_data_and_is_left_alone(tmp_path):
    store = snapshots.SnapshotStore(tmp_path)
    assert store.get_limits() is None
    (tmp_path / "limits.json").write_text('{"schema_version": 1}', encoding="utf-8")
    assert store.get_limits() is None
    assert (tmp_path / "limits.json").read_text(encoding="utf-8") == '{"schema_version": 1}'
    assert store.put_limits(A, taken_at=TAKEN, quotas=_quotas()) == "written", \
        "the next good read of the active project replaces it"
    assert store.get_limits() is not None


NOT_THE_FOUR_KEYS = {
    "the echo of a view child": {**_quotas(), "hub_snapshot": {"project_id": A, "taken_at": TAKEN}},
    "a key missing": {"as_of": TAKEN, "max_age_seconds": 300, "providers": []},
    "max_age_seconds a string": {**_quotas(), "max_age_seconds": "300"},
    "max_age_seconds not finite": {**_quotas(), "max_age_seconds": float("nan")},
    "providers not a list": {**_quotas(), "providers": {}},
    "a row that is not an object": _quotas(rows=["x"]),
    "not an object at all": ["as_of", "max_age_seconds", "providers", "snapshots"],
}


@pytest.mark.parametrize("answer", list(NOT_THE_FOUR_KEYS.values()), ids=list(NOT_THE_FOUR_KEYS))
def test_a_quotas_answer_that_is_not_the_four_key_form_is_refused_and_the_good_file_stands(
        tmp_path, clock, answer):
    store = snapshots.SnapshotStore(tmp_path, clock=clock)
    assert store.put_limits(A, taken_at=TAKEN, quotas=_quotas()) == "written"
    before = (tmp_path / "limits.json").read_bytes()
    clock.now += 60
    assert store.put_limits(B, taken_at="2026-09-30T10:01:00Z", quotas=answer) == "refused"
    assert (tmp_path / "limits.json").read_bytes() == before
    assert store.get_limits().project_id == A, "a refused answer replaced the good file"


def test_a_refused_quotas_answer_makes_no_file_and_the_next_good_one_is_written_at_once(
        tmp_path, clock):
    store = snapshots.SnapshotStore(tmp_path, clock=clock)
    echo = NOT_THE_FOUR_KEYS["the echo of a view child"]
    assert store.put_limits(A, taken_at=TAKEN, quotas=echo) == "refused"
    assert not (tmp_path / "limits.json").exists()
    assert store.put_limits(A, taken_at=TAKEN, quotas=_quotas()) == "written"


def test_the_moment_a_snapshot_was_taken_reads_as_a_utc_instant_the_spec_writes(store):
    datetime.strptime(TAKEN, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        _put(store, taken="10:00")
