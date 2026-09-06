"""The fourth graph key: what the plan permits, served from Python.

A run read carried two readings of a plan and now carries three. The definition
says what was INTENDED, the runtime says what was OBSERVED, and the schedule
says what those two together PERMIT. Only the third can answer "where could this
step go next", and until it existed the browser answered it by walking the edge
list -- which was true only while no road could carry a condition. Afterwards it
would have told a person that approving opens a step their approval closes.

What is held here:

- the shape, in both directions, including the run that follows no plan and
  answers a fourth null rather than an absent key;
- that the answer is the SCHEDULE's own, entry for entry, rather than a second
  computation that happens to agree today;
- that a conditional road is reported with its word, because the word is the
  whole of what a consumer cannot derive for itself.
"""
from __future__ import annotations

from conductor.command.graph_projection import graph_payload
from conductor.command.graph_schedule import schedule
from conductor.command.run_store import (
    RecoveredRun,
    StoredRecord,
    _record_parts,
    snapshot_digest,
)
from tests.schedule_journal import NOW, Journal, routed_dalio, through_the_body
from tests.test_command_run_store import CONFIG, a_run

RUN_ID = "run-001"


def recovered(journal=None, *, plan=True) -> RecoveredRun:
    """One replayed run, assembled rather than written through the store.

    `graph_payload` is a pure function of a recovered run, and these witnesses
    are about what it ANSWERS. Driving the journals through `store.append`
    would make each of them also a test of the store's causal relations -- a
    request here repeats no proposal, which those relations rightly refuse and
    which has nothing to do with the shape under test.
    """
    values = [] if not plan else [routed_dalio()]
    values.extend(journal.rows() if journal is not None else ())
    return RecoveredRun(
        envelope=a_run(run_id=RUN_ID, mode="confirm",
                       config_digest=snapshot_digest(CONFIG)),
        config=CONFIG,
        records=tuple(StoredRecord(_record_parts(value)[0], value)
                      for value in values),
        warnings=())


def payload_of(journal=None, *, plan=True):
    return graph_payload(recovered(journal, plan=plan))


# -- the shape ----------------------------------------------------------------


def test_the_graph_half_of_a_run_read_now_carries_five_keys():
    """The fifth is `success_criteria`: what counts as success for each
    step, derived from the rules that operate rather than stored. It sits
    BESIDE the definition rather than inside it, because a plan's bytes
    are what its digest is taken over."""
    payload = payload_of()

    assert set(payload) == {
        "definition", "definition_digest", "runtime", "schedule",
        "success_criteria"}


def test_a_run_that_follows_no_plan_answers_nulls_and_no_criteria():
    """Nulls rather than absent keys, for the reason the others are: a
    reader telling "no plan" from "old server" by shape is guessing.

    The criteria answer an empty MAP rather than a null, and the
    difference is honest: the other four are one document that is not
    there, and this is a per-step reading over no steps.
    """
    payload = payload_of(plan=False)

    assert payload == {"definition": None, "definition_digest": None,
                       "runtime": None, "schedule": None,
                       "success_criteria": {}}


def test_the_schedule_states_the_run_word_and_the_three_subsets():
    payload = payload_of()["schedule"]

    assert set(payload) == {
        "run_state", "runnable", "settled", "unreachable", "nodes"}
    assert payload["run_state"] == "open"
    assert payload["runnable"] == ["goal"]
    assert payload["settled"] == [] and payload["unreachable"] == []


def test_every_step_reports_its_standing_and_its_roads():
    rows = payload_of()["schedule"]["nodes"]

    assert set(rows[0]) == {
        "node_id", "state", "opened_by", "blocked_by", "closed_by", "opens",
        "required_pass", "settled_laps", "attempts_spent",
        "awaiting_artifacts", "answerable"}
    # The third reason a step can be blocked reaches the window as its own key
    # rather than inside `blocked_by`, which carries predecessors and is
    # rendered beside a sentence about roads.
    assert all(row["awaiting_artifacts"] == [] for row in rows), rows
    assert [row["node_id"] for row in rows] == [
        "goal", "identify", "diagnose", "design", "confirm-gate", "do",
        "result-gate", "retry-loop"]


def _answerable(journal) -> dict[str, str | None]:
    return {row["node_id"]: row["answerable"]
            for row in payload_of(journal)["schedule"]["nodes"]}


def test_a_gate_row_says_whether_an_answer_would_be_admitted_and_how():
    """`answerable` is the decision DOOR's own verdict, served on the read.

    R02 of the Codex review of `8dec0e4` asked that the live door, the
    authorize hold and the screen live by ONE rule. The screen cannot compute
    laps without a second copy of the arithmetic, so the read carries the
    door's answer: `first` for an arrived gate nothing stands on, `supersede`
    where the standing answer may be replaced -- this lap's answer taken back,
    or a reopened lap the plan has reached again -- `none` where the door would
    refuse, and `null` on a step that is not a gate. Walked in order, because
    each state is a different arm.
    """
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    first = _answerable(journal)
    assert first["goal"] is None and first["do"] is None
    assert first["retry-loop"] is None
    assert first["result-gate"] == "first"
    assert first["confirm-gate"] == "supersede"

    journal.decide("gate-result", "request_changes")
    reopened = _answerable(journal)
    assert reopened["result-gate"] == "supersede"
    assert reopened["confirm-gate"] == "supersede"

    journal.did("identify")
    moved = _answerable(journal)
    assert moved["result-gate"] == "none"
    assert moved["confirm-gate"] == "none"

    journal.did("diagnose")
    journal.did("design")
    reached = _answerable(journal)
    assert reached["confirm-gate"] == "supersede"
    assert reached["result-gate"] == "none"


def test_a_run_that_recorded_its_ending_answers_none_on_every_gate():
    """The door refuses every receipt on an ended run before it asks the plan.

    A word served from the plan alone said `supersede` about the result gate
    of a run nothing can be added to -- the slice review's probe watched the
    POST answer 409 `run_terminal` beside it. The read now says what the door
    will say, on every gate at once.
    """
    from conductor.command.run_terminal import RunTerminal

    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "approve")
    computed = schedule(routed_dalio(), journal.rows())
    assert computed.run_state == "complete"
    open_words = _answerable(journal)
    assert open_words["result-gate"] == "supersede", open_words

    journal.values.append(RunTerminal(
        terminal_id="terminal-1", run_id=RUN_ID, graph_id=routed_dalio().graph_id,
        state=computed.run_state, settled_nodes=computed.settled,
        unreachable_nodes=computed.unreachable, recorded_at=NOW))

    ended = _answerable(journal)
    assert {ended[node] for node in ("confirm-gate", "result-gate")} == {"none"}
    assert ended["goal"] is None


# -- it is the schedule's own answer, not a second one ------------------------


def test_the_payload_is_the_schedule_entry_for_entry():
    """Compared to the computation itself rather than to a copy of its rules,
    so a serializer that drifted from the owner reds here."""
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")
    replayed = recovered(journal)

    served = graph_payload(replayed)["schedule"]
    computed = schedule(routed_dalio(),
                        tuple(row.value for row in replayed.records))

    assert served["run_state"] == computed.run_state
    assert served["runnable"] == list(computed.runnable)
    assert served["settled"] == list(computed.settled)
    assert served["unreachable"] == list(computed.unreachable)
    for row, source in zip(served["nodes"], computed.nodes, strict=True):
        assert row["node_id"] == source.node_id
        assert row["state"] == source.state
        assert row["required_pass"] == source.required_pass
        assert row["settled_laps"] == source.settled_laps
        assert row["attempts_spent"] == source.attempts_spent
        assert row["blocked_by"] == list(source.blocked_by)


# -- a road carries its word --------------------------------------------------


def test_a_conditional_road_is_served_with_the_word_it_opens_on():
    """The one fact a consumer cannot derive: a bare edge list says WHERE a
    road goes and never on WHAT it opens."""
    rows = payload_of()["schedule"]["nodes"]
    gate = next(row for row in rows if row["node_id"] == "confirm-gate")
    plain = next(row for row in rows if row["node_id"] == "goal")

    assert gate["opens"] == [{"to_node": "do", "condition": "on_approved"}]
    assert plain["opens"] == [{"to_node": "identify", "condition": None}]


def test_a_closed_road_is_reported_with_who_closed_it():
    """An approval at the result gate ends the cycle, and the screen must be
    able to say which step took the other road."""
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "approve")

    served = payload_of(journal)["schedule"]
    loop = next(row for row in served["nodes"]
                if row["node_id"] == "retry-loop")

    assert served["run_state"] == "complete"
    assert served["unreachable"] == ["retry-loop"]
    assert loop["closed_by"] == ["result-gate"]
