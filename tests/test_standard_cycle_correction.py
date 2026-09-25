"""The shipped standard cycle corrects one independent rejection under one authorization.

What the product decides is real, with one setup step taken directly: the shipped `dalio-v5` file
is materialized by the product's own `materialize` and appended to the run's journal BEFORE
`server.build`, not through the server's routes. From there everything goes through the server's
HTTP doors on a real project owner: the input documents, the Policy preview and authorization, and
the human decisions, with the journal, the scheduler and both loops, the driver and the runtime
behind them. Only the harnesses are scripted in-process doubles, exactly as in `test_policy_server`:
this is not a live vendor claim.

The standard cycle before revision 5 had no road from a rejected `do` back to `do`
(`policy_frontier.correction_frontier` starts only at `on_failed`), so a checker's rejection
ended the authorized work. Revision 5 adds `do -> correct (on_failed)`, a loop of bound 2 home to
`do`: one correction, carrying the original instruction and the checker's exact feedback, then a
fresh independent check.
"""
from __future__ import annotations

from dataclasses import replace
from itertools import count
import json
from threading import Thread
import time

import pytest

from conductor import ownership_transition, server
from conductor.command.adapters import AdapterRegistry, AdapterVerification
from conductor.command.artifacts import ArtifactDocument, latest_artifacts, settled_products
from conductor.command.artifact_handoff import ArtifactHandoff
from conductor.command.contracts import EvidenceRef, RunEnvelope
from conductor.command.feedback_payload import payload_bytes
from conductor.command.graph_template import DEFAULT_TEMPLATE, RunBinding, load_template, materialize
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_http_api import TOKEN, decision_body
from tests.test_policy_driver import Signing
from tests.test_policy_feedback import PAYLOAD
from tests.test_policy_runtime import NOW, PD
from tests.test_server_command_http import _request
from tests.test_store import good_lane, write_project

RUN = "run"
CONFIG = {"cycle": {"id": "cycle"},
          "instances": [{"id": "doer", "adapter": "claude-code"},
                        {"id": "checker", "adapter": "codex-cli"}],
          "workflow": {"id": "standard", "revision": 1},
          "automation_contract": "bounded-run-v1"}
PLANNING = ("goal", "identify", "diagnose", "design")
#: One attempt per planning step and two for `do`: the correction is budgeted before the grant.
ASK = {"node_limits": [{"node_id": node, "timeout_seconds": 30, "max_attempts": 1} for node in PLANNING]
       + [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 2}],
       "max_actions": 6, "max_action_seconds": 60, "max_total_task_seconds": 240,
       "duration_seconds": 600}


class Doer(Signing):
    """Carries every step out; records what each `do` attempt was handed."""

    argument_schemas = {"dispatch": "deep-arguments-v1", "review": "deep-arguments-v1"}

    def __init__(self, store):
        super().__init__(store, capabilities=("observe", "review", "dispatch"))
        self.dispatches = []

    def verify(self, request, result):
        if request.capability == "review":
            # A review's one result document, published once its execution is observed, as the real
            # review transport does: the product verifies a review on exactly that document.
            # Its inputs are what the request's references resolve to, through the product's own
            # resolver: a document claiming other inputs is refused by the journal.
            documents = [row.value for row in self._store.read(request.run_id).records
                         if row.kind == "artifact"]
            consumed = latest_artifacts(documents, request.arguments["target_artifact_refs"])
            document = ArtifactDocument(
                artifact_id=f"doc-{request.action_id}", artifact_ref=request.arguments["result_artifact_ref"],
                run_id=request.run_id, created_at=NOW, media_type="text/markdown",
                content=f"{request.node_id} result.", source_action_id=request.action_id,
                input_artifact_ids=tuple(document.artifact_id for document in consumed))
            self._store.append(document)
            # ...and its verification digests exactly that document.
            evidence_id = f"evidence-{request.action_id}-{self.manifest.adapter_id}"
            self._store.append(EvidenceRef(
                evidence_id=evidence_id, run_id=request.run_id, kind="verification",
                uri=f"verification/{request.action_id}", label="Reviewed document",
                created_by=self.manifest.adapter_id, observed_at=NOW, digest=document.digest(),
                verification="verified", verified_by=self.manifest.adapter_id, verified_at=NOW))
            self.verify_calls += 1
            return AdapterVerification(adapter_id=self.manifest.adapter_id, action_id=request.action_id,
                                       state="verified", observed_at=NOW, detail="",
                                       evidence_refs=(evidence_id,))
        return super().verify(request, result)

    def execute(self, prepared):
        request = prepared.request
        if request.capability == "dispatch":
            handoff = ArtifactHandoff(self._store, clock=lambda: NOW, ids=lambda kind: kind)
            self.dispatches.append((request.node_id, dict(request.arguments), handoff.feedback(request)))
        return super().execute(prepared)

    def publish(self, request, result):
        """The handoff a transport makes: the documents this `do` consumed, and its result manifest.

        The consumed documents are the request's instruction and plan inputs, resolved the way the
        product resolves them; a manifest naming any other input cut is refused with its feedback.
        """
        published = super().publish(request, result)
        values = tuple(row.value for row in self._store.read(request.run_id).records)
        refs = (request.arguments["instruction_ref"], *request.arguments["artifact_refs"])
        consumed = tuple(latest_artifacts(settled_products(values), (ref,))[0].artifact_id for ref in refs)
        return replace(published, input_artifact_ids=consumed, result_manifest={
            "action_id": request.action_id, "attempt_id": request.attempt_id,
            "input_artifact_ids": list(consumed), "files": []})


class Checker(Signing):
    """Answers each independent check from a script: accept, typed (rejection with feedback), plain."""

    def __init__(self, store, verdicts):
        super().__init__(store, adapter_id="codex-cli")
        self.verdicts = list(verdicts)

    def verify_for(self, request, result, verifier, material):
        verdict = self.verdicts.pop(0) if self.verdicts else "accept"
        self.independent_calls.append((verifier, material))
        self.started = True
        if verdict == "accept":
            return self._sign(request, verifier.instance_id)
        typed = verdict == "typed"
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id, state="mismatch",
            observed_at=NOW, detail="rejected", feedback=payload_bytes(PAYLOAD) if typed else None,
            result_manifest=material.result_manifest if typed else None)


class Standard:
    """One owned server, one Policy run on the shipped standard cycle, driven through its doors."""

    def __init__(self, root, verdicts, template=DEFAULT_TEMPLATE):
        project = write_project(root, lanes={"claude": good_lane()})
        journal = RunStore(project)
        journal.create_run(RunEnvelope(RUN, "cycle", NOW, snapshot_digest(CONFIG), mode="policy"), CONFIG)
        # The shipped file, through the product's own materialize: roles to this run's instances.
        shipped = load_template(template)
        self.graph = materialize(shipped, RunBinding(assignments={
            role: "checker" if role == "role-checker" else "doer" for role in shipped.roles}),
            CONFIG, graph_id="graph-standard", run_id=RUN, created_at=NOW)
        journal.append(self.graph)
        ownership_transition.activate(project, legacy_writers_stopped=True)
        self.doer, self.checker = Doer(None), Checker(None, verdicts)
        seq = count()
        self.subject = server.build(project, 0, registry=AdapterRegistry([self.doer, self.checker]),
                                    clock=lambda: NOW, ids=lambda kind: f"{kind}-{next(seq)}",
                                    token_factory=lambda _: TOKEN)
        self.store = self.subject.command_store
        self.doer._store = self.checker._store = self.store
        policy = self.subject.command_api._policy
        # Registry injection has no installed provider configuration (as in test_policy_server).
        policy.provider_digest, policy.provider_facts = (lambda config: PD), None
        self.thread = Thread(target=self.subject.serve_forever, daemon=True)
        self.thread.start()

    def post(self, path, body):
        status, payload, _ = _request(self.subject, "POST", path, body)
        return status, payload

    def prepare(self):
        for reference, text in (("artifact-brief", "Count only records whose outcome is succeeded."),
                                ("instruction-plan", "Implement count_succeeded with its tests.")):
            status, body = self.post(f"/command/runs/{RUN}/artifacts", {
                "artifact_id": "input-" + reference, "artifact_ref": reference,
                "media_type": "text/markdown", "content": text})
            assert status == 201, body

    def authorize(self, ask=ASK):
        status, preview = self.post(f"/command/runs/{RUN}/automation/preview", ask)
        assert status == 200, preview
        status, grant = self.post(f"/command/runs/{RUN}/automation/authorize", {
            "authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None})
        assert status == 201, grant
        return preview

    def records(self, kind):
        return [row.value for row in self.store.read(RUN).records if row.kind == kind]

    def until(self, what, predicate, seconds=10):
        """Wait for one journal fact while the driver stays quiet; fail naming what never came."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            requests, results = self.records("action_request"), self.records("action_result")
            reason = self.subject.policy_driver.reason(RUN)
            if len(requests) == len(results) and reason not in (None, "ready", "running") and predicate():
                return str(reason)
            time.sleep(0.05)
        raise AssertionError(f"{what} never came: driver {self.subject.policy_driver.reason(RUN)}, "
                             f"requests {[r.node_id for r in self.records('action_request')]}")

    def outcomes(self, node_id):
        asked = {r.action_id for r in self.records("action_request") if r.node_id == node_id}
        return [r.outcome for r in self.records("action_result") if r.action_id in asked]

    def decide(self, gate, receipt, action="approve", supersedes=None):
        return self.post(f"/command/runs/{RUN}/decisions", decision_body(
            gate_id=gate, receipt_id=receipt, action=action, scope_refs=["work"], supersedes=supersedes))

    def at_confirm_gate(self, ask=ASK):
        """The four planning steps, carried out under the grant, then the first human door."""
        self.prepare()
        self.authorize(ask)
        self.until("the confirm gate", lambda: self.outcomes("design") == ["succeeded"])
        assert [r.node_id for r in self.records("action_request")] == list(PLANNING)
        status, body = self.decide("gate-confirm-do", "approve-do")
        assert status == 201, body

    def terminal(self):
        return [row for row in self.records("run_terminal")]

    def close(self):
        self.subject.shutdown()
        self.subject.server_close()
        self.thread.join(5)


@pytest.fixture
def standard(tmp_path):
    made = []

    def make(verdicts=(), template=DEFAULT_TEMPLATE):
        made.append(Standard(tmp_path / f"project-{len(made)}", verdicts, template))
        return made[-1]
    yield make
    for subject in made:
        subject.close()


def test_the_default_standard_cycle_is_revision_five():
    assert DEFAULT_TEMPLATE == "dalio-v5" and load_template(DEFAULT_TEMPLATE).revision == 5


def test_a_clean_result_runs_five_steps_under_one_grant_through_both_human_doors(standard):
    cycle = standard(["accept"])
    cycle.at_confirm_gate()
    cycle.until("the result gate", lambda: cycle.outcomes("do") == ["succeeded"])
    assert not cycle.terminal(), "the result gate is a human decision; the run may not end without it"
    status, body = cycle.decide("gate-result", "approve-result")
    assert status == 201, body
    cycle.until("the end of the run", lambda: bool(cycle.terminal()))
    assert [r.node_id for r in cycle.records("action_request")] == [*PLANNING, "do"]
    assert len(cycle.records("run_authorization")) == 1
    assert cycle.records("correction_feedback") == []
    assert [feedback for _node, _args, feedback in cycle.doer.dispatches] == [()]


def test_one_typed_rejection_is_corrected_once_with_the_original_instruction_and_its_exact_feedback(standard):
    cycle = standard(["typed", "accept"])
    cycle.at_confirm_gate()
    cycle.until("the corrected result", lambda: cycle.outcomes("do") == ["verification_failed", "succeeded"])
    feedback = cycle.records("correction_feedback")
    assert len(feedback) == 1 and feedback[0].as_dict()["payload"] == PAYLOAD
    assert feedback[0].checker_instance_id == "checker" and feedback[0].source_node_id == "do"
    proposals = [p for p in cycle.records("action_proposal") if p.node_id == "do"]
    assert proposals[1].feedback_ids == (feedback[0].feedback_id,)
    (_, first, before), (_, second, after) = cycle.doer.dispatches
    assert first == second and first["instruction_ref"] == "instruction-plan"
    assert before == () and after == (feedback[0].as_dict(),)
    # Both passes were checked by the independent checker; the correction is not self-approved.
    assert len(cycle.checker.independent_calls) == 2
    assert len(cycle.records("run_authorization")) == 1
    assert len(cycle.records("action_request")) == 6
    status, body = cycle.decide("gate-result", "approve-result")
    assert status == 201, body
    cycle.until("the end of the run", lambda: bool(cycle.terminal()))


#: A grant that would admit a THIRD `do`: whatever stops it is the plan's loop, not the grant.
THIRD_DO_ALLOWED = {**ASK, "node_limits": [
    {"node_id": node, "timeout_seconds": 30, "max_attempts": 1} for node in PLANNING]
    + [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 3}],
    "max_actions": 7, "max_total_task_seconds": 300}


def test_a_second_rejection_stops_without_a_third_do_and_is_never_a_success(standard):
    cycle = standard(["typed", "typed", "accept"])
    cycle.at_confirm_gate(THIRD_DO_ALLOWED)
    cycle.until("the exhausted correction",
                lambda: cycle.outcomes("do") == ["verification_failed", "verification_failed"])
    time.sleep(0.3)  # a third `do` would be proposed at once if the loop allowed one
    assert cycle.outcomes("do") == ["verification_failed", "verification_failed"]
    assert len(cycle.checker.independent_calls) == 2
    # The result gate never opened on a failed result, so a person's approval cannot stand in for the check.
    status, _body = cycle.decide("gate-result", "approve-anyway")
    assert status != 201
    assert all(outcome != "succeeded" for outcome in cycle.outcomes("do"))


def test_a_rejection_without_usable_feedback_invents_no_correction(standard):
    cycle = standard(["plain", "accept"])
    cycle.at_confirm_gate()
    cycle.until("the rejected result", lambda: cycle.outcomes("do") == ["verification_failed"])
    time.sleep(0.3)
    assert cycle.outcomes("do") == ["verification_failed"]
    assert cycle.records("correction_feedback") == []
    assert len(cycle.doer.dispatches) == 1


#: A grant that budgets the outer loop's replanning: every planning step but goal twice, eight actions.
REPLAN = {**ASK, "node_limits": [
    {"node_id": node, "timeout_seconds": 30, "max_attempts": 1 if node == "goal" else 2} for node in PLANNING]
    + [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 2}],
    "max_actions": 8, "max_total_task_seconds": 480}


def test_the_outer_request_changes_road_reopens_identify_and_a_second_lap_stops_at_the_cap(standard):
    """The human road back to identify is kept. A full second lap is nine actions, and the cap is eight."""
    cycle = standard(["accept"])
    cycle.at_confirm_gate(REPLAN)
    cycle.until("the result gate", lambda: cycle.outcomes("do") == ["succeeded"])
    status, body = cycle.decide("gate-result", "changes", action="request_changes")
    assert status == 201, body
    cycle.until("the replanned lap", lambda: len(cycle.outcomes("design")) == 2)
    assert cycle.outcomes("goal") == ["succeeded"], "the loop reopens identify, never goal"
    assert [r.node_id for r in cycle.records("action_request")] == [
        *PLANNING, "do", "identify", "diagnose", "design"]
    status, body = cycle.decide("gate-confirm-do", "approve-do-2", supersedes="approve-do")
    assert status == 201, body
    reason = cycle.until("an honest stop", lambda: True)
    time.sleep(0.3)
    assert len(cycle.records("action_request")) == 8, "a ninth action was admitted past the cap"
    assert cycle.outcomes("do") == ["succeeded"] and reason not in ("ready", "running")


def test_a_grant_that_budgets_one_planning_attempt_refuses_the_replanned_lap_honestly(standard):
    cycle = standard(["accept"])
    cycle.at_confirm_gate()
    cycle.until("the result gate", lambda: cycle.outcomes("do") == ["succeeded"])
    status, body = cycle.decide("gate-result", "changes", action="request_changes")
    assert status == 201, body
    reason = cycle.until("an honest refusal", lambda: True)
    time.sleep(0.3)
    assert reason == "admission_refused" and len(cycle.outcomes("identify")) == 1


def test_revision_four_had_no_correction_road(standard):
    cycle = standard(["typed", "accept"], template="dalio-v4")
    cycle.at_confirm_gate()
    cycle.until("the rejected result", lambda: cycle.outcomes("do") == ["verification_failed"])
    time.sleep(0.3)
    assert cycle.outcomes("do") == ["verification_failed"]


def _studio_draft(definition):
    """The preview body the Studio form starts from, computed by the shipped module itself."""
    import json
    from pathlib import Path
    import shutil
    import subprocess

    model = (Path(__file__).resolve().parents[1] / "src/conductor/panel/studio-automation-model.js").as_uri()
    source = (f"import * as m from {json.dumps(model)};"
              f"console.log(JSON.stringify(m.previewRequest(m.automationDraft({{graph: {{definition: "
              f"{json.dumps(definition)}}}}}))));")
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the Studio module")
    done = subprocess.run([node, "--input-type=module", "-e", source], capture_output=True, text=True,
                          encoding="utf-8", timeout=15, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_studio_draft_is_a_preview_the_server_admits_and_the_old_defaults_were_not(standard):
    cycle = standard(["accept"])
    cycle.prepare()
    body = _studio_draft(cycle.graph.as_dict())
    status, preview = cycle.post(f"/command/runs/{RUN}/automation/preview", {**body, "duration_seconds": 3600})
    assert status == 200, preview
    limits = {row["node_id"]: row["max_attempts"] for row in preview["terms"]["node_limits"]}
    assert limits["do"] == 2 and preview["terms"]["max_actions"] == 6
    old = {"max_actions": 8, "max_action_seconds": 300, "max_total_task_seconds": 2400,
           "duration_seconds": 3600, "node_limits": [
               {"node_id": row["node_id"], "timeout_seconds": 300, "max_attempts": 1}
               for row in body["node_limits"]]}
    status, refused = cycle.post(f"/command/runs/{RUN}/automation/preview", old)
    assert status == 422 and refused["error"]["code"] == "contract_invalid", refused
    # The door answers generically; this pins the reason: the admitted draft with ONE change -- a
    # per-action ceiling below `do` plus its checker -- is refused the same way.
    status, refused = cycle.post(f"/command/runs/{RUN}/automation/preview",
                                 {**body, "duration_seconds": 3600, "max_action_seconds": 300})
    assert status == 422 and refused["error"]["code"] == "contract_invalid", refused


def _first_scenario(do_attempts, max_actions, total):
    """Codex's table for the owner's first scenario: a reservation by contract, not a forecast of time or cost."""
    return {"node_limits": [{"node_id": node, "timeout_seconds": 900, "max_attempts": 1} for node in PLANNING]
            + [{"node_id": "do", "timeout_seconds": 1800, "max_attempts": do_attempts}],
            "max_actions": max_actions, "max_action_seconds": 3600, "max_total_task_seconds": total,
            "duration_seconds": 14400}


FIRST_CLEAN, FIRST_CORRECTED = _first_scenario(1, 5, 7200), _first_scenario(2, 6, 10800)


def _spent(cycle):
    from conductor.command.policy_history import spent_budget

    return spent_budget(tuple(row.value for row in cycle.store.read(RUN).records), cycle.graph)


def test_the_first_scenario_clean_budget_carries_the_clean_path_to_its_last_second(standard):
    cycle = standard(["accept"])
    cycle.at_confirm_gate(FIRST_CLEAN)
    cycle.until("the checked result", lambda: cycle.outcomes("do") == ["succeeded"])
    assert _spent(cycle) == (5, 7200)


def test_the_first_scenario_correction_budget_carries_one_correction_to_its_last_second(standard):
    """4 x 900 + 2 x (1800 x 2) = 10800: all six reservations fit exactly, under one grant."""
    cycle = standard(["typed", "accept"])
    cycle.at_confirm_gate(FIRST_CORRECTED)
    cycle.until("the corrected result", lambda: cycle.outcomes("do") == ["verification_failed", "succeeded"])
    assert _spent(cycle) == (6, 10800)
    assert len(cycle.records("run_authorization")) == 1


@pytest.mark.parametrize("budget", ["clean_table", "one_second_short"])
def test_a_budget_that_does_not_reserve_the_correction_refuses_it_and_calls_nothing_a_success(standard, budget):
    """The clean path's table is not a budget for the correction, and neither is 10799 seconds."""
    ask = FIRST_CLEAN if budget == "clean_table" else {**FIRST_CORRECTED, "max_total_task_seconds": 10799}
    cycle = standard(["typed", "accept"])
    cycle.at_confirm_gate(ask)
    reason = cycle.until("the refused correction", lambda: bool(cycle.records("correction_feedback")))
    assert reason == "admission_refused", reason
    assert [r.node_id for r in cycle.records("action_request")] == [*PLANNING, "do"]
    assert cycle.outcomes("do") == ["verification_failed"]
    status, body = cycle.decide("gate-result", "approve-anyway")
    assert status != 201, body
