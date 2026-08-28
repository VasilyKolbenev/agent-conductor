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

import ast
from pathlib import Path

import pytest

from conductor.command import graph_projection
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


# -- a finished attempt never speaks for the one happening now -----------------


def a_finished_run(tmp_path):
    """The Do node, taken all the way to a verified success."""
    return a_walked_run(tmp_path, upto="result")


def a_second_attempt(store, *, index=2, confirmed=True, **result_changes):
    """Ask for the same node again, and take it as far as a test wants."""
    proposal = a_proposal(index=index)
    store.append(proposal)
    if not confirmed:
        return None
    request = a_request(proposal, index=index)
    store.append(request)
    return request


def test_a_new_proposal_takes_the_node_off_the_outcome_it_had(tmp_path):
    """The exact reading a Cockpit must never offer.

    A node whose first attempt finished `succeeded` and whose second is already
    being asked for showed the old outcome, the old evidence and `observed` --
    a green finished step, while the work was being done again.
    """
    store = a_finished_run(tmp_path)
    assert node_of(payload_of(store), DO_NODE)["outcome"] == "succeeded"

    a_second_attempt(store, confirmed=False)

    row = node_of(payload_of(store), DO_NODE)
    assert row["phase"] == "proposed"
    assert row["outcome"] is None and row["observed_at"] is None
    assert row["evidence_refs"] == []
    assert row["attempt_ids"] == ["attempt-001", "attempt-002"]


def test_a_new_request_reports_the_new_attempt_and_not_the_finished_one(tmp_path):
    store = a_finished_run(tmp_path)
    request = a_second_attempt(store)

    row = node_of(payload_of(store), DO_NODE)
    assert (row["phase"], row["outcome"]) == ("requested", None)
    assert row["evidence_refs"] == []

    store.append(an_event(request, "effect_lease", index=2))
    running = node_of(payload_of(store), DO_NODE)
    assert (running["phase"], running["outcome"]) == ("running", None)


def test_a_success_followed_by_a_failure_reports_the_failure(tmp_path):
    """The one direction a stale projection would get most dangerously wrong."""
    store = a_finished_run(tmp_path)
    request = a_second_attempt(store)
    store.append(an_event(request, "effect_lease", index=2))
    store.append(an_event(request, "execution_observed", index=2,
                          outcome="failed", exit_code=3))
    store.append(a_result(request, index=2, outcome="failed", exit_code=3,
                          evidence_refs=(), observed_at="2026-08-19T10:00:00Z"))

    row = node_of(payload_of(store), DO_NODE)

    assert (row["phase"], row["outcome"]) == ("observed", "failed")
    assert row["observed_at"] == "2026-08-19T10:00:00Z"
    assert row["evidence_refs"] == [], "the first attempt's evidence is not this one's"


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


# -- a loop counts the trips it sent the work around, not the steps of one -----


def a_traversal(store, node_ids, *, start=1):
    """One distinct attempt on each named node, in the order a run takes them."""
    for offset, node_id in enumerate(node_ids):
        store.append(a_proposal(node_id=node_id, index=start + offset))
    return start + len(node_ids)


def the_loop(store):
    return node_of(payload_of(store), "retry-loop")


def test_a_whole_first_traversal_of_the_plan_is_still_only_the_first_pass(tmp_path):
    """The reading a Cockpit must never offer, in the shape a real run makes it.

    Dalio's cycle carries four steps that can act and a bound of three. Counting
    a pass as the attempts recorded anywhere on that cycle made one ordinary
    top-to-bottom traversal -- goal, identify, diagnose, design, do, each
    attempted once -- report four passes and announce the ceiling reached, while
    the loop had never sent any work around again.
    """
    store = a_store(tmp_path)
    assert the_node("retry-loop").loop.bound == 3
    a_traversal(store, ("goal", "identify", "diagnose", "design", DO_NODE))

    loop = the_loop(store)
    assert (loop["pass"], loop["bound_reached"]) == (1, False)


def test_work_on_the_cycles_other_steps_never_moves_the_pass(tmp_path):
    """A pass is a trip, and only the reopened step marks the start of one.

    `diagnose`, `design` and `do` all sit on the road the loop sends work
    around, so counting their attempts moved the position once per step of a
    single trip. They are work done ON a pass; they are never evidence of a
    second one, and a journal that has never touched the reopened step has
    taken no trip at all.
    """
    store = a_store(tmp_path)
    a_traversal(store, ("goal", "diagnose", "design", DO_NODE))

    loop = the_loop(store)
    assert (loop["pass"], loop["bound_reached"]) == (0, False)


def test_the_first_reopening_of_the_work_is_the_second_pass(tmp_path):
    """A second attempt at the step the loop reopens IS the run going around.

    The reopened node is attempted exactly once per trip, so its attempt count
    is the trip the run is on -- one durable fact, with no arithmetic invented
    on top of it.
    """
    store = a_store(tmp_path)
    index = a_traversal(
        store, ("goal", "identify", "diagnose", "design", DO_NODE))
    assert the_loop(store)["pass"] == 1

    store.append(a_proposal(node_id="identify", index=index))

    loop = the_loop(store)
    assert (loop["pass"], loop["bound_reached"]) == (2, False)


def test_the_bound_is_reached_at_the_exact_pass_the_plan_names(tmp_path):
    """Three whole trips against a bound of three; the ceiling is the plan's.

    Each trip here is the work a reopening really produces -- a fresh attempt at
    every acting step of the cycle -- so nothing can reach the bound by counting
    one trip's steps instead of the trips themselves, and the flip is asserted
    at every trip rather than only at the last.
    """
    store = a_store(tmp_path)
    assert the_node("retry-loop").loop.bound == 3
    index = 1
    for trip in (1, 2, 3):
        index = a_traversal(
            store, ("identify", "diagnose", "design", DO_NODE), start=index)
        loop = the_loop(store)
        assert loop["pass"] == trip, f"after trip {trip}"
        assert loop["bound_reached"] is (trip >= 3), f"after trip {trip}"


def test_two_proposals_that_name_one_attempt_are_one_pass(tmp_path):
    """A pass is a set of attempts, never a count of documents.

    The store screens identity on `proposal_id`, so one attempt may legally be
    described by two proposals. A position that counted documents on the
    reopened step would report a trip this run never took -- the same class of
    over-count as the cycle-wide sum, reached from the other direction.
    """
    store = a_store(tmp_path)
    store.append(a_proposal(node_id="identify", index=1))
    store.append(
        a_proposal(node_id="identify", index=2, attempt_id="attempt-001"))

    loop = the_loop(store)
    assert (loop["pass"], loop["bound_reached"]) == (1, False)


# -- the position is a reading for a Human, and no decision rests on it --------


#: The modules that decide what a run DOES: the loop that drives it, the
#: service and coordinator that own its lifecycle, and the runtime beneath
#: them. A loop's position is recomputed from the journal on every read and
#: exists to be shown; a decision resting on it would turn a projection into
#: control, and would then make correcting how a pass is counted a change to
#: what the product executes rather than to what it displays.
DECIDING_MODULES = ("runtime.py", "control_loop.py", "service.py",
                    "coordinator.py")
#: The two words this projection writes for a loop node and for nothing else.
DISPLAY_ONLY_WORDS = frozenset({"pass", "bound_reached"})


def _reads_a_display_word(source: str) -> set[str]:
    """Every loop display word this source names, however it reaches for one.

    `pass` is a Python keyword, so a reader can only ever spell it as a string:
    a subscript, a `get`, a comparison against a key, a name bound to it
    earlier. So every string constant in the module is judged rather than one
    syntactic shape, which needs no list of the ways a dict can be read.
    """
    spoken = {node.value for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    return spoken & DISPLAY_ONLY_WORDS


def test_the_display_word_gate_finds_a_module_that_would_read_the_position():
    """The instrument, calibrated on a case it must catch and one it must not.

    A gate that answers "clean" whatever it is given proves nothing about the
    modules it clears, so it is shown finding both words -- one subscripted,
    one fetched through a name -- before it is trusted to find none.
    """
    reader = ("KEY = 'bound_reached'\n"
              "def decide(row):\n"
              "    return row['pass'] if row.get(KEY) else None\n")
    assert _reads_a_display_word(reader) == DISPLAY_ONLY_WORDS
    assert _reads_a_display_word(
        "def decide(row):\n    return row['phase']\n") == set()


def test_no_module_that_decides_what_a_run_does_reads_the_loops_position():
    package = Path(graph_projection.__file__).resolve().parent
    # The same walk, over a real module off the same disk that DOES speak both
    # words: without it the clean verdict below could come from a path that
    # read nothing at all.
    assert _reads_a_display_word(
        (package / "graph_projection.py").read_text(encoding="utf-8")) == (
            DISPLAY_ONLY_WORDS)
    offenders: dict[str, list[str]] = {}
    for name in DECIDING_MODULES:
        path = package / name
        assert path.is_file(), f"{name} has left the command package"
        spoken = _reads_a_display_word(path.read_text(encoding="utf-8"))
        if spoken:
            offenders[name] = sorted(spoken)
    assert offenders == {}, f"a run decision reached for a display value: {offenders}"


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
    # The run's own phase is `run.status`, which the read carries from the
    # durable envelope. A second spelling of it here could disagree with the
    # first, so the top level carries the join and the nodes and nothing else.
    assert set(payload["runtime"]) == {"run_id", "graph_id", "nodes"}
    spoken = set(payload["runtime"]) | {
        key for row in payload["runtime"]["nodes"] for key in row}
    assert spoken - JOIN_NAMES <= RUNTIME_ONLY_FIELDS
    assert not (spoken - JOIN_NAMES) & set(GraphNode._FIELDS)
    assert not (spoken - JOIN_NAMES) & set(GraphDefinition._FIELDS)
    assert "loop" not in spoken and "bound" not in spoken


def test_every_phase_this_vocabulary_names_is_one_a_journal_can_produce(tmp_path):
    """Closed AND reachable, in both directions.

    A word no journal can produce is a word a consumer must handle and will
    never see; a phase this projection produces that the tuple does not name is
    a word no consumer knew to handle. So the set of phases observed across the
    whole chain is compared to the vocabulary itself, not merely contained by
    it.
    """
    seen = set()
    for step in ("proposed", "requested", "running", "observed", "result"):
        payload = payload_of(a_walked_run(tmp_path / step, upto=step))
        seen |= {row["phase"] for row in payload["runtime"]["nodes"]}
    assert seen == set(NODE_PHASES)


def test_every_gate_word_this_vocabulary_names_is_one_a_journal_can_produce(
        tmp_path):
    """GATE_STATES is held to `gate_decision`, not copied from beside it.

    Each Human decision, an absent receipt and an ambiguous pair are driven
    through the real store, and what comes back must be the whole tuple: a
    state this file invented would have nothing to produce it, and a state
    production produces would be missing from it.
    """
    seen = {node_of(payload_of(a_store(tmp_path / "idle")), "confirm-gate")[
        "decision"]}
    for index, action in enumerate(
            ("approve", "reject", "request_changes", "waive"), start=1):
        store = a_store(tmp_path / action)
        store.append(a_decision(action=action, reason="Stated for the record."))
        seen.add(node_of(payload_of(store), "confirm-gate")["decision"])
    ambiguous = a_store(tmp_path / "ambiguous")
    ambiguous.append(a_decision(index=1))
    ambiguous.append(a_decision(index=2, action="reject", decided_at=NOW))
    seen.add(node_of(payload_of(ambiguous), "confirm-gate")["decision"])
    assert seen == set(GATE_STATES)


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
