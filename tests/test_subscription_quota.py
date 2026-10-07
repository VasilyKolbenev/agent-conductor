"""Native subscription read, account-unknown cache and fixed error boundaries."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from conductor.command.adapters.codex_cli import CodexCliTransport, QUOTA_POLICY, QUOTA_RPC, codex_pin
from conductor.command.adapters.dsh_harness import QUOTA_POLICY as BALANCE
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner
from conductor.command.adapters.quota_connection import NativeQuotaReader, NativeQuotaReadError
from conductor.command.quota import SessionContext, CredentialContext, QuotaError, QuotaSource, parse_observation
from conductor.command.quota_plans import quota_plan_for
from conductor.command.quota_service import QuotaService
from conductor.quota_collectors import QuotaCollector

AT = datetime(2026, 9, 21, 16, tzinfo=timezone.utc)
PAYLOAD = {'rateLimits':{'primary':{'usedPercent':27, 'windowDurationMins':300,
                                 'resetsAt':int(AT.timestamp())+3600}}}


def transcript(account='chatgpt', payload=None):
    return b'\n'.join(json.dumps(row).encode() for row in [
        {'id':1,'result':{'userAgent':'native'}},
        {'id':2,'result':{'account':{'type':account,'email':'private@example.invalid'}}},
        {'id':3,'result':PAYLOAD if payload is None else payload}]) + b'\n'


class ReaderRunner(ProcessRunner):
    def __init__(self, root, env):
        super().__init__(root, environ=env)
        self.specs = []
        self.payload = transcript()
    def run(self, spec):
        self.specs.append(spec)
        output = b'codex-cli 0.112.0' if spec.argv[-1] == '--version' else self.payload
        return ProcessOutcome('completed',0,output,False,spec.output_limit,0,'synthetic',
                              'delivered' if spec.stdin_bytes else 'not_provided')


def adapter(tmp_path, *, auth='subscription'):
    home = tmp_path / 'pinned-login'
    home.mkdir()
    environ = {'VISIBLE':'synthetic-selected','HIDDEN':'synthetic-excluded'}
    runner = ReaderRunner(tmp_path, environ)
    environ['VISIBLE'] = 'changed-after-runner'
    pin = codex_pin(str(tmp_path/'native.exe'), ('VISIBLE',), auth=auth,
                    auth_home=str(home) if auth=='subscription' else '')
    value = CodexCliTransport(pin, runner, root=tmp_path, clock=lambda:AT.isoformat(),
                             ids=lambda kind:kind+'-quota')
    return value, runner, home


def test_supplier_does_not_spawn_and_read_uses_dispatch_pin_environment_and_home(tmp_path):
    value, runner, home = adapter(tmp_path)
    plan = quota_plan_for('bound-provider', value)
    assert runner.specs == [] and type(plan.request) is NativeQuotaReader
    assert type(plan.connection) is SessionContext
    assert plan.request.read() == PAYLOAD
    assert len(runner.specs) == 2
    for spec in runner.specs:
        env = runner._child_env(spec)
        assert env['CODEX_HOME'] == str(home)
        assert env['VISIBLE'] == 'synthetic-selected' and 'HIDDEN' not in env
        assert spec.argv[0] == str(tmp_path/'native.exe')
    assert runner.specs[-1].stdin_completion_id == 3
    assert runner.specs[-1].separate_stderr and runner.specs[-1].timeout_seconds == 15
    assert value._login_seen == ()


def test_api_key_pin_never_polls_a_subscription_or_spawns(tmp_path):
    value, runner, _ = adapter(tmp_path, auth='api_key')
    plan = quota_plan_for('bound-provider', value)
    assert plan.reason == 'not_supported' and plan.connection is None and runner.specs == []


@pytest.mark.parametrize('raw', [b'', b'not-json\n', transcript()+transcript(),
    transcript().replace(b'"id": 2',b'"id": true'),
    transcript().replace(b'"id": 2',b'"id": 2, "id": 2'),
    transcript().replace(b'"result": {"userAgent": "native"}',b'"result": {}, "error": {}'),
    transcript().splitlines()[0]+b'\n'+transcript().splitlines()[2]+b'\n'])
def test_protocol_refuses_missing_duplicate_malformed_or_ambiguous_replies(raw):
    with pytest.raises(NativeQuotaReadError):
        QUOTA_RPC.decode(raw)


def test_auth_refusal_does_not_echo_email_error_or_claim_zero(tmp_path):
    value, runner, _ = adapter(tmp_path)
    runner.payload = transcript('apiKey')
    plan = quota_plan_for('bound-provider', value)
    cache = QuotaService()
    collector = QuotaCollector(cache, (plan,), clock=lambda:AT)
    collector._collect(*collector._work[0])
    row = cache.snapshot('bound-provider',now=AT,max_age=timedelta(minutes=5)).as_dict()
    assert row['account'] is None and row['reason']=='not_authenticated' and row['windows']==[]
    assert 'private@example' not in json.dumps(row)


def test_session_cache_never_merges_and_rebind_rejects_old_success_or_error():
    a,b = SessionContext.create(QUOTA_POLICY),SessionContext.create(QUOTA_POLICY)
    source = QuotaSource(QUOTA_POLICY,'0.112.0')
    cache = QuotaService()
    old = cache.bind('one',None,source,connection=a)
    sibling = cache.bind('two',None,source,connection=b)
    observation = parse_observation(PAYLOAD,policy=QUOTA_POLICY,version=source.version,observed_at=AT,connection=a)
    assert cache.publish(old,observation,now=AT)
    cache.bind('one',None,source,connection=b)
    current = cache.bind('one',None,source,connection=a)
    assert not cache.publish(old,observation,now=AT)
    assert cache.publish(current,observation,now=AT)
    rows = cache.snapshots(('one','two'),now=AT,max_age=timedelta(minutes=5))
    assert len(rows)==2 and rows[0].as_dict()['account'] is None
    assert rows[1].freshness=='missing'
    assert cache.snapshot('one',now=AT-timedelta(seconds=1),max_age=timedelta(minutes=5)).freshness=='stale'
    with pytest.raises(QuotaError, match='does not match'):
        cache.publish(sibling,observation,now=AT)


def test_session_and_credential_kinds_and_parser_stamps_cannot_be_laundered():
    with pytest.raises(QuotaError): SessionContext.create(BALANCE)
    with pytest.raises(QuotaError): CredentialContext.create(QUOTA_POLICY)
    context = SessionContext.create(QUOTA_POLICY)
    renamed = replace(QUOTA_POLICY,source_kind='renamed-native-source')
    with pytest.raises(QuotaError):
        parse_observation(PAYLOAD,policy=renamed,version='v',observed_at=AT,connection=context)
    with pytest.raises(QuotaError):
        parse_observation(PAYLOAD,policy=renamed,version='v',observed_at=AT,
                          connection=SessionContext.create(renamed))


def test_collector_publishes_real_fields_then_removes_them_on_next_error(tmp_path):
    value, runner, _ = adapter(tmp_path)
    plan = quota_plan_for('bound-provider',value)
    cache = QuotaService()
    clock = [AT]
    collector = QuotaCollector(cache,(plan,),clock=lambda:clock[0])
    collector._collect(*collector._work[0])
    row = cache.snapshot('bound-provider',now=AT,max_age=timedelta(minutes=5)).as_dict()
    assert row['windows'][0]['remaining_percent']==73 and row['source']['version']=='0.112.0'
    runner.payload = b'bad-private-upstream\n'
    clock[0] += timedelta(seconds=1)
    collector._collect(*collector._work[0])
    row = cache.snapshot('bound-provider',now=clock[0],max_age=timedelta(minutes=5)).as_dict()
    assert row['state']=='error' and row['windows']==[]
    assert 'private-upstream' not in json.dumps(row)


def test_native_collector_http_row_keeps_existing_unknown_account_wire(tmp_path, monkeypatch):
    from tests.test_command_quota_routes import contracts, get, quota_api
    value, runner, _ = adapter(tmp_path)
    plan = quota_plan_for('bound-provider', value)
    cache = QuotaService()
    collector = QuotaCollector(cache,(plan,),clock=lambda:AT)
    collector._collect(*collector._work[0])
    subject = quota_api(tmp_path,service=cache,providers=contracts('bound-provider'),clock=lambda:AT.isoformat())
    def forbidden(*args, **kwargs):
        raise AssertionError('GET invoked native reader')
    monkeypatch.setattr(runner,'run',forbidden)
    row = get(subject).payload['snapshots'][0]
    assert row['account'] is None and row['account_status']=='unknown'
    assert 'connection' not in row and row['binding_ids']==['bound-provider']
    assert row['windows'][0]['remaining_percent']==73


def test_a_read_behind_a_dispatch_turn_is_deferred_within_its_wait_and_stop_stays_bounded(tmp_path, monkeypatch):
    from datetime import timedelta
    from threading import Thread
    from time import monotonic, sleep
    from conductor.command.adapters import subscription_quota as native

    monkeypatch.setattr(native, 'ROOT_WAIT_SECONDS', 0.3)
    value, _, _ = adapter(tmp_path)
    service = QuotaService()
    collector = QuotaCollector(service, (quota_plan_for('codex-cli', value),), clock=lambda: AT)
    read = lambda: service.snapshot('codex-cli', now=AT, max_age=timedelta(minutes=5))
    with value._workspace.owned():  # stands in for a T5 attempt holding the root for its whole turn
        collector.start()
        deadline = monotonic() + 5
        while monotonic() < deadline and read().deferred_at is None:
            sleep(0.02)
        seen = read()
        stopper = Thread(target=collector.stop, daemon=True)
        stopper.start()
        stopper.join(3)
        hung = stopper.is_alive()
    stopper.join(10)
    assert not hung, 'stop waited behind a whole dispatch turn'
    # Codex ruling J (23.09.2026): a busy root is neither an error nor a reading. With no earlier
    # reading the screen gets 'deferred' and 'no data' -- never an invented figure.
    assert seen.observation is None and seen.deferred_at == AT
    body = seen.as_dict()
    assert body['state'] == 'missing' and body['reason'] == 'no_data' and body['windows'] == []
    assert body['deferred_at'] == '2026-09-21T16:00:00Z'
