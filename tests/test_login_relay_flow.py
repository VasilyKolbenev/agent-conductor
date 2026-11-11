"""`ready` and `copy_in`: the relay's content layer, driven through both harnesses.

What is proved here is what lands in the relay home and what does not, and every refusal is a
value: a login that is not ready, a file that changed between the look and the copy, a relay home
that is not empty and a write that failed all come back as a closed code and never raise, because
the caller refuses before anything is claimed and a raise inside the login lease would poison it.
Taking a relay home away again (`discard`, `sweep`) is `test_login_relay_discard`.

The relay documents the tests expect are spelled here by hand (the changed value, the dropped key),
and the values they share with the real login come from the fixture the real login was written
from. Nothing here asks the code under test what it ought to have written.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone

import pytest

from conductor.command.adapters import login_relay
from conductor.command.adapters.claude_relay import CLAUDE_RELAY
from conductor.command.adapters.codex_relay import CODEX_RELAY
from conductor.command.adapters.login_relay import Ready, Refused, Ticket, copy_in, ready
from tests import relay_credentials as fake
from tests.relay_fixtures import link

HORIZON = timedelta(minutes=40)
EXPIRY = datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc)
SPECS = {"claude": CLAUDE_RELAY, "codex": CODEX_RELAY}
KINDS = sorted(SPECS)
WRITTEN = {"claude": [".claude.json", ".credentials.json"], "codex": ["auth.json"]}


def real_home(kind, base, **kwargs):
    build = fake.claude_home if kind == "claude" else fake.codex_home
    return build(base, **kwargs)


def real_bytes(kind, home):
    return {name: (home / name).read_bytes() for name in WRITTEN[kind]
            if (home / name).is_file()}


def digest_of(kind, home):
    """The digest `ready` names for a home that is ready (what a caller holds to `copy_in`)."""
    found = ready(home, SPECS[kind], fake.NOW, HORIZON)
    assert isinstance(found, Ready), found
    return found.digest


def leaf_digest(kind, home):
    """SHA-256 of the credential file's bytes, spelled here and not asked of the code."""
    return hashlib.sha256((home / SPECS[kind].credential).read_bytes()).hexdigest()


def relay_leaf(kind, relay):
    return json.loads((relay / SPECS[kind].credential).read_text(encoding="utf-8"))


# --- ready -----------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_a_login_with_a_token_that_outlasts_the_horizon_is_ready(tmp_path, kind):
    home = real_home(kind, tmp_path)

    found = ready(home, SPECS[kind], fake.NOW, HORIZON)

    assert isinstance(found, Ready), found
    assert len(found.digest) == 64 and set(found.digest) <= set("0123456789abcdef")
    assert found.expires_at == EXPIRY
    assert found.account == {"claude": fake.CLAUDE_ACCOUNT, "codex": fake.CODEX_ACCOUNT}[kind]


def test_the_digest_of_a_login_with_no_other_file_is_the_digest_of_its_credential(tmp_path):
    home = real_home("codex", tmp_path)

    found = ready(home, CODEX_RELAY, fake.NOW, HORIZON)

    assert isinstance(found, Ready), found
    assert found.digest == leaf_digest("codex", home)


def test_the_digest_of_a_claude_login_binds_the_account_that_is_written_beside_the_credential(
        tmp_path):
    """The credential alone is not what the copy is made of: the account profile is, too."""
    home = real_home("claude", tmp_path)
    before = digest_of("claude", home)

    assert before != leaf_digest("claude", home)
    profile = json.loads((home / ".claude.json").read_text("utf-8"))
    profile["numStartups"] = 8  # a part of the profile that is never written to the relay
    fake.put(home, ".claude.json", profile)
    assert digest_of("claude", home) == before, "a change of what is not copied moved the digest"
    profile["oauthAccount"]["displayName"] = "Another Fake Person"
    fake.put(home, ".claude.json", profile)
    assert digest_of("claude", home) != before


def test_the_digest_binds_the_name_of_a_file_beside_the_credential_and_not_only_its_bytes(
        tmp_path):
    """The same bytes under another name are another copy: a spec with one file, named twice."""
    home = real_home("claude", tmp_path)
    parts = {field.name: getattr(CLAUDE_RELAY, field.name) for field in fields(CLAUDE_RELAY)}
    parts["files"] = (".credentials.json", "a.json", "b.json")

    def giving(name):
        @dataclass(frozen=True)
        class OneFile(type(CLAUDE_RELAY)):
            def bootstrap(self, real_home):
                return {name: b'{"same": "bytes"}'}

        return OneFile(**parts)

    under_a = ready(home, giving("a.json"), fake.NOW, HORIZON)
    under_b = ready(home, giving("b.json"), fake.NOW, HORIZON)

    assert isinstance(under_a, Ready) and isinstance(under_b, Ready), (under_a, under_b)
    assert under_a.digest != under_b.digest


@pytest.mark.parametrize("kind", KINDS)
def test_a_changed_credential_is_a_changed_digest(tmp_path, kind):
    home = real_home(kind, tmp_path)
    before = digest_of(kind, home)
    fake.put(home, SPECS[kind].credential,
             fake.claude_leaf(accessToken="fake-claude-access-token-CHANGED0000")
             if kind == "claude" else fake.codex_leaf(account_id="fake-codex-account-CHANGED"))

    assert digest_of(kind, home) != before


@pytest.mark.parametrize("kind", KINDS)
def test_no_repr_of_what_the_relay_returns_carries_a_secret(tmp_path, kind):
    """`Leaf`, `Ready` and `Ticket` hold real tokens for the leak scan and for nothing else."""
    tokens = fake.codex_leaf()["tokens"]
    secrets = {"claude": [fake.CLAUDE_ACCESS, fake.CLAUDE_REFRESH],
               "codex": [tokens["id_token"], tokens["access_token"], fake.CODEX_REFRESH]}[kind]
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    leaf = login_relay.read_leaf(home / SPECS[kind].credential)
    found = ready(home, SPECS[kind], fake.NOW, HORIZON)
    ticket = copy_in(home, relay, SPECS[kind], digest_of(kind, home))

    assert isinstance(leaf, login_relay.Leaf) and isinstance(found, Ready), (leaf, found)
    assert isinstance(ticket, Ticket), ticket
    assert found.secrets and ticket.secrets and leaf.doc, "the objects hold nothing to hide"
    for shown in (leaf, found, ticket):
        for text in (repr(shown), str(shown), f"{shown!r}", f"{shown}"):
            for secret in secrets:
                assert secret not in text, type(shown).__name__


@pytest.mark.parametrize("kind", KINDS)
def test_the_values_to_scan_for_are_every_secret_of_the_real_login(tmp_path, kind):
    """The scan must hold the refresh values too: the child could echo what it never received."""
    tokens = fake.codex_leaf()["tokens"]
    expected = {
        "claude": {fake.CLAUDE_ACCESS.encode(), fake.CLAUDE_REFRESH.encode()},
        "codex": {tokens["id_token"].encode(), tokens["access_token"].encode(),
                  fake.CODEX_REFRESH.encode()}}[kind]

    found = ready(real_home(kind, tmp_path), SPECS[kind], fake.NOW, HORIZON)

    assert isinstance(found, Ready), found
    assert set(found.secrets) == expected


@pytest.mark.parametrize("kind", KINDS)
def test_a_token_that_expires_exactly_at_the_horizon_is_enough_and_one_second_less_is_not(
        tmp_path, kind):
    home = real_home(kind, tmp_path)
    at_the_edge = EXPIRY - HORIZON

    assert isinstance(ready(home, SPECS[kind], at_the_edge, HORIZON), Ready)
    short = ready(home, SPECS[kind], at_the_edge + timedelta(seconds=1), HORIZON)
    assert short == Refused("expiry_short")


@pytest.mark.parametrize("kind", KINDS)
def test_a_token_that_has_already_expired_is_refused(tmp_path, kind):
    found = ready(real_home(kind, tmp_path), SPECS[kind], EXPIRY + timedelta(hours=1), HORIZON)

    assert found == Refused("expiry_short")


def test_a_claude_login_that_names_no_expiry_is_refused_not_assumed_fresh(tmp_path):
    leaf = fake.claude_leaf()
    del leaf["claudeAiOauth"]["expiresAt"]

    found = ready(real_home("claude", tmp_path, leaf=leaf), CLAUDE_RELAY, fake.NOW, HORIZON)

    assert found == Refused("expiry_unknown")


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b", fake.jwt({"sub": "no-exp"})])
def test_a_codex_login_whose_token_names_no_expiry_is_refused(tmp_path, token):
    leaf = fake.codex_leaf(access_token=token)

    found = ready(real_home("codex", tmp_path, leaf=leaf), CODEX_RELAY, fake.NOW, HORIZON)

    assert found == Refused("expiry_unknown")


@pytest.mark.parametrize("kind", KINDS)
def test_a_credential_file_that_is_not_there_is_refused_by_value(tmp_path, kind):
    (tmp_path / "empty").mkdir()

    assert ready(tmp_path / "empty", SPECS[kind], fake.NOW, HORIZON) == Refused("leaf_absent")
    assert ready(tmp_path / "no-such-folder", SPECS[kind], fake.NOW, HORIZON) == Refused(
        "leaf_absent")


@pytest.mark.parametrize("kind", KINDS)
def test_a_login_that_holds_anything_the_schema_does_not_name_is_refused(tmp_path, kind):
    leaf = fake.claude_leaf() if kind == "claude" else fake.codex_leaf()
    leaf["mcpOAuth"] = {"fake-server": {"accessToken": "fake-mcp-token-0123456789"}}

    found = ready(real_home(kind, tmp_path, leaf=leaf), SPECS[kind], fake.NOW, HORIZON)

    assert found == Refused("foreign_credentials")


@pytest.mark.parametrize("kind", KINDS)
def test_readiness_reads_and_writes_nothing_in_the_real_login(tmp_path, kind):
    home = real_home(kind, tmp_path)
    before = real_bytes(kind, home)
    names = sorted(path.name for path in home.iterdir())

    ready(home, SPECS[kind], fake.NOW, HORIZON)

    assert real_bytes(kind, home) == before
    assert sorted(path.name for path in home.iterdir()) == names


def test_a_naive_clock_is_a_fault_of_the_caller_and_is_not_guessed_at(tmp_path):
    with pytest.raises(ValueError):
        ready(real_home("claude", tmp_path), CLAUDE_RELAY, datetime(2026, 10, 23, 12, 0), HORIZON)


# --- copy_in ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_the_relay_home_holds_exactly_the_declared_files(tmp_path, kind):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    ticket = copy_in(home, relay, SPECS[kind], digest_of(kind, home))

    assert isinstance(ticket, Ticket), ticket
    assert fake.listing(relay) == WRITTEN[kind]
    assert sorted(ticket.names) == WRITTEN[kind]
    assert ticket.leaf == str(relay / SPECS[kind].credential)
    assert sorted(path.name for path in relay.iterdir()) == WRITTEN[kind]


def test_the_claude_relay_credential_has_no_refresh_token_and_no_refresh_expiry(tmp_path):
    home, relay = real_home("claude", tmp_path), fake.relay_home(tmp_path)

    found = copy_in(home, relay, CLAUDE_RELAY, digest_of("claude", home))

    assert isinstance(found, Ticket), found
    assert relay_leaf("claude", relay) == {"claudeAiOauth": {
        "accessToken": "fake-claude-access-token-AAAAAAAAAAAA",
        "expiresAt": 1792771200000,
        "scopes": ["user:inference", "user:profile"],
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_5x",
        "clientId": "fake-claude-client-id-0000"}}


def test_the_codex_relay_credential_carries_an_empty_refresh_token_and_changes_nothing_else(
        tmp_path):
    home, relay = real_home("codex", tmp_path), fake.relay_home(tmp_path)
    real = fake.codex_leaf()

    found = copy_in(home, relay, CODEX_RELAY, digest_of("codex", home))

    assert isinstance(found, Ticket), found
    assert relay_leaf("codex", relay) == {
        "OPENAI_API_KEY": None,
        "tokens": {"id_token": real["tokens"]["id_token"],
                   "access_token": real["tokens"]["access_token"],
                   "refresh_token": "",
                   "account_id": "fake-codex-account-0001"},
        "last_refresh": "2026-10-23T11:00:00Z"}


M1_CODEX = {**fake.codex_leaf(), "auth_mode": "chatgpt"}


def test_the_login_a_chatgpt_sign_in_really_writes_is_ready_and_copied_with_its_mode(tmp_path):
    """M1 (23.10.2026): the real `auth.json` has `auth_mode`: `chatgpt`, which a copy keeps."""
    home, relay = real_home("codex", tmp_path, leaf=M1_CODEX), fake.relay_home(tmp_path)
    real = fake.codex_leaf()

    found = ready(home, CODEX_RELAY, fake.NOW, HORIZON)
    assert isinstance(found, Ready), found
    ticket = copy_in(home, relay, CODEX_RELAY, found.digest)

    assert isinstance(ticket, Ticket), ticket
    assert relay_leaf("codex", relay) == {
        "OPENAI_API_KEY": None,
        "auth_mode": "chatgpt",
        "tokens": {"id_token": real["tokens"]["id_token"],
                   "access_token": real["tokens"]["access_token"],
                   "refresh_token": "",
                   "account_id": "fake-codex-account-0001"},
        "last_refresh": "2026-10-23T11:00:00Z"}
    assert fake.CODEX_REFRESH.encode() not in fake.all_bytes(relay)


@pytest.mark.parametrize("mode,code", [
    ("apikey", "foreign_credentials"), ("ChatGPT", "foreign_credentials"),
    ("", "foreign_credentials"), (" chatgpt", "foreign_credentials"),
    (None, "unknown_shape"), (5, "unknown_shape"), (True, "unknown_shape"),
    (["chatgpt"], "unknown_shape"), ({"mode": "chatgpt"}, "unknown_shape")])
def test_a_mode_that_is_not_chatgpt_is_refused_by_readiness_and_by_the_copy(tmp_path, mode, code):
    home, relay = real_home("codex", tmp_path, leaf=M1_CODEX), fake.relay_home(tmp_path)
    digest = digest_of("codex", home)
    fake.put(home, "auth.json", {**M1_CODEX, "auth_mode": mode})

    assert ready(home, CODEX_RELAY, fake.NOW, HORIZON) == Refused(code)
    assert copy_in(home, relay, CODEX_RELAY, digest) == Refused(code)
    assert list(relay.iterdir()) == []


def test_an_api_key_beside_the_chatgpt_mode_is_still_an_api_key(tmp_path):
    leaf = {**M1_CODEX, "OPENAI_API_KEY": fake.CODEX_API_KEY}
    home = real_home("codex", tmp_path, leaf=leaf)

    assert ready(home, CODEX_RELAY, fake.NOW, HORIZON) == Refused("api_key")


@pytest.mark.parametrize("kind,refresh", [
    ("claude", fake.CLAUDE_REFRESH), ("codex", fake.CODEX_REFRESH)])
def test_no_byte_of_the_real_refresh_token_reaches_the_relay_home(tmp_path, kind, refresh):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)

    assert isinstance(copy_in(home, relay, SPECS[kind], digest_of(kind, home)), Ticket)

    assert refresh.encode() in real_bytes(kind, home)[SPECS[kind].credential]
    assert refresh.encode() not in fake.all_bytes(relay)


@pytest.mark.parametrize("kind", KINDS)
def test_the_real_login_is_not_touched_by_a_copy(tmp_path, kind):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    before = real_bytes(kind, home)
    names = sorted(path.name for path in home.iterdir())

    assert isinstance(copy_in(home, relay, SPECS[kind], digest_of(kind, home)), Ticket)

    assert real_bytes(kind, home) == before
    assert sorted(path.name for path in home.iterdir()) == names


@pytest.mark.parametrize("kind", KINDS)
def test_the_values_to_scan_for_in_a_ticket_are_the_ones_the_relay_really_holds(tmp_path, kind):
    tokens = fake.codex_leaf()["tokens"]
    expected = {"claude": {fake.CLAUDE_ACCESS.encode()},
                "codex": {tokens["id_token"].encode(), tokens["access_token"].encode()}}[kind]
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)

    ticket = copy_in(home, relay, SPECS[kind], digest_of(kind, home))

    assert isinstance(ticket, Ticket), ticket
    assert set(ticket.secrets) == expected


@pytest.mark.parametrize("kind,account", [
    ("claude", fake.CLAUDE_ACCOUNT), ("codex", fake.CODEX_ACCOUNT)])
def test_the_ticket_names_the_account_that_was_written_and_it_is_the_one_readiness_named(
        tmp_path, kind, account):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    found = ready(home, SPECS[kind], fake.NOW, HORIZON)
    assert isinstance(found, Ready), found

    ticket = copy_in(home, relay, SPECS[kind], found.digest)

    assert isinstance(ticket, Ticket), ticket
    assert found.account == ticket.account == account
    if kind == "claude":
        written = json.loads((relay / ".claude.json").read_text("utf-8"))
        assert written["oauthAccount"]["accountUuid"] == ticket.account
    else:
        assert relay_leaf("codex", relay)["tokens"]["account_id"] == ticket.account


def test_a_profile_that_named_another_account_after_the_readiness_is_not_copied(tmp_path):
    """The credential is untouched; the account written beside it would be a different one."""
    home, relay = real_home("claude", tmp_path), fake.relay_home(tmp_path)
    digest = digest_of("claude", home)
    profile = json.loads((home / ".claude.json").read_text("utf-8"))
    profile["oauthAccount"]["accountUuid"] = "00000000-0000-4000-8000-0000000000ff"
    fake.put(home, ".claude.json", profile)

    assert copy_in(home, relay, CLAUDE_RELAY, digest) == Refused("changed")
    assert list(relay.iterdir()) == []


def test_a_nested_value_in_the_account_object_is_never_written_to_the_relay(tmp_path):
    home = real_home("claude", tmp_path)
    profile = json.loads((home / ".claude.json").read_text("utf-8"))
    profile["oauthAccount"].update({
        "hasExtraUsageEnabled": True, "billingType": "subscription",
        "ccOnboardingFlags": {"deep": {"token": "fake-nested-value-must-not-travel"},
                              "list": ["fake-listed-value-must-not-travel"]}})
    fake.put(home, ".claude.json", profile)
    relay = fake.relay_home(tmp_path)

    ticket = copy_in(home, relay, CLAUDE_RELAY, digest_of("claude", home))

    assert isinstance(ticket, Ticket), ticket
    account = json.loads((relay / ".claude.json").read_text("utf-8"))["oauthAccount"]
    assert account["hasExtraUsageEnabled"] is True and account["billingType"] == "subscription"
    assert account["accountUuid"] == fake.CLAUDE_ACCOUNT
    assert "ccOnboardingFlags" not in account
    assert b"must-not-travel" not in fake.all_bytes(relay)


@pytest.mark.parametrize("kind", KINDS)
def test_a_real_login_that_changed_after_the_readiness_is_refused_and_nothing_is_written(
        tmp_path, kind):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    digest = digest_of(kind, home)
    swapped = fake.claude_leaf(accessToken="fake-claude-access-token-CHANGED0000") \
        if kind == "claude" else fake.codex_leaf(account_id="fake-codex-account-CHANGED")
    fake.put(home, SPECS[kind].credential, swapped)

    assert copy_in(home, relay, SPECS[kind], digest) == Refused("changed")
    assert list(relay.iterdir()) == []


@pytest.mark.parametrize("kind", KINDS)
def test_a_change_of_spelling_alone_is_a_change(tmp_path, kind):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    digest = digest_of(kind, home)
    leaf = home / SPECS[kind].credential
    leaf.write_text(json.dumps(json.loads(leaf.read_text("utf-8")), indent=2), encoding="utf-8")

    assert copy_in(home, relay, SPECS[kind], digest) == Refused("changed")
    assert list(relay.iterdir()) == []


@pytest.mark.parametrize("kind", KINDS)
def test_a_digest_that_is_not_the_files_is_refused_whatever_the_file_holds(tmp_path, kind):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)

    assert copy_in(home, relay, SPECS[kind], "0" * 64) == Refused("changed")
    assert list(relay.iterdir()) == []


@pytest.mark.parametrize("kind", KINDS)
def test_a_real_login_that_disappeared_after_the_readiness_is_refused_by_its_own_code(
        tmp_path, kind):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    digest = digest_of(kind, home)
    (home / SPECS[kind].credential).unlink()

    assert copy_in(home, relay, SPECS[kind], digest) == Refused("leaf_absent")
    assert list(relay.iterdir()) == []


@pytest.mark.parametrize("kind", KINDS)
def test_a_login_that_became_foreign_is_refused_even_when_the_caller_names_its_digest(
        tmp_path, kind):
    """The copy does not trust that readiness was asked: it admits what it copies."""
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    digest = digest_of(kind, home)  # taken while the login was one the build admits
    leaf = json.loads((home / SPECS[kind].credential).read_text("utf-8"))
    leaf["pluginSecrets"] = {"fake": "fake-plugin-secret-0123456789"}
    fake.put(home, SPECS[kind].credential, leaf)

    found = copy_in(home, relay, SPECS[kind], digest)

    assert found == Refused("foreign_credentials")
    assert list(relay.iterdir()) == []


@pytest.mark.parametrize("kind", KINDS)
def test_a_relay_home_that_is_not_empty_is_refused_and_what_stands_there_is_left(tmp_path, kind):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    (relay / "left-by-someone").write_bytes(b"left")

    assert copy_in(home, relay, SPECS[kind], digest_of(kind, home)) == Refused("not_empty")
    assert [path.name for path in relay.iterdir()] == ["left-by-someone"]
    assert (relay / "left-by-someone").read_bytes() == b"left"


@pytest.mark.parametrize("kind", KINDS)
def test_a_relay_home_that_is_missing_or_not_a_folder_is_refused(tmp_path, kind):
    home = real_home(kind, tmp_path)
    digest = digest_of(kind, home)
    (tmp_path / "a-file").write_bytes(b"x")

    assert copy_in(home, tmp_path / "missing", SPECS[kind], digest) == Refused("relay_unusable")
    assert copy_in(home, tmp_path / "a-file", SPECS[kind], digest) == Refused("relay_unusable")
    assert (tmp_path / "a-file").read_bytes() == b"x"


@pytest.mark.parametrize("kind", KINDS)
def test_a_relay_home_that_is_a_link_is_refused_and_its_target_stays_empty(tmp_path, kind):
    home = real_home(kind, tmp_path)
    target = fake.relay_home(tmp_path, "elsewhere")
    link(tmp_path / "relay-link", target)

    found = copy_in(home, tmp_path / "relay-link", SPECS[kind], digest_of(kind, home))

    assert found == Refused("relay_unusable")
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("kind,failing", [("claude", 1), ("claude", 2), ("codex", 1)])
def test_a_write_that_fails_leaves_the_relay_home_empty_and_comes_back_as_a_value(
        tmp_path, monkeypatch, kind, failing):
    home, relay = real_home(kind, tmp_path), fake.relay_home(tmp_path)
    digest = digest_of(kind, home)
    real, seen = os.open, []

    def refuse_the_nth_creation(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:
            seen.append(os.fspath(path))
            if len(seen) == failing:
                raise OSError(errno.ENOSPC, "no space left on device")
        return real(path, flags, *args, **kwargs)

    monkeypatch.setattr(login_relay.os, "open", refuse_the_nth_creation)

    assert copy_in(home, relay, SPECS[kind], digest) == Refused("write_failed")
    assert len(seen) == failing
    assert list(relay.iterdir()) == []


@pytest.mark.parametrize("files", [
    {"other.json": b"{}"}, {".credentials.json": b"{}"}, {"../escape.json": b"{}"}])
def test_a_spec_that_bootstraps_a_file_it_did_not_declare_is_a_fault_and_writes_nothing(
        tmp_path, files):
    @dataclass(frozen=True)
    class Overreaching(type(CLAUDE_RELAY)):
        def bootstrap(self, real_home):
            return files

    spec = Overreaching(**{field.name: getattr(CLAUDE_RELAY, field.name)
                           for field in fields(CLAUDE_RELAY)})
    home, relay = real_home("claude", tmp_path), fake.relay_home(tmp_path)

    with pytest.raises(ValueError):
        copy_in(home, relay, spec, digest_of("claude", home))

    assert list(relay.iterdir()) == []
    assert not (tmp_path / "escape.json").exists()


def test_a_form_that_lets_a_real_refresh_value_through_is_refused_before_a_byte_is_written(
        tmp_path):
    """The refusal does not rest on the form being right: the real value is looked for."""
    @dataclass(frozen=True)
    class Leaky(type(CLAUDE_RELAY)):
        def strip(self, doc):
            return doc

    leaky = Leaky(**{field.name: getattr(CLAUDE_RELAY, field.name)
                     for field in fields(CLAUDE_RELAY)})
    home, relay = real_home("claude", tmp_path), fake.relay_home(tmp_path)

    found = copy_in(home, relay, leaky, digest_of("claude", home))

    assert found == Refused("refresh_leak")
    assert list(relay.iterdir()) == []


def test_a_refresh_value_found_in_the_account_object_is_refused_and_not_copied(tmp_path):
    """The profile is the vendor's file, and it is not trusted to be free of the secret."""
    home = real_home("claude", tmp_path)
    profile = json.loads((home / ".claude.json").read_text("utf-8"))
    profile["oauthAccount"]["displayName"] = fake.CLAUDE_REFRESH
    fake.put(home, ".claude.json", profile)
    relay = fake.relay_home(tmp_path)
    digest = digest_of("claude", home)

    assert copy_in(home, relay, CLAUDE_RELAY, digest) == Refused("refresh_leak")
    assert list(relay.iterdir()) == []


@pytest.mark.parametrize("refresh", [
    'fake-claude-refresh-"quoted"-0123456789',
    "fake-claude-refresh-back\\slash-0123456789",
    "fake-claude-refresh-éя-0123456789",
    "fake-claude-refresh-line\nbreak-0123456789"])
def test_a_leaked_refresh_value_is_found_in_the_spelling_json_writes_it_in(tmp_path, refresh):
    """The relay file is JSON: a value with a quote, a backslash or a non-ASCII letter is in its
    bytes as an escape, and a search for the raw text alone would not find it."""
    @dataclass(frozen=True)
    class Leaky(type(CLAUDE_RELAY)):
        def strip(self, doc):
            return doc

    leaky = Leaky(**{field.name: getattr(CLAUDE_RELAY, field.name)
                     for field in fields(CLAUDE_RELAY)})
    home = real_home("claude", tmp_path, leaf=fake.claude_leaf(refreshToken=refresh))
    relay = fake.relay_home(tmp_path)
    digest = digest_of("claude", home)
    assert refresh.encode("utf-8") not in (home / ".credentials.json").read_bytes(), (
        "the raw text stands in the file, so a raw search alone would find it and prove nothing")

    found = copy_in(home, relay, leaky, digest)

    assert found == Refused("refresh_leak")
    assert list(relay.iterdir()) == []
