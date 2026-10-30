"""Fake file witnesses for Grok's inactive subscription relay; no vendor is called."""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone

import pytest

from conductor.command.adapters.grok_relay import GROK_RELAY
from conductor.command.adapters.login_relay import (
    Ready, Refused, Ticket, copy_in, discard, ready_for)

SCOPE = "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828"
NOW = "2026-10-30T12:00:00Z"
ACCESS = "fake-grok-access-0123456789"
REFRESH = "fake-grok-refresh-9876543210"
ABSENT = object()


def _document(**changes):
    body = {
        "auth_mode": "oidc", "key": ACCESS, "refresh_token": REFRESH,
        "user_id": "fake-account-123", "expires_at": "2026-10-30T18:00:00Z",
        "oidc_issuer": "https://auth.x.ai",
        "oidc_client_id": "b1a00492-073a-47ea-816f-4c329264a828",
        "email": "fake@example.invalid", "has_grok_code_access": True,
    }
    for name, value in changes.items():
        if value is ABSENT:
            body.pop(name, None)
        else:
            body[name] = value
    return {SCOPE: body}


def _source(tmp_path, document):
    home = tmp_path / "login"
    home.mkdir()
    data = json.dumps(document, ensure_ascii=False).encode("utf-8")
    (home / "auth.json").write_bytes(data)
    return home, data


def test_copy_is_access_only_and_child_edits_and_discard_never_write_back(tmp_path):
    original = _document(first_name="Test")
    login, data = _source(tmp_path, original)
    config = b'marketplace = "fake-executable-config"\n'
    (login / "config.toml").write_bytes(config)
    relay = tmp_path / "attempt"
    relay.mkdir()

    ready = ready_for(login, GROK_RELAY, NOW, 600)
    assert isinstance(ready, Ready)
    assert ready.account == "fake-account-123"
    ticket = copy_in(login, relay, GROK_RELAY, ready.digest)
    assert isinstance(ticket, Ticket)
    assert ticket.account == "fake-account-123"
    assert sorted(path.name for path in relay.iterdir()) == ["auth.json"]
    copied = json.loads((relay / "auth.json").read_bytes())
    expected = copy.deepcopy(original)
    del expected[SCOPE]["refresh_token"]
    assert copied == expected
    assert REFRESH.encode() not in (relay / "auth.json").read_bytes()
    assert (login / "auth.json").read_bytes() == data

    copied[SCOPE]["key"] = "fake-child-replacement"
    copied[SCOPE]["refresh_token"] = "fake-child-refresh"
    (relay / "auth.json").write_text(json.dumps(copied), encoding="utf-8")
    (relay / "config.toml").write_text("fake child config", encoding="utf-8")
    assert (login / "auth.json").read_bytes() == data
    assert discard(relay, GROK_RELAY.files)
    assert not relay.exists()
    assert (login / "auth.json").read_bytes() == data
    assert (login / "config.toml").read_bytes() == config


@pytest.mark.parametrize("refresh", [ABSENT, None, "", REFRESH])
def test_optional_refresh_is_removed_in_every_admitted_form(tmp_path, refresh):
    document = _document(refresh_token=refresh)
    login, before = _source(tmp_path, document)
    relay = tmp_path / "attempt"
    relay.mkdir()
    ready = ready_for(login, GROK_RELAY, NOW, 600)
    assert isinstance(ready, Ready)
    assert isinstance(copy_in(login, relay, GROK_RELAY, ready.digest), Ticket)
    expected = copy.deepcopy(document)
    expected[SCOPE].pop("refresh_token", None)
    assert json.loads((relay / "auth.json").read_bytes()) == expected
    assert (login / "auth.json").read_bytes() == before


@pytest.mark.parametrize("document,code", [
    ({}, "unknown_shape"),
    ({"foreign::scope": _document()[SCOPE]}, "unknown_shape"),
    ({**_document(), "foreign::scope": {}}, "unknown_shape"),
    ({SCOPE: []}, "unknown_shape"),
    (_document(extra="not-known"), "unknown_shape"),
    (_document(auth_mode="api_key"), "api_key"),
    (_document(auth_mode="other"), "foreign_credentials"),
    (_document(auth_mode=ABSENT), "foreign_credentials"),
    (_document(auth_mode=5), "foreign_credentials"),
    (_document(key=ABSENT), "no_access_token"),
    (_document(key=""), "no_access_token"),
    (_document(key=5), "no_access_token"),
    (_document(key=None), "no_access_token"),
    (_document(refresh_token=5), "unknown_shape"),
    (_document(expires_at=5), "unknown_shape"),
    (_document(oidc_issuer=5), "unknown_shape"),
    (_document(oidc_client_id=None), "unknown_shape"),
    (_document(user_id=ABSENT), "account_unknown"),
    (_document(user_id=""), "account_unknown"),
    (_document(user_id=5), "account_unknown"),
    (_document(user_id=None), "account_unknown"),
])
def test_invalid_credentials_refuse_before_copying(tmp_path, document, code):
    login, before = _source(tmp_path, document)
    assert ready_for(login, GROK_RELAY, NOW, 600) == Refused(code)
    relay = tmp_path / "attempt"
    relay.mkdir()
    assert copy_in(login, relay, GROK_RELAY, "unused") == Refused(code)
    assert list(relay.iterdir()) == []
    assert (login / "auth.json").read_bytes() == before


@pytest.mark.parametrize("changes", [
    {"oidc_issuer": "https://foreign.invalid"},
    {"oidc_client_id": "foreign-client"},
    {"oidc_issuer": "https://foreign.invalid", "oidc_client_id": ABSENT},
    {"oidc_issuer": ABSENT, "oidc_client_id": "foreign-client"},
])
def test_each_present_route_field_must_match_even_without_its_partner(tmp_path, changes):
    login, _before = _source(tmp_path, _document(**changes))
    assert ready_for(login, GROK_RELAY, NOW, 600) == Refused("unknown_shape")


@pytest.mark.parametrize("changes", [
    {"oidc_issuer": "https://auth.x.ai/"},
    {"oidc_issuer": ABSENT}, {"oidc_client_id": ABSENT},
    {"oidc_issuer": ABSENT, "oidc_client_id": ABSENT},
])
def test_matching_or_absent_optional_route_fields_are_preserved(tmp_path, changes):
    document = _document(**changes)
    login, _before = _source(tmp_path, document)
    relay = tmp_path / "attempt"
    relay.mkdir()
    ready = ready_for(login, GROK_RELAY, NOW, 600)
    assert isinstance(ready, Ready)
    assert isinstance(copy_in(login, relay, GROK_RELAY, ready.digest), Ticket)
    expected = copy.deepcopy(document)
    del expected[SCOPE]["refresh_token"]
    assert json.loads((relay / "auth.json").read_bytes()) == expected


@pytest.mark.parametrize("expiry,code", [
    (ABSENT, "expiry_unknown"), ("not-a-time", "expiry_unknown"),
    ("2026-10-30T18:00:00", "expiry_unknown"),
    ("2026-10-30T11:00:00Z", "expiry_short"),
    ("2026-10-30T12:19:59.999999Z", "expiry_short"),
])
def test_expiry_must_cover_the_step_and_margin(tmp_path, expiry, code):
    login, before = _source(tmp_path, _document(expires_at=expiry))
    assert ready_for(login, GROK_RELAY, NOW, 600) == Refused(code)
    assert (login / "auth.json").read_bytes() == before


@pytest.mark.parametrize("expiry", [
    "2026-10-30T12:20:00Z", "2026-10-30T15:20:00+03:00",
    "2026-10-30T12:20:00.000000000Z",
])
def test_exact_expiry_horizon_is_accepted_but_next_step_rechecks(tmp_path, expiry):
    login, _before = _source(tmp_path, _document(expires_at=expiry))
    ready = ready_for(login, GROK_RELAY, NOW, 600)
    assert isinstance(ready, Ready)
    assert ready.expires_at == datetime(2026, 10, 30, 12, 20, tzinfo=timezone.utc)
    assert ready_for(login, GROK_RELAY, "2026-10-30T12:00:01Z", 600) == Refused("expiry_short")


def test_changed_source_is_not_copied_or_overwritten(tmp_path):
    login, _before = _source(tmp_path, _document())
    ready = ready_for(login, GROK_RELAY, NOW, 600)
    assert isinstance(ready, Ready)
    changed = json.dumps(_document(user_id="fake-other-account")).encode()
    (login / "auth.json").write_bytes(changed)
    relay = tmp_path / "attempt"
    relay.mkdir()
    assert copy_in(login, relay, GROK_RELAY, ready.digest) == Refused("changed")
    assert list(relay.iterdir()) == []
    assert (login / "auth.json").read_bytes() == changed


def test_nonempty_relay_is_never_overwritten(tmp_path):
    login, before = _source(tmp_path, _document())
    ready = ready_for(login, GROK_RELAY, NOW, 600)
    assert isinstance(ready, Ready)
    relay = tmp_path / "attempt"
    relay.mkdir()
    (relay / "auth.json").write_bytes(b"do not overwrite")
    assert copy_in(login, relay, GROK_RELAY, ready.digest) == Refused("not_empty")
    assert (relay / "auth.json").read_bytes() == b"do not overwrite"
    assert (login / "auth.json").read_bytes() == before


def test_refresh_hidden_in_a_retained_field_is_refused_without_writing(tmp_path):
    login, before = _source(tmp_path, _document(email=REFRESH))
    ready = ready_for(login, GROK_RELAY, NOW, 600)
    assert isinstance(ready, Ready)
    relay = tmp_path / "attempt"
    relay.mkdir()
    assert copy_in(login, relay, GROK_RELAY, ready.digest) == Refused("refresh_leak")
    assert list(relay.iterdir()) == []
    assert (login / "auth.json").read_bytes() == before


def test_forbidden_prefixes_are_serialized_and_each_spec_uses_its_own_rules():
    assert asdict(GROK_RELAY)["forbidden_prefixes"] == (
        "GROK_TRACE_UPLOAD_", "GROK_INTERNAL_OTLP_")
    for name in ("GROK_TRACE_UPLOAD_NEW", "grok_internal_otlp_future", "GROK_AUTH_PATH"):
        assert GROK_RELAY.forbids(name)
    custom = replace(GROK_RELAY, forbidden_env=("ONLY_NAME",), forbidden_prefixes=("ONLY_PREFIX_",))
    assert custom.forbids("only_name")
    assert custom.forbids("only_prefix_future")
    assert not custom.forbids("GROK_TRACE_UPLOAD_NEW")
    assert not custom.forbids("GROK_AUTH_PATH")
    assert not custom.forbids("ONLY_PREFIX")
