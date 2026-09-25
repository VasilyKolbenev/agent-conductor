"""Automation wire orchestration under the existing session/CSRF boundary."""
from .api_refusals import ApiRefusal
from .policy_view import automation_view


def route(api, name, run_id, body=None):
    api._hold_route(run_id)
    policy = api._policy
    if name == "automation":
        return 200, automation_view(policy, run_id)
    if name == "automation_preview":
        return 200, policy.preview(run_id, body)
    if name == "automation_authorize":
        value, created = policy.authorize(run_id, body)
    elif name == "automation_control":
        value, created = policy.control(run_id, body)
    else:
        raise ApiRefusal.fixed("route_not_found")
    return (201 if created else 200), value.as_dict()
