"""The Claude Code relay: what the real login must look like, and what an attempt is given of it.

`.credentials.json` of the pinned 2.1.239 is one subscription credential, but the same file can
also carry other credentials (a tool server's OAuth, plugin secrets, a gateway's trust), and a copy
of a file that holds them would hand them to a child that was never meant to have them. So the
relay admits one shape only, and anything else is refused by name before a byte is copied.

The account is not in that file. It is in the vendor's profile (`.claude.json`), which also holds
tool servers, projects and a great deal else; the relay takes the account object from it and
nothing more. The credential the child gets has no refresh token (the decision of 23.10.2026:
access-only), and the Windows credential manager, which would take the refreshed token out of a
file altogether, is refused when the profile says it is on.

Expected relay documents are spelled here by hand. Whether the real CLI works on them is the live
measurement M2 and is not proved by this file.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from conductor.command.adapters import login_relay
from conductor.command.adapters.claude_relay import CLAUDE_FORM, CLAUDE_RELAY
from conductor.command.adapters.login_relay import Refused, ready
from tests import relay_credentials as fake

EXPIRY = datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc)
ACCOUNT = {
    "accountUuid": "00000000-0000-4000-8000-00000000000a",
    "emailAddress": "fake.person@example.invalid",
    "organizationUuid": "00000000-0000-4000-8000-00000000000b",
    "displayName": "Fake Person",
    "organizationName": "Fake Organization",
    "organizationRole": "admin",
}


def admit(doc):
    return CLAUDE_RELAY.admit(doc)


def with_oauth(**changes):
    return fake.claude_leaf(**changes)


def bootstrapped(home):
    """The files `bootstrap` returns for a home that must be one it can read."""
    found = CLAUDE_RELAY.bootstrap(home)
    assert not isinstance(found, Refused), found
    return found


# --- admit -----------------------------------------------------------------------------------


def test_a_full_subscription_credential_is_admitted():
    assert admit(fake.claude_leaf()) is None


def test_a_credential_that_names_no_refresh_token_at_all_is_still_a_credential():
    leaf = fake.claude_leaf()
    del leaf["claudeAiOauth"]["refreshToken"], leaf["claudeAiOauth"]["refreshTokenExpiresAt"]

    assert admit(leaf) is None


@pytest.mark.parametrize("extra", [
    "mcpOAuth", "pluginSecrets", "enterpriseGateway", "gatewayTrust", "primaryApiKey",
    "a_key_this_build_has_never_heard_of"])
def test_a_file_that_holds_anything_beside_the_subscription_credential_is_foreign(extra):
    leaf = fake.claude_leaf()
    leaf[extra] = {"fake": "fake-value-that-must-not-travel-0123"}

    assert admit(leaf) == "foreign_credentials"


@pytest.mark.parametrize("doc", [
    {}, {"mcpOAuth": {"fake": {}}}, {"apiKey": "fake-api-key-0123456789"},
    {"primaryApiKey": "fake-api-key-0123456789"}])
def test_a_file_without_the_subscription_credential_is_foreign(doc):
    assert admit(doc) == "foreign_credentials"


@pytest.mark.parametrize("body", [None, "text", ["accessToken"], 5])
def test_a_credential_that_is_not_an_object_is_not_a_known_shape(body):
    assert admit({"claudeAiOauth": body}) == "unknown_shape"


@pytest.mark.parametrize("value", [
    "fake-api-key-0123456789", 1, True, None, ["fake-scope"], [], {"nested": "fake"}])
def test_a_key_inside_the_credential_that_the_schema_does_not_name_is_refused(value):
    """Whatever the type of its value: a list of text is a type the schema names for `scopes`."""
    assert admit(with_oauth(extraField=value)) == "unknown_shape"


@pytest.mark.parametrize("key,value", [
    ("accessToken", 5), ("refreshToken", ["x"]), ("expiresAt", "soon"), ("expiresAt", True),
    ("expiresAt", 1.5), ("expiresAt", None), ("refreshTokenExpiresAt", "x"),
    ("scopes", "user:inference"), ("scopes", [1, 2]), ("scopes", None),
    ("subscriptionType", 5), ("rateLimitTier", None), ("clientId", 1)])
def test_a_value_of_the_wrong_type_is_not_a_known_shape(key, value):
    assert admit(with_oauth(**{key: value})) == "unknown_shape"


def test_an_empty_or_missing_access_token_is_refused_by_its_own_code():
    leaf = fake.claude_leaf()
    del leaf["claudeAiOauth"]["accessToken"]

    assert admit(with_oauth(accessToken="")) == "no_access_token"
    assert admit(leaf) == "no_access_token"


@pytest.mark.parametrize("plan", ["console", "Console", " Console ", "Claude Console"])
def test_the_api_billing_plan_is_not_a_subscription(plan):
    assert admit(with_oauth(subscriptionType=plan)) == "console_plan"


@pytest.mark.parametrize("plan", ["max", "pro", "Claude Max", "team"])
def test_a_plan_that_is_not_the_api_billing_plan_is_admitted(plan):
    assert admit(with_oauth(subscriptionType=plan)) is None


def test_a_credential_that_names_no_plan_cannot_say_it_is_not_the_api_plan():
    leaf = fake.claude_leaf()
    del leaf["claudeAiOauth"]["subscriptionType"]

    assert admit(leaf) == "plan_unknown"
    assert admit(with_oauth(subscriptionType="   ")) == "plan_unknown"


# --- strip -----------------------------------------------------------------------------------


def test_the_access_only_copy_has_no_refresh_token_and_no_refresh_expiry():
    stripped = CLAUDE_RELAY.strip(fake.claude_leaf())

    assert stripped == {"claudeAiOauth": {
        "accessToken": "fake-claude-access-token-AAAAAAAAAAAA",
        "expiresAt": 1792771200000,
        "scopes": ["user:inference", "user:profile"],
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_5x",
        "clientId": "fake-claude-client-id-0000"}}
    assert "refreshToken" not in stripped["claudeAiOauth"]
    assert "refreshTokenExpiresAt" not in stripped["claudeAiOauth"]


def test_stripping_copies_and_never_changes_the_document_it_was_given():
    original = fake.claude_leaf()
    before = copy.deepcopy(original)

    stripped = CLAUDE_RELAY.strip(original)
    stripped["claudeAiOauth"]["scopes"].append("changed-in-the-copy")

    assert original == before
    assert original["claudeAiOauth"]["refreshToken"] == fake.CLAUDE_REFRESH


def test_stripping_a_credential_that_has_nothing_to_strip_is_not_an_error():
    leaf = fake.claude_leaf()
    del leaf["claudeAiOauth"]["refreshToken"]

    assert "refreshToken" not in CLAUDE_RELAY.strip(leaf)["claudeAiOauth"]


def test_the_form_of_the_copy_is_one_constant_and_it_alone_decides_it():
    """M2 may find that the CLI needs the key present: that is this one constant to change."""
    assert CLAUDE_FORM == (("refreshToken", None), ("refreshTokenExpiresAt", None))
    assert CLAUDE_RELAY.form == CLAUDE_FORM
    present = replace(CLAUDE_RELAY, form=(("refreshToken", ""),))

    body = present.strip(fake.claude_leaf())["claudeAiOauth"]

    assert body["refreshToken"] == ""
    assert body["refreshTokenExpiresAt"] == 1795348800000


# --- bootstrap and account -------------------------------------------------------------------


def test_the_relay_profile_holds_the_account_object_and_nothing_else_of_the_real_one(tmp_path):
    home = fake.claude_home(tmp_path)

    found = bootstrapped(home)

    assert list(found) == [".claude.json"]
    assert json.loads(found[".claude.json"]) == {"oauthAccount": ACCOUNT}
    for must_not_travel in (b"cachedGrowthBookFeatures", b"mcpServers", b"projects",
                            b"primaryApiKey", b"fake-claude-primary-api-key",
                            b"fake-command-that-must-not-travel", b"numStartups"):
        assert must_not_travel not in found[".claude.json"]


@pytest.mark.parametrize("name,profile", [
    ("no oauthAccount", {"numStartups": 1}),
    ("oauthAccount not an object", {"oauthAccount": ["accountUuid"]}),
    ("no accountUuid", {"oauthAccount": {"organizationUuid": "org"}}),
    ("empty accountUuid", {"oauthAccount": {"accountUuid": "", "organizationUuid": "org"}}),
    ("accountUuid not text", {"oauthAccount": {"accountUuid": 5, "organizationUuid": "org"}}),
    ("no organizationUuid", {"oauthAccount": {"accountUuid": "acc"}}),
    ("empty organizationUuid", {"oauthAccount": {"accountUuid": "acc", "organizationUuid": ""}}),
])
def test_a_profile_that_does_not_name_the_account_is_refused(tmp_path, name, profile):
    home = fake.claude_home(tmp_path, profile=profile)

    assert CLAUDE_RELAY.bootstrap(home) == Refused("account_unknown")


def test_a_login_with_no_profile_or_a_broken_one_has_no_known_account(tmp_path):
    home = fake.claude_home(tmp_path)
    (home / ".claude.json").write_text('{"oauthAccount": ', encoding="utf-8")
    assert CLAUDE_RELAY.bootstrap(home) == Refused("account_unknown")

    (home / ".claude.json").unlink()
    assert CLAUDE_RELAY.bootstrap(home) == Refused("account_unknown")


def test_the_profile_may_be_far_larger_than_a_credential_but_not_without_a_bound(tmp_path):
    """A real `.claude.json` is large (projects, history); the bound is 4 MiB, not 64 KiB."""
    assert login_relay.PROFILE_LIMIT == 4 * 1024 * 1024
    big = fake.claude_profile(projects={"p": "x" * (1024 * 1024)})
    huge = fake.claude_profile(projects={"p": "x" * (4 * 1024 * 1024)})

    assert list(bootstrapped(fake.claude_home(tmp_path / "a", profile=big))) == [
        ".claude.json"]
    assert CLAUDE_RELAY.bootstrap(fake.claude_home(tmp_path / "b", profile=huge)) == Refused(
        "account_unknown")


def test_observed_plain_values_are_carried_and_known_nested_flags_are_not(tmp_path):
    """Only measured names/types are admitted; nested flags keep their explicit omission."""
    account = {**fake.claude_profile()["oauthAccount"],
               "hasExtraUsageEnabled": True, "profileFetchedAt": 3, "billingType": "stripe",
               "ccOnboardingFlags": {"token": "fake-nested-value-must-not-travel"}}
    home = fake.claude_home(tmp_path, profile=fake.claude_profile(oauthAccount=account))

    found = bootstrapped(home)

    assert json.loads(found[".claude.json"]) == {"oauthAccount": {
        **ACCOUNT, "hasExtraUsageEnabled": True, "profileFetchedAt": 3, "billingType": "stripe"}}
    assert b"must-not-travel" not in found[".claude.json"]


def test_an_object_nested_far_below_the_account_is_left_out_and_does_not_fail_the_reading(tmp_path):
    deep: object = "fake-bottom-value-must-not-travel"
    for _ in range(200):
        deep = {"x": deep}
    account = {**fake.claude_profile()["oauthAccount"], "ccOnboardingFlags": deep}
    home = fake.claude_home(tmp_path, profile=fake.claude_profile(oauthAccount=account))

    found = bootstrapped(home)

    assert json.loads(found[".claude.json"]) == {"oauthAccount": ACCOUNT}


def test_the_account_is_the_account_uuid_of_what_the_copy_is_made_of(tmp_path):
    material = bootstrapped(fake.claude_home(tmp_path))

    assert CLAUDE_RELAY.account(fake.claude_leaf(), material) == fake.CLAUDE_ACCOUNT


@pytest.mark.parametrize("material", [
    {}, {".credentials.json": b"{}"}, {".claude.json": b'{"oauthAccount": '},
    {".claude.json": b"[]"}, {".claude.json": b"{}"}, {".claude.json": b'{"oauthAccount": 5}'},
    {".claude.json": b'{"oauthAccount": {"accountUuid": 5}}'},
    {".claude.json": b'{"oauthAccount": {"accountUuid": ""}}'}])
def test_an_account_that_cannot_be_read_from_the_copy_is_none_not_an_error(material):
    assert CLAUDE_RELAY.account(fake.claude_leaf(), material) is None


# --- expires_at ------------------------------------------------------------------------------


def test_the_expiry_is_the_access_token_expiry_in_milliseconds():
    assert CLAUDE_RELAY.expires_at(fake.claude_leaf()) == EXPIRY


def test_the_refresh_token_expiry_is_not_the_expiry_of_what_the_child_is_given():
    soon = with_oauth(refreshTokenExpiresAt=1)
    assert CLAUDE_RELAY.expires_at(soon) == EXPIRY
    leaf = fake.claude_leaf()
    del leaf["claudeAiOauth"]["expiresAt"]
    assert CLAUDE_RELAY.expires_at(leaf) is None


@pytest.mark.parametrize("value", ["soon", 1.5, True, None, 0, -1, 10 ** 20, [1]])
def test_an_expiry_that_is_not_a_plausible_instant_is_unknown(value):
    assert CLAUDE_RELAY.expires_at(with_oauth(expiresAt=value)) is None


# --- the credential manager ------------------------------------------------------------------


def credman_profile(on, where="cachedGrowthBookFeatures"):
    return fake.claude_profile(**{where: {"tengu_windows_credman": on}})


def test_a_profile_that_does_not_turn_the_credential_manager_on_is_not_refused(tmp_path):
    assert CLAUDE_RELAY.credman_refusal(fake.claude_home(tmp_path)) is None
    home = fake.claude_home(tmp_path / "b", profile={"numStartups": 1})
    assert CLAUDE_RELAY.credman_refusal(home) is None
    home = fake.claude_home(tmp_path / "c", profile=credman_profile("true"))
    assert CLAUDE_RELAY.credman_refusal(home) is None, "only the boolean true turns it on"


def test_the_profile_turning_the_credential_manager_on_is_refused(tmp_path):
    home = fake.claude_home(tmp_path, profile=credman_profile(True))

    assert CLAUDE_RELAY.credman_refusal(home) == "credman"


def test_the_config_file_turning_it_on_is_refused_though_the_profile_says_off(tmp_path):
    home = fake.claude_home(tmp_path)
    fake.put(home, ".config.json", credman_profile(True))

    assert CLAUDE_RELAY.credman_refusal(home) == "credman"


def test_either_file_turning_it_on_refuses_whichever_the_vendor_reads_first(tmp_path):
    home = fake.claude_home(tmp_path, profile=credman_profile(True))
    fake.put(home, ".config.json", credman_profile(False))

    assert CLAUDE_RELAY.credman_refusal(home) == "credman"


@pytest.mark.parametrize("name", [".config.json", ".claude.json"])
def test_a_file_that_may_say_it_but_cannot_be_read_is_refused_by_its_own_code(tmp_path, name):
    home = fake.claude_home(tmp_path)
    (home / name).write_text('{"cachedGrowthBookFeatures": ', encoding="utf-8")

    assert CLAUDE_RELAY.credman_refusal(home) == "credman_unknown"


def test_no_profile_and_no_config_cannot_turn_it_on(tmp_path):
    home = fake.claude_home(tmp_path)
    (home / ".claude.json").unlink()

    assert CLAUDE_RELAY.credman_refusal(home) is None


def test_readiness_refuses_a_login_whose_refresh_would_go_to_the_credential_manager(tmp_path):
    home = fake.claude_home(tmp_path, profile=credman_profile(True))

    found = ready(home, CLAUDE_RELAY, fake.NOW, timedelta(minutes=40))

    assert found == Refused("credman")


def test_readiness_refuses_a_login_whose_account_cannot_be_named(tmp_path):
    home = fake.claude_home(tmp_path, profile={"numStartups": 1})

    found = ready(home, CLAUDE_RELAY, fake.NOW, timedelta(minutes=40))

    assert found == Refused("account_unknown")
