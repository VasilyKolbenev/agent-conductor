"""What a FINISHED road may still be holding of the login it sampled.

Split from the login-leak module at 757 of 800 lines, and on a subject: next
door proves where a credential may TRAVEL -- into a child's output, into
material handed to a checker, into a receipt -- while this proves how long the
adapter goes on holding it after the road that read it is over.

Nothing here is a claim about a leak. Nothing published these bytes, nothing
wrote them down, and no other process could read them. What is held here is a
LIFETIME: this build reads an operator's credential out of a directory it does
not own, and the contract it makes in return is that it stops holding what it
read when the road that read it ends.

Two roads had nobody to hand the sample to, so they kept it until something
unrelated happened to reset the field. A checker samples around its own spawn
and hands nothing to any attempt. A login preflight that refuses spawns a
status probe, reads the file on both sides of it, and then returns without ever
reaching the attempt that would have owned the values. Both are held below, and
so is the release's own boundary: it may drop what the ROAD gathered and it may
not touch what an attempt was given.

The value is synthetic and is the fixture's, never a real credential: no test in
this repository reads, writes or observes vendor login material.
"""
from __future__ import annotations

from tests import _fakeclaude
from tests.test_command_claude_transport import a_request, run_once
from tests.test_harness_login_leaks import SECRET, a_signed_in_home
from tests.test_harness_subscription_login import a_harness

SAMPLED = SECRET.encode("utf-8")


def test_a_finished_checker_holds_no_copy_of_the_login_it_sampled(tmp_path):
    """The road with nobody to hand its sample to.

    A checker reads the login file on both sides of its own spawn -- it has to,
    because a vendor that refreshes mid-run leaves two values in play -- and
    then answers. No attempt owns what it gathered, so nothing carried it away,
    and the field kept it until an unrelated road happened to reset it.
    """
    from tests.test_independent_checker_transport import _run_state

    home = a_signed_in_home(tmp_path)
    adapter, root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.WRITE_FILE: "result.txt:synthetic-work-result",
           _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
    runtime, authorization, _store = _run_state(
        root, adapter, adapter, False, False, None, None, None)

    attempt = runtime.execute(authorization)

    assert attempt.state.value == "succeeded", attempt.receipt.detail
    assert adapter._login_history == {}, "the attempt's own values outlived it"
    assert SAMPLED not in adapter._login_seen, (
        "a finished checker is still holding the login it sampled")


def test_a_refused_preflight_holds_no_copy_of_the_login_it_read(tmp_path):
    """The other road with nobody to hand it to, and it never spawned a task.

    The status probe runs, the file is read on both sides of it, and the road
    refuses. Release drops what an attempt owned; this set was never an
    attempt's, so release was never going to reach it.
    """
    home = a_signed_in_home(tmp_path)
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.LOGIN_FAILS: "enabled"})
    request = a_request()

    receipt = run_once(adapter, request)
    adapter.release(request)

    assert receipt.outcome == "failed", receipt.detail
    assert _fakeclaude.prompt_spawns(log) == [], "a task ran on a refused login"
    assert adapter._login_history == {}
    assert SAMPLED not in adapter._login_seen, (
        "a road that refused before any task is still holding the login")


def test_a_review_refused_at_its_own_preflight_holds_no_copy(tmp_path):
    """The THIRD road, and it is a road because the release is on three of them.

    A review takes its own turn and asks its own login preflight, so a refusal
    there leaves it exactly where the dispatch road was: a sample gathered, no
    attempt to hand it to, and a road that is over. Named separately because a
    fix written once for "the adapter" is a fix that reached two roads and got
    counted for three -- which is the shape every regression on this road has
    had.
    """
    from tests.test_harness_login_leaks import a_review

    home = a_signed_in_home(tmp_path)
    attempt, _store, adapter, log = a_review(
        tmp_path, home, **{_fakeclaude.LOGIN_FAILS: "enabled"})

    assert attempt.state.value != "succeeded", attempt.receipt.detail
    assert _fakeclaude.prompt_spawns(log) == [], "a review ran on a refused login"
    assert SAMPLED not in adapter._login_seen, (
        "a refused review is still holding the login it read")


def test_a_completed_dispatch_holds_no_copy_either(tmp_path):
    """The road that DOES hand its sample over, asked the same question.

    This one always cleared the field, because handing the values to the attempt
    empties it. Held anyway, and on the same terms as the two roads above: the
    promise is about every road, and a promise kept by accident on one of them
    is the one that breaks when the hand-off moves.
    """
    home = a_signed_in_home(tmp_path)
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))
    request = a_request()

    receipt = run_once(adapter, request)

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(_fakeclaude.prompt_spawns(log)) == 1
    assert SAMPLED not in adapter._login_seen
    assert adapter._login_history, (
        "the attempt was handed nothing, so this proves the wrong thing")


def test_the_release_drops_the_roads_set_and_not_an_attempts(tmp_path):
    """The boundary, and it is the one a wider release would cross.

    An attempt that is still owed its material scan keeps what it was given.
    Dropping the road's working set is not licence to drop that: the scan a
    publication runs is built from the attempt's own values, and a release that
    reached them would leave the next surface scanning for the wrong secret.
    """
    home = a_signed_in_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))
    request = a_request()
    run_once(adapter, request)
    standing = dict(adapter._login_history)

    adapter._forget_login_sample()

    assert adapter._login_history == standing, (
        "the road's release reached into what an attempt was given")
    assert standing, "the attempt held nothing, so the boundary is untested"
