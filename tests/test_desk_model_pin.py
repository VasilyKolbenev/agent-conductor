"""The Desk pin is a registered profile capability; deployment changes cannot rewrite history."""
from conductor.command.adapters.codex_cli import CODEX_PROFILE
from conductor.command.adapters.grok_build import GROK_PROFILE
from conductor.command.run_store import RunStore
from tests.test_command_workflow_routes import api, contracts, get, post
from tests.test_command_run_routes import a_run
from tests.test_standard_cycle_checker import _StandardAdapter


def test_roster_and_run_admission_follow_profile_and_skip_rejudging_a_standing_run(tmp_path):
    class Configurable(_StandardAdapter):
        profile = CODEX_PROFILE

    class DefaultOnly(_StandardAdapter):
        profile = GROK_PROFILE

    known = ("codex", "grok-build")
    store = RunStore(tmp_path)
    subject, *_ = api(tmp_path, providers=contracts(reachable=known, known=known), adapters=[
        Configurable(store, adapter_id="codex"), DefaultOnly(store, adapter_id="grok-build")])
    roster = get(subject, "/command/workflows").payload["providers"]
    assert {row["provider_id"]: row["model_pin_supported"] for row in roster} == {
        "codex": True, "grok-build": False}

    def request(run, provider, model):
        writer = {"instance_id": "writer", "provider_id": provider, "model": model}
        return a_run(run_id=run, workflow_id=None, revision=None, assignments={},
                     participants=[writer])

    pin = request("selected", "codex", "gpt-6.1-sol")
    original = post(subject, "/command/runs", pin)
    assert original.status == 201, original.payload
    denied = post(subject, "/command/runs", request("unsupported", "grok-build", "chosen-model"))
    assert denied.status == 422 and denied.payload["error"]["code"] == "contract_invalid"
    assert not store.run_path("unsupported").exists()
    assert post(subject, "/command/runs", request("use-default", "grok-build", None)).status == 201
    Configurable.profile = GROK_PROFILE  # Same durable run, changed installation capability.
    repeated = post(subject, "/command/runs", pin)
    assert repeated.status == 200, repeated.payload
    assert store.read("selected").config["instances"][0]["model"] == "gpt-6.1-sol"
