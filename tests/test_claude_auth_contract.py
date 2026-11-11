"""Q8: measured saved-profile names/types and effective subscription environment.

The roster was measured without values on 2026-11-11 from the saved dedicated
2026-10-30 profile. Fake values here prove policy, not a new live Claude login.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from conductor.command.adapters.claude_code import CLAUDE_PROFILE
from conductor.command.adapters.claude_relay import CLAUDE_RELAY
from conductor.command.adapters.headless_spec import attempt_spec
from conductor.command.adapters.login_relay import Refused
from conductor.command.adapters.provider import ProviderConfigError
from conductor.command.contract_values import _content_digest
from tests import relay_credentials as fake
from tests.relay_roads import CLAUDE, Site
from tests.test_provider_auth_mode import AUTH_HOME, a_config
from tests.test_provider_setup import configure, menu_choice, pinned_files, project, written

__all__ = ["project"]


EXTRA_NAMES = (
    "CLAUDE_CODE_HOST_AUTH_ENV_VAR", "CLAUDE_CODE_HFI_BEARER_TOKEN",
    "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST", "CLAUDE_CODE_HOST_HTTP_PROXY_PORT",
    "CLAUDE_CODE_HOST_SOCKS_PROXY_PORT", "ANTHROPIC_UNIX_SOCKET", "ANTHROPIC_CUSTOM_HEADERS",
    "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE", "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_FOUNDRY_AUTH_TOKEN", "ANTHROPIC_AWS_API_KEY")
ROSTER = (
    ("accountCreatedAt", "str"), ("accountUuid", "str"), ("billingType", "str"),
    ("ccOnboardingFlags", "dict"), ("claudeCodeTrialDurationDays", "null"),
    ("claudeCodeTrialEndsAt", "null"), ("displayName", "str"), ("emailAddress", "str"),
    ("fullName", "str"), ("hasExtraUsageEnabled", "bool"), ("organizationName", "str"),
    ("organizationRateLimitTier", "str"), ("organizationRole", "str"),
    ("organizationType", "str"), ("organizationUuid", "str"), ("profileFetchedAt", "int"),
    ("seatTier", "null"), ("subscriptionCreatedAt", "str"), ("userRateLimitTier", "null"),
    ("workspaceRole", "null"))


def account():
    values = {"str": "fake-profile-text", "dict": {"unknownNested": "fake-never-carried"},
              "null": None, "bool": True, "int": 1770000000000}
    return {name: values[kind] for name, kind in ROSTER}


@pytest.mark.parametrize("name", EXTRA_NAMES)
@pytest.mark.parametrize("lower", [False, True])
def test_auth_route_name_is_refused_by_the_subscription_config(name, lower):
    selected = name.lower() if lower else name
    with pytest.raises(ProviderConfigError):
        a_config(auth="subscription", auth_home=AUTH_HOME, env_allow=[selected])
    assert a_config(env_allow=[selected]).env_allow == (selected,), "API control changed"


@pytest.mark.parametrize("name", EXTRA_NAMES)
@pytest.mark.parametrize("source", ["selected", "forced"])
def test_auth_route_is_refused_before_a_vendor_question(tmp_path, name, source):
    site = Site(tmp_path, CLAUDE)
    if source == "selected":
        site.adapter._pin = replace(site.adapter._pin, env_allow=(name.lower(),))
        site.runner._environ[name.lower()] = "fake-route-value-never-forwarded"
    else:
        site.adapter.profile = replace(site.adapter.profile,
                                       forced_env=(*site.adapter.profile.forced_env,
                                                   (name, "fake-route-value-never-forwarded")))
    result = site.run()
    assert result.outcome == "failed", result.detail
    assert result.detail == ("the Claude Code login is not ready for an isolated attempt: "
                             "the environment of the attempt carries a name that replaces "
                             "the login or reroutes its traffic, so no task was spawned")
    assert site.rows() == [] and site.runner.runs == []
    assert site.runner.events == ["relay-root"]
    assert "fake-route-value" not in result.detail


@pytest.mark.parametrize("name", EXTRA_NAMES)
def test_wizard_rejects_new_route_name_and_saves_the_harmless_answer(project, tmp_path, name):
    executable, _ = pinned_files(tmp_path, "claude-code")
    home = tmp_path / "DecemberCommand" / "logins" / "claude-code"
    assert configure(project, menu_choice("claude-code"), str(executable), "1", str(home),
                     name.lower(), "MY_TOKEN_NAME", "y") == 0
    assert written(project)["providers"][0]["env_allow"] == ["MY_TOKEN_NAME"]


def test_observed_roster_is_closed_and_nested_flags_stay_explicitly_out(tmp_path):
    original = account()
    home = fake.claude_home(tmp_path, profile=fake.claude_profile(oauthAccount=original))
    result = CLAUDE_RELAY.bootstrap(home)
    assert not isinstance(result, Refused), result
    expected = {key: value for key, value in original.items() if key != "ccOnboardingFlags"}
    assert json.loads(result[".claude.json"]) == {"oauthAccount": expected}
    assert b"fake-never-carried" not in result[".claude.json"]
    assert len(expected) == 19 and len(original) == 20


@pytest.mark.parametrize("value", ["fake-secret-value-must-not-travel", 3, False, None, {}, []])
def test_unknown_account_field_refuses_the_whole_copy(tmp_path, value):
    extra = {**account(), "unmeasuredField": value}
    home = fake.claude_home(tmp_path, profile=fake.claude_profile(oauthAccount=extra))
    assert CLAUDE_RELAY.bootstrap(home) == Refused("account_unknown")


@pytest.mark.parametrize("name,kind", ROSTER)
def test_changed_observed_field_type_refuses_the_whole_copy(tmp_path, name, kind):
    changed = account()
    changed[name] = [] if kind != "dict" else "fake-not-a-dict"
    home = fake.claude_home(tmp_path, profile=fake.claude_profile(oauthAccount=changed))
    assert CLAUDE_RELAY.bootstrap(home) == Refused("account_unknown")


def test_only_two_nonempty_uuids_are_required_and_all_other_observed_fields_are_optional(tmp_path):
    minimal = {"accountUuid": "fake-account-uuid", "organizationUuid": "fake-org-uuid"}
    home = fake.claude_home(tmp_path, profile=fake.claude_profile(oauthAccount=minimal))
    result = CLAUDE_RELAY.bootstrap(home)
    assert not isinstance(result, Refused), result
    assert json.loads(result[".claude.json"]) == {"oauthAccount": minimal}


def test_schema_and_omit_policy_enter_the_frozen_profile_digest():
    profile = asdict(CLAUDE_PROFILE)
    policy = profile["login_relay"]
    assert policy.get("account_schema") == ROSTER
    assert policy.get("account_omitted") == ("ccOnboardingFlags",)
    changed = replace(CLAUDE_RELAY, account_schema=ROSTER[:-1])
    assert _content_digest(asdict(replace(CLAUDE_PROFILE, login_relay=changed))) != (
        _content_digest(profile))
    carried = replace(CLAUDE_RELAY, account_omitted=())
    assert _content_digest(asdict(replace(CLAUDE_PROFILE, login_relay=carried))) != (
        _content_digest(profile))


def test_the_pinned_b_environment_has_exact_code_owned_switches_and_minted_home(tmp_path):
    site = Site(tmp_path, CLAUDE)
    selected = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP")
    site.adapter._pin = replace(site.adapter._pin, env_allow=selected)
    home, work = tmp_path / "relay", tmp_path / "work"
    spec = attempt_spec(site.adapter, ("--safe-mode", "-p", "fake-task"), home, str(work),
                        timeout=60, stdin_bytes=b"fake-task", mode="dispatch")
    assert spec.env_allow == selected
    assert dict(spec.env) == {"PYTHONDONTWRITEBYTECODE": "1", "DISABLE_AUTOUPDATER": "1",
                              "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                              "CLAUDE_CONFIG_DIR": str(home)}
    assert spec.cwd == str(work) and spec.timeout_seconds == 60
