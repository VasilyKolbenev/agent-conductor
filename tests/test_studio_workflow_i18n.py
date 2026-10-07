"""Translate the inspector while preserving editor identities and user input."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from tests.test_studio_agents_i18n import DOM

PANEL=Path(__file__).resolve().parents[1]/'src/conductor/panel'


@pytest.mark.parametrize('locale,heading', [('ru','Общее'),('en','General')])
def test_workflow_locale_keeps_context_keys_draft_and_edit_identity(locale,heading):
    node=shutil.which('node')
    if node is None:pytest.skip('Node is required for localized editor rendering')
    code=f'import {{mountInspector}} from {json.dumps((PANEL/"studio-inspector.js").as_uri())};\n'+DOM+'''
    Object.defineProperty(E.prototype,'classList',{get(){return {add(){},remove(){},toggle(){}};}});
    const step={node_id:'my-step',kind:'task',title:'General',purpose:'User <b> задача',
      role_id:'my-role',capability:'dispatch',verifier_role_id:null,resources:[],arguments:{},
      timeout_seconds:null,attempt_bound:null,position:null};
    const state={locale:LOCALE,canvas:{selection:{kind:'node',id:'my-step'}},
      workflows:{draft:{document:{nodes:[step],edges:[]}}},providers:[]};
    const before=JSON.stringify(state),mount=new E('main');let edited=null;
    mountInspector(mount,state,{onEdit:value=>edited=value});
    const title=all(mount).find(x=>x.attrs['data-edit-field']==='title');
    const initialTitle=title.value;
    title.value='New <b> title';title.events.change();
    console.log(JSON.stringify({text:mount.textContent,initialTitle,edited,
      contexts:all(mount).map(x=>x.attrs['data-context']).filter(Boolean),
      immutable:JSON.stringify(state)===before,html:all(mount).some(x=>x.tag==='b')}));
    '''.replace('LOCALE',json.dumps(locale))
    result=subprocess.run([node,'--input-type=module','-e',code],capture_output=True,
        text=True,encoding='utf-8',timeout=15,check=False)
    assert result.returncode==0,result.stderr
    answer=json.loads(result.stdout)
    assert heading in answer['text']
    assert answer['initialTitle']=='General' and answer['immutable'] and not answer['html']
    assert {'stable-id','success-criteria','output-budget'} <= set(answer['contexts'])
    assert answer['edited']=={'type':'set-field','nodeId':'my-step','field':'title','value':'New <b> title'}
