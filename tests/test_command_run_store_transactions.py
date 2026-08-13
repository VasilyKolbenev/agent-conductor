"""RunStore process-local root transactions protect every journal observer."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gc
import threading
import weakref

import conductor.command.run_store as run_store_module
from conductor.command.run_store import RunStore

from tests.test_command_run_store import a_torn_run
from tests.test_command_runtime_authorize import a_proposal, a_store


def test_nested_transaction_can_read_and_append_reentrantly(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal()
    result = []

    def nested():
        with store.transaction():
            assert store.read("run-001").records == ()
            assert store.append(proposal) is True
            result.append(store.read("run-001").records[0].value)

    worker = threading.Thread(target=nested, daemon=True)
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert result == [proposal]


def test_read_waits_for_the_complete_append_transaction(tmp_path, monkeypatch):
    store = a_store(tmp_path)
    entered = threading.Event()
    read_entered = threading.Event()
    release = threading.Event()
    original = run_store_module._append_bytes
    original_replay = RunStore._replay

    def paused_append(path, payload):
        entered.set()
        assert release.wait(timeout=3)
        return original(path, payload)

    def witnessed_replay(self, run_id, *, repair):
        if not repair:
            read_entered.set()
        return original_replay(self, run_id, repair=repair)

    monkeypatch.setattr(run_store_module, "_append_bytes", paused_append)
    monkeypatch.setattr(RunStore, "_replay", witnessed_replay)
    with ThreadPoolExecutor(max_workers=2) as pool:
        append = pool.submit(store.append, a_proposal())
        assert entered.wait(timeout=3)
        read = pool.submit(RunStore(tmp_path).read, "run-001")
        assert not read_entered.wait(timeout=0.1)
        assert not read.done()
        release.set()
        assert append.result(timeout=3) is True
        recovered = read.result(timeout=3)

    assert read_entered.is_set()
    assert [row.kind for row in recovered.records] == ["action_proposal"]
    assert recovered.warnings == ()


def test_resolved_alias_stores_share_one_root_writer_gate(tmp_path, monkeypatch):
    root = tmp_path / "project"
    store = a_store(root)
    alias = root / ".." / "project"
    entered = threading.Event()
    release = threading.Event()
    original = run_store_module._append_bytes

    def paused_append(path, payload):
        entered.set()
        assert release.wait(timeout=3)
        return original(path, payload)

    monkeypatch.setattr(run_store_module, "_append_bytes", paused_append)
    with ThreadPoolExecutor(max_workers=2) as pool:
        append = pool.submit(store.append, a_proposal())
        assert entered.wait(timeout=3)
        read = pool.submit(RunStore(alias).read, "run-001")
        assert not read.done()
        release.set()
        append.result(timeout=3)
        recovered = read.result(timeout=3)

    assert recovered.records[0].kind == "action_proposal"


def test_direct_recover_writers_share_the_resolved_alias_root_gate(tmp_path, monkeypatch):
    root = tmp_path / "project"
    store, journal = a_torn_run(root)
    alias = RunStore(root / ".." / "project")
    barrier = threading.Barrier(2)
    witness = []
    original = run_store_module._append_bytes

    def racing_repair(path, payload):
        if b'"record_type":"decision"' in payload:
            try:
                barrier.wait(timeout=0.1)
            except threading.BrokenBarrierError:
                witness.append(False)
            else:
                witness.append(True)
        return original(path, payload)

    monkeypatch.setattr(run_store_module, "_append_bytes", racing_repair)
    with ThreadPoolExecutor(max_workers=2) as pool:
        recovered = [
            future.result(timeout=3) for future in (
                pool.submit(store.recover, "run-001"),
                pool.submit(alias.recover, "run-001"),
            )]

    assert witness == [False]
    assert recovered[0].records == recovered[1].records
    assert len(journal.read_bytes().splitlines()) == 1
    assert RunStore(root).read("run-001").records == recovered[0].records


def test_root_gate_identity_survives_a_waiter_then_idle_root_is_released(tmp_path):
    gc.collect()
    baseline = set(run_store_module._ROOT_GATES)
    root = tmp_path / "project"
    store = RunStore(root)
    alias = RunStore(root / ".." / "project")
    assert store._root_gate is alias._root_gate
    gate_ref = weakref.ref(store._root_gate)
    key = store.project_root
    entered = threading.Event()

    def waiter():
        with alias.transaction():
            entered.set()

    with store.transaction():
        worker = threading.Thread(target=waiter)
        worker.start()
        worker.join(timeout=0.05)
        assert not entered.is_set()
    worker.join(timeout=3)
    assert entered.is_set() and not worker.is_alive()

    del store, alias, worker
    gc.collect()
    assert gate_ref() is None
    assert key not in run_store_module._ROOT_GATES
    assert set(run_store_module._ROOT_GATES) == baseline
