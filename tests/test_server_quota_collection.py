"""Production provider resolution -> owned collector -> real cache-only HTTP.

Only the transport fetch is replaced with a controlled synthetic response. The
DSH capture, private plan, source policy, cache and HTTP serialization are real.
No provider executable runs and no credential or external endpoint is contacted.
"""
from datetime import datetime, timezone
import json
from threading import Event, Thread

import pytest

from conductor import server
from conductor.command.adapters.dsh_harness import (
    BALANCE_ENDPOINT, BALANCE_SOURCE_VERSION, DEFAULT_API_KEY_ENV, DSH_PROTOCOL)
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers
from conductor.quota_collectors import QuotaCollector
from tests.test_command_http_api import TOKEN, ids
from tests.test_quota_collectors import balance
from tests.test_server_quota_http import request
from tests.test_store import good_lane, write_project


AT = datetime(2026, 9, 21, 14, tzinfo=timezone.utc)
NOW = "2026-09-21T14:00:00Z"
SECRET = "synthetic-server-quota-capture"
WAIT = 10


class QuotaHost:
    def __init__(self, tmp_path, monkeypatch, *, payload, key=True):
        root = write_project(tmp_path, lanes={"claude": good_lane()})
        executable, entrypoint = root / "node.exe", root / "bin.js"
        executable.write_bytes(b"")
        entrypoint.write_bytes(b"")
        config = ProviderConfig("deepseek-harness", str(executable), DSH_PROTOCOL,
            env_allow=(DEFAULT_API_KEY_ENV,), entrypoint=str(entrypoint))
        self.entered, self.release, self.published = Event(), Event(), Event()
        self.calls, self.resolutions, self.collectors = [], [], []
        self.payload = payload
        self._install(monkeypatch, key)
        self.subject = server.build(root, 0, providers=(config,), clock=lambda: NOW,
                                    ids=ids(), token_factory=lambda _: TOKEN)
        self.thread = Thread(target=self.subject.serve_forever, daemon=True)
        self.thread.start()

    def _install(self, monkeypatch, key):
        def resolved(configs, **kwargs):
            value = resolve_providers(configs, **kwargs,
                environ={DEFAULT_API_KEY_ENV: SECRET} if key else {})
            self.resolutions.append(value)
            return value

        def collect(service, plans, **kwargs):
            original = service.publish
            def published(*args, **named):
                result = original(*args, **named)
                self.published.set()
                return result
            monkeypatch.setattr(service, "publish", published)
            collector = QuotaCollector(service, plans, fetch=self.fetch, **kwargs)
            self.collectors.append(collector)
            return collector

        monkeypatch.setattr(server, "resolve_providers", resolved)
        monkeypatch.setattr(server, "QuotaCollector", collect)
        monkeypatch.setattr(ProcessRunner, "run",
            lambda *a, **kw: pytest.fail("quota startup must not launch a harness"))

    def fetch(self, endpoint, bearer):
        self.calls.append((endpoint, bearer))
        self.entered.set()
        assert self.release.wait(WAIT), "controlled fetch was not released"
        return self.payload

    def read(self):
        status, body, headers = request(self.subject)
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert SECRET not in json.dumps(body)
        assert "connection" not in json.dumps(body)
        matches = [row for row in body["snapshots"] if "deepseek-harness" in row["binding_ids"]]
        assert len(matches) == 1
        return matches[0]

    def close(self):
        self.release.set()
        self.subject.shutdown()
        self.subject.server_close()
        self.thread.join(WAIT)
        assert not self.thread.is_alive()
        assert all(not collector.running for collector in self.collectors)
        assert self.subject.command_execution.owned_tokens() == ()


@pytest.mark.parametrize("payload,expected", [
    (balance("1234567890.1234567890"), "observed"),
    ({"is_available": "private-invalid-" + SECRET, "balance_infos": []}, "error"),
], ids=["exact-decimal", "invalid-source"])
def test_real_server_uses_the_dispatch_capture_and_get_never_refreshes_it(
        tmp_path, monkeypatch, payload, expected):
    host = QuotaHost(tmp_path, monkeypatch, payload=payload)
    try:
        assert host.entered.wait(WAIT)
        assert host.read()["state"] == "missing"
        assert host.read()["state"] == "missing"
        assert host.calls == [(BALANCE_ENDPOINT, SECRET)]
        plan = host.resolutions[0].quota_plans[0]
        adapter = host.subject.command_registry.resolve("deepseek-harness")
        assert adapter.quota_connection() == plan.request
        assert plan.source.version == BALANCE_SOURCE_VERSION
        host.release.set()
        assert host.published.wait(WAIT)
        row = host.read()
        assert row["state"] == expected and row["freshness"] == "current"
        assert row["account"] is None and row["account_status"] == "unknown"
        assert row["source"]["version"] == BALANCE_SOURCE_VERSION
        assert row["reset_applicability"] == "not_applicable"
        if expected == "observed":
            assert row["balances"][0]["total_balance"] == "1234567890.1234567890"
            assert row["is_available"] is True
        else:
            assert row["reason"] == "malformed_payload" and row["balances"] == []
        assert host.calls == [(BALANCE_ENDPOINT, SECRET)]
    finally:
        host.close()


def test_real_server_missing_key_keeps_data_unavailable_without_polling(tmp_path, monkeypatch):
    host = QuotaHost(tmp_path, monkeypatch, payload=balance(), key=False)
    try:
        row = host.read()
        assert row["state"] == "missing" and row["freshness"] == "missing"
        assert row["account"] is None and row["account_status"] == "unknown"
        assert host.calls == [] and not host.collectors[0].running
        assert host.resolutions[0].quota_plans[0].reason == "no_data"
    finally:
        host.close()
