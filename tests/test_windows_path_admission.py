"""New filesystem admission refuses before effects; history keeps its grammar.

Prepared, not run. The Windows integration cases use actual directories rather
than a mocked os.name. PureWindowsPath cases pin the UTF-16 boundaries on any OS.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path, PureWindowsPath
import stat

import pytest

from conductor.command import run_store, task_store, template_store
from conductor.command.adapters.base import PreparedAction
from conductor.command.adapters.deep_commands import DeepDispatchArgs, DeepReviewArgs
from conductor.command.adapters.harness_workspace import HarnessWorkspace, WorkspaceNotContained
from conductor.command.contracts import ContractError, _id
from conductor.command.graph_template import GraphTemplate, load_template
from conductor.command.run_store import RunStore
from conductor.command.store_errors import StoreError
from conductor.command.task_store import TaskStore
from conductor.command.template_store import TemplateStore, RevisionConflict
from conductor.command.workflow_draft import WorkflowDraft

from tests.test_command_task_store import a_task
from tests.test_command_run_store import a_run as envelope, CONFIG
from tests.test_command_run_routes import a_run as run_body
from tests.test_command_workflow_draft import a_document
from tests.test_command_workflow_routes import api, post, NOW
from tests.test_command_codex_transport import a_harness, a_request


BAD = ('edge.', 'NUL', 'nul.txt', 'Con', 'LPT9.log', 'com1')
GOOD = ('edge.ok', 'null', 'nulled', 'console', 'COM10', 'com1-task')


def tree_snapshot(root):
    """Exact root/entry kinds and bytes, including a missing or empty root."""
    if not root.exists():
        return {'.': ('missing',)}
    rows = {}
    for path in [root, *sorted(root.rglob('*'))]:
        mode = path.lstat().st_mode
        name = path.relative_to(root).as_posix()
        if stat.S_ISDIR(mode):
            rows[name] = ('directory',)
        elif stat.S_ISREG(mode):
            rows[name] = ('file', path.read_bytes())
        else:
            raise AssertionError(f'fixture contains an unsupported entry: {name}')
    return rows


def test_tree_snapshot_observes_empty_directories_and_same_size_byte_changes(tmp_path):
    root = tmp_path / 'snapshot-root'
    assert tree_snapshot(root) == {'.': ('missing',)}
    root.mkdir()
    assert tree_snapshot(root) == {'.': ('directory',)}
    (root / 'empty').mkdir()
    directories = {'.': ('directory',), 'empty': ('directory',)}
    assert tree_snapshot(root) == directories
    (root / 'payload').write_bytes(b'a')
    first = tree_snapshot(root)
    assert first == {**directories, 'payload': ('file', b'a')}
    (root / 'payload').write_bytes(b'b')
    assert tree_snapshot(root) == {**directories, 'payload': ('file', b'b')}
    assert tree_snapshot(root) != first


def revision(name):
    return replace(load_template('dalio-v1'), template_id=name)


def draft(name):
    return WorkflowDraft(workflow_id=name, saved_at=NOW, document=a_document())


def create(kind, root, name):
    if kind == 'task':
        return TaskStore(root).create_task(a_task(task_id=name, work_scope=name))
    if kind == 'run':
        return RunStore(root).create_run(envelope(run_id=name), CONFIG)
    if kind == 'revision':
        return TemplateStore(root).save(revision(name))
    return TemplateStore(root).save_draft(draft(name))


@pytest.mark.parametrize('kind', ('task', 'run', 'revision', 'draft'))
@pytest.mark.parametrize('name', BAD)
def test_new_store_names_refuse_before_any_mkdir_or_stage(tmp_path, monkeypatch, kind, name):
    calls = []
    mkdir = Path.mkdir

    def counted(path, *args, **kwargs):
        calls.append(path)
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', counted)
    with pytest.raises(ContractError, match='(dot or space|reserved Windows basename)') as refusal:
        create(kind, tmp_path, name)
    assert calls == [], 'an invalid identity reached the first mkdir'
    assert list(tmp_path.iterdir()) == []
    assert str(tmp_path) not in str(refusal.value)


@pytest.mark.parametrize('kind', ('task', 'run', 'revision', 'draft'))
@pytest.mark.parametrize('name', GOOD)
def test_valid_neighbours_publish_actual_files_with_exact_names(tmp_path, kind, name):
    create(kind, tmp_path, name)
    if kind == 'task':
        assert TaskStore(tmp_path).read(name).task_id == name
        assert TaskStore(tmp_path).tasks() == (name,)
    elif kind == 'run':
        assert RunStore(tmp_path).read(name).envelope.run_id == name
    elif kind == 'revision':
        assert TemplateStore(tmp_path).load(name, 1).template_id == name
    else:
        assert TemplateStore(tmp_path).load_draft(name).workflow_id == name


@pytest.mark.parametrize('item,scope', [('nul', None), ('ok', 'task.'), ('ok.', 'task')])
def test_work_admission_precedes_work_root_mkdir(tmp_path, monkeypatch, item, scope):
    space = HarnessWorkspace.at(tmp_path, home_dir='homes', marker_dir='markers')
    calls = []
    mkdir = Path.mkdir

    def counted(path, *args, **kwargs):
        calls.append(path)
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', counted)
    with pytest.raises(ContractError, match='(dot or space|reserved Windows basename)'):
        space.work_dir(item, scope)
    assert calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('name', GOOD)
def test_work_paths_keep_exact_positive_names(tmp_path, name):
    space = HarnessWorkspace.at(tmp_path, home_dir='homes', marker_dir='markers')
    path = space.work_dir(name, 'task-ok')
    assert path.is_dir()
    assert path.name == name
    assert path.relative_to(tmp_path).as_posix() == 'work/_tasks/task-ok/' + name


def test_work_budget_counts_utf16_and_room_for_final_separator():
    from conductor.command.path_admission import admit_work_path
    # The scalar count would accept the failing path; UTF-16 has two units per emoji.
    base = PureWindowsPath('C:/') / ('😀' * 110)
    good = base / ('x' * 34)
    bad = base / ('x' * 35)
    assert len(str(good).encode('utf-16-le')) // 2 == 258
    assert len(str(bad).encode('utf-16-le')) // 2 == 259
    admit_work_path(good, 'ok', None)
    with pytest.raises(ContractError, match='Windows path budget'):
        admit_work_path(bad, 'ok', None)


def test_file_budget_includes_actual_private_temp_name():
    from conductor.command.path_admission import admit_file
    parent = PureWindowsPath('C:/') / ('p' * 222)
    good = parent / ('x' * 19)
    bad = parent / ('x' * 20)
    assert len(str(good)) < 259 and len(str(bad)) < 259
    admit_file(good, 'file')
    with pytest.raises(ContractError, match='Windows path budget'):
        admit_file(bad, 'file')


def test_supported_tempfile_suffix_matches_real_store_staging(tmp_path, monkeypatch):
    """The path reserve is a witnessed dependency on supported CPython tempfile."""
    import tempfile
    from conductor.command import run_files
    made = []
    real_file, real_directory = tempfile.mkstemp, tempfile.mkdtemp

    def file_stage(*args, **kwargs):
        fd, path = real_file(*args, **kwargs)
        made.append((Path(path).name, kwargs['prefix'], kwargs.get('suffix', '')))
        return fd, path

    def directory_stage(*args, **kwargs):
        path = real_directory(*args, **kwargs)
        made.append((Path(path).name, kwargs['prefix'], kwargs.get('suffix', '')))
        return path

    monkeypatch.setattr(tempfile, 'mkstemp', file_stage)
    monkeypatch.setattr(tempfile, 'mkdtemp', directory_stage)
    TaskStore(tmp_path).create_task(a_task())
    assert len(made) == 2, made
    for name, prefix, suffix in made:
        assert name.startswith(prefix) and name.endswith(suffix)
        assert len(name) - len(prefix) - len(suffix) == 8


def test_standing_store_directories_keep_exists_before_new_creation_policy(tmp_path, monkeypatch):
    from conductor.command.run_store import RunExists
    from conductor.command.task_store import TaskExists
    from conductor.command.path_admission import WindowsPathError
    runs, tasks = RunStore(tmp_path), TaskStore(tmp_path)
    runs.create_run(envelope(), CONFIG)
    tasks.create_task(a_task())
    before = tree_snapshot(tmp_path)

    def newer_budget(*args, **kwargs):
        raise WindowsPathError('new stricter path budget')

    monkeypatch.setattr(RunStore, 'admit_run_creation', newer_budget)
    monkeypatch.setattr(TaskStore, 'admit_task_creation', newer_budget)
    with pytest.raises(RunExists):
        runs.create_run(envelope(), CONFIG)
    with pytest.raises(TaskExists):
        tasks.create_task(a_task())
    assert tree_snapshot(tmp_path) == before


def test_cli_preview_translates_the_new_typed_creation_refusal(tmp_path, monkeypatch):
    from conductor.command.path_admission import WindowsPathError
    from conductor.command.preview import PreviewError, render_dispatch_preview

    def refusal(*args, **kwargs):
        raise WindowsPathError('Windows path budget exceeded')

    monkeypatch.setattr(RunStore, 'create_run', refusal)
    with pytest.raises(PreviewError, match='Windows path budget'):
        render_dispatch_preview(str(tmp_path))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != 'nt', reason='actual Windows preview creation budget')
def test_cli_preview_overlong_root_refuses_before_creating_any_store(tmp_path):
    from conductor.command.preview import PreviewError, render_dispatch_preview
    root = tmp_path
    while len(str(root)) < 208:
        root /= 'parent'
    root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(PreviewError):
        render_dispatch_preview(str(root))
    assert list(root.iterdir()) == []


@pytest.mark.skipif(os.name != 'nt', reason='actual Windows filesystem/cwd paths')
def test_scope_plus_item_too_long_refuses_before_first_filesystem_effect(tmp_path, monkeypatch):
    # Root remains a real, ordinary directory; only the composed work path is long.
    root = tmp_path
    while len(str(root)) < 100:
        root = root / 'ordinary-parent'
    root.mkdir(parents=True, exist_ok=True)
    space = HarnessWorkspace.at(root, home_dir='homes', marker_dir='markers')
    before = tree_snapshot(tmp_path)
    effects = []
    mkdir = Path.mkdir

    def counted(path, *args, **kwargs):
        effects.append(path)
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', counted)
    with pytest.raises(ContractError, match='Windows path budget'):
        space.work_dir('i' * 128, 's' * 64)
    assert effects == []
    assert tree_snapshot(tmp_path) == before


@pytest.mark.skipif(os.name != 'nt', reason='actual Windows creation/staging budget')
@pytest.mark.parametrize('kind', ('task', 'run', 'revision', 'draft'))
def test_overlong_store_path_refuses_before_conductor_directory(tmp_path, kind):
    root = tmp_path
    while len(str(root)) < 190:
        root = root / 'ordinary-parent'
    root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ContractError, match='Windows path budget'):
        create(kind, root, 'n' * 64)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize('capability', ('dispatch', 'review'))
def test_prepare_and_forged_prepared_both_refuse_before_sweep_or_version(tmp_path, monkeypatch, capability):
    adapter, root, log = a_harness(tmp_path)
    body = ({'work_item_id': 'nul', 'target_artifact_refs': ['input-1'],
             'result_artifact_ref': 'review-out', 'review_profile': 'quality'}
            if capability == 'review' else
            dict(a_request().as_dict()['arguments'], work_item_id='nul'))
    request = a_request(capability=capability, arguments=body)
    # Legacy values still parse; execution admission, not reading, refuses them.
    (DeepReviewArgs if capability == 'review' else DeepDispatchArgs).from_dict(body)
    before = tree_snapshot(root)
    calls = []

    def must_not_reach(*args, **kwargs):
        calls.append('effect')
        raise AssertionError('reached sweep, materialization or version probe')

    monkeypatch.setattr(type(adapter._workspace), 'sweep_homes', must_not_reach)
    monkeypatch.setattr(adapter, '_preflight', must_not_reach)
    monkeypatch.setattr(adapter, '_bound_instruction', must_not_reach)
    with pytest.raises(ContractError, match='reserved Windows basename'):
        adapter.prepare(request)
    prepared = PreparedAction(adapter_id=adapter.manifest.adapter_id,
                              request=request, adapter_payload=body)
    with pytest.raises(ContractError, match='reserved Windows basename'):
        adapter.execute(prepared)
    assert calls == []
    assert not log.exists()
    assert tree_snapshot(root) == before


@pytest.mark.parametrize('kind', ('task', 'run'))
def test_historical_trailing_dot_http_exact_repeat_survives_fresh_api(tmp_path, monkeypatch, kind):
    name = 'historical.'
    assert _id('history', name) == name
    subject, store, templates, events = api(tmp_path)
    route = '/command/tasks' if kind == 'task' else '/command/runs'
    body = ({'task_id': name, 'title': 'Historical task'} if kind == 'task' else
            run_body(run_id=name, workflow_id=None, revision=None, assignments={}))
    # The production writer with only the newly introduced admission removed.
    with monkeypatch.context() as old:
        module = task_store if kind == 'task' else run_store
        old.setattr(module, 'admit_directory', lambda *a, **kw: None)
        if kind == 'task':
            old.setattr(module, 'admit_name', lambda *a, **kw: None)
        created = post(subject, route, body)
        assert created.status == 201, created.payload
    before = tree_snapshot(tmp_path)
    fresh, _s, _t, fresh_events = api(tmp_path, clock=lambda: '2099-01-01T00:00:00Z')
    repeated = post(fresh, route, body)
    assert repeated.status == 200, repeated.payload
    assert repeated.payload == created.payload
    assert tree_snapshot(tmp_path) == before
    assert fresh_events == []


def test_historical_template_and_draft_read_repeat_do_not_stage(tmp_path, monkeypatch):
    name = 'historical.'
    template, drawing = revision(name), draft(name)
    with monkeypatch.context() as old:
        old.setattr(template_store, 'admit_name', lambda *a, **kw: None)
        old.setattr(template_store, 'admit_file', lambda *a, **kw: None)
        store = TemplateStore(tmp_path)
        assert store.save(template).created
        assert store.save_draft(drawing).created
    before = tree_snapshot(tmp_path)
    fresh = TemplateStore(tmp_path)
    assert fresh.load(name, 1) == template
    assert fresh.load_draft(name) == drawing
    effects = []

    def forbidden(*args, **kwargs):
        effects.append('write')
        raise AssertionError('historical repeat reached staging')

    monkeypatch.setattr(template_store, '_exclusive_bytes', forbidden)
    monkeypatch.setattr(template_store, '_replace_bytes', forbidden)
    assert not fresh.save(template).created
    assert not fresh.save_draft(drawing).created
    with pytest.raises(RevisionConflict):
        fresh.save(replace(template, title='Contradict the existing revision'))
    with pytest.raises(ContractError, match='dot or space'):
        fresh.save(replace(template, revision=2))
    with pytest.raises(ContractError, match='dot or space'):
        fresh.save_draft(replace(drawing, saved_at='2099-01-01T00:00:00Z',
                                 document=drawing.settled()))
    assert effects == []
    assert tree_snapshot(tmp_path) == before
