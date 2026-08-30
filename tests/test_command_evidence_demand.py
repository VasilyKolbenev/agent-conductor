"""What a plan's evidence demand DOES to a run, on every road that can reach it.

`required_evidence` is durable next door. Here it is spent, and the whole point
of the field is that it is spent in more than one place:

    ControlRuntime._causal_evidence   the honest road, before a succeeded
                                      receipt is written at all
    run_store.append                  the record offered to the writer
    run_store.read                    the same rule over bytes THIS PROCESS
                                      DID NOT WRITE

The last one is what the field is for. `EvidenceRef.digest` is optional and
`attempt_replay._validate_evidence` never read it, so a forged journal carrying
a verification with `"digest": null` behind a `succeeded` receipt replayed as
sound. It still does -- for every plan that asks for nothing, which is every
plan that exists. What changed is that a plan may now ask.

Two shapes are held here that a single-layer test would miss:

- **the layer-above trap.** A rule that lived only in the store would still stop
  the forgery, so the runtime witness below asserts the STATE the honest road
  lands on -- `verification_failed`, with the plan's own sentence -- and not
  merely that success did not happen. A build whose runtime forgot the demand
  reaches the store's refusal instead, and raises out of `execute` rather than
  recording a terminal attempt, which is a different product.
- **the control.** The forged bytes are replayed twice, against a demanding plan
  and against one that demands nothing, so the refusal is provably the PLAN's
  and not a blanket change to what a journal may say.

The forgery is driven the way a tamperer would: an honest run is taken to
`succeeded` through the real runtime, and only then is the journal edited on
disk. Nothing here builds a broken run through the writer, because the writer
already refuses it and the question is whether the READER does.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry, AdapterVerification
from conductor.command.attempt_replay import validate_event_result
from conductor.command.contracts import EvidenceRef, canonical_json
from conductor.command.graph_causality import demanded_evidence
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.graph_values import REQUIRED_EVIDENCE
from conductor.command.run_store import CorruptRun, RunStore, StoreError, snapshot_digest
from conductor.command.runtime import AttemptState, ControlRuntime

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
NODE = "do"
#: A well-formed digest, in the one grammar `contract_values._digest` admits.
DIGEST = "sha256:" + "1f" * 32

#: How an adapter SATISFIES each word the vocabulary carries, as the evidence
#: fields its verification must then write. Held equal to `REQUIRED_EVIDENCE` in
#: both directions below, so a word ADDED to that frozenset reds here until
#: somebody has shown a real journal that reaches `succeeded` under it. A demand
#: nothing can meet is a plan that cannot run, and the closed set is exactly
#: where that becomes possible to ship by accident.
SATISFIED_BY = {"digest": {"digest": DIGEST}}


class _Signing(ScriptedAdapter):
    """Answers `verified` and writes the one verification row itself.

    The evidence writer is test-local because the adapter API returns refs and
    receives no append power -- the stand-in `test_command_plan_verifier` makes
    next door, for the same reason. What varies here is the one field the plan
    can demand: `fields` is spread into the row, so the same adapter writes a
    digest-bearing verification and a digest-less one and the run is otherwise
    identical.
    """

    def __init__(self, store, *, fields=None, **knobs):
        super().__init__(verify_state="verified", **knobs)
        self._store = store
        self._fields = dict(fields or {})

    def verify(self, request, result):
        self.verify_calls += 1
        signature = self.manifest.adapter_id
        evidence_id = f"evidence-{signature}"
        self._store.append(EvidenceRef(
            evidence_id=evidence_id, run_id=request.run_id, kind="verification",
            uri=f"verification/{request.action_id}",
            label="durable verification fact", created_by=signature,
            observed_at=NOW, verification="verified", verified_by=signature,
            verified_at=NOW, **self._fields))
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state="verified", observed_at=NOW, detail="scripted verification",
            evidence_refs=(evidence_id,))


def a_plan(store, *, required_evidence):
    """One gate and one dispatching step, the step making a demand or not."""
    nodes = (
        GraphNode(node_id="confirm-gate", kind="gate", title="Human gate",
                  gate_id="gate-confirm-do"),
        GraphNode(node_id=NODE, kind="task", title="Do the work",
                  instance_id=DOER, capability="dispatch",
                  arguments={"handoff": "packet-001"},
                  required_evidence=required_evidence),
    )
    definition = GraphDefinition(
        graph_id="graph-001", run_id=RUN_ID, created_at=NOW, nodes=nodes,
        edges=(GraphEdge(from_node="confirm-gate", to_node=NODE),))
    store.append(definition)
    return definition


def a_bound_store(tmp_path, *, required_evidence):
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    a_plan(store, required_evidence=required_evidence)
    return store


def a_run_of(tmp_path, *, required_evidence, fields, node_id=NODE):
    """Drive one whole attempt through the real runtime and hand back both ends."""
    doer = _Signing(None, adapter_id="claude-code", fields=fields)
    store = a_bound_store(tmp_path, required_evidence=required_evidence)
    doer._store = store
    runtime = ControlRuntime(store, AdapterRegistry([doer]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(
        store, instance_id=DOER, capability="dispatch",
        arguments={"handoff": "packet-001"}, node_id=node_id)
    attempt = runtime.execute(
        runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    return store, attempt


def journal(store) -> Path:
    return Path(store.run_path(RUN_ID)) / "records.jsonl"


def rows_of(store) -> list[dict]:
    return [json.loads(line) for line
            in journal(store).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def rewrite(store, rows) -> None:
    """Put edited rows back as canonical bytes, the way a tamperer would.

    Nothing goes through the store's own writer. The writer already refuses
    what is being written here; the question this module asks is whether the
    READER does.
    """
    journal(store).write_text(
        "".join(canonical_json(row) + "\n" for row in rows),
        encoding="utf-8", newline="\n")


def strip_the_digest(store) -> None:
    """Take the digest off the run's one verification, on disk."""
    rows = rows_of(store)
    forged = [row for row in rows if row["record_type"] == "evidence"]
    assert len(forged) == 1, f"expected one verification, found {len(forged)}"
    assert forged[0]["record"]["digest"] is not None, (
        "the run under forgery never named a digest, so nothing was removed")
    forged[0]["record"]["digest"] = None
    rewrite(store, rows)


# -- the demand works ---------------------------------------------------------


@pytest.mark.parametrize("word", sorted(REQUIRED_EVIDENCE))
def test_a_demanding_step_reaches_succeeded_when_its_verification_says_so(
        tmp_path, word):
    """The positive control, and the proof that no word of the set is dead.

    Parametrized over the vocabulary itself rather than over a list written
    here, so the day the frozenset grows this test asks the new word for a real
    journal instead of taking the widening on trust.
    """
    store, attempt = a_run_of(
        tmp_path, required_evidence=word, fields=SATISFIED_BY[word])

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    standing = [row.value for row in store.read(RUN_ID).records
                if row.kind == "evidence"]
    assert len(standing) == 1 and standing[0].digest == DIGEST
    # And the bytes replay as sound from a store that wrote none of them.
    assert RunStore(tmp_path).read(RUN_ID).records


def test_the_vocabulary_has_no_word_without_a_journal_that_reaches_it():
    """A demand nothing can satisfy is a plan that cannot run.

    Held in both directions: a word with no way to satisfy it would ship a step
    nobody could ever complete, and a way to satisfy a word the contract does
    not carry is a test proving something about a plan no document may state.
    """
    assert set(SATISFIED_BY) == set(REQUIRED_EVIDENCE)


def test_a_demanding_step_whose_verification_names_nothing_fails_verification(
        tmp_path):
    """The honest road, and it lands on a STATE rather than on an exception.

    This is the layer-above trap made mechanical. The store refuses these bytes
    too -- that is the next section -- so a runtime that forgot the demand would
    still not record a success. What it would do instead is raise out of
    `execute` while appending the receipt, leaving an authorized action with no
    terminal record and an operator with a traceback. So the assertion is the
    state and the sentence, not merely the absence of `succeeded`.
    """
    store, attempt = a_run_of(tmp_path, required_evidence="digest", fields={})

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.state
    assert attempt.verification_evidence == ()
    # The FACT: this refusal has a detail of its OWN, read from the runtime
    # rather than typed here -- so a build that collapsed the two sentences reds
    # whichever of them it kept. The word below is the change-detector beside it,
    # and it is free to be reworded as long as it still says which field spoke.
    assert attempt.receipt.detail != ControlRuntime._EVIDENCE_UNSOUND
    assert "digest" in attempt.receipt.detail, attempt.receipt.detail
    # A terminal receipt was recorded, and it is not a success.
    outcomes = [row.value.outcome for row in store.read(RUN_ID).records
                if row.kind == "action_result"]
    assert outcomes == ["verification_failed"], outcomes


def test_the_plans_refusal_reads_differently_from_an_unsound_evidence_row(
        tmp_path):
    """Two refusals, two sentences. A person is owed which relation spoke.

    Collapsing them into one would make the field invisible on the screen a
    person actually meets: `verification_failed` with "did not satisfy the
    causal store relation" says nothing about a plan having asked for more.
    """
    _, demanded = a_run_of(tmp_path, required_evidence="digest", fields={})
    assert demanded.receipt.detail != ControlRuntime._EVIDENCE_UNSOUND

    # The other refusal is unchanged, and it is the one the verifier suite pins:
    # a verification for another action does not stand at all.
    doer = _Signing(None, adapter_id="claude-code", fields={"digest": DIGEST})
    store = a_bound_store(tmp_path / "other", required_evidence="digest")
    doer._store = store
    runtime = ControlRuntime(store, AdapterRegistry([doer]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(
        store, instance_id=DOER, capability="dispatch",
        arguments={"handoff": "packet-001"}, node_id=NODE)
    authorization = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    doer.verify = lambda request, result: AdapterVerification(
        adapter_id=doer.manifest.adapter_id, action_id=request.action_id,
        state="verified", observed_at=NOW, detail="names evidence nobody wrote",
        evidence_refs=("evidence-nobody-wrote",))
    unsound = runtime.execute(authorization)

    assert unsound.state is AttemptState.VERIFICATION_FAILED
    assert unsound.receipt.detail == ControlRuntime._EVIDENCE_UNSOUND


def test_a_step_that_demands_nothing_still_succeeds_on_a_digestless_verification(
        tmp_path):
    """The field is a DEMAND, not a default, and this is what pays for that.

    Four durable artifacts write a digest-less verified row behind a succeeded
    result -- two frozen ALPHA-1 fixtures, the ALPHA-1 fixture provider, and the
    shipped demo, which does it on a run that really does carry a materialized
    plan. Making the digest unconditional would make all four unreadable, and
    the frozen ones may not be rewritten.
    """
    store, attempt = a_run_of(tmp_path, required_evidence=None, fields={})

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    standing = [row.value for row in store.read(RUN_ID).records
                if row.kind == "evidence"]
    assert len(standing) == 1 and standing[0].digest is None
    assert RunStore(tmp_path).read(RUN_ID).records


def test_the_shipped_demo_still_writes_a_story_this_build_can_read(tmp_path):
    """The artifact closest to the danger, driven rather than described.

    `demo_scenario` materializes `dalio-v2`, so it is a PLANNED run -- which is
    why scoping the correction to "runs with a plan" would not have saved it --
    and it mints a verification with no digest and appends a `succeeded` receipt
    naming it. It is read back through `RunStore.read`, which re-validates every
    causal relation from the bytes on disk.
    """
    from conductor.command import demo_scenario

    demo_scenario.build(tmp_path)
    recovered = RunStore(tmp_path).read(demo_scenario.RUN_ID)

    evidence = [row.value for row in recovered.records if row.kind == "evidence"]
    assert evidence and all(row.digest is None for row in evidence)
    assert any(row.kind == "graph_definition" for row in recovered.records)
    assert "succeeded" in [row.value.outcome for row in recovered.records
                           if row.kind == "action_result"]


# -- the forged journal, and its control --------------------------------------


def test_a_journal_that_strips_the_demanded_digest_is_corrupt_on_replay(tmp_path):
    """The DURABLE lock, asked of raw bytes rather than through the runtime.

    The runtime refuses a digest-less verification before a succeeded receipt is
    ever written, so its rule can never be reached by a tamperer -- which is
    exactly why the store's rule cannot be tested through it. An honest run is
    taken to `succeeded` with a digest-bearing verification, the digest is then
    removed on disk, and the journal is re-read by a store that wrote none of it.
    """
    store, attempt = a_run_of(
        tmp_path, required_evidence="digest", fields={"digest": DIGEST})
    assert attempt.state is AttemptState.SUCCEEDED
    # The control: these exact bytes replay clean before anything is edited.
    assert RunStore(tmp_path).read(RUN_ID).records

    strip_the_digest(store)

    with pytest.raises(CorruptRun, match="names no digest"):
        RunStore(tmp_path).read(RUN_ID)


def test_the_same_forged_bytes_are_refused_by_the_writer_as_well(tmp_path):
    """The append road, offered the forgery the way a caller would offer it.

    The journal is edited down to the prefix a tamperer would have -- a
    digest-less verification standing behind an observed attempt -- and the
    succeeded receipt is then handed to `store.append`. Both roads run the same
    `_validate_new_relation`, and this is the half that a replay test alone
    would leave unproved.
    """
    store, attempt = a_run_of(
        tmp_path, required_evidence="digest", fields={"digest": DIGEST})
    assert attempt.state is AttemptState.SUCCEEDED
    receipt = attempt.receipt

    strip_the_digest(store)
    rewrite(store, [row for row in rows_of(store)
                    if row["record_type"] != "action_result"])
    # The prefix alone is sound: the demand fires on the terminal receipt, so
    # what follows is the writer's verdict and not a corrupt run.
    assert RunStore(tmp_path).read(RUN_ID).records

    with pytest.raises(StoreError, match="names no digest"):
        RunStore(tmp_path).append(receipt)


def test_the_identical_forgery_replays_as_sound_when_the_plan_asked_nothing(
        tmp_path):
    """The control, and without it the refusal above proves nothing about plans.

    The same bytes, the same edit, the same reader -- and a node that makes no
    demand. If this reds, the digest became unconditional and four durable
    artifacts stopped being readable; if the test above greens while this one
    does too, the refusal belongs to the plan and to nothing else.
    """
    store, attempt = a_run_of(
        tmp_path, required_evidence=None, fields={"digest": DIGEST})
    assert attempt.state is AttemptState.SUCCEEDED

    strip_the_digest(store)

    recovered = RunStore(tmp_path).read(RUN_ID)
    standing = [row.value for row in recovered.records if row.kind == "evidence"]
    assert len(standing) == 1 and standing[0].digest is None
    assert "succeeded" in [row.value.outcome for row in recovered.records
                           if row.kind == "action_result"]


# -- what the plan-derived hold answers, and what it refuses to invent ---------


def test_the_hold_says_nothing_about_a_run_whose_plan_says_nothing(tmp_path):
    """Four shapes, all of them `None`, and every journal that exists is one.

    A request naming no node, a run following no graph, a node the graph does
    not carry, and a node carrying no demand. Each is a road a hold derived from
    frozen bytes must decline rather than guess at, and together they are why no
    stored run changes meaning.
    """
    store = a_bound_store(tmp_path, required_evidence="digest")
    unbound = a_proposal(store, instance_id=DOER, capability="dispatch",
                         arguments={"handoff": "packet-001"})
    runtime = ControlRuntime(store, AdapterRegistry([]), clock=fixed_clock(),
                             ids=fixed_ids())
    request = runtime.authorize(a_confirmation(unbound), budget=a_budget()).request
    recovered = store.read(RUN_ID)

    # An UNBOUND request: legal, and older than graphs.
    assert request.node_id is None
    assert demanded_evidence(recovered, request.action_id) is None
    # An action this run never authorized.
    assert demanded_evidence(recovered, "action-nobody-requested") is None

    # A run with no graph at all, and a bound run whose node demands nothing.
    plain = RunStore(tmp_path / "plain")
    plain.create_run(a_run(run_id=RUN_ID, mode="confirm",
                           config_digest=snapshot_digest(CONFIG)), CONFIG)
    bare = a_proposal(plain, instance_id=DOER, capability="dispatch",
                      arguments={"handoff": "packet-001"})
    bare_runtime = ControlRuntime(plain, AdapterRegistry([]),
                                  clock=fixed_clock(), ids=fixed_ids())
    bare_request = bare_runtime.authorize(
        a_confirmation(bare), budget=a_budget()).request
    assert demanded_evidence(plain.read(RUN_ID), bare_request.action_id) is None

    silent, silent_attempt = a_run_of(
        tmp_path / "silent", required_evidence=None, fields={})
    assert demanded_evidence(
        silent.read(RUN_ID), silent_attempt.request.action_id) is None


def test_the_hold_reads_the_demand_off_the_plan_and_not_off_the_evidence(
        tmp_path):
    """The value comes from the run's own graph record, which a forgery cannot
    reach without rewriting the plan -- and rewriting the plan moves the graph
    the run says it follows."""
    store, attempt = a_run_of(
        tmp_path, required_evidence="digest", fields={"digest": DIGEST})

    assert demanded_evidence(
        store.read(RUN_ID), attempt.request.action_id) == "digest"


# -- the signature, and every caller that predates it -------------------------


def test_the_demand_is_keyword_only_so_no_caller_can_slide_into_signer(tmp_path):
    """A fifth POSITIONAL parameter is a value that can land in the wrong slot.

    `signer` and `demanded` are both optional strings read off the same plan, so
    a positional `demanded` would be a mistake nothing could catch: passing one
    where the other belongs type-checks, runs, and quietly judges the evidence
    against the wrong question. Keyword-only closes it by construction.
    """
    parameter = inspect.signature(validate_event_result).parameters["demanded"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None
    positional = [name for name, row in
                  inspect.signature(validate_event_result).parameters.items()
                  if row.kind is not inspect.Parameter.KEYWORD_ONLY]
    assert positional == ["values", "result", "events", "signer"]
