"""Dispatch existing read routes; HTTP serialization and mutations stay in CommandApi.

Extracted along the GET boundary when the facade reached its module limit.
The supplied facade owns the stores and controls exactly as before; this module
creates no runtime, worker, provider, collector or execution authority.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import studio_routes, task_routes
from .command_routes import Route

if TYPE_CHECKING:
    from .http_api import CommandApi


def read_route(api: CommandApi, route: Route, host: str) -> tuple[int, dict[str, Any]]:
    if route.name == "automation":
        from .policy_routes import route as policy_route
        return policy_route(api, route.name, route.run_id)
    if route.name == "session":
        return 200, api._session.session_response(host)
    if route.name == "quotas":
        return 200, api._quota_view.payload(api._providers, api._clock())
    if route.name == "workflows":
        return studio_routes.list_workflows(api._templates, api._providers, api._project())
    if route.name == "runs":
        return studio_routes.list_runs(api._store, api._providers, computed_at=api._clock())
    if route.name == "tasks":
        return task_routes.list_tasks(api._tasks)
    if route.name == "task":
        assert route.task_id is not None
        return task_routes.read_task(api._tasks, api._store, route.task_id)
    if route.name in {"workflow", "workflow_revision"}:
        assert route.workflow_id is not None
        if route.name == "workflow":
            return studio_routes.read_workflow(api._templates, route.workflow_id)
        assert route.revision is not None
        return studio_routes.read_revision(api._templates, route.workflow_id, route.revision)
    assert route.run_id is not None
    api._hold_route(route.run_id)
    recovered = api._store.read(route.run_id)
    if route.name == "run":
        return 200, studio_routes.recovered_payload(recovered, api._tasks, computed_at=api._clock())
    return 200, api._controls(recovered.config)
