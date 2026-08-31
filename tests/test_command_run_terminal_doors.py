"""A plan that constrains what may run: eligibility, and the doors after an end.

Three refusals land here, and they are three different sentences about one idea
-- the plan is a permission and not only a description:

- **eligibility.** `authorize` mints nothing for a step the run has not reached.
  The rule is MEMBERSHIP in what the schedule computes, so the refusals for a
  blocked step, a settled one, an unreachable one, a spent one and a stranger
  all arrive together and cannot drift apart.
- **presence.** A proposal on a planned run names the step it carries out. This
  is the one intended behavioural change to a shipped surface: the legacy
  panel's composer emits seven keys and CANNOT emit `node_id`, so it is refused
  on every planned run and unchanged on a plan-less one. Both directions below.
- **the ending.** Once a run records its terminal, all three write doors refuse
  and NOTHING is written. The witnesses read `records.jsonl` as BYTES either
  side of the refused call, because "the record is absent" would also be true
  of a journal that had been rewritten.

The last one is the amendment that matters most, and the gap it closes is exact:
`_validate_records` never judges the record being APPENDED. It runs over the
journal as read -- which passes, the terminal being last -- and then
`_validate_new_relation` is asked about the new value alone, and none of its
arms fires for a decision or a proposal on a terminated run. Without a live
refusal the byte is written and only the NEXT read reports the run as corrupt.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
)
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime_values import (
    AuthorizationError,
    RunAlreadyTerminal,
)
from conductor.command.service import ServiceError
from tests.test_command_graph_binding import (
    CONFIG,
    RUN_ID,
    a_budget,
    a_confirmation,
    a_proposal,
    a_run,
    a_runtime,
    a_store,
    let_the_gate_through,
)
from tests.test_command_http_api import (
    api,
    decision_body,
    post,
    proposal_body,
)
from tests.test_command_schema_doubles import DeepDispatchAdapter

NOW = "2026-08-19T09:00:00Z"


def journal_bytes(store, run_id=RUN_ID):
    return (store.run_path(run_id) / "records.jsonl").read_bytes()


def kinds(store, run_id=RUN_ID):
    text = (store.run_path(run_id) / "records.jsonl").read_text(encoding="utf-8")
    return [json.loads(line)["record_type"] for line in text.splitlines() if line]


# -- eligibility: the plan says which step may run now --------------------------


def test_a_step_the_plan_has_not_reached_is_refused_at_authorize(tmp_path):
    """Witness 1's first shape: `do` is blocked behind an unanswered gate."""
    store = a_store(tmp_path)
    proposal = a_proposal()
    store.append(proposal)
    before = journal_bytes(store)

    with pytest.raises(AuthorizationError, match="is blocked"):
        a_runtime(store).authorize(a_confirmation(proposal), budget=a_budget())

    assert journal_bytes(store) == before


def test_the_refusal_names_the_step_its_state_and_what_is_runnable(tmp_path):
    """An operator needs to know WHY and WHAT INSTEAD, not merely "refused"."""
    store = a_store(tmp_path)
    store.append(a_proposal())

    with pytest.raises(AuthorizationError) as caught:
        a_runtime(store).authorize(
            a_confirmation(a_proposal()), budget=a_budget())

    message = str(caught.value)
    assert "'do'" in message and "blocked" in message
    assert "['goal']" in message


def test_the_same_step_is_authorized_once_the_plan_reaches_it(tmp_path):
    """Witness 2, the positive control: the rule is about the PLAN's state and
    not about the node, so the identical proposal goes through once the gate
    that stands in front of it has been answered."""
    store = a_store(tmp_path)
    let_the_gate_through(store)
    proposal = a_proposal()
    store.append(proposal)

    authorization = a_runtime(store).authorize(
        a_confirmation(proposal), budget=a_budget())

    assert authorization.request.node_id == "do"
    assert authorization.record_created is True


def test_a_spent_step_is_refused_and_the_schedule_agrees_it_is_blocked(tmp_path):
    """The spent arm, and the agreement that makes it worth having.

    One attempt is allowed and one is taken. The runtime then refuses the
    second, and the SCHEDULE -- which is what a screen reads -- independently
    calls the same step `blocked` with its attempts spent. A screen that still
    offered it would be offering work `authorize` is bound to refuse.
    """
    from conductor.command.graph_schedule import schedule

    store = _a_bounded_run(tmp_path)
    first = a_proposal()
    store.append(first)
    a_runtime(store).authorize(a_confirmation(first), budget=a_budget())

    second = a_proposal(proposal_id="proposal-2", attempt_id="attempt-002")
    store.append(second)
    with pytest.raises(AuthorizationError):
        a_runtime(store).authorize(a_confirmation(second), budget=a_budget())

    recovered = store.read(RUN_ID)
    computed = schedule(
        next(row.value for row in recovered.records
             if row.kind == "graph_definition"),
        tuple(row.value for row in recovered.records))
    spent = next(row for row in computed.nodes if row.node_id == "do")
    assert (spent.state, spent.attempts_spent) == ("blocked", True)
    assert "do" not in computed.runnable


def _a_bounded_run(tmp_path):
    """The shipped plan, its Do node allowed exactly one attempt, gate answered."""
    from tests.alpha3_graph_artifacts import dalio_definition

    store = a_store(tmp_path, with_graph=False)
    plan = dalio_definition(run_id=RUN_ID)
    nodes = tuple(
        GraphNode.from_dict({**row.as_dict(), "attempt_bound": 1})
        if row.node_id == "do" else row for row in plan.nodes)
    store.append(GraphDefinition(
        graph_id=plan.graph_id, run_id=plan.run_id,
        created_at=plan.created_at, nodes=nodes, edges=plan.edges))
    let_the_gate_through(store)
    return store


# -- presence: a proposal on a planned run names its step ----------------------


def legacy_composer_body():
    """Exactly the seven keys `panel/command.js` `proposalBody` can emit.

    Written out rather than derived, because the point is what that composer
    CANNOT put in: there is no `node_id` key anywhere in it, and no branch of
    that function adds one.
    """
    body = proposal_body()
    assert set(body) == {
        "instance_id", "attempt_id", "capability", "arguments", "scope",
        "proposed_by", "rationale", "timeout_seconds"}
    return body


def test_the_legacy_composers_body_is_refused_on_a_planned_run(tmp_path):
    """Witness 3, first direction, and the intended behavioural change.

    An unbound proposal on a planned run is authority the plan never gave, and
    it silently mis-resolves the verifier as well. Refusing is the only honest
    answer until that panel learns to bind a node.
    """
    from tests.alpha3_graph_artifacts import dalio_definition

    subject, store, _ = api(tmp_path, adapters=[DeepDispatchAdapter()])
    store.append(dalio_definition(run_id=RUN_ID))
    before = journal_bytes(store)

    refused = post(subject, f"/command/runs/{RUN_ID}/proposals",
                   legacy_composer_body())

    assert refused.status == ERROR_STATUS["service_refused"]
    assert refused.payload["error"]["code"] == "service_refused"
    assert journal_bytes(store) == before


def test_the_same_body_is_accepted_unchanged_on_a_plan_less_run(tmp_path):
    """Witness 3, second direction: runs without a graph are byte-identical.

    Without this the refusal above could equally be a composer that stopped
    working at all.
    """
    subject, store, _ = api(tmp_path, adapters=[DeepDispatchAdapter()])

    answer = post(subject, f"/command/runs/{RUN_ID}/proposals",
                  legacy_composer_body())

    assert answer.status == 201
    assert "node_id" not in answer.payload
    assert kinds(store) == ["action_proposal"]


def test_the_service_refusal_names_the_graph_and_what_is_missing(tmp_path):
    """A caller has to learn WHICH plan is making the demand."""
    from tests.alpha3_graph_artifacts import dalio_definition

    store = a_store(tmp_path, with_graph=False)
    store.append(dalio_definition(run_id=RUN_ID))
    service = a_runtime(store)  # builds the store-backed service seam too

    assert service is not None
    with pytest.raises(ServiceError, match="must name the node it carries out"):
        _propose_unbound(store)


def _propose_unbound(store):
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.service import CommandService
    from tests.test_command_schema_doubles import DeepDispatchAdapter

    body = legacy_composer_body()
    CommandService(store, AdapterRegistry([DeepDispatchAdapter()]),
                   clock=lambda: NOW,
                   ids=lambda kind: f"{kind}-001").propose(
        run_id=RUN_ID, node_id=None, **body)


# -- the ending: three doors, one word, and not one byte -----------------------


def a_run_that_ends(tmp_path):
    """A run whose plan completes the moment its one gate is answered."""
    subject, store, events = api(tmp_path, adapters=[DeepDispatchAdapter()])
    store.append(GraphDefinition(
        graph_id="graph-gated", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="release"),
               GraphNode(node_id="note", kind="task", title="Note")),
        edges=(GraphEdge(from_node="gate", to_node="note"),)))
    answered = post(subject, f"/command/runs/{RUN_ID}/decisions", decision_body())
    assert answered.status == 201
    return subject, store, events


def test_answering_the_last_gate_records_the_runs_terminal(tmp_path):
    """The decide door's closing call, and the record it writes."""
    _subject, store, _events = a_run_that_ends(tmp_path)

    assert kinds(store) == ["graph_definition", "decision", "run_terminal"]
    terminal = store.read(RUN_ID).records[-1].value
    assert (terminal.state, terminal.settled_nodes) == ("complete", ("gate", "note"))
    assert terminal.graph_id == "graph-gated"


def test_a_decision_after_the_terminal_is_refused_and_writes_no_byte(tmp_path):
    """Witness 18, road one."""
    subject, store, _ = a_run_that_ends(tmp_path)
    before = journal_bytes(store)

    refused = post(subject, f"/command/runs/{RUN_ID}/decisions",
                   decision_body(receipt_id="decision-002"))

    assert refused.status == ERROR_STATUS["run_terminal"]
    assert refused.payload["error"]["code"] == "run_terminal"
    assert journal_bytes(store) == before


def test_a_proposal_after_the_terminal_is_refused_and_writes_no_byte(tmp_path):
    """Witness 18, road two."""
    subject, store, _ = a_run_that_ends(tmp_path)
    before = journal_bytes(store)

    refused = post(subject, f"/command/runs/{RUN_ID}/proposals",
                   proposal_body())

    assert refused.status == ERROR_STATUS["run_terminal"]
    assert refused.payload["error"]["code"] == "run_terminal"
    assert journal_bytes(store) == before


def test_an_authorize_after_the_terminal_is_refused_by_the_runtime(tmp_path):
    """Witness 18, road three: the depth refuses whatever the caller.

    The proposal is written BEFORE the run ends, so what is being refused is
    the authorization and not the proposal -- which is the only way to reach
    the runtime hold at all.
    """
    store = a_store(tmp_path, with_graph=False)
    store.append(GraphDefinition(
        graph_id="graph-gated", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="gate-confirm-do"),
               GraphNode(node_id="note", kind="task", title="Note")),
        edges=(GraphEdge(from_node="gate", to_node="note"),)))
    proposal = a_proposal(node_id=None)
    store.append(proposal)
    let_the_gate_through(store)
    close_if_terminal(store, RUN_ID, clock=lambda: NOW,
                      ids=lambda kind: f"{kind}-001")
    before = journal_bytes(store)

    with pytest.raises(RunAlreadyTerminal, match="accepts no further records"):
        a_runtime(store).authorize(a_confirmation(proposal), budget=a_budget())

    assert journal_bytes(store) == before


def test_the_runtime_refusal_is_an_authorization_error_every_handler_catches(
        tmp_path):
    """Subclassing is what keeps every existing `except` road working."""
    assert issubclass(RunAlreadyTerminal, AuthorizationError)


def test_the_wire_word_is_chosen_by_type_and_not_by_message():
    """The specific code wins over the general one, by arm order alone."""
    from conductor.command.api_contracts import refusal_from_exception

    specific = refusal_from_exception(RunAlreadyTerminal("anything at all"))
    general = refusal_from_exception(AuthorizationError("anything at all"))

    assert specific.code == "run_terminal"
    assert general.code == "authorization_refused"
    assert specific.status == ERROR_STATUS["run_terminal"] == 409


# -- closing is a no-op unless it has something new to say ---------------------


def test_a_second_closing_call_returns_the_standing_terminal_unchanged(tmp_path):
    """Nothing is re-minted, so two calls cannot record two sets of facts."""
    _subject, store, _events = a_run_that_ends(tmp_path)
    standing = store.read(RUN_ID).records[-1].value

    again = close_if_terminal(store, RUN_ID, clock=lambda: "2099-01-01T00:00:00Z",
                              ids=lambda kind: "terminal-second")

    assert again == standing
    assert kinds(store).count("run_terminal") == 1


def test_closing_a_run_that_follows_no_plan_writes_nothing(tmp_path):
    """The whole of the plan-less exemption, on the closing road."""
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    before = journal_bytes(store)

    assert close_if_terminal(store, RUN_ID, clock=lambda: NOW,
                             ids=lambda kind: "terminal-001") is None
    assert journal_bytes(store) == before


def test_closing_a_run_whose_plan_is_still_open_writes_nothing(tmp_path):
    """A verdict of `open` is never durable, so nothing is recorded for it."""
    store = a_store(tmp_path)
    before = journal_bytes(store)

    assert close_if_terminal(store, RUN_ID, clock=lambda: NOW,
                             ids=lambda kind: "terminal-001") is None
    assert journal_bytes(store) == before


# -- `stalled` from a real journal ---------------------------------------------


def test_a_reconciled_unknown_on_a_spent_step_stalls_the_run(tmp_path):
    """Witness 15, built the way the design describes and no other way.

    A plan allows the Do node ONE attempt. It is authorized, the process dies
    before any effect lease, and the operator runs `reconcile` -- which writes
    the terminal `unknown` that is the only honest answer for an effect nobody
    observed. `unknown` settles nothing, the bound is spent, so the step can
    never settle and no human action can change that: the run is `stalled`, and
    `_finish` records it through the same road a completion takes.

    Without this the word `stalled` would be vocabulary nothing produces.
    """
    from conductor.command.runtime import AttemptState

    store = _a_stalling_run(tmp_path)
    proposal = a_proposal()
    store.append(proposal)
    request = a_runtime(store).authorize(
        a_confirmation(proposal), budget=a_budget()).request

    # `reconcile` resolves no adapter and asks none a thing.
    attempt = a_runtime(store).reconcile(RUN_ID, request.action_id)

    assert attempt.state is AttemptState.UNKNOWN
    assert kinds(store)[-1] == "run_terminal"
    terminal = store.read(RUN_ID).records[-1].value
    assert terminal.state == "stalled"
    assert "do" not in terminal.settled_nodes


def test_the_stalled_terminal_replays_to_the_same_verdict(tmp_path):
    """It is judged again from the plan's own bytes, by a reader that never
    saw the writing process."""
    store = _a_stalling_run(tmp_path)
    proposal = a_proposal()
    store.append(proposal)
    request = a_runtime(store).authorize(
        a_confirmation(proposal), budget=a_budget()).request
    a_runtime(store).reconcile(RUN_ID, request.action_id)

    replayed = RunStore(tmp_path).read(RUN_ID)

    assert [row.kind for row in replayed.records][-1] == "run_terminal"
    assert replayed.records[-1].value.state == "stalled"
    assert replayed.warnings == ()


def _a_stalling_run(tmp_path):
    """A gate and the one effecting step behind it, allowed a single attempt.

    The shipped cycle will not do here, and the reason is the point of the
    word: with `goal` still runnable the plan is `open`, not `stalled`. A run
    stalls only when NOTHING is runnable and something is still owed, so the
    plan has to be one whose whole remaining work is the step that spent its
    bound. The Do node is taken from the shipped plan verbatim -- instance,
    capability and arguments -- so the proposal below is the real one.
    """
    from tests.alpha3_graph_artifacts import dalio_definition

    plan = dalio_definition(run_id=RUN_ID)
    doing = next(row for row in plan.nodes if row.node_id == "do")
    store = a_store(tmp_path, with_graph=False)
    store.append(GraphDefinition(
        graph_id=plan.graph_id, run_id=RUN_ID, created_at=plan.created_at,
        nodes=(GraphNode(node_id="confirm-gate", kind="gate",
                         title="Human Gate", gate_id="gate-confirm-do"),
               GraphNode.from_dict({**doing.as_dict(), "attempt_bound": 1})),
        edges=(GraphEdge(from_node="confirm-gate", to_node="do"),)))
    let_the_gate_through(store)
    return store


# -- a frozen configuration nobody can read is corruption, not caller input ----


def test_a_run_whose_frozen_bindings_are_malformed_answers_run_corrupt(tmp_path):
    """The translation that had no witness anywhere in this suite.

    A frozen snapshot declaring one instance twice cannot be read into a
    binding map at all. That is not a caller's fault and not a request shape
    fault -- the durable bytes this run was created with do not say who runs
    what -- so the answer is `run_corrupt`, and a bare `ContractError` escaping
    here would surface as `contract_invalid` and blame the caller.
    """
    # An `adapter` that is not an id. Chosen over a duplicated instance
    # deliberately: a duplicate breaks `frozen_config_models` first, which is a
    # DIFFERENT untranslated road, and this witness is about the binding one.
    doubled = {"instances": [{"id": "claude-dev", "adapter": 5}]}
    subject, store, _ = api(tmp_path)
    store.create_run(
        a_run(run_id="run-doubled", mode="confirm",
              config_digest=snapshot_digest(doubled)), doubled)

    answer = subject.handle(
        "GET", "/command/runs/run-doubled/controls",
        (("Host", "127.0.0.1:7802"),), b"")

    assert answer.status == ERROR_STATUS["run_corrupt"]
    assert answer.payload["error"]["code"] == "run_corrupt"


def test_a_run_whose_frozen_bindings_are_readable_answers_its_controls(tmp_path):
    """The control: the refusal above is about the malformed snapshot alone."""
    subject, _store, _ = api(tmp_path)

    answer = subject.handle(
        "GET", f"/command/runs/{RUN_ID}/controls",
        (("Host", "127.0.0.1:7802"),), b"")

    assert answer.status == 200
    assert [row["instance_id"] for row in answer.payload["instances"]] == [
        "claude-dev", "codex-review"]
