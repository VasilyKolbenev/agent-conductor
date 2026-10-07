"""The Agents card says a deferral and never shows a passed-reset window as a remainder, in both locales."""
import json

import pytest

from tests.test_studio_agents_i18n import js


@pytest.mark.parametrize("locale,deferred,reset", [
    ("en", "Update deferred: a step is running", "Window reset after this reading"),
    ("ru", "Обновление отложено: идёт шаг", "Окно сброшено после этого показания")])
def test_a_deferred_card_keeps_its_reading_and_hides_the_figures_of_a_reset_window(locale, deferred, reset):
    result = js("""
      const window=(id,used,freshness)=>({limit_id:'codex',window_id:id,used_percent:used,
        remaining_percent:100-used,resets_at:'2026-09-21T17:00:00Z',starts_at:null,duration_minutes:300,freshness});
      const snapshot={binding_ids:['my-id'],account:null,account_status:'unknown',
        source:{kind:'codex-app-server',version:'0.112.0'},observed_at:'2026-09-21T16:00:00Z',
        state:'observed',reason:null,freshness:'stale',deferred_at:'2026-09-21T16:01:00Z',
        windows:[window('primary',27,'reset_passed'),window('secondary',41,'stale')]};
      const state={locale:LOCALE,providers:[{provider_id:'my-id',display_name:'Codex',
        availability:'available',implementation:'real_experimental',auth:'subscription',controls:['dispatch']}],
        agents:{phase:'ready',participants:[]},
        quotas:{phase:'ready',payload:{providers:[{provider_id:'my-id',display_name:'Codex'}],
          snapshots:[snapshot],as_of:'2026-09-21T17:05:00Z',max_age_seconds:300}}};
      const mount=new E('main');
      people.mountAgents(mount,state,{refreshQuotas:()=>{},refreshAgents:()=>{}});
      const cards=all(mount).filter(x=>x.attrs['data-quota-window']);
      console.log(JSON.stringify({text:mount.textContent,
        primary:cards.find(x=>x.attrs['data-quota-window']==='primary').textContent,
        secondary:cards.find(x=>x.attrs['data-quota-window']==='secondary').textContent}));
    """.replace("LOCALE", json.dumps(locale)))
    assert deferred in result["text"] and "2026-09-21 16:01:00 UTC" in result["text"]
    assert "2026-09-21 16:00:00 UTC" in result["text"], "the last reading keeps its own time"
    assert reset in result["primary"] and "27%" not in result["primary"] and "73%" not in result["primary"]
    assert "41%" in result["secondary"] and "59%" in result["secondary"], "an aged window keeps its figures"
