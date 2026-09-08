"""What a login VALUE may reach, and what a login that CHANGES may reach.

Split out of `test_harness_subscription_login` when that module crossed the
800-line cap. The seam is a subject, not a size: next door proves which
directory a child is pointed at and which flag it is given -- facts about this
build's own argv and environment -- while this module proves what may happen to
the SECRET that directory holds.

Three claims live here and nowhere else. A child that echoes its own login is
seen doing it, including when the vendor refreshed that login while the child
ran, which is the case a scan built before the spawn cannot see. A login this
build cannot read widens nothing and refuses nothing. And the value channel that
carries those bytes to the runner takes bytes and nothing else.

The PUBLICATION claims are driven through a REAL store and runtime, not through
the transport alone: what has to be proved is what a run's durable record ends
up holding, and a check on an intermediate flag cannot say that. The REFRESH
claim is measured at the seam instead, and its name says so: the two answers it
compares -- the scan the runner took before the spawn and the one taken after --
are not separable in a finished run, because a run that refuses for the right
reason and one that fails for another end the same way from outside.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.adapters.harness_workspace import WORK_DIR

from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, _Ids, a_request, run_once
from tests.test_harness_subscription_login import a_harness, a_login_home

REFRESHED = "sk-ant-oat01-SYNTHETIC-REFRESHED-VALUE-NOT-A-REAL-CREDENTIAL"
#: Words only the CHILD's own review output carries. The fixture's seed document
#: is an artifact in the same run, so a needle both could hold would call a
#: refusal a publication and pass either way.
CHILD_ONLY = "causal tests"


def a_review(tmp_path: Path, home: Path, **knobs: str):
    """Drive ONE real review through Confirm, on a subscription harness.

    Through the store and the runtime rather than through the transport alone:
    what has to be proved is what a run's own durable record ends up holding,
    and a check on an intermediate flag cannot say that.
    """
    from conductor.command.contracts import RunEnvelope
    from conductor.command.runtime import Budget, ControlRuntime
    from conductor.command.run_store import RunStore, snapshot_digest
    from conductor.command.artifacts import ArtifactDocument
    from conductor.command.adapters import AdapterRegistry
    from tests.test_command_claude_review import (
        ARGUMENTS, CONFIG, INPUT_REF, RUN_ID, SEED_CONTENT, _confirmation,
        _proposal)

    adapter, root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home), **knobs)
    store = RunStore(root)
    store.create_run(
        RunEnvelope(run_id=RUN_ID, cycle_id="review-cycle", created_at=NOW,
                    config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    store.append(ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=INPUT_REF, run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown", content=SEED_CONTENT))
    proposal = _proposal(ARGUMENTS)
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    attempt = runtime.execute(runtime.authorize(
        _confirmation(proposal),
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600)))
    return attempt, store, adapter, log


def documents_holding(store, needle: str) -> list:
    """Every DURABLE artifact in the run whose content carries this text.

    Read back out of the store, because that is the record a person and the next
    step both read. The seed this fixture plants is an artifact too, so the
    needle has to be something only the child could have produced.
    """
    from tests.test_command_claude_review import RUN_ID

    return [row.value for row in store.read(RUN_ID).records
            if row.kind == "artifact" and needle in str(row.value.content)]


def test_a_login_refreshed_mid_run_is_caught_by_the_scan_taken_after_the_spawn(
        tmp_path):
    """The scan the runner performs is built from the values that stood BEFORE
    the child started, because those are the only ones it can have. A vendor
    that refreshes its own credential while it runs leaves a different secret
    behind, and a child echoing the new one passed a scan built entirely from
    the old -- into an artifact the run keeps.
    """
    home = a_signed_in_home(tmp_path)
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.REFRESH_LOGIN: REFRESHED.encode("utf-8").hex()})[0]

    adapter._workspace.work_root()
    outcome = adapter._attempt(
        adapter._review_argv, WORK_DIR, timeout=30, stdin_bytes=b"probe")

    assert (home / ".credentials.json").read_text(
        encoding="utf-8").count(REFRESHED) == 1, "the fixture refreshed nothing"
    assert REFRESHED.encode("utf-8") in outcome.output, "nothing was echoed"
    # BOTH halves are the claim. The runner's own scan MISSED it -- that is the
    # gap, and a witness that did not show the miss could be passing on the old
    # value alone -- and the answer taken after the spawn catches it.
    assert outcome.output_contains_env_value is False, (
        "the fixture did not reproduce the gap this closes")
    assert adapter._login_echo is True
    assert adapter._review_attempt_carries(outcome) is True


def test_a_review_that_echoes_nothing_still_publishes(tmp_path):
    """The positive control for the two refusals above: the same road, the same
    subscription, an output that carries no login, and a document is written."""
    home = a_signed_in_home(tmp_path)
    attempt, store, _adapter, _log = a_review(
        tmp_path, home, **{_fakeclaude.EMIT_REVIEW: "enabled"})

    assert attempt.state.value == "succeeded"
    assert documents_holding(store, CHILD_ONLY) != [], "nothing was published"


def test_a_review_that_leaves_undeclared_state_publishes_nothing(tmp_path):
    """The retention rule reaches the road where output becomes durable. A
    review that left something nobody declared in a directory this build cannot
    clean has not met the promise it makes about that directory."""
    home = a_signed_in_home(tmp_path)
    attempt, store, _adapter, _log = a_review(
        tmp_path, home, **{_fakeclaude.EMIT_REVIEW: "enabled",
                           _fakeclaude.HOME_FILE: "stowaway.txt:PROBE"})

    assert (home / "stowaway.txt").exists(), "the fixture left nothing behind"
    assert attempt.state.value != "succeeded", attempt.detail
    assert documents_holding(store, CHILD_ONLY) == [], (
        "a review published over a promise this build had already broken")


# -- the login joins the leak scan it was never in --------------------------


SECRET = "sk-ant-oat01-SYNTHETIC-LOGIN-VALUE-NOT-A-REAL-CREDENTIAL"


def a_signed_in_home(tmp_path: Path) -> Path:
    """A login directory holding a credential file the vendor's login wrote."""
    home = tmp_path / "auth" / "claude-code"
    home.mkdir(parents=True)
    (home / ".credentials.json").write_text(
        '{"claudeAiOauth": {"accessToken": "' + SECRET + '", "scopes": ["a"]}}',
        encoding="utf-8", newline="\n")
    return home


def test_a_child_that_echoes_its_own_login_is_seen_doing_it(tmp_path):
    """The gap this closes: every credential the scan knew about arrived through
    an allowed environment name, and a vendor login arrives in a file.

    Measured at the flag the publication road reads. A review output becomes
    durable artifact content unless that flag is set, so a login the scan had
    never heard of would have been written into the run's own record.
    """
    home = a_signed_in_home(tmp_path)
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.EMIT_HEX: SECRET.encode("utf-8").hex()})[0]

    adapter._workspace.work_root()
    outcome = adapter._attempt(
        adapter._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=b"probe")

    assert outcome.output_contains_env_value is True


def test_the_same_output_is_unremarkable_when_no_login_was_pinned(tmp_path):
    """The positive control: the flag above is the LOGIN being scanned for, not
    this build flagging every output that looks like a token."""
    # The child is told what to emit as HEX, so the value the knob carries
    # through the allowed environment is not the value it writes: without that,
    # the control would be flagged for the ENVIRONMENT reason and would prove
    # nothing about a login at all.
    adapter = a_harness(
        tmp_path, **{_fakeclaude.EMIT_HEX: SECRET.encode("utf-8").hex()})[0]

    adapter._workspace.work_root()
    outcome = adapter._attempt(
        adapter._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=b"probe")

    assert outcome.output_contains_env_value is False


def test_a_login_value_reaches_the_scan_and_nothing_else(tmp_path):
    """Read to protect, never to report: the values are bytes for one substring
    test, and no receipt, journal row or exception carries them."""
    from conductor.command.adapters import login_home

    home = a_signed_in_home(tmp_path)
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))[0]

    assert SECRET.encode("utf-8") in adapter._login_secrets()
    assert SECRET.encode("utf-8") in adapter._sensitive_values()
    # The scopes entry is a real string in that file and far too short to scan
    # for: a two-character value would flag every output containing it.
    assert b"a" not in adapter._login_secrets()
    assert login_home.credential_values(str(home), ()) == ()


def test_only_the_declared_login_file_is_ever_read(tmp_path):
    """Read from the DECLARED names, never by looking at what a directory
    happens to hold: a build that scanned every file it found would be reading
    an operator's unrelated documents in order to protect them."""
    home = a_signed_in_home(tmp_path)
    (home / "notes-of-my-own.txt").write_text(
        '{"diary": "SOMETHING-ELSE-ENTIRELY-AND-QUITE-LONG"}',
        encoding="utf-8", newline="\n")
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))[0]

    values = adapter._login_secrets()

    assert SECRET.encode("utf-8") in values
    assert b"SOMETHING-ELSE-ENTIRELY-AND-QUITE-LONG" not in values


def test_the_value_channel_carries_bytes_and_refuses_anything_else():
    """The one field of a command spec that holds a VALUE. A string here would
    be a text credential compared against a byte stream and never matching."""
    from conductor.command.adapters.process import CommandSpec, CommandSpecError

    with pytest.raises(CommandSpecError, match="VALUES as bytes"):
        CommandSpec(argv=("/bin/true",), cwd="work",
                    sensitive_extra=("a string",))
    spec = CommandSpec(argv=("/bin/true",), cwd="work",
                       sensitive_extra=(b"kept", b"", b"kept"))
    assert spec.sensitive_extra == (b"kept",)
    assert "kept" not in repr(spec)


def test_a_login_this_build_cannot_read_widens_nothing_and_refuses_nothing(
        tmp_path):
    """A login that cannot be read is a scan that cannot be widened, not a
    reason to refuse a run the login preflight already admitted."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    (home / ".credentials.json").write_text(
        "not json at all", encoding="utf-8", newline="\n")
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    assert adapter._login_secrets() == ()
    assert run_once(adapter, a_request()).outcome == "succeeded"
    assert login_home.credential_values(
        str(home), (".credentials.json",)) == ()


def test_the_two_declared_lists_are_the_measured_ones():
    """Spelled out WHOLE as an independent claim about each pinned build.

    Both halves matter and a spot check covers neither: dropping a name from
    `login_scratch` leaves per-run state standing in an operator's directory,
    and dropping one from `login_expected` turns ordinary vendor state into a
    reported residue that fails every run.
    """
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.codex_cli import CODEX_PROFILE

    assert CLAUDE_PROFILE.login_scratch == ("sessions", ".last-cleanup")
    assert CLAUDE_PROFILE.login_expected == (
        ".claude.json", "backups", ".credentials.json")
    assert CODEX_PROFILE.login_scratch == ("tmp",)
    assert CODEX_PROFILE.login_expected == ("skills", "auth.json", "version.json")
    # `config.toml` moved from tolerated to REFUSED: it carries this vendor's
    # project trust map, and a trusted work tree re-admits the configuration an
    # empty per-attempt home had excluded.
    assert CODEX_PROFILE.login_forbidden == ("config.toml",)
    assert CLAUDE_PROFILE.login_forbidden == ("settings.json", "CLAUDE.md")


@pytest.mark.parametrize("bad", [
    "/etc", "C:\\Windows", "..", ".", "", "sessions/inner", "a\\b", 7])
def test_a_declared_login_name_is_one_component_and_never_a_path(bad):
    """These lists are joined to a directory an operator pinned and one of them
    is then DELETED, so a name carrying a separator, a parent segment or a drive
    would reach outside the directory they pointed at."""
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.harness_profile import HeadlessCliError
    from dataclasses import replace

    with pytest.raises(HeadlessCliError):
        replace(CLAUDE_PROFILE, login_scratch=(bad,))


def test_a_name_cannot_be_both_taken_back_and_left_alone():
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.harness_profile import HeadlessCliError
    from dataclasses import replace

    with pytest.raises(HeadlessCliError, match="never both"):
        replace(CLAUDE_PROFILE, login_scratch=("sessions",),
                login_expected=("sessions",))


def test_a_provider_that_can_be_asked_about_a_login_says_how_to_perform_one():
    """The refusal has to print a command, so a profile that could be asked and
    could not answer would leave a person told to sign in and not told how."""
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.harness_profile import HeadlessCliError
    from dataclasses import replace

    with pytest.raises(HeadlessCliError, match="how"):
        replace(CLAUDE_PROFILE, login_command=())


def test_a_checker_whose_preflight_left_state_verifies_nothing(tmp_path):
    """The third road, and the one that had no such rule at all.

    A verification is the strongest thing this build says about a piece of work,
    and it may not be built on a preflight that already broke the promise this
    provider makes about its login directory. The checker here is a subscription
    harness whose own status spawn leaves a name nobody declared; the answer is
    its own closed word, and the run records no evidence.
    """
    from conductor.command.runtime import AttemptState
    from tests import _fakecodex
    from tests.test_independent_checker_transport import RUN, setup

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    runtime, authorization, store, _doer, _checker, _log, clog, _root = setup(
        tmp_path, cross=True, checker_auth="subscription",
        checker_auth_home=str(home),
        **{_fakecodex.PREFLIGHT_HOME_FILE: "stowaway.txt:PROBE"})

    attempt = runtime.execute(authorization)

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert [row for row in store.read(RUN).records if row.kind == "evidence"] == []
    assert (home / "stowaway.txt").exists(), "the fixture left nothing behind"
    # The TASK, not the outcome. A refusal after the checker has already run is
    # a different rule from a refusal that stops it running, and the outcome
    # alone cannot tell them apart: this build refuses on both sides, so only
    # the absent spawn says the preflight rule is the one that fired.
    assert _fakecodex.task_spawns(clog) == [], (
        "the checker ran on top of a promise this build had already broken")


def test_both_harnesses_read_their_login_from_the_variable_they_already_owned():
    """No new environment name is invented for a login: the directory a login
    lives in is the same one the API-key road minted."""
    from conductor.command.adapters.claude_code import CLAUDE_HOME_ENV
    from conductor.command.adapters.codex_cli import CODEX_HOME_ENV

    assert CLAUDE_HOME_ENV == "CLAUDE_CONFIG_DIR"
    assert CODEX_HOME_ENV == "CODEX_HOME"
