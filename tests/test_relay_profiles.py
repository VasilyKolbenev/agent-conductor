"""The relay spec a profile carries: declared facts, kept coherent, and part of what a grant binds.

A profile is code, and `ProviderAuthority` freezes it as canonical JSON into the digest an approved
plan is bound to (`policy_providers`), so a profile that carries a relay spec must stay plain data
to that reader: a spec whose fields were functions would break every digest of a Claude or a Codex
run at once. The behaviour lives in methods and the declaration in fields, and the fields are what a
grant binds: a changed form of the copy is a changed digest and an old grant is refused.

Claude Code, Codex and Grok Build declare a relay; DeepSeek and Kimi Code do not. The shared
full-mode fixtures below cover Claude and Codex; Grok has its own relay and activation tests.
"""
from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from conductor.command.adapters.claude_code import (
    CLAUDE_PROFILE, CLAUDE_PROTOCOL, CLAUDE_PROVIDER_ID, ClaudeCodeTransport)
from conductor.command.adapters.claude_relay import CLAUDE_RELAY
from conductor.command.adapters.codex_cli import (
    CODEX_PROFILE, CODEX_PROTOCOL, CODEX_PROVIDER_ID, CodexCliTransport)
from conductor.command.adapters.codex_relay import CODEX_RELAY
from conductor.command.adapters.dsh_harness import DSH_PROFILE
from conductor.command.adapters.grok_build import GROK_PROFILE
from conductor.command.adapters.grok_relay import GROK_RELAY
from conductor.command.adapters.harness_profile import HeadlessCliError
from conductor.command.adapters.kimi_code import KIMI_PROFILE
from conductor.command.adapters.login_relay import RelaySpec
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.adapters.relay_home import HOME_NAME
from conductor.command.policy_providers import ProviderAuthority
from conductor.command.providers import resolve_providers
from tests.test_command_claude_transport import _Ids, _executable as claude_executable
from tests.test_command_codex_transport import _executable as codex_executable

RELAYED = {"claude": (CLAUDE_PROFILE, CLAUDE_RELAY), "codex": (CODEX_PROFILE, CODEX_RELAY)}


def test_only_the_three_subscription_harnesses_declare_a_relay():
    assert CLAUDE_PROFILE.login_relay is CLAUDE_RELAY
    assert CODEX_PROFILE.login_relay is CODEX_RELAY
    assert GROK_PROFILE.login_relay is GROK_RELAY
    assert (DSH_PROFILE.login_relay, KIMI_PROFILE.login_relay) == (None, None)


def test_the_declared_facts_of_the_claude_relay():
    assert (CLAUDE_RELAY.kind, CLAUDE_RELAY.credential) == ("c", ".credentials.json")
    assert CLAUDE_RELAY.files == (".credentials.json", ".claude.json")
    assert CLAUDE_RELAY.secret_fields == ("accessToken", "refreshToken")
    assert CLAUDE_RELAY.refresh_fields == ("refreshToken", "refreshTokenExpiresAt")
    assert CLAUDE_RELAY.section == "claudeAiOauth"


def test_the_declared_facts_of_the_codex_relay():
    assert (CODEX_RELAY.kind, CODEX_RELAY.credential) == ("x", "auth.json")
    assert CODEX_RELAY.files == ("auth.json",)
    assert CODEX_RELAY.secret_fields == (
        "id_token", "access_token", "refresh_token", "OPENAI_API_KEY")
    assert CODEX_RELAY.refresh_fields == ("refresh_token",)
    assert CODEX_RELAY.section == "tokens"


@pytest.mark.parametrize("which", sorted(RELAYED))
def test_the_credential_a_relay_copies_is_one_the_leak_scan_already_reads(which):
    profile, spec = RELAYED[which]

    assert spec.credential in profile.login_credentials


def test_the_codex_leak_scan_also_reads_the_tool_server_credentials_it_does_not_copy():
    assert CODEX_PROFILE.login_credentials == ("auth.json", ".credentials.json")
    assert ".credentials.json" not in CODEX_PROFILE.login_forbidden
    assert ".credentials.json" not in CODEX_RELAY.files


@pytest.mark.parametrize("which", sorted(RELAYED))
def test_the_kind_is_a_letter_the_relay_home_shape_accepts_and_the_two_differ(which):
    _profile, spec = RELAYED[which]

    assert HOME_NAME.fullmatch(f"{spec.kind}-0123456789abcdef") is not None
    assert CLAUDE_RELAY.kind != CODEX_RELAY.kind


def an_authority(tmp_path, which):
    """The real `ProviderAuthority` over the real registry of one harness (over its fake binary).

    This is the reader that freezes a profile into the digest a grant is bound to: the tests below
    go through it and do not repeat what it does.
    """
    executable, provider_id, protocol = {
        "claude": (claude_executable, CLAUDE_PROVIDER_ID, CLAUDE_PROTOCOL),
        "codex": (codex_executable, CODEX_PROVIDER_ID, CODEX_PROTOCOL)}[which]
    root = tmp_path / "root"
    root.mkdir()
    config = ProviderConfig(provider_id=provider_id, executable=str(executable(tmp_path)),
                            protocol=protocol)
    resolution = resolve_providers(
        [config], root=root, clock=lambda: "2026-08-22T12:00:00Z", ids=_Ids(), environ={},
        confine_platform=None)
    authority = ProviderAuthority([config], resolution.contracts, resolution.registry)
    return authority, {"instances": [{"id": "doer", "adapter": provider_id}]}


@pytest.mark.parametrize("which", sorted(RELAYED))
def test_the_spec_is_plain_data_to_the_reader_that_freezes_a_profile_into_a_grant(
        tmp_path, which):
    profile, spec = RELAYED[which]
    authority, run_config = an_authority(tmp_path, which)

    facts = authority.facts(run_config)["providers"][0]["transport"]["login_relay"]

    assert facts["kind"] == spec.kind and facts["credential"] == spec.credential
    assert tuple(facts["files"]) == spec.files
    assert tuple(tuple(row) for row in facts["form"]) == spec.form
    assert authority.digest(run_config).startswith("sha256:")
    assert '"login_relay": {' in json.dumps(asdict(profile), sort_keys=True, allow_nan=False)


@pytest.mark.parametrize("which", sorted(RELAYED))
def test_a_relay_is_part_of_what_a_grant_binds(tmp_path, monkeypatch, which):
    profile, spec = RELAYED[which]
    authority, run_config = an_authority(tmp_path, which)
    transport = {"claude": ClaudeCodeTransport, "codex": CodexCliTransport}[which]
    with_relay = authority.digest(run_config)

    monkeypatch.setattr(transport, "profile", replace(profile, login_relay=None))
    bare = authority.digest(run_config)
    monkeypatch.setattr(transport, "profile", replace(
        profile, login_relay=replace(spec, form=())))
    changed = authority.digest(run_config)

    assert len({with_relay, bare, changed}) == 3, "a changed relay did not change the digest"


@pytest.mark.parametrize("which", sorted(RELAYED))
def test_a_profile_without_its_relay_is_still_a_valid_profile(which):
    profile, _spec = RELAYED[which]

    assert replace(profile, login_relay=None).login_relay is None


def test_a_profile_refuses_a_relay_that_is_not_one():
    with pytest.raises(HeadlessCliError):
        replace(CLAUDE_PROFILE, login_relay="a spec, as text")


def test_a_profile_refuses_a_relay_whose_credential_the_leak_scan_does_not_read():
    elsewhere = replace(CLAUDE_RELAY, credential="other.json", files=("other.json",))

    with pytest.raises(HeadlessCliError):
        replace(CLAUDE_PROFILE, login_relay=elsewhere)


def test_a_spec_is_an_abstract_base_that_cannot_be_used_whole():
    with pytest.raises(TypeError):
        RelaySpec(kind="c", credential="x.json", files=("x.json",), secret_fields=(),
                  refresh_fields=(), section="s", form=(), forbidden_env=())


@pytest.mark.parametrize("change", [
    {"kind": "cc"}, {"kind": "C"}, {"kind": ""}, {"kind": "1"},
    {"files": (".claude.json",)},
    {"files": (".credentials.json", "sub/dir.json")},
    {"files": (".credentials.json", "..")},
    {"credential": "../x.json"},
    {"form": (("accessToken", None),)},
    {"form": (("refreshToken", 5),)},
    {"form": ("refreshToken",)},
    {"section": ""},
    {"secret_fields": ("accessToken", "accessToken")},
    {"forbidden_env": ("not a name",)},
])
def test_a_spec_that_contradicts_itself_cannot_be_made(change):
    with pytest.raises(ValueError):
        replace(CLAUDE_RELAY, **change)
