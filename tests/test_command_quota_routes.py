"""Quota HTTP reads preserve cached facts without invoking a collector or a run."""
from __future__ import annotations

from datetime import timedelta
import json
import socket
import subprocess

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.api_contracts import ApiRefusal
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.providers import resolve_providers
from conductor.command.quota import CredentialContext, QuotaObservation
from conductor.command.quota_service import QuotaService
from conductor.command.run_store import RunStore

from tests.test_command_http_api import PORT, TOKEN, get_headers, ids
from tests.test_command_provider_contract import _contract
from tests.test_command_quota import AT, SOURCE, account, parsed
from tests.test_quota_connection import BALANCE, SOURCE as MONEY_SOURCE, observed


NOW = AT.isoformat().replace("+00:00", "Z")
PATH = "/command/quotas"


def catalog(tmp_path):
    return resolve_providers((), root=tmp_path, clock=lambda: NOW, ids=ids()).contracts


def contracts(*names):
    return tuple(_contract(provider_id=name, display_name="Same visible label") for name in names)


def quota_api(tmp_path, *, service=None, providers=None, clock=lambda: NOW, **options):
    return CommandApi(
        RunStore(tmp_path), AdapterRegistry(), session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=clock, ids=ids(), publish_run=lambda _: None,
        providers=catalog(tmp_path) if providers is None else providers,
        quota_service=service, **options)


def get(subject, *, path=PATH, headers=None, body=b""):
    return subject.handle("GET", path, get_headers() if headers is None else headers, body)


def bind_quota(cache, binding="codex-cli", *, identity=None, value=25):
    identity = account() if identity is None else identity
    ticket = cache.bind(binding, identity, SOURCE)
    cache.publish(ticket, parsed(value, identity=identity), now=AT)
    return ticket


def test_default_cache_shows_every_catalog_provider_even_when_unconfigured(tmp_path, monkeypatch):
    subject = quota_api(tmp_path)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    def forbidden(*args, **kwargs):
        raise AssertionError("a quota GET crossed an execution or network boundary")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subject._store, "read", forbidden)
    monkeypatch.setattr(subject._service, "propose", forbidden)
    body = get(subject).payload
    expected = {row.provider_id for row in catalog(tmp_path)}
    assert len(expected) == 5
    assert {row["provider_id"] for row in body["providers"]} == expected
    assert {tuple(row["binding_ids"]) for row in body["snapshots"]} == {(name,) for name in expected}
    assert all(row["availability"] == "unconfigured" for row in body["providers"])
    assert all(row["state"] == "missing" and row["reason"] == "no_data"
               and row["freshness"] == "missing" and row["account"] is None
               and row["account_status"] == "unknown" and row["source"] is None
               and row["windows"] == [] for row in body["snapshots"])
    assert body["as_of"] == NOW and body["max_age_seconds"] == 300
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")) == before


def test_confirmed_accounts_group_only_selected_bindings_without_summing(tmp_path):
    cache = QuotaService()
    for name in ("first", "alias", "hidden"):
        bind_quota(cache, name)
    bind_quota(cache, "other", identity=account(native="other-account"), value=70)
    subject = quota_api(tmp_path, service=cache, providers=contracts("first", "alias", "other"))
    result = get(subject)
    assert result.status == 200
    rows = result.payload["snapshots"]
    assert [row["binding_ids"] for row in rows] == [["first", "alias"], ["other"]]
    assert [row["windows"][0]["remaining_percent"] for row in rows] == [75, 30]
    assert all(row["account_status"] == "verified" for row in rows)
    assert rows[0]["account"]["account_digest"] != rows[1]["account"]["account_digest"]
    assert "hidden" not in json.dumps(result.payload)


def test_unknown_connections_remain_two_rows_without_exposing_uuid_or_account_claim(tmp_path):
    cache = QuotaService()
    contexts = [CredentialContext.create(BALANCE), CredentialContext.create(BALANCE)]
    exact = "12345678901234567890.12345678901234567890"
    for name, context in zip(("one", "two"), contexts):
        ticket = cache.bind(name, None, MONEY_SOURCE, connection=context)
        cache.publish(ticket, observed(context, total=exact), now=AT)
    body = get(quota_api(tmp_path, service=cache, providers=contracts("one", "two"))).payload
    assert [row["binding_ids"] for row in body["snapshots"]] == [["one"], ["two"]]
    for row in body["snapshots"]:
        assert row["account"] is None and row["account_status"] == "unknown"
        assert row["balances"][0]["total_balance"] == exact
        assert row["balances"][0]["currency"] == "CNY"
        assert row["is_available"] is False and row["windows"] == []
        assert row["resets_at"] is None and row["reset_applicability"] == "not_applicable"
        assert row["source"] == {"kind": MONEY_SOURCE.kind, "version": MONEY_SOURCE.version}
    serialized = json.dumps(body)
    assert all(context.context_id not in serialized for context in contexts)
    assert all(name not in serialized for name in ("connection", "account_digest", "verified_by"))


def test_http_freshness_uses_each_clock_read_and_never_resets_cached_usage(tmp_path):
    cache = QuotaService()
    bind_quota(cache, "one")
    clock = [AT]
    subject = quota_api(tmp_path, service=cache, providers=contracts("one"),
                        clock=lambda: clock[0].isoformat(), quota_max_age=timedelta(hours=3))
    first = get(subject).payload
    original_window = dict(first["snapshots"][0]["windows"][0])
    assert first["snapshots"][0]["freshness"] == "current"
    clock[0] = AT + timedelta(hours=2)
    stale = get(subject).payload["snapshots"][0]
    assert stale["freshness"] == "stale" and stale["windows"][0]["freshness"] == "reset_passed"
    assert {**stale["windows"][0], "freshness": "current"} == original_window
    first["snapshots"][0]["windows"][0]["used_percent"] = 0
    first["providers"][0]["display_name"] = "mutated response"
    assert get(subject).payload["snapshots"][0]["windows"][0]["used_percent"] == 25
    assert get(subject).payload["providers"][0]["display_name"] == "Same visible label"
    clock[0] = AT - timedelta(seconds=1)
    assert get(subject).payload["snapshots"][0]["freshness"] == "stale"


def test_new_error_and_rebinding_replace_success_without_any_get_collection(tmp_path, monkeypatch):
    cache = QuotaService()
    ticket = bind_quota(cache, "one")
    at = AT + timedelta(seconds=1)
    failed = QuotaObservation(account(), SOURCE, at, "error", reason="source_error")
    assert cache.publish(ticket, failed, now=at)
    subject = quota_api(tmp_path, service=cache, providers=contracts("one"), clock=lambda: at.isoformat())
    def no_publish(*args, **kwargs):
        raise AssertionError("GET tried to change the cache")
    monkeypatch.setattr(cache, "publish", no_publish)
    monkeypatch.setattr(cache, "defer", no_publish)
    row = get(subject).payload["snapshots"][0]
    assert row["state"] == "error" and row["reason"] == "source_error" and row["windows"] == []
    assert row["freshness"] == "current"
    cache.bind("one", account(native="replacement"), SOURCE)
    missing = get(subject).payload["snapshots"][0]
    assert missing["state"] == "missing" and missing["windows"] == []
    assert missing["account"]["account_digest"] != row["account"]["account_digest"]


@pytest.mark.parametrize("path", [PATH + "?refresh=1", PATH + "?", PATH + "#", PATH + "/",
                                  PATH + "/refresh", PATH + "/one"])
def test_quota_read_has_no_query_alias_selector_or_refresh_path(tmp_path, path):
    result = get(quota_api(tmp_path), path=path)
    assert result.status == 404 and result.payload["error"]["code"] == "route_not_found"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_quota_route_is_get_only_before_mutation_authority(tmp_path, method):
    subject = quota_api(tmp_path)
    result = subject.handle(method, PATH, get_headers(), b'{"refresh":true}')
    assert result.status == 405 and result.payload["error"]["code"] == "method_not_allowed"
    with pytest.raises(ApiRefusal):
        subject.body_length(PATH, get_headers())


@pytest.mark.parametrize("headers,body", [
    (get_headers(), b"{}"),
    (get_headers() + (("Content-Length", "2"),), b""),
    (get_headers() + (("Content-Length", "0"),), b"{}"),
    (get_headers() + (("Content-Length", "0"), ("Content-Length", "0")), b""),
    (get_headers() + (("Transfer-Encoding", "chunked"),), b""),
    (get_headers() + (("Content-Length", "-1"),), b""),
])
def test_quota_get_refuses_body_or_ambiguous_framing_before_reading_cache(tmp_path, headers, body):
    result = get(quota_api(tmp_path), headers=headers, body=body)
    assert result.status == 400 and result.payload["error"]["code"] == "malformed_request"


@pytest.mark.parametrize("headers", [(), (("Host", "attacker.test"),),
                                   get_headers() + get_headers()])
def test_quota_read_keeps_exact_host_guard(tmp_path, headers):
    result = get(quota_api(tmp_path), headers=headers)
    assert result.status == 403 and result.payload["error"]["code"] == "same_origin_denied"


def test_explicit_zero_length_is_bodyless_and_constructor_rejects_noncache(tmp_path):
    result = get(quota_api(tmp_path), headers=get_headers() + (("Content-Length", "0"),))
    assert result.status == 200
    with pytest.raises(TypeError, match="QuotaService"):
        quota_api(tmp_path, service=object())
    with pytest.raises(TypeError, match="positive timedelta"):
        quota_api(tmp_path, quota_max_age=timedelta(0))


def test_corrupt_cached_observation_is_refused_without_its_fields(tmp_path):
    cache = QuotaService()
    bind_quota(cache, "one")
    stored = next(iter(cache._latest.values()))
    object.__setattr__(stored, "reason", "private-native-error-marker")
    result = get(quota_api(tmp_path, service=cache, providers=contracts("one")))
    assert result.status == 409 and result.payload["error"]["code"] == "service_refused"
    assert "private-native-error-marker" not in json.dumps(result.payload)
