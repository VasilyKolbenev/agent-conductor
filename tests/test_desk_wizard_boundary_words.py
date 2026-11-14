"""Step 5 says why the isolation was refused by the pair (`auth`, `task_road`) of the agents chosen.

The plan door refuses a step whose agent cannot be given the execution boundary with one closed
word (`service_refused`, the route `execution-boundary`), whatever the cause. The wizard
reads the selected providers' actual auth and task road. A refused subscription task should
send the owner to a compatible harness. The generic refusal remains for other configurations.

The model answers the cause (`boundaryOf`); the view draws the sentence of the language (a small
stand-in DOM, the same the Agents screen is tested with).
"""
from __future__ import annotations

import pytest

from tests.desk_wizard_node import run_js
from tests.test_desk_wizard_prepare import CHAIN, DATA

MODULES = {"wiz": "desk-wizard-model.js", "prep": "desk-wizard-prepare-view.js",
           "i18n": "studio-i18n.js"}
#: A stand-in DOM: what `element` needs and what the text of a drawn node is.
DOM = """
class E {
  constructor(tag) {this.tag = tag; this.children = []; this.attrs = {}; this.events = {};
    this.className = "";}
  set textContent(value) {this.children = [String(value)];}
  get textContent() {
    return this.children.map((one) => typeof one === "string" ? one : one.textContent).join(" ");
  }
  setAttribute(name, value) {this.attrs[name] = String(value);}
  append(...children) {this.children.push(...children);}
  addEventListener(name, call) {this.events[name] = call;}
}
globalThis.document = {createElement: (tag) => new E(tag)};
const all = (node) => [node,
  ...node.children.filter((one) => typeof one !== "string").flatMap(all)];
"""
#: The refusal the plan door gives a step whose agent has no boundary (it carries the route).
WIRE = """
const wire = {error: {code: "service_refused",
  message: "step 'build' demands sandbox route 'execution-boundary' that this build does not "
    + "provide",
  detail: {run_id: "task-t1-r1", node_id: "build", sandbox: "execution-boundary"}}};
const rowsFor = (patch) => ({...d.workflows,
  providers: d.workflows.providers.map((row) => ({...row, ...patch(row)}))});
const chosen = () => new Set(wiz.assignmentView(ready()).map((row) => row.provider));
"""
GENERAL = {
    "en": "This step needs the isolation (execution boundary), and this computer cannot give it to "
          "the agent chosen, so nothing was started. A task runs in the isolation only on Windows "
          "and only from a build installed under ...\\harnesses\\<name>\\<version>\\.",
    "ru": "Этому шагу нужна изоляция (execution boundary), а выбранному агенту этот компьютер её "
          "дать не может, поэтому ничего не запускалось. Задача исполняется в изоляции только на "
          "Windows и только из сборки, установленной в ...\\harnesses\\<имя>\\<версия>\\.",
}
LOGIN = {
    "en": "Nothing started. The selected harness cannot run this step in isolation with its "
          "subscription login. Choose a configured harness that supports this step "
          "through your subscription.",
    "ru": "Шаг не начался. Выбранный участник не может выполнить его в изоляции по подписке. "
          "Назначьте на эту роль подключённого участника, который поддерживает этот шаг "
          "по подписке.",
}


def test_the_cause_is_read_from_the_pair_of_the_agents_chosen_and_from_no_name():
    out = run_js(CHAIN + WIRE + """
      const cause = (patch) => wiz.boundaryOf(ready({workflows: rowsFor(patch)}));
      const given = chosen();
      const without = ({task_road, ...row}) => row;
      show({
        given: [...given].length,
        login: cause(() => ({auth: "subscription", task_road: "refused"})),
        key_refused: cause(() => ({auth: "api_key", task_road: "refused"})),
        covered: cause(() => ({auth: "subscription", task_road: "boundary"})),
        unstated: wiz.boundaryOf(ready({workflows: {...d.workflows,
          providers: d.workflows.providers.map(without)}})),
        others_only: cause((row) => given.has(row.provider_id)
          ? {auth: "api_key", task_road: "boundary"}
          : {auth: "subscription", task_road: "refused"}),
        one_chosen: cause((row) => given.has(row.provider_id) && row.provider_id === [...given][0]
          ? {auth: "subscription", task_road: "refused"}
          : {auth: "api_key", task_road: "boundary"}),
      });
    """, DATA, modules=MODULES)
    assert out["given"] >= 1
    assert out["login"] == "login", "every agent is a subscription whose road is refused"
    assert out["key_refused"] == "plain", "an API key that is refused is not a login's cause"
    assert out["covered"] == "plain", "a subscription whose road is a boundary is not a cause"
    assert out["unstated"] == "plain", "no fact served, no cause claimed"
    assert out["others_only"] == "plain", "an agent nobody chose cannot be the cause"
    assert out["one_chosen"] == "login", "one chosen agent is enough"


@pytest.mark.parametrize("lang", ["en", "ru"])
@pytest.mark.parametrize("pair,says", [
    ({"auth": "subscription", "task_road": "refused"}, LOGIN),
    ({"auth": "subscription", "task_road": "boundary"}, GENERAL),
    ({"auth": "api_key", "task_road": "refused"}, GENERAL)],
    ids=["subscription-refused", "subscription-boundary", "api-key-refused"])
def test_the_refusal_note_of_the_boundary_is_the_sentence_of_the_pair(lang, pair, says):
    out = run_js(DOM + CHAIN + WIRE + """
      const state = ready({workflows: rowsFor(() => d.pair)});
      const stopped = drive(press(state), {prep_run: () => refused("service_refused", wire)});
      const ctx = {wizard: stopped.state, lang: d.lang, send() {}, leave() {},
        t: (key, params) => i18n.message(d.lang, key, params)};
      const notes = prep.prepareBody(ctx).flatMap(all)
        .filter((node) => node.attrs && "data-refusal-link" in node.attrs);
      show({phase: stopped.state.run.phase, notes: notes.map((node) => node.textContent)});
    """, {**DATA, "pair": pair, "lang": lang}, modules=MODULES)
    assert out["phase"] == "refused"
    assert out["notes"] == [says[lang]]


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_the_words_of_the_boundary_no_longer_say_it_is_only_for_an_api_key(lang):
    out = run_js("""
      console.log(JSON.stringify({general: i18n.MESSAGES["wizard.chain.boundary"],
        login: i18n.MESSAGES["wizard.chain.boundary_login"]}));
    """, modules=MODULES)
    for text in (out["general"][lang], out["login"][lang]):
        assert "API key (not a subscription)" not in text
        assert "по API-ключу (не по подписке)" not in text
