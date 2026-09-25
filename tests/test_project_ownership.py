"""Real layout and direct writer guards; these tests spawn no child processes."""
from __future__ import annotations

import os

import pytest

from conductor import ownership, ownership_records as records
from conductor import ownership_transition as transition
from conductor.command import operator_config
from conductor.command.run_store import RunStore, StoreError
from conductor.command.task_store import TaskStore
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft
from tests.test_command_run_store import CONFIG, a_run, a_decision
from tests.test_command_task_store import a_task, durable_bytes
from tests.test_command_template_store import dalio
from tests.test_command_workflow_draft import a_document, SAVED_AT, WORKFLOW


def legacy(root):
    RunStore(root).create_run(a_run(), CONFIG)
    TaskStore(root).create_task(a_task())
    return root


def activated(root):
    legacy(root)
    transition.activate(root, legacy_writers_stopped=True)
    return root


def draft():
    return WorkflowDraft(workflow_id=WORKFLOW, saved_at=SAVED_AT, document=a_document())


def test_legacy_reads_and_writes_do_not_activate_or_grant_policy(tmp_path):
    legacy(tmp_path)
    before = durable_bytes(tmp_path)
    assert not ownership.is_activated(tmp_path)
    assert ownership.data_root(tmp_path) == tmp_path / "conductor"
    with pytest.raises(ownership.OwnerRefused, match="activation_required"):
        ownership.require_owner(tmp_path)
    assert durable_bytes(tmp_path) == before
    RunStore(tmp_path).append(a_decision())
    assert not (tmp_path / ".conduct").exists()


def test_activation_requires_explicit_stopped_writers_and_preserves_data(tmp_path):
    legacy(tmp_path)
    original = durable_bytes(tmp_path / "conductor")
    with pytest.raises(ownership.OwnerRefused, match="legacy_writers_must_stop"):
        transition.activate(tmp_path)
    assert not (tmp_path / ".conduct").exists()
    head = transition.activate(tmp_path, legacy_writers_stopped=True)
    assert head["phase"] == "active"
    assert durable_bytes(tmp_path / "conductor.v3") == original
    assert (tmp_path / "conductor").read_bytes() == records.fence_bytes(head["nonce"])
    with pytest.raises(OSError):
        (tmp_path / "conductor" / "runs" / "legacy-write").mkdir(parents=True)
    assert RunStore(tmp_path).read("run-001").envelope == a_run()
    assert TaskStore(tmp_path).read("task-001") == a_task()


def test_new_layout_reads_never_acquire_or_repair(tmp_path):
    activated(tmp_path)
    before = durable_bytes(tmp_path)
    assert ownership.is_activated(tmp_path)
    assert RunStore(tmp_path).read("run-001").records == ()
    with pytest.raises(ownership.OwnerRefused, match="owner_required"):
        ownership.require_owner(tmp_path)
    assert durable_bytes(tmp_path) == before


WRITERS = (
    lambda root: RunStore(root).create_run(a_run(run_id="run-002"), CONFIG),
    lambda root: RunStore(root).append(a_decision()),
    lambda root: RunStore(root).recover("run-001"),
    lambda root: TaskStore(root).create_task(a_task(task_id="task-002", work_scope="task-002")),
    lambda root: TemplateStore(root).save(dalio()),
    lambda root: TemplateStore(root).save_draft(draft()),
    lambda root: TemplateStore(root).discard_draft(WORKFLOW),
)


@pytest.mark.parametrize("write", WRITERS)
def test_every_direct_store_writer_requires_live_owner_and_works_with_it(tmp_path, write):
    activated(tmp_path)
    before = durable_bytes(tmp_path)
    with pytest.raises(StoreError, match="owner_required"):
        write(tmp_path)
    assert durable_bytes(tmp_path) == before
    with ownership.acquire_owner(tmp_path) as owner:
        assert ownership.require_owner(tmp_path / ".") is owner
        write(tmp_path)
    assert records.chain(tmp_path)["phase"] == "closed"
    with pytest.raises(StoreError, match="owner_required"):
        write(tmp_path)


def test_provider_configuration_requires_actual_root_context_and_owner(tmp_path):
    activated(tmp_path)
    target = ownership.data_root(tmp_path) / "providers.json"
    before = durable_bytes(tmp_path)
    with pytest.raises(operator_config.OperatorConfigError, match="project_context_required"):
        operator_config.save_provider_configs(target, [])
    with pytest.raises(operator_config.OperatorConfigError, match="owner_required"):
        operator_config.save_provider_configs(target, [], project_root=tmp_path)
    assert durable_bytes(tmp_path) == before
    with ownership.acquire_owner(tmp_path):
        operator_config.save_provider_configs(target, [], project_root=tmp_path)
    assert target.is_file()


def test_init_does_not_overwrite_active_fence(tmp_path):
    activated(tmp_path)
    before = durable_bytes(tmp_path)
    with pytest.raises(ownership.OwnerRefused, match="activation_present"):
        ownership.init_target(tmp_path)
    assert durable_bytes(tmp_path) == before


def test_live_owner_refuses_second_acquisition_and_release_while_borrowed(tmp_path):
    activated(tmp_path)
    with ownership.acquire_owner(tmp_path) as owner:
        with pytest.raises(ownership.OwnerRefused, match="owner_busy"):
            ownership.acquire_owner(tmp_path)
        with owner.borrow():
            with pytest.raises(ownership.OwnerRefused, match="owner_busy"):
                owner.release()
        assert ownership.require_owner(tmp_path) is owner
    assert records.chain(tmp_path)["phase"] == "closed"


def test_owner_object_is_not_authority_in_another_pid(tmp_path, monkeypatch):
    activated(tmp_path)
    with ownership.acquire_owner(tmp_path) as owner:
        actual = os.getpid()
        with monkeypatch.context() as patch:
            patch.setattr(ownership.os, "getpid", lambda: actual + 1)
            with pytest.raises(ownership.OwnerRefused, match="another process"):
                owner.check()
        owner.check()


def test_clean_restart_uses_a_new_session_without_recovery(tmp_path):
    activated(tmp_path)
    with ownership.acquire_owner(tmp_path):
        first = records.chain(tmp_path)
        RunStore(tmp_path).append(a_decision())
    with ownership.acquire_owner(tmp_path):
        second = records.chain(tmp_path)
        assert second["session_id"] != first["session_id"]
        assert second["boot_id"] == first["boot_id"]
        assert RunStore(tmp_path).read("run-001").records[-1].value == a_decision()


def test_rollback_before_any_owner_session_restores_exact_old_namespace(tmp_path):
    legacy(tmp_path)
    before = durable_bytes(tmp_path / "conductor")
    transition.activate(tmp_path, legacy_writers_stopped=True)
    transition.rollback(tmp_path, legacy_writers_stopped=True)
    assert not ownership.is_activated(tmp_path)
    assert not (tmp_path / "conductor.v3").exists()
    assert durable_bytes(tmp_path / "conductor") == before
    assert len(list(tmp_path.glob(".conduct-retired-*"))) == 1
    transition.activate(tmp_path, legacy_writers_stopped=True)
    assert ownership.is_activated(tmp_path)


def test_rollback_refuses_after_even_an_empty_owner_session(tmp_path):
    activated(tmp_path)
    with ownership.acquire_owner(tmp_path):
        pass
    before = durable_bytes(tmp_path)
    with pytest.raises(ownership.OwnerRefused, match="rollback_refused"):
        transition.rollback(tmp_path, legacy_writers_stopped=True)
    assert durable_bytes(tmp_path) == before


@pytest.mark.parametrize("phase", ["rollback_prepared", "fence_retired", "rolled_back"])
def test_interrupted_rollback_resumes_only_its_original_objects(tmp_path, monkeypatch, phase):
    activated(tmp_path)
    actual = transition.publish

    def interrupt(root, previous, **changes):
        value = actual(root, previous, **changes)
        if changes.get("phase") == phase:
            raise RuntimeError("interrupted after durable generation")
        return value

    with monkeypatch.context() as patch:
        patch.setattr(transition, "publish", interrupt)
        with pytest.raises(RuntimeError, match="interrupted"):
            transition.rollback(tmp_path, legacy_writers_stopped=True)
    transition.rollback(tmp_path, legacy_writers_stopped=True)
    assert not ownership.is_activated(tmp_path)
    assert RunStore(tmp_path).read("run-001").envelope == a_run()


def test_existing_fence_cannot_be_adopted_even_with_the_exact_nonce(tmp_path, monkeypatch):
    legacy(tmp_path)
    actual = transition._finish_activation

    def foreign(root, head, stack):
        (root / "conductor").write_bytes(records.fence_bytes(head["nonce"]))
        return actual(root, head, stack)

    monkeypatch.setattr(transition, "_finish_activation", foreign)
    with pytest.raises(ownership.OwnerRefused, match="transition_conflict"):
        transition.activate(tmp_path, legacy_writers_stopped=True)
    assert records.chain(tmp_path)["phase"] == "moved"
    before = durable_bytes(tmp_path)
    with pytest.raises(ownership.OwnerRefused):
        ownership.acquire_owner(tmp_path)
    assert durable_bytes(tmp_path) == before


def test_existing_destination_is_preserved_without_starting_transition(tmp_path):
    legacy(tmp_path)
    (tmp_path / "conductor.v3").mkdir()
    (tmp_path / "conductor.v3" / "foreign").write_bytes(b"operator data")
    before = durable_bytes(tmp_path)
    with pytest.raises(ownership.OwnerRefused, match="transition_conflict"):
        transition.activate(tmp_path, legacy_writers_stopped=True)
    assert durable_bytes(tmp_path) == before


def test_incomplete_generation_never_repairs_or_acquires(tmp_path):
    activated(tmp_path)
    (tmp_path / ".conduct" / "ownership" / "gen-00000003.json").write_bytes(b'{"schema":')
    before = durable_bytes(tmp_path)
    for read in (ownership.is_activated, ownership.data_root, ownership.acquire_owner):
        with pytest.raises(ownership.OwnerRefused, match="transition_conflict"):
            read(tmp_path)
    assert durable_bytes(tmp_path) == before
