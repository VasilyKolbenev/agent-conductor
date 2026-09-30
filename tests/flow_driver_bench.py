"""A server on a real project owner that runs any compiled flow on scripted doubles.

What the product decides is real: the flow is compiled by the product's own `compile_flow`, taken
by `GraphTemplate`, bound by `materialize` and appended to the run's journal before the server is
built (the one setup step taken directly, as in `test_standard_cycle_correction`). From there
everything goes through the server's HTTP doors on a real project owner: the documents the plan
reads, the automation preview with the body `{}` (the server drafts the terms, spec 6.4.4), the
authorization and the human decisions, with the journal, the schedule, the loops, the driver and the
runtime behind them. Only the harnesses are in-process doubles: not a live vendor claim.

Two scripts drive the doubles and both are self-checking. `verdicts` is what the independent checker
says to each checked step, in order, as `(step_id, verdict)`; a check that arrives for another step
than the script names is recorded in `mismatches` and read as an accept, so a test that asks
`mismatches == []` fails on a plan that did not take the road the script assumed. `outcomes` is what
each named step's action ends with, in order, before the default `succeeded`.
"""
from __future__ import annotations

import time
from itertools import count
from threading import Lock, Thread

from conductor import ownership_transition, server
from conductor.command import task_preparation
from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import RunEnvelope
from conductor.command.graph_definition import GraphDefinition
from conductor.command.graph_schedule import schedule
from conductor.command.graph_template import GraphTemplate, RunBinding, materialize
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.workflow_flow import compile_flow
from tests.test_command_http_api import TOKEN, decision_body
from tests.test_command_workflow_routes import contracts
from tests.test_policy_runtime import NOW, PD
from tests.test_server_command_http import _request
from tests.test_standard_cycle_correction import CONFIG, RUN, Checker, Doer
from tests.test_store import good_lane, write_project

GRANT = "grant"
#: Two instances of two providers: the checker is never the doer's own adapter.
PARTICIPANTS = [{"instance_id": "doer", "provider_id": "claude-code", "model": None},
                {"instance_id": "checker", "provider_id": "codex-cli", "model": None}]


def template_of(flow, template_id="flow-bench"):
    """The template a flow compiles to, as the store accepts it."""
    return GraphTemplate.from_dict({**compile_flow(flow), "template_id": template_id,
                                    "revision": 1})


class ScriptedDoer(Doer):
    """Carries every step out; a step named in `outcomes` ends as scripted, once per entry."""

    def __init__(self, store, outcomes):
        super().__init__(store)
        self.outcomes = {step: list(rows) for step, rows in (outcomes or {}).items()}
        self._gate = Lock()
        self.in_flight = 0
        self.most_in_flight = 0

    def execute(self, prepared):
        step = prepared.request.node_id
        with self._gate:
            self.in_flight += 1
            self.most_in_flight = max(self.most_in_flight, self.in_flight)
            scripted = self.outcomes.get(step)
            self._execute_outcome = scripted.pop(0) if scripted else "succeeded"
        try:
            time.sleep(0.02)
            return super().execute(prepared)
        finally:
            with self._gate:
                self.in_flight -= 1


class ScriptedChecker(Checker):
    """Answers each independent check from the script, and notes a check the script did not name."""

    def __init__(self, store, verdicts):
        super().__init__(store, [])
        self.script = list(verdicts)
        self.mismatches = []
        self.checked = []

    def verify_for(self, request, result, verifier, material):
        expected, verdict = self.script.pop(0) if self.script else (request.node_id, "accept")
        if expected != request.node_id:
            self.mismatches.append((expected, request.node_id))
        self.checked.append((request.node_id, verdict))
        self.verdicts = [verdict]
        return super().verify_for(request, result, verifier, material)


class FlowCycle:
    """One owned server and one Policy run on a compiled flow, driven through its doors."""

    def __init__(self, root, flow, *, verdicts=(), outcomes=None, through_doors=False):
        """`through_doors`: publish the template and open the run by the server's own routes,
        instead of appending the run's journal before the server is built."""
        project = write_project(root, lanes={"claude": good_lane()})
        self.template = template_of(flow)
        self.roles = {role: "checker" if role == "role-checker" else "doer"
                      for role in self.template.roles}
        self.graph = self.published = None
        if not through_doors:
            journal = RunStore(project)
            journal.create_run(
                RunEnvelope(RUN, "cycle", NOW, snapshot_digest(CONFIG), mode="policy"), CONFIG)
            self.graph = materialize(self.template, RunBinding(assignments=self.roles), CONFIG,
                                     graph_id="graph-bench", run_id=RUN, created_at=NOW)
            journal.append(self.graph)
        ownership_transition.activate(project, legacy_writers_stopped=True)
        self.doer, self.checker = ScriptedDoer(None, outcomes), ScriptedChecker(None, verdicts)
        seq = count()
        self.subject = server.build(project, 0, registry=AdapterRegistry([self.doer, self.checker]),
                                    clock=lambda: NOW, ids=lambda kind: f"{kind}-{next(seq)}",
                                    token_factory=lambda _: TOKEN)
        self.store = self.subject.command_store
        self.doer._store = self.checker._store = self.store
        policy = self.subject.command_api._policy
        policy.provider_digest, policy.provider_facts = (lambda config: PD), None
        self.thread = Thread(target=self.subject.serve_forever, daemon=True)
        self.thread.start()
        if through_doors:
            self.open_through_doors()

    def open_through_doors(self):
        """Publish revision 1 of the template, then open the run on it, each by its own door.

        An injected registry carries no provider descriptors, so the roster the open door reads
        is the two reviewed descriptors the route tests use, both reachable.
        """
        providers = [row["provider_id"] for row in PARTICIPANTS]
        self.subject.command_api._providers = contracts(reachable=providers, known=providers)
        status, self.published = self.post("/command/templates", self.template.as_dict())
        assert status == 201, self.published
        status, opened = self.post("/command/runs", {
            "run_id": RUN, "cycle_id": "cycle", "mode": "policy", "participants": PARTICIPANTS,
            "workflow_id": self.template.template_id, "revision": 1, "assignments": self.roles,
            "task_id": None, "automation_contract": "bounded-run-v1"})
        assert status == 201, opened
        self.graph = GraphDefinition.from_dict(opened["graph"])

    def post(self, path, body):
        status, payload, _ = _request(self.subject, "POST", path, body)
        return status, payload

    def prepare(self):
        """Publish, as a human would, every document the plan reads and does not produce."""
        recovered = self.store.read(RUN)
        values = tuple(row.value for row in recovered.records)
        missing = task_preparation.missing_bindings(self.graph, values)
        refs = [row["instruction_ref"] for row in missing["instructions"]] + missing["inputs"]
        for ref in dict.fromkeys(refs):  # steps sharing an instruction name one document
            status, body = self.post(f"/command/runs/{RUN}/artifacts", {
                "artifact_id": f"input-{ref}", "artifact_ref": ref,
                "media_type": "text/markdown", "content": f"{ref}.\n"})
            assert status == 201, body

    def preview(self):
        """The terms the server drafts for this plan (body `{}`, spec 6.4.4)."""
        status, preview = self.post(f"/command/runs/{RUN}/automation/preview", {})
        assert status == 200, preview
        return preview

    def authorize(self):
        """The grant of the terms the server drafts for this plan."""
        preview = self.preview()
        status, grant = self.post(f"/command/runs/{RUN}/automation/authorize", {
            "authorization_id": GRANT, "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None})
        assert status == 201, grant
        return preview

    def start(self):
        self.prepare()
        return self.authorize()

    def records(self, kind):
        return [row.value for row in self.store.read(RUN).records if row.kind == kind]

    def reason(self):
        return self.subject.policy_driver.reason(RUN)

    def until(self, what, predicate=lambda: True, seconds=15):
        """Wait for a journal fact while the driver is quiet; fail naming what never came."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            requests, results = self.records("action_request"), self.records("action_result")
            if (len(requests) == len(results) and self.reason() not in (None, "ready", "running")
                    and predicate()):
                return str(self.reason())
            time.sleep(0.05)
        raise AssertionError(f"{what} never came: driver {self.reason()}, "
                             f"steps {self.steps()}, outcomes "
                             f"{[r.outcome for r in self.records('action_result')]}")

    def steps(self):
        """The steps the driver asked for, in order of asking."""
        return [row.node_id for row in self.records("action_request")]

    def plan_state(self):
        """What the schedule says of the whole plan: `open`, `complete`, `stalled`."""
        values = tuple(row.value for row in self.store.read(RUN).records)
        return schedule(self.graph, values).run_state

    def holder(self):
        """The run that holds the project's slot, or None when it is free."""
        return self.subject.policy_driver.slot().active_run_id

    def automation(self):
        """The automation read of the run: its state and the reason of that state."""
        status, payload, _ = _request(self.subject, "GET", f"/command/runs/{RUN}/automation")
        assert status == 200, payload
        return payload["state"], payload["reason_code"]

    def outcomes(self, step_id):
        asked = {r.action_id for r in self.records("action_request") if r.node_id == step_id}
        return [r.outcome for r in self.records("action_result") if r.action_id in asked]

    def settle(self, pause=0.4):
        """Let a driver that would admit one more step do so, then say what it did not."""
        time.sleep(pause)
        return len(self.records("action_request"))

    def decide(self, gate_step, receipt, action="approve", supersedes=None):
        return self.post(f"/command/runs/{RUN}/decisions", decision_body(
            gate_id=f"gate-{gate_step}", receipt_id=receipt, action=action, scope_refs=["work"],
            supersedes=supersedes))

    def terminal(self):
        return self.records("run_terminal")

    def close(self):
        self.subject.shutdown()
        self.subject.server_close()
        self.thread.join(5)
