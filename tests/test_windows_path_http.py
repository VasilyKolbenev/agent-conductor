"""Admission at actual HTTP/service doors, with standing-history controls.

No schema widening: the adversarial mutable adapters are registered first,
then made unable to prepare/execute anything. Native/process tests are elsewhere.
"""
from dataclasses import replace
import os

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.api_contracts import refusal_from_exception
from conductor.command.contracts import ContractError
from conductor.command.graph_template import GraphTemplate, RunBinding, materialize
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.service import CommandService
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from conductor.command.template_store import TemplateStore

from tests.test_command_http_api import NOW, PORT, TOKEN, ids, proposal_body, confirm_body
from tests.test_command_run_routes import a_run as run_body
from tests.test_command_run_store import a_run
from tests.test_command_schema_doubles import DeepPlanAdapter, FakeAdapter
from tests.test_command_workflow_draft import a_document
from tests.test_command_workflow_routes import contracts, post
from tests.test_windows_path_admission import tree_snapshot

RUN = 'run-admission'
WORKFLOW = 'flow-admission'
INSTANCE = 'claude-dev'
NAME_MESSAGE = ('choose an identifier without a trailing dot or space and without '
                'a reserved Windows basename such as NUL')
PATH_MESSAGE = ('shorten the identifier or move the project to a shorter path; '
                'the Windows path budget is exceeded')


def forbidden(*args, **kwargs):
    raise AssertionError('admission called mutable adapter execution/preparation')


def make_api(root, *, scope=None, opened=True, registry=None, clock=lambda: NOW):
    config = {'cycle': {'id': 'default-orbit', 'phases': ['do']},
              'instances': [{'id': INSTANCE, 'adapter': 'claude-code'}]}
    if scope is not None:
        config['task'] = {'id': 'task-held', 'work_scope': scope}
    store = RunStore(root)
    if opened:
        store.create_run(a_run(run_id=RUN, mode='confirm',
                              config_digest=snapshot_digest(config)), config)
    if registry is None:
        adapter = DeepPlanAdapter()
        registry = AdapterRegistry([adapter])
        adapter.prepare = forbidden
        adapter.execute = forbidden
        # A mutable callback with an appealing name must never be discovered.
        adapter.admit_arguments = forbidden
    templates = TemplateStore(root)
    events = []
    subject = CommandApi(store, registry, session=CommandSession(PORT, TOKEN),
                         budget=PRODUCT_COMMAND_BUDGET, clock=clock, ids=ids(),
                         publish_run=events.append, templates=templates,
                         providers=contracts())
    return subject, store, templates, events, config


def arguments(capability, item, scope=None):
    body = ({'work_item_id': item, 'target_artifact_refs': ['input'],
             'result_artifact_ref': 'review-out', 'review_profile': 'quality'}
            if capability == 'review' else
            dict(proposal_body()['arguments'], work_item_id=item))
    if scope is not None:
        body['work_scope'] = scope
    return body


def plan(capability, item, scope=None):
    document = a_document()
    document['nodes'][1]['capability'] = capability
    document['nodes'][1]['arguments'] = arguments(capability, item, scope)
    return GraphTemplate.from_dict({**document, 'template_id': WORKFLOW, 'revision': 1})


def plan_request(door, template, config):
    assignments = {'role-implementer': INSTANCE}
    if door == 'run-open':
        body = run_body(run_id=RUN, workflow_id=WORKFLOW, revision=1,
                        assignments=assignments,
                        participants=[{'instance_id': INSTANCE, 'provider_id': 'claude-code',
                                       'model': None}],
                        task_id='task-held' if 'task' in config else None)
        return '/command/runs', body
    if door == 'from-template':
        return f'/command/runs/{RUN}/graph/from-template', {
            'graph_id': 'graph-1', 'template_id': WORKFLOW, 'revision': 1,
            'assignments': assignments}
    graph = materialize(template, RunBinding.from_dict({'assignments': assignments}),
                        config, graph_id='graph-1', run_id=RUN, created_at=NOW).as_dict()
    return f'/command/runs/{RUN}/graph', {key: graph[key] for key in ('graph_id', 'nodes', 'edges')}


def assert_refused(response, code):
    message = NAME_MESSAGE if code == 'windows_name_unsafe' else PATH_MESSAGE
    assert response.status == 422, response.payload
    assert response.payload == {'error': {'code': code, 'message': message, 'detail': {}}}


@pytest.mark.parametrize('capability', ['dispatch', 'review'])
@pytest.mark.parametrize('item,scope', [('nul', None), ('last.', None), ('ok', 'last.')])
def test_http_proposal_refuses_before_append_without_mutable_adapter(tmp_path, capability, item, scope):
    subject, store, _t, events, _config = make_api(tmp_path, scope=scope)
    before = tree_snapshot(tmp_path)
    response = post(subject, f'/command/runs/{RUN}/proposals', {
        **proposal_body(), 'capability': capability,
        'arguments': arguments(capability, item, scope)})
    assert_refused(response, 'windows_name_unsafe')
    assert tree_snapshot(tmp_path) == before
    assert store.read(RUN).records == ()
    assert events == []


@pytest.mark.parametrize('door', ['graph', 'from-template', 'run-open'])
@pytest.mark.parametrize('capability', ['dispatch', 'review'])
@pytest.mark.parametrize('item', ['nul', 'last.'])
def test_every_new_plan_door_refuses_before_any_record(tmp_path, door, capability, item):
    subject, _store, templates, events, config = make_api(tmp_path, opened=door != 'run-open')
    template = plan(capability, item)
    templates.save(template)  # library values remain readable; a new plan is judged.
    path, body = plan_request(door, template, config)
    before = tree_snapshot(tmp_path)
    assert_refused(post(subject, path, body), 'windows_name_unsafe')
    assert tree_snapshot(tmp_path) == before
    assert events == []


@pytest.mark.parametrize('door', ['graph', 'from-template', 'run-open'])
def test_a_later_plan_step_is_also_judged(tmp_path, door):
    subject, _store, templates, events, config = make_api(tmp_path, opened=door != 'run-open')
    document = plan('dispatch', 'valid').as_dict()
    second = dict(document['nodes'][1], node_id='later', title='Later work',
                  arguments=arguments('dispatch', 'nul'))
    gate = dict(document['nodes'][0], node_id='later-gate',
                gate_id='gate-confirm-later', title='Confirm later work')
    document['nodes'].extend([gate, second])
    document['edges'].extend([
        {'from_node': 'do', 'to_node': 'later-gate'},
        {'from_node': 'later-gate', 'to_node': 'later'},
    ])
    template = GraphTemplate.from_dict(document)
    templates.save(template)
    path, body = plan_request(door, template, config)
    before = tree_snapshot(tmp_path)
    assert_refused(post(subject, path, body), 'windows_name_unsafe')
    assert tree_snapshot(tmp_path) == before and events == []


@pytest.mark.parametrize('door', ['graph', 'from-template', 'run-open'])
def test_valid_neighbour_plan_is_published_without_any_adapter_callback(tmp_path, door):
    subject, _store, templates, events, config = make_api(tmp_path, opened=door != 'run-open')
    template = plan('dispatch', 'null')
    templates.save(template)
    path, body = plan_request(door, template, config)
    assert post(subject, path, body).status == 201
    assert events == [RUN]


@pytest.mark.parametrize('door', ['graph', 'from-template', 'run-open'])
@pytest.mark.parametrize('capability', ['dispatch', 'review'])
def test_historical_plan_exact_repeat_uses_standing_bytes_before_new_admission(
        tmp_path, monkeypatch, door, capability):
    import conductor.command.http_api as api_module
    subject, _store, templates, _events, config = make_api(tmp_path, opened=door != 'run-open')
    template = plan(capability, 'last.')
    templates.save(template)
    path, body = plan_request(door, template, config)
    with monkeypatch.context() as prior:
        prior.setattr(api_module, 'admit_new_work', lambda *a, **kw: None)
        created = post(subject, path, body)
        assert created.status == 201, created.payload
    before = tree_snapshot(tmp_path)
    fresh, _s, _t, events, _c = make_api(tmp_path, opened=False,
                                       registry=AdapterRegistry([]),
                                       clock=lambda: '2099-01-01T00:00:00Z')
    repeated = post(fresh, path, body)
    assert repeated.status == 200, repeated.payload
    assert repeated.payload == created.payload
    assert tree_snapshot(tmp_path) == before and events == []


@pytest.mark.parametrize('kind', ['task', 'run', 'template', 'draft', 'revision'])
@pytest.mark.parametrize('name', ['NUL', 'last.'])
def test_http_identity_refusal_is_clear_before_store_metadata_failure(tmp_path, kind, name):
    subject, _s, _t, events, _c = make_api(tmp_path, opened=False)
    if kind == 'task':
        path, body = '/command/tasks', {'task_id': name, 'title': 'New task'}
    elif kind == 'run':
        path, body = '/command/runs', run_body(run_id=name, workflow_id=None,
                                               revision=None, assignments={})
    elif kind == 'template':
        path, body = '/command/templates', replace(plan('dispatch', 'ok'), template_id=name).as_dict()
    elif kind == 'revision':
        path, body = f'/command/workflows/{name}/revisions', {'revision': 1, 'document': a_document()}
    else:
        path, body = f'/command/workflows/{name}/draft', {'document': a_document(), 'expected_absent': True}
    before = tree_snapshot(tmp_path)
    assert_refused(post(subject, path, body), 'windows_name_unsafe')
    assert tree_snapshot(tmp_path) == before and events == []


@pytest.mark.skipif(os.name != 'nt', reason='actual composed Windows paths')
@pytest.mark.parametrize('door', ['proposal', 'graph', 'from-template', 'run-open'])
def test_http_long_scope_item_refuses_before_new_append(tmp_path, door):
    root = tmp_path
    while len(str(root)) < 100:
        root /= 'parent'
    root.mkdir(parents=True, exist_ok=True)
    scope = 's' * 64
    subject, _s, templates, events, config = make_api(root, scope=scope, opened=door != 'run-open')
    if door == 'run-open':
        TaskStore(root).create_task(TaskRecord(task_id='task-held', title='Held task',
                                              work_scope=scope, created_at=NOW))
    template = plan('dispatch', 'i' * 128, scope)
    templates.save(template)
    if door == 'proposal':
        path, body = f'/command/runs/{RUN}/proposals', {
            **proposal_body(), 'arguments': arguments('dispatch', 'i' * 128, scope)}
    else:
        path, body = plan_request(door, template, config)
    before = tree_snapshot(root)
    assert_refused(post(subject, path, body), 'windows_path_too_long')
    assert tree_snapshot(root) == before and events == []


def test_service_itself_refuses_new_deep_work_but_does_not_impose_layout_on_other_schema(tmp_path):
    _subject, store, _t, _events, _config = make_api(tmp_path)
    deep = CommandService(store, AdapterRegistry([DeepPlanAdapter()]), clock=lambda: NOW, ids=ids())
    body = {'run_id': RUN, 'instance_id': INSTANCE, 'attempt_id': 'attempt-1',
            'capability': 'dispatch', 'arguments': arguments('dispatch', 'nul'),
            'scope': ['work'], 'proposed_by': 'owner', 'rationale': 'Admission witness', 'timeout_seconds': 30}
    before = tree_snapshot(tmp_path)
    with pytest.raises(ContractError, match='reserved Windows basename'):
        deep.propose(**body)
    assert tree_snapshot(tmp_path) == before
    legacy = CommandService(store, AdapterRegistry([FakeAdapter()]), clock=lambda: NOW, ids=ids())
    result = legacy.propose(**body)
    assert result.arguments['work_item_id'] == 'nul'
    assert len(store.read(RUN).records) == 1


def test_fresh_service_exact_historical_proposal_id_repeats_and_conflicts_as_before(tmp_path, monkeypatch):
    import conductor.command.service as service_module
    from conductor.command.store_errors import RecordConflict
    _subject, store, _t, _events, _config = make_api(tmp_path)
    registry = AdapterRegistry([DeepPlanAdapter()])
    body = {'run_id': RUN, 'instance_id': INSTANCE, 'attempt_id': 'attempt-1',
            'capability': 'dispatch', 'arguments': arguments('dispatch', 'last.'),
            'scope': ['work'], 'proposed_by': 'owner', 'rationale': 'Historical proposal',
            'timeout_seconds': 30, 'proposal_id': 'fixed-history', 'proposed_at': NOW}
    old = CommandService(store, registry, clock=lambda: NOW, ids=ids())
    with monkeypatch.context() as prior:
        prior.setattr(service_module, 'admit_new_work', lambda *a, **kw: None)
        standing = old.propose(**body)
    before = tree_snapshot(tmp_path)
    fresh = CommandService(RunStore(tmp_path), registry, clock=forbidden, ids=forbidden)
    assert fresh.propose(**body) == standing
    with pytest.raises(RecordConflict):
        fresh.propose(**{**body, 'rationale': 'Conflicting facts under the same ID'})
    assert tree_snapshot(tmp_path) == before


def test_fixed_http_refusals_discard_even_a_typed_exceptions_arbitrary_prose():
    from conductor.command.path_admission import WindowsNameError, WindowsPathError
    for kind, code in ((WindowsNameError, 'windows_name_unsafe'),
                       (WindowsPathError, 'windows_path_too_long')):
        refused = refusal_from_exception(kind('secret C:/private/account/API_KEY_VALUE'))
        assert refused.status == 422 and refused.code == code
        rendered = str(refused.as_dict())
        assert 'secret' not in rendered and 'private' not in rendered and 'API_KEY_VALUE' not in rendered


@pytest.mark.parametrize('capability', ['dispatch', 'review'])
@pytest.mark.parametrize('again_at', [NOW, '2099-01-01T00:00:00Z'])
def test_historical_authorized_request_exact_http_repeat_never_mints_a_grant(
        tmp_path, monkeypatch, capability, again_at):
    import conductor.command.service as service_module
    from conductor.command.runtime_values import ExecutionError
    from tests.test_command_runtime_authorize import a_confirmation
    registry = AdapterRegistry([DeepPlanAdapter()])
    old, _s, _t, _events, _config = make_api(tmp_path, registry=registry)
    with monkeypatch.context() as prior:
        prior.setattr(service_module, 'admit_new_work', lambda *a, **kw: None)
        response = post(old, f'/command/runs/{RUN}/proposals', {
            **proposal_body(), 'capability': capability,
            'arguments': arguments(capability, 'last.')})
        assert response.status == 201, response.payload
        confirmed = post(old, f'/command/runs/{RUN}/actions', confirm_body(response.payload))
        assert confirmed.status == 201, confirmed.payload
    before = tree_snapshot(tmp_path)
    fresh, store, _t, events, _config = make_api(
        tmp_path, opened=False, registry=registry, clock=lambda: again_at)
    repeated = post(fresh, f'/command/runs/{RUN}/actions', confirm_body(response.payload))
    assert repeated.status == 200 and repeated.payload == confirmed.payload
    proposal = next(row.value for row in store.read(RUN).records if row.kind == 'action_proposal')
    authorization = fresh.runtime.authorize(
        a_confirmation(proposal, confirmed_at=again_at), budget=PRODUCT_COMMAND_BUDGET)
    assert authorization.record_created is False
    with pytest.raises(ExecutionError, match='no live execution grant'):
        fresh.runtime.execute(authorization)
    assert tree_snapshot(tmp_path) == before and events == []
