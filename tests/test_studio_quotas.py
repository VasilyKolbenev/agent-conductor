"""Execute quota value/queue boundaries against production cache projections."""
from __future__ import annotations

from datetime import timedelta
import json
import shutil
import subprocess

import pytest

from conductor.command.quota import CredentialContext, QuotaObservation, QuotaSource, QuotaWindow
from conductor.command.quota_service import QuotaService
from conductor.command.quota_views import DEFAULT_QUOTA_MAX_AGE, QuotaView
from tests.test_command_quota import AT, SOURCE, account, parsed
from tests.test_command_quota_routes import catalog, contracts, get, quota_api
from tests.test_quota_connection import BALANCE, observed
from tests.test_studio_source import DOM_FORMS, PANEL, TRANSPORT, _code

EXACT = "123456789012345678901234567890.12345678901234567890"
NAMES = ("codex-cli", "codex-alias", "dsh-a", "dsh-b", "missing", "failed")
MARKUP = '<img src=x onerror="throw 1">'
MONEY_SOURCE = QuotaSource(BALANCE, MARKUP)


def quota_seed():
    cache = QuotaService()
    for name in NAMES[:2]:
        ticket = cache.bind(name, account(), SOURCE)
        cache.publish(ticket, parsed(0), now=AT)
    contexts = {}
    for name in NAMES[2:4]:
        context = CredentialContext.create(BALANCE)
        ticket = cache.bind(name, None, MONEY_SOURCE, connection=context)
        cache.publish(ticket, observed(context, total=EXACT, version=MARKUP), now=AT)
        contexts[name] = (ticket, context)
    identity = account(native="failed-account")
    ticket = cache.bind("failed", identity, SOURCE)
    cache.publish(ticket, QuotaObservation(identity, SOURCE, AT, "error", reason="source_error"), now=AT)
    return cache, contexts


def quota_payload(*, at=AT):
    cache, _ = quota_seed()
    return QuotaView(cache, DEFAULT_QUOTA_MAX_AGE).payload(contracts(*NAMES), at.isoformat())


def _js(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute the Studio quota modules")
    source = (f"import * as quota from {json.dumps((PANEL / 'studio-quotas-model.js').as_uri())};\n"
              f"import {{quotaFlow}} from {json.dumps((PANEL / 'studio-quotaflow.js').as_uri())};\n"
              f"import {{EMPTY, reduce}} from {json.dumps((PANEL / 'studio-store.js').as_uri())};\n" + body)
    result = subprocess.run([node, "--input-type=module", "-e", source],
                            capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_real_quota_projection_preserves_every_catalog_entry(tmp_path):
    payload = QuotaView(None, DEFAULT_QUOTA_MAX_AGE).payload(catalog(tmp_path), AT.isoformat())
    assert len(payload["providers"]) == len(payload["snapshots"]) == 5
    assert _js(f"console.log(JSON.stringify(quota.projectQuotas({json.dumps(payload)}))); ") == payload


@pytest.mark.parametrize("at", [AT, AT + timedelta(minutes=5), AT - timedelta(seconds=1)])
def test_native_projection_retains_zero_money_unknown_isolation_and_freshness(at):
    payload = quota_payload(at=at)
    got = _js(f"console.log(JSON.stringify(quota.projectQuotas({json.dumps(payload)}))); ")
    assert got == payload
    assert got["snapshots"][0]["binding_ids"] == list(NAMES[:2])
    assert got["snapshots"][0]["windows"][0]["used_percent"] == 0
    assert got["snapshots"][0]["windows"][0]["remaining_percent"] == 100
    money = [row for row in got["snapshots"] if "balances" in row]
    assert len(money) == 2
    assert all(row["balances"][0]["total_balance"] == EXACT for row in money)
    assert all(row["is_available"] is False and row["account_status"] == "unknown" for row in money)
    assert "connection" not in json.dumps(got)


@pytest.mark.parametrize("tiny_window", [False, True])
def test_real_api_microsecond_facts_survive_without_a_javascript_clock_judgement(tmp_path, tiny_window):
    cache = QuotaService()
    ticket = cache.bind("codex-cli", account(), SOURCE)
    micro = AT + timedelta(microseconds=1)
    reset = micro + timedelta(microseconds=1) if tiny_window else AT + timedelta(hours=1)
    observed_at = AT if tiny_window else micro
    now = AT if tiny_window else AT + timedelta(minutes=5)
    reading = QuotaObservation(account(), SOURCE, observed_at, "observed",
                               (QuotaWindow("codex", "micro", 0, reset, starts_at=micro),))
    assert cache.publish(ticket, reading, now=now)
    api = quota_api(tmp_path, service=cache, providers=contracts("codex-cli"), clock=lambda: now.isoformat())
    payload = get(api).payload
    assert payload["snapshots"][0]["freshness"] == "current"
    assert _js(f"console.log(JSON.stringify(quota.projectQuotas({json.dumps(payload)}))); ") == payload


@pytest.mark.parametrize("path,value", [
    (("connection",), {"context_id": "private"}),
    (("as_of",), "2026-02-30T12:00:00Z"), (("max_age_seconds",), True),
    (("snapshots", 1, "connection"), {"context_id": "private"}),
    (("snapshots", 1, "account_status"), "verified"),
    (("snapshots", 0, "account", "account_digest"), "sha256:" + "a" * 64),
    (("snapshots", 0, "account", "account_digest"), "A" * 64),
    (("snapshots", 0, "account", "account_digest"), "a" * 63),
    (("snapshots", 1, "binding_ids"), ["dsh-a", "dsh-b"]),
    (("snapshots", 0, "binding_ids"), ["codex-cli", "unknown"]),
    (("snapshots", 1, "is_available"), "false"),
    (("snapshots", 1, "balances", 0, "total_balance"), 0),
    (("snapshots", 1, "balances", 0, "total_balance"), "1e3"),
    (("snapshots", 1, "balances", 0, "total_balance"), "-1"),
    (("snapshots", 1, "balances", 0, "currency"), "usd"),
    (("snapshots", 1, "resets_at"), "2026-09-22T12:00:00Z"),
    (("snapshots", 0, "windows", 0, "remaining_percent"), 0),
    (("snapshots", 0, "windows", 0, "used_percent"), False),
    (("snapshots", 0, "windows", 0, "freshness"), "stale"),
    (("snapshots", 0, "freshness"), "stale"),
    (("snapshots", 0, "windows", 0, "freshness"), "reset_passed"),
    (("snapshots", 0, "deferred_at"), "2026-02-30T12:00:00Z"),
    (("snapshots", 0, "deferred_at"), 5),
    (("snapshots", 3, "deferred_at"), "2026-09-21T12:00:00Z"),
    (("snapshots", 4, "reason"), "secret failure body"),
    (("providers", 0, "provider_id"), "dsh-a"),
])
def test_malformed_or_inconsistent_quota_payload_is_refused_whole(path, value):
    payload = quota_payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert _js(f"console.log(JSON.stringify(quota.projectQuotas({json.dumps(payload)}))); ") is None


def test_quota_updates_are_detached_and_preserve_human_state():
    body = f"""
    const payload = {json.dumps(quota_payload())};
    let state = reduce(EMPTY, {{type:'task-edit',patch:{{taskId:'task-one',title:'Keep this'}}}});
    state = reduce(state, {{type:'status',notice:'My pending decision'}});
    const before = state;
    state = reduce(state, {{type:'quotas-loaded',payload}});
    payload.snapshots[1].balances[0].total_balance = '999';
    const facts = state.quotas.payload;
    state = reduce(state, {{type:'quotas-phase',phase:'failed'}});
    console.log(JSON.stringify([state.tasks === before.tasks, state.workflows === before.workflows,
      state.runs === before.runs, state.decisions === before.decisions, state.notice === before.notice,
      facts.snapshots[1].balances[0].total_balance, state.quotas.payload === facts,
      Object.isFrozen(facts.snapshots[1].balances[0])]));
    """
    assert _js(body) == [True, True, True, True, True, EXACT, True, True]


FLOW = """
const pending = [], events = [], scheduled = new Map();
let enabled = true, next = 0, active = 0, maxActive = 0, aborted = 0;
const flow = quotaFlow({enabled:()=>enabled, dispatch:event=>events.push(event),
  stop:()=>({abort:()=>aborted++}), cancel:id=>scheduled.delete(id),
  schedule:fn=>{scheduled.set(++next,fn); return next;},
  read:(path,stop)=>{if(path !== '/command/quotas') throw Error('foreign path');
    active++; maxActive=Math.max(active,maxActive);
    return new Promise((resolve,reject)=>pending.push({
      resolve:value=>{active--;resolve(value);}, reject:()=>{active--;reject(Error('lost'));}}));}});
const tick = async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();};
"""


def test_many_refreshes_coalesce_and_old_reply_never_lands():
    body = FLOW + """
    flow.refreshQuotas();
    for(let i=0;i<50;i++) flow.refreshQuotas();
    const first = pending.length;
    pending[0].resolve({value:'old'}); await tick();
    const second = pending.length;
    pending[1].resolve({value:'new'}); await tick();
    console.log(JSON.stringify([first,second,maxActive,
      events.filter(e=>e.type==='quotas-loaded').map(e=>e.payload.value),scheduled.size]));
    """
    assert _js(body) == [1, 2, 1, ["new"], 1]


def test_disconnect_reconnect_and_timer_disposal_retire_old_answers():
    body = FLOW + """
    flow.refreshQuotas(); enabled=false; flow.disconnectQuotas();
    enabled=true; flow.syncQuotas(); pending[0].resolve({value:'before drop'}); await tick();
    pending[1].resolve({value:'after reconnect'}); await tick();
    const timer=[...scheduled.values()][0]; enabled=false; flow.syncQuotas(); timer();
    const hiddenCount=pending.length;
    enabled=true; flow.syncQuotas(); pending[2].reject(); await tick();
    const retry=[...scheduled.values()][0]; flow.disposeQuotas(); retry(); await tick();
    console.log(JSON.stringify([maxActive,aborted,hiddenCount,pending.length,scheduled.size,
      events.filter(e=>e.type==='quotas-loaded').map(e=>e.payload.value),events.at(-1).phase]));
    """
    assert _js(body) == [1, 1, 2, 3, 0, ["after reconnect"], "failed"]


def test_timer_uses_same_serial_read_door_after_a_failure():
    body = FLOW + """
    flow.refreshQuotas(); pending[0].reject(); await tick();
    const timer=[...scheduled.values()][0]; timer();
    pending[1].resolve({value:'recovered'}); await tick();
    console.log(JSON.stringify([pending.length,maxActive,scheduled.size,events.at(-1).payload.value]));
    """
    assert _js(body) == [2, 1, 1, "recovered"]


def test_quota_model_and_flow_reach_no_dom_or_network():
    for name in ("studio-quotas-model.js", "studio-quotaflow.js"):
        source = _code(PANEL / name).lower()
        for forbidden in DOM_FORMS + TRANSPORT:
            assert forbidden not in source, (name, forbidden)
