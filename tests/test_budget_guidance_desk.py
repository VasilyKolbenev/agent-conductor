"""The assistant and the person edit the same wizard draft; no transition grants work."""
from tests.desk_wizard_node import run_js
from tests.test_desk_wizard_launch import DATA, LAUNCH, MODULES
from tests.test_project_task_draft import answers, call, installation


def test_preparation_uses_the_edited_depth_and_blocks_the_previous_card_while_changing():
    out = run_js(LAUNCH + """
      const base = ready();
      const working = {...base, guided: true};
      const prior = wiz.reduceWizard(working, {type:"launch-budget", depth:"bogus"});
      const chosen = wiz.reduceWizard(prior, {type:"launch-budget", depth:"thorough"});
      const profileAnswer = (ask) => {
        const p = freshPreview(ask.body.recommendation.depth);
        return ok(p);
      };
      function freshPreview(depth) {
        const p = moved(d.preview);
        return {...p, recommendation:{depth, status:"preliminary", base_seconds:600,
          step_count:p.terms.node_limits.length, checker_steps:0, effect_steps:0, resources:0,
          input_bytes:80, history_samples:0, history:[], limited_steps:[]}};
      }
      const advanced = {...chosen, guided: false};
      const simulation = drive(press(advanced), {preview:profileAnswer});
      const first = simulation.log.find(a => a.name === "preview");
      const changed = wiz.stepWizard(simulation.state, {type:"launch-budget", depth:"quick"});
      const ask = changed.asks.find(x=>x.name==="launch_preview");
      const tryStart = wiz.stepWizard(changed.state, {type:"launch-start"});
      const bad = drive(press(chosen), {preview:()=>ok(freshPreview("balanced"))});
      show({fresh:working.budgetDepth, invalid:prior.budgetDepth, chosen:chosen.budgetDepth,
        requested:first.body, state:simulation.state.run.phase, changed:ask?.body,
        authorized:tryStart.asks.some(x=>x.target==="automationAuthorize"),
        mismatched:bad.state.run.phase});
    """, DATA, MODULES)
    assert out == {"fresh": "balanced", "invalid": "balanced", "chosen": "thorough",
                   "requested": {"recommendation": {"depth": "thorough"}}, "state": "review",
                   "changed": {"recommendation": {"depth": "quick"}}, "authorized": False,
                   "mismatched": "refused"}


def test_project_answers_preserve_custom_depth_and_refuse_unknown_values(tmp_path):
    subject, _, _ = installation(tmp_path)
    from tests.test_project_task_draft import TASK

    key = call(subject, "open", task=TASK).payload["key"]
    original = answers()
    custom = {**original, "budgetDepth": "quick"}
    assert call(subject, "save", key=key, base=0, answers=custom).status == 200
    assert call(subject, "read", key=key).payload["answers"] == custom
    assert call(subject, "save", key=key, base=1,
                answers={**custom, "budgetDepth": "unlimited"}).status == 422
    assert call(subject, "read", key=key).payload["answers"] == custom
