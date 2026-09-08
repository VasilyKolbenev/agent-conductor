"""What turns a REPORTED success into a terminal one: the verify circuit.

The execute state machine next door owns the seven states and the roads a
result can go missing on. This module owns the one relation those roads all
funnel into -- whether a process that says it succeeded ever becomes a product
success -- because that relation is now global rather than per-adapter, and it
is the single place the whole product could be talked into believing an exit
code.

Succeeded has exactly three legs and needs all of them: the execution was
OBSERVED to succeed, the bound adapter answered ``verified``, and the refs it
named resolve to a durable ``EvidenceRef`` the store recorded AFTER that
observation. Every other answer -- ``mismatch``, ``error``, a verifier that
raised, and ``unavailable`` -- lands on ``verification_failed`` with EMPTY
evidence. ``unavailable`` used to be the exception: an adapter that exposed no
verifier had its process exit promoted to success. It is not an exception any
more, because it never was one adapter's problem -- any next harness could
answer ``unavailable`` and be believed for it.

The adapters, the store seeding and the authorize ground all come from the
execute circuit, which owns them.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import AdapterVerification
from conductor.command.contracts import EvidenceRef
from conductor.command.runtime import AttemptState
from conductor.command import verify_holds

from tests.test_command_runtime_authorize import NOW, a_store
from tests.test_command_runtime_execute import (
    ScriptedAdapter,
    VerifiedAdapter,
    authorized,
    kinds,
)


def seed_verified_evidence(store, adapter_id="claude-code", *,
                           action_id="action-fixed", evidence_id="scripted-evidence"):
    evidence = EvidenceRef(
        evidence_id=evidence_id, run_id="run-001", kind="verification",
        uri=f"verification/{action_id}", label="test-local verified fact",
        created_by=adapter_id, observed_at=NOW, verification="verified",
        verified_by=adapter_id, verified_at=NOW)
    store.append(evidence)
    return evidence


#: Each road out of the verify circuit, and the sentence the terminal receipt
#: is owed on it. The expected values are READ from `verify_holds` rather than
#: written here, so this is a relation between a road and the constant the
#: product names for it -- not a pin on prose, which is free to be rewritten in
#: one place and stay right in every other.
ROADS = {
    "raised": verify_holds.VERIFY_RAISED,
    "another action": verify_holds.NOT_THIS_ACTION,
    "unavailable": verify_holds.NO_VERIFIER,
    "mismatch": "adapter verification was mismatch",
    "unsound evidence": verify_holds.EVIDENCE_UNSOUND,
    "verified": verify_holds.VERIFIED,
}


def _drive(store, road):
    """One attempt down one of the six roads, through the real runtime."""
    adapter = {
        "raised": lambda: ScriptedAdapter(verify_raises=True),
        "another action": lambda: ScriptedAdapter(
            verify_state="verified",
            verification_changes={"action_id": "action-somebody-else"}),
        "unavailable": lambda: ScriptedAdapter(verify_state="unavailable"),
        "mismatch": lambda: ScriptedAdapter(verify_state="mismatch"),
        # Answers `verified` and names a ref nothing ever wrote, so the row
        # relation is what refuses rather than the adapter's own word.
        "unsound evidence": lambda: ScriptedAdapter(verify_state="verified"),
        "verified": lambda: VerifiedAdapter(store),
    }[road]()
    runtime, authorization = authorized(store, adapter)
    return runtime.execute(authorization)


@pytest.mark.parametrize("road", sorted(ROADS))
def test_each_road_out_of_the_verify_circuit_carries_its_own_sentence(
        tmp_path, road):
    """A receipt may not say something its outcome denies.

    The five refusals and the one success are named constants in one module now,
    which is what makes them one voice -- and also what makes swapping two of
    them a single-token edit. A mutation did exactly that: the raised-verifier
    road was made to carry "post-effect evidence was verified by the bound
    adapter", so a `verification_failed` receipt claimed in its own detail that
    the work had been verified, and every test in this suite stayed green. The
    outcome was pinned everywhere and the sentence beside it nowhere.

    So each road is driven and asked for its own sentence. The pairing below is
    the point: five distinct refusals and one success, none of them
    interchangeable, and the success sentence reachable only from the one road
    that actually succeeds.
    """
    attempt = _drive(a_store(tmp_path), road)

    assert attempt.receipt.detail == ROADS[road], attempt.receipt.detail
    succeeded = road == "verified"
    assert (attempt.state is AttemptState.SUCCEEDED) is succeeded, attempt.state
    assert (attempt.receipt.detail == verify_holds.VERIFIED) is succeeded


def test_every_refusal_a_publication_may_carry_is_legal_and_has_its_own_sentence():
    """Two modules hold one vocabulary, and neither can be changed alone.

    A publication refuses with a key from a CLOSED set the adapter door owns,
    and this road turns that key into the sentence a run's record keeps. A key
    in only one of the two is not a small inconsistency: added to the door
    alone, the lookup raises and the blanket guard below reports it as a broken
    VERIFIER -- so a run whose doer failed a promise says its checker failed
    instead. Added here alone, the door refuses to build the refusal at all and
    the sentence is prose nobody can reach.

    A review found exactly the first of those in a shipped fold: the new
    retention refusal was legal here and illegal at the door. Held over the
    constants, because it is a fact about the vocabulary and not about a run --
    and because either half alone stays green in every end-to-end suite.
    """
    from conductor.command.adapters.base import PUBLISH_REFUSALS
    from conductor.command.verify_road import PUBLISH_REASONS

    assert set(PUBLISH_REASONS) == set(PUBLISH_REFUSALS)
    assert len(set(PUBLISH_REASONS.values())) == len(PUBLISH_REASONS)


def test_no_two_roads_out_of_the_verify_circuit_say_the_same_thing():
    """Six roads, six sentences. Two that matched would be one road to a reader.

    Held over the constants rather than over a run, because it is a fact about
    the vocabulary and not about any one attempt -- and because a duplicate here
    would make the parametrized relation above pass for the wrong reason.
    """
    assert len(set(ROADS.values())) == len(ROADS)


# -- Verified evidence must follow the durable effect observation --

def test_preplanted_verified_evidence_cannot_become_post_action_success(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(verify_state="verified")
    runtime, authorization = authorized(store, adapter)
    seed_verified_evidence(store)
    assert kinds(store) == ["action_proposal", "action_request", "evidence"]

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.history == (
        AttemptState.ACCEPTED, AttemptState.STARTED, AttemptState.VERIFICATION_FAILED)
    assert attempt.receipt.outcome == "verification_failed"
    assert attempt.verification_evidence == ()
    assert attempt.receipt.evidence_refs == ()
    assert kinds(store) == [
        "action_proposal", "action_request", "evidence",
        "attempt_event", "attempt_event", "action_result"]
    assert adapter.execute_calls == 1 and adapter.verify_calls == 1


# -- a reported success is not the terminal word until verify confirms it --

@pytest.mark.parametrize("verify_state", ["mismatch", "error"])
def test_a_verify_that_refutes_success_reaches_verification_failed(tmp_path, verify_state):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(verify_state=verify_state)
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.state is not AttemptState.SUCCEEDED
    assert attempt.receipt.outcome == "verification_failed"
    assert attempt.verification_evidence == ()


def test_a_verify_that_raises_cannot_confirm_success(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(verify_raises=True)
    attempt = (lambda r, a: r.execute(a))(*authorized(store, adapter))
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.outcome == "verification_failed"


def test_an_unavailable_verifier_leaves_execution_observed_and_never_succeeded(tmp_path):
    """The systemic rule, held on the RUNTIME rather than inside any one adapter.

    An adapter that exposed no verifier used to hand its process exit straight to
    ``succeeded``. That is not a defect of one adapter: any next harness could
    answer ``unavailable`` and receive product success with no proof behind it,
    so the token is refused globally. What survives is the honest half -- the
    execution really was observed, and the durable event still says so -- while
    the terminal outcome says only that nothing was verified.
    """
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(verify_state="unavailable")
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.state is not AttemptState.SUCCEEDED
    assert attempt.receipt.outcome == "verification_failed"
    assert attempt.verification_evidence == ()
    assert attempt.receipt.evidence_refs == ()
    assert "no verifier" in attempt.receipt.detail
    assert "evidence" not in kinds(store)
    # Execution observed, unverified: the observation is not rewritten by the
    # verdict, so a reader can still tell a run process from a proven one.
    observed = [
        row.value for row in store.read("run-001").records
        if row.kind == "attempt_event" and row.value.phase == "execution_observed"]
    assert [row.outcome for row in observed] == ["succeeded"]


def test_only_the_whole_triple_ever_reaches_succeeded(tmp_path):
    """Three legs hold ``succeeded`` up, and taking away any one drops it.

    Observation alone is a process fact. Verification alone is an adapter's own
    word. A durable evidence record that predates the observation cannot have
    been caused by it. Only all three together are a success.
    """
    def no_verifier(store):
        return ScriptedAdapter(verify_state="unavailable"), False

    def verified_with_no_durable_record(store):
        return ScriptedAdapter(verify_state="verified"), False

    def verified_against_a_record_that_predates_the_effect(store):
        return ScriptedAdapter(verify_state="verified"), True

    def the_whole_triple(store):
        return VerifiedAdapter(store), False

    legs = (no_verifier, verified_with_no_durable_record,
            verified_against_a_record_that_predates_the_effect, the_whole_triple)
    reached = {}
    for index, build in enumerate(legs):
        store = a_store(tmp_path / f"leg-{index}")
        adapter, preplant = build(store)
        runtime, authorization = authorized(store, adapter)
        if preplant:
            seed_verified_evidence(store)
        reached[build.__name__] = runtime.execute(authorization).state
    assert reached == {
        "no_verifier": AttemptState.VERIFICATION_FAILED,
        "verified_with_no_durable_record": AttemptState.VERIFICATION_FAILED,
        "verified_against_a_record_that_predates_the_effect":
            AttemptState.VERIFICATION_FAILED,
        "the_whole_triple": AttemptState.SUCCEEDED,
    }


def test_verify_rejects_a_foreign_adapter_identity(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(
        verify_state="verified",
        verification_changes={"adapter_id": "foreign-adapter"})
    runtime, authorization = authorized(store, adapter)
    seed_verified_evidence(store)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.evidence_refs == ()
    assert attempt.verification_evidence == ()


def test_evidence_appended_after_observation_can_gain_causal_authority(tmp_path):
    class SideEffectVerifier(ScriptedAdapter):
        def verify(self, request, result):
            # Test-only stand-in for the independent evidence writer. The adapter
            # API returns refs only; it receives neither this store nor append power.
            store.append(EvidenceRef(
                evidence_id="during-verify", run_id=request.run_id,
                kind="verification", uri=f"verification/{request.action_id}",
                label="adapter side effect", created_by=self.manifest.adapter_id,
                observed_at=NOW, verification="verified",
                verified_by=self.manifest.adapter_id, verified_at=NOW))
            return AdapterVerification(
                adapter_id=self.manifest.adapter_id, action_id=request.action_id,
                state="verified", observed_at=NOW, detail="self assertion",
                evidence_refs=("during-verify",))

    store = a_store(tmp_path)
    adapter = SideEffectVerifier(verify_state="verified")
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.receipt.evidence_refs == ("during-verify",)
    assert tuple(row.evidence_id for row in attempt.verification_evidence) == (
        "during-verify",)



@pytest.mark.parametrize("state", ["verified", "unavailable", "mismatch", "error"])
def test_verifier_free_text_never_reaches_attempt_evidence_or_journal(tmp_path, state):
    secret = f"VERIFY-SECRET-{state}"
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(
        verify_state=state, verification_changes={"detail": secret})
    runtime, authorization = authorized(store, adapter)
    if state == "verified":
        seed_verified_evidence(store)
    attempt = runtime.execute(authorization)
    assert secret not in repr(attempt)
    assert secret.encode() not in store.run_path("run-001").joinpath(
        "records.jsonl").read_bytes()
