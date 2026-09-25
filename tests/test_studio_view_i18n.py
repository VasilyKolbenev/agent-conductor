"""Visible Overview and run form copy changes without changing project or draft data."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from tests.test_studio_agents_i18n import DOM
PANEL=Path(__file__).resolve().parents[1]/'src/conductor/panel'


@pytest.mark.parametrize('locale,title,run_label',[('ru','О проекте','Открыть запуск'),('en','What this is','Open a run')])
def test_overview_and_run_form_localize_without_rewriting_project_or_opening(locale,title,run_label):
    node=shutil.which('node')
    if node is None:pytest.skip('Node is required for UI renderers')
    source='\n'.join(f'import * as {alias} from {json.dumps((PANEL/name).as_uri())};'
        for alias,name in [('view','studio-view.js'),('form','studio-runform.js'),('store','studio-store.js')])
    source+=DOM+'''
    Object.defineProperty(E.prototype,'classList',{get(){return {add(){},remove(){},toggle(){}};}});
    const state=structuredClone(store.EMPTY);state.locale=LOCALE;state.project={name:'Project <b> имя'};
    state.workflows.list=[{workflow_id:'workflow',title:'User title',latest_revision:1,revisions:[1],has_draft:false}];
    state.workflows.selectedId='workflow';state.workflows.detail={published:{revision:1,nodes:[]}};
    state.workflows.opening={runId:'my-run',cycleId:'my-cycle',mode:'observe'};
    state.providers=[];
    const before=JSON.stringify(state),mount=new E('main');view.mountOverview(mount,state,{});
    const formNode=form.runForm(state,{});
    console.log(JSON.stringify({overview:mount.textContent,form:formNode.textContent,
      inputs:all(formNode).filter(x=>x.tag==='input').map(x=>x.value),
      unchanged:before===JSON.stringify(state),html:all(mount).some(x=>x.tag==='b')}));
    '''.replace('LOCALE',json.dumps(locale))
    result=subprocess.run([node,'--input-type=module','-e',source],capture_output=True,text=True,encoding='utf-8',timeout=15,check=False)
    assert result.returncode==0,result.stderr
    got=json.loads(result.stdout)
    assert title in got['overview'] and 'Project <b> имя' in got['overview']
    assert run_label in got['form'] and got['inputs']==['my-run','my-cycle']
    assert got['unchanged'] and not got['html']
