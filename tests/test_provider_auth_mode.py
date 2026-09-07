"""How a provider row says which login it is pinned to, and what that refuses.

Until this circuit existed a provider row could not say how the harness
authenticates at all, so the only road the Claude transport could take was the
one it hard-codes: ``--bare``, which the vendor's own help says never reads an
OAuth credential or the system keychain, plus a fresh config directory per
attempt. That road works only with an API key in the environment, and the owner
rejected an API key as a prerequisite on 2026-09-07.

The mode is DECLARED, never guessed. A row that says nothing is the road that
shipped, so every configuration written before this circuit means exactly what
it meant. A row that says ``subscription`` must also say where the login is
kept, because the product will not derive that path from an environment
variable: ``%LOCALAPPDATA%`` was measured to resolve differently for a packaged
process than for a shell, which is how a documented install path came to point
at an empty directory.

The refusal that matters most here is the one against a silent fallback. The
reviewed Claude build was measured going straight to ``POST /v1/messages`` with
an ``x-api-key`` header when ``ANTHROPIC_API_KEY`` stood in its environment --
under ``--safe-mode``, the very flag the subscription road needs. So a
subscription row that also forwards an API-billing credential is not a
belt-and-braces configuration: it is a row that would quietly bill an API
account while the operator believes a subscription is being used. It is refused
by name at the door.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.adapters.provider import (
    API_BILLING_ENV,
    AUTH_MODES,
    AVAILABILITY_STATES,
    CONTRACT_AUTH_STATES,
    IMPLEMENTATION_STATES,
    DEFAULT_AUTH_MODE,
    SUBSCRIPTION_AUTH,
    SUBSCRIPTION_PROTOCOLS,
    UNPINNED_AUTH,
    ProviderConfig,
    ProviderConfigError,
    ProviderContract,
    provider_projection,
)
from conductor.command.operator_config import (
    PROVIDER_CONFIG_FILENAME,
    OperatorConfigError,
    load_provider_configs,
    save_provider_configs,
)
from conductor.command.adapters.provider import KNOWN_PROTOCOLS
from conductor.command.providers import resolve_providers

PROTOCOL = "claude-code-headless-v1"
EXECUTABLE = "/opt/claude/bin/claude"
AUTH_HOME = "/var/lib/conduct/auth/claude-code"


def a_config(**changes):
    """One admitted provider row, before this circuit's keys are pinned."""
    row = {"provider_id": "claude-code", "executable": EXECUTABLE, "protocol": PROTOCOL}
    row.update(changes)
    return ProviderConfig(**row)


def a_contract(**changes):
    """One reviewed descriptor of a provider, as the registry would build it."""
    fields = {
        "provider_id": "claude-code", "display_name": "Claude Code", "vendor": "A",
        "version": PROTOCOL, "capabilities": ("observe",), "schema_pairs": (),
        "lifecycle": ("observe", "prepare", "execute", "verify"),
        "availability": "available", "available": True, "auth": DEFAULT_AUTH_MODE}
    fields.update(changes)
    return ProviderContract(**fields)


def a_document(**changes):
    """One well-formed operator document carrying a single provider row."""
    row = {"provider_id": "claude-code", "executable": EXECUTABLE, "protocol": PROTOCOL}
    row.update(changes)
    return {"schema_version": 1, "providers": [row]}


def write_config(tmp_path, document):
    path = tmp_path / PROVIDER_CONFIG_FILENAME
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_a_row_that_says_nothing_about_authentication_is_the_road_that_shipped():
    config = a_config()
    assert config.auth == DEFAULT_AUTH_MODE == "api_key"
    assert config.auth_home == ""
    assert config.as_dict()["auth"] == "api_key"
    assert config.as_dict()["auth_home"] == ""


def test_the_two_authentication_modes_are_a_closed_set():
    assert AUTH_MODES == frozenset({"api_key", "subscription"})
    assert SUBSCRIPTION_AUTH == "subscription"
    assert DEFAULT_AUTH_MODE in AUTH_MODES


@pytest.mark.parametrize("mode", ["", "oauth", "API-KEY", "subscription ", None, 1, True])
def test_an_authentication_mode_outside_the_closed_set_is_refused(mode):
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth=mode)
    assert "auth" in str(error.value)


def test_a_subscription_row_that_does_not_say_where_the_login_lives_is_refused():
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth=SUBSCRIPTION_AUTH)
    assert "auth_home" in str(error.value)


def test_an_api_key_row_may_not_pin_a_login_directory_nothing_would_read():
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth_home=AUTH_HOME)
    assert "auth_home" in str(error.value)


@pytest.mark.parametrize("home", ["auth/claude", "./auth", "", "\x00/auth", 7])
def test_a_login_directory_that_is_not_one_absolute_path_is_refused(home):
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth=SUBSCRIPTION_AUTH, auth_home=home)
    assert "auth_home" in str(error.value)


def test_a_subscription_row_is_admitted_with_an_absolute_login_directory():
    config = a_config(auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME)
    assert config.auth == SUBSCRIPTION_AUTH
    assert config.auth_home == AUTH_HOME
    assert ProviderConfig.from_dict(config.as_dict()) == config


def test_the_api_billing_variables_are_a_closed_named_roster():
    assert API_BILLING_ENV == frozenset({
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY", "CODEX_API_KEY"})


@pytest.mark.parametrize("name", sorted(API_BILLING_ENV))
def test_a_subscription_row_may_not_forward_an_api_billing_credential(name):
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME, env_allow=[name])
    assert name in str(error.value)


@pytest.mark.parametrize("name", sorted(API_BILLING_ENV))
def test_an_api_key_row_still_forwards_the_credential_that_road_needs(name):
    assert a_config(env_allow=[name]).env_allow == (name,)


def test_a_subscription_row_may_forward_a_variable_that_is_not_a_credential():
    config = a_config(
        auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME, env_allow=["HTTPS_PROXY"])
    assert config.env_allow == ("HTTPS_PROXY",)


def test_the_operator_file_reads_and_writes_the_two_new_keys(tmp_path):
    path = write_config(tmp_path, a_document(auth="subscription", auth_home=AUTH_HOME))
    (config,) = load_provider_configs(path)
    assert (config.auth, config.auth_home) == (SUBSCRIPTION_AUTH, AUTH_HOME)
    save_provider_configs(path, (config,))
    written = json.loads(path.read_text(encoding="utf-8"))["providers"][0]
    assert written["auth"] == "subscription"
    assert written["auth_home"] == AUTH_HOME


def test_the_operator_file_writes_no_authentication_key_for_the_road_that_shipped(tmp_path):
    path = write_config(tmp_path, a_document())
    (config,) = load_provider_configs(path)
    save_provider_configs(path, (config,))
    written = json.loads(path.read_text(encoding="utf-8"))["providers"][0]
    assert "auth" not in written and "auth_home" not in written
    assert set(written) == {"provider_id", "executable", "protocol"}


def test_the_vendor_login_is_implemented_for_exactly_two_protocols():
    """A mode is not a label: only a transport that drives a login may claim one."""
    assert SUBSCRIPTION_PROTOCOLS == frozenset({
        "claude-code-headless-v1", "codex-headless-v1"})
    assert SUBSCRIPTION_PROTOCOLS <= KNOWN_PROTOCOLS


@pytest.mark.parametrize(
    "protocol", sorted(KNOWN_PROTOCOLS - SUBSCRIPTION_PROTOCOLS))
def test_a_protocol_with_no_login_transport_refuses_the_subscription_mode(protocol):
    with pytest.raises(ProviderConfigError) as error:
        a_config(protocol=protocol, auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME)
    assert protocol in str(error.value)


@pytest.mark.parametrize("protocol", sorted(SUBSCRIPTION_PROTOCOLS))
def test_both_login_protocols_admit_the_subscription_mode(protocol):
    assert a_config(protocol=protocol, auth=SUBSCRIPTION_AUTH,
                    auth_home=AUTH_HOME).auth == SUBSCRIPTION_AUTH


def test_the_login_vocabulary_shares_no_value_with_the_other_two(tmp_path):
    assert CONTRACT_AUTH_STATES == frozenset(
        {"api_key", "subscription", "unpinned"})
    assert not CONTRACT_AUTH_STATES & set(AVAILABILITY_STATES)
    assert not CONTRACT_AUTH_STATES & set(IMPLEMENTATION_STATES)


def a_resolution(tmp_path, *configs):
    return resolve_providers(
        list(configs), root=tmp_path, clock=lambda: "2026-09-07T00:00:00Z",
        ids=lambda kind: f"{kind}-1")


def test_a_configured_row_carries_the_login_it_pinned_onto_the_wire(tmp_path):
    resolution = a_resolution(tmp_path, a_config(
        executable=str(tmp_path / "claude.exe"), auth=SUBSCRIPTION_AUTH,
        auth_home=AUTH_HOME))
    rows = {row["provider_id"]: row for row in provider_projection(resolution.contracts)}
    assert rows["claude-code"]["auth"] == SUBSCRIPTION_AUTH
    assert rows["claude-code"]["availability"] == "executable_absent"


def test_a_row_that_left_the_field_out_carries_the_login_that_shipped(tmp_path):
    resolution = a_resolution(tmp_path, a_config(executable=str(tmp_path / "claude.exe")))
    rows = {row["provider_id"]: row for row in provider_projection(resolution.contracts)}
    assert rows["claude-code"]["auth"] == "api_key"


def test_a_provider_no_row_names_carries_no_login_at_all(tmp_path):
    resolution = a_resolution(tmp_path)
    rows = {row["provider_id"]: row for row in provider_projection(resolution.contracts)}
    assert rows, "the catalogue registers every provider, configured or not"
    for row in rows.values():
        assert row["availability"] == "unconfigured"
        assert row["auth"] == UNPINNED_AUTH


def test_a_descriptor_may_not_claim_a_login_no_row_pinned():
    """Unconfigured and api_key are different facts, and the first may not borrow."""
    with pytest.raises(ProviderConfigError, match="unpinned login"):
        a_contract(availability="unconfigured", available=False)
    with pytest.raises(ProviderConfigError, match="unpinned login"):
        a_contract(availability="unconfigured", available=False, auth=SUBSCRIPTION_AUTH)
    assert a_contract(
        availability="unconfigured", available=False, auth=UNPINNED_AUTH).auth == "unpinned"


@pytest.mark.parametrize("state", ["", "none", "API-KEY", None, True])
def test_a_descriptor_refuses_a_login_state_outside_the_closed_set(state):
    with pytest.raises(ProviderConfigError, match="reviewed login state"):
        a_contract(auth=state)


def test_the_wire_row_never_carries_the_login_directory(tmp_path):
    resolution = a_resolution(tmp_path, a_config(
        executable=str(tmp_path / "claude.exe"), auth=SUBSCRIPTION_AUTH,
        auth_home=AUTH_HOME))
    blob = json.dumps(provider_projection(resolution.contracts))
    assert AUTH_HOME not in blob
    assert set(provider_projection(resolution.contracts)[0]) == {
        "provider_id", "display_name", "availability", "implementation", "auth",
        "controls"}


@pytest.mark.parametrize("row", [
    {"auth": "oauth", "auth_home": AUTH_HOME},
    {"auth": "subscription"},
    {"auth_home": AUTH_HOME},
    {"auth": "subscription", "auth_home": "relative/path"},
    {"auth": "subscription", "auth_home": AUTH_HOME, "env_allow": ["ANTHROPIC_API_KEY"]},
])
def test_a_refused_authentication_row_names_the_exact_file_and_row(tmp_path, row):
    path = write_config(tmp_path, a_document(**row))
    with pytest.raises(OperatorConfigError) as error:
        load_provider_configs(path)
    assert str(path) in str(error.value)
    assert "providers[0]" in str(error.value)
