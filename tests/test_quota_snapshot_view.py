"""The reader of the hub's limits snapshot: what `GET /command/quotas` answers in view (4.5.4).

`<conduct-home>/limits.json` is written by the hub after a good read of the ACTIVE project's
`GET /command/quotas` (4.1.9). A view child answers that route from it: the same keys the
active answer has, taken as they were, plus `hub_snapshot` with the project and the time the
hub took it. A missing or damaged file is "no data" (an empty `snapshots` and a null
`hub_snapshot`), never a zero and never a guess; the reader writes nothing.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from conductor.command.quota_snapshot_view import HubLimitsView

NOW = "2026-08-11T12:00:00Z"
PROJECT = "3f9c0a1b2c3d4e5f60718293a4b5c6d7"
TAKEN = "2026-08-11T11:58:30Z"
ANSWER = {
    "as_of": "2026-08-11T11:58:29Z",
    "max_age_seconds": 300.0,
    "providers": [{"provider_id": "codex", "availability": "available"}],
    "snapshots": [{"binding_id": "codex", "state": "observed", "windows": []}],
}
NO_DATA = {"as_of": NOW, "max_age_seconds": 300.0, "providers": [], "snapshots": [],
           "hub_snapshot": None}
MAX_AGE = timedelta(minutes=5)


def _file(**changes) -> dict:
    stored = {"schema_version": 1, "project_id": PROJECT, "taken_at": TAKEN,
              "quotas": dict(ANSWER)}
    return {**stored, **changes}


def _view(tmp_path, document=None, *, raw: bytes | None = None) -> HubLimitsView:
    path = tmp_path / "limits.json"
    if raw is not None:
        path.write_bytes(raw)
    elif document is not None:
        path.write_text(json.dumps(document), encoding="utf-8")
    return HubLimitsView(path, MAX_AGE)


def test_a_good_snapshot_answers_the_stored_keys_as_they_were_plus_the_hub_snapshot(tmp_path):
    answer = _view(tmp_path, _file()).payload((), NOW)
    assert answer == {**ANSWER, "hub_snapshot": {"project_id": PROJECT, "taken_at": TAKEN}}
    assert list(answer) == ["as_of", "max_age_seconds", "providers", "snapshots", "hub_snapshot"]


def test_no_file_and_no_path_are_no_data_with_this_projects_own_provider_rows(tmp_path):
    assert _view(tmp_path).payload((), NOW) == NO_DATA
    assert HubLimitsView(None, MAX_AGE).payload((), NOW) == NO_DATA


BAD_FILES = {
    "not json": {"raw": b"{not json"},
    "a json array": {"raw": b"[]"},
    "invalid utf-8": {"raw": b"\xff\xfe{}"},
    "a file over the size cap": {"raw": b" " * (600 * 1024) + json.dumps(_file()).encode()},
    "a key too many": {"document": {**_file(), "extra": 1}},
    "a key missing": {"document": {k: v for k, v in _file().items() if k != "taken_at"}},
    "schema version 2": {"document": _file(schema_version=2)},
    "schema version as text": {"document": _file(schema_version="1")},
    "schema version true": {"document": _file(schema_version=True)},
    "an upper-case project id": {"document": _file(project_id=PROJECT.upper())},
    "a short project id": {"document": _file(project_id=PROJECT[:31])},
    "a null project id": {"document": _file(project_id=None)},
    "a time without Z": {"document": _file(taken_at="2026-08-11T11:58:30")},
    "a time that is not text": {"document": _file(taken_at=1785000000)},
    "an answer that is not an object": {"document": _file(quotas=[])},
    "an answer without snapshots": {"document": _file(
        quotas={k: v for k, v in ANSWER.items() if k != "snapshots"})},
    "an answer with a key too many": {"document": _file(quotas={**ANSWER, "extra": []})},
    "snapshots that are not a list": {"document": _file(quotas={**ANSWER, "snapshots": {}})},
    "a row that is not an object": {"document": _file(quotas={**ANSWER, "providers": [1]})},
    "an age that is not a number": {"document": _file(
        quotas={**ANSWER, "max_age_seconds": "300"})},
    "an as_of that is not text": {"document": _file(quotas={**ANSWER, "as_of": 5})},
}


@pytest.mark.parametrize("name", sorted(BAD_FILES))
def test_a_damaged_or_foreign_file_is_no_data_and_never_a_partial_answer(tmp_path, name):
    assert _view(tmp_path, **BAD_FILES[name]).payload((), NOW) == NO_DATA


def test_a_path_that_is_a_folder_is_no_data(tmp_path):
    (tmp_path / "limits.json").mkdir()
    assert HubLimitsView(tmp_path / "limits.json", MAX_AGE).payload((), NOW) == NO_DATA


def test_the_file_is_read_at_every_answer_so_a_newer_snapshot_shows_at_once(tmp_path):
    view = _view(tmp_path)
    assert view.payload((), NOW)["hub_snapshot"] is None
    (tmp_path / "limits.json").write_text(json.dumps(_file()), encoding="utf-8")
    assert view.payload((), NOW)["hub_snapshot"]["taken_at"] == TAKEN
    (tmp_path / "limits.json").write_text(json.dumps(_file(taken_at=NOW)), encoding="utf-8")
    assert view.payload((), NOW)["hub_snapshot"]["taken_at"] == NOW


def test_answering_writes_nothing_and_leaves_the_file_byte_for_byte(tmp_path):
    view = _view(tmp_path, _file())
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    for _ in range(3):
        view.payload((), NOW)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_the_answer_is_a_copy_so_a_caller_cannot_change_what_the_next_answer_says(tmp_path):
    view = _view(tmp_path, _file())
    view.payload((), NOW)["snapshots"].append({"forged": True})
    assert view.payload((), NOW)["snapshots"] == ANSWER["snapshots"]
