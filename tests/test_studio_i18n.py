"""Closed UI messages and preferences, executed as pure JavaScript values."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"


def js(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the Studio value boundary")
    source = "\n".join(
        f"import * as {alias} from {json.dumps((PANEL / filename).as_uri())};"
        for alias, filename in [("i18n", "studio-i18n.js"),
            ("prefs", "studio-preferences.js"), ("nav", "studio-taskflow.js")])
    result = subprocess.run([node, "--input-type=module", "-e", source + "\n" + body],
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_both_catalogs_have_complete_keys_and_exact_parameters():
    result = js("""
      const good = i18n.validateMessages(i18n.MESSAGES);
      const broken = {...i18n.MESSAGES, 'task.unavailable': {en:'{id}',ru:'{other}'}};
      console.log(JSON.stringify([good, i18n.validateMessages(broken),
        i18n.validateMessages({}), Object.isFrozen(i18n.MESSAGES['task.unavailable'])]));
    """)
    assert result == [True, False, False, True]


def test_unknown_keys_locales_and_wrong_parameters_never_silently_fallback():
    result = js("""
      const calls = [()=>i18n.message('xx','nav.runs'),()=>i18n.message('ru','missing'),
        ()=>i18n.message('ru','task.unavailable'),
        ()=>i18n.message('ru','task.unavailable',{id:'x',extra:'x'}),
        ()=>i18n.message('ru','task.unavailable',{id:1})];
      console.log(JSON.stringify(calls.map(call=>{try {call();return false;} catch {return true;}})));
    """)
    assert result == [True] * 5


def test_parameters_stay_literal_data_in_both_languages():
    value = '<img src=x> $& {other} Название'
    result = js(f"console.log(JSON.stringify(i18n.LOCALES.map(lang => "
        f"i18n.message(lang,'task.unavailable',{{id:{json.dumps(value)}}}))));")
    assert result == [value + " · not available", value + " · недоступна"]


@pytest.mark.parametrize("hash_value,language,expected", [
    ("", "ru-RU", {"locale": "ru", "theme": None}),
    ("", "de-DE", {"locale": "en", "theme": None}),
    ("#lang=en&theme=dark", "ru", {"locale": "en", "theme": "dark"}),
    ("#lang=ru&theme=light", "en", {"locale": "ru", "theme": "light"}),
    ("#lang=xx&theme=bad", "ru", {"locale": "ru", "theme": None}),
    ("#lang=ru&lang=en&theme=dark&theme=light", "en", {"locale": "en", "theme": None}),
])
def test_preferences_use_closed_values_and_reject_ambiguous_hashes(hash_value, language, expected):
    assert js(f"console.log(JSON.stringify(prefs.readPreferences("
        f"{json.dumps(hash_value)},{json.dumps(language)})));") == expected


def test_preference_hash_preserves_navigation_and_roundtrips_without_domain_changes():
    result = js("""
      const state={screen:'runs',tasks:{selectedId:'task-1'},
        workflows:{selectedId:'workflow-2'},runs:{selectedId:'run-3'}};
      const before=JSON.stringify(state);
      const hash=prefs.preferenceHash(nav.navigationHash(state),{locale:'ru',theme:'dark'});
      console.log(JSON.stringify([nav.navigation(hash),prefs.readPreferences(hash,'en'),
        JSON.stringify(state)===before]));
    """)
    assert result == [{"screen": "runs", "taskId": "task-1", "workflowId": "workflow-2", "runId": "run-3"},
        {"locale": "ru", "theme": "dark"}, True]


def test_every_explicit_static_translation_key_resolves_in_both_languages():
    keys = re.findall(r'data-i18n(?:-label)?="([a-z_.]+)"',
        (PANEL / "studio.html").read_text(encoding="utf-8"))
    assert len(keys) >= 10
    rendered = js(f"console.log(JSON.stringify({json.dumps(keys)}.map(key=>"
        "i18n.LOCALES.map(locale=>i18n.message(locale,key)))));")
    assert all(len(pair) == 2 and all(pair) and pair[0] != pair[1] for pair in rendered)
