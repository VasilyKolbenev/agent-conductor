"""A sentence the window has already said switches with the language, because it is stored as a key.

The store keeps `{key, params}` -- never a rendered sentence -- for its status, save and task
notices and for a drawing's local problems, and every renderer says them in the reader's language
when it draws them. Identifiers and a person's own words stay parameters and are never translated.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tests.studio_source_messages import message_english
from tests.test_studio_agents_i18n import DOM

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"


def _node(body: str) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the Studio renderers")
    source = "\n".join(f"import * as {alias} from {json.dumps((PANEL / name).as_uri())};" for alias, name in (
        ("store", "studio-store.js"), ("shell", "studio-shell.js"), ("i18n", "studio-i18n.js")))
    source += DOM + "\nObject.defineProperty(E.prototype,'classList',{get(){return {add(){},remove(){},toggle(){}};}});\n" + body
    result = subprocess.run([node, "--input-type=module", "-e", source], capture_output=True, text=True,
                            encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_status_line_says_a_stored_notice_in_the_language_it_is_drawn_in():
    got = _node("""
      const mounts = () => ({main: new E('main'), project: new E('p'), connection: new E('p'), primary: new E('div'),
        tabs: [], screens: {}, states: {}, translatedText: [], translatedLabels: [], title: new E('title'), status: new E('p')});
      let state = store.reduce(store.EMPTY, {type: 'status', notice: {key: 'notice.task_created', params: {title: 'Мой <b> task'}}});
      const said = (locale) => { const m = mounts(); m.main.dataset = {}; shell.mountShell(m, {...state, locale}, {});
        return m.status.textContent; };
      const first = {en: said('en'), ru: said('ru')};
      state = store.reduce(state, {type: 'connection', state: 'closed'});
      const closed = {en: said('en'), ru: said('ru')};
      console.log(JSON.stringify({first, closed, stored: JSON.stringify(state.notice)}));
    """)
    assert got["first"]["en"] == "Task “Мой <b> task” was created."
    assert got["first"]["ru"] == "Задача «Мой <b> task» создана."
    assert got["closed"]["en"] == message_english("notice.connection_lost")
    assert got["closed"]["ru"].startswith("Связь потеряна.")
    # What the store holds is the key, never the English sentence.
    assert "notice.connection_lost" in got["stored"] and "Connection lost" not in got["stored"]


def test_a_drawings_local_problems_are_keys_with_their_step_and_switch_whole():
    got = _node("""
      const problems = store.saveProblems({title: '', nodes: [{node_id: 'bad id!', title: '', kind: 'task'},
        {node_id: 'review', title: 'Review', kind: 'task', role_id: 'checker'}], edges: []});
      const say = (locale) => problems.map((row) => i18n.noticeText({locale}, row));
      console.log(JSON.stringify({en: say('en'), ru: say('ru'), stored: JSON.stringify(problems)}));
    """)
    assert got["en"] == [
        "This workflow needs a name.",
        message_english("notice.problem_id_grammar"),
        "Step a step needs a display name.",
        message_english("notice.problem_half_binding").replace("{step}", "review"),
    ]
    assert got["ru"][2] == "Шагу шаг нужно отображаемое имя." and "review" in got["ru"][3]
    assert all(en != ru for en, ru in zip(got["en"], got["ru"]))
    assert "needs a name" not in got["stored"] and "notice.problem_workflow_name" in got["stored"]


def _error_labels() -> dict:
    source = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    block = source[source.index("export const ERROR_LABELS = Object.freeze({"):]
    block = block[:block.index("\n});")]
    labels = {}
    for code, spelled in re.findall(r'^  ([a-z_]+): ((?:"[^"]*"(?:\s*\+\s*)?)+),?$', block, re.M):
        labels[code] = "".join(re.findall(r'"([^"]*)"', spelled))
    return labels


def test_every_refusal_code_a_door_can_send_has_the_same_sentence_in_the_studio_catalogue():
    labels = _error_labels()
    assert len(labels) >= 20, "control: the shared refusal table was read whole"
    for code, sentence in labels.items():
        assert message_english(f"error.{code}") == sentence, code


#: How a module would slip an English sentence back into a stored notice: a non-empty literal
#: given to a notice field, to the status reducer, to a problem list or to the status callback.
_LITERAL_NOTICE = (
    re.compile(r"""\bnotice:\s*(?:["'`][^"'`\n]*\s|[A-Z_]{3,}\b(?!\s*\())"""),
    re.compile(r"""\bspoken\(state,\s*["'`]"""),
    re.compile(r"""\bfound\.push\(\s*["'`]"""),
    re.compile(r""""onStatus",\s*(?:localize|L)\("""),
)
#: Constants that name a key object, declared in the module that says them.
_KEY_CONSTANT = re.compile(r"const ([A-Z_]{3,}) = Object\.freeze\(\{key: ")


def _literal_notices(source: str) -> list[str]:
    keys = set(_KEY_CONSTANT.findall(source)) | {"DECIDED"}
    found = []
    for pattern in _LITERAL_NOTICE:
        for hit in pattern.finditer(source):
            word = re.match(r"notice:\s*([A-Z_]{3,})", hit.group(0))
            if word and word.group(1) in keys:
                continue
            found.append(source[max(0, hit.start() - 30):hit.end() + 30].replace("\n", " "))
    return found


def test_no_studio_module_stores_a_rendered_sentence_as_a_notice():
    offenders = {path.name: _literal_notices(path.read_text(encoding="utf-8"))
                 for path in sorted(PANEL.glob("studio*.js"))}
    assert {name: rows for name, rows in offenders.items() if rows} == {}


@pytest.mark.parametrize("sabotage", [
    'dispatch({type: "status", notice: "Something happened."});',
    'return spoken(state, "A sentence.");',
    'found.push("This workflow needs a name.");',
    'call(form.handlers, "onStatus", localize(form.state, "workflow.copy_57"));',
])
def test_the_literal_notice_guard_goes_red_on_each_way_back(sabotage):
    assert _literal_notices(sabotage), sabotage
