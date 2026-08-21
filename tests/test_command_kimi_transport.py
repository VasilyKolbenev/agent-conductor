"""Kimi Code driven for real, against a fake that is a REAL single executable.

Every claim here is a relation driven through the real provider door, the real
owned-process runner and a real child process: the fake stands in for the pinned
binary, never for the adapter. A spawn is counted by the line the child itself
wrote, the isolated home is read out of the child's own environment, and the
absence of a planted secret is checked against every value the adapter can hand
onward.

The pin shape is the point of the fake. Kimi Code installs as a native binary
and runs no interpreter, so the adapter pins ONE absolute path and puts nothing
in front of it. A fake driven through ``sys.executable`` would exercise the dsh
shape instead and would quietly prove nothing about this one, so
``_fakekimi.build_executable`` produces a file the operating system really runs
-- and where a platform grants no way to build one without a shell, these tests
SKIP rather than test the wrong thing. This build never spawns through a shell,
so a fake that needed one would be a fake of something else.

What is held here is what is specific to Kimi: its documented flags in its
documented shape, the exact version its preflight demands, the home its own
environment variable relocates, the telemetry switch its docs name, and the
weaker reading its receipts must give an exit code the vendor never explained.
The relations the shared transport owns -- the marker, the sweep, the retention
promise against a hostile child, the containment of every written route -- are
held once, in the dsh suite, against the same code.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.adapters.kimi_code import (
    HOME_DIR,
    INSTRUCTION_DIR,
    KIMI_PROTOCOL,
    KIMI_PROVIDER_ID,
    MARKER_DIR,
    REVIEWED_KIMI_VERSION,
    KimiCodeError,
    kimi_pin,
)
from conductor.command.adapters.provider import (
    ProviderConfig,
    ProviderConfigError,
)
from conductor.command.contracts import ActionRequest
from conductor.command.providers import resolve_providers

from tests import _fakekimi

NOW = "2026-08-21T12:00:00Z"
DIGEST = "sha256:" + "a" * 64
SECRET = "sk-live-planted-kimi-secret"
INSTRUCTION_BODY = "Add the missing guard and prove it with one failing test."


class _Ids:
    """A deterministic id mint that never repeats a value."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count}"


def _executable(tmp_path: Path) -> Path:
    exe = _fakekimi.build_executable(tmp_path / "bin")
    if exe is None:
        pytest.skip("this platform builds no shell-free single-file executable")
    return exe


def a_harness(tmp_path: Path, **knobs: str):
    """A registered, available Kimi provider over the fake, its root and its log."""
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    instructions = root / INSTRUCTION_DIR
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    log = tmp_path / "spawns.log"
    environ = {_fakekimi.SPAWN_LOG: str(log), **knobs}
    config = ProviderConfig(
        provider_id=KIMI_PROVIDER_ID, executable=str(exe),
        protocol=KIMI_PROTOCOL, env_allow=tuple(sorted(environ)))
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ=environ)
    return resolution.registry.resolve(KIMI_PROVIDER_ID), root, log


def a_request(*, action_id="act-1", capability="dispatch", timeout=60,
              work_item_id="work-001", arguments=None) -> ActionRequest:
    body = arguments if arguments is not None else {
        "work_item_id": work_item_id, "instruction_ref": "instr-001",
        "profile": "implement", "artifact_refs": ["art-001"],
        "output_limit_profile": "normal"}
    return ActionRequest(
        action_id=action_id, run_id="run-1", attempt_id="att-1",
        instance_id="inst-1", capability=capability, arguments=body,
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key=f"idem-{action_id}", timeout_seconds=timeout,
        preview_digest=DIGEST, mode="confirm")


def run_once(adapter, request: ActionRequest):
    """Drive prepare -> execute exactly as the runtime does; return the receipt."""
    return adapter.execute(adapter.prepare(request))


# --- the pin is one path, and the argv is the vendor's documented shape --------


def test_one_pinned_binary_and_code_owned_flags_are_the_whole_command(tmp_path):
    """``--output-format text --prompt <task>``, prompt LAST, nothing in front.

    The child reports the argv it was handed after the pin, so what is read here
    is what the operating system really passed: the two documented flags this
    module owns and exactly one prompt token built from validated identifiers.
    """
    adapter, _root, log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    prompts = _fakekimi.prompt_spawns(log)
    assert len(prompts) == 1
    argv = prompts[0]["argv"]
    assert argv[:3] == ["--output-format", "text", "--prompt"]
    assert len(argv) == 4, f"UNEXPECTED_ARGV={argv}"
    for row in _fakekimi.spawns(log):
        rendered = " ".join(row["argv"]).lower()
        for banned in ("npx", "npm", ".cmd", "-c ", "&&", "|"):
            assert banned not in rendered, f"SHELL_SHAPED_ARGV={row['argv']}"


def test_the_prompt_carries_the_materialized_instruction_and_not_its_reference(
        tmp_path):
    """A prompt naming only a reference would ask the real tool something else."""
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    prompt = _fakekimi.prompt_spawns(log)[0]["argv"][3]
    assert INSTRUCTION_BODY in prompt, "PROMPT_LACKS_THE_INSTRUCTION_TEXT=True"
    assert "instr-001" in prompt


def test_a_relative_pin_is_refused_before_any_child_can_exist():
    for bad in ("kimi", "./kimi", "bin/kimi"):
        with pytest.raises(KimiCodeError, match="absolute operator pin"):
            kimi_pin(bad)


def test_an_entrypoint_pinned_against_a_single_binary_is_refused(tmp_path):
    """Half of what the operator wrote down would otherwise be silently dropped.

    Kimi Code runs no interpreter, so an entrypoint pinned beside it is a config
    this build cannot honour: the operator believes a second file is run, and
    nothing here would run it. Refusing says so; ignoring it would leave them
    believing a path that never executes.
    """
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    config = ProviderConfig(
        provider_id=KIMI_PROVIDER_ID, executable=str(exe),
        protocol=KIMI_PROTOCOL, entrypoint=str(exe))

    with pytest.raises(ProviderConfigError, match="never be run"):
        resolve_providers(
            [config], root=root, clock=lambda: NOW, ids=_Ids(), environ={})


# --- the version preflight is exact, and a mismatch spawns no prompt ----------


def test_the_reviewed_version_is_proved_before_any_prompt_is_spawned(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    spawns = _fakekimi.spawns(log)
    assert spawns[0]["argv"] == ["--version"], "THE_PREFLIGHT_IS_NOT_FIRST=True"
    assert len(_fakekimi.prompt_spawns(log)) == 1


def test_a_version_that_is_not_the_reviewed_one_spawns_zero_prompts(tmp_path):
    """A near miss is a miss: the product ships breaking changes between minors."""
    adapter, _root, log = a_harness(tmp_path, FAKEKIMI_VERSION="0.37.2")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert REVIEWED_KIMI_VERSION in receipt.detail
    assert _fakekimi.prompt_spawns(log) == [], "PROMPT_SPAWNED_ON_MISMATCH=True"


def test_a_version_print_the_build_cannot_answer_spawns_zero_prompts(tmp_path):
    adapter, _root, log = a_harness(tmp_path, FAKEKIMI_VERSION_FAILS="1")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "version preflight" in receipt.detail
    assert _fakekimi.prompt_spawns(log) == []


def test_a_version_token_carrying_a_prefix_refuses_rather_than_spawning(tmp_path):
    """The vendor publishes no format for the print, so an exact match is demanded.

    This is the documented cost of that decision, held as a test rather than
    left as a hope: a build that prints its number with a prefix stops the
    dispatch instead of running a prompt. A false refusal is the safe direction
    of a wrong guess, and the opt-in real smoke is what settles the format.
    """
    adapter, _root, log = a_harness(
        tmp_path, FAKEKIMI_VERSION=f"kimi {REVIEWED_KIMI_VERSION}")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert _fakekimi.prompt_spawns(log) == []


# --- the home is fresh, isolated, and gone when the spawn returns -------------


def test_every_spawn_gets_a_fresh_home_under_this_providers_own_root(tmp_path):
    """Read out of the CHILD's environment, not out of the adapter's intent."""
    adapter, root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    homes = [row["kimi_home"] for row in _fakekimi.spawns(log)]
    assert len(homes) == 2, f"EXPECTED_PREFLIGHT_AND_PROMPT={homes}"
    assert len(set(homes)) == 2, "TWO_SPAWNS_SHARED_ONE_HOME=True"
    for home in homes:
        assert Path(home).parent == (root / HOME_DIR).resolve(), (
            f"HOME_OUTSIDE_THIS_PROVIDERS_ROOT={home}")


def test_the_telemetry_switch_the_vendor_documents_is_sent_on_every_spawn(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    sent = {row["telemetry_disabled"] for row in _fakekimi.spawns(log)}
    assert sent == {"1"}, f"TELEMETRY_NOT_DISABLED={sent}"


def test_no_attempt_home_survives_a_completed_dispatch(tmp_path):
    """A real Kimi Code writes config, sessions, logs and OAuth credentials here.

    The vendor's own words for what KIMI_CODE_HOME relocates are the reason this
    matters: whatever the tool wrote is model and account state this build
    promised not to retain, so the honest lifetime of the home is the lifetime
    of the spawn.
    """
    adapter, root, _log = a_harness(
        tmp_path, FAKEKIMI_HOME_FILE="sessions/turn.json:{}")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    standing = sorted(path.name for path in (root / HOME_DIR).iterdir())
    assert standing == [], f"HOME_SURVIVED_THE_DISPATCH={standing}"


def test_only_the_names_the_operator_allowed_reach_the_child(tmp_path):
    """The allowlist is names; a value this build invented would be a leak."""
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    names = set(_fakekimi.spawns(log)[0]["env_names"])
    assert "KIMI_CODE_HOME" in names and "KIMI_DISABLE_TELEMETRY" in names
    assert _fakekimi.SPAWN_LOG in names
    # Nothing this build never named and the operator never allowed.
    assert "KIMI_API_KEY" not in names, "AN_UNALLOWED_CREDENTIAL_NAME_REACHED_THE_CHILD"


# --- what an exit code is allowed to mean ------------------------------------


def test_exit_zero_says_the_vendor_published_no_exit_code_contract(tmp_path):
    """The weaker reading, in the receipt, because the stronger one is unearned.

    Both readings end at an observation of the process. They do not start in the
    same place: dsh publishes what its one-shot codes mean and Kimi Code does
    not, so a receipt that gave them the same sentence would be overstating this
    one. The claim is checked in the receipt a caller actually reads.
    """
    adapter, _root, _log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    assert receipt.exit_code == 0
    assert "no exit-code contract" in receipt.detail
    assert "not a verification" in receipt.detail


def test_a_non_zero_exit_is_observed_as_failed_and_carries_the_code(tmp_path):
    adapter, _root, _log = a_harness(tmp_path, FAKEKIMI_EXIT="4")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert receipt.exit_code == 4


def test_output_past_the_capture_bound_can_never_be_called_a_success(tmp_path):
    """The one-shot answer arrives on stdout; an unread stream was not observed."""
    adapter, _root, _log = a_harness(tmp_path, FAKEKIMI_BOMB_BYTES="200000")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "capture bound" in receipt.detail


def test_a_prompt_past_its_timeout_is_terminated_and_reported(tmp_path):
    adapter, _root, _log = a_harness(tmp_path, FAKEKIMI_SLEEP="30")

    receipt = run_once(adapter, a_request(timeout=2))

    assert receipt.outcome == "failed"
    assert "timeout" in receipt.detail


# --- verification, and the ceiling it cannot pass ----------------------------


def test_a_real_change_inside_the_authorized_subtree_still_never_reaches_verified(
        tmp_path):
    """Exit zero plus a real file change is still not evidence this build wrote."""
    adapter, _root, _log = a_harness(
        tmp_path, FAKEKIMI_WRITE_FILE="guard.py:# a real change\n")
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    assert receipt.outcome == "succeeded"
    assert verification.state == "error", f"STATE={verification.state}"
    assert verification.state != "verified"
    assert verification.evidence_refs == ()
    assert "no durable evidence record" in verification.detail


def test_a_change_outside_the_authorized_subtree_is_a_mismatch(tmp_path):
    adapter, _root, _log = a_harness(
        tmp_path, FAKEKIMI_ESCAPE_FILE="stolen.py:# outside the work item\n")
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    assert verification.state == "mismatch"
    assert verification.evidence_refs == ()


def test_a_prompt_that_changed_nothing_is_an_error_and_not_a_success(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    assert receipt.outcome == "succeeded"
    assert verification.state == "error"
    assert verification.state != "unavailable", (
        "an adapter that HAS a verifier must never borrow the absent-verifier token")


# --- a crashed prompt is never run twice, and no secret escapes ---------------


def test_a_marker_from_an_earlier_attempt_stops_a_second_prompt(tmp_path):
    adapter, root, log = a_harness(tmp_path)
    request = a_request()
    first = run_once(adapter, request)

    second = run_once(adapter, request)

    assert first.outcome == "succeeded"
    assert second.outcome == "unknown"
    assert "never repeated" in second.detail
    assert len(_fakekimi.prompt_spawns(log)) == 1, "THE_PROMPT_RAN_TWICE=True"
    assert (root / MARKER_DIR / "act-1.marker").is_file()


def test_a_secret_the_child_prints_reaches_no_receipt_and_no_verification(tmp_path):
    """Raw child output is bounded, drained and dropped; it is never carried."""
    adapter, _root, _log = a_harness(
        tmp_path, FAKEKIMI_STDOUT=SECRET, FAKEKIMI_STDERR=SECRET)
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    assert SECRET not in receipt.detail
    assert SECRET not in str(receipt)
    assert SECRET not in verification.detail
    assert SECRET not in str(verification)


def test_a_secret_planted_where_a_version_belongs_never_reaches_a_receipt(tmp_path):
    """The version token is COMPARED and never reported, for exactly this reason."""
    adapter, _root, _log = a_harness(tmp_path, FAKEKIMI_VERSION=SECRET)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert SECRET not in receipt.detail
    assert SECRET not in str(receipt)
