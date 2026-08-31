"""A run records that its plan ENDED, once, and nothing follows it.

The verdict is durable rather than computed, and the reason is monotonicity: a
superseding decision can flip a gate from satisfied to failed, closing one road
and opening another, so a run a person was told had finished would silently
reopen behind them. Writing it down makes *this run ended* a fact later records
are judged against.

What this module holds, and how each claim fails on its own:

- **it is a record kind like the nine before it.** Same identity rule, same
  idempotent retry, same canonical wrapper, same replay.
- **it belongs to a plan.** A run following no graph has no terminal to record
  and no `graph_id` to name one with, so the record is refused outright -- which
  is also the whole reason no journal written before graphs can ever hold one.
- **it happens once.** A second terminal under any id is refused, so one
  identity can never carry two sets of facts recorded at two instants.
- **nothing follows it.** The whole-journal rule, held on the raw-replay road
  where a hand-written journal arrives.

**OWED, and deliberately absent here:** the design's third relation -- that the
recorded partitions equal what `graph_schedule.schedule` recomputes from this
run's own prior records. That module lands in the next commit and this one does
not write a relation against a function it cannot call. Nothing in this commit
appends a terminal on any production road, so no road reaches the gap.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.contracts import ContractError, canonical_json
from conductor.command.run_store import (
    CorruptRun,
    RecordConflict,
    RunStore,
    StoreError,
    snapshot_digest,
)
from conductor.command.run_terminal import TERMINAL_STATES, RunTerminal
from conductor.command import run_store as run_store_module
from tests.alpha3_graph_artifacts import dalio_definition
from tests.test_command_run_store import CONFIG, a_run

RUN_ID = "run-001"
NOW = "2026-08-30T10:00:00Z"
#: The Dalio plan's own node ids, in definition order, which is the order the
#: record's two partitions are written in.
PLANNED = ("goal", "identify", "diagnose", "design", "confirm-gate", "do",
           "result-gate", "retry-loop")


def a_store(tmp_path, *, with_graph=True):
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, config_digest=snapshot_digest(CONFIG)), CONFIG)
    if with_graph:
        store.append(dalio_definition(run_id=RUN_ID))
    return store


def a_terminal(**changes) -> RunTerminal:
    values = {
        "terminal_id": "terminal-001", "run_id": RUN_ID,
        "graph_id": "graph-dalio", "state": "complete",
        "settled_nodes": PLANNED[:-1], "unreachable_nodes": ("retry-loop",),
        "recorded_at": NOW,
    }
    values.update(changes)
    return RunTerminal(**values)


def journal_lines(store):
    text = (store.run_path(RUN_ID) / "records.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


# -- the record contract -------------------------------------------------------


def test_the_terminal_carries_the_verdict_and_the_two_partitions_and_no_more():
    """It restates no node phase, no outcome and no pass count: those stay
    computed, where a second copy could not disagree with the first."""
    terminal = a_terminal()

    assert set(terminal.as_dict()) == set(RunTerminal._FIELDS)
    assert set(RunTerminal._FIELDS) == {
        "schema_version", "terminal_id", "run_id", "graph_id", "state",
        "settled_nodes", "unreachable_nodes", "recorded_at"}
    assert terminal.schema_version == 2


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES))
def test_a_run_may_end_on_either_of_the_two_words(state):
    assert a_terminal(state=state).state == state


@pytest.mark.parametrize("state", ["open", "", "COMPLETE", "running", None, 1])
def test_a_state_that_is_not_an_ending_is_refused(state):
    """`open` above all: a run that has not ended has nothing to record, and a
    record saying "not yet" goes stale the instant after it is written."""
    with pytest.raises(ContractError):
        a_terminal(state=state)


def test_open_is_never_a_word_this_record_can_carry():
    assert "open" not in TERMINAL_STATES
    assert TERMINAL_STATES == frozenset({"complete", "stalled"})


def test_a_node_recorded_as_both_settled_and_unreachable_is_refused():
    """A step is one or the other; both is a verdict that contradicts itself."""
    with pytest.raises(ContractError, match="never both"):
        a_terminal(settled_nodes=("goal", "do"), unreachable_nodes=("do",))


def test_a_partition_repeating_a_node_is_refused():
    with pytest.raises(ContractError):
        a_terminal(settled_nodes=("goal", "goal"))


def test_both_partitions_may_be_empty_only_where_the_plan_supports_it():
    """No shape rule ties the two together; the relation that does is the
    schedule's, and it arrives with the schedule."""
    terminal = a_terminal(state="stalled", settled_nodes=(),
                          unreachable_nodes=())

    assert (terminal.settled_nodes, terminal.unreachable_nodes) == ((), ())


def test_the_record_round_trips_through_its_own_canonical_document():
    terminal = a_terminal()

    rebuilt = RunTerminal.from_dict(terminal.as_dict())

    assert rebuilt == terminal
    assert rebuilt.as_dict() == terminal.as_dict()
    assert canonical_json(rebuilt.as_dict()) == canonical_json(terminal.as_dict())


def test_a_document_carrying_a_field_this_record_has_no_place_for_is_refused():
    with pytest.raises(ContractError, match="unsupported field"):
        RunTerminal.from_dict({**a_terminal().as_dict(), "run_state": "open"})


@pytest.mark.parametrize("missing", [
    "terminal_id", "run_id", "graph_id", "state", "settled_nodes",
    "unreachable_nodes", "recorded_at"])
def test_every_fact_but_the_schema_is_required(missing):
    document = a_terminal().as_dict()
    document.pop(missing)
    with pytest.raises(ContractError):
        RunTerminal.from_dict(document)


# -- it is a record kind like the nine before it -------------------------------


def test_the_terminal_is_the_tenth_record_kind_the_store_knows():
    contract, identity = run_store_module._RECORDS["run_terminal"]

    assert (contract, identity) == (RunTerminal, "terminal_id")
    assert len(run_store_module._RECORDS) == 10


def test_a_terminal_is_appended_and_recovered_whole(tmp_path):
    store = a_store(tmp_path)
    terminal = a_terminal()

    assert store.append(terminal) is True

    rows = [row for row in store.read(RUN_ID).records
            if row.kind == "run_terminal"]
    assert len(rows) == 1
    assert rows[0].value == terminal


def test_the_journal_holds_the_terminal_in_the_one_canonical_spelling(tmp_path):
    store = a_store(tmp_path)
    store.append(a_terminal())

    wrapper = journal_lines(store)[-1]

    assert set(wrapper) == {"record", "record_type"}
    assert wrapper["record_type"] == "run_terminal"
    assert RunTerminal.from_dict(wrapper["record"]).as_dict() == wrapper["record"]


def test_an_identical_terminal_is_a_retry_and_writes_no_second_line(tmp_path):
    """The first of the three roads a second append can take."""
    store = a_store(tmp_path)

    assert store.append(a_terminal()) is True
    assert store.append(a_terminal()) is False

    assert [row["record_type"] for row in journal_lines(store)] == [
        "graph_definition", "run_terminal"]


def test_the_same_terminal_id_carrying_different_facts_is_a_conflict(tmp_path):
    """The second road: one identity may never carry two verdicts."""
    store = a_store(tmp_path)
    store.append(a_terminal())

    with pytest.raises(RecordConflict, match="already records different facts"):
        store.append(a_terminal(state="stalled"))

    assert len(journal_lines(store)) == 2


# -- a terminal belongs to a plan ---------------------------------------------


def test_a_run_that_follows_no_graph_has_no_terminal_to_record(tmp_path):
    """The whole of the plan-less exemption, from the other side: such a run
    can never hold one, so every rule keyed off a standing terminal is vacuous
    for every journal written before graphs existed."""
    store = a_store(tmp_path, with_graph=False)

    with pytest.raises(StoreError, match="follows no graph"):
        store.append(a_terminal())

    assert journal_lines(store) == []


def test_a_terminal_naming_a_graph_this_run_does_not_follow_is_refused(tmp_path):
    store = a_store(tmp_path)

    with pytest.raises(StoreError, match="graph-elsewhere"):
        store.append(a_terminal(graph_id="graph-elsewhere"))

    assert [row["record_type"] for row in journal_lines(store)] == [
        "graph_definition"]


# -- a run records its terminal once ------------------------------------------


def test_a_second_terminal_under_another_id_is_refused_and_the_first_stands(
        tmp_path):
    """The third road, and the one a fresh id would otherwise walk straight
    through: nothing is re-minted, so two calls at two instants cannot record
    two different sets of facts."""
    store = a_store(tmp_path)
    store.append(a_terminal())

    with pytest.raises(RecordConflict, match="already recorded its terminal"):
        store.append(a_terminal(terminal_id="terminal-002", state="stalled"))

    rows = [row.value for row in store.read(RUN_ID).records
            if row.kind == "run_terminal"]
    assert [row.terminal_id for row in rows] == ["terminal-001"]


def test_the_journal_replays_to_the_same_single_terminal(tmp_path):
    """Replay is a pure function of bytes already written, so it says what the
    append road said, and says it again."""
    store = a_store(tmp_path)
    store.append(a_terminal())

    first = store.read(RUN_ID)
    second = store.read(RUN_ID)

    assert [row.kind for row in first.records] == [
        "graph_definition", "run_terminal"]
    assert [row.value for row in first.records] == [
        row.value for row in second.records]
    assert first.warnings == second.warnings == ()


# -- nothing follows a recorded terminal --------------------------------------


def raw_append(store, kind, value):
    """Write one canonical record straight into the journal, past every door."""
    line = json.dumps({"record": value.as_dict(), "record_type": kind},
                      ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n"
    with (store.run_path(RUN_ID) / "records.jsonl").open("ab") as stream:
        stream.write(line.encode("utf-8"))


def test_a_journal_carrying_a_record_after_its_terminal_is_corrupt(tmp_path):
    """The replay rule, driven the only way it can be driven -- by writing the
    bytes a hostile or a broken writer would have written."""
    store = a_store(tmp_path)
    store.append(a_terminal())
    raw_append(store, "graph_definition",
               dalio_definition(run_id=RUN_ID, graph_id="graph-second"))

    with pytest.raises(CorruptRun, match="follows the run terminal"):
        store.read(RUN_ID)


def test_the_refusal_names_the_kind_that_followed_the_terminal(tmp_path):
    """An operator has to know WHAT came after it, not merely that something
    did -- the journal is append-only and the row cannot be pointed at."""
    store = a_store(tmp_path)
    store.append(a_terminal())
    raw_append(store, "graph_definition",
               dalio_definition(run_id=RUN_ID, graph_id="graph-second"))

    with pytest.raises(CorruptRun) as caught:
        store.read(RUN_ID)

    assert "graph_definition follows the run terminal" in str(caught.value)


def test_a_terminal_that_is_last_replays_clean(tmp_path):
    """The positive control: the rule above is about POSITION and nothing else."""
    store = a_store(tmp_path)
    store.append(a_terminal())

    recovered = store.read(RUN_ID)

    assert [row.kind for row in recovered.records][-1] == "run_terminal"


def test_the_rule_is_vacuous_on_every_journal_that_holds_no_terminal(tmp_path):
    """It cannot change the verdict on any journal that exists, because none
    holds one."""
    store = a_store(tmp_path)

    recovered = store.read(RUN_ID)

    assert [row.kind for row in recovered.records] == ["graph_definition"]
    assert recovered.warnings == ()
