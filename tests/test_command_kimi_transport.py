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
    KIMI_HOME_ENV,
    KIMI_PROTOCOL,
    KIMI_PROVIDER_ID,
    KIMI_TELEMETRY_ENV,
    MARKER_DIR,
    REVIEWED_KIMI_VERSION,
    KimiCodeAdapter,
    KimiCodeError,
    kimi_pin,
)
from conductor.command.adapters.dsh_harness import DshHarnessError
from conductor.command.adapters.headless_cli import (
    ExecutablePin,
    HeadlessCliError,
)
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner
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
        # Name the CAUSE. "This platform" blamed the platform for what is almost
        # always an environment fact -- no console-script launcher to copy -- and
        # a skip that misattributes its reason is how a builder fault hides.
        # tests/test_fake_executable_builder.py holds the builder directly, so
        # the fault has somewhere to be reported that cannot skip.
        pytest.skip(
            "no console-script launcher stub is available to copy in this "
            "environment, so no shell-free single-file executable can be built")
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
        "profile": "implement", "artifact_refs": [],
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


class _RecordingRunner(ProcessRunner):
    """A runner that keeps every CommandSpec it was handed and starts no child.

    The WHOLE argv is only observable here. A child cannot see its own parent's
    command line, and for this fake it cannot even infer it: `kimi.exe` is a
    launcher stub with an appended zip, and Python will run such a file as a zip
    application, so `python kimi.exe --version` hands the child exactly the
    `sys.argv` that `kimi.exe --version` does. A self-report can therefore never
    witness "nothing in front of the pin" -- the spec can.
    """

    def __init__(self, root) -> None:
        super().__init__(root)
        self.specs: list[object] = []

    def run(self, spec):  # type: ignore[override]
        self.specs.append(spec)
        return ProcessOutcome(
            status="completed", exit_code=0,
            output=REVIEWED_KIMI_VERSION.encode("utf-8") + b"\n",
            output_truncated=False, output_limit=spec.output_limit, pid=0,
            token="recorded")


def test_the_whole_argv_is_the_pinned_binary_and_this_builds_own_flags(tmp_path):
    """``<pin> --output-format text --prompt <task>``, and NOTHING in front of it.

    Read off the spec the adapter built, because that is the only place the whole
    command exists. The end-to-end test below proves a real child really runs;
    this one proves what it is asked to run, argv[0] included.
    """
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / INSTRUCTION_DIR).mkdir()
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    runner = _RecordingRunner(root)
    adapter = KimiCodeAdapter(
        kimi_pin(str(exe)), runner, root=root, clock=lambda: NOW, ids=_Ids())

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    argvs = [tuple(spec.argv) for spec in runner.specs]  # type: ignore[attr-defined]
    assert argvs[0] == (str(exe), "--version"), f"PREFLIGHT_ARGV={argvs[0]}"
    prompt = argvs[1]
    assert prompt[:4] == (
        str(exe), "--output-format", "text", "--prompt"), f"PROMPT_ARGV={prompt}"
    assert len(prompt) == 5, f"UNEXPECTED_ARGV={prompt}"
    for argv in argvs:
        assert argv[0] == str(exe), f"SOMETHING_STANDS_IN_FRONT_OF_THE_PIN={argv}"


def test_one_pinned_binary_and_code_owned_flags_really_run_a_child(tmp_path):
    """The same command, driven all the way through a real process.

    What this adds to the spec test above is that the flags are ones the pinned
    file really accepts: a real child ran, exited, and reported the argv it saw.
    It cannot see in front of the pin -- see `_RecordingRunner` for why -- so it
    does not claim to.
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


def test_a_pin_built_for_another_provider_is_not_this_adapters_pin(tmp_path):
    """The pin SHAPE is shared, so the class alone binds nothing.

    ``ExecutablePin`` is neutral by design -- every single-binary product pins
    exactly one absolute path -- which means ``type(pin) is ExecutablePin`` says
    only "somebody's pin". Deleting that check left the whole suite green, so
    what the adapter really needs to know is whose refusal type the pin carries:
    a pin built for another provider refuses as that provider, and a caller
    catching this one's error would never see it.
    """
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    foreign = ExecutablePin(
        executable=str(exe), error=DshHarnessError, env_allow=())

    with pytest.raises(KimiCodeError, match="pin of its own"):
        KimiCodeAdapter(
            foreign, _RecordingRunner(root), root=root, clock=lambda: NOW,
            ids=_Ids())


@pytest.mark.parametrize("bad", (None, "KimiCodeError", RuntimeError, object()))
def test_a_pin_whose_refusal_type_is_not_one_is_refused(tmp_path, bad):
    """The field is required AND proved, because it decides how a pin refuses.

    It used to default to the shared base class and was never checked, so a pin
    could carry a string, an unrelated exception, or nothing at all and still be
    constructed -- and then refuse as a type no provider's callers name.
    """
    exe = _executable(tmp_path)

    with pytest.raises(HeadlessCliError, match="refusal type"):
        ExecutablePin(executable=str(exe), error=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("entrypoint_exists", (True, False))
def test_an_entrypoint_pinned_against_a_single_binary_costs_availability(
        tmp_path, entrypoint_exists):
    """Half of what the operator wrote down would otherwise be silently dropped.

    Kimi Code runs no interpreter, so an entrypoint pinned beside it is a config
    this build cannot honour: the operator believes a second file is run, and
    nothing here would run it.

    The answer is UNAVAILABILITY, not an exception. Raising from the adapter
    factory took the whole roster down -- `conduct up` does not catch
    ProviderConfigError, so one typo ended the server with a traceback and no
    descriptor for ANY provider -- and it fired only when the pinned entrypoint
    really existed, which is the case that needed it least. Both cases are held
    here for exactly that reason: the shape of the config decides, not the disk.
    """
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    entrypoint = str(exe) if entrypoint_exists else str(tmp_path / "absent.js")
    config = ProviderConfig(
        provider_id=KIMI_PROVIDER_ID, executable=str(exe),
        protocol=KIMI_PROTOCOL, entrypoint=entrypoint)

    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ={})

    described = next(
        row for row in resolution.contracts if row.provider_id == KIMI_PROVIDER_ID)
    assert described.available is False
    assert resolution.spawn_capable(KIMI_PROVIDER_ID) is False
    # Every catalogued provider is still described: one bad config costs its own
    # provider its availability and costs the roster nothing.
    assert len(resolution.contracts) >= 4, "THE_WHOLE_ROSTER_WAS_LOST"


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


def test_a_credential_the_operator_did_not_allow_never_reaches_the_child(
        tmp_path, monkeypatch):
    """A name absent from the allowlist stays absent, even when the parent HAS it.

    The earlier version of this test proved nothing twice over: it allowed every
    name it then read back, and the credential it denied was never set anywhere,
    so a runner that copied the whole parent environment would have passed. The
    denial is real now -- ``KIMI_API_KEY`` is set in this process and left OUT of
    the operator's allowlist, and the vendor's own docs name it as a credential
    variable, so this is the exact shape of the leak that would matter.
    """
    monkeypatch.setenv("KIMI_API_KEY", "sk-live-never-allowed")
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    # A BOUND, not a membership. The dsh suite already held this relation with
    # set equality; asserting one hand-picked absence was a weaker copy of a
    # working guard, and a runner that copied the whole parent environment would
    # have satisfied it.
    names = set(_fakekimi.spawns(log)[0]["env_names"])
    assert names == {
        KIMI_HOME_ENV, KIMI_TELEMETRY_ENV, _fakekimi.SPAWN_LOG}, (
        "THE_CHILD_ENVIRONMENT_IS_NOT_THE_ONE_THIS_BUILD_GAVE_IT: "
        f"{sorted(names)}")
    assert "KIMI_API_KEY" not in names


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


def test_verification_judges_the_evidence_read_under_the_turn_not_the_live_tree(
        tmp_path):
    """A neighbour's later work cannot be charged to this action's child.

    The runtime serializes on `(run_id, action_id)`, so another provider's whole
    dispatch can land between this `execute` returning and `verify` being called.
    While the evidence was re-read at verify time, that neighbour's ordinary work
    appeared in this action's diff and came back as `mismatch` -- a change
    "outside the authorized work subtree" that this child never made.

    Both snapshots are taken inside the dispatch's turn now, so what is judged is
    what was read. The foreign directory below stands in for the neighbour, and
    it is written AFTER execute returns, which is exactly when the turn is over.
    """
    adapter, root, _log = a_harness(
        tmp_path, FAKEKIMI_WRITE_FILE="guard.py:# a real change\n")
    request = a_request()
    receipt = run_once(adapter, request)

    foreign = root / "work" / "neighbour-work-item"
    foreign.mkdir(parents=True)
    (foreign / "theirs.txt").write_text("another provider's work", encoding="utf-8")
    verification = adapter.verify(request, receipt)

    assert receipt.outcome == "succeeded"
    assert verification.state != "mismatch", (
        f"A_NEIGHBOURS_WORK_WAS_CHARGED_TO_THIS_CHILD detail={verification.detail}")
    assert verification.state == "error"
    assert "no durable evidence record" in verification.detail


def test_a_prompt_that_changed_nothing_is_an_error_and_not_a_success(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    assert receipt.outcome == "succeeded"
    assert verification.state == "error"
    assert verification.state != "unavailable", (
        "an adapter that HAS a verifier must never borrow the absent-verifier token")
    # The STATE is shared by three different branches, so it cannot tell this
    # one apart. The sentence can: swapping the no-change branch for the
    # durable-evidence one would tell an operator files changed when none did.
    assert "changed nothing" in verification.detail, (
        f"THE_WRONG_ERROR_BRANCH_ANSWERED detail={verification.detail}")


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
