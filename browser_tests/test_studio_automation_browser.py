"""A human reviews and controls actual bounded authority in the served Studio.

The provider is a deterministic injected adapter. The real project owner,
HTTP/session boundary, immutable history and driver are used. An unanswered
human gate deliberately prevents all execution in these UI witnesses.
"""
from threading import Thread

import pytest
from playwright.sync_api import Browser, expect

from conductor import ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.kimi_code import KIMI_PROFILE
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from tests.test_policy_runtime import ARGS, DeepScripted, NOW, PD
from tests.test_store import good_lane, write_project
from browser_tests.test_studio_lifecycle import _Project, _open, TOKEN


class _ArgvScripted(DeepScripted):
    """The scripted adapter under a real command-line profile, so its facts carry that channel's bound."""

    profile = KIMI_PROFILE


def _real_facts(policy, registry):
    """Facts from the real authority, as the served product builds them."""
    from conductor.command.adapters.provider import ProviderConfig
    from conductor.command.policy_providers import ProviderAuthority
    from tests.test_command_provider_contract import _contract
    config = ProviderConfig("claude-code", "/opt/claude/bin/claude", "fake-claude-jsonl-v1",
                            env_allow=("ANTHROPIC_API_KEY",))
    authority = ProviderAuthority([config], [_contract(auth="api_key")], registry)
    policy.provider_digest, policy.provider_facts = authority.digest, authority.facts


@pytest.fixture
def bounded_project(tmp_path, request):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    config = {"cycle": {"id": "cycle"}, "instances": [{"id": "doer", "adapter": "claude-code"}],
              "workflow": {"id": "custom", "revision": 1}, "automation_contract": "bounded-run-v1"}
    store = RunStore(root)
    store.create_run(RunEnvelope("run", "cycle", NOW, snapshot_digest(config), mode="policy"), config)
    store.append(GraphDefinition("plan", "run", NOW, execution_contract="bounded-run-v1", nodes=(
        GraphNode("ask", "gate", "Human choice", gate_id="answer"),
        GraphNode("work", "task", "Approved work", instance_id="doer", capability="dispatch",
                  arguments=ARGS, timeout_seconds=30, attempt_bound=2)),
        edges=(GraphEdge("ask", "work", condition="on_approved"),)))
    store.append(ArtifactDocument(artifact_id="instruction", run_id="run", artifact_ref="instructions",
        created_at=NOW, media_type="text/plain", content="Keep this task."))
    ownership_transition.activate(root, legacy_writers_stopped=True)
    argv_facts = getattr(request, "param", False)
    adapter = (_ArgvScripted if argv_facts else DeepScripted)(execute_outcome="failed")
    registry = AdapterRegistry([adapter])
    subject = server.build(root, 0, registry=registry,
                           clock=lambda: NOW, token_factory=lambda _: TOKEN)
    if argv_facts:
        _real_facts(subject.command_api._policy, registry)
    else:
        subject.command_api._policy.provider_digest = lambda config: PD
        subject.command_api._policy.provider_facts = None  # No installed-provider claim.
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    host, port = subject.server_address[:2]
    try:
        yield _Project(f"http://{host}:{port}/", root), adapter
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(5)
        assert not thread.is_alive()


def prepare(page, project):
    page.get_by_role("button", name="Read this run", exact=True).click()
    box = page.locator('[data-automation="run"]')
    expect(box.locator('[data-automation-state]')).to_have_attribute("data-automation-state", "unconfigured")
    for name, value in {"actor": "owner", "max_actions": "2", "max_action_seconds": "30",
                        "max_total_task_seconds": "60", "duration_seconds": "300"}.items():
        box.locator(f'[data-focus="automation:run:{name}"]').fill(value)
    with page.expect_response(lambda row: row.request.method == "POST"
                              and row.url.endswith("/automation/preview")) as response:
        box.locator('[data-focus="automation:preview"]').click()
    assert response.value.status == 200, response.value.json()
    expect(box.locator("[data-automation-preview]")).to_be_visible()
    box.get_by_text("Instruction for work: instruction", exact=True).click()
    expect(box.locator("pre").filter(has_text="Keep this task.")).to_be_visible()
    return box


def test_one_reviewed_permission_and_explicit_pause_resume_revoke(chromium: Browser, bounded_project):
    project, adapter = bounded_project
    page, window = _open(chromium, project)
    try:
        box = prepare(page, project)
        store = RunStore(project.root)
        assert not any(row.kind == "run_authorization" for row in store.read("run").records)
        for action, state in [("authorize", "waiting"), ("pause", "paused"),
                              ("resume", "waiting"), ("revoke", "revoked")]:
            suffix = "/authorize" if action == "authorize" else "/control"
            with page.expect_response(lambda row: row.request.method == "POST"
                                      and row.url.endswith("/automation" + suffix)) as response:
                box.locator(f'[data-focus="automation:{action}"]').click()
            assert response.value.status == 201, response.value.json()
            expect(box.locator("[data-automation-state]")).to_have_attribute("data-automation-state", state)
        values = store.read("run").records
        assert sum(row.kind == "run_authorization" for row in values) == 1
        assert [row.value.action for row in values if row.kind == "run_authorization_control"] == ["pause", "resume", "revoke"]
        assert not any(row.kind in {"action_request", "action_proposal"} for row in values)
        assert adapter.execute_calls == 0 and window.page_errors == []
    finally:
        page.context.close()


def test_lost_authorize_reply_reads_the_same_durable_permission_and_language_keeps_actor(chromium: Browser, bounded_project):
    project, adapter = bounded_project
    page, window = _open(chromium, project)
    try:
        box = prepare(page, project)
        posted = []
        def lose_reply(route):
            posted.append(route.request.post_data_json)
            accepted = route.fetch()
            assert accepted.status == 201, accepted.text()
            route.abort("failed")
        page.route("**/command/runs/run/automation/authorize", lose_reply)
        box.locator('[data-focus="automation:authorize"]').click()
        expect(box.locator('[data-automation-notice="recorded"]')).to_be_visible()
        assert len(posted) == 1
        grants = [row.value for row in RunStore(project.root).read("run").records if row.kind == "run_authorization"]
        assert len(grants) == 1 and grants[0].authorization_id == posted[0]["authorization_id"]
        page.locator('[data-focus="preference-language"]').select_option("ru")
        expect(box.locator('[data-focus="automation:pause"]')).to_have_text("Пауза после текущего действия")
        expect(box.locator('[data-focus="automation:run:actor"]')).to_have_value("owner")
        assert adapter.execute_calls == 0 and window.page_errors == []
    finally:
        page.context.close()


@pytest.mark.parametrize("bounded_project", [True], indirect=True)
def test_the_review_names_the_doers_task_channel_and_the_bound_the_grant_freezes(
        chromium: Browser, bounded_project):
    """Codex R2: a person authorizing a command-line doer reads its real bound, not the 256 KiB of stdin."""
    project, adapter = bounded_project
    page, window = _open(chromium, project)
    try:
        box = prepare(page, project)
        expect(box.get_by_text(
            "Task channel: command line. The whole command — instruction, input documents and any "
            "correction included — must fit in 32767 UTF-16 code units, its terminating NUL "
            "included; a larger task is refused before it starts.", exact=True)).to_be_visible()
        page.locator('[data-focus="preference-language"]').select_option("ru")
        expect(box.get_by_text("Канал задачи: командная строка.", exact=False)).to_contain_text(
            "32767 единиц UTF-16")
        assert adapter.execute_calls == 0 and window.page_errors == []
    finally:
        page.context.close()
