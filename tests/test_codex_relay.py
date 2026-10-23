"""The Codex relay: what the real `auth.json` must look like, and what an attempt is given of it.

Codex 0.112.0 keeps one subscription login in `auth.json`: a ChatGPT token set, and an API key
slot that must be empty (a file that holds a key answers "logged in" like a subscription does and
the key wins, so a run on it would be billed to an API account nobody pinned). The relay admits
that shape only.

The copy the child gets has no usable refresh token. The pinned CLI refuses a file that lacks the
`refresh_token` field altogether (measured by Codex on 23.10.2026: `missing field refresh_token`)
and reads one holding an empty string, so the relay writes the empty string and changes nothing
else: not `last_refresh`, not a deadline. Whether the CLI then WORKS on it is the live measurement
M2, not something this file can show.

The expiry is the `exp` of the access token, read from its JWT payload with no check of any
signature: it is a time and not a proof of anything, least of all of whose token it is.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from conductor.command.adapters.codex_relay import CODEX_FORM, CODEX_MCP_CREDENTIALS, CODEX_RELAY
from conductor.command.adapters.login_relay import jwt_expiry
from tests import relay_credentials as fake

EXPIRY = datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc)


def admit(doc):
    return CODEX_RELAY.admit(doc)


def leaf_with(**top):
    leaf = fake.codex_leaf()
    leaf.update(top)
    return leaf


# --- admit -----------------------------------------------------------------------------------


def test_a_full_chatgpt_login_is_admitted():
    assert admit(fake.codex_leaf()) is None


def test_a_login_with_no_last_refresh_is_admitted():
    leaf = fake.codex_leaf()
    del leaf["last_refresh"]

    assert admit(leaf) is None


def test_a_login_that_names_no_api_key_slot_at_all_is_admitted():
    leaf = fake.codex_leaf()
    del leaf["OPENAI_API_KEY"]

    assert admit(leaf) is None


def test_the_login_a_chatgpt_sign_in_writes_is_admitted_with_its_mode():
    """M1 (23.10.2026): the real file has `auth_mode`: `chatgpt`; one without it stays admitted."""
    assert admit(leaf_with(auth_mode="chatgpt")) is None
    assert admit(fake.codex_leaf()) is None


@pytest.mark.parametrize("mode", ["apikey", "ApiKey", "ChatGPT", "chatgpt ", "", "chatgpt\n"])
def test_a_login_mode_that_is_not_exactly_chatgpt_is_a_credential_this_build_does_not_copy(mode):
    assert admit(leaf_with(auth_mode=mode)) == "foreign_credentials"


@pytest.mark.parametrize("mode", [None, 5, 1.5, True, ["chatgpt"], {"mode": "chatgpt"}, b"chatgpt"])
def test_a_login_mode_that_is_not_text_is_not_a_known_shape(mode):
    assert admit(leaf_with(auth_mode=mode)) == "unknown_shape"


@pytest.mark.parametrize("mode", ["chatgpt", "apikey"])
def test_an_api_key_is_an_api_key_whatever_the_mode_says(mode):
    assert admit(leaf_with(auth_mode=mode, OPENAI_API_KEY=fake.CODEX_API_KEY)) == "api_key"


def test_the_mode_is_kept_by_the_copy_as_it_is():
    stripped = CODEX_RELAY.strip(leaf_with(auth_mode="chatgpt"))

    assert stripped["auth_mode"] == "chatgpt"
    assert stripped["tokens"]["refresh_token"] == ""


@pytest.mark.parametrize("extra", ["mcp_oauth", "plugins", "a_key_this_build_has_never_heard_of"])
def test_a_key_at_the_top_that_the_schema_does_not_name_is_foreign(extra):
    assert admit(leaf_with(**{extra: {"fake": "fake-value-0123456789"}})) == (
        "foreign_credentials")


@pytest.mark.parametrize("key", [fake.CODEX_API_KEY, "", "sk-fake-0123456789"])
def test_a_login_that_holds_an_api_key_is_not_a_subscription(key):
    assert admit(leaf_with(OPENAI_API_KEY=key)) == "api_key"


def test_a_file_that_holds_only_an_api_key_is_not_a_subscription():
    assert admit({"OPENAI_API_KEY": fake.CODEX_API_KEY}) == "api_key"


@pytest.mark.parametrize("tokens", [None, "text", ["access_token"], 5])
def test_tokens_that_are_not_an_object_are_not_a_known_shape(tokens):
    assert admit(leaf_with(tokens=tokens)) == "unknown_shape"


def test_a_key_among_the_tokens_that_the_schema_does_not_name_is_refused():
    assert admit(leaf_with(tokens={**fake.codex_leaf()["tokens"], "extra": "x"})) == (
        "unknown_shape")


@pytest.mark.parametrize("key,value", [
    ("id_token", 5), ("access_token", ["x"]), ("refresh_token", None), ("account_id", 7)])
def test_a_token_that_is_not_text_is_not_a_known_shape(key, value):
    tokens = {**fake.codex_leaf()["tokens"], key: value}

    assert admit(leaf_with(tokens=tokens)) == "unknown_shape"


def test_a_last_refresh_that_is_not_text_is_not_a_known_shape():
    assert admit(leaf_with(last_refresh=5)) == "unknown_shape"


def test_an_empty_or_missing_access_token_is_refused_by_its_own_code():
    tokens = dict(fake.codex_leaf()["tokens"])
    del tokens["access_token"]

    assert admit(leaf_with(tokens={**tokens, "access_token": ""})) == "no_access_token"
    assert admit(leaf_with(tokens=tokens)) == "no_access_token"


def test_a_login_with_no_account_id_cannot_name_its_account():
    tokens = dict(fake.codex_leaf()["tokens"])
    del tokens["account_id"]

    assert admit(leaf_with(tokens={**tokens, "account_id": ""})) == "account_unknown"
    assert admit(leaf_with(tokens=tokens)) == "account_unknown"


# --- strip -----------------------------------------------------------------------------------


def test_the_access_only_copy_has_an_empty_refresh_token_and_everything_else_as_it_was():
    real = fake.codex_leaf()

    stripped = CODEX_RELAY.strip(real)

    assert stripped == {
        "OPENAI_API_KEY": None,
        "tokens": {"id_token": real["tokens"]["id_token"],
                   "access_token": real["tokens"]["access_token"],
                   "refresh_token": "",
                   "account_id": "fake-codex-account-0001"},
        "last_refresh": "2026-10-23T11:00:00Z"}


def test_the_refresh_token_field_is_present_because_the_cli_needs_it():
    """Measured on 0.112.0 by the Codex review: the field absent is a refusal to read the file."""
    tokens = dict(fake.codex_leaf()["tokens"])
    del tokens["refresh_token"]

    assert CODEX_RELAY.strip(leaf_with(tokens=tokens))["tokens"]["refresh_token"] == ""


def test_stripping_copies_and_never_changes_the_document_it_was_given():
    original = fake.codex_leaf()
    before = copy.deepcopy(original)

    stripped = CODEX_RELAY.strip(original)
    stripped["tokens"]["account_id"] = "changed-in-the-copy"

    assert original == before
    assert original["tokens"]["refresh_token"] == fake.CODEX_REFRESH


def test_the_form_of_the_copy_is_one_constant_and_it_alone_decides_it():
    assert CODEX_FORM == (("refresh_token", ""),)
    assert CODEX_RELAY.form == CODEX_FORM
    dropped = replace(CODEX_RELAY, form=(("refresh_token", None),))

    assert "refresh_token" not in dropped.strip(fake.codex_leaf())["tokens"]


# --- bootstrap, account, the credential manager ----------------------------------------------


def test_nothing_but_the_credential_is_copied_whatever_the_real_home_holds(tmp_path):
    home = fake.codex_home(tmp_path)
    (home / "config.toml").write_text(
        '[projects."C:\\\\fake"]\ntrust_level = "trusted"\n', encoding="utf-8")
    fake.put(home, CODEX_MCP_CREDENTIALS,
             {"fake-mcp": {"access_token": "fake-mcp-token-0123456789"}})

    assert CODEX_RELAY.bootstrap(home) == {}


def test_the_account_is_the_account_id_of_the_admitted_credential_and_nothing_is_read_again():
    """The account comes from the document that was admitted, not from a second reading."""
    assert CODEX_RELAY.account(fake.codex_leaf(), {}) == fake.CODEX_ACCOUNT


@pytest.mark.parametrize("doc", [
    leaf_with(tokens={"account_id": 5}), leaf_with(tokens={"account_id": ""}),
    leaf_with(tokens={}), leaf_with(tokens=None), {}, {"tokens": "text"}])
def test_an_account_that_the_document_does_not_name_is_none_not_an_error(doc):
    assert CODEX_RELAY.account(doc, {}) is None


def test_there_is_no_credential_manager_to_refuse_on_this_harness(tmp_path):
    assert CODEX_RELAY.credman_refusal(fake.codex_home(tmp_path)) is None


def test_the_mcp_credential_file_has_a_name_and_is_not_one_the_relay_copies():
    assert CODEX_MCP_CREDENTIALS == ".credentials.json"
    assert CODEX_MCP_CREDENTIALS not in CODEX_RELAY.files
    assert CODEX_RELAY.credential not in (CODEX_MCP_CREDENTIALS,)


# --- expires_at ------------------------------------------------------------------------------


def test_the_expiry_is_the_exp_of_the_access_token_payload():
    assert CODEX_RELAY.expires_at(fake.codex_leaf()) == EXPIRY


def test_a_fractional_exp_is_an_instant_too():
    token = fake.jwt({"exp": 1792771200.5})

    assert jwt_expiry(token) == datetime(2026, 10, 23, 16, 0, 0, 500000, tzinfo=timezone.utc)


def test_the_signature_is_never_checked():
    token = fake.jwt({"exp": 1792771200}).rsplit(".", 1)[0] + ".not-the-signature"

    assert jwt_expiry(token) == EXPIRY


def test_the_other_tokens_of_the_login_say_nothing_about_the_expiry():
    soon = fake.codex_leaf(id_token=fake.jwt({"exp": 1}))

    assert CODEX_RELAY.expires_at(soon) == EXPIRY


@pytest.mark.parametrize("token", [
    "", "not-a-jwt", "a.b", "a.b.c.d", "..", "a..c",
    "aGVhZGVy.@@@@.c",
    f"aGVhZGVy.{fake.segment('a json string')}.c",
    f"aGVhZGVy.{fake.segment([1, 2])}.c",
    f"aGVhZGVy.{fake.segment({'sub': 'no exp'})}.c",
    "aGVhZGVy." + "bm90IGpzb24" + ".c",
    fake.jwt({"exp": "soon"}), fake.jwt({"exp": True}), fake.jwt({"exp": None}),
    fake.jwt({"exp": 0}), fake.jwt({"exp": -5}), fake.jwt({"exp": 10 ** 30}),
    fake.jwt({"exp": float("1e30")}),
])
def test_a_token_that_does_not_name_a_plausible_expiry_gives_none(token):
    assert jwt_expiry(token) is None


def test_the_credential_without_a_readable_token_has_no_known_expiry():
    assert CODEX_RELAY.expires_at(fake.codex_leaf(access_token="not-a-jwt")) is None
    assert CODEX_RELAY.expires_at({"tokens": "x"}) is None
    assert CODEX_RELAY.expires_at({}) is None
