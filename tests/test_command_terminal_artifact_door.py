"""The fourth write door: publishing a document on a run that has ended.

`POST /command/runs/<id>/artifacts` shipped without the hold the other three
carry, and the answer it gave was the worst one available. The operator was told
`201` -- their document was durable -- and the row landed behind the run's
`run_terminal`, so every read of that run from then on answered `run_corrupt`:
the run, its controls, `store.read`, and every other write door. The product
bricked a run through its own front door and then reported the journal as
corrupt.

The three doors that already held it are next door in
`tests/test_command_run_terminal_doors.py`, together with the depth beneath all
four. This door needs a module of its own because it is the only one whose
refusal has to sit in a particular PLACE rather than merely exist:

- it refuses about RECORDS, so it is asked AFTER the identity lookup. An exact
  retry of a document that stands BEFORE the terminal appends nothing, so there
  is nothing for the ending to refuse and the answer is still `200`;
- the same `artifact_id` carrying different facts is still `record_conflict`,
  because a caller contradicting their own durable record is doing that whether
  or not the run has finished;
- and it is asked strictly BEFORE the clock and the append, so a refusal reads
  no instant, writes no byte and publishes no frame.

Every witness reads `records.jsonl` as BYTES either side of the call, because
"the record is absent" would also be true of a journal that had been rewritten,
and reads the run back afterwards, because a `409` that arrived after the append
would say the right word about a journal it had already broken.
"""
from __future__ import annotations

from conductor.command.api_contracts import ERROR_STATUS
from tests.test_command_artifacts import body
from tests.test_command_http_api import (
    RUN_ID,
    api,
    decision_body,
    get_headers,
    post,
)
from tests.test_command_run_terminal_doors import (
    NOW,
    a_gated_plan,
    a_run_that_ends,
    journal_bytes,
)
from tests.test_command_schema_doubles import DeepDispatchAdapter


def a_run_ending_after_an_artifact(tmp_path, **api_changes):
    """The same run, with one document published while it was still open.

    The document stands BEFORE the terminal, which is what makes the three
    witnesses that use it about the door's placement rather than about the word
    it says: the retry, the conflict and the later read all have something
    durable to be answered from.
    """
    subject, store, events = api(
        tmp_path, adapters=[DeepDispatchAdapter()], **api_changes)
    store.append(a_gated_plan())
    published = post(subject, f"/command/runs/{RUN_ID}/artifacts", body())
    assert published.status == 201
    answered = post(subject, f"/command/runs/{RUN_ID}/decisions", decision_body())
    assert answered.status == 201
    return subject, store, events


def test_an_artifact_after_the_terminal_is_refused_and_writes_no_byte(tmp_path):
    """Witness 18, road four -- the road that bricked a real journal.

    Five facts, because the status alone would also be true of a door that
    refused after doing the work: no byte moved, no frame was published, the run
    is still readable, and it still carries exactly the three records it ended
    with.

    The clock is the fifth, and it is the one fact this DOOR alone owns. The
    store refuses the same append beneath it, so a boundary that had no hold at
    all would still answer `run_terminal` and still write nothing -- having first
    minted a `created_at` for a document that was never going to exist. A
    timestamp read for a refused request is a reading of when nothing happened,
    and it is the only evidence left that the hold is asked before the work
    rather than after it.
    """
    ticks = []
    subject, store, events = a_run_that_ends(
        tmp_path, clock=lambda: ticks.append(NOW) or NOW)
    before, published, read_by_now = (
        journal_bytes(store), list(events), len(ticks))

    refused = post(subject, f"/command/runs/{RUN_ID}/artifacts", body())

    assert refused.status == ERROR_STATUS["run_terminal"]
    assert refused.payload["error"]["code"] == "run_terminal"
    assert journal_bytes(store) == before
    assert list(events) == published
    assert len(ticks) == read_by_now
    read = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers())
    assert read.status == 200
    assert [row.kind for row in store.read(RUN_ID).records] == [
        "graph_definition", "decision", "run_terminal"]


def test_an_artifact_standing_before_the_terminal_is_answered_by_its_exact_retry(
        tmp_path):
    """The hold is about RECORDS, so it stands after the identity branch.

    An exact retry of a document this run already carries appends nothing --
    that is the whole of what `200` means on this route -- so there is no record
    for the ending to refuse. Asked before the identity lookup instead, the same
    hold would answer `409` to a request that changes nothing: a caller retrying
    a document published hours before the run ended would be told the publish
    failed. The clock is counted because a `200` must not read one either.
    """
    ticks = []
    subject, store, _ = a_run_ending_after_an_artifact(
        tmp_path, clock=lambda: ticks.append(NOW) or NOW)
    standing = store.read(RUN_ID).records[1].value
    before, read_by_now = journal_bytes(store), len(ticks)

    retried = post(subject, f"/command/runs/{RUN_ID}/artifacts", body())

    assert retried.status == 200
    assert retried.payload == standing.as_dict()
    assert journal_bytes(store) == before
    assert len(ticks) == read_by_now
    assert store.read(RUN_ID).warnings == ()


def test_a_conflicting_artifact_after_the_terminal_is_still_a_record_conflict(
        tmp_path):
    """The other half of the placement: one id may never carry two answers.

    The same identity with different content is a caller contradicting their own
    durable record, and the run's ending does not change what that is. A hold
    asked before the identity branch would rename this refusal, and a client
    told `run_terminal` would look for somewhere else to publish instead of
    fixing the id it reused.
    """
    subject, store, _ = a_run_ending_after_an_artifact(tmp_path)
    before = journal_bytes(store)

    refused = post(subject, f"/command/runs/{RUN_ID}/artifacts",
                   body(content="Different durable bytes."))

    assert refused.status == ERROR_STATUS["record_conflict"]
    assert refused.payload["error"]["code"] == "record_conflict"
    assert journal_bytes(store) == before


def test_the_pre_terminal_artifact_is_still_read_after_the_refused_post(tmp_path):
    """A refused publish leaves the run exactly as readable as it was.

    A NEW document -- a new id, nothing standing to answer from -- is refused,
    and the document published before the ending is still served. A door that
    held after its append would say the same word here and brick both.

    The clock is counted here as well as on the empty run above, and for a
    reason the pair alone makes visible: a hold that skipped itself whenever the
    run already carried an artifact would still be answered `run_terminal` by
    the store, write no byte, and read back clean. Only the instant it minted
    for a document that was never going to exist would move -- and only on a run
    that HAS one, which is the shape the other witness cannot reach.
    """
    ticks = []
    subject, store, _ = a_run_ending_after_an_artifact(
        tmp_path, clock=lambda: ticks.append(NOW) or NOW)
    read_by_now = len(ticks)

    refused = post(subject, f"/command/runs/{RUN_ID}/artifacts",
                   body(artifact_id="artifact-document-002"))
    read = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers())

    assert refused.status == ERROR_STATUS["run_terminal"]
    assert refused.payload["error"]["code"] == "run_terminal"
    assert len(ticks) == read_by_now
    assert read.status == 200
    assert [row["record_type"] for row in read.payload["records"]].count(
        "artifact") == 1
    assert [row.kind for row in store.read(RUN_ID).records] == [
        "graph_definition", "artifact", "decision", "run_terminal"]
