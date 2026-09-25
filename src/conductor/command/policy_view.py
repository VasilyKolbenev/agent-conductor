"""Read-only automation state. No read creates ownership or live activation."""
from .authorization_terms import _time_parts
from .contracts import ActionRequest, ActionResultReceipt
from .graph_schedule import schedule
from .policy_history import current_authorization, current_control, spent_budget


def automation_view(policy, run_id):
    recovered = policy.store.read(run_id)
    values = tuple(row.value for row in recovered.records)
    grant = current_authorization(values)
    control = current_control(values, grant) if grant else None
    definition = next((row.value for row in recovered.records if row.kind == "graph_definition"), None)
    terminal = {v.action_id for v in values if type(v) is ActionResultReceipt}
    pending = [v.action_id for v in values if type(v) is ActionRequest and v.action_id not in terminal]
    owner = _owner_present(policy)
    computed = schedule(definition, values) if definition else None
    state, reason = _state(policy, run_id, grant, control, computed, pending, owner, policy.clock())
    actions, seconds = spent_budget(values, definition) if grant else (0, 0)
    next_node = next((n.node_id for n in definition.nodes if n.capability is not None
                     and n.node_id in computed.runnable), None) if computed else None
    return {"run_id": run_id, "authorization": grant.as_dict() if grant else None,
            "control": control.as_dict() if control else None, "state": state, "reason_code": reason,
            "active_action_id": pending[0] if len(pending) == 1 else None, "next_node_id": next_node,
            "spent_actions": actions, "remaining_actions": max(0, grant.max_actions - actions) if grant else 0,
            "spent_task_seconds": seconds,
            "remaining_task_seconds": max(0, grant.max_total_task_seconds - seconds) if grant else 0,
            "expires_at": grant.expires_at if grant else None, "owner_present": owner}


def _owner_present(policy):
    try:
        policy.owner_check()
    except Exception:
        return False
    return True


def _state(policy, run_id, grant, control, computed, pending, owner, now):
    if grant is None:
        return "unconfigured", "authorization_required"
    if computed is not None and computed.run_state == "complete":
        return "complete", "plan_ended"
    if control is not None and control.action in {"pause", "revoke"}:
        word = "paused" if control.action == "pause" else "revoked"
        return word, word
    if _time_parts("now", now) >= _time_parts("expires_at", grant.expires_at):
        return "expired", "expired"
    driver = policy.driver
    if not owner or driver is None or not driver.is_active(run_id, grant.authorization_id):
        return "restart_required", "owner_required" if not owner else "explicit_resume_required"
    if len(pending) > 1:
        return "stalled", "ambiguous_actions"
    if pending:
        return "running", "action_in_flight"
    reason = driver.reason(run_id)
    if reason in {"unknown_action", "feedback_required", "admission_refused", "stalled"}:
        return "stalled", reason
    if computed is not None and computed.run_state == "stalled":
        return "stalled", "plan_stalled"
    if reason == "waiting":
        return "waiting", "plan_waiting"
    return "ready", "ready"
