"""Codex ruling K (23.09.2026): one byte budget along the do -> independent check road.

Live, a 43-49 KiB plan and a 19,538-byte test file could not be judged: the file was past the 16 KiB read budget
and plan + file past the 64 KiB frame. FILE_BUDGET is now 32 KiB and FRAME = STDIN = INSTRUCTION = 256 KiB.
Codex R1/R2 (25.09.2026): the argv channel is the whole command line in Windows' UTF-16 units, and the
provider facts a grant binds carry each adapter's channel with that bound, unit and scope.
"""
import hashlib
import json

import pytest

from conductor import ownership
from conductor.command import verify_holds as words
from conductor.command.adapters.harness_workspace import FILE_BUDGET
from conductor.command.adapters.independent_check import FRAME_LIMIT
from conductor.command.adapters.kimi_code import MARKER_DIR
from conductor.command.artifacts import ARTIFACT_CONTENT_LIMIT, ArtifactDocument
from conductor.command.service import CommandService
from tests import _fakecodex, _fakepolicy
from tests.test_policy_driver import attach_driver, authorize
from tests.test_policy_native_feedback import native_registry, run_state, terminal
from tests.test_policy_runtime import NOW, Activation, propose
from tests.test_project_ownership import activated

TEST_FILE = 19538  # MEASURED live (live-v5-8): the test file the old road could not hand a checker


def _plan():
    row = '| AC-7 | `[{"outcome": "succeeded"}]` -> 1 | a "quoted" cell \\ and a backslash |\n'
    return (row * (ARTIFACT_CONTENT_LIMIT // len(row) + 1))[:ARTIFACT_CONTENT_LIMIT]


def _semantic(log):
    return [json.loads(line) for line in log.with_suffix(".semantic.jsonl").read_text().splitlines()]


def test_a_plan_at_the_document_bound_and_a_19538_byte_file_reach_the_real_checker_whole(tmp_path):
    """Through the real native executable, runner, pipe and stdin, both passes of a typed correction."""
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    plan = _plan()
    assert len(plan.encode("utf-8")) == ARTIFACT_CONTENT_LIMIT
    pad = TEST_FILE - len(_fakepolicy.BAD)
    registry, ids, log = native_registry(root, tmp_path, **{
        _fakepolicy.PAD: str(pad), _fakepolicy.PLAN_SHA: hashlib.sha256(plan.encode("utf-8")).hexdigest()})
    with ownership.acquire_owner(root):
        f = run_state(root, registry, ids, plan=plan)
        driver, execution = attach_driver(f)
        try:
            authorize(f)
            settled = terminal(f)
        finally:
            driver.stop()
            execution.shutdown()
    results = [row.value for row in settled.records if row.kind == "action_result"]
    assert [row.outcome for row in results] == ["verification_failed", "succeeded"]
    rows = _semantic(log)
    doers = [row for row in rows if row["role"] == "doer"]
    checkers = [row for row in rows if row["role"] == "checker"]
    assert len(doers) == len(checkers) == 2
    assert all(row["plan_whole"] and row["limits_told"] for row in doers)
    assert all(row["plan_whole"] and row["file_bytes"] == TEST_FILE for row in checkers)
    assert all(64 * 1024 < row["frame_bytes"] <= FRAME_LIMIT for row in checkers), checkers
    assert [row["accepted"] for row in checkers] == [False, True]
    assert (root / "work/item/answer.py").read_bytes() == _fakepolicy.GOOD + b"#" * pad
    evidence = [row.value for row in settled.records if row.kind == "evidence"]
    assert len(evidence) == 1 and evidence[0].verifier_instance_id == "checker"


def test_files_each_within_budget_whose_frame_would_pass_the_ceiling_are_refused_before_the_checker(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    extra = FRAME_LIMIT // FILE_BUDGET  # every file legal, the frame one JSON overhead too large
    registry, ids, log = native_registry(root, tmp_path, **{
        _fakepolicy.EXTRA: f"files-{extra}", _fakepolicy.EXTRA_BYTES: f"bytes-{FILE_BUDGET}"})
    from conductor.command.adapters.codex_cli import CODEX_PROVIDER_ID
    adapter = registry.resolve(CODEX_PROVIDER_ID)
    with ownership.acquire_owner(root):
        f = run_state(root, registry, ids)
        f.policy.driver = Activation()
        f.service = CommandService(f.store, f.runtime._registry, clock=lambda: NOW, ids=ids)
        grant = authorize(f)
        propose(f)
        result = f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
    assert result.receipt.outcome == "verification_failed"
    assert result.receipt.detail == words.FRAME_OVER_LIMIT
    assert not adapter.verification_started(result.request)
    assert len(_fakecodex.task_spawns(log)) == 1, "only the doer ran; no checker was started"


@pytest.mark.parametrize("module,name", [
    ("conductor.command.adapters.independent_check", "FRAME_LIMIT"),
    ("conductor.command.adapters.process", "STDIN_LIMIT"),
    ("conductor.command.adapters.harness_workspace", "INSTRUCTION_LIMIT"),
    ("conductor.command.adapters.harness_workspace", "FILE_BUDGET")])
def test_the_provider_digest_binds_every_limit_on_the_road(tmp_path, monkeypatch, module, name):
    """A changed limit changes the digest, so an old grant is refused, never silently reinterpreted."""
    import importlib
    from conductor.command.adapters.provider import ProviderConfig
    from conductor.command.policy_providers import ProviderAuthority
    from tests.test_command_provider_contract import _contract
    from tests.test_policy_runtime import setup
    f = setup(tmp_path)
    config = ProviderConfig("claude-code", "/opt/claude/bin/claude", "fake-claude-jsonl-v1",
                            env_allow=("ANTHROPIC_API_KEY",))
    authority = ProviderAuthority([config], [_contract(auth="api_key")], f.registry)
    run = f.store.read("run")
    facts = authority.facts(run.config)["providers"][0]
    assert facts["file_budget"] == FILE_BUDGET == 32 * 1024
    assert facts["input_limits"] == {"frame": 256 * 1024, "stdin": 256 * 1024, "instruction": 256 * 1024}
    assert facts["task_channel"] is None, "a class with no profile declares no channel to bound"
    before = authority.digest(run.config)
    target = importlib.import_module(module)
    monkeypatch.setattr(target, name, getattr(target, name) // 2)
    assert authority.digest(run.config) != before


def test_a_do_task_past_the_stdin_ceiling_is_refused_before_its_claim_and_spawns_nothing(tmp_path):
    """D7: the payload used to be sized after the claim, so an oversized task became an unknown with a
    standing marker. Six input documents at the document bound compose more than the stdin ceiling."""
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.contracts import ActionProposal, RunEnvelope
    from conductor.command.run_store import RunStore, snapshot_digest
    from conductor.command.runtime import AttemptState, Budget, Confirmation, ControlRuntime
    from tests import _fakeclaude
    from tests.test_command_artifact_dispatch import ARGUMENTS, CONFIG, INSTANCE_ID, INSTRUCTION, RUN_ID, _Ids
    from tests.test_command_claude_transport import a_harness
    adapter, root, log = a_harness(tmp_path, instruction=INSTRUCTION)
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id=RUN_ID, cycle_id="artifact-cycle", created_at=NOW,
                                 config_digest=snapshot_digest(CONFIG), mode="confirm"), CONFIG)
    refs = [f"artifact-part-{index}" for index in range(6)]
    for index, ref in enumerate(refs):
        store.append(ArtifactDocument(f"part-{index}", ref, RUN_ID, NOW, "text/markdown", "p" * ARTIFACT_CONTENT_LIMIT))
    proposal = ActionProposal(
        proposal_id="proposal-dispatch", run_id=RUN_ID, attempt_id="attempt-dispatch", instance_id=INSTANCE_ID,
        capability="dispatch", arguments={**ARGUMENTS, "artifact_refs": refs}, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60, rationale="six documents at the bound",
        config_digest=snapshot_digest(CONFIG), input_binding="proposal-v1")
    store.append(proposal)
    confirmation = Confirmation(
        confirmation_id="confirmation-dispatch", run_id=RUN_ID, proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="dispatch", scope=("work",),
        config_digest=proposal.config_digest, confirmed_by="release-owner", confirmed_at=NOW)
    runtime = ControlRuntime(store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    budget = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
    attempt = runtime.execute(runtime.authorize(confirmation, budget=budget))
    assert attempt.state is AttemptState.FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == "adapter reported failed: its task was larger than the bounded task channel"
    assert _fakeclaude.prompt_spawns(log) == []



def test_an_argv_channel_task_past_its_command_line_bound_is_refused_before_its_claim(tmp_path):
    """D9 (M/J/K review): Kimi, Grok and DSH carry the task in one argv element; Windows refuses a
    command line past 32,767 characters with an OSError the claim used to precede."""
    from tests import _fakekimi
    from tests.test_command_kimi_transport import a_harness, a_request, run_once
    adapter, root, log = a_harness(tmp_path)
    (root / "instructions" / "instr-001.md").write_bytes(b"Keep this long instruction. " * 1500)
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed"
    assert receipt.detail == REFUSED
    assert _fakekimi.prompt_spawns(log) == []
    assert not (root / MARKER_DIR / "run-1" / "act-1.marker").exists(), "refused before its claim"


REFUSED = "the materialized task exceeds the bounded task channel, so no task was spawned"


def test_the_command_line_is_counted_whole_in_the_utf16_units_windows_measures():
    """Codex R1: the serializer Popen uses, a character past the BMP as two units, the NUL included."""
    import subprocess
    from conductor.command.adapters._procgroup import COMMAND_LINE_LIMIT, command_line_units
    smile = "\U0001F642"
    assert command_line_units(["kimi.exe", "--prompt", smile * 18000]) == 36019  # the helper read 18000
    assert command_line_units(["k", "x" * (COMMAND_LINE_LIMIT - 3)]) == COMMAND_LINE_LIMIT
    for argv in (["x"], ["C:\\Program Files\\k\\kimi.exe", "--prompt", 'say "hi" \\" ' + smile],
                 ["a b", "tail\\\\", 'q"'], ["", smile]):
        line = subprocess.list2cmdline(argv)
        assert command_line_units(argv) == len(line.encode("utf-16-le")) // 2 + 1, argv
    assert COMMAND_LINE_LIMIT == 32767  # MEASURED: 32,766 units and the NUL start, one more refuses


def _kimi(tmp_path, name, instruction):
    from tests.test_command_kimi_transport import a_harness
    adapter, root, log = a_harness(tmp_path / name)
    (root / "instructions" / "instr-001.md").write_text(instruction, encoding="utf-8", newline="\n")
    return adapter, root, log


def _edge_instruction(tmp_path):
    """An ASCII instruction whose whole command line is exactly the bound, and its task's own units.

    One short pass through a same-shaped harness measures what the pins, flags and composed frame add;
    the instruction reaches the task verbatim, so each further character is one unit.
    """
    from conductor.command.adapters._procgroup import COMMAND_LINE_LIMIT, command_line_units
    from tests import _fakekimi
    from tests.test_command_kimi_transport import a_request, run_once
    adapter, _root, log = _kimi(tmp_path, "cal", "Z")
    assert run_once(adapter, a_request()).outcome == "succeeded"
    argv = _fakekimi.prompt_spawns(log)[0]["argv"]
    grow = COMMAND_LINE_LIMIT - command_line_units((*adapter._argv_prefix(), *argv))
    return "Z" * (1 + grow), command_line_units(argv[-1:]) + grow


@pytest.mark.parametrize("over", [0, 1])
def test_the_argv_channel_counts_its_pins_and_flags_and_refuses_one_unit_past_the_bound(tmp_path, over):
    """Codex R1: the whole command line is bounded, not the task text; at the bound it runs, one past it
    is refused before the claim with no task spawned and no marker left."""
    from conductor.command.adapters._procgroup import COMMAND_LINE_LIMIT
    from tests import _fakekimi
    from tests.test_command_kimi_transport import a_request, run_once
    edge, task_units = _edge_instruction(tmp_path)
    adapter, root, log = _kimi(tmp_path, "run", edge + "Z" * over)  # "run" and "cal": one path length
    receipt = run_once(adapter, a_request())
    marker = root / MARKER_DIR / "run-1" / "act-1.marker"
    if over:
        assert receipt.detail == REFUSED and _fakekimi.prompt_spawns(log) == [] and not marker.exists()
        assert task_units + over < COMMAND_LINE_LIMIT, "the task alone fits: the pins and flags refused it"
    else:
        # Started, not lost: CreateProcess took the command line at the bound (a launch it refused
        # would read unknown). The Windows stand-in may still fail relaunching its own interpreter.
        assert receipt.detail != REFUSED and marker.is_file(), "claimed and started at the bound"
        assert receipt.outcome in ("succeeded", "failed"), (receipt.outcome, receipt.detail)


def test_a_non_bmp_task_the_old_count_admitted_is_refused_before_its_claim(tmp_path):
    """Codex R1: 18,000 x U+1F642 read 18,000 against 24,576; Windows sees more than 36,000 units."""
    from tests import _fakekimi
    from tests.test_command_kimi_transport import a_request, run_once
    adapter, root, log = _kimi(tmp_path, "run", "\U0001F642" * 18000)
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed" and receipt.detail == REFUSED
    assert _fakekimi.prompt_spawns(log) == []
    assert not (root / MARKER_DIR / "run-1" / "act-1.marker").exists()


def test_an_argv_providers_facts_freeze_its_command_line_bound_so_a_new_bound_needs_a_new_grant(
        tmp_path, monkeypatch):
    """Codex R2: the channel, its bound, unit and scope are in the facts the grant digest binds."""
    from conductor.command.adapters import _procgroup
    from conductor.command.adapters.kimi_code import KIMI_PROTOCOL, KIMI_PROVIDER_ID
    from conductor.command.adapters.provider import ProviderConfig
    from conductor.command.policy_providers import ProviderAuthority
    from conductor.command.providers import resolve_providers
    from tests.test_command_kimi_transport import _executable, _Ids
    root = tmp_path / "root"
    root.mkdir()
    config = ProviderConfig(provider_id=KIMI_PROVIDER_ID, executable=str(_executable(tmp_path)),
                            protocol=KIMI_PROTOCOL)
    resolution = resolve_providers([config], root=root, clock=lambda: NOW, ids=_Ids(), environ={})
    authority = ProviderAuthority([config], resolution.contracts, resolution.registry)
    run_config = {"instances": [{"id": "doer", "adapter": KIMI_PROVIDER_ID}]}
    facts = authority.facts(run_config)["providers"][0]
    assert facts["transport"]["task_channel"] == "argv"
    assert facts["task_channel"] == {"channel": "argv", "limit": 32767, "unit": "utf16_units",
                                     "scope": "command_line"}
    before = authority.digest(run_config)
    monkeypatch.setattr(_procgroup, "COMMAND_LINE_LIMIT", 24 * 1024)
    assert authority.digest(run_config) != before



def test_a_rejection_whose_findings_are_not_typed_is_named_a_rejection_and_carries_no_correction(tmp_path):
    """MEASURED live (live-nc-1): a real REJECT with reasons before its JSON read 'no complete accepted verdict'."""
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    registry, ids, log = native_registry(root, tmp_path, **{_fakepolicy.PROSE: "with-prose"})
    with ownership.acquire_owner(root):
        f = run_state(root, registry, ids)
        f.policy.driver = Activation()
        f.service = CommandService(f.store, f.runtime._registry, clock=lambda: NOW, ids=ids)
        grant = authorize(f)
        propose(f)
        result = f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
    assert result.receipt.outcome == "verification_failed"
    assert result.receipt.detail == words.CHECKER_FINDINGS_REFUSED
    assert not any(row.kind == "correction_feedback" for row in f.store.read("run").records)
    checker = [row for row in _semantic(log) if row["role"] == "checker"]
    assert checker and all(row["shape_told"] for row in checker), "the bounded frame names one reply shape"
