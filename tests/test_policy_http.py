"""The existing CSRF/session door carries bounded controls without effects."""
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from tests.test_command_http_api import PORT, TOKEN, get_headers, post
from tests.test_policy_runtime import ASK, setup


def test_preview_authorize_pause_resume_revoke_through_http(tmp_path):
    f = setup(tmp_path)
    events = []
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
        budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids, publish_run=events.append)
    # Owner and activation are test doubles; HTTP parsing/transport/store are real.
    api._policy = f.policy
    f.policy.notify = events.append
    path = "/command/runs/run/automation"
    before = f.store.read("run").records
    state = api.handle("GET", path, get_headers())
    assert state.status == 200 and state.payload["state"] == "unconfigured"
    assert post(api, path + "/preview", ASK, token="foreign").status == 403
    preview = post(api, path + "/preview", ASK)
    assert preview.status == 200 and f.store.read("run").records == before
    assert f.adapter.prepare_calls == 0 and events == []
    body = {"authorization_id": "grant", "preview_digest": preview.payload["preview_digest"],
            "authorized_by": "owner", "terms": preview.payload["terms"], "supersedes": None}
    granted = post(api, path + "/authorize", body)
    assert granted.status == 201 and events == ["run"] and f.policy.driver.calls == 1
    assert post(api, path + "/authorize", body).status == 200
    assert events == ["run"] and f.policy.driver.calls == 1
    control = {"control_id": "pause", "authorization_id": "grant",
        "authorization_digest": granted.payload["authorization_digest"],
        "action": "pause", "actor": "owner", "expected_control_id": None}
    assert post(api, path + "/control", control).status == 201
    assert post(api, path + "/control", control).status == 200
    assert api.handle("GET", path, get_headers()).payload["state"] == "paused"
    resume = {**control, "control_id": "resume", "action": "resume", "expected_control_id": "pause"}
    assert post(api, path + "/control", resume).status == 201
    assert f.policy.driver.calls == 2
    revoke = {**control, "control_id": "revoke", "action": "revoke", "expected_control_id": "resume"}
    assert post(api, path + "/control", revoke).status == 201
    assert api.handle("GET", path, get_headers()).payload["state"] == "revoked"
    before = f.store.read("run").records
    assert post(api, path + "/control", {**resume, "control_id": "bad-resume",
        "expected_control_id": "revoke"}).status == 422
    assert f.store.read("run").records == before and f.adapter.execute_calls == 0


def test_read_and_preview_do_not_acquire_owner_or_activate_driver(tmp_path):
    f = setup(tmp_path)
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
        budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids, publish_run=lambda run: None)
    api._policy = f.policy
    def missing_owner():
        raise RuntimeError("no live owner")
    f.policy.owner_check = missing_owner
    before = f.store.read("run").records
    result = api.handle("GET", "/command/runs/run/automation", get_headers())
    assert result.status == 200 and not result.payload["owner_present"]
    assert post(api, "/command/runs/run/automation/preview", ASK).status == 200
    assert f.policy.driver.calls == 0 and f.store.read("run").records == before
