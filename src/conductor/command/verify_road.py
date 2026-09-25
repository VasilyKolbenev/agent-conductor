"""Spend live checker authority once, then judge only its durable evidence.

This is the independent arm; ordinary adapter verification stays in runtime.
No participant-controlled prose is copied into a receipt. Recovery reads facts,
never publishes material or starts a checker. Release belongs to the doer and
is attempted on every exit, including a broken checker or a refused publish.
"""
from types import MappingProxyType

from .adapters.base import AdapterVerification, IndependentVerifierUnavailable
from .contracts import frozen_config_bindings
from . import verify_holds as words


PUBLISH_REASONS = MappingProxyType({
    "outside_subtree": words.DOER_OUTSIDE_SUBTREE,
    "nothing_changed": words.DOER_NOTHING_CHANGED,
    "uncontained": words.DOER_UNCONTAINED,
    "over_read_budget": words.DOER_OVER_READ_BUDGET,
    "home_retained": words.DOER_HOME_RETAINED,
    "tree_changed": words.DOER_TREE_CHANGED,
    "env_echo": words.DOER_ENV_ECHO,
})
CHECK_REASONS = MappingProxyType({
    ("error", "frame_over_limit"): words.FRAME_OVER_LIMIT,
    ("error", "frame_env_echo"): words.FRAME_ENV_ECHO,
    ("error", "homes_refused"): words.CHECKER_HOMES_REFUSED,
    ("error", "login_residue"): words.CHECKER_LOGIN_RESIDUE,
    ("error", "preflight_refused"): words.CHECKER_PREFLIGHT_REFUSED,
    ("error", "marker_standing"): words.CHECKER_MARKER_STANDING,
    ("error", "no_verdict"): words.CHECKER_NO_VERDICT,
    ("error", "material_unavailable"): words.CHECKER_MATERIAL_UNAVAILABLE,
    ("mismatch", "tree_changed"): words.CHECKER_TREE_CHANGED,
    ("mismatch", "rejected"): words.CHECKER_REJECTED,
    ("mismatch", "rejected_findings_refused"): words.CHECKER_FINDINGS_REFUSED,
})


def _evidence(store, request, verifier, observed, refs):
    return words.standing_evidence(
        store.read(request.run_id), request, verifier.adapter_id, observed,
        refs, verifier_instance_id=verifier.instance_id)


def _resume(registry, store, request, verifier, observed):
    recovered = store.read(request.run_id)
    refs = tuple(row.value.evidence_id for row in recovered.records
                 if row.kind == "evidence"
                 and row.value.uri == f"verification/{request.action_id}")
    if refs:
        return _evidence(store, request, verifier, observed, refs)
    started = registry.verification_started(verifier.adapter_id, request)
    return None, (words.NOT_RESUMABLE_NEVER if started is False
                  else words.NOT_RESUMABLE_LOST)


def verify_independently(registry, store, request, report, verifier, observed, *, live, clock=None):
    """Return causal evidence or a fixed refusal, without producing a receipt."""
    doer = frozen_config_bindings(store.read(request.run_id).config)[request.instance_id]
    try:
        if not live:
            return _resume(registry, store, request, verifier, observed)
        published = registry.publish(doer, request, report)
        if published is None:
            return None, words.NOT_INDEPENDENT
        if published.refusal is not None:
            return None, PUBLISH_REASONS[published.refusal]
        verification = registry.verify(
            verifier.adapter_id, request, report, verifier=verifier, material=published)
        refused = words.refused_verification(verification, request, verifier.adapter_id)
        if refused is not None:
            if (isinstance(verification, AdapterVerification)
                    and verification.action_id == request.action_id
                    and verification.adapter_id == verifier.adapter_id):
                if verification.feedback is not None:
                    from .feedback_runtime import record_rejection
                    record_rejection(store, request, verifier, verification, published, clock=clock)
                refused = CHECK_REASONS.get(
                    (verification.state, verification.detail), refused)
            return None, refused
        return _evidence(store, request, verifier, observed, verification.evidence_refs)
    except IndependentVerifierUnavailable:
        return None, words.NOT_INDEPENDENT
    except Exception:  # an untrusted seam cannot manufacture success
        return None, words.VERIFY_RAISED
    finally:
        registry.release(doer, request)
