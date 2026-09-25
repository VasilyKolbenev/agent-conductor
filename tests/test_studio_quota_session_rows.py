"""The Studio must read the subscription row production really emits.

The collector binds every live source without a verified account: a subscription
harness arrives with ``account: null`` and one binding. Refusing that row voids
the whole payload, the money rows of other providers included.
"""
from __future__ import annotations

import json

from conductor.command.adapters.codex_cli import QUOTA_POLICY
from conductor.command.quota import QuotaObservation, QuotaSource, SessionContext, parse_observation
from conductor.command.quota_service import QuotaService
from conductor.command.quota_views import DEFAULT_QUOTA_MAX_AGE, QuotaView
from tests.test_command_quota_routes import contracts
from tests.test_studio_quotas import _js
from tests.test_subscription_quota import AT, PAYLOAD

SOURCE = QuotaSource(QUOTA_POLICY, "0.112.0")


def _payload(observe, *names):
    context, cache = SessionContext.create(QUOTA_POLICY), QuotaService()
    ticket = cache.bind("codex-cli", None, SOURCE, connection=context)
    assert cache.publish(ticket, observe(context), now=AT)
    return QuotaView(cache, DEFAULT_QUOTA_MAX_AGE).payload(
        contracts("codex-cli", *names), AT.isoformat())


def _projected(payload):
    return _js(f"console.log(JSON.stringify(quota.projectQuotas({json.dumps(payload)})));")


def test_session_bound_subscription_reading_reaches_the_studio():
    payload = _payload(lambda context: parse_observation(
        PAYLOAD, policy=QUOTA_POLICY, version="0.112.0", observed_at=AT, connection=context))
    row = payload["snapshots"][0]
    assert row["account"] is None and row["state"] == "observed" and row["windows"]
    assert _projected(payload) == payload


def test_session_bound_subscription_failure_reaches_the_studio():
    payload = _payload(lambda context: QuotaObservation(
        None, SOURCE, AT, "error", reason="not_authenticated", connection=context))
    row = payload["snapshots"][0]
    assert row["account"] is None and row["state"] == "error" and row["windows"] == []
    assert _projected(payload) == payload


def test_an_unknown_account_reading_is_still_never_grouped():
    payload = _payload(lambda context: parse_observation(
        PAYLOAD, policy=QUOTA_POLICY, version="0.112.0", observed_at=AT,
        connection=context), "codex-alias")
    assert _projected(payload) == payload, "control: the honest two-row payload is read"
    # One row claiming both bindings, nothing else wrong: only isolation can refuse it.
    observed = next(row for row in payload["snapshots"] if row["state"] == "observed")
    observed["binding_ids"] = ["codex-cli", "codex-alias"]
    payload["snapshots"] = [observed]
    assert _projected(payload) is None
