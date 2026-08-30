"""Whether a verification and its evidence PROVE anything, asked before success.

Split out of ``runtime`` when that module reached its line cap, along the seam
``authorize_holds`` was cut on rather than one invented for the split:
everything here is a pure verdict over an adapter's answer and a replayed run.
No store is written, no clock is read, no adapter is called, no receipt is
appended and no lock is taken -- each function either names a refusal or answers
with what stands.

That is also WHERE they belong in the road. ``ControlRuntime._verify`` calls the
first before it believes an adapter's word and the second before it writes a
``succeeded`` receipt, so a run that would rest on a verification that proves
nothing never reaches a terminal success. The run store asks the evidence
relation again as a causal rule, which is what makes it true of bytes this
process did not write; asking it here is what makes it true early.

WHAT STAYED in ``runtime`` and why, because the line is the whole point of the
split: ``_verify`` is an arm of the execute state machine -- it calls the
registry's verify seam, it appends the one durable receipt through ``_finish``,
and the release matrix names it as the VERIFY-FAIL door. A module holding it
would have to be handed the runtime, which is a method spelled differently
rather than a seam. So the TOUCHING stayed there and the JUDGING came here, and
nothing in this file imports ``runtime`` or reaches back into it.

The sentences are here for a second reason. Five refusals and one success used
to be written inline at the five places that produced them, which is five
chances for one voice to become two -- and two of them are read by tests as the
signature of a particular relation. One home, one spelling.
"""
from __future__ import annotations

from .adapters import AdapterVerification
from .attempts import AttemptEvent
from .contracts import ActionRequest, EvidenceRef
from .graph_causality import demanded_evidence
from .run_store import RecoveredRun

#: The verifier seam itself raised. A broken verifier cannot confirm success.
VERIFY_RAISED = "adapter verify failed"
#: The answer was not an ``AdapterVerification``, or was about another action or
#: from another adapter. Either way it is not this action's proof.
NOT_THIS_ACTION = "the adapter returned no verification for this action"
#: No verifier is no proof, and no proof is not a success. This is the one place
#: the whole product could be talked into believing an exit code, so the refusal
#: lives HERE rather than inside whichever adapter happens to be honest today:
#: any next harness may answer `unavailable`, and none of them may be believed
#: for it.
NO_VERIFIER = ("execution observed; the adapter exposed no verifier, so "
               "nothing about the work is verified")
#: What a refusal says when the evidence ROW itself is the problem: it does not
#: stand, it does not follow the observation, or it is not the plan's verifier's.
EVIDENCE_UNSOUND = "verified evidence did not satisfy the causal store relation"
#: What a refusal says when the row stands and the PLAN asked for more of it.
EVIDENCE_UNNAMED = ("this run's plan requires this step's verification "
                    "to name what it checked, and it names no digest")
#: The one sentence on the other side of all of them.
VERIFIED = "post-effect evidence was verified by the bound adapter"


def refused_verification(
        verification: object, request: ActionRequest,
        verifier: str) -> str | None:
    """Why this adapter's answer is not proof, or None when it claims success.

    Three refusals and they are three different failures: an answer that is not
    a verification of THIS action by THIS adapter, an adapter that exposes no
    verifier at all, and a verifier that looked and did not agree. The middle one
    is the load-bearing one and it is refused by name -- see ``NO_VERIFIER``.

    Answering `None` is not "this succeeded". It is "the adapter says it
    verified", which is a claim; whether anything durable backs that claim is
    ``standing_evidence``'s question and it is asked next.

    Args:
        verification: Whatever the registry's verify seam returned.
        request: The action being judged.
        verifier: The adapter identity this run's plan makes authoritative.

    Returns:
        The refusal sentence, or None when the answer is a claim of success.
    """
    if (not isinstance(verification, AdapterVerification)
            or verification.action_id != request.action_id
            or verification.adapter_id != verifier):
        return NOT_THIS_ACTION
    if verification.state == "unavailable":
        return NO_VERIFIER
    if verification.state != "verified":
        return f"adapter verification was {verification.state}"
    return None


def _bound_rows(
        recovered: RecoveredRun, request: ActionRequest, verifier: str,
        observed: AttemptEvent,
        refs: tuple[str, ...]) -> tuple[EvidenceRef, ...] | None:
    """The rows this result may rest on, or None when one of them does not stand.

    Every field of a verification is pinned here and pinned to the run's own
    frozen facts: it belongs to this run, it is a verification, it is at this
    action's one uri, and it is signed -- created AND verified -- by the single
    adapter identity the plan makes authoritative. The eligibility window is the
    other half: only rows appended AFTER the durable execution observation are
    even looked at, so nothing recorded before the work happened can be offered
    as proof that it did.

    Args:
        recovered: The run replayed from disk, oldest record first.
        request: The action whose success is being decided.
        verifier: The adapter identity this run's plan makes authoritative.
        observed: The durable execution observation the evidence must follow.
        refs: The evidence ids the adapter's verification named.

    Returns:
        The rows as the journal holds them, or None.
    """
    rows = list(recovered.records)
    index = next((
        position for position, row in enumerate(rows)
        if row.kind == "attempt_event" and row.value == observed), None)
    if index is None:
        return None
    eligible = {
        row.value.evidence_id: row.value for row in rows[index + 1:]
        if row.kind == "evidence"
    }
    evidence = tuple(eligible.get(ref) for ref in refs)
    if any(row is None for row in evidence):
        return None
    expected_uri = f"verification/{request.action_id}"
    if any(
            row.run_id != request.run_id or row.kind != "verification"
            or row.uri != expected_uri or row.created_by != verifier
            or row.verification != "verified" or row.verified_by != verifier
            for row in evidence):
        return None
    return evidence


def standing_evidence(
        recovered: RecoveredRun, request: ActionRequest, verifier: str,
        observed: AttemptEvent,
        refs: tuple[str, ...]) -> tuple[tuple[EvidenceRef, ...] | None, str]:
    """Resolve only bound verification evidence recorded after observation.

    Answers the evidence and no complaint, or `None` and the sentence saying
    WHICH relation refused. The two are one question asked twice and they are
    kept apart deliberately: a row that does not stand is the runtime's own
    rule, a row standing while naming nothing checked is the PLAN's demand, and
    one sentence for both would hide the field from whoever meets
    `verification_failed`.

    That demand is read through `graph_causality.demanded_evidence`, the same
    function the store spends on both its roads, so the honest road and a forged
    journal cannot disagree about what a plan said. Refusing here too is
    `_hold_plan_bounds`' two-place shape: before a `succeeded` receipt exists,
    and again over bytes we did not write.

    The run is handed in already replayed. Reading it here would make this a
    door onto the store rather than a verdict over one, and the caller has to
    hold its own route gate before it reads anything anyway.

    Returns:
        The evidence and an empty sentence, or None and the refusal.
    """
    evidence = _bound_rows(recovered, request, verifier, observed, refs)
    if evidence is None:
        return None, EVIDENCE_UNSOUND
    if (demanded_evidence(recovered, request.action_id) == "digest"
            and any(row.digest is None for row in evidence)):
        return None, EVIDENCE_UNNAMED
    return tuple(EvidenceRef.from_dict(row.as_dict())
                 for row in evidence), ""
