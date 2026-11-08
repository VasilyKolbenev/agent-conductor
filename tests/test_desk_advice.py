"""A subscriber's reply is an editable suggestion within the draft's actual choices."""
from tests.desk_wizard_node import run_js

MODULE = {"advice": "desk-advice-run.js"}


def test_only_known_cycle_roles_and_depth_can_be_proposed():
    outcomes = run_js("""
        const input = {cycles:["published", "custom"], current_cycle:"published",
          role_options:{"role-checker":["subscribed-reviewer"]}};
        const good = {criterion:"Compare the actual changed file", question:null,
          cycle_id:"published", roles:{"role-checker":"subscribed-reviewer"}, depth:"thorough"};
        const changes=[{}, {roles:{"role-checker":"invented"}}, {authorize:true},
          {roles:{"role-secret":"subscribed-reviewer"}}, {cycle_id:"custom"}, {depth:"unlimited"},
          {cycle_id:"invented"}, {question:3}, {criterion:" "}];
        const reviewed=changes.map((patch) => {
          const content="\u0060\u0060\u0060json\\n"+JSON.stringify({...good,...patch})+"\\n\u0060\u0060\u0060";
          try {return advice.suggestionFrom(content,input).depth}
          catch(error){return error.message}
        });
        console.log(JSON.stringify(reviewed));
    """, modules=MODULE)
    assert outcomes == ["thorough"] + ["answer_invalid"] * 8


def test_request_identity_changes_with_the_task_or_inputs_and_survives_a_reload():
    observed = run_js("""
        const input={task:"Исправить счётчик",current_criterion:"zero failures"};
        const id=(task,provider,model,data)=>advice.requestFor(task,provider,model,data).id;
        const first=id("one","first","",input);
        console.log(JSON.stringify([first===id("one","first","",structuredClone(input)),
          [id("two","first","",input), id("one","other","",input),
           id("one","first","pin",input), id("one","first","",{...input,question:"A different question"})]
          .every((value)=>value!==first)]));
    """, modules=MODULE)
    assert observed == [True, True]
