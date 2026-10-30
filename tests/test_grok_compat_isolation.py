"""Every real fake-Grok child receives disabled personal-profile import switches."""
from dataclasses import replace

import pytest

from conductor.command.adapters.grok_build import GROK_PROTOCOL, GrokBuildAdapter
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.policy_providers import ProviderAuthority
from conductor.command.providers import resolve_providers
from tests import _fakegrok
from tests.test_command_grok_transport import (
    INSTRUCTION_BODY, NOW, _Ids, _executable, a_request, run_once)


COMPAT = {
    "GROK_CLAUDE_SKILLS_ENABLED": "false",
    "GROK_CLAUDE_RULES_ENABLED": "false",
    "GROK_CLAUDE_AGENTS_ENABLED": "false",
    "GROK_CLAUDE_MCPS_ENABLED": "false",
    "GROK_CLAUDE_HOOKS_ENABLED": "false",
    "GROK_CLAUDE_SESSIONS_ENABLED": "false",
    "GROK_CURSOR_SKILLS_ENABLED": "false",
    "GROK_CURSOR_RULES_ENABLED": "false",
    "GROK_CURSOR_AGENTS_ENABLED": "false",
    "GROK_CURSOR_MCPS_ENABLED": "false",
    "GROK_CURSOR_HOOKS_ENABLED": "false",
    "GROK_CURSOR_SESSIONS_ENABLED": "false",
}
TELEMETRY = {
    "GROK_TELEMETRY_ENABLED": "0", "GROK_TELEMETRY_TRACE_UPLOAD": "0",
    "GROK_TELEMETRY_MIXPANEL_ENABLED": "0", "GROK_FEEDBACK_ENABLED": "0",
}


def _harness(tmp_path, subscription=False):
    executable = _executable(tmp_path)
    root, login, log = tmp_path / "root", tmp_path / "fake-login", tmp_path / "spawns.log"
    (root / "instructions").mkdir(parents=True)
    (root / "instructions/instr-001.md").write_text(INSTRUCTION_BODY, encoding="utf-8")
    login.mkdir()
    (login / "auth.json").write_text("{}", encoding="utf-8")
    # These are explicitly selected operator values, not unselected ambient variables.
    environment = {name: "true" for name in COMPAT}
    environment[_fakegrok.SPAWN_LOG] = str(log)
    config = ProviderConfig(
        provider_id="grok-build", executable=str(executable), protocol=GROK_PROTOCOL,
        env_allow=tuple(environment), auth="subscription" if subscription else "api_key",
        auth_home=str(login) if subscription else "")
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ=environment,
        # The existing fake transport road; this is not evidence of Grok subscription
        # execution inside the product boundary, which still needs its own relay.
        confine_platform=None)
    adapter = resolution.registry.resolve("grok-build")
    authority = ProviderAuthority([config], resolution.contracts, resolution.registry)
    return adapter, log, authority


@pytest.mark.parametrize("road", ["api-dispatch", "subscription-dispatch", "quota"])
def test_selected_true_values_cannot_enable_compat_imports_in_any_child(tmp_path, road):
    adapter, log, _authority = _harness(tmp_path, subscription=road != "api-dispatch")
    expected = [["--version"]]
    if road == "quota":
        assert adapter.quota_connection().read() == {"config": {"creditUsagePercent": 41}}
        expected.append(["--no-auto-update", "agent", "stdio"])
    else:
        assert run_once(adapter, a_request()).outcome == "succeeded"
        if road == "subscription-dispatch":
            expected.append(["--no-auto-update", "agent", "stdio"])
        expected.append(["--no-auto-update", "--output-format", "plain",
                         "--allow", "Edit", "--allow", "Write", "--single"])
    rows = _fakegrok.spawns(log)
    assert len(rows) == len(expected), "the expected native fake children must really run"
    for row, prefix in zip(rows, expected, strict=True):
        assert row["argv"][:len(prefix)] == prefix
        assert row["compat_switches"] == COMPAT
        assert row["switches"] == TELEMETRY


def test_compat_pairs_are_bound_into_the_grok_grant_digest(tmp_path, monkeypatch):
    _adapter, _log, authority = _harness(tmp_path)
    config = {"instances": [{"id": "doer", "adapter": "grok-build"}]}
    profile = GrokBuildAdapter.profile
    current = authority.digest(config)
    facts = authority.facts(config)["providers"][0]["transport"]
    assert dict(facts["forced_env"]) == {**TELEMETRY, **COMPAT}
    old = replace(profile, forced_env=tuple(TELEMETRY.items()))
    monkeypatch.setattr(GrokBuildAdapter, "profile", old)
    assert authority.digest(config) != current, "old grants must not describe the new profile"
