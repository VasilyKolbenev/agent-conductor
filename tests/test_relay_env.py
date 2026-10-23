"""The environment names a subscription may not forward, at the door, in the wizard and in the spec.

A subscription task runs on a login the product copied for it. A variable that carries its own
token, points the CLI at another credential store or another account, or reroutes the traffic or
the certificate it trusts, replaces that login without a word: the run would go on, on something
else, and nothing afterwards could see it. So a row that pins the subscription refuses them by name,
at the config door and at the question in the wizard, and the spec of each harness carries the same
names for a pin that was built without a row.

The roster is spelled out below on purpose and is the one F10 of the design lists (names read from
the pinned binaries; not a complete census of what they read). The match ignores case: a Windows
variable named `https_proxy` is `HTTPS_PROXY`, and on the other platforms the lower-case spelling
of a proxy variable is the one most tools read first.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import relay_env
from conductor.command.adapters.claude_relay import CLAUDE_RELAY
from conductor.command.adapters.codex_relay import CODEX_RELAY
from conductor.command.adapters.provider import (
    SUBSCRIPTION_AUTH, SUBSCRIPTION_PROTOCOLS, ProviderConfigError)
from tests.test_provider_auth_mode import AUTH_HOME, a_config
from tests.test_provider_setup import configure, menu_choice, pinned_files, project, written

__all__ = ["project"]

CLAUDE_NAMES = (
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
    "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_OAUTH_CLIENT_ID",
    "CLAUDE_CODE_HOST_CREDS_FILE", "CLAUDE_SECURESTORAGE_CONFIG_DIR",
    "CLAUDE_CODE_FORCE_WINDOWS_CREDMAN", "CLAUDE_CODE_CUSTOM_OAUTH_URL",
    "CLAUDE_CODE_ACCOUNT_UUID", "CLAUDE_CODE_USER_EMAIL", "CLAUDE_CODE_ORGANIZATION_UUID")
CODEX_NAMES = ("CODEX_REFRESH_TOKEN_URL_OVERRIDE",)
COMMON_NAMES = (
    "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "NODE_EXTRA_CA_CERTS", "NODE_TLS_REJECT_UNAUTHORIZED",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
EVERY_NAME = CLAUDE_NAMES + CODEX_NAMES + COMMON_NAMES
HARMLESS = ("MY_TOKEN_NAME", "LANG", "NO_PROXY", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")
REFUSAL_WORDS = "replaces the subscription login or reroutes the harness's traffic"


def test_the_roster_of_names_is_the_one_f10_of_the_design_lists():
    assert relay_env.COMMON_ROUTE_ENV == tuple(sorted(COMMON_NAMES))
    assert relay_env.CLAUDE_ROUTE_ENV == tuple(sorted(CLAUDE_NAMES))
    assert relay_env.CODEX_ROUTE_ENV == tuple(sorted(CODEX_NAMES))
    assert relay_env.SUBSCRIPTION_ROUTE_ENV == tuple(sorted(EVERY_NAME))


def test_each_harness_carries_its_own_names_and_the_common_ones():
    assert CLAUDE_RELAY.forbidden_env == tuple(sorted(CLAUDE_NAMES + COMMON_NAMES))
    assert CODEX_RELAY.forbidden_env == tuple(sorted(CODEX_NAMES + COMMON_NAMES))
    assert relay_env.CLAUDE_FORBIDDEN_ENV == CLAUDE_RELAY.forbidden_env
    assert relay_env.CODEX_FORBIDDEN_ENV == CODEX_RELAY.forbidden_env


@pytest.mark.parametrize("name", EVERY_NAME)
def test_a_spec_forbids_its_names_in_any_spelling_and_not_the_other_harnesses(name):
    for spec, own in ((CLAUDE_RELAY, CLAUDE_NAMES + COMMON_NAMES),
                      (CODEX_RELAY, CODEX_NAMES + COMMON_NAMES)):
        expected = name in own
        assert spec.forbids(name) is expected
        assert spec.forbids(name.lower()) is expected
        assert spec.forbids(name.title()) is expected


@pytest.mark.parametrize("name", HARMLESS)
def test_a_spec_forbids_no_name_it_has_no_reason_to(name):
    assert CLAUDE_RELAY.forbids(name) is False
    assert CODEX_RELAY.forbids(name) is False


def test_the_names_a_list_holds_are_returned_as_the_operator_wrote_them():
    named = relay_env.route_env_named(
        ["MY_TOKEN_NAME", "https_proxy", "Node_Extra_Ca_Certs", "LANG"])

    assert named == ("https_proxy", "Node_Extra_Ca_Certs")
    assert relay_env.route_env_named([]) == ()
    assert relay_env.route_env_named(["PATH", "LANG"]) == ()


# --- the config door -------------------------------------------------------------------------


@pytest.mark.parametrize("name", EVERY_NAME)
def test_a_subscription_row_may_not_forward_a_name_that_replaces_the_login(name):
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME, env_allow=[name])

    assert name in str(error.value)
    assert "reroute" in str(error.value)


@pytest.mark.parametrize("name", EVERY_NAME)
def test_the_door_matches_the_name_in_any_case(name):
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME, env_allow=[name.lower()])

    assert name.lower() in str(error.value)


@pytest.mark.parametrize("protocol", sorted(SUBSCRIPTION_PROTOCOLS))
def test_every_subscription_protocol_refuses_the_same_names(protocol):
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "CODEX_REFRESH_TOKEN_URL_OVERRIDE", "HTTPS_PROXY"):
        with pytest.raises(ProviderConfigError):
            a_config(protocol=protocol, auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME,
                     env_allow=[name])


def test_the_door_names_every_offender_and_not_the_innocent_beside_them():
    with pytest.raises(ProviderConfigError) as error:
        a_config(auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME,
                 env_allow=["HTTPS_PROXY", "MY_TOKEN_NAME", "SSL_CERT_FILE"])

    text = str(error.value)
    assert "HTTPS_PROXY" in text and "SSL_CERT_FILE" in text
    assert "MY_TOKEN_NAME" not in text


@pytest.mark.parametrize("name", HARMLESS)
def test_a_subscription_row_may_forward_a_name_that_changes_no_login(name):
    config = a_config(auth=SUBSCRIPTION_AUTH, auth_home=AUTH_HOME, env_allow=[name])

    assert config.env_allow == (name,)


@pytest.mark.parametrize("name", EVERY_NAME)
def test_the_environment_road_still_forwards_what_it_always_did(name):
    """The refusal is the subscription's: an API-key row has no login to replace."""
    assert a_config(env_allow=[name]).env_allow == (name,)


# --- the wizard ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "CLAUDE_CODE_OAUTH_TOKEN", "CODEX_REFRESH_TOKEN_URL_OVERRIDE", "HTTPS_PROXY", "https_proxy",
    "NODE_EXTRA_CA_CERTS", "ANTHROPIC_BASE_URL", "SSL_CERT_DIR"])
def test_the_wizard_refuses_such_a_name_while_it_is_typed_and_writes_the_one_after(
        project, tmp_path, capsys, name):
    executable, _ = pinned_files(tmp_path, "claude-code")
    home = tmp_path / "auth" / "claude-code"

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", str(home), name, "MY_TOKEN_NAME", "y") == 0

    said = capsys.readouterr().err
    assert REFUSAL_WORDS in said, said
    assert f"{name!r}" in said
    assert written(project)["providers"][0]["env_allow"] == ["MY_TOKEN_NAME"]


def test_the_wizard_leaves_the_environment_road_alone(project, tmp_path, capsys):
    executable, _ = pinned_files(tmp_path, "claude-code")

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "2", "HTTPS_PROXY", "y") == 0

    assert REFUSAL_WORDS not in capsys.readouterr().err
    assert written(project)["providers"][0]["env_allow"] == ["HTTPS_PROXY"]
