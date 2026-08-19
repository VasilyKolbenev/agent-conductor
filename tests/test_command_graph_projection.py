"""What a run was observed to do, read back out of the records it holds.

The projection is a COMPUTATION, so every claim below is made by appending
durable records through the real store and asking what the plan then looks
like. Nothing here builds a projection by hand: a fixture that agreed with
itself would prove only that two pieces of this test file match.

Two rules give the projection its weight. It says what the journal supports and
never one step further -- an observed boundary is not a product success, and a
gate with two standing decisions is `unknown` rather than the more convenient
of the two. And it shares no word with the definition except the join: what is
a ceiling over there is a position here, and a reader can never confuse them.
"""
from __future__ import annotations

import pytest

from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    DecisionReceipt,
    EvidenceRef,
)
from conductor.command.graph_definition import (
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphNode,
)
from conductor.command.graph_projection import (
    GATE_STATES,
    NODE_PHASES,
    graph_payload,
)
from conductor.command.run_store import RunStore, snapshot_digest
from tests.alpha3_graph_artifacts import dalio_definition
from tests.test_command_run_store import CONFIG, a_run

RUN_ID = "run-001"
NOW = "2026-08-19T09:00:00Z"
ADAPTER = "claude-code"
DO_NODE = "do"
CONFIRM_GATE = "gate-confirm-do"


def a_store(tmp_path, *, with_graph=True):
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    if with_graph:
        store.append(dalio_definition(run_id=RUN_ID))
    return store


def the_node(node_id):
    return next(node for node in dalio_definition(run_id=RUN_ID).nodes
                if node.node_id == node_id)


def a_proposal(node_id=DO_NODE, index=1, binds=True, **changes):
    """A proposal whose facts are the named node's, unless a test moves one.

    `binds` decides whether it SAYS so: an action may do exactly a node's work
    without claiming to be that step of the plan, and the two are different
    documents to a projection.
    """
    node = the_node(node_id)
    body = dict(
        proposal_id=f"proposal-{index}", run_id=RUN_ID,
        attempt_id=f"attempt-{index:03d}", instance_id=node.instance_id,
        capability=node.capability, arguments=node.payload(),
        scope=("src",), proposed_by="claude-dev", proposed_at=NOW,
        timeout_seconds=900, rationale=f"Carry out {node_id}.",
        config_digest=snapshot_digest(CONFIG),
        node_id=node_id if binds else None)
    body.update(changes)
    return ActionProposal(**body)


def a_request(proposal, index=1, **changes):
    body = dict(
        action_id=f"action-{index}", run_id=RUN_ID,
        attempt_id=proposal.attempt_id, instance_id=proposal.instance_id,
        capability=proposal.capability, arguments=dict(proposal.arguments),
        scope=tuple(proposal.scope), requested_by="release-owner",
        requested_at=NOW, idempotency_key=f"dispatch-{proposal.proposal_id}",
        timeout_seconds=proposal.timeout_seconds,
        preview_digest=proposal.preview_digest, mode="confirm",
        node_id=proposal.node_id)
    body.update(changes)
    return ActionRequest(**body)


def an_event(request, phase, index=1, **changes):
    body = dict(
        event_id=f"event-{phase}-{index}", run_id=RUN_ID,
        action_id=request.action_id, attempt_id=request.attempt_id,
        instance_id=request.instance_id, adapter_id=ADAPTER, phase=phase,
        recorded_at=NOW, request_digest=action_request_digest(request),
        recovery_ref=f"recovery-{index}", outcome=None, exit_code=None,
        schema_version=2)
    body.update(changes)
    return AttemptEvent(**body)


def a_result(request, index=1, **changes):
    body = dict(
        receipt_id=f"result-{index}", action_id=request.action_id,
        run_id=RUN_ID, attempt_id=request.attempt_id,
        instance_id=request.instance_id, outcome="succeeded", exit_code=0,
        observed_at="2026-08-19T09:30:00Z", evidence_refs=("evidence-1",))
    body.update(changes)
    return ActionResultReceipt(**body)


def an_evidence(request, index=1, **changes):
    """The verification the bound adapter must have written for a success."""
    body = dict(
        evidence_id=f"evidence-{index}", run_id=RUN_ID, kind="verification",
        uri=f"verification/{request.action_id}", label="dispatch verification",
        created_by=ADAPTER, observed_at=NOW, verification="verified",
        verified_by=ADAPTER, verified_at=NOW)
    body.update(changes)
    return EvidenceRef(**body)


def a_decision(index=1, gate_id=CONFIRM_GATE, **changes):
    body = dict(
        receipt_id=f"decision-{index}", run_id=RUN_ID, gate_id=gate_id,
        action="approve", actor="release-owner",
        decided_at="2026-08-19T09:15:00Z", reason="Reviewed the plan.",
        scope_refs=("src",), config_digest=snapshot_digest(CONFIG))
    body.update(changes)
    return DecisionReceipt(**body)


def payload_of(store):
    return graph_payload(store.read(RUN_ID))


def node_of(payload, node_id):
    return next(row for row in payload["runtime"]["nodes"]
                if row["node_id"] == node_id)


# -- the plan, its digest, and a run that has none -----------------------------


def test_a_run_that_follows_no_graph_answers_three_nulls(tmp_path):
    """A reader must not have to tell "no graph" from "old server" by shape."""
    payload = payload_of(a_store(tmp_path, with_graph=False))
    assert payload == {
        "definition": None, "definition_digest": None, "runtime": None}


def test_the_definition_and_its_digest_are_the_contracts_own(tmp_path):
    graph = dalio_definition(run_id=RUN_ID)
    payload = payload_of(a_store(tmp_path))
    assert payload["definition"] == graph.as_dict()
    assert payload["definition_digest"] == graph.digest()


def test_a_plan_with_no_records_yet_puts_every_node_at_idle(tmp_path):
    """Absence is idle. It is never a phase further on for want of a record."""
    payload = payload_of(a_store(tmp_path))
    rows = payload["runtime"]["nodes"]
    assert [row["node_id"] for row in rows] == [
        node.node_id for node in dalio_definition(run_id=RUN_ID).nodes]
    assert {row["phase"] for row in rows} == {"idle"}
    assert all(row["attempt_ids"] == [] for row in rows)
    assert all(row["outcome"] is None and row["observed_at"] is None
               for row in rows)
    assert payload["runtime"]["run_id"] == RUN_ID
    assert payload["runtime"]["graph_id"] == "graph-dalio"


# -- a node walks only as far as its own records carry it ----------------------


def a_walked_run(tmp_path, *, upto):
    """Append the durable chain for the Do node, stopping where a test asks."""
    store = a_store(tmp_path)
    steps = ("proposed", "requested", "running", "observed", "result")
    proposal, request = a_proposal(), None
    for step in steps[:steps.index(upto) + 1]:
        if step == "proposed":
            store.append(proposal)
        elif step == "requested":
            request = a_request(proposal)
            store.append(request)
        elif step == "running":
            store.append(an_event(request, "effect_lease"))
        elif step == "observed":
            store.append(an_event(
                request, "execution_observed", outcome="succeeded", exit_code=0))
        else:
            store.append(an_evidence(request))
            store.append(a_result(request))
    return store


@pytest.mark.parametrize("upto,phase", [
    ("proposed", "proposed"),
    ("requested", "requested"),
    ("running", "running"),
    ("observed", "observed"),
    ("result", "observed"),
])
def test_a_node_reports_exactly_how_far_its_records_carry_it(
        tmp_path, upto, phase):
    payload = payload_of(a_walked_run(tmp_path, upto=upto))
    assert node_of(payload, DO_NODE)["phase"] == phase
    assert node_of(payload, DO_NODE)["attempt_ids"] == ["attempt-001"]
    assert node_of(payload, "goal")["phase"] == "idle"


def test_an_observed_boundary_is_not_a_product_outcome(tmp_path):
    """Safety law 9: acceptance and observation are not success.

    The attempt event that ends an execution carries an outcome of its own, and
    reading it here would let a lease and a watched exit stand in for the
    immutable result record a product success requires.
    """
    watched = a_walked_run(tmp_path / "watched", upto="observed")
    observed = node_of(payload_of(watched), DO_NODE)
    assert (observed["phase"], observed["outcome"]) == ("observed", None)
    assert observed["evidence_refs"] == [] and observed["observed_at"] is None

    finished = node_of(
        payload_of(a_walked_run(tmp_path / "finished", upto="result")), DO_NODE)
    assert finished["outcome"] == "succeeded"
    assert finished["evidence_refs"] == ["evidence-1"]
    assert finished["observed_at"] == "2026-08-19T09:30:00Z"


def test_an_action_that_names_no_node_is_projected_nowhere(tmp_path):
    """A graph does not make every action part of it."""
    store = a_store(tmp_path)
    unbound = a_proposal(binds=False)
    store.append(unbound)
    store.append(a_request(unbound))
    rows = payload_of(store)["runtime"]["nodes"]
    assert {row["phase"] for row in rows} == {"idle"}
    assert all(row["attempt_ids"] == [] for row in rows)


# -- a gate is what the one decision function says it is -----------------------


def test_a_gate_with_no_receipt_is_idle_and_an_approval_satisfies_it(tmp_path):
    store = a_store(tmp_path)
    assert node_of(payload_of(store), "confirm-gate")["decision"] == "idle"
    store.append(a_decision())
    assert node_of(payload_of(store), "confirm-gate")["decision"] == "satisfied"
    assert node_of(payload_of(store), "result-gate")["decision"] == "idle"


def test_a_gate_holding_two_standing_decisions_is_unknown(tmp_path):
    """The store takes both, because neither supersedes the other.

    Answering with either one would be this computation choosing which Human
    decision is current, which is exactly the fact it is not allowed to invent.
    """
    store = a_store(tmp_path)
    store.append(a_decision(index=1))
    store.append(a_decision(index=2, action="reject", decided_at=NOW))
    assert node_of(payload_of(store), "confirm-gate")["decision"] == "unknown"


def test_a_superseded_decision_leaves_the_gate_on_the_receipt_that_stands(tmp_path):
    store = a_store(tmp_path)
    store.append(a_decision(index=1))
    store.append(a_decision(
        index=2, action="request_changes", reason="Scope grew.",
        decided_at=NOW, supersedes="decision-1"))
    assert node_of(payload_of(store), "confirm-gate")["decision"] == (
        "changes_requested")


def test_only_a_gate_node_carries_a_decision_and_only_a_loop_a_pass(tmp_path):
    rows = payload_of(a_store(tmp_path))["runtime"]["nodes"]
    graph = dalio_definition(run_id=RUN_ID)
    kinds = {node.node_id: node.kind for node in graph.nodes}
    for row in rows:
        assert ("decision" in row) is (kinds[row["node_id"]] == "gate")
        assert ("pass" in row) is (kinds[row["node_id"]] == "loop")
        assert ("bound_reached" in row) is (kinds[row["node_id"]] == "loop")


# -- a loop counts the work it actually reopens --------------------------------


def test_a_loop_counts_the_attempts_on_the_cycle_it_reopens(tmp_path):
    """`goal` runs before the loop's target, so going around never repeats it."""
    store = a_store(tmp_path)
    store.append(a_proposal(node_id="goal", index=1))
    loop = node_of(payload_of(store), "retry-loop")
    assert (loop["pass"], loop["bound_reached"]) == (0, False)

    store.append(a_proposal(node_id="diagnose", index=2))
    loop = node_of(payload_of(store), "retry-loop")
    assert (loop["pass"], loop["bound_reached"]) == (1, False)


def test_a_loop_says_bound_reached_only_when_the_plans_ceiling_is_met(tmp_path):
    """Three passes against a bound of three; the ceiling is the definition's."""
    store = a_store(tmp_path)
    assert the_node("retry-loop").loop.bound == 3
    for index, node_id in enumerate(("diagnose", "design", DO_NODE), start=1):
        store.append(a_proposal(node_id=node_id, index=index))
        loop = node_of(payload_of(store), "retry-loop")
        assert loop["pass"] == index
        assert loop["bound_reached"] is (index >= 3)


# -- the two halves of a graph share no word but the join ----------------------


#: The only names a runtime row may carry that are not runtime words: the join
#: to the plan, and the identities this projection is a projection OF.
JOIN_NAMES = frozenset({"node_id", "run_id", "graph_id", "nodes"})


def test_every_runtime_word_is_one_the_definition_refuses_by_name(tmp_path):
    """The partition, in both directions, over the whole projected document.

    A field the definition would have accepted is a fact about the plan, and a
    second copy of a plan fact can disagree with the first. A field the
    definition refuses is a fact about the run, which is what this document is
    for -- so the two vocabularies meet only at the join.
    """
    payload = payload_of(a_walked_run(tmp_path, upto="result"))
    spoken = set(payload["runtime"]) | {
        key for row in payload["runtime"]["nodes"] for key in row}
    assert spoken - JOIN_NAMES <= RUNTIME_ONLY_FIELDS
    assert not (spoken - JOIN_NAMES) & set(GraphNode._FIELDS)
    assert not (spoken - JOIN_NAMES) & set(GraphDefinition._FIELDS)
    assert "loop" not in spoken and "bound" not in spoken


def test_the_projected_vocabularies_are_closed_and_reachable(tmp_path):
    """Every word these tuples name is a word some journal can produce."""
    store = a_walked_run(tmp_path, upto="result")
    store.append(a_decision())
    payload = payload_of(store)
    phases = {row["phase"] for row in payload["runtime"]["nodes"]}
    assert phases <= set(NODE_PHASES)
    decisions = {row["decision"] for row in payload["runtime"]["nodes"]
                 if "decision" in row}
    assert decisions <= set(GATE_STATES)


@pytest.mark.parametrize("action", ["approve", "reject", "request_changes", "waive"])
def test_every_decision_a_human_may_take_lands_inside_the_gate_vocabulary(
        tmp_path, action):
    """GATE_STATES is held to `gate_decision`, not copied from beside it."""
    store = a_store(tmp_path)
    store.append(a_decision(action=action, reason="Stated for the record."))
    assert node_of(payload_of(store), "confirm-gate")["decision"] in GATE_STATES


def test_no_record_body_path_token_or_recovery_reference_reaches_the_wire(tmp_path):
    """The projection carries identifiers, closed words, counts and times.

    Everything a record body holds -- an evidence URI, an adapter's recovery
    reference, a rationale, a digest, an exit code -- stays in `records`, where
    a contract validated it and where safety law 8 already looks for it.
    """
    store = a_walked_run(tmp_path, upto="result")
    store.append(a_decision())
    text = repr(payload_of(store)["runtime"])
    for leaked in ("recovery-", "verification/", "dispatch verification",
                   "Carry out", "sha256:", "exit_code", "adapter_id"):
        assert leaked not in text, leaked
