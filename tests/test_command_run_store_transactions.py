"""RunStore process-local root transactions protect every journal observer."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

import conductor.command.run_store as run_store_module
from conductor.command.run_store import RunStore

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
