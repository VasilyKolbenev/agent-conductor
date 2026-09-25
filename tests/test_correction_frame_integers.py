"""A finding admitted against the checker's samples is scanned again against the doer's current ones.

The material scan reads an integer as the digits it spells. The native witness records a typed
rejection whose cited line spells no sample the checker held, then lets a value that spells exactly
that line enter the doer's allowed environment before the correction: the correction is refused
before any task is spawned. An ordinary number in the same place is the positive control.
"""
from itertools import count
import json

import pytest

from conductor import ownership
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.codex_cli import CODEX_PROVIDER_ID, CODEX_PROTOCOL
from conductor.command.adapters.independent_check import CheckFrameError, scan_material
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers
from conductor.command.service import CommandService
from tests import _fakecodex, _fakeexe, _fakepin, _fakepolicy
from tests.test_policy_driver import authorize
from tests.test_policy_native_feedback import run_state
from tests.test_policy_runtime import NOW, ARGS, Activation, propose
from tests.test_project_ownership import activated

PIN = "POLICY_PIN"
DIGITS = str(_fakepin.LINE).encode("utf-8")


def test_the_material_scan_reads_an_integer_as_the_digits_it_spells():
    rows = ({"payload": {"findings": [{"line": _fakepin.LINE}]}, "source_lap": 1},)
    with pytest.raises(CheckFrameError, match="^frame_env_echo$"):
        scan_material(rows, (DIGITS,))
    scan_material(rows, (b"1234567", b""))  # an ordinary number and an empty sample refuse nothing


def pin_registry(root, tmp_path):
    executable = _fakeexe.build(tmp_path / "bin", "pin", "_fakepin")
    assert executable is not None, "this native witness must run, not silently skip"
    log = tmp_path / "spawns.log"
    environment = {_fakecodex.SPAWN_LOG: str(log)}
    config = ProviderConfig(provider_id=CODEX_PROVIDER_ID, protocol=CODEX_PROTOCOL,
        executable=str(executable), env_allow=(*environment, PIN))
    seq = count()
    ids = lambda kind: f"{kind}-{next(seq)}"
    resolution = resolve_providers([config], root=root, clock=lambda: NOW, ids=ids,
                                   environ=environment)
    return resolution.registry, ids, log


def semantic_rows(log):
    return [json.loads(line) for line in log.with_suffix(".semantic.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("current,launched", [(DIGITS, False), (b"1234567", True)])
def test_a_recorded_line_that_spells_the_doers_current_secret_is_refused_before_the_correction_spawns(
        tmp_path, monkeypatch, current, launched):
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    registry, ids, log = pin_registry(root, tmp_path)
    adapter = registry.resolve(CODEX_PROVIDER_ID)
    reported, execute = [], adapter.execute

    def spy(prepared):  # the adapter's own receipt: the runtime keeps its outcome, not its sentence
        receipt = execute(prepared)
        reported.append(receipt)
        return receipt

    monkeypatch.setattr(adapter, "execute", spy)
    with ownership.acquire_owner(root):
        f = run_state(root, AdapterRegistry([adapter]), ids)
        f.policy.driver = Activation()
        f.service = CommandService(f.store, f.runtime._registry, clock=lambda: NOW, ids=ids)
        grant = authorize(f)
        propose(f)
        assert DIGITS not in adapter._sensitive_values(), "control: no sample spells the line yet"
        first = f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
        assert first.receipt.outcome == "verification_failed"
        feedback = next(r.value for r in f.store.read("run").records if r.kind == "correction_feedback")
        assert feedback.as_dict()["payload"]["findings"][0]["line"] == _fakepin.LINE
        assert len(_fakecodex.task_spawns(log)) == 2
        # The doer's samples change AFTER the record: an allowed environment value now spells the line.
        monkeypatch.setitem(adapter._runner._environ, PIN, current.decode("utf-8"))
        assert current in adapter._sensitive_values()
        f.service.propose(run_id="run", attempt_id="correction", instance_id="doer", capability="dispatch",
            arguments=ARGS, scope=("work/item",), proposed_by="owner", rationale="Fix finding",
            timeout_seconds=30, node_id="next", proposal_id="fix", feedback_ids=(feedback.feedback_id,))
        second = f.runtime.execute(f.runtime.authorize_policy("run", "fix", grant.authorization_id))
    spawns, rows = _fakecodex.task_spawns(log), semantic_rows(log)
    if launched:
        assert second.receipt.outcome == "succeeded" and len(spawns) == 4
        assert rows[2] == {"role": "doer", "correction_received": True,
                           "instruction_preserved": True, "written": 1}
        assert (root / "work/item/answer.py").read_bytes() == _fakepolicy.GOOD
    else:
        # A refusal known before the spawn is a named `failed` receipt, never a result lost after an effect.
        assert second.receipt.outcome == "failed" and len(spawns) == 2 and len(rows) == 2
        assert reported[-1].outcome == "failed" and reported[-1].exit_code is None
        assert "frame_env_echo" in reported[-1].detail and "no task was spawned" in reported[-1].detail
        assert (root / "work/item/answer.py").read_bytes() == _fakepolicy.BAD


def test_a_result_lost_after_the_task_spawned_stays_unknown(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    registry, ids, log = pin_registry(root, tmp_path)
    adapter = registry.resolve(CODEX_PROVIDER_ID)

    def lost(request, outcome):
        raise RuntimeError("the observation road broke after the child ran")

    monkeypatch.setattr(adapter, "_observed", lost)
    with ownership.acquire_owner(root):
        f = run_state(root, AdapterRegistry([adapter]), ids)
        f.policy.driver = Activation()
        f.service = CommandService(f.store, f.runtime._registry, clock=lambda: NOW, ids=ids)
        grant = authorize(f)
        propose(f)
        first = f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
    assert first.receipt.outcome == "unknown", "control: an effect may have happened, so nothing is claimed"
    assert len(_fakecodex.task_spawns(log)) == 1 and semantic_rows(log)[0]["role"] == "doer"
