"""A plan-named checker is a second real native process, not a doer verdict."""
from dataclasses import replace

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.base import VerifierBinding
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, ControlRuntime
from tests import _fakeclaude, _fakecodex, _fakegrok
from tests.test_command_claude_transport import a_harness, NOW, _Ids
from tests.test_command_codex_transport import a_harness as codex_harness
from tests.test_command_grok_transport import a_harness as grok_harness
from tests.test_command_runtime_authorize import a_budget, a_confirmation


RUN = "run-001"
CHECKER = "codex-review"


def setup(tmp_path, *, cross=False, review=False, verdict="enabled-verdict-accept",
          checker_write=False, secret=None, secret_place=None, instruction_document=None,
          checker_auth="api_key", checker_auth_home="", **checker_extra):
    fake = _fakecodex if cross else _fakeclaude
    checker_knobs = {fake.EMIT_VERDICT: verdict}
    if checker_write:
        checker_knobs[fake.VERDICT_WRITE_FILE] = "forbidden.txt:checker changed work"
    knobs = ({_fakeclaude.EMIT_REVIEW: "enabled-review-output"} if review else
             {_fakeclaude.WRITE_FILE: "result.txt:" + (secret if secret_place == "file" else "done")})
    if secret:
        knobs["PRIVATE_CREDENTIAL"] = secret
    if not cross:
        knobs.update(checker_knobs)
    doer, root, log = a_harness(tmp_path / "doer", **knobs)
    checker, check_log = doer, log
    if cross:
        checker, _, check_log = codex_harness(
            tmp_path / "checker", root=root, auth=checker_auth,
            auth_home=checker_auth_home, **checker_knobs, **checker_extra)
    runtime, authorization, store = _run_state(root, doer, checker, cross, review,
        secret, secret_place, instruction_document)
    return runtime, authorization, store, doer, checker, log, check_log, root


def _run_state(root, doer, checker, cross, review, secret, secret_place, instruction_document,
               *, doer_model="doer-model", same_input=False):
    config = {"cycle": {"id": "default-orbit", "phases": ["implement", "review"]},
              "instances": [{"id": "claude-dev", "adapter": doer.manifest.adapter_id,
                             **({"model": doer_model} if doer_model else {})},
                            {"id": CHECKER, "adapter": checker.manifest.adapter_id,
                             "model": "checker-model"}]}
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id=RUN, cycle_id="default-orbit", created_at=NOW,
                                config_digest=snapshot_digest(config), mode="confirm"), config)
    args = _arguments(review, secret_place == "document")
    if same_input:
        args["artifact_refs"] = [args["instruction_ref"]]
    if instruction_document is not None:
        store.append(instruction_document)
    if review or secret_place == "document":
        store.append(ArtifactDocument(artifact_id="input-001", artifact_ref="input-ref", run_id=RUN,
                                      created_at=NOW, media_type="text/markdown",
                                      content=secret if secret_place == "document" else "Review this input."))
    store.append(GraphDefinition(graph_id="graph-001", run_id=RUN, created_at=NOW,
        nodes=(GraphNode(node_id="confirm-gate", kind="gate", title="Human", gate_id="gate-confirm-do"),
               GraphNode(node_id="do", kind="task", title="Do work", instance_id="claude-dev",
                         capability="review" if review else "dispatch", arguments=args,
                         verifier_instance_id=CHECKER)),
        edges=(GraphEdge(from_node="confirm-gate", to_node="do"),)))
    store.append(DecisionReceipt(receipt_id="decision-gate-confirm-do", run_id=RUN,
        gate_id="gate-confirm-do", action="approve", actor="owner", decided_at=NOW,
        reason="Let the work through", scope_refs=("work",), config_digest=snapshot_digest(config)))
    proposal = ActionProposal(proposal_id="proposal-001", run_id=RUN, attempt_id="attempt-001",
        instance_id="claude-dev", capability="review" if review else "dispatch", arguments=args,
        scope=("work",), proposed_by="owner", proposed_at=NOW, timeout_seconds=60,
        rationale="Judge the actual work independently", config_digest=snapshot_digest(config),
        node_id="do", input_binding="proposal-v1")
    store.append(proposal)
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker] if cross else [doer]),
                             clock=lambda: NOW, ids=_Ids())
    authorization = runtime.authorize(a_confirmation(proposal, confirmed_at=NOW), budget=a_budget())
    return runtime, authorization, store


def _arguments(review, with_input):
    if review:
        return {"work_item_id": "work-001", "target_artifact_refs": ["input-ref"],
                "result_artifact_ref": "review-result", "review_profile": "quality"}
    return {"work_item_id": "work-001", "instruction_ref": "instr-001", "profile": "implement",
            "artifact_refs": ["input-ref"] if with_input else [], "output_limit_profile": "small"}


@pytest.mark.parametrize("cross", [False, True])
@pytest.mark.parametrize("review", [False, True])
def test_same_or_different_harness_really_spawns_checker_and_signs_its_identity(tmp_path, cross, review):
    runtime, authorization, store, doer, checker, log, check_log, root = setup(
        tmp_path, cross=cross, review=review)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    prompts = _fakeclaude.prompt_spawns(log)
    checks = _fakecodex.task_spawns(check_log) if cross else prompts[1:]
    assert len(prompts) == (1 if cross else 2)
    assert len(checks) == 1
    argv = checks[0]["argv"]
    assert "checker-model" in argv and "doer-model" not in argv
    assert ("read-only" if cross else "plan") in argv
    assert prompts[0]["stdin"]["sha256"] != checks[0]["stdin"]["sha256"]
    evidence = [row.value for row in store.read(RUN).records if row.kind == "evidence"]
    assert len(evidence) == 1 and evidence[0].verifier_instance_id == CHECKER
    assert evidence[0].verified_by == ("codex" if cross else "claude-code")
    assert doer._check_materials == {} and doer._attempts == {} and doer._review_attempts == {}
    _released(doer, checker)
    assert checker.verification_started(attempt.request) is True
    journals = tuple(root.rglob("records.jsonl"))
    assert len(journals) == 1
    raw = journals[0].read_bytes()
    assert b"VERDICT: accept" not in raw


@pytest.mark.parametrize("mode", ["reject", "missing", "write"])
def test_checker_refusal_no_verdict_or_write_never_becomes_success(tmp_path, mode):
    values = setup(tmp_path, verdict="enabled-verdict-reject" if mode == "reject"
                   else "enabled-verdict-no-answer" if mode == "missing" else "enabled-verdict-accept",
                   checker_write=mode == "write")
    runtime, authorization, store, doer, checker, log, _, _ = values
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert len(_fakeclaude.prompt_spawns(log)) == 2
    assert not [row for row in store.read(RUN).records if row.kind == "evidence"]
    _released(doer, checker)


@pytest.mark.parametrize("place", ["file", "document"])
def test_escaped_allowed_credential_in_material_stops_before_checker_spawn(tmp_path, place):
    secret = 'synthetic-quote"slash\\line\nprivate'
    runtime, authorization, store, doer, checker, log, _, _ = setup(
        tmp_path, secret=secret, secret_place=place)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert len(_fakeclaude.prompt_spawns(log)) == 1
    assert checker.verification_started(attempt.request) is False
    _released(doer, checker)


def test_material_ids_cannot_claim_a_document_the_doer_did_not_supply(tmp_path):
    runtime, authorization, store, doer, checker, log, _, _ = setup(tmp_path)
    prepared = doer.prepare(authorization.request)
    result = doer.execute(prepared)
    published = doer.publish(authorization.request, result)
    forged = replace(published, input_artifact_ids=("foreign-input",))
    answer = checker.verify_for(authorization.request, result,
        VerifierBinding(CHECKER, "claude-code", "checker-model"), forged)
    assert answer.state == "error" and answer.detail == "material_unavailable"
    assert len(_fakeclaude.prompt_spawns(log)) == 1
    doer.release(authorization.request)


def test_checker_uses_exact_consumed_instruction_even_after_file_and_ref_change(tmp_path, monkeypatch):
    old = ArtifactDocument(artifact_id="instruction-first", artifact_ref="instr-001",
        run_id=RUN, created_at=NOW, media_type="text/markdown", content="Exact reviewed instruction.")
    runtime, authorization, store, doer, checker, log, _, root = setup(
        tmp_path, instruction_document=old)
    original = doer.publish
    material = []
    consumed = []
    original_run = checker._runner.run
    def run(spec):
        if spec.stdin_bytes and spec.stdin_bytes.startswith(b"conduct independent verification"):
            consumed.append(old.content.encode() in spec.stdin_bytes
                            and b"Different later instruction." not in spec.stdin_bytes
                            and b"Different file instruction." not in spec.stdin_bytes)
        return original_run(spec)
    monkeypatch.setattr(checker._runner, "run", run)
    def publish(request, result):
        store.append(replace(old, artifact_id="instruction-later", content="Different later instruction."))
        (root / "instructions" / "instr-001.md").write_text("Different file instruction.")
        value = original(request, result)
        material.append(value)
        return value
    monkeypatch.setattr(doer, "publish", publish)
    # Registration snapshots optional seams, so re-register this instrumented doer.
    runtime._registry = AdapterRegistry([doer])
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert material[0].instruction == old.content
    assert material[0].instruction_document["artifact_id"] == old.artifact_id
    assert material[0].input_artifact_ids == (old.artifact_id,)
    assert consumed == [True]
    assert len(_fakeclaude.prompt_spawns(log)) == 2
    assert doer._check_materials == {}


def test_checker_capture_obeys_the_smaller_plan_budget(tmp_path, monkeypatch):
    runtime, authorization, store, doer, checker, log, _, _ = setup(tmp_path)
    original = checker._runner.run
    limits = []
    def run(spec):
        if spec.stdin_bytes and spec.stdin_bytes.startswith(b"conduct independent verification"):
            limits.append(spec.output_limit)
        return original(spec)
    monkeypatch.setattr(checker._runner, "run", run)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert limits == [4096]


def test_standing_checker_evidence_is_reused_without_another_spawn(tmp_path):
    runtime, authorization, store, doer, checker, log, _, _ = setup(tmp_path)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    answer = checker.verify_for(attempt.request, attempt.receipt,
        VerifierBinding(CHECKER, "claude-code", "checker-model"), None)
    assert answer.state == "verified"
    assert len(_fakeclaude.prompt_spawns(log)) == 2


def test_dispatch_only_doer_can_publish_to_checker_but_cannot_be_a_checker(tmp_path):
    doer, root, log = grok_harness(tmp_path / "grok", **{
        _fakegrok.WRITE_FILE: "result.txt:the Grok doer changed this"})
    checker, _, check_log = a_harness(tmp_path / "claude", root=root, **{
        _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
    registry = AdapterRegistry([doer, checker])
    assert registry.verifies_independently(doer.manifest.adapter_id, "dispatch") is False
    assert registry.verifies_independently(checker.manifest.adapter_id, "dispatch") is True
    assert callable(doer.publish) and callable(doer.release)
    runtime, authorization, store = _run_state(root, doer, checker, True, False, None, None, None,
                                              doer_model=None)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert len(_fakegrok.prompt_spawns(log)) == 1
    assert len(_fakeclaude.prompt_spawns(check_log)) == 1
    assert doer._check_materials == {} and doer._attempts == {}
    evidence = [row.value for row in store.read(RUN).records if row.kind == "evidence"]
    assert len(evidence) == 1 and evidence[0].verified_by == "claude-code"


def test_same_document_can_be_consumed_as_instruction_and_explicit_input(tmp_path):
    doer, root, log = a_harness(tmp_path, **{
        _fakeclaude.WRITE_FILE: "result.txt:done", _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
    document = ArtifactDocument(artifact_id="instruction-both", artifact_ref="instr-001",
        run_id=RUN, created_at=NOW, media_type="text/markdown", content="The instruction and input.")
    runtime, authorization, store = _run_state(root, doer, doer, False, False, None, None,
                                               document, same_input=True)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert len(_fakeclaude.prompt_spawns(log)) == 2


def _released(*adapters):
    for adapter in adapters:
        homes = adapter._workspace.homes_root()
        assert homes.is_dir(), "the asserted home root was never allocated"
        assert tuple(homes.iterdir()) == (), homes
        assert adapter._check_materials == {} and adapter._attempts == {}
        assert adapter._materials == {} and adapter._review_attempts == {}
        assert adapter._dispatch_inputs == {}
