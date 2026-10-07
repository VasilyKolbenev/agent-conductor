"""Language changes presentation only, never frozen history or authority."""
import pytest
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.response_locale import language_for, localize_criteria
from conductor.command.success_criteria import for_document
from conductor.command.graph_template import TemplateNode
from tests.test_command_http_api import PORT, TOKEN, get_headers
from tests.test_command_workflow_draft import a_document
from tests.test_policy_runtime import setup


@pytest.mark.parametrize("header,expected", [('', 'en'), ('ru-RU, en;q=0.8','ru'),
    ('ru;q=0,en;q=1','en'), ('ru;q=NaN,en','en'), ('ru;q=bad,en','en')])
def test_language_negotiation_is_bounded_and_defaults_to_english(header,expected):
    assert language_for([('Accept-Language',header)]) == expected


def test_russian_run_read_preserves_immutable_material_and_effect_counts(tmp_path):
    f=setup(tmp_path,checker=True)
    api=CommandApi(f.store,f.registry,session=CommandSession(PORT,TOKEN),
        clock=f.policy.clock,ids=f.runtime._ids,budget=f.policy.budget,publish_run=lambda run: None)
    before=f.store.read('run').records
    english=api.handle('GET','/command/runs/run',get_headers())
    russian=api.handle('GET','/command/runs/run',(*get_headers(),('Accept-Language','ru')))
    again=api.handle('GET','/command/runs/run',get_headers())
    assert english.status == russian.status == 200
    assert again.payload == english.payload
    assert russian.payload['graph']['success_criteria']['do'][0]['text'].startswith('Результат')
    assert english.payload['graph']['success_criteria']['do'][0]['text'].startswith('The result')
    for key in ('run','records','config'):
        assert russian.payload[key] == english.payload[key]
    assert russian.payload['graph']['definition'] == english.payload['graph']['definition']
    assert f.store.read('run').records == before and f.adapter.execute_calls == 0


def test_workflow_response_translates_only_derived_criteria():
    document=a_document()
    nodes=tuple(TemplateNode.from_dict(row) for row in document['nodes'])
    payload={'draft':{'document':document},'published':None,'success_criteria':for_document(nodes)}
    russian=localize_criteria(payload,'ru')
    assert russian['draft'] == payload['draft']
    assert russian['success_criteria']['do'][0]['text'].startswith('Результат')
    assert payload['success_criteria']['do'][0]['text'].startswith('The result')
