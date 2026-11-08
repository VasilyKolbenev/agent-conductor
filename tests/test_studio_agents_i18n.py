"""Execute localized renderers without altering identifiers or source evidence."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"
DOM = """
class E {
  constructor(tag) {this.tag=tag;this.children=[];this.attrs={};this.dataset={};this.events={};this.value='';}
  set textContent(value) {this.children=[String(value)];}
  get textContent() {return this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
  setAttribute(k,v) {
    this.attrs[k]=String(v);
    if(k.startsWith('data-')) this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(v);
  }
  getAttribute(k) {return this.attrs[k]??null;}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children=[...children];}
  addEventListener(k,v) {this.events[k]=v;}
  contains() {return false;}
  querySelector() {return null;}
  querySelectorAll(selector) {
    if(selector!=="details[open][data-decision-details]") throw Error(selector);
    return all(this).filter(x=>x.tag==="details" && x.open &&
      x.getAttribute("data-decision-details")!==null);
  }
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
    # A subscription row that carries no task road (an older payload) claims nothing about tasks:
    # the claim that it only reads quotas and that tasks need an API key is no longer made.
    said = "Настроена собственная авторизация провайдера" if locale == "ru" else (
        "Configured to use the vendor's own login")
    assert said in result["text"]
    assert "only reads quotas" not in result["text"]
    assert "только для чтения квот" not in result["text"]
    assert "only with an API key" not in result["text"]
    assert "только с API-ключом" not in result["text"]


#: What a row says of its login and of the road a task takes, by language and by road, spelled by
#: hand: the sentence of the pair (`auth`, `task_road`) and the line of the road itself.
SUBSCRIPTION_SAYS = {
    ("en", "boundary"): (
        "A task runs inside the execution boundary on a copy of that login that has no refresh "
        "token; the login directory itself is never given to the task.",
        "A task of this harness runs inside the execution boundary."),
    ("ru", "boundary"): (
        "Задача исполняется в изоляции на копии этого входа без refresh-токена; сам каталог "
        "входа задаче не выдаётся.",
        "Задача этого агента исполняется в изоляции (execution boundary)."),
    ("en", "refused"): (
        "A task on this login is refused before it starts. Possible reasons: a subscription "
        "login for this harness is not supported inside the execution boundary yet; its login "
        "directory is not named ...\\DecemberCommand\\logins\\<name>; or this machine cannot give "
        "the boundary (it needs Windows and a build installed under ...\\harnesses\\<name>\\"
        "<version>).",
        "A task of this harness is refused before it starts: it cannot run inside the execution "
        "boundary here."),
    ("ru", "refused"): (
        "Задача с этим входом отклоняется до запуска. Возможные причины: вход по подписке для "
        "этого агента в изоляции пока не поддержан; каталог входа не называется "
        "...\\DecemberCommand\\logins\\<имя>; либо этот компьютер не даёт изоляцию (нужны Windows "
        "и сборка, установленная в ...\\harnesses\\<имя>\\<версия>).",
        "Задача этого агента отклоняется до запуска: здесь она не может исполняться в изоляции."),
}


def agents_view(locale, auth, road, availability="available"):
    """The Agents screen for one provider row that pins `auth` and says `road`: its text, and each
    chip it draws as the class and the text the person sees (glyph first, then the word)."""
    return js("""
      const row={provider_id:'my-id',display_name:'Harness',availability:AVAILABILITY,
        implementation:'real_experimental',auth:AUTH,controls:['dispatch'],ROAD};
      const state={locale:LOCALE,providers:[row],agents:{phase:'ready',participants:[]},
        quotas:{phase:'empty',payload:null}};
      const mount=new E('main');
      people.mountAgents(mount,state,{refreshQuotas:()=>{},refreshAgents:()=>{}});
      const chips=all(mount).filter(x=>typeof x.className==='string'
        &&x.className.startsWith('studio-chip ')).map(x=>[x.className,x.textContent]);
      console.log(JSON.stringify({text:mount.textContent,chips}));
    """.replace("LOCALE", json.dumps(locale)).replace("AUTH", json.dumps(auth)).replace(
        "AVAILABILITY", json.dumps(availability)).replace(
        "ROAD", "" if road is None else f"task_road:{json.dumps(road)}"))


def agents_text(locale, auth, road, availability="available"):
    """The text of the Agents screen for one provider row that pins `auth` and says `road`."""
    return agents_view(locale, auth, road, availability)["text"]


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("road", ["boundary", "refused"])
def test_a_subscription_row_says_what_a_task_does_by_its_road_and_why_it_is_refused(
        locale, road):
    text = agents_text(locale, "subscription", road)
    pair, line = SUBSCRIPTION_SAYS[(locale, road)]
    other = "refused" if road == "boundary" else "boundary"

    assert pair in text and line in text
    assert road in text.split(), "the road is said as a word, like the other closed facts"
    assert SUBSCRIPTION_SAYS[(locale, other)][0] not in text
    assert SUBSCRIPTION_SAYS[(locale, other)][1] not in text
    assert "only reads quotas" not in text and "только для чтения квот" not in text


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_a_row_that_says_no_road_states_no_task_road_and_no_pair(locale):
    text = agents_text(locale, "subscription", None)

    for pair, line in SUBSCRIPTION_SAYS.values():
        assert pair not in text and line not in text


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("road", ["boundary", "refused"])
def test_an_api_key_row_keeps_its_own_words_and_adds_only_the_line_of_its_road(locale, road):
    text = agents_text(locale, "api_key", road)
    own = "Настроено чтение ключа из окружения." if locale == "ru" else (
        "Configured to read a credential from the environment.")
    pair, line = SUBSCRIPTION_SAYS[(locale, road)]

    assert own in text and line in text and pair not in text


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("road,chip,glyph", [
    ("boundary", "studio-chip--pass", "✓"), ("refused", "studio-chip--fail", "✕")])
def test_the_chip_of_a_road_is_drawn_as_the_fact_it_is(locale, road, chip, glyph):
    """A refused road is a fact the person must see, and a road a task can take is not a warning:
    the chip says the word of the road, in the colour and with the glyph of what it means."""
    chips = agents_view(locale, "subscription", road)["chips"]

    assert [f"studio-chip {chip}", f"{glyph} {road}"] in chips, chips
    assert [one for one in chips if one[1].endswith(" " + road)] == [
        [f"studio-chip {chip}", f"{glyph} {road}"]], "the road is drawn once, and as one fact"


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("availability", ["unconfigured", "executable_absent", "version_mismatch"])
@pytest.mark.parametrize("auth", ["subscription", "api_key", "unpinned"])
def test_a_row_this_machine_cannot_start_says_no_road_and_no_pair(locale, availability, auth):
    """A harness nothing was set up for has no adapter, so the registry answers `refused` for it:
    that is no verdict on the machine, and a column of red chips on a fresh machine would read as
    one. Its row keeps what it knows (the machine, the build, the login) and claims no road."""
    view = agents_view(locale, auth, "refused", availability)
    named = [one for one in view["chips"] if one[1].split()[-1] in ("boundary", "refused")]

    assert named == [], named
    for pair, line in SUBSCRIPTION_SAYS.values():
        assert pair not in view["text"] and line not in view["text"]


@pytest.mark.parametrize("locale,four,road", [
    ("en", "Four facts per row", "the road of a task"),
    ("ru", "дорога задачи", "дорога задачи")])
def test_the_explainer_under_the_list_counts_the_road_of_a_task_among_its_facts(
        locale, four, road):
    text = agents_text(locale, "subscription", "boundary")

    assert four in text and road in text
    assert "Three facts" not in text
    assert ("its expiry is checked before every task" if locale == "en"
            else "срок входа проверяется перед каждой задачей") in text


@pytest.mark.parametrize("locale,stop,folder", [
    ("en", "Stop the server first (Ctrl+C in its window)", "owner_busy"),
    ("ru", "Сначала остановите сервер (Ctrl+C в его окне)", "owner_busy")])
def test_the_empty_roster_names_the_wizard_the_stopped_server_and_the_login_folder(
        locale, stop, folder):
    text = js("""
      const state={locale:LOCALE,providers:[],agents:{phase:'ready',participants:[]},
        quotas:{phase:'empty',payload:null}};
      const mount=new E('main');
      people.mountAgents(mount,state,{refreshQuotas:()=>{},refreshAgents:()=>{}});
      console.log(JSON.stringify({text:mount.textContent}));
    """.replace("LOCALE", json.dumps(locale)))["text"]

    assert "conduct providers" in text
    assert stop in text and folder in text
    assert "\\DecemberCommand\\logins\\<id>" in text


@pytest.mark.parametrize("locale,title", [("ru", "Записать решение"), ("en", "Record this decision")])
def test_decision_locale_retains_human_input_and_callback_identity(locale, title):
    result = js("""
      const row={run_id:'run',gate_id:'gate',node_id:'step',title:'User <b> title',
        decision:'satisfied',answerable:'supersede',standing:'old-receipt',unblocks:[]};
      const draft={key:'run/gate',action:'request_changes',actor:'human',reason:'<b> Keep my input'};
      const state={locale:LOCALE,connection:'open',decisions:{phase:'ready',list:[row],draft}};
      const before=JSON.stringify(state), mount=new E('main');let submitted=null;
      const handlers={editDecision:()=>{},submitDecision:value=>submitted=value,selectDecision:()=>{}};
      people.mountDecisions(mount,state,handlers);
      all(mount).find(x=>x.dataset.decisionDetails==='run/gate').open=true;
      people.mountDecisions(mount,state,handlers);
      const form=all(mount).find(x=>x.tag==='form');form.events.submit({preventDefault(){}});
      console.log(JSON.stringify({text:mount.textContent,inputs:all(mount).filter(x=>x.tag==='input').map(x=>x.value),
        open:mount.querySelectorAll('details[open][data-decision-details]').map(x=>x.dataset.decisionDetails),
        unchanged:JSON.stringify(state)===before,identity:submitted===row}));
    """.replace("LOCALE", json.dumps(locale)))
    assert title in result["text"] and "old-receipt" in result["text"]
    assert "<b> Keep my input" in result["inputs"] and "human" in result["inputs"]
    assert result["unchanged"] and result["identity"]
    assert result["open"] == ["run/gate"]


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
