"""A graph is a durable record of one run, written once and never edited.

The definition contract next door says what a graph IS. This module says what
the store does with one: it is a record kind like the six before it, it obeys
the same identity and idempotency rules, and it carries one extra relation this
alpha needs -- a run follows ONE graph.

That last rule is not identity. Two graphs with different ids are two different
identities, and a store that took both would leave every reader to guess which
one the run is actually following. Editing, versioning and templates are a later
slice; until they land, a second graph is a question this product cannot answer,
so it is refused rather than stored beside the first.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
)
from conductor.command.run_store import RecordConflict, RunStore, snapshot_digest
from tests.alpha3_graph_artifacts import dalio_definition
from tests.test_command_run_store import CONFIG, a_run

RUN_ID = "run-001"


def a_store(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, config_digest=snapshot_digest(CONFIG)), CONFIG)
    return store


def journal_lines(store):
    text = (store.run_path(RUN_ID) / "records.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def a_graph(**changes):
    return dalio_definition(run_id=RUN_ID, **changes)


def another_shape(graph_id="graph-dalio"):
    """A different plan under whichever id the caller names."""
    nodes = (
        GraphNode(node_id="collect", kind="task", title="Collect"),
        GraphNode(node_id="gate", kind="gate", title="Gate", gate_id="gate-1"),
        GraphNode(node_id="apply", kind="task", title="Apply",
                  instance_id="claude-dev", capability="dispatch"),
    )
    return GraphDefinition(
        graph_id=graph_id, run_id=RUN_ID, created_at="2026-08-19T09:00:00Z",
        nodes=nodes, edges=(GraphEdge(from_node="collect", to_node="gate"),
                            GraphEdge(from_node="gate", to_node="apply")))


# -- a graph is a record like the six before it --------------------------------


def test_a_graph_is_appended_as_its_own_record_kind_and_recovered_whole(tmp_path):
    store = a_store(tmp_path)
    graph = a_graph()

    assert store.append(graph) is True

    recovered = store.read(RUN_ID)
    rows = [row for row in recovered.records if row.kind == "graph_definition"]
    assert len(rows) == 1
    assert rows[0].value.as_dict() == graph.as_dict()
    assert rows[0].value.digest() == graph.digest()


def test_the_journal_holds_the_graph_in_the_one_canonical_spelling(tmp_path):
    """The store re-encodes every line it reads; a graph is no exception."""
    store = a_store(tmp_path)
    store.append(a_graph())
    wrappers = journal_lines(store)
    assert [row["record_type"] for row in wrappers] == ["graph_definition"]
    assert set(wrappers[0]) == {"record", "record_type"}
    assert GraphDefinition.from_dict(wrappers[0]["record"]).as_dict() == (
        wrappers[0]["record"])


def test_an_identical_graph_is_a_retry_and_writes_no_second_line(tmp_path):
    store = a_store(tmp_path)
    assert store.append(a_graph()) is True
    assert store.append(a_graph()) is False
    assert len(journal_lines(store)) == 1


def test_the_same_graph_id_carrying_different_facts_is_a_conflict(tmp_path):
    store = a_store(tmp_path)
    store.append(a_graph())
    with pytest.raises(RecordConflict, match="already records different facts"):
        store.append(another_shape(graph_id="graph-dalio"))
    assert len(journal_lines(store)) == 1


# -- one run follows one graph -------------------------------------------------


def test_a_second_graph_under_another_id_is_refused_and_the_first_stands(tmp_path):
    store = a_store(tmp_path)
    store.append(a_graph())
    with pytest.raises(RecordConflict, match="one run carries one graph"):
        store.append(another_shape(graph_id="graph-second"))
    rows = [row for row in store.read(RUN_ID).records
            if row.kind == "graph_definition"]
    assert [row.value.graph_id for row in rows] == ["graph-dalio"]


def test_the_refusal_names_the_graph_the_run_already_follows(tmp_path):
    """An operator has to know WHICH plan is standing, not merely that one is."""
    store = a_store(tmp_path)
    store.append(a_graph())
    with pytest.raises(RecordConflict) as caught:
        store.append(another_shape(graph_id="graph-second"))
    assert "graph-dalio" in str(caught.value)


def test_a_run_that_never_took_a_graph_carries_none(tmp_path):
    store = a_store(tmp_path)
    assert [row for row in store.read(RUN_ID).records
            if row.kind == "graph_definition"] == []


def test_a_graph_may_be_written_after_a_run_already_holds_other_records(tmp_path):
    """Nothing about the graph depends on being first; it is one more record."""
    store = a_store(tmp_path)
    store.append(a_graph())
    recovered = store.read(RUN_ID)
    assert recovered.warnings == ()
    assert [row.kind for row in recovered.records] == ["graph_definition"]
