"""Prepare, record one effect lease, then observe and independently verify."""
from .contracts import ControlMode, frozen_config_models
from .policy_runtime import hold_start
from .runtime_values import AttemptState, ExecutionError


def execute_fresh(runtime, request, recovered):
    _, bound = runtime._bound_adapter(recovered, request.instance_id)
    runtime._hold_route(request.run_id, ExecutionError)
    cancelled = _start_refusal(runtime, request)
    if cancelled is not None:
        return cancelled
    try:
        model = frozen_config_models(recovered.config).get(request.instance_id)
        prepared = runtime._registry.prepare(bound, request, model=model)
    except Exception:
        return runtime._finish(request, AttemptState.UNKNOWN, (AttemptState.ACCEPTED,),
                               detail="adapter prepare failed")
    # Pause/revoke and lease publication linearize under the SAME store gate.
    # No transaction spans execute, its child, or independent verification.
    with runtime._store.transaction():
        cancelled = _start_refusal(runtime, request, prepared=True)
        if cancelled is not None:
            return cancelled
        runtime._hold_route(request.run_id, ExecutionError)
        lease = runtime._append_event(request, bound, phase="effect_lease")
    report, note = runtime._observe_execute(bound, prepared, request)
    observed = runtime._append_event(request, bound, phase="execution_observed",
        recovery_ref=lease.recovery_ref, outcome=report.outcome if report is not None else "unknown",
        exit_code=report.exit_code if report is not None else None)
    history = (AttemptState.ACCEPTED, AttemptState.STARTED)
    if report is None:
        runtime._release_independent(recovered, request)
        return runtime._finish(request, AttemptState.UNKNOWN, history, detail=note)
    canonical = runtime._observed_report(request, observed)
    # Only a non-success carries the adapter's sentence; a success is verified from the event.
    reason = report.detail if report.outcome != "succeeded" else None
    return runtime._resolve(request, runtime._verifier_for(recovered, request),
                            canonical, observed, history, live=True, reason=reason)


def _start_refusal(runtime, request, prepared=False):
    if request.mode is not ControlMode.POLICY:
        return None
    try:
        hold_start(runtime, request)
    except Exception:
        # A lost owner may refuse this append too. That leaves an ambiguous
        # request for recovery, never a new effect or a success claim.
        if prepared:
            recovered = runtime._store.read(request.run_id)
            runtime._release_independent(recovered, request)
        return runtime._finish(request, AttemptState.CANCELLED, (AttemptState.ACCEPTED,),
            detail="bounded authorization no longer permits this unstarted action")
    return None
