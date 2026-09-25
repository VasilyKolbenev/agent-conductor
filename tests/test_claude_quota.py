"""Pinned native control source, same login road, honest cached age."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from conductor.command.adapters.claude_code import (
    ClaudeCodeTransport, CONTROL_QUOTA_POLICY, CONTROL_QUOTA_RPC, claude_pin)
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner
from conductor.command.adapters.quota_connection import (NativeQuotaReadError, NativeQuotaSample,
                                                       NativeQuotaUnconfirmed)
from conductor.command.quota_plans import quota_plan_for
from conductor.command.quota_service import QuotaService
from conductor.quota_collectors import QuotaCollector

AT = datetime(2026, 9, 21, 17, tzinfo=timezone.utc)
LIMITS = {'five_hour': {'utilization': 23, 'resets_at':'2026-09-21T20:00:00Z'},
          'seven_day': {'utilization': None, 'resets_at':'2026-09-25T20:00:00Z'}}


def transcript(account=None, usage=None):
    account = {'apiProvider':'firstParty','subscriptionType':'max',
               'email':'private@example.invalid'} if account is None else account
    usage = {'subscription_type':'max','rate_limits_available':True,'rate_limits':LIMITS,
             'session':{'total_cost_usd':42},'behaviors':{'private':'never-public'}} if usage is None else usage
    return b'\n'.join(json.dumps({'type':'control_response','response':{
        'subtype':'success','request_id':key,'response':body}}).encode()
        for key, body in [('init',{'account':account}),('usage',usage)]) + b'\n'


class NativeRunner(ProcessRunner):
    def __init__(self, root, environ=None):
        super().__init__(root, environ=environ or {'SELECTED':'synthetic-context','EXCLUDED':'other'})
        self.specs, self.raw = [], transcript()
        self.cache = {'fetchedAtMs':int(AT.timestamp()*1000), 'utilization':LIMITS}

    def run(self, spec):
        self.specs.append(spec)
        version = spec.argv[-1] == '--version'
        if not version and self.cache is not None:
            (Path(spec.env['CLAUDE_CONFIG_DIR'])/'.claude.json').write_text(json.dumps({
                'cachedUsageUtilization':self.cache,'unrelated':'not-returned'}),encoding='utf-8')
        return ProcessOutcome('completed',0,b'2.1.239 (Claude Code)' if version else self.raw,
                              False,spec.output_limit,0,'synthetic',
                              'delivered' if spec.stdin_bytes else 'not_provided')


def make(tmp_path, *, auth='subscription', environ=None, allowed=('SELECTED',)):
    home = tmp_path/'pinned'; home.mkdir()
    runner = NativeRunner(tmp_path, environ)
    pin = claude_pin(str(tmp_path/'native.exe'),allowed,auth=auth,
                    auth_home=str(home) if auth=='subscription' else '')
    counter = [0]
    def ids(kind):
        counter[0] += 1
        return kind+'-'+str(counter[0])
    value = ClaudeCodeTransport(pin,runner,root=tmp_path,clock=lambda:AT.isoformat(),ids=ids)
    return value,runner,home


def test_native_control_read_uses_dispatch_identity_without_prompt_or_dispatch_changes(tmp_path):
    value,runner,home = make(tmp_path)
    before = value._stdin_argv(home,None)
    plan = quota_plan_for('binding',value)
    assert runner.specs == []
    sample = plan.request.read()
    assert type(sample) is NativeQuotaSample
    assert sample.observed_at_ms == int(AT.timestamp()*1000)
    assert value._stdin_argv(home,None) == before and '--output-format' in before
    assert before[before.index('--output-format')+1] == 'text'
    assert len(runner.specs) == 2
    for spec in runner.specs:
        assert spec.argv[0] == str(tmp_path/'native.exe')
        env = runner._child_env(spec)
        assert env['CLAUDE_CONFIG_DIR'] == str(home)
        assert env['SELECTED'] == 'synthetic-context' and 'EXCLUDED' not in env
    spec = runner.specs[-1]
    assert spec.argv[1:] == CONTROL_QUOTA_RPC.argv and spec.separate_stderr
    rows = [json.loads(row) for row in spec.stdin_bytes.splitlines()]
    assert [row['request']['subtype'] for row in rows] == ['initialize','get_usage']
    assert all(row['type']=='control_request' for row in rows)
    assert value._login_seen == ()


def test_polling_preserves_native_cache_age_then_failure_removes_old_windows(tmp_path):
    value,runner,_ = make(tmp_path)
    plan = quota_plan_for('binding',value)
    now = [AT]
    cache = QuotaService()
    collector = QuotaCollector(cache,(plan,),clock=lambda:now[0])
    collector._collect(*collector._work[0])
    row = cache.snapshot('binding',now=AT,max_age=timedelta(minutes=5)).as_dict()
    assert row['windows'][0]['remaining_percent'] == 77
    assert row['windows'][1]['used_percent'] is None
    assert row['source']['kind'] == 'claude-control'
    assert 'private@example' not in json.dumps(row) and 'never-public' not in json.dumps(row)
    now[0] += timedelta(minutes=6)
    collector._collect(*collector._work[0])
    row = cache.snapshot('binding',now=now[0],max_age=timedelta(minutes=5)).as_dict()
    assert row['freshness'] == 'stale' and row['observed_at'] == AT.isoformat().replace('+00:00','Z')
    runner.raw = b'sensitive-error-output'
    now[0] += timedelta(seconds=1)
    collector._collect(*collector._work[0])
    row = cache.snapshot('binding',now=now[0],max_age=timedelta(minutes=5)).as_dict()
    assert row['state']=='error' and row['windows']==[]
    assert 'sensitive-error' not in json.dumps(row)


@pytest.mark.parametrize('account', [
    {'apiProvider':'firstParty','subscriptionType':'max','apiKeySource':'ANTHROPIC_API_KEY'},
    {'apiProvider':'firstParty','subscriptionType':'max','tokenSource':'CLAUDE_CODE_OAUTH_TOKEN'},
    {'apiProvider':'vertex','subscriptionType':'max'},
    {'apiProvider':'firstParty','subscriptionType':'api'},
    {'apiProvider':'firstParty'},
])
def test_other_billing_connections_never_inherit_subscription(account,tmp_path):
    value,runner,_ = make(tmp_path)
    runner.raw = transcript(account=account)
    with pytest.raises(NativeQuotaReadError,match='not_authenticated'):
        value.quota_connection().read()


@pytest.mark.parametrize('cached', [None,{}, {'fetchedAtMs':True,'utilization':LIMITS},
    {'fetchedAtMs':'now','utilization':LIMITS},
    {'fetchedAtMs':int(AT.timestamp()*1000),'utilization':{'five_hour':{'utilization':0}}}])
def test_missing_or_different_cache_cannot_supply_a_new_timestamp(cached,tmp_path):
    value,runner,_ = make(tmp_path); runner.cache = cached
    # Refused either way: an error, or (a young cache that moved) unconfirmed -- never a timestamp.
    with pytest.raises((NativeQuotaReadError, NativeQuotaUnconfirmed)):
        value.quota_connection().read()


@pytest.mark.parametrize('raw',[b'',b'not-json',transcript()+transcript(),
    transcript().replace(b'"request_id": "usage"',b'"request_id": "usage", "request_id": "usage"'),
    transcript().splitlines()[0]+b'\n',
    transcript().replace(b'"subtype": "success"',b'"subtype": "error"'),
    transcript()+b'{"type":"assistant","message":"unrequested-turn"}\n'])
def test_control_protocol_rejects_missing_ambiguous_or_unrequested_messages(raw):
    with pytest.raises(NativeQuotaReadError): CONTROL_QUOTA_RPC.decode(raw)


def test_api_key_supplier_is_unavailable_without_native_spawn(tmp_path):
    value,runner,_ = make(tmp_path,auth='api_key')
    plan = quota_plan_for('binding',value)
    assert plan.reason == 'not_supported' and not runner.specs


def test_http_reads_only_sample_cache(tmp_path,monkeypatch):
    from tests.test_command_quota_routes import contracts,get,quota_api
    value,runner,_ = make(tmp_path)
    cache = QuotaService()
    collector = QuotaCollector(cache,(quota_plan_for('binding',value),),clock=lambda:AT)
    collector._collect(*collector._work[0])
    api = quota_api(tmp_path,service=cache,providers=contracts('binding'),clock=lambda:AT.isoformat())
    def forbidden(*args,**kwargs): raise AssertionError('GET spawned native CLI')
    monkeypatch.setattr(runner,'run',forbidden)
    row = get(api).payload['snapshots'][0]
    assert row['account'] is None and row['windows'][0]['remaining_percent']==77


def test_metadata_projection_rejects_portal_and_oversize(tmp_path):
    from conductor.command.adapters.login_home import quota_metadata
    home = tmp_path/'home'; home.mkdir()
    path = home/'.claude.json'
    path.write_text(json.dumps({'cachedUsageUtilization':{'fetchedAtMs':1},'secret':'not-returned'}))
    assert quota_metadata(str(home),path.name,'cachedUsageUtilization') == {'fetchedAtMs':1}
    path.write_bytes(b' '*65537)
    assert quota_metadata(str(home),path.name,'cachedUsageUtilization') is None


def test_the_vendors_plan_label_and_its_value_name_one_subscription(tmp_path):
    """MEASURED on the first real login (23.09.2026): initialize says "Claude Max", get_usage "max"."""
    value,runner,_ = make(tmp_path)
    runner.raw = transcript(account={'apiProvider':'firstParty','subscriptionType':'Claude Max'})
    sample = quota_plan_for('binding',value).request.read()
    assert type(sample) is NativeQuotaSample and sample.observed_at_ms == int(AT.timestamp()*1000)


@pytest.mark.parametrize(('label','machine'), [('Claude Max','pro'), ('Claude Max','console'),
    ('Console','console'), ('Claude Max',''), ('Claude Max',None), ('Claude Maxi','max'), ('Max Claude','max'),
    # The label form of API billing: refused only because the VALUE side is read too.
    ('Claude Console','console'), ('Claude Console','Claude Console')])
def test_a_plan_label_and_value_that_disagree_or_name_api_billing_refuse(label,machine,tmp_path):
    value,runner,_ = make(tmp_path)
    usage = {'subscription_type':machine,'rate_limits_available':True,'rate_limits':LIMITS}
    runner.raw = transcript(account={'apiProvider':'firstParty','subscriptionType':label},usage=usage)
    with pytest.raises(NativeQuotaReadError,match='not_authenticated'):
        value.quota_connection().read()


def _re_rendered(seconds, stamp):
    """One snapshot as the vendor renders it again: every reset moved, the breakdown re-stamped."""
    moved = {name: {**row, 'resets_at': (datetime.fromisoformat(row['resets_at'].replace('Z','+00:00'))
                                       + timedelta(seconds=seconds)).isoformat()}
             for name, row in LIMITS.items()}
    return {**moved, 'seven_day_breakdown': {'as_of': stamp}}


@pytest.mark.parametrize(('seconds','kept'), [(0.45,True), (-59,True), (61,False)])
def test_a_snapshot_the_vendor_re_rendered_keeps_the_age_it_was_cached_with(seconds,kept,tmp_path):
    """MEASURED: get_usage re-renders each reset (12:59:59.98 cached, 13:00:00.43 replied) and
    re-stamps its breakdown, so whole-object equality lost the age of every real reading."""
    value,runner,_ = make(tmp_path)
    cached_at = int((AT - timedelta(minutes=2)).timestamp()*1000)
    runner.cache = {'fetchedAtMs':cached_at,'utilization':_re_rendered(0,'cached')}
    runner.raw = transcript(usage={'subscription_type':'max','rate_limits_available':True,
                                   'rate_limits':_re_rendered(seconds,'replied')})
    if not kept:
        with pytest.raises((NativeQuotaReadError, NativeQuotaUnconfirmed)):
            value.quota_connection().read()
        return
    assert quota_plan_for('binding',value).request.read().observed_at_ms == cached_at


@pytest.mark.parametrize(('plan','admitted'), [('max',True), ('Claude Max',True),
    ('console',False), ('Claude Console',False), ('CLAUDE CONSOLE ',False)])
def test_the_dispatch_login_check_reads_the_plan_as_the_quota_road_does(plan,admitted):
    """`auth status` said "max" on the real login; a label-form console answer is refused too."""
    said = {'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty','subscriptionType':plan}
    assert ClaudeCodeTransport._login_method_admitted(None, json.dumps(said).encode()) is admitted


WINDOW = {'utilization':5,'resets_at':'2026-09-23T13:00:00+00:00'}


@pytest.mark.parametrize(('live','cached'), [
    # a different window SET with equal utilization everywhere else
    ({'five_hour':WINDOW}, {'five_hour':WINDOW,'seven_day':WINDOW}),
    # a reset without a zone is not an instant two replies can be compared by
    ({'five_hour':{**WINDOW,'resets_at':'2026-09-23T13:00:00'}},
     {'five_hour':{**WINDOW,'resets_at':'2026-09-23T13:00:01'}}),
    # an absent reset against a present one
    ({'five_hour':{**WINDOW,'resets_at':None}}, {'five_hour':WINDOW}),
    # a window that is not an object
    ({'five_hour':'5%'}, {'five_hour':WINDOW}),
])
def test_windows_that_do_not_show_the_same_facts_never_share_an_age(live,cached):
    from conductor.command.adapters.claude_quota import _same_windows
    assert _same_windows(live,cached) is False
    assert _same_windows({'five_hour':WINDOW},{'five_hour':WINDOW}) is True


@pytest.mark.parametrize('stamp', ['2026-09-23T12:59:59.982660+00:00', '2026-09-23T13:00:00Z',
    '2024-02-29T23:59:59.5-05:30', '1999-12-31T00:00:00+14:00', '2026-01-01T00:00:00.123456789Z'])
def test_the_package_s_own_instant_arithmetic_agrees_with_the_calendar(stamp):
    """The adapter package imports no time module; its arithmetic is held to one here."""
    from conductor.command.adapters.claude_quota import _epoch_seconds
    expected = datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()
    assert abs(_epoch_seconds(stamp) - expected) < 1e-3
    assert _epoch_seconds('2026-09-23T13:00:00') is None and _epoch_seconds(None) is None


NONESSENTIAL = 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'


@pytest.mark.parametrize('spelling', [NONESSENTIAL, NONESSENTIAL.lower()])
def test_only_the_quota_control_spawn_runs_without_the_nonessential_switch(tmp_path, spelling):
    """MEASURED live (live-v5-7): under that switch 2.1.239's get_usage only echoes the vendor's cache.

    The control spawn loses the one name from both places a value could come from -- the forced
    switches and an operator allowlist the runner copies -- and nothing else; the version preflight of
    the same read keeps the full profile. The lower-case spelling is the same variable on Windows.
    """
    import os
    from conductor.command.adapters.claude_code import CLAUDE_NONESSENTIAL_ENV
    assert CLAUDE_NONESSENTIAL_ENV == NONESSENTIAL
    assert CONTROL_QUOTA_RPC.unset_env == (NONESSENTIAL,)
    value, runner, home = make(tmp_path, environ={'SELECTED': 'synthetic-context', spelling: 'operator-value'},
                               allowed=('SELECTED', spelling))
    sample = quota_plan_for('binding', value).request.read()
    assert sample.observed_at_ms == int(AT.timestamp()*1000)
    version, control = runner.specs
    assert runner._child_env(version)[NONESSENTIAL] == '1'
    env = runner._child_env(control)
    same = (lambda name: name.upper() == NONESSENTIAL) if os.name == 'nt' else (lambda name: name == spelling)
    assert not any(same(name) for name in env) and not any(same(name) for name in control.env)
    assert not any(same(name) for name in control.env_allow)
    assert env['DISABLE_AUTOUPDATER'] == '1' and env['CLAUDE_CONFIG_DIR'] == str(home)
    assert env['SELECTED'] == 'synthetic-context'
    assert control.argv[1:] == CONTROL_QUOTA_RPC.argv and '--safe-mode' in control.argv
    assert control.timeout_seconds == 15



@pytest.mark.parametrize('age_seconds,unconfirmed', [(0, True), (299, True), (300, False), (3600, False)])
def test_a_live_reply_newer_than_a_throttled_cache_is_unconfirmed_not_an_error(tmp_path, age_seconds, unconfirmed):
    """The M review read it from the pinned binary: the vendor rewrites its usage cache at most every
    300 s, while get_usage now fetches live on every poll. A moved reply inside that window is newer
    than the cache that would date it; past the window a mismatch is a real inconsistency."""
    from conductor.command.adapters.quota_connection import NativeQuotaUnconfirmed
    value, runner, _home = make(tmp_path)
    runner.cache = {'fetchedAtMs': int(AT.timestamp() * 1000) - age_seconds * 1000,
                    'utilization': {**LIMITS, 'five_hour': {**LIMITS['five_hour'], 'utilization': 22}}}
    expected = NativeQuotaUnconfirmed if unconfirmed else NativeQuotaReadError
    with pytest.raises(expected):
        quota_plan_for('binding', value).request.read()


def test_an_unconfirmed_poll_keeps_the_last_reading_and_ends_a_deferral(tmp_path):
    from datetime import timedelta
    from conductor.command.quota_service import QuotaService
    from conductor.quota_collectors import QuotaCollector
    value, runner, _home = make(tmp_path)
    service = QuotaService()
    collector = QuotaCollector(service, (quota_plan_for('binding', value),), clock=lambda: AT)
    plan, ticket = collector._work[0]
    collector._collect(plan, ticket)
    first = service.snapshot('binding', now=AT, max_age=timedelta(minutes=5))
    assert first.observation.state == 'observed'
    assert service.defer(ticket, now=AT)
    runner.cache = {'fetchedAtMs': int(AT.timestamp() * 1000),
                    'utilization': {**LIMITS, 'five_hour': {**LIMITS['five_hour'], 'utilization': 22}}}
    collector._collect(plan, ticket)
    after = service.snapshot('binding', now=AT, max_age=timedelta(minutes=5))
    assert after.observation == first.observation and after.deferred_at is None
