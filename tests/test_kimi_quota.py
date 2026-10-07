"""Native OAuth metadata stays on dispatch's managed profile and owned process."""
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from conductor.command.adapters import login_home
from conductor.command.adapters.kimi_code import KimiCodeAdapter, kimi_pin, LIVE_QUOTA_POLICY, _managed_profile
from conductor.command.adapters.process import ProcessRunner, ProcessOutcome, OwnedProcess
from conductor.command.adapters.quota_connection import NativeQuotaReadError
from conductor.command.quota import parse_observation
from conductor.command.quota_service import QuotaService
from conductor.command.quota_plans import quota_plan_for
from conductor.quota_collectors import QuotaCollector

AT=datetime(2026,9,21,18,tzinfo=timezone.utc)
CONFIG="""default_model = "kimi-code/kimi-test"
[providers."managed:kimi-code"]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"
api_key = ""
[providers."managed:kimi-code".oauth]
storage = "file"
key = "oauth/kimi-code"
[models."kimi-code/kimi-test"]
provider = "managed:kimi-code"
model = "kimi-test"
max_context_size = 262144
"""
AUTH={'code':0,'data':{'ready':True,'providers_count':1,'default_model':'kimi-code/kimi-test',
    'managed_provider':{'name':'managed:kimi-code','status':'authenticated'}}}
USAGE={'code':0,'data':{'kind':'ok','summary':{'used':20,'limit':100,
    'window':{'duration':1,'unit':'week'},'reset_at':'2026-09-28T18:00:00Z'},
    'limits':[{'used':30,'limit':60,'window':{'duration':5,'unit':'hour'},
    'reset_at':'2026-09-21T23:00:00Z'}]}}

class NativeRunner(ProcessRunner):
    def __init__(self,root,env):
        super().__init__(root,environ=env);self.specs=[];self.live=False;self.stopped=0
    def run(self,spec):
        self.specs.append(spec)
        output=b'0.38.0' if spec.argv[-1]=='--version' else b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1}}\n{"jsonrpc":"2.0","id":2,"result":{}}\n'
        return ProcessOutcome('completed',0,output,False,spec.output_limit,0,'synthetic','delivered' if spec.stdin_bytes else 'not_provided')
    def start(self,spec):
        self.specs.append(spec);self.live=True
        home=Path(spec.env['KIMI_CODE_HOME']);meta=home/'server'/'instances';meta.mkdir(parents=True)
        (meta/'owned.json').write_text(json.dumps({'pid':12345,'host':'127.0.0.1','port':45678,'serverVersion':'0.38.0'}))
        (home/'server.token').write_text('a'*43)
        (home/'logs').mkdir();(home/'logs'/'trace.log').write_text('native trace')
        return OwnedProcess('owned-token',12345)
    def stop(self,token):
        assert token=='owned-token';self.live=False;self.stopped+=1
        return ProcessOutcome('stopped',1,b'',False,16384,0,'synthetic')


def make(tmp_path,env=None):
    home=tmp_path/'auth';home.mkdir();(home/'config.toml').write_text(CONFIG)
    (home/'credentials').mkdir();(home/'credentials'/'kimi-code.json').write_text(json.dumps({'access_token':'synthetic-access-secret','refresh_token':'synthetic-refresh-secret'}))
    env=env or {};runner=NativeRunner(tmp_path,env);counter=[0]
    def ids(kind):counter[0]+=1;return kind+'-'+str(counter[0])
    adapter=KimiCodeAdapter(kimi_pin(str(tmp_path/'kimi.exe'),tuple(env),auth='subscription',auth_home=str(home)),runner,root=tmp_path,clock=lambda:AT.isoformat(),ids=ids)
    return adapter,runner,home


def waiting(ready,**kwargs):
    value=ready();assert value==(45678,'a'*43);return value


def test_same_native_profile_owned_server_is_reaped_and_transients_removed(tmp_path):
    adapter,runner,home=make(tmp_path);calls=[]
    def fetch(**kwargs):
        assert runner.live and kwargs['bearer']=='a'*43;calls.append(kwargs['path'])
        return AUTH if kwargs['path']=='/api/v1/auth' else USAGE
    plan=quota_plan_for('bound',adapter)
    assert plan.request.transport=='loopback' and not runner.specs
    assert plan.request.read(waiting,fetch,lambda:45678)==USAGE
    assert calls==['/api/v1/auth','/api/v1/oauth/usage'] and runner.stopped==1 and not runner.live
    assert not (home/'server').exists() and not (home/'logs').exists()
    assert (home/'credentials'/'kimi-code.json').is_file() and adapter._login_seen==()
    assert all(spec.env['KIMI_CODE_HOME']==str(home) for spec in runner.specs)
    assert b'synthetic-access-secret' in runner.specs[-1].sensitive_extra
    assert runner.specs[-1].argv[1:]==('web','--no-open','--host','127.0.0.1','--port','45678')


@pytest.mark.parametrize('failure',['auth','fetch','wait','interrupt'])
def test_failures_reap_owned_server_and_do_not_publish_old_quota(failure,tmp_path):
    adapter,runner,home=make(tmp_path)
    def wait(ready,**kwargs):
        if failure=='wait':raise RuntimeError('private bearer detail')
        return waiting(ready)
    def fetch(**kwargs):
        if failure=='interrupt':raise KeyboardInterrupt()
        if failure=='fetch':raise RuntimeError('private bearer detail')
        return {'code':0,'data':{'ready':False}}
    with pytest.raises(KeyboardInterrupt if failure=='interrupt' else NativeQuotaReadError) as caught:
        adapter.quota_connection().read(wait,fetch,lambda:45678)
    assert 'private' not in str(caught.value) and not runner.live and runner.stopped==1
    assert not (home/'server').exists() and adapter._login_seen==()


@pytest.mark.parametrize('replacement',[('api_key = ""','api_key = "synthetic-key"'),
    ('https://api.kimi.com/coding/v1','https://other.invalid/v1'),
    ('key = "oauth/kimi-code"','key = "other-account"'),
    ('provider = "managed:kimi-code"','provider = "api-provider"')])
def test_unsupported_auth_configuration_refuses_before_spawn(replacement,tmp_path):
    adapter,runner,home=make(tmp_path);(home/'config.toml').write_text(CONFIG.replace(*replacement))
    with pytest.raises(NativeQuotaReadError,match='not_supported'):adapter.quota_connection().read(waiting,lambda **kw:USAGE,lambda:45678)
    assert runner.specs==[]


def test_a_signed_out_home_asks_for_a_login_instead_of_calling_the_source_unsupported(tmp_path):
    """MEASURED live (23.09.2026): before the owner's login the pinned home holds no config.toml,
    and the reading said 'not_supported' although the product calls the vendor's own usage route."""
    adapter,runner,home=make(tmp_path);(home/'config.toml').unlink()
    with pytest.raises(NativeQuotaReadError,match='not_authenticated'):adapter.quota_connection().read(waiting,lambda **kw:USAGE,lambda:45678)
    assert runner.specs==[]


@pytest.mark.parametrize('name',['KIMI_MODEL_NAME','KIMI_CODE_BASE_URL','KIMI_CODE_OAUTH_HOST'])
def test_actual_environment_overrides_refuse_before_spawn(name,tmp_path):
    adapter,runner,_=make(tmp_path,{name:'synthetic'})
    with pytest.raises(NativeQuotaReadError,match='not_supported'):adapter.quota_connection().read(waiting,lambda **kw:USAGE,lambda:45678)
    assert runner.specs==[]


def test_native_acp_authenticate_is_readiness_only_and_requires_both_successes(tmp_path):
    adapter,runner,_=make(tmp_path)
    class Request:timeout_seconds=10
    output=adapter._attempt_login_status(Request()).output
    assert adapter._login_method_admitted(output)
    assert [json.loads(x)['method'] for x in runner.specs[-1].stdin_bytes.splitlines()]==['initialize','authenticate']
    assert not adapter._login_method_admitted(output.splitlines()[1])
    assert not adapter._login_method_admitted(output.replace(b'"result":{}',b'"error":{"code":-32000}'))


def test_native_token_is_bounded_and_never_rotated(tmp_path):
    adapter,runner,home=make(tmp_path)
    token=home/'server.token'
    assert login_home.native_server_token(str(home),'server.token') is None
    for value in ('bad', 'x'*257, '../'+('a'*40)):
        token.write_text(value)
        assert login_home.native_server_token(str(home),'server.token') is None
        assert token.read_text()==value
    token.write_text('a'*43)
    assert login_home.native_server_token(str(home),'server.token')=='a'*43


def test_a_finished_or_unowned_server_refuses_even_after_valid_http(tmp_path):
    from conductor.command.adapters.process import OwnershipError
    adapter,runner,_=make(tmp_path)
    original=runner.stop
    def stopped(token):
        original(token)
        raise OwnershipError('synthetic leader already ended')
    runner.stop=stopped
    with pytest.raises(NativeQuotaReadError):
        adapter.quota_connection().read(waiting,lambda **kw:AUTH if kw['path']=='/api/v1/auth' else USAGE,lambda:45678)
    assert not runner.live and runner.stopped==1


def test_native_counts_and_reset_reach_cache_and_get_never_spawns(tmp_path,monkeypatch):
    from tests.test_command_quota_routes import contracts,get,quota_api
    adapter,runner,_=make(tmp_path);cache=QuotaService()
    collector=QuotaCollector(cache,(quota_plan_for('bound',adapter),),clock=lambda:AT,
        loopback_wait=waiting,loopback_port=lambda:45678,loopback_fetch=lambda **kw:AUTH if kw['path']=='/api/v1/auth' else USAGE)
    collector._collect(*collector._work[0])
    api=quota_api(tmp_path,service=cache,providers=contracts('bound'),clock=lambda:AT.isoformat())
    def forbidden(*args,**kwargs):raise AssertionError('GET starts native')
    monkeypatch.setattr(runner,'start',forbidden);monkeypatch.setattr(runner,'run',forbidden)
    row=get(api).payload['snapshots'][0]
    assert [x['remaining_percent'] for x in row['windows']]==[80,50]
    assert row['windows'][1]['resets_at']=='2026-09-21T23:00:00Z'
    assert row['source']['kind']=='kimi-local-server' and row['account'] is None
    assert 'synthetic-access' not in json.dumps(row)


@pytest.mark.parametrize('used,limit',[(False,100),(-1,100),(1,None),(1,-1),(2**54,100)])
def test_invalid_native_counts_never_become_zero(used,limit,tmp_path):
    adapter,_,_=make(tmp_path);plan=quota_plan_for('bound',adapter);raw=json.loads(json.dumps(USAGE))
    raw['data']['summary'].update(used=used,limit=limit)
    with pytest.raises(ValueError):parse_observation(raw,policy=LIVE_QUOTA_POLICY,version='0.38.0',observed_at=AT,connection=plan.connection)


def test_zero_capacity_remains_unknown_not_free(tmp_path):
    adapter,_,_=make(tmp_path);plan=quota_plan_for('bound',adapter);raw=json.loads(json.dumps(USAGE));raw['data']['summary']['limit']=0
    value=parse_observation(raw,policy=LIVE_QUOTA_POLICY,version='0.38.0',observed_at=AT,connection=plan.connection)
    assert value.windows[0].used_percent is None


def test_a_loopback_read_behind_a_dispatch_turn_is_deferred_within_its_wait(tmp_path, monkeypatch):
    from datetime import timedelta
    from threading import Thread
    from conductor.command.adapters import subscription_quota as native

    monkeypatch.setattr(native, 'ROOT_WAIT_SECONDS', 0.3)
    adapter, runner, _ = make(tmp_path); cache = QuotaService()
    collector = QuotaCollector(cache, (quota_plan_for('bound', adapter),), clock=lambda: AT,
        loopback_wait=waiting, loopback_port=lambda: 45678,
        loopback_fetch=lambda **kw: AUTH if kw['path'] == '/api/v1/auth' else USAGE)
    reader = Thread(target=collector._collect, args=collector._work[0], daemon=True)
    with adapter._workspace.owned():  # stands in for a T5 attempt holding the root for its whole turn
        reader.start()
        reader.join(3)
        hung = reader.is_alive()
    reader.join(10)
    assert not hung, 'the loopback read waited behind a whole dispatch turn'
    seen = cache.snapshot('bound', now=AT, max_age=timedelta(minutes=5))
    assert seen.observation is None and seen.deferred_at == AT, 'busy is a deferral, not an error'
    assert seen.as_dict()['state'] == 'missing' and seen.as_dict()['windows'] == []
    assert runner.specs == [], 'nothing was spawned without the turn'
