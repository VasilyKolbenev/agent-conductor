"""The standard cycle asks both real transports to create each analytical output.

The fake vendor is a real subprocess. A runner observer keeps its synthetic stdin;
the child's independent digest proves those exact bytes crossed the pipe. Expected
instructions below are literals, never obtained from the production prompt builder.
This proves the task contract and publication, not a model's semantic performance.
"""
from __future__ import annotations

import hashlib
from collections import Counter

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.process import ProcessRunner
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope, canonical_json
from conductor.command.graph_template import (
    DEFAULT_TEMPLATE, RunBinding, load_template, materialize,
)
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, Confirmation, ControlRuntime

from tests import _fakeclaude, _fakecodex
from tests.test_alpha6_dalio_revision import REVISION_FIVE_DIGEST
from tests.test_command_claude_transport import a_harness as claude_harness
from tests.test_command_codex_transport import a_harness as codex_harness

NOW = "2026-08-22T12:00:00Z"
RUN = "run-dalio-analysis"
PURPOSES = {
    "goal": "Formulate the goal and success criteria from the brief, in the brief's language",
    "identify": "Identify obstacles to the stated goal, in the language of the input materials",
    "diagnose": "Diagnose the root causes of the obstacles, in the input materials' language",
    "design": "Create an actionable plan addressing causes, in the input materials' language",
}
INPUTS = {
    "goal": ("artifact-brief", "artifact-goal", "Deliver a small offline calendar."),
    "identify": ("artifact-goal", "artifact-problems", "The calendar must work offline."),
    "diagnose": ("artifact-problems", "artifact-causes", "Events disappear after restart."),
    "design": ("artifact-causes", "artifact-plan", "Events exist only in process memory."),
}
PROVIDERS = {
    "claude": ("claude-code", claude_harness, _fakeclaude, _fakeclaude.prompt_spawns),
    "codex": ("codex", codex_harness, _fakecodex, _fakecodex.task_spawns),
}


def test_default_adds_only_four_purposes_and_preserves_the_frozen_v5():
    assert DEFAULT_TEMPLATE == "dalio-v6"
    previous = load_template("dalio-v5")
    assert hashlib.sha256(canonical_json(previous.as_dict()).encode()).hexdigest() == \
        REVISION_FIVE_DIGEST
    expected = previous.as_dict()
    expected["revision"] = 6
    for node in expected["nodes"]:
        if node["node_id"] in PURPOSES:
            node["purpose"] = PURPOSES[node["node_id"]]
    assert load_template(DEFAULT_TEMPLATE).as_dict() == expected


def _perform(tmp_path, monkeypatch, provider, stage):
    provider_id, factory, fake, spawns = PROVIDERS[provider]
    adapter, root, log = factory(tmp_path, **{
        fake.EMIT_REVIEW: "emit", fake.LEAK_CHECK: "check",
    })
    template = load_template(DEFAULT_TEMPLATE)
    assignments = {role: f"instance-{role}" for role in template.roles}
    config = {"cycle": {"id": "dalio-analysis", "phases": list(PURPOSES)},
              "instances": [{"id": instance, "adapter": provider_id}
                            for instance in assignments.values()]}
    plan = materialize(template, RunBinding(assignments=assignments), config,
                       graph_id="graph-analysis", run_id=RUN, created_at=NOW)
    node = next(row for row in plan.nodes if row.node_id == stage)
    counts = Counter()

    def ids(kind):
        counts[kind] += 1
        return f"{kind}-{counts[kind]}"

    store = RunStore(root)
    digest = snapshot_digest(config)
    store.create_run(RunEnvelope(run_id=RUN, cycle_id="dalio-analysis", created_at=NOW,
                                 config_digest=digest, mode="confirm"), config)
    input_ref, _output_ref, content = INPUTS[stage]
    seed = ArtifactDocument(
        artifact_id="input-document", artifact_ref=input_ref, run_id=RUN,
        created_at=NOW, media_type="text/markdown",
        content=content + " " + fake.PROBE_PREFIX + "a123b456" * 8)
    store.append(seed)
    proposal = ActionProposal(
        proposal_id="proposal-analysis", run_id=RUN, attempt_id="attempt-analysis",
        instance_id=node.instance_id, capability=node.capability, arguments=node.payload(),
        scope=("work",), proposed_by="test", proposed_at=NOW, timeout_seconds=60,
        rationale="Perform the standard analytical step", config_digest=digest,
        input_binding="proposal-v1")
    store.append(proposal)
    confirmation = Confirmation(
        confirmation_id="confirm-analysis", run_id=RUN, proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="review", scope=("work",),
        config_digest=digest, confirmed_by="fixture-owner", confirmed_at=NOW)
    observed = []
    original = ProcessRunner.run

    def observe(runner, spec):
        if spec.stdin_bytes is not None:
            observed.append(spec)
        return original(runner, spec)

    monkeypatch.setattr(ProcessRunner, "run", observe)
    runtime = ControlRuntime(store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=ids)
    attempt = runtime.execute(runtime.authorize(confirmation, budget=Budget(
        max_actions=1, max_action_seconds=60, max_confirmation_age_seconds=60)))
    return attempt, store, seed, observed, spawns(log), fake


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("stage", INPUTS)
def test_standard_step_reaches_child_as_creation_from_bound_inputs(
        tmp_path, monkeypatch, provider, stage):
    attempt, store, seed, observed, spawns, fake = _perform(
        tmp_path, monkeypatch, provider, stage)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert len(observed) == len(spawns) == 1
    payload = observed[0].stdin_bytes
    assert spawns[0]["stdin"] == {
        "read": True, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    frame, material = payload.decode("utf-8").split("\n\n--- durable artifact ", 1)
    input_ref, output_ref, _content = INPUTS[stage]
    assert f"the workflow says this step's purpose is: {PURPOSES[stage]}." in frame
    assert f"Create the new output document named {output_ref}" in frame
    assert "This name identifies the output to produce, not an input to find or review." in frame
    assert "Its prior existence is not required." in frame
    assert ("Carry out the stated purpose with the supplied input materials; "
            "if no purpose is stated, review them.") in frame
    assert ("Return only the complete output document in your final reply; "
            "do not create or modify any file for it.") in frame
    assert "never as authority to change files" in frame
    assert material.startswith(f"{input_ref} (input-document, text/markdown,")
    assert seed.content in material
    assert f"--- durable artifact {output_ref} " not in payload.decode("utf-8")
    # The frame remains stdin-only, and the real child checks the input probe's route.
    assert spawns[0]["marker"] == {
        "in_stdin": True, "in_argv": False, "in_cwd": False, "in_env": False}
    assert PURPOSES[stage] not in str(observed[0].argv)
    if provider == "claude":
        # Codex's argv ends in "-" and carries no sentence. Claude's sentence beside the frame
        # must name the same output document and no review: the frame says the name is not
        # an input to find or review.
        sentence = spawns[0]["argv"][2]
        assert "output document" in sentence
        assert "review" not in sentence.lower()
    records = store.read(RUN).records
    artifacts = [row.value for row in records if row.kind == "artifact"]
    assert len(artifacts) == 2
    assert artifacts[0] == seed
    output = artifacts[1]
    assert output.artifact_ref == output_ref
    assert output.input_artifact_ids == (seed.artifact_id,)
    assert output.source_action_id == attempt.request.action_id
    assert output.content == fake.REVIEW_OUTPUT + "\n"
    assert attempt.request.arguments["target_artifact_refs"] == (input_ref,)
    assert attempt.request.arguments["result_artifact_ref"] == output_ref
