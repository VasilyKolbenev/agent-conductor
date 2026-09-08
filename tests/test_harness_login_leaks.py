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

from conductor.command import verify_holds
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


def test_the_token_a_doer_wrote_before_a_refresh_never_reaches_the_checker(
        tmp_path):
    """The scan that guards the checker's material was built from the credential
    file as it stands AT PUBLICATION, which is the wrong secret.

    A doer that writes its login into a work-tree file and then refreshes that
    login leaves the OLD value in the file and the NEW one on disk. The material
    handed to the independent checker carries the old one, and a scan that read
    the file again was looking for the new one -- so the old token travelled in
    the checker's own stdin and the run succeeded.

    Measured on what is HANDED ONWARD, not on a flag: the published sensitive
    set is what the frame is scanned against, and the frame is what the checker
    reads.
    """
    home = a_signed_in_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.WRITE_FILE: f"result.txt:{SECRET}",
           _fakeclaude.REFRESH_LOGIN: REFRESHED.encode("utf-8").hex()})

    request = a_request()
    receipt = run_once(adapter, request)
    published = adapter.publish(request, receipt)

    assert (home / ".credentials.json").read_text(
        encoding="utf-8").count(REFRESHED) == 1, "the fixture refreshed nothing"
    values = set(published.sensitive)
    assert REFRESHED.encode("utf-8") in values, "the login standing now is unscanned"
    assert SECRET.encode("utf-8") in values, (
        "the login that stood while the doer wrote is not scanned for")
    adapter.release(request)
    assert adapter._login_history == {}, (
        "an attempt's login values outlived the attempt")


def test_both_sides_of_one_spawn_are_remembered(tmp_path):
    """Measured at the seam, because a preflight hides the answer end to end.

    A version probe runs before every task, and the value standing at ITS end is
    the value standing at the task's beginning -- so a build that only looked
    after each spawn would still hold both, by accident, for as long as a
    preflight precedes a task. This drives ONE spawn and asks what it saw.
    """
    home = a_signed_in_home(tmp_path)
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.REFRESH_LOGIN: REFRESHED.encode("utf-8").hex()})[0]

    adapter._workspace.work_root()
    adapter._login_seen = ()
    adapter._attempt(
        adapter._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=b"probe")

    assert set(adapter._login_seen) == {
        SECRET.encode("utf-8"), REFRESHED.encode("utf-8")}


def test_the_checker_is_never_spawned_on_material_carrying_that_token(tmp_path):
    """The frame the independent checker reads is what has to be clean, and the
    published set is only the means. Driven through the real verification road:
    the doer writes its login into the work tree and refreshes it, and the
    checker's own spawn never happens."""
    from conductor.command.runtime import AttemptState
    from tests import _fakeclaude as fake
    from tests.test_independent_checker_transport import RUN, setup

    home = a_signed_in_home(tmp_path)
    runtime, authorization, store, _doer, _checker, log, clog, _root = setup(
        tmp_path, doer_auth="subscription", doer_auth_home=str(home),
        doer_extra={fake.REFRESH_LOGIN: REFRESHED.encode("utf-8").hex()},
        secret=SECRET, secret_place="file")

    attempt = runtime.execute(authorization)

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert len(_fakeclaude.prompt_spawns(clog)) == 1, (
        "the checker was spawned on material carrying a login")
    assert [row for row in store.read(RUN).records if row.kind == "evidence"] == []


def test_a_verification_still_refuses_a_home_the_doer_could_not_discard(
        tmp_path, monkeypatch):
    """A verification may not be built on a retention promise already broken.

    The check itself no longer reads a count the doer left behind -- that
    reading was somebody else's on a cross-provider run and unreachable on a
    same-instance one. The refusal stands at PUBLICATION instead, from the fact
    the attempt recorded in its own turn, so this asks the OUTCOME and not the
    mechanism: nothing is verified and no checker runs.

    Driven through the real verification road with a discard that really fails.
    """
    from conductor.command.adapters import harness_workspace
    from conductor.command.runtime import AttemptState
    from tests.test_independent_checker_transport import RUN, setup

    runtime, authorization, store, _doer, _checker, log, _clog, _root = setup(
        tmp_path)
    real = harness_workspace.HarnessWorkspace.discard_home
    seen: list[int] = []

    def refuse(self, home):
        real(self, home)
        seen.append(1)
        # The TASK's own home, not the version probe's: a probe that could not
        # discard stops the dispatch before any task, which is a different rule.
        if len(seen) == 2:
            raise OSError("this machine would not take the home back")

    monkeypatch.setattr(
        harness_workspace.HarnessWorkspace, "discard_home", refuse)
    attempt = runtime.execute(authorization)

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert [row for row in store.read(RUN).records if row.kind == "evidence"] == []
    assert len(_fakeclaude.prompt_spawns(log)) == 1, (
        "a checker ran on top of a home the doer could not discard")


def test_a_doer_that_could_not_discard_publishes_nothing_to_any_checker(tmp_path):
    """A cross-provider check runs on a DIFFERENT instance, which can see no
    count the doer's transport holds. So the refusal stands where the fact is:
    a doer that could not take its own home back has nothing to hand a checker,
    whoever the checker is.
    """
    from conductor.command.adapters import harness_workspace
    from conductor.command.runtime import AttemptState
    from tests import _fakecodex
    from tests.test_independent_checker_transport import RUN, setup

    runtime, authorization, store, _doer, _checker, _log, clog, _root = setup(
        tmp_path, cross=True)
    real = harness_workspace.HarnessWorkspace.discard_home
    seen: list[int] = []

    def refuse(self, home):
        real(self, home)
        seen.append(1)
        if len(seen) == 2:
            raise OSError("this machine would not take the home back")

    original = harness_workspace.HarnessWorkspace.discard_home
    harness_workspace.HarnessWorkspace.discard_home = refuse
    try:
        attempt = runtime.execute(authorization)
    finally:
        harness_workspace.HarnessWorkspace.discard_home = original

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert _fakecodex.task_spawns(clog) == [], (
        "a checker on another provider ran on work the doer could not account for")
    assert [row for row in store.read(RUN).records if row.kind == "evidence"] == []
    # The record has to name WHICH promise broke. A refusal key the publication
    # may return but the verify road has no sentence for raises on the way out
    # and lands on the sentence a BROKEN VERIFIER produces -- the run then says
    # the checker failed, about a checker that was right not to run.
    assert attempt.receipt.detail == verify_holds.DOER_HOME_RETAINED, (
        attempt.receipt.detail)


def test_a_review_that_could_not_discard_publishes_nothing_either(tmp_path):
    """The same promise, the other capability.

    The review road builds its own attempt record, and this fact carried a
    DEFAULT once: the road did not fill it, so a review published as though it
    had taken its home back and a checker really read the material. A default is
    the safe-looking answer to a question a road forgot to ask, which is why the
    field has none now -- but the guard is a fact about PUBLICATION, so it is
    asked here on the road that forgot.
    """
    from conductor.command.adapters import harness_workspace
    from conductor.command.runtime import AttemptState
    from tests.test_independent_checker_transport import RUN, setup

    runtime, authorization, store, _doer, _checker, log, _clog, _root = setup(
        tmp_path, review=True)
    # The guard stands BEFORE the review branch, and that branch writes the
    # review's own text into the run's record. Position is the whole protection
    # here: the same refusal one call later would leave the material published
    # and refuse afterwards.
    seeded = sum(1 for row in store.read(RUN).records if row.kind == "artifact")
    real = harness_workspace.HarnessWorkspace.discard_home
    seen: list[int] = []

    def refuse(self, home):
        real(self, home)
        seen.append(1)
        if len(seen) == 2:
            raise OSError("this machine would not take the home back")

    original = harness_workspace.HarnessWorkspace.discard_home
    harness_workspace.HarnessWorkspace.discard_home = refuse
    try:
        attempt = runtime.execute(authorization)
    finally:
        harness_workspace.HarnessWorkspace.discard_home = original

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert attempt.receipt.detail == verify_holds.DOER_HOME_RETAINED, (
        attempt.receipt.detail)
    assert len(_fakeclaude.prompt_spawns(log)) == 1, (
        "a checker read a review whose home the doer could not take back")
    assert [row for row in store.read(RUN).records if row.kind == "evidence"] == []
    assert sum(1 for row in store.read(RUN).records
               if row.kind == "artifact") == seeded, (
        "the review's own text reached the record of a run that refused it")


def test_a_checker_does_not_refuse_a_verification_for_a_count_it_did_not_take(
        tmp_path):
    """A check reads its OWN view of the home root, and nothing it inherited.

    An earlier version read the count standing on the transport on the way in.
    On one instance that answered the question before it was asked -- an adapter
    that only verifies would refuse every later verification because of a single
    earlier failure of its own -- and across two instances the count it read
    belonged to somebody else entirely. Here the checker carries a count from
    its own earlier road, and the verification it is asked for is unrelated.
    """
    from conductor.command.runtime import AttemptState
    from tests.test_independent_checker_transport import RUN, setup

    runtime, authorization, store, _doer, checker, _log, _clog, _root = setup(
        tmp_path, cross=True)
    checker._retained = 1

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert [row for row in store.read(RUN).records if row.kind == "evidence"]


def test_a_dispatch_re_derives_the_retention_count_it_inherited(tmp_path):
    """No road inherits one now. A dispatch that kept a count from whatever ran
    before it would report another action's broken promise as its own."""
    from tests.test_command_claude_transport import a_harness as plain

    adapter = plain(tmp_path)[0]
    adapter._retained = 1

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert "could not be discarded" not in receipt.detail
    assert adapter._retained == 0


def test_a_finished_attempt_leaves_no_login_values_on_the_transport(tmp_path):
    """Two places let go, and both are needed: the road stops holding what it
    handed over, and the attempt's own entry goes when the attempt is judged --
    on the BASE road, so the promise is not a property of who inherits."""
    home = a_signed_in_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    request = a_request()
    receipt = run_once(adapter, request)

    assert adapter._login_seen == (), "the road kept its own copy"
    assert adapter._login_history, "the attempt was handed nothing to keep"
    adapter.verify(request, receipt)
    assert adapter._login_history == {}, (
        "credential bytes outlived the attempt that saw them")


def test_the_base_road_is_where_the_release_lives(tmp_path):
    """Asked of a transport that inherits NOTHING but the base.

    Every catalogued provider subclasses the artifact-aware transport, whose own
    forget also drops this -- so an end-to-end run on one of them cannot tell a
    base that kept its promise from one that inherited somebody else's. This
    drives the bare transport the ownership suite already keeps for exactly that
    question, through its real verify road.
    """
    from conductor.command.adapters.headless_values import attempt_relation
    from tests.test_command_attempt_ownership import (
        _bare, _stand_an_attempt, a_receipt, a_request as bare_request)

    transport = _bare(tmp_path)
    request = bare_request("run-a", capability="dispatch")
    _stand_an_attempt(transport, request)
    transport._login_history[attempt_relation(request)] = (
        b"SYNTHETIC-NOT-A-CREDENTIAL",)

    transport.verify(request, a_receipt(request))

    assert transport._login_history == {}, (
        "the base road kept credential bytes an attempt was finished with")


def test_the_retention_fact_a_publication_reads_belongs_to_its_own_attempt(
        tmp_path):
    """One adapter serves every action of its provider, so a count standing on
    the transport is not this attempt's to read.

    Both halves of the race are driven: a sibling beginning its own road must
    not erase what this attempt recorded, and a sibling's own failure must not
    refuse this attempt's publication.
    """
    from conductor.command.adapters.headless_values import attempt_relation

    adapter, _root, _log = a_harness(tmp_path)
    request = a_request()

    receipt = run_once(adapter, request)
    snapshot = adapter._attempts[attempt_relation(request)]
    assert snapshot.retained is False

    adapter._begin_road()          # a sibling action starts its road
    adapter._retained = 1          # and fails to discard its own home
    published = adapter.publish(request, receipt)

    assert published.refusal != "home_retained", (
        "a sibling's failure refused this attempt's publication")


def test_a_second_handoff_keeps_what_the_first_one_saw(tmp_path):
    """A road that hands off and spawns again for the same attempt must not
    drop what the earlier spawn sampled -- that is the pre-refresh value this
    whole mechanism exists to keep."""
    adapter = a_harness(tmp_path)[0]
    relation = ("run-1", "act-1", "att-1", "inst-1")

    adapter._login_seen = (b"FIRST-SYNTHETIC",)
    adapter._keep_login_values(relation)
    adapter._login_seen = (b"SECOND-SYNTHETIC",)
    adapter._keep_login_values(relation)

    assert adapter._login_history[relation] == (
        b"FIRST-SYNTHETIC", b"SECOND-SYNTHETIC")


def test_a_refusal_built_before_the_turn_neither_says_nor_erases(tmp_path):
    """It is built before this road has minted anything, so the counts standing
    on the transport are a sibling's or the last road's.

    Two claims, and the second is the one a previous version got wrong: the
    refusal must not REPORT them as this action's, and it must not CLEAR them
    either -- clearing before the turn erases a sibling's real refusal and the
    credential values it had sampled.
    """
    adapter = a_harness(tmp_path)[0]
    adapter._login_residue = 1
    adapter._login_seen = (b"A-SIBLINGS-SYNTHETIC-VALUE",)

    # A model the vendor publishes as an alias for whatever it ships this week,
    # refused before anything is minted, claimed or spawned.
    receipt = adapter._unroutable(a_request(), "sonnet")

    assert receipt is not None and receipt.outcome == "failed"
    assert "login directory" not in receipt.detail, receipt.detail
    assert adapter._login_residue == 1, "a sibling's refusal was erased"
    assert adapter._login_seen == (b"A-SIBLINGS-SYNTHETIC-VALUE",), (
        "a sibling's sampled credential values were erased")

    # And the other refusal of the same seam: a provider that cannot be told a
    # model at all. Two branches, and a reset written into one of them is a
    # reset the other does not have.
    from dataclasses import replace

    from conductor.command.adapters.claude_code import CLAUDE_PROFILE

    adapter.profile = replace(
        CLAUDE_PROFILE, model_flag="", unstable_models=())
    flagless = adapter._unroutable(a_request(), "any-model-at-all")

    assert flagless is not None and flagless.outcome == "failed"
    assert "login directory" not in flagless.detail, flagless.detail
    assert adapter._login_residue == 1


def test_one_attempt_never_borrows_another_attempts_login_values(tmp_path):
    """Per attempt, by its own relation. A road that inherited the last one
    would be scanning new material against a secret from another action."""
    home = a_signed_in_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.REFRESH_LOGIN: REFRESHED.encode("utf-8").hex()})

    first = a_request(action_id="act-first")
    adapter.publish(first, run_once(adapter, first))
    adapter.release(first)
    second = a_request(action_id="act-second")

    kept = adapter.publish(second, run_once(adapter, second)).sensitive

    assert REFRESHED.encode("utf-8") in set(kept)
    assert SECRET.encode("utf-8") not in set(kept), (
        "a later attempt inherited a login value from an earlier one")


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
