"""The wizard roster joins reviewed V1 membership to registered transport facts."""
from conductor.command import studio_routes
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.claude_code import CLAUDE_PROFILE
from conductor.command.adapters.provider import provider_projection
from conductor.command.policy_providers import task_channel_fact
from conductor.command.template_store import TemplateStore

from tests.test_command_adapters import FakeAdapter
from tests.test_command_workflow_routes import contracts


class ProfiledFake(FakeAdapter):
    profile = CLAUDE_PROFILE


def test_workflow_roster_uses_explicit_catalogue_and_registered_class(tmp_path):
    (tmp_path / "conductor").mkdir()
    descriptors = contracts(known=("claude-code", "codex", "other"))
    registry = AdapterRegistry([ProfiledFake("claude-code")])
    status, payload = studio_routes.list_workflows(
        TemplateStore(tmp_path), descriptors, registry=registry,
        offered_ids={"claude-code", "codex"})

    assert status == 200
    rows = {row["provider_id"]: row for row in payload["providers"]}
    assert rows["claude-code"]["offered"] is True
    assert rows["claude-code"]["task_channel"] == task_channel_fact(CLAUDE_PROFILE)
    assert rows["codex"]["offered"] is True
    assert rows["codex"]["task_channel"] is None
    assert rows["other"]["offered"] is False
    assert rows["other"]["task_channel"] is None
    assert all("offered" not in row and "task_channel" not in row
               for row in provider_projection(descriptors))
