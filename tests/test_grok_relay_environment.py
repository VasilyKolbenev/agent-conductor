"""Grok route names refuse before a child; code-owned compatibility pairs survive metadata."""
from dataclasses import replace

import pytest

from conductor.command.adapters import relay_env
from conductor.command.adapters.provider import ProviderConfigError
from tests.test_provider_auth_mode import AUTH_HOME, a_config
from tests.relay_fixtures import layout, shape
from tests.test_grok_compat_isolation import COMPAT


ROUTES = (
    "XAI_API_KEY", "GROK_CLI_CHAT_PROXY_BASE_URL", "GROK_AUTH_PROVIDER_COMMAND",
    "GROK_OIDC_ISSUER", "GROK_OIDC_CLIENT_ID", "GROK_DEPLOYMENT_KEY",
    "GROK_AUTH", "GROK_AUTH_PATH", "GROK_AUTH_EARLY_INVALIDATION_SECS",
    "GROK_AUTH_TOKEN_TTL", "GROK_AUTH_PROVIDER_LABEL", "GROK_LOCAL_AUTH",
    "GROK_OAUTH2_ISSUER", "GROK_OAUTH2_CLIENT_ID", "GROK_OAUTH2_PRINCIPAL_TYPE",
    "GROK_OAUTH2_PRINCIPAL_ID", "GROK_OAUTH2_SCOPES", "GROK_OAUTH2_REFERRER",
    "GROK_OIDC_SCOPES", "GROK_OIDC_AUDIENCE", "GROK_FORCE_LOGIN_TEAM_ID",
    "GROK_DISABLE_API_KEY_AUTH", "GROK_FOLDER_TRUST", "GROK_TRACK_HEADLESS",
    "GROK_WS_URL", "GROK_WS_ORIGIN", "GROK_TELEMETRY_EVENTS_URL",
    "GROK_TELEMETRY_EVENTS_API_KEY", "GROK_TELEMETRY_MIXPANEL_TOKEN",
    "XAI_API_BASE_URL", "GROK_MODELS_BASE_URL", "GROK_MODELS_LIST_URL",
    "GROK_MANAGED_CONFIG_URL", "GROK_FEEDBACK_BASE_URL", "GROK_ALPHA_TEST_KEY",
    "GROK_AUTH_FORCE_DARK_WAKE", *COMPAT,
)
PREFIX_NAMES = ("GROK_TRACE_UPLOAD_FUTURE", "grok_internal_otlp_future")


@pytest.mark.parametrize("name", (*ROUTES, *PREFIX_NAMES))
def test_subscription_configuration_rejects_grok_routing_names(name):
    with pytest.raises(ProviderConfigError):
        a_config(auth="subscription", auth_home=AUTH_HOME, env_allow=[name.lower()])


def test_api_configuration_keeps_its_existing_environment_selection():
    assert a_config(env_allow=list(ROUTES)).env_allow == ROUTES


def test_grok_home_uses_the_same_project_identity_and_containment_rules(tmp_path):
    found = layout(tmp_path, kind="g")
    assert shape(found) is None
    assert "another project" in shape(found, root_identity=(123, 456))


def test_grok_roster_and_prefix_policy_are_independent_literals():
    from conductor.command.adapters.grok_relay import GROK_RELAY

    assert set(GROK_RELAY.forbidden_env) == set(ROUTES) | set(relay_env.COMMON_ROUTE_ENV)
    assert GROK_RELAY.forbidden_prefixes == ("GROK_TRACE_UPLOAD_", "GROK_INTERNAL_OTLP_")
    for name in (*ROUTES, *PREFIX_NAMES):
        assert GROK_RELAY.forbids(name.lower())
        assert relay_env.route_env_named([name.lower()]) == (name.lower(),)
    changed = replace(GROK_RELAY, forbidden_prefixes=())
    assert not changed.forbids(PREFIX_NAMES[0]), "the bound prefix field must control behavior"
    for name in ("GROK_DEBUG_LOG", "RUST_LOG", "GROK_TRACE_UPLOAD", "GROK_INTERNAL_OTLP"):
        assert not GROK_RELAY.forbids(name)


def _metadata(tmp_path):
    """A real fake child and login lease; the production Grok profile stays inactive."""
    from conductor import ownership_transition
    from conductor.command.adapters.grok_relay import GROK_RELAY
    from tests._fakeboundary import confined
    from tests.test_grok_compat_isolation import _harness

    adapter, log, _authority = _harness(tmp_path, subscription=True)
    (adapter._root / "conductor").mkdir()
    ownership_transition.activate(adapter._root, legacy_writers_stopped=True)
    login = tmp_path / "DecemberCommand" / "logins" / "grok-build"
    login.mkdir(parents=True)
    (login / "auth.json").write_bytes(b"{}")
    adapter._pin = replace(adapter._pin, auth_home=str(login))
    adapter.profile = replace(adapter.profile, login_relay=GROK_RELAY)
    confined(adapter, tmp_path / "scratch", auth_homes=(login,))
    return adapter, log, login


def _read(adapter):
    from conductor import ownership

    with ownership.acquire_owner(adapter._root):
        return adapter.quota_connection().read()


def test_code_owned_false_pairs_reach_both_real_home_metadata_children(tmp_path):
    from conductor.command.adapters.quota_connection import NativeQuotaReadError
    from tests import _fakegrok

    adapter, log, login = _metadata(tmp_path)
    try:
        result = _read(adapter)
    except NativeQuotaReadError as error:
        result = {"refused": error.reason}
    assert result == {"config": {"creditUsagePercent": 41}}
    rows = _fakegrok.spawns(log)
    assert len(rows) == 2
    assert rows[0]["argv"] == ["--version"]
    assert rows[1]["argv"] == ["--no-auto-update", "agent", "stdio"]
    assert all(row["compat_switches"] == COMPAT for row in rows)
    assert (login / "auth.json").read_bytes() == b"{}"


@pytest.mark.parametrize("name", ["GROK_CLAUDE_HOOKS_ENABLED", "grok_cursor_mcps_enabled",
                                  "GROK_AUTH_PATH", "grok_trace_upload_future"])
@pytest.mark.parametrize("value", ["true", "false"])
def test_direct_pin_operator_routes_refuse_before_any_child(tmp_path, name, value):
    from conductor.command.adapters.quota_connection import NativeQuotaReadError
    from tests import _fakegrok

    adapter, log, _login = _metadata(tmp_path)
    adapter._pin = replace(adapter._pin, env_allow=(*adapter._pin.env_allow, name))
    adapter._runner._environ[name] = value
    with pytest.raises(NativeQuotaReadError) as refused:
        _read(adapter)
    assert refused.value.reason == "not_supported"
    assert _fakegrok.spawns(log) == []


def test_selected_but_absent_route_is_not_forwarded_or_refused(tmp_path):
    adapter, _log, _login = _metadata(tmp_path)
    name = "GROK_AUTH_PATH"
    adapter._pin = replace(adapter._pin, env_allow=(*adapter._pin.env_allow, name))
    assert name not in adapter._runner._environ
    assert _read(adapter) == {"config": {"creditUsagePercent": 41}}


@pytest.mark.parametrize("pair", [("GROK_CLAUDE_HOOKS_ENABLED", "true"),
                                  ("grok_claude_hooks_enabled", "false")])
def test_other_forced_pairs_do_not_gain_the_code_owned_exception(tmp_path, pair):
    from conductor.command.adapters.quota_connection import NativeQuotaReadError
    from tests import _fakegrok

    adapter, log, _login = _metadata(tmp_path)
    adapter.profile = replace(adapter.profile, forced_env=(pair,))
    with pytest.raises(NativeQuotaReadError) as refused:
        _read(adapter)
    assert refused.value.reason == "not_supported"
    assert _fakegrok.spawns(log) == []


@pytest.mark.parametrize("changes", [{"home_env": "CODEX_HOME"}, {"login_relay": None}])
def test_compat_exception_does_not_apply_to_other_profiles(changes):
    from conductor.command.adapters.grok_build import GROK_PROFILE
    from conductor.command.adapters.grok_relay import GROK_RELAY

    profile = replace(GROK_PROFILE, login_relay=GROK_RELAY)
    assert relay_env.grok_compat_switch(profile, "GROK_CLAUDE_HOOKS_ENABLED", "false")
    assert not relay_env.grok_compat_switch(
        replace(profile, **changes), "GROK_CLAUDE_HOOKS_ENABLED", "false")
