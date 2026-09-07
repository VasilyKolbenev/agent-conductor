"""Opt-in real checker: correct AND incorrect one-file results get distinct verdicts.

No installation or credential discovery. Set CONDUCT_CLAUDE_REAL_CHECKER=1 or
CONDUCT_CODEX_REAL_CHECKER=1, the corresponding existing EXECUTABLE and KEY_NAME
smoke variables, and the key in the process environment. Optional
CONDUCT_CHECKER_MODEL pins the checker; CONDUCT_CHECKER_ENV_NAMES is a comma
separated list of additional allowed names (for example the configured API
endpoint or a Windows process bootstrap variable). Values never enter reports.

Each case spends one model call, with a 60-second task ceiling and the small
4 KiB capture profile. This proves the vendor's verdict format and reading of
actual result bytes, not a complete owner acceptance of the Studio workflow.
"""
import os
from dataclasses import replace

import pytest

from conductor.command.adapters.base import Published, VerifierBinding
from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.contracts import RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import ControlRuntime
from tests.test_command_claude_real_smoke import _real_harness as claude_install
from tests.test_command_codex_real_smoke import _real_harness as codex_install
from tests.test_command_claude_transport import NOW, a_request


INSTALLS = {"CLAUDE": claude_install, "CODEX": codex_install}


def _allowed_names(provider):
    if os.environ.get(f"CONDUCT_{provider}_REAL_CHECKER") != "1":
        pytest.skip(f"real paid checker not opted in: CONDUCT_{provider}_REAL_CHECKER=1")
    key_name = os.environ.get(f"CONDUCT_{provider}_KEY_NAME", "")
    if not key_name or not os.environ.get(key_name):
        pytest.skip(f"no checker credential: CONDUCT_{provider}_KEY_NAME must name a set variable")
    extra = tuple(name.strip() for name in os.environ.get(
        "CONDUCT_CHECKER_ENV_NAMES", "").split(",") if name.strip())
    return tuple(dict.fromkeys((key_name, *extra)))


def _observation(root, adapter):
    request = replace(a_request(timeout=60), arguments={
        "work_item_id": "work-001", "instruction_ref": "instr-001",
        "profile": "implement", "artifact_refs": [], "output_limit_profile": "small"})
    config = {"cycle": {"id": "default-orbit", "phases": ["implement", "review"]},
              "instances": [{"id": request.instance_id, "adapter": adapter.manifest.adapter_id},
                            {"id": "checker", "adapter": adapter.manifest.adapter_id}]}
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id=request.run_id, cycle_id="default-orbit",
        created_at=NOW, mode="confirm", config_digest=snapshot_digest(config)), config)
    store.append(request)
    common = dict(run_id=request.run_id, action_id=request.action_id,
        attempt_id=request.attempt_id, instance_id=request.instance_id,
        adapter_id=adapter.manifest.adapter_id, recorded_at=NOW,
        request_digest=action_request_digest(request), recovery_ref="smoke-recovery",
        schema_version=2)
    store.append(AttemptEvent(event_id="smoke-lease", phase="effect_lease",
                              outcome=None, exit_code=None, **common))
    observed = AttemptEvent(event_id="smoke-observed", phase="execution_observed",
        outcome="succeeded", exit_code=0, **common)
    store.append(observed)
    return request, ControlRuntime._observed_report(request, observed)


def _observe_first_line(adapter, monkeypatch, recorded):
    production_attempt = adapter._attempt

    def attempt(*args, **kwargs):
        outcome = production_attempt(*args, **kwargs)
        if callable(args[0]):  # version argv is a fixed tuple, task argv a home-aware function
            text = outcome.output.decode("utf-8", errors="replace")
            first = next((line.lstrip() for line in text.splitlines() if line.strip()), "")
            # Never retain arbitrary vendor output in a report, even on a failure.
            recorded.append(first if first in {"VERDICT: accept", "VERDICT: reject"}
                            else "<no literal verdict>")
        return outcome

    monkeypatch.setattr(adapter, "_attempt", attempt)


@pytest.mark.parametrize("provider", sorted(INSTALLS))
@pytest.mark.parametrize("correct", [True, False], ids=["correct-result", "incorrect-result"])
def test_real_checker_judges_the_file_not_just_the_process_exit(
        tmp_path, monkeypatch, record_property, provider, correct):
    adapter, root = INSTALLS[provider](tmp_path, _allowed_names(provider))
    work = adapter._workspace.work_dir("work-001")
    (work / "answer.py").write_text(
        "def answer():\n    return " + ("1\n" if correct else "2\n"),
        encoding="utf-8", newline="\n")
    version = adapter._attempt(("--version",), "work", timeout=30)
    assert version.status == "completed" and version.exit_code == 0
    assert adapter._version_matches(version.output), "install is not the reviewed checker build"
    request, result = _observation(root, adapter)
    before = adapter._workspace.digest_work_tree()
    material = Published(None, ("work-001/answer.py",), before, (), (),
                        instruction="Implement answer() in answer.py to return the integer 1.")
    recorded = []
    _observe_first_line(adapter, monkeypatch, recorded)
    verification = adapter.verify_for(request, result, VerifierBinding(
        "checker", adapter.manifest.adapter_id, os.environ.get("CONDUCT_CHECKER_MODEL")), material)
    expected = "VERDICT: accept" if correct else "VERDICT: reject"
    assert recorded == [expected], "real checker did not return the expected literal first line"
    record_property("checker_first_line", recorded[0])
    assert verification.state == ("verified" if correct else "mismatch")
    assert bool(verification.evidence_refs) is correct
    assert adapter._workspace.digest_work_tree() == before
    homes = root / adapter._workspace.home_dir
    assert homes.is_dir() and not tuple(homes.iterdir())
