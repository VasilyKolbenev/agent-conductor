"""Subscription ACP metadata uses the same native login road as dispatch."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from conductor.command.adapters.grok_build import (
    GrokBuildAdapter, GROK_AUTH_RPC, GROK_QUOTA_RPC, grok_pin)
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner
from conductor.command.adapters.quota_connection import NativeQuotaReadError
from conductor.command.quota_plans import quota_plan_for
from conductor.command.quota_service import QuotaService
from conductor.quota_collectors import QuotaCollector

AT = datetime(2026,9,21,17,tzinfo=timezone.utc)
BILLING = {'config': {'creditUsagePercent': 41, 'currentPeriod': {
    'type':'USAGE_PERIOD_TYPE_WEEKLY','start':'2026-09-20T12:00:00Z','end':'2026-09-27T12:00:00Z'}}}


def transcript(method='cached_token', *, billing=True, notification=True):
    rows = [{'jsonrpc':'2.0','id':1,'result':{'_meta':{'defaultAuthMethodId':method}}},
            {'jsonrpc':'2.0','id':2,'result':{'methodId':method,'email':'private@example.invalid'}}]
    if billing: rows.append({'jsonrpc':'2.0','id':3,'result':BILLING})
    if notification: rows.append({'jsonrpc':'2.0','method':'_x.ai/mcp/servers_updated','params':{'mcpServers':[]}})
    return b'\n'.join(json.dumps(row).encode() for row in rows)+b'\n'


class NativeRunner(ProcessRunner):
    def __init__(self,root,env):
        super().__init__(root,environ=env)
        self.specs=[]; self.method='cached_token'; self.bad=False
    def run(self,spec):
        self.specs.append(spec)
        if spec.argv[-1]=='--version': output=b'grok 1.0.5 (19d42e3) [stable]'
        else:
            output=b'private-upstream-error' if self.bad else transcript(self.method,billing=spec.stdin_completion_id==3)
            home=Path(spec.env['GROK_HOME']); (home/'logs').mkdir(exist_ok=True)
            (home/'logs'/'unified.jsonl').write_text('native metadata trace')
        return ProcessOutcome('completed',0,output,False,spec.output_limit,0,'synthetic',
                              'delivered' if spec.stdin_bytes else 'not_provided')


def make(tmp_path,*,auth='subscription',env=None):
    home=tmp_path/'pinned'; home.mkdir()
    (home/'config.toml').write_text('[marketplace]\ndefault_skills_installs_purged = true\n')
    env=env or {'SELECTED':'synthetic-context','EXCLUDED':'hidden'}
    runner=NativeRunner(tmp_path,env)
    pin=grok_pin(str(tmp_path/'native.exe'),tuple(key for key in env if key!='EXCLUDED'),
        auth=auth,auth_home=str(home) if auth=='subscription' else '')
    counter=[0]
    def ids(kind): counter[0]+=1; return kind+'-'+str(counter[0])
    value=GrokBuildAdapter(pin,runner,root=tmp_path,clock=lambda:AT.isoformat(),ids=ids)
    return value,runner,home


def test_subscription_read_and_dispatch_use_the_same_pinned_home_and_environment(tmp_path):
    value,runner,home=make(tmp_path)
    plan=quota_plan_for('bound',value)
    assert not runner.specs
    assert plan.request.read()==BILLING
    assert len(runner.specs)==2 and value._login()==('subscription',str(home))
    assert value._home_value(tmp_path/'fresh-attempt')==str(home)
    for spec in runner.specs:
        env=runner._child_env(spec)
        assert env['GROK_HOME']==str(home) and env['SELECTED']=='synthetic-context'
        assert 'EXCLUDED' not in env and spec.argv[0]==str(tmp_path/'native.exe')
    assert runner.specs[-1].stdin_completion_id==3 and runner.specs[-1].separate_stderr
    assert not (home/'logs').exists() and value._login_seen==()


@pytest.mark.parametrize('method',[None,'xai.api_key','grok.com','oidc','',True])
def test_only_existing_cached_session_is_admitted_and_no_login_is_requested(method,tmp_path):
    value,runner,_=make(tmp_path); runner.method=method
    assert not value._login_method_admitted(transcript(method,billing=False))
    with pytest.raises(NativeQuotaReadError,match='not_authenticated'):
        value.quota_connection().read()
    requests=[json.loads(row) for row in runner.specs[-1].stdin_bytes.splitlines()]
    assert [row['method'] for row in requests]==['initialize','_x.ai/auth/info','_x.ai/billing']


def test_native_auth_preflight_admits_positive_control_and_refuses_wrong_initialize_identity(tmp_path):
    value,_,_=make(tmp_path)
    assert value._login_method_admitted(transcript(billing=False))
    raw=transcript(billing=False).replace(b'"defaultAuthMethodId": "cached_token"',b'"defaultAuthMethodId": null')
    assert not value._login_method_admitted(raw)


@pytest.mark.parametrize('config',['[model]\napi_key="synthetic"\n',
    '[hooks]\ncommand="do-not-run"\n','[grok_com_config]\nbase_url="https://other.invalid"\n'])
def test_custom_profile_configuration_refuses_before_any_spawn(config,tmp_path):
    value,runner,home=make(tmp_path); (home/'config.toml').write_text(config)
    with pytest.raises(NativeQuotaReadError,match='not_supported'):
        value.quota_connection().read()
    assert runner.specs==[]


@pytest.mark.parametrize('name',['XAI_API_KEY','GROK_AUTH_PROVIDER_COMMAND','GROK_CLI_CHAT_PROXY_BASE_URL'])
def test_active_native_auth_or_origin_override_refuses_before_spawn(name,tmp_path):
    value,runner,_=make(tmp_path,env={name:'synthetic-selected'})
    with pytest.raises(NativeQuotaReadError,match='not_supported'): value.quota_connection().read()
    assert runner.specs==[]


def test_collector_then_http_projection_keeps_native_values_and_removes_on_error(tmp_path,monkeypatch):
    from tests.test_command_quota_routes import contracts,get,quota_api
    value,runner,_=make(tmp_path); cache=QuotaService(); now=[AT]
    collector=QuotaCollector(cache,(quota_plan_for('bound',value),),clock=lambda:now[0])
    collector._collect(*collector._work[0])
    api=quota_api(tmp_path,service=cache,providers=contracts('bound'),clock=lambda:now[0].isoformat())
    row=get(api).payload['snapshots'][0]
    assert row['windows'][0]['remaining_percent']==59 and row['source']['kind']=='grok-acp'
    assert row['account'] is None and 'private@example' not in json.dumps(row)
    runner.bad=True; now[0]+=timedelta(seconds=1); collector._collect(*collector._work[0])
    def forbidden(*args,**kwargs): raise AssertionError('GET spawned a child')
    monkeypatch.setattr(runner,'run',forbidden)
    row=get(api).payload['snapshots'][0]
    assert row['state']=='error' and row['windows']==[] and 'private-upstream' not in json.dumps(row)


def test_only_calibrated_metadata_notification_is_tolerated():
    assert GROK_QUOTA_RPC.decode(transcript())==BILLING
    with pytest.raises(NativeQuotaReadError):
        GROK_QUOTA_RPC.decode(transcript().replace(b'_x.ai/mcp/servers_updated',b'_x.ai/unknown'))
    with pytest.raises(NativeQuotaReadError):
        GROK_QUOTA_RPC.decode(transcript()+transcript())


def test_api_key_road_does_not_attempt_subscription_metadata(tmp_path):
    value,runner,_=make(tmp_path,auth='api_key')
    assert value.quota_connection().reason=='not_supported' and not runner.specs
