"""Claude Code driven for real, against a fake that is a REAL single executable.

Every claim here is a relation driven through the real provider door, the real
owned-process runner and a real child process: the fake stands in for the pinned
binary, never for the adapter.

What is held here is what is specific to Claude Code, and one of those is new to
this roster:

- **its task travels by STDIN**, not argv. That is the first provider to do so,
  so this file holds both halves: the child really received the exact bytes, and
  the command line really carries none of them. The exactness is a DIGEST the
  child computes and this side recomputes, because a fake that echoed the
  instruction back would put the operator's prose legitimately into the child's
  own output and no leak assertion anywhere could then tell an echo from a leak;
- **``--bare`` is a containment flag, not a speed one.** Without it a ``-p``
  session runs the hooks in a ``.claude/settings.json`` it finds and connects
  the servers in a ``.mcp.json``, with no trust dialog -- and this build spawns
  the child INSIDE the work tree the workspace door handed the run;
- **the two switches must hold on BOTH spawns.** ``DISABLE_AUTOUPDATER`` is a
  version invariant rather than a privacy one: an update between the version
  preflight and the task would mean this build proved one binary and ran another;
- **its version print is described and never observed.** The parser reads one
  closed form; every other shape is refused with zero prompt spawns.

The relations the shared transport owns -- the marker, the sweep, the retention
promise against a hostile child, the containment of every written route -- are
held once, in the dsh suite, against the same code.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from conductor.command.adapters.claude_code import (
    CLAUDE_FORCED_ENV,
    CLAUDE_HOME_ENV,
    CLAUDE_PROTOCOL,
    CLAUDE_PROVIDER_ID,
    CONSTANT_PROMPT,
    HOME_DIR,
    INSTRUCTION_DIR,
    MARKER_DIR,
    REVIEWED_CLAUDE_VERSION,
    ClaudeCodeError,
    ClaudeCodeTransport,
    claude_pin,
)
from conductor.command.adapters.grok_build import GrokBuildError
from conductor.command.adapters.headless_cli import ExecutablePin
from conductor.command.adapters.process import (
    STDIN_DELIVERED,
    STDIN_INCOMPLETE,
    ProcessOutcome,
    ProcessRunner,
)
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.contracts import ActionRequest
from conductor.command.graph_template import load_template
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers

from tests import _fakeclaude

NOW = "2026-08-22T12:00:00Z"
DIGEST = "sha256:" + "a" * 64
INSTRUCTION_BODY = "Add the missing guard and prove it with one failing test."


class _Ids:
    """A deterministic id mint that never repeats a value."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count}"


def _executable(tmp_path: Path) -> Path:
    exe = _fakeclaude.build_executable(tmp_path / "bin")
    if exe is None:
        pytest.skip(
            "no console-script launcher stub is available to copy in this "
            "environment, so no shell-free single-file executable can be built")
    return exe


def a_harness(tmp_path: Path, *, instruction: str = INSTRUCTION_BODY,
              root: Path | None = None, **knobs: str):
    """A registered, available Claude provider over the fake, its root and its log.

    The spawn log lives beside the root and never inside it: it is a test
    artefact, and a file this build does not sweep has no business under a tree
    whose whole promise is that this build sweeps it.
    """
    exe = _executable(tmp_path)
    # A caller may hand in a root it already owns -- a served project, say -- so
    # the provider resolves against the SAME tree the rest of the run uses.
    root = (tmp_path / "root") if root is None else Path(root)
    root.mkdir(parents=True, exist_ok=True)
    instructions = root / INSTRUCTION_DIR
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        instruction, encoding="utf-8", newline="\n")
    log = tmp_path / "spawns.log"
    environ = {_fakeclaude.SPAWN_LOG: str(log), **knobs}
    config = ProviderConfig(
        provider_id=CLAUDE_PROVIDER_ID, executable=str(exe),
        protocol=CLAUDE_PROTOCOL, env_allow=tuple(sorted(environ)))
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ=environ)
    return resolution.registry.resolve(CLAUDE_PROVIDER_ID), root, log


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


def _prompt_row(log: Path) -> dict:
    """The one prompt spawn, refusing to guess when there is not exactly one."""
    rows = _fakeclaude.prompt_spawns(log)
    assert len(rows) == 1, f"EXPECTED_ONE_PROMPT_SPAWN={len(rows)}"
    return rows[0]


# --- the task travels by stdin, and only by stdin -----------------------------


def test_the_child_receives_the_whole_task_on_stdin_and_the_bytes_are_exact(
        tmp_path):
    """A digest computed on the far side and recomputed here.

    Exactness matters more for this provider than for any other in the roster:
    a truncated instruction is not a failed dispatch, it is a DIFFERENT one, and
    nothing downstream would say so. The frame this build composes stands ahead
    of the operator's instruction, so both are checked -- the instruction by its
    presence, the whole by its digest.
    """
    adapter, _root, log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    row = _prompt_row(log)
    assert row["stdin"]["read"] is True
    assert row["stdin"]["bytes"] > len(INSTRUCTION_BODY)
    # The exact bytes, rebuilt from the same two parts the transport composes.
    task = adapter._task_text(
        adapter._dispatch_args(a_request().arguments), INSTRUCTION_BODY)
    assert row["stdin"]["sha256"] == hashlib.sha256(
        task.encode("utf-8")).hexdigest(), "THE_CHILD_READ_DIFFERENT_BYTES"
    assert row["stdin"]["bytes"] == len(task.encode("utf-8"))


def test_the_whole_argv_is_the_pinned_binary_and_this_builds_own_flags(tmp_path):
    """Every token is code-owned, and the prompt argument is a CONSTANT.

    The constant is asserted as a whole token rather than by substring: what
    makes it safe is that it is the same sentence on every dispatch for every
    operator, carrying no run, no work item and no instruction.
    """
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    argv = _prompt_row(log)["argv"]
    # Every token is SPELLED. Reading `CONSTANT_PROMPT` from the module here
    # would put the same value on both sides of the comparison, so any edit to
    # the sentence would move both and this would keep passing -- which is what
    # it did until a mutation said so.
    assert argv == [
        "--bare", "-p", "Execute the complete task supplied on standard input.",
        "--input-format", "text", "--output-format", "text",
        "--no-session-persistence", "--permission-mode", "acceptEdits"], argv
    assert argv[0] == "--bare", "the containment flag must stand first"
    # And the spelled sentence really is the one the module ships, so the two
    # cannot drift apart silently in the other direction either.
    assert CONSTANT_PROMPT == argv[2]


def test_no_byte_of_the_operators_instruction_reaches_argv_or_the_environment(
        tmp_path):
    """Asked of the CHILD, with a probe token that arrives only by stdin.

    The child extracts the token from the task it read and then scans its own
    argv, its own cwd and EVERY value of its own environment. No channel is
    exempted, and the token never travelled by any of them, so a hit would be a
    real leak rather than an artefact of how the test delivered it.
    """
    probe = _fakeclaude.PROBE_PREFIX + "ab12cd34" * 8
    adapter, _root, log = a_harness(
        tmp_path, instruction=f"{INSTRUCTION_BODY} {probe}",
        **{_fakeclaude.LEAK_CHECK: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert _prompt_row(log)["marker"] == {
        "in_stdin": True, "in_argv": False, "in_cwd": False, "in_env": False}


def test_a_task_the_leak_witness_cannot_scan_fails_instead_of_passing(tmp_path):
    """The control for the control: an armed scan with nothing to look for is RED.

    Without this, a future test that turned the scan on and forgot its probe
    token would be a leak test that checked nothing and said it passed.
    """
    adapter, _root, log = a_harness(
        tmp_path, **{_fakeclaude.LEAK_CHECK: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert receipt.exit_code == _fakeclaude.PROBE_MISSING_EXIT
    assert _prompt_row(log)["marker"] is None


#: Comfortably past the operating system's pipe buffer, which is where this
#: guard begins to see anything at all. Measured on this platform: a deaf child
#: reports `delivered` up to 4 KiB and `incomplete` from 8 KiB. Well under the
#: 64 KiB ceiling either limit imposes, so the size is about the buffer and not
#: about a bound this build chose.
BEYOND_THE_PIPE_BUFFER = "Refactor the guard. " * 1600


def test_an_instruction_too_large_to_buffer_is_never_a_success_if_unread(tmp_path):
    """A deaf child exits zero honestly, about a task it was never given.

    This is the relation the runner's `stdin_state` exists for, seen from the
    provider that actually uses the channel. Every process fact about this run
    is good -- completed, exit zero -- and the run still did not happen.

    The instruction is deliberately larger than the pipe buffer, because that is
    the only region in which the near side can tell. The other region has its
    own test below, and it is not a happier one.
    """
    adapter, _root, log = a_harness(
        tmp_path, instruction=BEYOND_THE_PIPE_BUFFER, **{_fakeclaude.DEAF: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", "an undelivered instruction became a success"
    assert "never handed its whole instruction" in receipt.detail
    assert _prompt_row(log)["stdin"] == {"read": False}


def test_an_instruction_small_enough_to_buffer_defeats_the_delivery_guard(tmp_path):
    """The BOUND of the guard above, pinned rather than left to be discovered.

    A payload that fits the operating system's pipe buffer is written, flushed
    and closed successfully whether or not the child ever reads it -- the read
    happens on the far side of the kernel and leaves no trace on this one. So
    for an ordinary instruction, which is far smaller than the buffer, a child
    that ignores its input entirely still produces `succeeded`.

    That is not a defect this test tolerates; it is the honest edge of what a
    parent can know, and it is written down here so nobody reads
    `stdin_state == "delivered"` as "the child acted on it". The far side is
    closed by one thing only: a witness that returns something present ONLY in
    what was piped, which is what the opt-in real smoke requires of a real
    install and what the leak suite's probe token does here.

    If this test ever goes RED because the receipt came back `failed`, the guard
    has become stronger than it was, and that is a correction to celebrate and
    to re-word -- not a regression.
    """
    adapter, _root, log = a_harness(tmp_path, **{_fakeclaude.DEAF: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", (
        "the near-side guard grew past the pipe buffer; rewrite this claim")
    assert _prompt_row(log)["stdin"] == {"read": False}, (
        "the child DID read, so this test no longer describes a deaf run")


# --- the environment every spawn is given -------------------------------------


def test_both_documented_switches_are_set_on_the_preflight_and_on_the_task(
        tmp_path):
    """BOTH spawns, and that is the point rather than a thoroughness flourish.

    `DISABLE_AUTOUPDATER` is a version invariant: an update between the version
    preflight and the task would mean this build proved one binary and ran
    another. A test that checked only the task spawn would leave exactly that
    window open.
    """
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    rows = _fakeclaude.spawns(log)
    assert len(rows) == 2, f"EXPECTED_PREFLIGHT_AND_TASK={len(rows)}"
    # The VALUES are spelled, not read from the module. Both are DISABLE flags,
    # so `1` is what turns the behaviour off -- the opposite polarity from Grok
    # Build's four ENABLED flags, and exactly the kind of fact a test that
    # imported its own expectation would stop holding.
    expected = {
        "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    for row in rows:
        assert row["switches"] == expected, row["argv"]
    # The NAMES come from the code and are cross-checked against the spelling,
    # so a rename is a failure here rather than a silent narrowing.
    assert dict(CLAUDE_FORCED_ENV) == expected
    assert set(_fakeclaude.SWITCH_NAMES) == set(expected)


def test_every_spawn_gets_a_fresh_home_under_this_providers_own_root(tmp_path):
    """Two spawns, two homes, both beneath this provider's own subtree."""
    adapter, root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    homes = [row["claude_home"] for row in _fakeclaude.spawns(log)]
    assert len(homes) == 2 and len(set(homes)) == 2, homes
    for home in homes:
        assert Path(home).parent == (root / HOME_DIR).resolve(), home
        # The NAME carries this provider's own id kind, so a home left standing
        # under the shared root says whose it was. A neutral kind would make an
        # abandoned home unattributable, and the sweep's refusal unexplainable.
        assert Path(home).name.startswith("claude-home"), home
    # And nothing of either home is still standing.
    standing = sorted(p.name for p in (root / HOME_DIR).iterdir()) \
        if (root / HOME_DIR).is_dir() else []
    assert standing == [], f"A_HOME_OUTLIVED_ITS_SPAWN={standing}"


def test_the_environment_name_that_relocates_the_home_is_the_documented_one():
    """`CLAUDE_CONFIG_DIR`, and it is demonstrated rather than merely described.

    Anthropic's own devcontainer and both gateway Dockerfiles set it to a
    directory, which is the strongest evidence in this module. Pinned as a
    VALUE here so a rename in the adapter has to be a deliberate edit.
    """
    assert CLAUDE_HOME_ENV == "CLAUDE_CONFIG_DIR"
    assert _fakeclaude.CLAUDE_HOME_NAME == CLAUDE_HOME_ENV


# --- the version is PARSED, and only its semver counts ------------------------


#: The ONE form two Anthropic issue templates describe, directly beneath "Run
#: `claude --version` and paste the output". There is no cross-product here and
#: that is itself the finding: unlike Grok Build, nothing in this form is
#: optional, because nothing in the sources says any part of it varies.
#: SPELLED, both halves. Built from `REVIEWED_CLAUDE_VERSION` it would move
#: whenever the constant moved, and the one thing this suite most needs to catch
#: -- a reviewed version changed without a review -- would change the expectation
#: with it. The constant is cross-checked against the spelling instead.
ACCEPTED_FORM = "2.1.239 (Claude Code)"

#: Grouped by WHAT is wrong, so a failure names its category. Every row is one
#: edit away from the accepted form, so each fails for the reason it is filed
#: under and not for a second reason it happens to also have.
REFUSED_FORMS = (
    # a different version, dressed correctly
    ("version", "2.1.238 (Claude Code)"),
    ("version", "2.1.2390 (Claude Code)"),
    ("version", "2.1.239.1 (Claude Code)"),
    ("version", "02.1.239 (Claude Code)"),
    ("version", "2.1.239-rc.1 (Claude Code)"),
    # the product name, which may never become a version
    ("product", "2.1.239"),
    ("product", "2.1.239 (claude code)"),
    ("product", "2.1.239 (Claude)"),
    ("product", "2.1.239 (Claude Code CLI)"),
    ("product", "2.1.239 [Claude Code]"),
    ("product", "2.1.239 Claude Code"),
    # the order, which is the fact this module could most easily have guessed
    # wrong: Grok Build puts the program name FIRST, and this vendor does not.
    ("order", "claude 2.1.239"),
    ("order", "Claude Code 2.1.239"),
    ("order", "Claude Code (2.1.239)"),
    # anything else on the line
    ("extra", "2.1.239 (Claude Code) extra"),
    ("extra", "v2.1.239 (Claude Code)"),
    ("extra", "the 2.1.239 (Claude Code) release"),
    ("extra", ""),
    ("extra", "warning: cache is stale"),
)


def test_the_one_described_form_of_the_version_print_is_accepted(tmp_path):
    """Driven end to end through a child, because that is where it matters."""
    adapter, _root, log = a_harness(
        tmp_path, **{_fakeclaude.VERSION: ACCEPTED_FORM})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(_fakeclaude.prompt_spawns(log)) == 1
    assert ACCEPTED_FORM == f"{REVIEWED_CLAUDE_VERSION} (Claude Code)", (
        "the reviewed version moved without this suite's spelling moving with it")


@pytest.mark.parametrize(
    "category,printed", REFUSED_FORMS,
    ids=[f"{c}-{i}" for i, (c, _) in enumerate(REFUSED_FORMS)])
def test_no_other_shape_is_read_as_the_reviewed_version(
        tmp_path, category, printed):
    """Zero prompt spawns is the assertion that matters.

    A refusal that still spawned would be no refusal, so every case is checked
    against the child's own spawn log rather than against the receipt alone.
    """
    adapter, _root, log = a_harness(tmp_path, **{_fakeclaude.VERSION: printed})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", f"ACCEPTED[{category}]={printed!r}"
    assert REVIEWED_CLAUDE_VERSION in receipt.detail
    assert _fakeclaude.prompt_spawns(log) == [], (
        f"PROMPT_SPAWNED_ON[{category}]={printed!r}")


def test_a_version_print_the_build_cannot_answer_spawns_zero_prompts(tmp_path):
    adapter, _root, log = a_harness(tmp_path, **{_fakeclaude.VERSION_FAILS: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "version preflight" in receipt.detail
    assert _fakeclaude.prompt_spawns(log) == []


def test_the_reviewed_version_is_proved_before_any_prompt_is_spawned(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    rows = _fakeclaude.spawns(log)
    assert rows[0]["argv"] == ["--version"], "THE_PREFLIGHT_IS_NOT_FIRST=True"


def test_a_secret_planted_where_a_version_belongs_never_reaches_a_receipt(tmp_path):
    """The observed token is raw child output and may not be echoed anywhere."""
    secret = "sk-ant-planted-where-a-version-belongs"
    adapter, _root, _log = a_harness(tmp_path, **{_fakeclaude.VERSION: secret})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert secret not in (receipt.detail or "")
    assert secret not in repr(receipt.as_dict())


# --- the pin this adapter will accept -----------------------------------------


def test_a_pin_built_for_another_provider_is_not_this_adapters_pin(tmp_path):
    """The class alone binds nothing now that every single-binary provider shares it."""
    exe = _executable(tmp_path)
    foreign = ExecutablePin(executable=str(exe), error=GrokBuildError)

    with pytest.raises(ClaudeCodeError, match="pin of its own"):
        ClaudeCodeTransport(
            foreign, ProcessRunner(tmp_path), root=tmp_path,
            clock=lambda: NOW, ids=_Ids())


def test_this_provider_owns_its_own_home_and_marker_names():
    """Named here so a collision with another provider's subtree is a test failure."""
    assert HOME_DIR == ".claude-home" and MARKER_DIR == ".claude-marker"
    assert HOME_DIR != MARKER_DIR


# --- what a delivered payload buys, and what it does not ----------------------


def test_a_delivered_instruction_is_reported_delivered_by_the_runner(tmp_path):
    """The positive control for the delivery state, at the provider that uses it.

    Without it, a transport that always reported `incomplete` would pass every
    refusal test in this file while making Claude Code permanently unable to
    succeed -- and the failure would read as the vendor's.
    """
    adapter, _root, _log = a_harness(tmp_path)
    seen: list[ProcessOutcome] = []
    real_attempt = adapter._attempt

    def watched(*args, **kwargs):
        outcome = real_attempt(*args, **kwargs)
        seen.append(outcome)
        return outcome

    adapter._attempt = watched
    run_once(adapter, a_request())

    states = [outcome.stdin_state for outcome in seen]
    # The preflight is spawned with no payload; the task is spawned with one.
    assert states[0] == "not_provided", states
    assert states[-1] == STDIN_DELIVERED, states
    assert STDIN_INCOMPLETE not in states


# --- durable review is now a real, separately bounded control ----------------


def test_the_real_transport_carries_dispatch_and_durable_review():
    """The catalog says exactly the two controls the production class serves."""
    entry = PROVIDER_CATALOG[CLAUDE_PROVIDER_ID]

    assert entry.implementation == "real_experimental"
    assert entry.capabilities == ("observe", "dispatch", "review")
    assert entry.schema_pairs == (
        ("dispatch", "deep-arguments-v1"),
        ("review", "deep-arguments-v1"),
    )


def test_the_frozen_dalio_template_controls_are_served_by_claude():
    """The Day 3 artifact handoff closes the old materialization blocker."""
    template = load_template("dalio-v1")
    # Only TASK nodes carry a capability; a gate and a loop decide flow and
    # drive no provider. Reading every node would have raised on the first gate
    # and said nothing about what the template asks a provider to do.
    nodes = template.as_dict()["nodes"]
    bound = {node["capability"] for node in nodes if node["kind"] == "task"}

    assert bound == {"dispatch", "review"}, bound
    assert len(bound) < len(nodes), "every node drives a provider, which is new"
    missing = bound - set(PROVIDER_CATALOG[CLAUDE_PROVIDER_ID].capabilities)
    assert missing == set(), missing


#: A form the vendor really could print, at a version this build never reviewed.
#: It is the ONE case that separates "read the form and refused the version"
#: from "could not read the form at all", because both come back False.
VALID_BUT_UNREVIEWED = "9.9.9 (Claude Code)"


def test_a_valid_form_at_an_unreviewed_version_is_read_and_then_refused(tmp_path):
    """The parse and the comparison are two answers, and both are checked here.

    `_version_matches` is a boolean, and a boolean cannot say WHICH question it
    answered. `False` means either "a different build" -- correct, refuse -- or
    "this parser read nothing at all", which is a defect no refusal repairs. A
    production parser replaced with one matching NOTHING behaves identically to a
    correct one on every input except this: a valid form whose version differs.

    So this asserts the parser READ the form, that it then declined the version,
    and that no prompt was spawned. Its opposite number is the opt-in smoke,
    which asks the same of whatever a real install prints.
    """
    adapter, _root, log = a_harness(
        tmp_path, **{_fakeclaude.VERSION: VALID_BUT_UNREVIEWED})

    receipt = run_once(adapter, a_request())

    printed = (VALID_BUT_UNREVIEWED + "\n").encode("utf-8")
    assert adapter._parsed_version(printed) == "9.9.9", (
        "the parser could not read a form the vendor describes")
    assert adapter._version_matches(printed) is False
    assert receipt.outcome == "failed"
    assert REVIEWED_CLAUDE_VERSION in receipt.detail
    assert _fakeclaude.prompt_spawns(log) == []


def test_the_parser_reads_the_reviewed_form_into_the_reviewed_semver():
    """The positive control: reading and agreeing are still two separate steps."""
    unbound = ClaudeCodeTransport.__new__(ClaudeCodeTransport)

    assert ClaudeCodeTransport._parsed_version(
        unbound, b"2.1.239 (Claude Code)\n") == "2.1.239"
    assert ClaudeCodeTransport._parsed_version(unbound, b"2.1.239\n") is None
    assert ClaudeCodeTransport._parsed_version(
        unbound, b"claude 2.1.239 (Claude Code)\n") is None
