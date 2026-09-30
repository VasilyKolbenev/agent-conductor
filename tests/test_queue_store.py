"""The queue file and the receipts of the runs it started (spec 4.4.3).

The file is `data_root/queue/queue.json`: canonical bytes replaced atomically under the project's
root gate, at most 32 entries, one per run. The receipt of a start is
`queue/started/<run_id>/<kind>/<record_id>.json`, created exclusively before the grant or the
control it names is written. Neither file is a permission by itself: what they say is judged
against the run's journal by the reader and the pump, which is why this file is about shape, the
route, and the writing, and nothing here starts a run.
"""
from __future__ import annotations

import copy
import os

import pytest

from conductor.command.contract_values import ContractError
from conductor.command.contracts import canonical_json
from conductor.command.path_admission import WindowsNameError
from conductor.command.queue_store import (
    JOURNAL_KIND, MAX_QUEUE, CorruptQueue, CorruptReceipt, Dropped, QueueEntry, QueueFile,
    QueueStore, Receipt, ReceiptExists, ResumePreauth, StartPreauth)
from conductor.command.store_errors import StoreError
from conductor.command.template_store import RouteNotOwned
from conductor.ownership import data_root

NOW = "2026-09-30T10:00:00Z"
LATER = "2026-09-30T10:05:00Z"
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
ASKED = {"node_limits": [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 2}],
         "max_actions": 2, "max_action_seconds": 60, "max_total_task_seconds": 120,
         "duration_seconds": 300}


def start_preauth(**changes):
    values = {"authorization_id": "grant-1", "preview_digest": DIGEST,
              "source_prefix_digest": OTHER, "asked": copy.deepcopy(ASKED), "supersedes": None,
              "authorized_by": "vasily", "preauthorized_at": NOW}
    return StartPreauth(**{**values, **changes})


def resume_preauth(**changes):
    values = {"control_id": "resume-1", "authorization_id": "grant-1",
              "authorization_digest": DIGEST, "expected_control_id": "pause-1",
              "actor": "vasily", "preauthorized_at": NOW}
    return ResumePreauth(**{**values, **changes})


def entry(run_id="task-1-r1", kind="start", **changes):
    body = start_preauth() if kind == "start" else resume_preauth()
    values = {"run_id": run_id, "kind": kind, "enqueued_at": NOW, "enqueued_by": "vasily",
              "preauthorization": body, "dropped": None}
    return QueueEntry(**{**values, **changes})


def receipt(**changes):
    values = {"run_id": "task-1-r1", "kind": "run_authorization", "record_id": "grant-1",
              "authorized_by": "vasily", "preauthorized_at": NOW, "digest": DIGEST,
              "record_digest": OTHER, "started_at": LATER, "admission": "confirmation",
              "flag_id": None, "transition_id": None}
    return Receipt(**{**values, **changes})


def entries_of(count):
    return tuple(entry(f"task-{number}-r1") for number in range(count))


# --- the entry ------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["start", "resume"])
def test_an_entry_is_stored_and_read_back_equal(kind):
    original = entry(kind=kind)
    assert QueueEntry.from_dict(original.as_dict()) == original


def test_a_start_entry_stores_exactly_the_spec_keys_and_the_prefix_digest_of_its_terms():
    stored = entry().as_dict()
    assert list(stored) == ["run_id", "kind", "enqueued_at", "enqueued_by", "preauthorization",
                            "dropped"]
    assert list(stored["preauthorization"]) == [
        "authorization_id", "preview_digest", "source_prefix_digest", "asked", "supersedes",
        "authorized_by", "preauthorized_at"]
    assert stored["preauthorization"]["asked"] == ASKED and stored["dropped"] is None


def test_a_resume_entry_stores_exactly_the_spec_keys():
    stored = entry(kind="resume").as_dict()["preauthorization"]
    assert list(stored) == ["control_id", "authorization_id", "authorization_digest",
                            "expected_control_id", "actor", "preauthorized_at"]


def test_the_key_of_an_entry_is_its_run_the_journal_kind_and_its_record():
    assert entry().key == ("task-1-r1", "run_authorization", "grant-1")
    assert entry(kind="resume").key == ("task-1-r1", "run_authorization_control", "resume-1")
    assert entry(preauthorization=None, dropped=Dropped("terms_changed", LATER)).key is None
    assert JOURNAL_KIND == {"start": "run_authorization", "resume": "run_authorization_control"}


def test_a_dropped_entry_has_no_preauthorization_and_names_why_and_when():
    dropped = entry(preauthorization=None, dropped=Dropped("grant_expired", LATER))
    assert QueueEntry.from_dict(dropped.as_dict()) == dropped
    assert dropped.as_dict()["dropped"] == {"reason_code": "grant_expired", "at": LATER}


@pytest.mark.parametrize("changes", [
    {"dropped": Dropped("terms_changed", LATER)},                     # both
    {"preauthorization": None},                                       # neither
    {"kind": "later"},
    {"run_id": "not a safe id!"},
    {"enqueued_at": "yesterday"},
    {"enqueued_by": ""},
])
def test_an_entry_the_contract_refuses_cannot_be_built(changes):
    with pytest.raises(ContractError):
        entry(**changes)


def test_an_entry_whose_body_is_the_body_of_the_other_kind_cannot_be_built():
    for kind, body in (("resume", start_preauth()), ("start", resume_preauth())):
        with pytest.raises(ContractError):
            QueueEntry("task-1-r1", kind, NOW, "vasily", body, None)


@pytest.mark.parametrize("reason", ["server_restarted", "preview_stale", "", None])
def test_a_drop_reason_outside_the_four_the_pump_writes_is_refused(reason):
    with pytest.raises(ContractError):
        Dropped(reason, LATER)


@pytest.mark.parametrize("make, changes", [
    (start_preauth, {"authorization_id": "x y"}), (start_preauth, {"preview_digest": "sha256:1"}),
    (start_preauth, {"source_prefix_digest": "nope"}), (start_preauth, {"supersedes": 3}),
    (start_preauth, {"authorized_by": ""}), (start_preauth, {"preauthorized_at": "soon"}),
    (start_preauth, {"asked": {}}), (start_preauth, {"asked": {**ASKED, "extra": 1}}),
    (start_preauth, {"asked": {**ASKED, "max_actions": 0}}),
    (start_preauth, {"asked": {**ASKED, "node_limits": [{"node_id": "do"}]}}),
    (resume_preauth, {"control_id": ""}), (resume_preauth, {"authorization_digest": "x"}),
    (resume_preauth, {"expected_control_id": 7}), (resume_preauth, {"actor": ""}),
])
def test_a_preauthorization_the_contract_refuses_cannot_be_built(make, changes):
    with pytest.raises(ContractError):
        make(**changes)


def test_a_stored_entry_with_a_key_too_many_or_too_few_is_refused():
    stored = entry().as_dict()
    with pytest.raises(ContractError):
        QueueEntry.from_dict({**stored, "note": "x"})
    with pytest.raises(ContractError):
        QueueEntry.from_dict({key: value for key, value in stored.items() if key != "dropped"})
    bad = copy.deepcopy(stored)
    bad["preauthorization"]["role"] = "owner"
    with pytest.raises(ContractError):
        QueueEntry.from_dict(bad)


def test_an_entry_does_not_share_its_asked_terms_with_the_dict_it_was_built_from():
    asked = copy.deepcopy(ASKED)
    built = start_preauth(asked=asked)
    asked["max_actions"] = 99
    assert built.asked["max_actions"] == 2
    built.as_dict()["asked"]["max_actions"] = 98
    assert built.as_dict()["asked"]["max_actions"] == 2


# --- the file -------------------------------------------------------------------------------------


def test_the_queue_holds_at_most_thirty_two_entries_and_one_per_run():
    assert MAX_QUEUE == 32
    QueueFile(1, entries_of(MAX_QUEUE))
    with pytest.raises(ContractError):
        QueueFile(1, entries_of(MAX_QUEUE + 1))
    with pytest.raises(ContractError):
        QueueFile(1, (entry("task-1-r1"), entry("task-1-r1", kind="resume")))
    with pytest.raises(ContractError):
        QueueFile(-1, ())


def test_an_absent_file_reads_as_revision_zero_and_no_entries(tmp_path):
    assert QueueStore(tmp_path).read() == QueueFile(0, ())


def test_a_write_takes_the_revision_one_further_and_is_read_back(tmp_path):
    store = QueueStore(tmp_path)
    first = store.write((entry("task-1-r1"),))
    second = store.write((entry("task-1-r1"), entry("task-2-r1", kind="resume")))
    assert (first.revision, second.revision) == (1, 2)
    assert store.read() == second
    assert [row.run_id for row in second.entries] == ["task-1-r1", "task-2-r1"]


def test_the_file_is_canonical_json_with_unix_line_ends_and_leaves_no_stage_behind(tmp_path):
    store = QueueStore(tmp_path)
    written = store.write((entry(),))
    path = data_root(tmp_path) / "queue" / "queue.json"
    assert store.path == path
    raw = path.read_bytes()
    assert raw == (canonical_json(written.as_dict()) + "\n").encode("utf-8") and b"\r" not in raw
    assert sorted(child.name for child in path.parent.iterdir()) == ["queue.json"]


def test_a_write_takes_entries_and_nothing_else(tmp_path):
    store = QueueStore(tmp_path)
    for wrong in (entry(), [entry()], ({"run_id": "x"},), None):
        with pytest.raises(StoreError):
            store.write(wrong)
    assert store.read() == QueueFile(0, ())


@pytest.mark.parametrize("text", [
    "{not json", "[]", '{"schema_version": 2, "revision": 1, "entries": []}',
    '{"schema_version": 1, "revision": "1", "entries": []}',
    '{"schema_version": 1, "revision": 1}',
    '{"schema_version": 1, "revision": 1, "entries": [], "note": 1}',
    '{"schema_version": 1, "revision": 1, "entries": [{}]}',
    '{"schema_version": true, "revision": 1, "entries": []}',
])
def test_a_file_that_is_not_a_record_of_the_contract_is_corrupt_and_names_no_path(
        tmp_path, text):
    store = QueueStore(tmp_path)
    store.write(())
    store.path.write_bytes(text.encode("utf-8"))
    with pytest.raises(CorruptQueue) as refused:
        store.read()
    assert str(tmp_path) not in str(refused.value) and "queue.json" not in str(refused.value)
    assert isinstance(refused.value, StoreError)


def test_a_second_name_for_the_file_is_a_route_the_store_does_not_own(tmp_path):
    store = QueueStore(tmp_path)
    store.write(())
    os.link(store.path, tmp_path / "second-name")
    for call in (store.read, lambda: store.write(())):
        with pytest.raises(RouteNotOwned):
            call()


def test_a_queue_that_is_a_file_and_not_a_directory_is_a_route_the_store_does_not_own(tmp_path):
    store = QueueStore(tmp_path)
    store.path.parent.parent.mkdir(parents=True, exist_ok=True)
    store.path.parent.write_bytes(b"not a directory")
    for call in (store.read, lambda: store.write(())):
        with pytest.raises(RouteNotOwned):
            call()


# --- the receipts ---------------------------------------------------------------------------------


def test_a_receipt_lives_at_run_kind_and_record_under_started(tmp_path):
    store = QueueStore(tmp_path)
    store.write_receipt(receipt())
    path = (data_root(tmp_path) / "queue" / "started" / "task-1-r1" / "run_authorization"
            / "grant-1.json")
    assert path.is_file()
    assert store.receipt_path("task-1-r1", "run_authorization", "grant-1") == path
    assert store.read_receipt("task-1-r1", "run_authorization", "grant-1") == receipt()


def test_an_absent_receipt_reads_as_none(tmp_path):
    assert QueueStore(tmp_path).read_receipt("task-1-r1", "run_authorization", "grant-1") is None


def test_a_confirmation_receipt_has_ten_keys_and_a_flag_receipt_twelve():
    assert list(receipt().as_dict()) == [
        "schema_version", "run_id", "kind", "record_id", "authorized_by", "preauthorized_at",
        "digest", "record_digest", "started_at", "admission"]
    flag = receipt(kind="run_authorization_control", admission="auto_continue",
                   flag_id="flag-1", transition_id="transition-1").as_dict()
    assert len(flag) == 12 and flag["flag_id"] == "flag-1"
    assert flag["transition_id"] == "transition-1"


@pytest.mark.parametrize("changes", [
    {"admission": "auto_continue"},                                    # no flag, no transition
    {"admission": "auto_continue", "flag_id": "flag-1"},               # no transition
    {"flag_id": "flag-1", "transition_id": "transition-1"},            # a flag on a confirmation
    {"admission": "by_hand"}, {"kind": "decision"}, {"record_id": "not safe!"},
    {"digest": "x"}, {"record_digest": ""}, {"started_at": "now"}, {"preauthorized_at": ""},
    {"authorized_by": ""},
])
def test_a_receipt_the_contract_refuses_cannot_be_built(changes):
    with pytest.raises(ContractError):
        receipt(**changes)


def test_a_receipt_is_created_exclusively_and_a_second_create_is_refused_untouched(tmp_path):
    store = QueueStore(tmp_path)
    store.write_receipt(receipt())
    path = store.receipt_path("task-1-r1", "run_authorization", "grant-1")
    before = path.read_bytes()
    with pytest.raises(ReceiptExists):
        store.write_receipt(receipt(started_at="2026-09-30T10:06:00Z"))
    assert path.read_bytes() == before


def test_an_orphan_receipt_is_replaced_by_the_one_call_that_says_so(tmp_path):
    store = QueueStore(tmp_path)
    store.write_receipt(receipt())
    later = receipt(started_at="2026-09-30T10:06:00Z")
    store.replace_receipt(later)
    assert store.read_receipt("task-1-r1", "run_authorization", "grant-1") == later


def test_a_replace_of_a_receipt_that_is_not_there_creates_it(tmp_path):
    store = QueueStore(tmp_path)
    store.replace_receipt(receipt())
    assert store.read_receipt("task-1-r1", "run_authorization", "grant-1") == receipt()


def test_equal_record_ids_in_two_runs_and_two_kinds_are_four_files(tmp_path):
    store = QueueStore(tmp_path)
    four = [receipt(run_id=run, kind=kind, record_id="same")
            for run in ("task-1-r1", "task-2-r1")
            for kind in ("run_authorization", "run_authorization_control")]
    for one in four:
        store.write_receipt(one)
    assert len({store.receipt_path(one.run_id, one.kind, one.record_id) for one in four}) == 4
    for one in four:
        assert store.read_receipt(one.run_id, one.kind, one.record_id) == one


@pytest.mark.parametrize("text", [
    "{not json", "[]", "{}", "null",
])
def test_a_receipt_file_that_is_not_a_record_is_corrupt_and_names_no_path(tmp_path, text):
    store = QueueStore(tmp_path)
    store.write_receipt(receipt())
    store.receipt_path("task-1-r1", "run_authorization", "grant-1").write_bytes(text.encode())
    with pytest.raises(CorruptReceipt) as refused:
        store.read_receipt("task-1-r1", "run_authorization", "grant-1")
    assert str(tmp_path) not in str(refused.value) and isinstance(refused.value, StoreError)


def test_a_receipt_that_names_another_key_than_its_path_is_corrupt(tmp_path):
    store = QueueStore(tmp_path)
    store.write_receipt(receipt())
    path = store.receipt_path("task-1-r1", "run_authorization", "grant-1")
    path.write_bytes((canonical_json(receipt(record_id="grant-2").as_dict()) + "\n").encode())
    with pytest.raises(CorruptReceipt):
        store.read_receipt("task-1-r1", "run_authorization", "grant-1")


@pytest.mark.parametrize("record_id", ["NUL", "con.txt", "LPT1", "ends.", "AUX"])
def test_a_record_id_that_is_a_windows_device_or_ends_in_a_dot_is_refused_before_any_file(
        tmp_path, record_id):
    store = QueueStore(tmp_path)
    with pytest.raises(WindowsNameError):
        store.write_receipt(receipt(record_id=record_id))
    with pytest.raises(WindowsNameError):
        store.replace_receipt(receipt(record_id=record_id))
    assert not (data_root(tmp_path) / "queue").exists()


def test_a_receipt_whose_directory_is_a_second_name_of_another_file_is_not_owned(tmp_path):
    store = QueueStore(tmp_path)
    store.write_receipt(receipt())
    path = store.receipt_path("task-1-r1", "run_authorization", "grant-1")
    os.link(path, tmp_path / "second-name")
    with pytest.raises(RouteNotOwned):
        store.read_receipt("task-1-r1", "run_authorization", "grant-1")
    with pytest.raises(RouteNotOwned):
        store.replace_receipt(receipt(started_at="2026-09-30T10:06:00Z"))
