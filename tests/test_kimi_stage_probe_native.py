"""Exercise the real isolated-process lab interface. Credentials here are synthetic."""
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Windows handle-relative stage and recovery")
ROOT = Path(__file__).resolve().parents[1]
ID = "02468ace02468ace02468ace02468ace"


def probe(base, verb):
    command, env = interface(base, verb)
    return subprocess.run(command, env=env, capture_output=True, check=False, timeout=30)


def interface(base, verb):
    env = dict(os.environ, TEMP=str(base), TMP=str(base), PYTHONPATH=str(ROOT / "src"))
    return [sys.executable, str(ROOT / "scripts/kimi_stage_probe.py"), verb, ID], env


def layout(base):
    return base / ("dc-kimi-stage-" + ID) / "DecemberCommand" / "relay"


def test_proof_stages_holds_and_retires_a_real_tree(tmp_path):
    reply = probe(tmp_path, "run")
    assert reply.returncode == 0, reply.stderr
    assert json.loads(reply.stdout) == {"status": "retired", "checked": True}
    root = layout(tmp_path)
    assert sorted(p.name for p in root.iterdir()) == ["stage-record.jsonl"]
    ledger = (root / "stage-record.jsonl").read_bytes()
    assert b"synthetic-stage-access" not in ledger and b"access_token" not in ledger
    assert probe(tmp_path, "recover").returncode == 0


def test_interrupt_in_another_process_recovers_once(tmp_path):
    assert probe(tmp_path, "interrupt").returncode == 75
    root = layout(tmp_path)
    assert b"synthetic-stage-access" in (root / "attempt/credentials/kimi-code.json").read_bytes()
    assert probe(tmp_path, "recover").returncode == 0
    assert not (root / "attempt").exists() and probe(tmp_path, "recover").returncode == 0


def test_pending_directory_deletion_is_not_recorded_as_completed(tmp_path):
    from conductor import ownership_native
    assert probe(tmp_path, "interrupt").returncode == 75
    root = layout(tmp_path)
    # A reader shares DELETE, so the owned handle may mark the directory for deletion.
    # Windows may retain its entry until this reader finally releases its own handle.
    kernel = ownership_native._k32
    reader = kernel.CreateFileW(str(root / "attempt"), 0x80, 7, None, 3, 0x02200000, None)
    assert reader not in (None, ownership_native._invalid)
    try:
        reply = probe(tmp_path, "recover")
        assert reply.returncode == 3
        assert b'["retired"]' not in (root / "stage-record.jsonl").read_bytes()
    finally:
        kernel.CloseHandle(reader)
    assert probe(tmp_path, "recover").returncode == 0 and not (root / "attempt").exists()


def test_an_independent_observer_cannot_replace_any_object_during_handover(tmp_path):
    command, env = interface(tmp_path, "hold")
    with subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE) as child:
        line = Queue()
        Thread(target=lambda: line.put(child.stdout.readline()), daemon=True).start()
        try:
            assert line.get(timeout=15).strip() == b'{"status": "held"}'
            root = layout(tmp_path)
            for relative in ("attempt", "attempt/config.toml", "attempt/credentials",
                             "attempt/credentials/kimi-code.json"):
                item = root / relative
                with pytest.raises(PermissionError):
                    item.rename(item.with_name("replaced"))
            out, err = child.communicate(b"release\n", timeout=15)
            assert child.returncode == 0 and json.loads(out)["status"] == "retired", err
            assert not (root / "attempt").exists()
        finally:
            if child.poll() is None:
                child.kill()


@pytest.mark.parametrize("case, recoverable", [
    ("interrupt-partial", True), ("interrupt-gap", False), ("interrupt-delete", True),
])
def test_crash_boundary_decides_ownership_without_guessing(tmp_path, case, recoverable):
    assert probe(tmp_path, case).returncode == 75
    root = layout(tmp_path)
    if case == "interrupt-gap":
        assert (root / "attempt/credentials/kimi-code.json").read_bytes() == b""
    reply = probe(tmp_path, "recover")
    assert reply.returncode == (0 if recoverable else 3)
    assert (root / "attempt").exists() is not recoverable
    if not recoverable:
        assert (root / "attempt/credentials/kimi-code.json").read_bytes() == b""


@pytest.mark.parametrize("damage", [
    "replace", "hardlink", "portal", "extra", "missing", "torn-record"])
def test_unknown_identity_refuses_before_touching_anything(tmp_path, damage):
    assert probe(tmp_path, "interrupt").returncode == 75
    root = layout(tmp_path)
    attempt, sentinel = root / "attempt", tmp_path / "outside"
    sentinel.write_bytes(b"must survive")
    leaf = attempt / "credentials/kimi-code.json"
    if damage in ("replace", "hardlink"):
        leaf.rename(tmp_path / "original")
        if damage == "hardlink":
            os.link(sentinel, leaf)
        else:
            leaf.write_bytes(b"replacement")
    elif damage == "portal":
        from tests.sabotage_fixtures import plant_route_portal
        leaf.parent.rename(tmp_path / "original-dir")
        outward = tmp_path / "outward"
        outward.mkdir()
        os.link(sentinel, outward / "kimi-code.json")
        plant_route_portal(leaf.parent, outward, kind="junction")
    elif damage == "extra":
        (attempt / "extra").write_bytes(b"unknown")
    elif damage == "missing":
        leaf.rename(tmp_path / "missing")
    else:
        with (root / "stage-record.jsonl").open("ab") as out:
            out.write(b'{"incomplete":')
    reply = probe(tmp_path, "recover")
    assert reply.returncode == 3 and json.loads(reply.stdout)["status"] == "refused"
    assert (attempt / "config.toml").exists() and sentinel.read_bytes() == b"must survive"
    if damage == "replace":
        assert leaf.read_bytes() == b"replacement"
