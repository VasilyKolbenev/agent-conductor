"""The shipped standard's executor is checked on every pass through its loop.

The template, HTTP admission, runtime, journal and scheduler are real. Adapters
are scripted in-process doubles: this is not a live vendor or browser claim.
Planning predecessors are seeded terminal facts so these witnesses isolate the
standard's execution and independent-verification requirement.
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import ActionRequest
from conductor.command.graph_definition import GraphDefinition
from conductor.command.graph_template import DEFAULT_TEMPLATE, load_template
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Authorization, AttemptState
from conductor.command.template_store import TemplateStore

from tests.test_command_decision_doors import settle_the_body, standing, run_word
from tests.test_command_http_api import (
    NOW, PORT, RUN_ID, TOKEN, confirm_body, decision_body, ids, post,
)
from tests.test_command_plan_verifier import CHECKER, DOER, _Signing
from tests.test_command_run_store import CONFIG, a_run
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_command_template_routes import contracts

RUN_PATH = f"/command/runs/{RUN_ID}"


class _StandardAdapter(_Signing):
    argument_schemas = DeepPlanAdapter.argument_schemas

    def __init__(self, store, **knobs):
        super().__init__(store, capabilities=("observe", "review", "dispatch"), **knobs)


def _installation(path, *, checker_state="verified", sign_as=None,
                  same_harness=False, max_actions=8):
    config = copy.deepcopy(CONFIG)
    if same_harness:
        for instance in config["instances"]:
            instance["adapter"] = "claude-code"
    store = RunStore(path)
    store.create_run(a_run(mode="confirm", config_digest=snapshot_digest(config)), config)
    doer = _StandardAdapter(store, adapter_id="claude-code")
    checker = doer if same_harness else _StandardAdapter(
        store, adapter_id="codex", verify_state=checker_state, sign_as=sign_as)
    registry = AdapterRegistry([doer] if same_harness else [doer, checker])
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=replace(PRODUCT_COMMAND_BUDGET, max_actions=max_actions),
        clock=lambda: NOW, ids=ids(),
        publish_run=lambda run_id: None, providers=contracts(),
        templates=TemplateStore(path))
    return api, store, doer, checker


def _assignments(template):
    return {role: CHECKER if role == "role-checker" else DOER
            for role in template.roles}


def _materialize(api, *, assignments=None, name=DEFAULT_TEMPLATE):
    template = load_template(name)
    assert post(api, "/command/templates", template.as_dict()).status == 201
    return post(api, RUN_PATH + "/graph/from-template", {
        "graph_id": "graph-standard", "template_id": template.template_id,
        "revision": template.revision,
        "assignments": _assignments(template) if assignments is None else assignments})


def _decide(api, gate, *, receipt, action="approve", supersedes=None):
    response = post(api, RUN_PATH + "/decisions", decision_body(
        gate_id=gate, receipt_id=receipt, action=action, supersedes=supersedes))
    assert response.status == 201, response.payload


def _ready(api, store, *, name=DEFAULT_TEMPLATE):
    created = _materialize(api, name=name)
    assert created.status == 201, created.payload
    graph = GraphDefinition.from_dict(created.payload)
    settle_the_body(store, graph)
    _decide(api, "gate-confirm-do", receipt="approve-first")
    # v4 retains v3's explicit instruction input. These are operator documents,
    # not an invented checker response or a claim that planning auto-published.
    for reference in ("instruction-plan", "artifact-plan"):
        response = post(api, RUN_PATH + "/artifacts", {
            "artifact_id": "input-" + reference, "artifact_ref": reference,
            "media_type": "text/markdown", "content": "The reviewed work plan."})
        assert response.status == 201, response.payload
    return graph


def _confirm(api, graph, *, lap=1):
    node = next(row for row in graph.nodes if row.node_id == "do")
    proposed = post(api, RUN_PATH + "/proposals", {
        "instance_id": node.instance_id, "attempt_id": f"attempt-do-{lap}",
        "capability": node.capability, "arguments": node.payload(),
        "scope": ["work"], "proposed_by": "release-owner",
        "rationale": "Execute the approved standard-cycle step.",
        "timeout_seconds": 30, "node_id": node.node_id})
    assert proposed.status == 201, proposed.payload
    return post(api, RUN_PATH + "/actions", confirm_body(proposed.payload))


def _execute(api, graph, *, lap=1):
    confirmed = _confirm(api, graph, lap=lap)
    assert confirmed.status == 201, confirmed.payload
    return api.runtime.execute(Authorization(ActionRequest.from_dict(confirmed.payload)))


@pytest.mark.parametrize("checker_state", ["mismatch", "unavailable", "error"])
def test_standard_execution_cannot_succeed_without_an_independent_verdict(
        tmp_path, checker_state):
    api, store, doer, checker = _installation(tmp_path, checker_state=checker_state)
    graph = _ready(api, store)
    attempt = _execute(api, graph)
    assert doer.execute_calls == 1, "the refusal must follow a successful doer"
    assert doer.verify_calls == 0, "the executor's own verification cannot substitute"
    assert len(checker.independent_calls) == 1
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.verification_evidence == ()
    # Revision 5: a refused result never reaches the human result decision; its correction road opens.
    assert standing(store, graph, "result-gate") == "blocked"
    assert standing(store, graph, "do") == "runnable"
    assert run_word(store, graph) != "complete"


def test_the_standard_corrects_a_rejected_attempt_once_and_checks_the_correction_again(tmp_path):
    """Revision 5 under Confirm: a person proposes the correction; the same checker judges it again."""
    api, store, doer, checker = _installation(tmp_path, checker_state="mismatch")
    graph = _ready(api, store)
    first = _execute(api, graph)
    assert first.state is AttemptState.VERIFICATION_FAILED
    checker._verify_state = "verified"
    second = _execute(api, graph, lap=2)
    assert second.state is AttemptState.SUCCEEDED, second.receipt.detail
    assert len(checker.independent_calls) == doer.execute_calls == 2 and doer.verify_calls == 0
    assert second.verification_evidence[0].verifier_instance_id == CHECKER
    assert standing(store, graph, "result-gate") == "runnable"
    _decide(api, "gate-result", receipt="accept-correction")
    assert run_word(store, graph) == "complete"


def test_standard_success_is_bound_to_the_distinct_checker(tmp_path):
    api, store, doer, checker = _installation(tmp_path)
    graph = _ready(api, store)
    attempt = _execute(api, graph)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert [row.verifier_instance_id for row in attempt.verification_evidence] == [CHECKER]
    assert [row.verified_by for row in attempt.verification_evidence] == ["codex"]
    assert doer.verify_calls == 0 and len(checker.independent_calls) == 1
    assert standing(store, graph, "result-gate") == "runnable"


def test_standard_rejects_evidence_attributed_to_its_executor(tmp_path):
    api, store, doer, checker = _installation(tmp_path, sign_as="claude-code")
    attempt = _execute(api, _ready(api, store))
    assert len(checker.independent_calls) == 1
    assert doer.execute_calls == 1 and doer.verify_calls == 0
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert not attempt.verification_evidence


@pytest.mark.parametrize("bad_binding", ["missing", "self"])
def test_standard_binding_cannot_drop_the_checker_or_assign_it_to_the_executor(
        tmp_path, bad_binding):
    api, store, doer, checker = _installation(tmp_path)
    assignments = _assignments(load_template(DEFAULT_TEMPLATE))
    if bad_binding == "missing":
        assignments.pop("role-checker")
    else:
        assignments["role-checker"] = assignments["role-implementer"]
    before = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()
    refused = _materialize(api, assignments=assignments)
    assert refused.status == 422, refused.payload
    assert refused.payload["error"]["code"] == "contract_invalid"
    assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    assert doer.execute_calls == checker.execute_calls == 0


def test_standard_allows_two_independent_instances_of_the_same_harness(tmp_path):
    api, store, adapter, checker = _installation(tmp_path, same_harness=True)
    attempt = _execute(api, _ready(api, store))
    assert adapter is checker
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert adapter.verify_calls == 0 and len(adapter.independent_calls) == 1
    assert adapter.independent_calls[0][0].instance_id == CHECKER != DOER


def test_standard_checks_the_corrected_attempt_again_after_its_existing_human_gates(
        tmp_path):
    # The full three-lap standard needs at most 13 actions. This deliberately
    # configured budget is not the product's current default of eight.
    api, store, doer, checker = _installation(
        tmp_path, checker_state="mismatch", max_actions=13)
    # Revision 4's road, which it keeps: a rejection is corrected by replanning through the result gate.
    graph = _ready(api, store, name="dalio-v4")
    first = _execute(api, graph)
    assert first.state is AttemptState.VERIFICATION_FAILED
    _decide(api, "gate-result", receipt="ask-for-changes", action="request_changes")
    assert standing(store, graph, "identify") == "runnable"
    assert standing(store, graph, "do") == "blocked"
    settle_the_body(store, graph, start=20, skip=("goal",))
    _decide(api, "gate-confirm-do", receipt="approve-correction", supersedes="approve-first")
    checker._verify_state = "verified"
    second = _execute(api, graph, lap=2)
    assert second.state is AttemptState.SUCCEEDED, second.receipt.detail
    assert len(checker.independent_calls) == doer.execute_calls == 2
    assert doer.verify_calls == 0
    assert second.verification_evidence[0].verifier_instance_id == CHECKER
    assert first.receipt.outcome == "verification_failed"
    _decide(api, "gate-result", receipt="accept-correction", supersedes="ask-for-changes")
    assert run_word(store, graph) == "complete"


def test_default_eight_action_budget_stops_the_second_do_before_execution(tmp_path):
    api, store, doer, checker = _installation(tmp_path, checker_state="mismatch")
    # Revision 4, whose only correction is a replanned lap: nine actions against the default eight.
    graph = _ready(api, store, name="dalio-v4")
    assert _execute(api, graph).state is AttemptState.VERIFICATION_FAILED
    _decide(api, "gate-result", receipt="request-fix", action="request_changes")
    settle_the_body(store, graph, start=20, skip=("goal",))
    _decide(api, "gate-confirm-do", receipt="approve-fix", supersedes="approve-first")
    assert standing(store, graph, "do") == "runnable"
    before = [row.value for row in store.read(RUN_ID).records
              if row.kind == "action_request"]
    assert len(before) == PRODUCT_COMMAND_BUDGET.max_actions == 8
    refused = _confirm(api, graph, lap=2)
    assert refused.status == 409, refused.payload
    assert refused.payload["error"]["code"] == "authorization_refused"
    after = [row.value for row in store.read(RUN_ID).records
             if row.kind == "action_request"]
    assert after == before
    assert doer.execute_calls == len(checker.independent_calls) == 1


def test_older_standard_keeps_its_existing_binding_rules(tmp_path):
    api, store, _doer, _checker = _installation(tmp_path)
    template = load_template("dalio-v3")
    assignments = {role: DOER for role in template.roles}
    created = _materialize(api, assignments=assignments, name="dalio-v3")
    assert created.status == 201, created.payload
    do = next(node for node in created.payload["nodes"] if node["node_id"] == "do")
    assert "verifier_instance_id" not in do
    assert not any(row.kind == "action_request" for row in store.read(RUN_ID).records)
