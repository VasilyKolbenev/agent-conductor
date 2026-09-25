"""Native competitors and existing ProcessRunner loans; no provider is invoked."""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from conductor import ownership, ownership_native, ownership_records, ownership_transition
from conductor.command.adapters.harness_workspace import HarnessWorkspace
from conductor.command.adapters.process import CommandSpec, OwnershipError, ProcessRunner
from tests._fakeproc import fake_argv, HEARTBEAT_FILE, wait_for_int
from tests.test_project_ownership import activated
from tests.test_command_task_store import durable_bytes


def held_snapshot(root):
    """The native byte-lock intentionally denies reading its empty anchor."""
    anchor = root / ".conduct" / ".conduct-owner"
    facts = anchor.stat()
    assert facts.st_size == 0
    files = {path.relative_to(root).as_posix(): path.read_bytes()
             for path in root.rglob("*") if path.is_file() and path != anchor}
    return files, (facts.st_dev, facts.st_ino, facts.st_size)


def child(root, code):
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR") if name in os.environ}
    environment.update(PYTHONPATH=str(Path(ownership.__file__).resolve().parents[1]),
                       PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-c", code, str(root)], env=environment,
                          cwd=str(root), capture_output=True, timeout=15, check=False)


PROBE = """
import sys
from conductor.ownership import acquire_owner, OwnerRefused
try:
    with acquire_owner(sys.argv[1]):
        print('acquired')
except OwnerRefused as error:
    print(error.code)
"""


def test_real_second_process_cannot_take_live_owner_but_can_after_close(tmp_path):
    activated(tmp_path)
    with ownership.acquire_owner(tmp_path):
        refused = child(tmp_path, PROBE)
        assert refused.returncode == 0, refused.stderr
        assert refused.stdout.strip() == b"owner_busy"
    accepted = child(tmp_path, PROBE)
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == b"acquired"
    assert ownership_records.chain(tmp_path)["phase"] == "closed"


def test_reader_in_another_process_does_not_need_or_steal_ownership(tmp_path):
    activated(tmp_path)
    with ownership.acquire_owner(tmp_path):
        before = held_snapshot(tmp_path)
        result = child(tmp_path, """
import sys
from conductor.command.run_store import RunStore
from conductor.command.task_store import TaskStore
print(RunStore(sys.argv[1]).read('run-001').envelope.run_id)
print(TaskStore(sys.argv[1]).read('task-001').task_id)
""")
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [b"run-001", b"task-001"]
        assert held_snapshot(tmp_path) == before


def test_real_writer_and_recover_in_another_process_refuse_without_mutation(tmp_path):
    activated(tmp_path)
    with ownership.acquire_owner(tmp_path):
        before = held_snapshot(tmp_path)
        result = child(tmp_path, """
import sys
from conductor.command.run_store import RunStore, StoreError
store = RunStore(sys.argv[1])
try:
    store.recover('run-001')
except StoreError as error:
    print('owner_required' in str(error))
""")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == b"True"
        assert held_snapshot(tmp_path) == before


def test_direct_runner_and_workspace_have_no_effect_without_owner(tmp_path):
    activated(tmp_path)
    (tmp_path / "work").mkdir()
    runner = ProcessRunner(tmp_path)
    workspace = HarnessWorkspace(tmp_path, ".ownership-test-homes", ".ownership-test-markers")
    before = durable_bytes(tmp_path)
    with pytest.raises(OwnershipError, match="live owner"):
        runner.run(CommandSpec(argv=fake_argv(), cwd="work", timeout_seconds=5))
    with pytest.raises(OwnershipError, match="live owner"):
        workspace.claim("run-001", "action-001")
    assert runner.active_tokens() == ()
    assert durable_bytes(tmp_path) == before


def test_real_process_loan_blocks_close_until_group_retirement(tmp_path):
    activated(tmp_path)
    (tmp_path / "work").mkdir()
    runner = ProcessRunner(tmp_path)
    with ownership.acquire_owner(tmp_path) as owner:
        process = runner.start(CommandSpec(argv=fake_argv(), cwd="work",
            env={HEARTBEAT_FILE: str(tmp_path / "heartbeat")}))
        try:
            wait_for_int(tmp_path / "heartbeat")
            with pytest.raises(ownership.OwnerRefused, match="process loans"):
                owner.release()
        finally:
            runner.stop(process.token)
        owner.check()
    assert runner.active_tokens() == ()
    assert ownership_records.chain(tmp_path)["phase"] == "closed"


def test_real_completed_process_uses_existing_curated_environment(tmp_path, monkeypatch):
    activated(tmp_path)
    (tmp_path / "work").mkdir()
    monkeypatch.setenv("OWNER_TEST_UNLISTED_SECRET", "not-inherited-secret-09876123")
    script = "import os; print('OWNER_TEST_UNLISTED_SECRET' in os.environ)"
    with ownership.acquire_owner(tmp_path) as owner:
        result = ProcessRunner(tmp_path).run(CommandSpec(
            argv=[sys.executable, "-c", script], cwd="work", timeout_seconds=5))
        assert result.status == "completed" and result.exit_code == 0
        assert result.output.strip() == b"False"
        owner.check()


def test_tree_handle_really_reaches_the_existing_native_child(tmp_path, monkeypatch):
    activated(tmp_path)
    (tmp_path / "work").mkdir()
    launch = ProcessRunner._launch
    code = """
import os, sys
handle = int(sys.argv[1])
if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    assert kernel.GetFileType(handle) == 1, ctypes.get_last_error()
else:
    import stat
    assert stat.S_ISREG(os.fstat(handle).st_mode)
print('native-tree-held')
"""

    def observe(spec, cwd, environment, payload, loan):
        assert len(loan.handles) == 1
        scripted = replace(spec, argv=[sys.executable, "-c", code, str(loan.handles[0])])
        return launch(scripted, cwd, environment, payload, loan)

    monkeypatch.setattr(ProcessRunner, "_launch", staticmethod(observe))
    with ownership.acquire_owner(tmp_path):
        result = ProcessRunner(tmp_path).run(CommandSpec(
            argv=fake_argv(), cwd="work", timeout_seconds=5))
        assert result.status == "completed" and result.exit_code == 0
        assert result.output.strip() == b"native-tree-held"


def test_real_crash_without_clean_close_refuses_same_boot_reacquisition(tmp_path):
    activated(tmp_path)
    result = child(tmp_path, """
import os, sys
from conductor.ownership import acquire_owner
owner = acquire_owner(sys.argv[1])
os._exit(0)
""")
    assert result.returncode == 0, result.stderr
    assert ownership_records.chain(tmp_path)["phase"] == "opened"
    before = durable_bytes(tmp_path)
    with pytest.raises(ownership.OwnerRefused, match="recovery_required"):
        ownership.acquire_owner(tmp_path)
    with pytest.raises(ownership.OwnerRefused, match="restart the OS"):
        ownership_transition.recover(tmp_path)
    assert durable_bytes(tmp_path) == before


def test_recovery_generation_requires_changed_boot_fact_and_preserves_run_history(tmp_path, monkeypatch):
    """Controlled boot boundary tests the protocol, not an actual OS restart."""
    activated(tmp_path)
    result = child(tmp_path, """
import os, sys
from conductor.ownership import acquire_owner
owner = acquire_owner(sys.argv[1])
os._exit(0)
""")
    assert result.returncode == 0, result.stderr
    before = durable_bytes(tmp_path / "conductor.v3")
    boot = ownership_records.chain(tmp_path)["boot_id"]
    other = boot.split(":")[0] + ":11111111-2222-4333-8444-555555555555"
    assert other != boot
    monkeypatch.setattr(ownership_native, "boot_identity", lambda: other)
    recovered = ownership_transition.recover(tmp_path)
    assert recovered["phase"] == "recovered"
    assert recovered["session_id"] == recovered["recovered_session"]
    assert durable_bytes(tmp_path / "conductor.v3") == before
    with ownership.acquire_owner(tmp_path):
        assert ownership_records.chain(tmp_path)["boot_id"] == other
