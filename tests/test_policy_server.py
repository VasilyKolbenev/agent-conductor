"""Real project owner, loopback HTTP and driver; deterministic adapters only."""
from threading import Thread
import pytest

from conductor import server, ownership, ownership_transition
from tests.test_store import write_project, good_lane
from tests.test_server_command_http import _request
from tests.test_command_http_api import TOKEN
from tests.test_policy_runtime import setup, NOW, PD
from tests.test_policy_driver import ask, wait_terminal, assert_two_steps


def test_owned_server_one_http_grant_drives_two_steps_and_closes_cleanly(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    f = setup(root, two_steps=True, checker=True)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, registry=f.registry, clock=lambda: NOW,
        ids=f.runtime._ids, token_factory=lambda _: TOKEN)
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    f.policy, f.runtime = subject.command_api._policy, subject.command_api.runtime
    f.store = subject.command_store
    f.adapter._store = f.verifier._store = f.store
    # Registry injection intentionally has no installed provider configurations.
    f.policy.provider_digest, f.policy.provider_facts = lambda config: PD, None
    try:
        assert ownership.require_owner(root) is subject.project_owner
        with pytest.raises(ownership.OwnerRefused, match="owner_busy"):
            server.build(root, 0, registry=f.registry)
        status, preview, _ = _request(subject, "POST", "/command/runs/run/automation/preview", ask())
        assert status == 200, preview
        status, grant, _ = _request(subject, "POST", "/command/runs/run/automation/authorize", {
            "authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None})
        assert status == 201, grant
        assert_two_steps(f, wait_terminal(f))
        status, state, _ = _request(subject, "GET", "/command/runs/run/automation")
        assert status == 200 and state["state"] == "complete"
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(5)
    assert not thread.is_alive() and subject.project_owner is None
    with pytest.raises(ownership.OwnerRefused, match="owner_required"):
        ownership.require_owner(root)
    restarted = server.build(root, 0, registry=f.registry, clock=lambda: NOW)
    try:
        assert not restarted.policy_driver.is_active("run", "grant")
        assert f.adapter.execute_calls == 2
    finally:
        restarted.server_close()
