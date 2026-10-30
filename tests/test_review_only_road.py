"""A read-only road stays visible but enters a role only through the owner's choice."""
import pytest

from conductor.command.adapters.provider import provider_projection
from tests.desk_node import run_js
from tests.test_command_provider_contract import _contract
from tests.test_studio_agents_i18n import DOM


@pytest.mark.parametrize("dispatch,review,expected,modes", [
    (False, True, "review_only", ["dispatch", "review"]),
    (True, True, "boundary", ["dispatch"]),
    (False, False, "refused", ["dispatch", "review"]),
    (False, 1, "refused", ["dispatch", "review"]),
    (None, True, "refused", ["dispatch"]),
    (1, True, "refused", ["dispatch"]),
    (False, "error", "refused", ["dispatch", "review"]),
    ("error", True, "refused", ["dispatch"]),
])
def test_projection_requires_exact_mode_evidence(dispatch, review, expected, modes):
    asked = []

    def boundary(provider, mode):
        asked.append(mode)
        value = dispatch if mode == "dispatch" else review
        if value == "error":
            raise LookupError("unavailable")
        return value

    (row,) = provider_projection([_contract()], boundary=boundary)
    assert row["task_road"] == expected
    assert asked == modes


_ROW = """
const row = {provider_id:'thin',display_name:'Read harness',availability:'available',
  implementation:'real_experimental',auth:'subscription',task_road:'review_only',
  controls:['review'],vendor_sandbox:null};
"""


@pytest.mark.parametrize("locale,meaning", [
    ("en", "Only read-only tasks run in isolation; editing tasks are not supported."),
    ("ru", "В изоляции доступны только задачи чтения; изменение файлов не поддерживается."),
])
def test_real_parser_and_people_keep_read_only_provider_quota_and_explain_it(locale, meaning):
    answer = run_js(DOM + _ROW + """
      const snapshot={binding_ids:['thin'],account_status:'unknown',source:'fake',
        observed_at:'2026-10-30T12:00:00Z',freshness:'current',state:'observed',reason:null,
        windows:[{limit_id:'weekly',window_id:'week',used_percent:37,remaining_percent:63,
              duration_minutes:10080,starts_at:null,
              resets_at:'2026-11-04T07:58:09Z',freshness:'current'}]};
      const state={locale:d,providers:[row],agents:{phase:'ready',participants:[]},
        quotas:{phase:'ready',payload:{providers:[row],snapshots:[snapshot],
          as_of:'2026-10-30T12:00:00Z',max_age_seconds:300}}};
      const before=JSON.stringify(state), mount=new E('main');
      people.mountAgents(mount,state,{refreshQuotas:()=>{},refreshAgents:()=>{}});
      console.log(JSON.stringify({roads:m.projectProviders([row]).map(r=>r.taskRoad),
        text:mount.textContent,unchanged:before===JSON.stringify(state),
        chips:all(mount).filter(n=>typeof n.className==='string'
          &&n.className.startsWith('studio-chip ')).map(n=>[n.className,n.textContent])}));
    """, {"m": "studio-model.js", "people": "studio-people.js"}, locale)
    assert answer["roads"] == ["review_only"]
    assert meaning in answer["text"]
    assert "63%" in answer["text"]
    assert "refresh" in answer["text"]
    assert any("wait" in css and "review_only" in text for css, text in answer["chips"])
    assert answer["unchanged"]


def test_wizard_read_only_is_owner_only_and_never_doer_or_checker():
    answer = run_js(_ROW + """
      const thin={...row,offered:true,task_channel:{channel:'file'},
        controls:['dispatch','review']};
      const full={...thin,provider_id:'full',task_road:'boundary'};
      const analysis={role_id:'analysis',needs:['review'],verifies:[]};
      const doer={role_id:'do',needs:['dispatch'],verifies:[]};
      const checker={role_id:'checker',needs:['review'],verifies:['do']};
      const rows=[thin,full], roster=w.rosterOf(rows);
      const quotas={snapshots:[['thin',99],['full',10]].map(([id,remaining])=>({
        binding_ids:[id],state:'observed',freshness:'current',windows:[{
          freshness:'current',remaining_percent:remaining}]}))};
      const choose=(role,providers,previous={},fixed={})=>{
        const result=w.suggest([role],providers,quotas,previous,{fixed});
        return [result.assignment[role.role_id],result.by[role.role_id]];
      };
      console.log(JSON.stringify({road:roster[0].taskRoad,
        offers:[analysis,doer,checker].map(role=>w.offersFor(role,roster).map(r=>r.id)),
        owner:choose(analysis,rows,{}, {analysis:'thin'}),
        previous:choose(analysis,rows,{analysis:'thin'}),
        ranked:choose(analysis,rows),alone:choose(analysis,[thin]),
        doer:choose(doer,rows,{}, {do:'thin'}),
        checker:choose(checker,rows,{}, {checker:'thin'}),
        ordinary:choose(analysis,rows,{analysis:'full'})}));
    """, {"w": "desk-wizard-roles.js"})
    assert answer == {"road": "review_only", "offers": [["thin", "full"], ["full"], ["full"]],
                      "owner": ["thin", "owner"], "previous": ["full", "suggestion"],
                      "ranked": ["full", "suggestion"], "alone": [None, None],
                      "doer": ["full", "suggestion"], "checker": ["full", "suggestion"],
                      "ordinary": ["full", "previous"]}
