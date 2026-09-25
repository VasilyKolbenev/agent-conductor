"""Real loopback quota GET with the production handler and an injected cache."""
from __future__ import annotations

import http.client
import json
import socket
import threading

import pytest

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import CommandApi
from conductor.command.quota import CredentialContext
from conductor.command.quota_service import QuotaService

from tests.test_command_http_api import TOKEN, ids
from tests.test_command_quota_routes import AT, NOW, PATH, bind_quota, contracts
from tests.test_quota_connection import BALANCE, SOURCE as MONEY_SOURCE, observed
from tests.test_store import good_lane, write_project


@pytest.fixture
def quota_server(tmp_path, monkeypatch):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    cache, calls = QuotaService(), []
    original_snapshots = cache.snapshots
    def snapshots(*args, **kwargs):
        calls.append(args[0])
        return original_snapshots(*args, **kwargs)
    def make_api(*args, **kwargs):
        kwargs.update(quota_service=cache, providers=contracts("one", "two"))
        return CommandApi(*args, **kwargs)
    monkeypatch.setattr(cache, "snapshots", snapshots)
    monkeypatch.setattr(server, "CommandApi", make_api)
    subject = server.build(root, 0, registry=AdapterRegistry(), clock=lambda: NOW,
                           ids=ids(), token_factory=lambda _: TOKEN)
    thread = threading.Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    try:
        yield subject, cache, calls
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def request(subject, method="GET", path=PATH, *, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", subject.server_address[1], timeout=5)
    try:
        connection.request(method, path, body=body, headers={} if headers is None else headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read()), dict(response.headers)
    finally:
        connection.close()


def raw_get(subject, headers):
    port = subject.server_address[1]
    head = (f"GET {PATH} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            + "".join(f"{name}: {value}\r\n" for name, value in headers)
            + "Connection: close\r\n\r\n")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall(head.encode("ascii"))
        connection.shutdown(socket.SHUT_WR)
        response = bytearray()
        while chunk := connection.recv(4096):
            response.extend(chunk)
    status, body = bytes(response).split(b"\r\n\r\n", 1)
    return int(status.split(b" ")[1]), json.loads(body)


def test_real_quota_read_is_no_store_cache_only_and_sees_later_published_observation(quota_server):
    subject, cache, calls = quota_server
    status, body, headers = request(subject)
    assert status == 200 and [row["state"] for row in body["snapshots"]] == ["missing", "missing"]
    assert headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in headers and "Access-Control-Allow-Origin" not in headers
    bind_quota(cache, "one", value=41)
    status, body, _ = request(subject)
    assert status == 200 and body["snapshots"][0]["windows"][0]["used_percent"] == 41
    assert body["snapshots"][1]["state"] == "missing"
    assert calls == [("one", "two"), ("one", "two")]


def test_real_http_keeps_unknown_balances_separate_without_context_identifiers(quota_server):
    subject, cache, calls = quota_server
    contexts = [CredentialContext.create(BALANCE), CredentialContext.create(BALANCE)]
    for name, context in zip(("one", "two"), contexts):
        ticket = cache.bind(name, None, MONEY_SOURCE, connection=context)
        cache.publish(ticket, observed(context, total="1234567890.1234567890"), now=AT)
    status, body, _ = request(subject)
    assert status == 200 and calls == [("one", "two")]
    assert [row["binding_ids"] for row in body["snapshots"]] == [["one"], ["two"]]
    assert all(row["account"] is None and row["account_status"] == "unknown"
               and row["balances"][0]["total_balance"] == "1234567890.1234567890"
               and row["reset_applicability"] == "not_applicable" for row in body["snapshots"])
    serialized = json.dumps(body)
    assert "connection" not in serialized and "account_digest" not in serialized
    assert all(context.context_id not in serialized for context in contexts)


@pytest.mark.parametrize("method,path,headers,expected", [
    ("POST", PATH, {}, 405),
    ("GET", PATH + "?refresh=1", {}, 404),
    ("GET", PATH + "?", {}, 404),
    ("GET", PATH + "/refresh", {}, 404),
    ("GET", PATH, {"Host": "attacker.test"}, 403),
])
def test_real_quota_invalid_routes_and_host_never_reach_cache(quota_server, method, path, headers, expected):
    subject, _cache, calls = quota_server
    assert request(subject, method, path, headers=headers)[0] == expected
    assert calls == []


def test_framed_get_body_is_refused_and_next_request_stays_aligned(quota_server):
    subject, _cache, calls = quota_server
    connection = http.client.HTTPConnection("127.0.0.1", subject.server_address[1], timeout=5)
    try:
        connection.request("GET", PATH, body=b'{"refresh":true}')
        refused = connection.getresponse()
        assert refused.status == 400
        assert json.loads(refused.read())["error"]["code"] == "malformed_request"
        assert calls == []
        connection.request("GET", "/command/session")
        accepted = connection.getresponse()
        assert accepted.status == 200 and json.loads(accepted.read())["csrf_token"] == TOKEN
    finally:
        connection.close()


@pytest.mark.parametrize("headers", [
    (("Content-Length", "0"), ("Content-Length", "0")),
    (("Transfer-Encoding", "chunked"),),
    (("Content-Length", "-1"),),
])
def test_real_quota_ambiguous_framing_is_refused_without_cache_read(quota_server, headers):
    subject, _cache, calls = quota_server
    status, body = raw_get(subject, headers)
    assert status == 400 and body["error"]["code"] == "malformed_request"
    assert calls == []
