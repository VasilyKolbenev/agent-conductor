"""WHO confirms a step, when the plan names somebody other than the doer.

`ControlRuntime` has always been adapter-agnostic about verification and it
still is. What it derives from the run's frozen configuration is unchanged: a
plan may not name an adapter, a provider or a model, and which adapter drives an
instance is a fact of the configuration and of nothing else. What a plan may now
say is which INSTANCE checks -- in the vocabulary of that same configuration --
and the runtime resolves it through the same `_bound_adapter` door, refusing an
instance the configuration does not declare exactly as it always did.

The chain, and every link is held below:

    TemplateNode.verifier_role_id   (a ROLE: a template may not name an instance)
      -> RunBinding assignments      (the roles a binding must cover, this one too)
      -> GraphNode.verifier_instance_id   frozen into the plan
      -> ControlRuntime._verifier_for     resolved through the frozen config
      -> registry.verify, the identity check, and the causal evidence relation

The sharpest test here is the third: evidence signed by the DOER no longer
satisfies `_causal_evidence` once the plan names somebody else. Without that,
"a different adapter verifies" would be a call this runtime happened to make
and not a rule anything held -- the run would still reach `succeeded` on the
doer's own word, which is the whole thing verification exists to prevent.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import AdapterRegistry, AdapterVerification
from conductor.command.contracts import EvidenceRef
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, ControlRuntime, ExecutionError

from tests.test_command_run_store import CONFIG, a_run
from tests.test_command_runtime_authorize import (
    NOW,
    a_budget,
    a_confirmation,
    a_proposal,
    fixed_clock,
    fixed_ids,
)
from tests.test_command_runtime_execute import ScriptedAdapter

RUN_ID = "run-001"
DOER = "claude-dev"
CHECKER = "codex-review"
NODE = "do"


class _Signing(ScriptedAdapter):
    """An adapter that answers `verified` and signs the evidence with its OWN id.

    The evidence writer is test-local because the adapter API returns refs and
    receives no append power -- the same stand-in `VerifiedAdapter` makes next
    door. What matters here is the SIGNATURE: `created_by` and `verified_by`
    are this adapter's id, so a run reaching `succeeded` says which adapter's
    word it was taken on.
    """

    def __init__(self, store, *, sign_as=None, **knobs):
        super().__init__(verify_state="verified", **knobs)
        self._store = store
        self._sign_as = sign_as

    def verify(self, request, result):
        self.verify_calls += 1
        signature = self._sign_as or self.manifest.adapter_id
        evidence_id = f"evidence-{signature}"
        self._store.append(EvidenceRef(
            evidence_id=evidence_id, run_id=request.run_id, kind="verification",
            uri=f"verification/{request.action_id}",
            label="durable verification fact", created_by=signature,
            observed_at=NOW, verification="verified", verified_by=signature,
            verified_at=NOW))
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state="verified", observed_at=NOW, detail="scripted verification",
            evidence_refs=(evidence_id,))


def a_plan(store, *, verifier):
    """One gate and one dispatching step, the step naming a verifier or not."""
    nodes = (
        GraphNode(node_id="confirm-gate", kind="gate", title="Human gate",
                  gate_id="gate-confirm-do"),
        GraphNode(node_id=NODE, kind="task", title="Do the work",
                  instance_id=DOER, capability="dispatch",
                  arguments={"handoff": "packet-001"},
                  verifier_instance_id=verifier),
    )
    definition = GraphDefinition(
        graph_id="graph-001", run_id=RUN_ID, created_at=NOW, nodes=nodes,
        edges=(GraphEdge(from_node="confirm-gate", to_node=NODE),))
    store.append(definition)
    return definition


def a_bound_store(tmp_path, *, verifier):
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    a_plan(store, verifier=verifier)
    return store


def test_the_doer_verifies_itself_when_the_plan_names_nobody(tmp_path):
    """The unchanged road, and every plan written before this field takes it."""
    doer = _Signing(None, adapter_id="claude-code")
    store = a_bound_store(tmp_path, verifier=None)
    doer._store = store
    runtime = ControlRuntime(store, AdapterRegistry([doer]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(
        store, instance_id=DOER, capability="dispatch",
        arguments={"handoff": "packet-001"}, node_id=NODE)
    attempt = runtime.execute(
        runtime.authorize(a_confirmation(proposal), budget=a_budget()))

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert doer.verify_calls == 1


def test_a_plan_named_verifier_is_the_adapter_that_confirms(tmp_path):
    """The doer executes; somebody else says whether it worked.

    Both adapters are registered, so nothing about this outcome comes from one
    of them being the only thing in the room.
    """
    doer = _Signing(None, adapter_id="claude-code")
    checker = _Signing(None, adapter_id="codex")
    store = a_bound_store(tmp_path, verifier=CHECKER)
    doer._store = checker._store = store
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(
        store, instance_id=DOER, capability="dispatch",
        arguments={"handoff": "packet-001"}, node_id=NODE)
    attempt = runtime.execute(
        runtime.authorize(a_confirmation(proposal), budget=a_budget()))

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert checker.verify_calls == 1, "the plan's verifier was not asked"
    assert doer.verify_calls == 0, "the doer verified its own work anyway"
    assert doer.execute_calls == 1 and checker.execute_calls == 0
    signed = {row.value.verified_by for row in store.read(RUN_ID).records
              if row.kind == "evidence"}
    assert signed == {"codex"}, signed


def test_the_doers_own_word_no_longer_satisfies_a_plan_that_named_somebody_else(
        tmp_path):
    """The rule, not the call: evidence signed by the DOER stops counting.

    This is what makes the field load-bearing. If `_causal_evidence` still
    accepted the executing adapter's signature, a plan naming a verifier would
    change which function was called and nothing about what the product would
    believe -- and a run would still reach `succeeded` on the doer's own word.
    """
    doer = _Signing(None, adapter_id="claude-code")
    # The named verifier answers `verified` but signs as the DOER, which is the
    # forgery this relation exists to refuse.
    checker = _Signing(None, adapter_id="codex", sign_as="claude-code")
    store = a_bound_store(tmp_path, verifier=CHECKER)
    doer._store = checker._store = store
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(
        store, instance_id=DOER, capability="dispatch",
        arguments={"handoff": "packet-001"}, node_id=NODE)
    attempt = runtime.execute(
        runtime.authorize(a_confirmation(proposal), budget=a_budget()))

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.state
    assert attempt.verification_evidence == ()
    assert "causal store relation" in attempt.receipt.detail, (
        attempt.receipt.detail)


def test_a_verifier_the_frozen_configuration_never_declared_is_refused(tmp_path):
    """The adapter-agnostic ruling, unchanged and now doing more work.

    A plan naming an instance the run's configuration does not declare is
    refused by the SAME door that refuses it for a doer. That is the whole
    reason the field names an instance rather than an adapter: a plan cannot
    reach past the configuration to pick a product.
    """
    doer = _Signing(None, adapter_id="claude-code")
    store = a_bound_store(tmp_path, verifier="nobody-declared-this")
    doer._store = store
    runtime = ControlRuntime(store, AdapterRegistry([doer]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(
        store, instance_id=DOER, capability="dispatch",
        arguments={"handoff": "packet-001"}, node_id=NODE)
    authorization = runtime.authorize(a_confirmation(proposal), budget=a_budget())

    with pytest.raises(ExecutionError, match="declares no instance"):
        runtime.execute(authorization)


def test_a_step_that_carries_nothing_out_may_not_name_a_verifier():
    """A gate decides; there is no execution for a verifier to judge."""
    from conductor.command.contracts import ContractError

    with pytest.raises(ContractError, match="nothing to verify"):
        GraphNode(node_id="confirm-gate", kind="gate", title="Human gate",
                  gate_id="gate-confirm-do", verifier_instance_id=CHECKER)


def _a_verified_run(tmp_path):
    """One honest run, driven to `succeeded` by a plan-named verifier."""
    doer = _Signing(None, adapter_id="claude-code")
    checker = _Signing(None, adapter_id="codex")
    store = a_bound_store(tmp_path, verifier=CHECKER)
    doer._store = checker._store = store
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(
        store, instance_id=DOER, capability="dispatch",
        arguments={"handoff": "packet-001"}, node_id=NODE)
    attempt = runtime.execute(
        runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    return store


def _forge_the_signature(store, signer: str) -> None:
    """Re-sign the run's one verification on disk, as a tamperer would.

    Nothing goes through the store's own writer, which is the whole point: the
    writer already refuses this, and the question is whether the READER does.
    """
    import json
    from pathlib import Path

    from conductor.command.contracts import canonical_json

    path = Path(store.run_path(RUN_ID)) / "records.jsonl"
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    forged = [row for row in rows if row["record_type"] == "evidence"]
    assert len(forged) == 1, f"expected one verification, found {len(forged)}"
    forged[0]["record"]["created_by"] = signer
    forged[0]["record"]["verified_by"] = signer
    path.write_text("".join(canonical_json(row) + "\n" for row in rows),
                    encoding="utf-8", newline="\n")


def test_a_journal_that_forges_the_doers_signature_is_corrupt_on_replay(tmp_path):
    """The DURABLE lock, asked of raw bytes rather than through the runtime.

    A mutation found this missing and it is the important kind: deleting the
    signature requirement from `attempt_replay` left every other test here
    green, because the runtime refuses a wrong signature first and the store's
    rule was never reached independently. That is a guard standing green
    against the exact thing it bans.

    The store's rule exists for bytes THIS PROCESS DID NOT WRITE -- it runs on
    the replay path as well as the append path, under the comment "hold causal
    relations even when bytes were written outside this process". So it is
    asked here the way a tamperer would ask it: an honest run is driven to
    success through the real runtime, then the journal is edited on disk and
    re-read.
    """
    from conductor.command.run_store import CorruptRun

    store = _a_verified_run(tmp_path)
    # The control: these exact bytes replay clean before anything is edited.
    assert RunStore(tmp_path).read(RUN_ID).records

    _forge_the_signature(store, "claude-code")

    with pytest.raises(CorruptRun, match="verified by"):
        RunStore(tmp_path).read(RUN_ID)


# -- the template half: a ROLE, and a binding that must cover it -------------


def a_template(*, verifier_role):
    """The smallest publishable workflow, its step naming a verifier role or not."""
    from conductor.command.graph_template import GraphTemplate

    step = {"kind": "task", "node_id": NODE, "title": "Do the work",
            "role_id": "role-implementer", "capability": "dispatch",
            "arguments": {"handoff": "packet-001"}, "resources": []}
    if verifier_role is not None:
        step["verifier_role_id"] = verifier_role
    return GraphTemplate.from_dict({
        "schema_version": 1, "template_id": "flow", "revision": 1,
        "title": "One reviewed dispatch",
        "nodes": [
            {"kind": "gate", "node_id": "confirm-gate", "title": "Human gate",
             "gate_id": "gate-confirm-do", "resources": []},
            step,
        ],
        "edges": [{"from_node": "confirm-gate", "to_node": NODE}],
    })


def test_a_binding_must_cover_the_verifier_role_like_any_other():
    """A role that verifies is a role.

    A binding that skipped it would leave `materialize` inventing an instance
    or dropping the field, so both directions are held: the role appears in
    what a binding must cover, and a binding that omits it produces no plan.
    """
    from conductor.command.graph_template import RunBinding, materialize

    template = a_template(verifier_role="role-checker")
    assert "role-checker" in template.roles
    assert a_template(verifier_role=None).roles == ("role-implementer",)

    with pytest.raises(Exception):
        materialize(
            template, RunBinding(assignments={"role-implementer": DOER}),
            CONFIG, graph_id="g", run_id=RUN_ID, created_at=NOW)


def test_the_role_becomes_the_instance_the_binding_named():
    """The whole ruling in one assertion: a template says WHO in its own
    vocabulary, and the run's binding decides which participant that is."""
    from conductor.command.graph_template import RunBinding, materialize

    plan = materialize(
        a_template(verifier_role="role-checker"),
        RunBinding(assignments={"role-implementer": DOER,
                                "role-checker": CHECKER}),
        CONFIG, graph_id="g", run_id=RUN_ID, created_at=NOW)

    step = next(node for node in plan.nodes if node.node_id == NODE)
    assert step.instance_id == DOER
    assert step.verifier_instance_id == CHECKER
    # And a template naming none materializes a plan naming none, which is what
    # every workflow written before this field existed says.
    plain = materialize(
        a_template(verifier_role=None),
        RunBinding(assignments={"role-implementer": DOER}),
        CONFIG, graph_id="g", run_id=RUN_ID, created_at=NOW)
    assert next(node for node in plain.nodes
                if node.node_id == NODE).verifier_instance_id is None


def test_a_template_step_that_does_no_work_may_not_name_a_verifier():
    """A template may not name an INSTANCE, so this is the role-level twin of
    the definition's rule: a step binding no role of its own carries nothing
    out, and has nothing for a verifier to judge."""
    from conductor.command.contracts import ContractError
    from conductor.command.graph_template import TemplateNode

    with pytest.raises(ContractError, match="nothing to verify"):
        TemplateNode(node_id="confirm-gate", kind="gate", title="Human gate",
                     gate_id="gate-confirm-do", resources=(),
                     verifier_role_id="role-checker")
