"""Codex CLI driven for real, against a fake that is a REAL single executable.

Every claim here is a relation driven through the real provider door, the real
owned-process runner and a real child process: the fake stands in for the pinned
binary, never for the adapter.

What is held here is what is specific to Codex CLI, and two of those are new to
this roster:

- **it is told where to write, and the place is inside the home this build
  discards.** `-o <FILE>` takes a path this transport MINTS inside the attempt
  home, so the file's whole lifetime is one spawn. Four different things can
  stand at that name when the spawn ends -- a written file, an empty one, no
  file, or something that is not a plain file at all -- and they are four
  different facts about the CLI's own reporting rather than one. All four are
  driven here, and so is the thing none of them may become: evidence about the
  work;
- **its task travels by STDIN**, like Claude Code's, so both halves are held:
  the child really received the exact bytes, and the command line really carries
  none of them. The exactness is a DIGEST the child computes and this side
  recomputes, because a fake that echoed the instruction back would put the
  operator's prose legitimately into the child's own output and no leak
  assertion anywhere could then tell an echo from a leak;
- **`--skip-git-repo-check` is a containment-shaped fact, not a convenience.**
  Without it the CLI refuses any working root that is not a git repository, and
  every work subtree this build hands it is one. A dispatch that lost the flag
  would fail before the model was asked anything;
- **nothing is forced into the environment at all.** This vendor publishes its
  switches as CONFIG rather than as environment variables, so they ride in argv
  through `-c`, and the child's environment is the operator's allowlist plus the
  one minted home and nothing else.

The version is held in `tests/test_command_codex_version.py`, in its own module
from the start: Grok Build's crossed the 800-line cap when two cases were added.
The relations the shared transport owns -- the marker, the sweep, the retention
promise against a hostile child, the containment of every written route -- are
held once, in the dsh suite, against the same code.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from conductor.command.adapters.codex_cli import (
    ANSWER_ABSENT,
    ANSWER_EMPTY,
    ANSWER_UNREADABLE,
    ANSWER_WRITTEN,
    CODEX_FORCED_ENV,
    CODEX_HOME_ENV,
    CODEX_PROFILE,
    CODEX_PROTOCOL,
    CODEX_PROVIDER_ID,
    HOME_DIR,
    INSTRUCTION_DIR,
    LAST_MESSAGE_NAME,
    MARKER_DIR,
    CodexCliError,
    CodexCliTransport,
    codex_pin,
)
from conductor.command.adapters.artifact_transport import ArtifactAwareTransport
from conductor.command.adapters.grok_build import GrokBuildError
from conductor.command.adapters.headless_cli import (
    TASK_CHANNEL_STDIN,
    ExecutablePin,
)
from conductor.command.adapters.process import (
    STDIN_DELIVERED,
    STDIN_INCOMPLETE,
    ProcessOutcome,
    ProcessRunner,
)
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.contracts import ActionRequest
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers

from tests import _fakecodex, _stdinseam
from tests._fakeenv import ENV_PROBE, NO_PROBE

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
    exe = _fakecodex.build_executable(tmp_path / "bin")
    if exe is None:
        pytest.skip(
            "no console-script launcher stub is available to copy in this "
            "environment, so no shell-free single-file executable can be built")
    return exe


def a_harness(tmp_path: Path, *, instruction: str = INSTRUCTION_BODY,
              ambient=None, auth: str = "api_key", auth_home: str = "",
              root: Path | None = None, **knobs: str):
    """A registered, available Codex provider over the fake, its root and its log.

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
    environ = {_fakecodex.SPAWN_LOG: str(log), **knobs}
    config = ProviderConfig(
        provider_id=CODEX_PROVIDER_ID, executable=str(exe),
        protocol=CODEX_PROTOCOL, env_allow=tuple(sorted(environ)),
        auth=auth, auth_home=auth_home)
    # `ambient` is a monkeypatch fixture. When it is given, the knobs are planted
    # in the REAL process environment and the runner is left to read that, so the
    # allowlist is exercised against an environment that can actually carry a
    # leak. Passing a synthetic dict -- what every other caller does, and what
    # every caller used to do -- means `ProcessRunner._environ` holds only the
    # knobs, so no parent value could reach a child however the filter behaved:
    # a mutation copying the ambient environment stayed GREEN under it.
    if ambient is not None:
        for _name, _value in environ.items():
            ambient.setenv(_name, _value)
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(),
        environ=None if ambient is not None else environ)
    return resolution.registry.resolve(CODEX_PROVIDER_ID), root, log


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


def _task_row(log: Path) -> dict:
    """The one task spawn, refusing to guess when there is not exactly one."""
    rows = _fakecodex.task_spawns(log)
    assert len(rows) == 1, f"EXPECTED_ONE_TASK_SPAWN={len(rows)}"
    return rows[0]


# --- the task travels by stdin, and only by stdin -----------------------------


def test_the_child_receives_the_whole_task_on_stdin_and_the_bytes_are_exact(
        tmp_path):
    """A digest computed on the far side and recomputed here.

    A truncated instruction is not a failed dispatch, it is a DIFFERENT one, and
    nothing downstream would say so. The frame this build composes stands ahead
    of the operator's instruction, so both are checked -- the instruction by its
    presence, the whole by its digest.
    """
    adapter, _root, log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    row = _task_row(log)
    assert row["stdin"]["read"] is True
    assert row["stdin"]["bytes"] > len(INSTRUCTION_BODY)
    # The exact bytes, rebuilt from the same two parts the transport composes.
    task = adapter._task_text(
        adapter._dispatch_args(a_request().arguments), INSTRUCTION_BODY)
    assert row["stdin"]["sha256"] == hashlib.sha256(
        task.encode("utf-8")).hexdigest(), "THE_CHILD_READ_DIFFERENT_BYTES"
    assert row["stdin"]["bytes"] == len(task.encode("utf-8"))


def test_the_whole_argv_is_the_pinned_binary_this_builds_flags_and_one_minted_path(
        tmp_path):
    """Every token is code-owned, and the only one that varies is a minted path.

    Spelled rather than read from the module: importing the constants here would
    put the same values on both sides of the comparison, so any edit would move
    both and this would keep passing -- which is what a mutation proved of the
    Claude suite before its tokens were spelled.
    """
    adapter, root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    argv = _task_row(log)["argv"]
    assert argv[:-2] == [
        "exec", "--skip-git-repo-check", "--ephemeral",
        "--color", "never", "--sandbox", "workspace-write",
        "-c", "analytics.enabled=false",
        "-c", 'otel.exporter="none"',
        "-c", 'otel.metrics_exporter="none"',
        "-c", 'otel.trace_exporter="none"',
        "-c", "otel.log_user_prompt=false",
        "-o"], argv
    assert argv[-1] == "-", "the stdin sentinel must stand last"
    # The one varying token is a path this build minted inside its OWN attempt
    # home, which is the only place a file this build discards may stand.
    written = Path(argv[-2])
    assert written.name == LAST_MESSAGE_NAME == "last-message.txt"
    assert written.parent.parent == (root / HOME_DIR).resolve(), written
    assert written.parent.name.startswith("codex-home"), written
    assert written.is_absolute(), "a relative -o would resolve against the work tree"


def test_the_subcommand_stands_first_and_the_repo_check_is_skipped(tmp_path):
    """Two tokens whose ORDER and PRESENCE are the whole of their meaning.

    `exec` first because every flag after it belongs to that subcommand and the
    bare CLI would refuse them; `--skip-git-repo-check` present because the CLI
    refuses outright when the working root is not a git repository, and no work
    subtree this build hands it ever is.
    """
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    argv = _task_row(log)["argv"]
    assert argv[0] == "exec", "the subcommand must stand first"
    assert "--skip-git-repo-check" in argv, (
        "without this the CLI refuses every work subtree this build creates")
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv


def test_no_byte_of_the_operators_instruction_reaches_argv_or_the_environment(
        tmp_path):
    """Asked of the CHILD, with a probe token that arrives only by stdin.

    The child extracts the token from the task it read and then scans its own
    argv, its own cwd and EVERY value of its own environment. No channel is
    exempted, and the token never travelled by any of them, so a hit would be a
    real leak rather than an artefact of how the test delivered it.
    """
    probe = _fakecodex.PROBE_PREFIX + "ab12cd34" * 8
    adapter, _root, log = a_harness(
        tmp_path, instruction=f"{INSTRUCTION_BODY} {probe}",
        **{_fakecodex.LEAK_CHECK: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert _task_row(log)["marker"] == {
        "in_stdin": True, "in_argv": False, "in_cwd": False, "in_env": False}


def test_the_leak_witness_really_looks_where_it_says_it_looks(tmp_path):
    """The positive control for the scan itself: planted, the probe is FOUND.

    Every leak assertion in this file and in the surfaces suite reads booleans a
    CHILD computed, so a witness that answered False without looking would make
    all of them pass while a real leak went by -- and nothing else would notice,
    because a clean answer is what a correct run gives too.

    Two of the three channels can be planted, and both are: the probe is put in
    an environment VALUE and in the work item id that names the child's working
    directory. The third cannot be planted at all, and that is the whole point of
    the channel -- there is no road from an instruction to this argv.
    """
    probe = _fakecodex.PROBE_PREFIX + "cafe0123" * 8
    adapter, _root, log = a_harness(
        tmp_path, instruction=f"{INSTRUCTION_BODY} {probe}",
        **{_fakecodex.LEAK_CHECK: "1", "CODEX_PROBE_ECHO": probe})

    receipt = run_once(adapter, a_request(work_item_id=probe))

    assert receipt.outcome == "succeeded", receipt.detail
    assert _task_row(log)["marker"] == {
        "in_stdin": True, "in_argv": False, "in_cwd": True, "in_env": True}


def test_a_task_the_leak_witness_cannot_scan_fails_instead_of_passing(tmp_path):
    """The control for the control: an armed scan with nothing to look for is RED.

    Without this, a future test that turned the scan on and forgot its probe
    token would be a leak test that checked nothing and said it passed.
    """
    adapter, _root, log = a_harness(tmp_path, **{_fakecodex.LEAK_CHECK: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert receipt.exit_code == _fakecodex.PROBE_MISSING_EXIT
    assert _task_row(log)["marker"] is None


#: A prefix small enough that what stopped the write can only be the double.
#: POSIX GUARANTEES a pipe of at least 512 bytes, so no system can refuse this
#: many; the observed defaults -- 4 KiB on Windows, 16 KiB on macOS, 64 KiB on
#: Linux -- are only how much room that leaves over.
A_PREFIX = 16


def test_an_instruction_the_child_was_never_handed_whole_is_not_a_success(
        tmp_path, monkeypatch):
    """A deaf child exits zero honestly, about a task it was never given.

    Every process fact about this run is good -- completed, exit zero -- and the
    run still did not happen.

    The delivery is broken HERE, at the step that fails, rather than by asking
    the operating system to break it. The older shape handed a deaf child more
    bytes than a pipe can hold, which is a region that does not exist on Linux:
    a pipe there takes 64 KiB whole, and 64 KiB is the ceiling this build bounds
    an instruction body at, so the write, the flush and the close all succeeded
    and the guard was right to say `delivered`. See `tests/_stdinseam.py`.
    """
    adapter, _root, log = a_harness(tmp_path, **{_fakecodex.DEAF: "1"})
    _stdinseam.every_child_input(
        monkeypatch,
        lambda real: _stdinseam.ChildInput(carrier=real, ceiling=A_PREFIX))

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", "an undelivered instruction became a success"
    assert "never handed its whole instruction" in receipt.detail
    assert _task_row(log)["stdin"] == {"read": False}


def test_a_delivered_instruction_is_reported_delivered_by_the_runner(tmp_path):
    """The positive control for the delivery state, at a provider that uses it.

    Without it, a transport that always reported `incomplete` would pass every
    refusal test in this file while making Codex CLI permanently unable to
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


# --- the file this build tells the CLI to write -------------------------------


def test_the_final_message_file_never_outlives_the_spawn_that_wrote_it(tmp_path):
    """It stands inside the attempt home, so the retention promise carries it.

    That placement is the point rather than a detail. In the work tree the file
    would land in the very evidence snapshot verification reads, and "the task
    changed nothing" would stop being observable; in the marker namespace, which
    nothing sweeps, it would be exactly the retained model text the home exists
    to prevent.
    """
    adapter, root, log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    written = Path(_task_row(log)["last_message"])
    assert written.parent.parent == (root / HOME_DIR).resolve()
    assert not written.exists(), "THE_FINAL_MESSAGE_FILE_SURVIVED_ITS_SPAWN"
    standing = sorted(p.name for p in (root / HOME_DIR).iterdir()) \
        if (root / HOME_DIR).is_dir() else []
    assert standing == [], f"A_HOME_OUTLIVED_ITS_SPAWN={standing}"


#: Each knob, the word the adapter must read out of what it leaves behind, and a
#: phrase from the sentence a receipt then carries. The phrases are SPELLED, so a
#: reworded promise is a failure here rather than a silent change of what a
#: receipt tells an operator.
FINAL_MESSAGE_CASES = (
    ("written", {}, ANSWER_WRITTEN, "wrote a final message into the file"),
    ("empty", {_fakecodex.EMPTY_LAST_MESSAGE: "1"}, ANSWER_EMPTY,
     "wrote an EMPTY final message file"),
    ("absent", {_fakecodex.NO_LAST_MESSAGE: "1"}, ANSWER_ABSENT,
     "wrote no final message file at all"),
    ("unreadable", {_fakecodex.LAST_MESSAGE_DIRECTORY: "1"}, ANSWER_UNREADABLE,
     "is not a plain file this build can read as one"),
)


@pytest.mark.parametrize(
    "label,knobs,expected,phrase", FINAL_MESSAGE_CASES,
    ids=[row[0] for row in FINAL_MESSAGE_CASES])
def test_what_stood_at_the_final_message_name_is_read_and_said_exactly(
        tmp_path, label, knobs, expected, phrase):
    """Four different facts about the CLI's own reporting, kept four.

    Flattening any two of them would overstate the weaker one. The vendor writes
    this file EMPTY when a run produced no final agent message, so `empty` is a
    run that finished and said nothing while `absent` is one that never reached
    the point of reporting -- and neither is a fact about the work.

    Read while the home still stands, which is the only moment it can be read at
    all: the home is discarded the instant the attempt returns.
    """
    adapter, _root, _log = a_harness(tmp_path, **knobs)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert adapter._answer == expected, f"READ_AS[{label}]={adapter._answer}"
    assert phrase in receipt.detail, receipt.detail
    # Whatever the CLI reported, the receipt still says a zero is a zero.
    assert "publishes no exit-code contract" in receipt.detail


def test_the_receipt_carries_neither_the_files_contents_nor_its_path(tmp_path):
    """The clause is chosen by a closed word, so nothing can ride out on it.

    The transport never opens the file -- it reads a kind and a size -- so this
    is a property of the code rather than a filter over it. Driven anyway,
    because the path is the other thing that must not escape and it is a real
    route on this machine.
    """
    secret = "sk-planted-inside-the-final-message-file"
    adapter, _root, log = a_harness(
        tmp_path, **{_fakecodex.LAST_MESSAGE: secret})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    written = _task_row(log)["last_message"]
    assert secret not in repr(receipt.as_dict())
    assert written not in repr(receipt.as_dict()), "THE_MINTED_PATH_ESCAPED"
    assert HOME_DIR not in repr(receipt.as_dict())


def test_a_second_dispatch_reports_its_own_file_and_never_the_previous_one(
        tmp_path):
    """The answer is re-established per attempt, so no receipt quotes a stale one.

    A reading kept on the adapter is a reading that can go stale, and the place
    that shows is the SAME adapter reading a second home. The first dispatch
    really wrote a file; the second reading is of a home that has none, and it
    must say so rather than repeating what it last saw.
    """
    adapter, _root, _log = a_harness(tmp_path)

    first = run_once(adapter, a_request(action_id="act-1"))
    assert adapter._answer == ANSWER_WRITTEN, first.detail

    empty_home = adapter._workspace.mint_home("codex-home-probe")
    try:
        adapter._read_attempt_home(empty_home)
    finally:
        adapter._workspace.discard_home(empty_home)

    assert adapter._answer == ANSWER_ABSENT, "A_STALE_ANSWER_SURVIVED_AN_ATTEMPT"


def test_a_reading_the_door_refuses_is_unreadable_and_never_absent(tmp_path):
    """A refusal and an absence are opposite findings and share no word.

    The door refuses a home that is not beneath this workspace's own fixed root,
    and its message carries the path -- so the refusal is caught and turned into
    this module's word for "I could not establish this". Reading it as `absent`
    would be reporting that the CLI wrote nothing, on a question that was never
    answered at all.
    """
    adapter, _root, _log = a_harness(tmp_path)

    adapter._read_attempt_home(tmp_path / "not-a-home-of-this-workspace")

    assert adapter._answer == ANSWER_UNREADABLE


# --- the environment every spawn is given -------------------------------------


def test_this_provider_forces_no_environment_and_nothing_of_the_parents_arrives(
        tmp_path, monkeypatch):
    """An EMPTY `forced_env`, and a child that got nothing of the parent's.

    This vendor publishes its switches as config keys rather than as environment
    variables, so they ride in argv through `-c` and there is nothing left to
    force. That is asked of the CHILD rather than of the profile, because an
    empty tuple says only what this build sent, not what arrived.

    What is NOT claimed, and what the name used to claim: that the child sees
    only the pin. It does not, and no build can make it -- the Python runtime
    adds `LC_CTYPE` on POSIX and macOS adds `__CF_USER_TEXT_ENCODING`, both on
    the far side of the interpreter. An equality here measured interpreter
    startup, and it is what took this test red on Linux and macOS in remote run
    #10. The two provable halves are below, and they are asserted separately.
    """
    monkeypatch.setenv("OPENAI_API_KEY", ENV_PROBE)
    monkeypatch.setenv(ENV_PROBE, "a parent value that may not travel")
    adapter, _root, log = a_harness(tmp_path, ambient=monkeypatch)

    run_once(adapter, a_request())

    assert CODEX_FORCED_ENV == ()
    allowed = {_fakecodex.SPAWN_LOG, CODEX_HOME_ENV}
    rows = _fakecodex.spawns(log)
    assert len(rows) == 2, f"EXPECTED_PREFLIGHT_AND_TASK={len(rows)}"
    for row in rows:
        # Both halves, and neither of them "nothing surplus": the Python runtime
        # adds `LC_CTYPE` on POSIX and macOS adds `__CF_USER_TEXT_ENCODING`, on
        # the far side of the interpreter and never through `ProcessRunner`, so
        # a surplus check measured the interpreter's own startup rather than
        # this build. The half that IS about this build is that nothing of the
        # PARENT's arrived, asked of every name and every value.
        assert row["probe"] == NO_PROBE, (
            "THE_PARENTS_ENVIRONMENT_REACHED_THE_CHILD")
        names = set(row["env_names"])
        assert allowed <= names, f"THE_CHILD_WAS_MISSING={sorted(allowed - names)}"


def test_every_spawn_gets_a_fresh_home_under_this_providers_own_root(tmp_path):
    """Two spawns, two homes, both beneath this provider's own subtree."""
    adapter, root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    homes = [row["codex_home"] for row in _fakecodex.spawns(log)]
    assert len(homes) == 2 and len(set(homes)) == 2, homes
    for home in homes:
        assert Path(home).parent == (root / HOME_DIR).resolve(), home
        # The NAME carries this provider's own id kind, so a home left standing
        # under the shared root says whose it was.
        assert Path(home).name.startswith("codex-home"), home
    standing = sorted(p.name for p in (root / HOME_DIR).iterdir()) \
        if (root / HOME_DIR).is_dir() else []
    assert standing == [], f"A_HOME_OUTLIVED_ITS_SPAWN={standing}"


def test_the_environment_name_that_relocates_the_home_is_the_documented_one():
    """`CODEX_HOME`, and this vendor requires the directory to EXIST.

    The source reads the variable, drops an empty value, and then errors when the
    path is not an existing directory -- so a minted home is load-bearing here
    rather than merely tidy. Pinned as a VALUE so a rename in the adapter has to
    be a deliberate edit.
    """
    assert CODEX_HOME_ENV == "CODEX_HOME"
    assert _fakecodex.CODEX_HOME_NAME == CODEX_HOME_ENV


def test_the_minted_home_really_exists_when_the_child_is_started(tmp_path):
    """Not a courtesy: this vendor refuses a `CODEX_HOME` that is not there.

    The source reads the variable and then errors when the path is not an
    existing directory, so a home that was merely NAMED would fail every real
    dispatch. Only the child can answer whether it was one, because the parent
    creates it before the spawn and destroys it after -- so the answer is the
    child's own boolean, recorded on both spawns.
    """
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    rows = _fakecodex.spawns(log)
    assert len(rows) == 2, f"EXPECTED_PREFLIGHT_AND_TASK={len(rows)}"
    assert [row["codex_home_is_dir"] for row in rows] == [True, True], (
        "A_SPAWN_RAN_WITHOUT_AN_EXISTING_HOME")


# --- the pin this adapter will accept -----------------------------------------


def test_a_pin_built_for_another_provider_is_not_this_adapters_pin(tmp_path):
    """The class alone binds nothing now that every single-binary provider shares it."""
    exe = _executable(tmp_path)
    foreign = ExecutablePin(executable=str(exe), error=GrokBuildError)

    with pytest.raises(CodexCliError, match="pin of its own"):
        CodexCliTransport(
            foreign, ProcessRunner(tmp_path), root=tmp_path,
            clock=lambda: NOW, ids=_Ids())


def test_this_providers_own_pin_is_accepted_and_carries_its_own_refusal_type(
        tmp_path):
    """The positive control, so the refusal above is about the pin and not the type."""
    exe = _executable(tmp_path)
    pin = codex_pin(str(exe), env_allow=("OPENAI_API_KEY",))

    assert pin.error is CodexCliError
    assert pin.env_allow == ("OPENAI_API_KEY",)
    assert CodexCliTransport(
        pin, ProcessRunner(tmp_path), root=tmp_path, clock=lambda: NOW,
        ids=_Ids()) is not None


def test_this_provider_owns_its_own_home_and_marker_names():
    """Named here so a collision with another provider's subtree is a test failure."""
    assert HOME_DIR == ".codex-home" and MARKER_DIR == ".codex-marker"
    assert HOME_DIR != MARKER_DIR


# --- what this transport does NOT claim, and what that costs -----------------


def test_the_real_transport_carries_both_controls_and_owes_a_read_only_argv():
    """`review` is DECLARED now, and what the declaration costs is spelled here.

    It was absent while this build had no resolver that turned an artifact
    reference into content. That reason is spent -- `artifact_handoff` is the
    resolver -- so the honest answer changed with the fact rather than with the
    schedule. What did NOT change is which seam is claimed: `codex exec review`
    reviews a GIT DIFF and this provider never sends it; see
    `test_command_codex_review`, which spells the whole argv.

    Declaring `review` is a promise the shared transport holds this class to at
    construction: a review-capable provider must take its task on stdin and must
    own a read-only argv of its own. Both are asserted, so a future edit that
    dropped `_review_argv` back to the base would fail here and not only where a
    review runs.
    """
    entry = PROVIDER_CATALOG[CODEX_PROVIDER_ID]

    assert entry.implementation == "real_experimental"
    assert entry.capabilities == ("observe", "dispatch", "review")
    assert entry.schema_pairs == (
        ("dispatch", "deep-arguments-v1"), ("review", "deep-arguments-v1"))
    assert CodexCliTransport.review_enabled is True
    assert CODEX_PROFILE.task_channel == TASK_CHANNEL_STDIN
    assert CodexCliTransport._review_argv is not \
        ArtifactAwareTransport._review_argv


def test_no_catalogued_provider_is_a_fixture_any_more(tmp_path):
    """The roster is real, all five of it, and two of the five can review.

    Codex was the last `fixture_only` row. Nothing in the catalog speaks a fake
    protocol any more, so a test that wants one builds its own catalog.

    The reviewers are named as a LIST rather than counted, because which
    products carry the control is a roster fact a reader should be able to check
    against the catalog by eye -- and because the day a third one lands, this is
    the line that says so.
    """
    implementations = {
        entry.implementation for entry in PROVIDER_CATALOG.values()}

    assert implementations == {"real_experimental"}, implementations
    reviewers = [
        provider_id for provider_id, entry in PROVIDER_CATALOG.items()
        if "review" in entry.capabilities]
    assert reviewers == ["claude-code", "codex"]
