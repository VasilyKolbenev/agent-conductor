"""One fresh attempt's optional in-process turn over its cooperating resource.

This is neither a project owner nor a cycle grant. The fresh grant is consumed
before any scope callback; waiting cannot mint, renew or recover authority.
Generic adapters without a declared shared resource keep their existing overlap.
"""
from contextlib import contextmanager
from threading import local

from .adapters.base import VerifierBinding
from .authorize_holds import _hold_run_not_terminal, _hold_work_scope
from .contracts import frozen_config_bindings
from .runtime_values import Authorization, AttemptState, ExecutionError


_ACTIVE = local()


def attempt_scope_active() -> bool:
    """Public runtime entry must not invert L2 -> another operation's L1."""
    return bool(getattr(_ACTIVE, "held", False))


def _selection(runtime, request, recovered):
    bindings = frozen_config_bindings(recovered.config)
    doer = bindings[request.instance_id]
    verifier = runtime._verifier_for(recovered, request)
    checker = verifier.adapter_id if isinstance(verifier, VerifierBinding) else verifier
    selected = None
    for adapter_id in (doer, checker):
        candidate = runtime._registry.attempt_scope(adapter_id)
        if candidate is None:
            continue
        if selected is not None and candidate.resource is not selected.resource:
            raise ExecutionError("attempt participants declare different shared resources")
        selected = selected or candidate
    return selected


@contextmanager
def _held(scope):
    if scope is None:
        yield
        return
    if attempt_scope_active():
        raise ExecutionError("runtime operation cannot nest inside an attempt scope")
    _ACTIVE.held = True
    acquired = False
    try:
        if scope.acquire() is not True:
            raise ExecutionError("attempt scope did not confirm acquisition")
        acquired = True
        yield
    finally:
        try:
            if acquired:
                scope.release()
        finally:
            _ACTIVE.held = False


def _frozen_context(recovered):
    """Append-only progress may grow; execution binding and frozen plan may not."""
    return (recovered.envelope.as_dict(), recovered.config,
            tuple(row.value.as_dict() for row in recovered.records
                  if row.kind == "graph_definition"))


def _after_wait(runtime, request, previous, scope):
    canonical, latest = runtime._recover_authorized(Authorization(request=request))
    if _frozen_context(latest) != _frozen_context(previous):
        raise ExecutionError("frozen execution context changed while awaiting attempt scope")
    selected = _selection(runtime, canonical, latest)
    if selected is None or selected.resource is not scope.resource:
        raise ExecutionError("registered attempt resource changed while waiting")
    replayed = runtime._replayed_attempt(canonical, latest)
    if replayed is not None:
        return latest, replayed
    lease, observed = runtime._durable_events(canonical, latest)
    if observed is not None:
        return latest, runtime._resume_observed(canonical, latest, observed)
    if lease is not None:
        return latest, runtime._finish(
            canonical, AttemptState.UNKNOWN,
            (AttemptState.ACCEPTED, AttemptState.STARTED),
            detail="effect lease has no durable observation; execution was not repeated")
    _hold_run_not_terminal(latest)
    proposal = next((row.value for row in latest.records
                     if row.kind == "action_proposal"
                     and f"dispatch-{row.value.proposal_id}" == canonical.idempotency_key), None)
    if proposal is None:
        raise ExecutionError("standing action lost its proposal while awaiting attempt scope")
    _hold_work_scope(proposal, latest)
    # Do not authorize again: this request already spends an action and makes
    # its node in-flight. Confirm grants currently have no wall-clock expiry,
    # pause or revocation field. Future cycle grants need their own post-wait hold.
    return latest, None


def drive_fresh_attempt(runtime, canonical, recovered, grant):
    """Called under this action's L1; hold L2 through checker cleanup and receipt."""
    # Every retry remains fail-closed even if a callback failed after taking a
    # resource or an effect happened without a terminal receipt.
    runtime._grants.remove(grant)
    scope = _selection(runtime, canonical, recovered)
    with _held(scope):
        if scope is not None:
            recovered, replayed = _after_wait(runtime, canonical, recovered, scope)
            if replayed is not None:
                return replayed
        return runtime._execute_fresh(canonical, recovered)
