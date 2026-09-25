"""Execute localized renderers without altering identifiers or source evidence."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"
DOM = """
class E {
  constructor(tag) {this.tag=tag;this.children=[];this.attrs={};this.events={};this.value='';}
  set textContent(value) {this.children=[String(value)];}
  get textContent() {return this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
  setAttribute(k,v) {this.attrs[k]=String(v);}
  getAttribute(k) {return this.attrs[k]??null;}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children=[...children];}
  addEventListener(k,v) {this.events[k]=v;}
  contains() {return false;}
  querySelector() {return null;}
}
globalThis.document={activeElement:null,body:new E('body'),createElement:t=>new E(t)};
const all=node=>[node,...node.children.filter(x=>typeof x!=='string').flatMap(all)];
"""


def js(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the localized rendering boundary")
    imports = "\n".join(f"import * as {alias} from {json.dumps((PANEL/name).as_uri())};"
        for alias, name in (("people", "studio-people.js"), ("isolation", "studio-isolation.js")))
    result = subprocess.run([node, "--input-type=module", "-e", imports+DOM+body],
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# The screen's heading is `studio.html`'s; the module's own words in the page's language are its lede.
@pytest.mark.parametrize("locale,title,unavailable", [("ru", "Процесс задаёт роли.", "Недоступно"),
    ("en", "A workflow names roles.", "Unavailable")])
def test_agents_and_quota_preserve_literal_names_money_and_unknown(locale, title, unavailable):
    result = js("""
      const name='<img src=x> Не переводить', amount='12345678901234567890.00100';
      const snapshot={binding_ids:['my-id'],account_status:'unknown',source:null,
        observed_at:null,freshness:'unknown',state:'unavailable',reason:'no_data',
        is_available:null,balances:[{currency:'USD',total_balance:amount,
          granted_balance:'0',topped_up_balance:amount}]};
      const state={locale:LOCALE,providers:[{provider_id:'my-id',display_name:name,
        availability:'available',implementation:'real_experimental',auth:'subscription',controls:['dispatch']}],
        agents:{phase:'ready',participants:[{instance_id:'instance-id',provider_id:'my-id',
          model:null,controls:['dispatch'],role_ids:['Role Не переводить']}]},
        quotas:{phase:'ready',payload:{providers:[{provider_id:'my-id',display_name:name}],
          snapshots:[snapshot],as_of:'2026-09-21T12:00:00Z',max_age_seconds:300}}};
      const before=JSON.stringify(state), mount=new E('main');let refresh=0;
      people.mountAgents(mount,state,{refreshQuotas:()=>refresh++,refreshAgents:()=>{}});
      all(mount).find(x=>x.attrs['data-focus-key']==='quota-read').events.click();
      console.log(JSON.stringify({text:mount.textContent,unchanged:JSON.stringify(state)===before,
        refresh,html:all(mount).some(x=>x.tag==='img'),amount,name}));
    """.replace("LOCALE", json.dumps(locale)))
    assert title in result["text"] and unavailable in result["text"]
    assert result["name"] in result["text"] and result["amount"] in result["text"]
    assert "instance-id" in result["text"] and "Role Не переводить" in result["text"]
    assert result["unchanged"] and result["refresh"] == 1 and not result["html"]
    assert ("Платёжный аккаунт неизвестен" if locale == "ru" else "Billing account unknown") in result["text"]


@pytest.mark.parametrize("locale,title", [("ru", "Записать решение"), ("en", "Record this decision")])
def test_decision_locale_retains_human_input_and_callback_identity(locale, title):
    result = js("""
      const row={run_id:'run',gate_id:'gate',node_id:'step',title:'User <b> title',
        decision:'satisfied',answerable:'supersede',standing:'old-receipt',unblocks:[]};
      const draft={key:'run/gate',action:'request_changes',actor:'human',reason:'<b> Keep my input'};
      const state={locale:LOCALE,connection:'open',decisions:{phase:'ready',list:[row],draft}};
      const before=JSON.stringify(state), mount=new E('main');let submitted=null;
      people.mountDecisions(mount,state,{editDecision:()=>{},submitDecision:value=>submitted=value,selectDecision:()=>{}});
      const form=all(mount).find(x=>x.tag==='form');form.events.submit({preventDefault(){}});
      console.log(JSON.stringify({text:mount.textContent,inputs:all(mount).filter(x=>x.tag==='input').map(x=>x.value),
        unchanged:JSON.stringify(state)===before,identity:submitted===row}));
    """.replace("LOCALE", json.dumps(locale)))
    assert title in result["text"] and "old-receipt" in result["text"]
    assert "<b> Keep my input" in result["inputs"] and "human" in result["inputs"]
    assert result["unchanged"] and result["identity"]


@pytest.mark.parametrize("locale,title", [("ru", "Отказ до запуска шага"), ("en", "Stopped before the step runs")])
def test_isolation_translates_only_interface_and_keeps_server_evidence(locale, title):
    result = js("""
      const facts={controls:{instances:[{instance_id:'instance',adapter_id:'vendor',
        isolation:{dispatch:[{name:'check',standing:'active',category:'refused_before_spawn'},
          {name:'unknown',standing:'unknown',category:'detected_after_spawn'}]}}],
        isolation_facts:[{name:'check',sentence:'SERVER <img> Не переводить'},
          {name:'unknown',sentence:'SECOND SERVER'}]}};
      const before=JSON.stringify(facts), output=isolation.isolationFacts(facts,{instance_id:'instance'},'dispatch',{locale:LOCALE});
      console.log(JSON.stringify({text:output.map(x=>x.textContent).join(' '),
        unchanged:JSON.stringify(facts)===before,html:output.flatMap(all).some(x=>x.tag==='img')}));
    """.replace("LOCALE", json.dumps(locale)))
    assert title in result["text"] and "SERVER <img> Не переводить" in result["text"]
    assert result["unchanged"] and not result["html"]
    assert ("не установлено" if locale == "ru" else "Not established") in result["text"]
