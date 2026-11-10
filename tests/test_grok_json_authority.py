"""The Grok wire allowance belongs to the selected transport and the ordinary review only."""
from dataclasses import replace

import pytest

from conductor.command.adapters.codex_cli import CODEX_PROTOCOL
from conductor.command.adapters.grok_build import GROK_PROTOCOL, GrokBuildAdapter
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.policy_providers import ProviderAuthority
from conductor.command.providers import resolve_providers
from tests.test_command_codex_transport import _executable as codex_fixture
from tests.test_command_grok_transport import NOW, _Ids, _executable as grok_fixture
from tests.test_grok_compat_isolation import _harness


def capture_specs(monkeypatch, runner):
    calls = []
    run = runner.run

    def measured(spec):
        calls.append((spec.argv, spec.output_limit))
        return run(spec)

    monkeypatch.setattr(runner, "run", measured)
    return calls


def test_the_new_wire_ceiling_invalidates_only_grants_that_selected_grok(tmp_path, monkeypatch):
    pins = [
        ProviderConfig("grok-build", str(grok_fixture(tmp_path)), GROK_PROTOCOL),
        ProviderConfig("codex", str(codex_fixture(tmp_path)), CODEX_PROTOCOL),
    ]
    resolution = resolve_providers(
        pins, root=tmp_path, clock=lambda: NOW, ids=_Ids(), environ={}, confine_platform=None)
    authority = ProviderAuthority(pins, resolution.contracts, resolution.registry)
    grok = {"instances": [{"id": "reviewer", "adapter": "grok-build"}]}
    codex = {"instances": [{"id": "reviewer", "adapter": "codex"}]}
    new_grok, codex_only = authority.digest(grok), authority.digest(codex)
    assert authority.facts(grok)["providers"][0]["transport"]["output_limit"] == 557056
    previous = replace(GrokBuildAdapter.profile, output_limit=49152)
    monkeypatch.setattr(GrokBuildAdapter, "profile", previous)
    assert authority.digest(grok) != new_grok
    assert authority.digest(codex) == codex_only


def test_version_and_subscription_metadata_keep_the_small_stdout_limit(tmp_path, monkeypatch):
    adapter, _, _ = _harness(tmp_path, subscription=True)
    calls = capture_specs(monkeypatch, adapter._runner)
    assert adapter.quota_connection().read() == {"config": {"creditUsagePercent": 41}}
    assert [size for argv, size in calls if argv[-1] == "--version"] == [49152]
    assert [size for argv, size in calls if argv[-2:] == ("agent", "stdio")] == [49152]


@pytest.mark.parametrize(("asked", "expected"), [(2048, 2048), (90000, 49152)])
def test_explicit_version_cap_is_a_ceiling_not_a_request_to_expand(
        tmp_path, monkeypatch, asked, expected):
    adapter, _, _ = _harness(tmp_path)
    (tmp_path / "root" / "probe").mkdir()
    calls = capture_specs(monkeypatch, adapter._runner)
    outcome = adapter._attempt(("--version",), "probe", timeout=5, output_limit=asked)
    assert outcome.exit_code == 0
    assert [size for argv, size in calls if argv[-1] == "--version"] == [expected]
