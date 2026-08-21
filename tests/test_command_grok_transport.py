"""Grok Build driven for real, against a fake that is a REAL single executable.

Every claim here is a relation driven through the real provider door, the real
owned-process runner and a real child process: the fake stands in for the pinned
binary, never for the adapter. A spawn is counted by the line the child itself
wrote, the isolated home is read out of the child's own environment, and the
absence of a planted secret is checked against every value the adapter can hand
onward.

What is held here is what is specific to Grok Build, and two of those are new to
this roster:

- its version print is a whole LINE that begins with the program name and
  carries a commit and often a channel, so this adapter PARSES the published form
  instead of comparing the whole line -- and neither the program name, the commit
  nor the channel may ever be read as a version;
- FOUR documented switches must be off, not one, so every spawn is checked
  against all four rather than against the one that happened to be spelled.

The relations the shared transport owns -- the marker, the sweep, the retention
promise against a hostile child, the containment of every written route -- are
held once, in the dsh suite, against the same code.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.adapters.grok_build import (
    GROK_FORCED_ENV,
    GROK_HOME_ENV,
    GROK_PROTOCOL,
    GROK_PROVIDER_ID,
    HOME_DIR,
    INSTRUCTION_DIR,
    MARKER_DIR,
    REVIEWED_GROK_VERSION,
    GrokBuildAdapter,
    GrokBuildError,
    grok_pin,
)
from conductor.command.adapters.kimi_code import KimiCodeError
from conductor.command.adapters.headless_cli import ExecutablePin, ProcessOutcome
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.contracts import ActionRequest
from conductor.command.providers import resolve_providers

from tests import _fakegrok

NOW = "2026-08-21T12:00:00Z"
DIGEST = "sha256:" + "a" * 64
SECRET = "sk-live-planted-grok-secret"
INSTRUCTION_BODY = "Add the missing guard and prove it with one failing test."


class _Ids:
    """A deterministic id mint that never repeats a value."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count}"


def _executable(tmp_path: Path) -> Path:
    exe = _fakegrok.build_executable(tmp_path / "bin")
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
    """A registered, available Grok provider over the fake, its root and its log."""
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    instructions = root / INSTRUCTION_DIR
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    log = tmp_path / "spawns.log"
    environ = {_fakegrok.SPAWN_LOG: str(log), **knobs}
    config = ProviderConfig(
        provider_id=GROK_PROVIDER_ID, executable=str(exe),
        protocol=GROK_PROTOCOL, env_allow=tuple(sorted(environ)))
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ=environ)
    return resolution.registry.resolve(GROK_PROVIDER_ID), root, log


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


class _RecordingRunner(ProcessRunner):
    """Keeps every CommandSpec it was handed and starts no child.

    The WHOLE argv only exists here. A child cannot see its own parent's command
    line, and for this fake it cannot even infer it -- the executable is a
    launcher stub with an appended zip, which Python will itself run as a zip
    application -- so a self-report can never witness "nothing in front of the
    pin". The spec can.
    """

    def __init__(self, root) -> None:
        super().__init__(root)
        self.specs: list[object] = []

    def run(self, spec):  # type: ignore[override]
        self.specs.append(spec)
        return ProcessOutcome(
            status="completed", exit_code=0,
            # The line a REAL release binary prints, not the bare semver it never
            # prints -- so every test driven through this runner exercises the
            # form the parser was corrected to accept.
            output=_fakegrok.DEFAULT_VERSION.encode("utf-8") + b"\n",
            output_truncated=False, output_limit=spec.output_limit, pid=0,
            token="recorded")


def _recorded(tmp_path: Path):
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / INSTRUCTION_DIR).mkdir()
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    runner = _RecordingRunner(root)
    adapter = GrokBuildAdapter(
        grok_pin(str(exe)), runner, root=root, clock=lambda: NOW, ids=_Ids())
    return adapter, runner, exe


# --- the pin is one path, and the argv is the vendor's documented shape --------


def test_the_whole_argv_is_the_pinned_binary_and_this_builds_own_flags(tmp_path):
    """``<pin> --no-auto-update --output-format plain --single <task>``.

    Read off the spec the adapter built, because that is the only place the whole
    command exists. ``--no-auto-update`` stands FIRST and is not optional here: a
    background update check during a dispatch would change the very build the
    preflight just proved.
    """
    adapter, runner, exe = _recorded(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    argvs = [tuple(spec.argv) for spec in runner.specs]  # type: ignore[attr-defined]
    assert argvs[0] == (str(exe), "--version"), f"PREFLIGHT_ARGV={argvs[0]}"
    prompt = argvs[1]
    assert prompt[:5] == (
        str(exe), "--no-auto-update", "--output-format", "plain",
        "--single"), f"PROMPT_ARGV={prompt}"
    assert len(prompt) == 6, f"UNEXPECTED_ARGV={prompt}"
    for argv in argvs:
        assert argv[0] == str(exe), f"SOMETHING_STANDS_IN_FRONT_OF_THE_PIN={argv}"


def test_one_pinned_binary_and_code_owned_flags_really_run_a_child(tmp_path):
    """The same command, driven all the way through a real process."""
    adapter, _root, log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    prompts = _fakegrok.prompt_spawns(log)
    assert len(prompts) == 1
    argv = prompts[0]["argv"]
    assert argv[:4] == [
        "--no-auto-update", "--output-format", "plain", "--single"]
    assert len(argv) == 5, f"UNEXPECTED_ARGV={argv}"
    for row in _fakegrok.spawns(log):
        rendered = " ".join(row["argv"]).lower()
        for banned in ("npx", "npm", ".cmd", "-c ", "&&", "|"):
            assert banned not in rendered, f"SHELL_SHAPED_ARGV={row['argv']}"


def test_the_prompt_carries_the_materialized_instruction_and_not_its_reference(
        tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    prompt = _fakegrok.prompt_spawns(log)[0]["argv"][4]
    assert INSTRUCTION_BODY in prompt, "PROMPT_LACKS_THE_INSTRUCTION_TEXT=True"
    assert "instr-001" in prompt


def test_a_relative_pin_is_refused_before_any_child_can_exist():
    for bad in ("grok", "./grok", "bin/grok"):
        with pytest.raises(GrokBuildError, match="absolute operator pin"):
            grok_pin(bad)


def test_a_pin_built_for_another_provider_is_not_this_adapters_pin(tmp_path):
    """The pin SHAPE is shared with Kimi Code, so the class alone binds nothing."""
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    foreign = ExecutablePin(
        executable=str(exe), error=KimiCodeError, env_allow=())

    with pytest.raises(GrokBuildError, match="pin of its own"):
        GrokBuildAdapter(
            foreign, _RecordingRunner(root), root=root, clock=lambda: NOW,
            ids=_Ids())


@pytest.mark.parametrize("entrypoint_exists", (True, False))
def test_an_entrypoint_pinned_against_a_single_binary_costs_availability(
        tmp_path, entrypoint_exists):
    """Grok Build runs no interpreter, so an entrypoint beside it is unhonourable.

    The answer is unavailability rather than a raise, so one bad config costs its
    own provider and never the roster; both disk states are held because the
    config's SHAPE decides, not the disk.
    """
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    entrypoint = str(exe) if entrypoint_exists else str(tmp_path / "absent.js")
    config = ProviderConfig(
        provider_id=GROK_PROVIDER_ID, executable=str(exe),
        protocol=GROK_PROTOCOL, entrypoint=entrypoint)

    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ={})

    described = next(
        row for row in resolution.contracts if row.provider_id == GROK_PROVIDER_ID)
    assert described.available is False
    assert resolution.spawn_capable(GROK_PROVIDER_ID) is False
    assert len(resolution.contracts) >= 5, "THE_WHOLE_ROSTER_WAS_LOST"


# --- the version is PARSED, and only its semver counts ------------------------


#: Every shape the vendor's own composition can produce, built as an explicit
#: cross-product so a form cannot be dropped by editing prose. The vendor builds
#: the line by wrapping the version crate's string with the program name and a
#: newline, and each of the three parts is independently optional in the sources:
#: the program name because `display_version_with_commit` is also called
#: directly, the commit because `full_version()` may carry none, and the channel
#: because `channel_label()` returns "" on a build with no channel.
_PREFIXES = ("", "grok ")
_COMMITS = ("", " (abc1234)")
_CHANNELS = ("", " [stable]", " [alpha]")
ACCEPTED_FORMS = tuple(
    f"{prefix}1.0.5{commit}{channel}"
    for prefix in _PREFIXES for commit in _COMMITS for channel in _CHANNELS)
#: Commit CONTENTS the sources publish beyond a 7-hex hash: `build.rs` falls back
#: to the literal `unknown`, and `git rev-parse --short` honours `core.abbrev`, so
#: neither the alphabet nor the length is this module's to assume.
ACCEPTED_COMMITS = (
    "grok 1.0.5 (unknown)",
    "grok 1.0.5 (def0)",
    "grok 1.0.5 (0123456789abcdef0123456789abcdef01234567) [stable]",
)


def test_the_accepted_set_is_the_whole_cross_product_and_nothing_was_dropped():
    """A count, so editing the lists above cannot silently narrow coverage."""
    assert len(ACCEPTED_FORMS) == len(_PREFIXES) * len(_COMMITS) * len(_CHANNELS)
    assert len(ACCEPTED_FORMS) == 12
    assert "grok 1.0.5" in ACCEPTED_FORMS, "the bare prefixed form must be covered"
    assert "1.0.5" in ACCEPTED_FORMS, "the bare crate-level form must be covered"
    assert len(set(ACCEPTED_FORMS) | set(ACCEPTED_COMMITS)) == 15


@pytest.mark.parametrize("printed", ACCEPTED_FORMS + ACCEPTED_COMMITS)
def test_every_published_form_of_the_version_print_is_accepted(tmp_path, printed):
    """Every shape a real install can print, driven end to end through a child.

    This list is the correction of a defect that would have shipped: the first
    version of this adapter modelled the version CRATE and never read the entry
    point that adds the `grok ` prefix, so it refused every string a real Grok
    Build prints -- while the row still reported itself available. The provider
    could not have dispatched once.
    """
    adapter, _root, log = a_harness(tmp_path, FAKEGROK_VERSION=printed)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", f"REFUSED_A_PUBLISHED_FORM={printed!r}"
    assert len(_fakegrok.prompt_spawns(log)) == 1


#: The refusal matrix, grouped by WHAT is wrong, so a failure names its category
#: rather than one string among many.
REFUSED_FORMS = (
    # a different version
    ("version", "1.0.4"),
    ("version", "grok 1.0.4 (abc1234) [stable]"),
    ("version", "1.0.50"),
    ("version", "grok 1.0.50"),
    ("version", "1.0.5.1"),
    ("version", "grok 1.0.5-rc.1"),
    ("version", "grok 1.0.5+meta"),
    ("version", "01.0.5"),
    # a prefix that is not the program name
    ("prefix", "krog 1.0.5"),
    ("prefix", "grok  1.0.5"),
    ("prefix", "GROK 1.0.5"),
    ("prefix", "the grok 1.0.5 release"),
    ("prefix", "v1.0.5"),
    # a commit that is not a parenthesised token
    ("commit", "grok 1.0.5 (abc 1234)"),
    ("commit", "grok 1.0.5 ()"),
    ("commit", "grok 1.0.5 abc1234"),
    ("commit", "grok 1.0.5 (abc1234"),
    ("commit", "grok 1.0.5 ((abc1234))"),
    # a channel the sources do not publish
    ("channel", "grok 1.0.5 (abc1234) [beta]"),
    ("channel", "grok 1.0.5 [STABLE]"),
    ("channel", "grok 1.0.5 stable"),
    ("channel", "grok 1.0.5 [stable] [alpha]"),
    # anything extra on the line
    ("extra", "1.0.5 extra"),
    ("extra", "grok 1.0.5 (abc1234) [stable] warning"),
    ("extra", "(1.0.5)"),
    ("extra", "abc1234"),
    ("extra", ""),
    ("extra", "warning: cache is stale"),
)


@pytest.mark.parametrize(
    "category,printed", REFUSED_FORMS,
    ids=[f"{category}-{index}" for index, (category, _) in enumerate(REFUSED_FORMS)])
def test_no_other_shape_is_read_as_the_reviewed_version(tmp_path, category, printed):
    """Zero prompt spawns is the assertion that matters.

    A refusal that still spawned would be no refusal, so every case is checked
    against the child's own spawn log rather than against the receipt alone.
    """
    adapter, _root, log = a_harness(tmp_path, FAKEGROK_VERSION=printed)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", f"ACCEPTED[{category}]={printed!r}"
    assert REVIEWED_GROK_VERSION in receipt.detail
    assert _fakegrok.prompt_spawns(log) == [], (
        f"PROMPT_SPAWNED_ON[{category}]={printed!r}")


#: Shapes that cannot travel through an environment variable, so they are put to
#: the parser as the RAW BYTES the transport really hands it. Multiline and
#: non-UTF-8 belong here: `_version_token` reads the first non-empty line and
#: decodes with `errors="replace"`, and both readings must refuse rather than
#: find a version somewhere in the noise.
REFUSED_BYTES = (
    ("multiline", b"warning: stale\n1.0.5\n"),
    ("multiline", b"grok 1.0.4\ngrok 1.0.5\n"),
    ("non-utf8", b"\xff\xfe1.0.5"),
    ("non-utf8", b"grok \xc3(1.0.5)"),
    ("non-utf8", b"\xef\xbb\xbfgrok 1.0.5 (abc1234)"),
    ("non-utf8", "grok 1.0.5 (abc1234)".encode("utf-16-le")),
    ("control", b"grok 1.0.5\x00"),
    ("control", b"\x1b[32mgrok 1.0.5\x1b[0m"),
    ("digits", "grok \u0661.\u0660.\u0665".encode("utf-8")),
)


@pytest.mark.parametrize(
    "category,raw", REFUSED_BYTES,
    ids=[f"{category}-{index}" for index, (category, _) in enumerate(REFUSED_BYTES)])
def test_no_byte_sequence_outside_the_published_form_is_a_version(
        tmp_path, category, raw):
    """Put to the parser directly, because these cannot pass through an env var.

    A multiline print must not have its version fished out of a later line, and
    a non-UTF-8 print must refuse rather than be repaired into something that
    parses. The answer is a BOOLEAN either way, so nothing derived from these
    bytes can reach a caller.
    """
    adapter, _runner, _exe = _recorded(tmp_path)

    assert adapter._version_matches(raw) is False, (
        f"ACCEPTED_BYTES[{category}]={raw!r}")


def test_the_one_byte_sequence_that_is_the_reviewed_version_is_accepted():
    """The positive control, so the test above cannot pass by refusing everything."""
    exe_free = GrokBuildAdapter.__new__(GrokBuildAdapter)

    assert GrokBuildAdapter._version_matches(
        exe_free, b"grok 1.0.5 (abc1234) [stable]\n") is True


#: A correct first line FOLLOWED by other output. Accepted, and named here rather
#: than left to be discovered: `_version_token` reads the first non-empty line,
#: which is a shared contract all three transports rest on and which this slice
#: did not invent. What matters is the direction -- a banner BEFORE the version is
#: never fished past, which the refusal matrix holds -- and that trailing chatter
#: from a reviewed build does not stop a dispatch it should not stop.
TOLERATED_TRAILING = (
    b"grok 1.0.5\nsecond line\n",
    b"\n\ngrok 1.0.5 (abc1234)\nmore\n",
    b"grok 1.0.5 (abc1234) [stable]\nwarning: cache is stale\n",
)


@pytest.mark.parametrize("raw", TOLERATED_TRAILING)
def test_output_after_a_correct_first_line_does_not_refuse_the_build(raw):
    """The boundary of the shared first-line reading, stated out loud.

    A build that prints the reviewed version and then a warning is still the
    reviewed build. Refusing it would be a false refusal of the kind that made
    this provider undispatchable in the first place, so the tolerance is
    deliberate -- and it is bounded on the side that matters by
    `test_no_byte_sequence_outside_the_published_form_is_a_version`, where a
    banner ahead of the version refuses.
    """
    unbound = GrokBuildAdapter.__new__(GrokBuildAdapter)

    assert GrokBuildAdapter._version_matches(unbound, raw) is True


def test_a_banner_before_the_version_is_never_fished_past(unused=None):
    """The other side of the same boundary, held as its own claim.

    This is the asymmetry: output AFTER a correct first line is tolerated, and
    output BEFORE it is fatal -- because the first non-empty line is the only
    line read, so a warning printed first IS the token.
    """
    unbound = GrokBuildAdapter.__new__(GrokBuildAdapter)

    assert GrokBuildAdapter._version_matches(
        unbound, b"warning: cache is stale\ngrok 1.0.5 (abc1234)\n") is False


def test_a_version_print_the_build_cannot_answer_spawns_zero_prompts(tmp_path):
    adapter, _root, log = a_harness(tmp_path, FAKEGROK_VERSION_FAILS="1")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "version preflight" in receipt.detail
    assert _fakegrok.prompt_spawns(log) == []


def test_the_reviewed_version_is_proved_before_any_prompt_is_spawned(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    spawns = _fakegrok.spawns(log)
    assert spawns[0]["argv"] == ["--version"], "THE_PREFLIGHT_IS_NOT_FIRST=True"
    assert len(_fakegrok.prompt_spawns(log)) == 1


def test_a_secret_planted_where_a_version_belongs_never_reaches_a_receipt(tmp_path):
    """The observed token is parsed and compared, never reported."""
    adapter, _root, _log = a_harness(tmp_path, FAKEGROK_VERSION=SECRET)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert SECRET not in receipt.detail
    assert SECRET not in str(receipt)


# --- the home is fresh, and all FOUR switches are off ------------------------


def test_every_spawn_gets_a_fresh_home_under_this_providers_own_root(tmp_path):
    adapter, root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    homes = [row["grok_home"] for row in _fakegrok.spawns(log)]
    assert len(homes) == 2, f"EXPECTED_PREFLIGHT_AND_PROMPT={homes}"
    assert len(set(homes)) == 2, "TWO_SPAWNS_SHARED_ONE_HOME=True"
    for home in homes:
        assert Path(home).parent == (root / HOME_DIR).resolve(), (
            f"HOME_OUTSIDE_THIS_PROVIDERS_ROOT={home}")
        assert Path(home).name.startswith("grok-home"), (
            f"HOME_NOT_NAMED_FOR_ITS_PROVIDER={home}")


def test_all_four_documented_switches_are_turned_off_on_every_spawn(tmp_path):
    """Four, not one. A test that checked the master switch alone would pass
    while session traces, Mixpanel and feedback all stayed on."""
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    # The VALUE is spelled here as a literal. Comparing against
    # `dict(GROK_FORCED_ENV)` made both sides of this assertion the same
    # constant, so flipping the published disable value -- turning telemetry,
    # trace upload, Mixpanel and feedback all ON -- left the entire suite green.
    # The NAMES still come from the adapter, cross-checked against the fake, so
    # a fifth switch appearing cannot pass unnoticed either.
    assert set(dict(GROK_FORCED_ENV)) == set(_fakegrok.SWITCH_NAMES), (
        "the adapter and the fake disagree about which switches exist")
    expected = {name: "0" for name in _fakegrok.SWITCH_NAMES}
    for row in _fakegrok.spawns(log):
        assert row["switches"] == expected, f"SWITCH_NOT_OFF={row['switches']}"


def test_no_attempt_home_survives_a_completed_dispatch(tmp_path):
    adapter, root, _log = a_harness(
        tmp_path, FAKEGROK_HOME_FILE="config.toml:[features]\n")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    standing = sorted(path.name for path in (root / HOME_DIR).iterdir())
    assert standing == [], f"HOME_SURVIVED_THE_DISPATCH={standing}"


def test_a_credential_the_operator_did_not_allow_never_reaches_the_child(
        tmp_path, monkeypatch):
    """``XAI_API_KEY`` is the vendor's documented shell channel, so it is the
    exact name whose leak would matter."""
    monkeypatch.setenv("XAI_API_KEY", "xai-live-never-allowed")
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    names = set(_fakegrok.spawns(log)[0]["env_names"])
    assert names == {
        GROK_HOME_ENV, *_fakegrok.SWITCH_NAMES, _fakegrok.SPAWN_LOG}, (
        f"THE_CHILD_ENVIRONMENT_IS_NOT_THE_ONE_THIS_BUILD_GAVE_IT: {sorted(names)}")
    assert "XAI_API_KEY" not in names


# --- what an exit code is allowed to mean, and what verification may claim ----


def test_exit_zero_says_the_vendor_published_no_exit_code_contract(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    assert receipt.exit_code == 0
    assert "no exit-code contract" in receipt.detail
    assert "not a verification" in receipt.detail


def test_a_non_zero_exit_is_observed_as_failed_and_carries_the_code(tmp_path):
    adapter, _root, _log = a_harness(tmp_path, FAKEGROK_EXIT="4")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert receipt.exit_code == 4


def test_output_past_the_capture_bound_can_never_be_called_a_success(tmp_path):
    adapter, _root, _log = a_harness(tmp_path, FAKEGROK_BOMB_BYTES="200000")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "capture bound" in receipt.detail


def test_a_prompt_past_its_timeout_is_terminated_and_reported(tmp_path):
    adapter, _root, _log = a_harness(tmp_path, FAKEGROK_SLEEP="30")

    receipt = run_once(adapter, a_request(timeout=2))

    assert receipt.outcome == "failed"
    assert "timeout" in receipt.detail


def test_a_real_change_inside_the_authorized_subtree_still_never_reaches_verified(
        tmp_path):
    adapter, _root, _log = a_harness(
        tmp_path, FAKEGROK_WRITE_FILE="guard.py:# a real change\n")
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    assert receipt.outcome == "succeeded"
    assert verification.state == "error"
    assert verification.evidence_refs == ()
    assert "no durable evidence record" in verification.detail


def test_a_change_outside_the_authorized_subtree_is_a_mismatch(tmp_path):
    adapter, _root, _log = a_harness(
        tmp_path, FAKEGROK_ESCAPE_FILE="stolen.py:# outside the work item\n")
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
    assert "changed nothing" in verification.detail


# --- a crashed prompt is never run twice, and no secret escapes ---------------


def test_a_marker_from_an_earlier_attempt_stops_a_second_prompt(tmp_path):
    adapter, root, log = a_harness(tmp_path)
    request = a_request()
    first = run_once(adapter, request)

    second = run_once(adapter, request)

    assert first.outcome == "succeeded"
    assert second.outcome == "unknown"
    assert "never repeated" in second.detail
    assert len(_fakegrok.prompt_spawns(log)) == 1, "THE_PROMPT_RAN_TWICE=True"
    assert (root / MARKER_DIR / "act-1.marker").is_file()


def test_a_secret_the_child_prints_reaches_no_receipt_and_no_verification(tmp_path):
    adapter, _root, _log = a_harness(
        tmp_path, FAKEGROK_STDOUT=SECRET, FAKEGROK_STDERR=SECRET)
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    assert SECRET not in receipt.detail
    assert SECRET not in str(receipt)
    assert SECRET not in verification.detail
    assert SECRET not in str(verification)
