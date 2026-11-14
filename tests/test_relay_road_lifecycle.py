"""What becomes of the relay home, the claim and the login lease when an attempt ends badly (I2b).

An attempt on the relay road holds the shared login lease from the copy to the removal of the home.
The words of the Codex ruling C2 and C3 (23.10.2026) are held here as behaviour:

- a boundary that refuses ENTRY started nothing: no marker, a clean lease, the next lease taken;
- a boundary that refuses to be LEFT after the child worked is an unknown outcome (the error the
  runtime records as `unknown`), with the marker standing and the lease still clean: nothing proves
  the tree is alive, so nothing declares the lease lost;
- a loan retired as unproven (`retire(False)`) keeps the lease uncertain, and the next attempt is
  refused for it: the one way this road poisons the lease is the way the runner already does;
- a child stopped or timed out is a receipt and the relay home is gone all the same;
- a home that cannot be removed is counted: the receipt says it, nothing the attempt made is
  published, and the next road is stopped by the sweep.

The shared lease is also held against another project's attempt on the same login, and a quota read
that comes while an attempt holds the project's root is deferred.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from conductor.command.adapters import subscription_quota
from conductor.command.adapters.harness_workspace import HarnessWorkspace, WorkspaceNotContained
from conductor.command.adapters.process import (
    CommandSpecError, OwnershipError, ProcessOutcome, ProcessRunner)
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.quota_connection import NativeQuotaDeferred
from conductor.command.failure_reasons import reason_words

from tests import _fakeclaude
from tests.relay_roads import CLAUDE, CODEX, Site, digests
from tests.test_relay_road_refusals import _raising, _refuse_removal_of

LEASE_BUSY = "the shared login lease was refused (login_owner_busy), so no task was spawned"
LEASE_LOST = "the shared login lease was refused (login_recovery_required), so no task was spawned"


# -- 1. the boundary refuses on the way out --------------------------------------------------


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_a_boundary_that_refuses_to_be_left_is_an_unknown_outcome_and_the_lease_stays_clean(
        vendor, tmp_path):
    site = Site(tmp_path, vendor)
    site.runner.exit_error = ProfileRefused("profile_acl_unproven", "a token is still alive")
    request, before = site.request(), digests(site.login)

    with pytest.raises(site.adapter.error, match="could not start the pinned build") as raised:
        site.run(request)

    assert "alive" not in str(raised.value)
    assert site.runner.events[-2:] == ["run-inside", "exit"] and len(site.tasks()) == 1
    assert site.claimed(request), "the child ran, so the action stays claimed"
    assert site.leftovers() == [] and digests(site.login) == before
    assert site.closed_leases() and site.lease_is_free()
    again = site.run(request)
    assert again.outcome == "unknown", "the work may have been done: it is never repeated"


def test_a_loan_retired_as_unproven_keeps_the_lease_uncertain_and_the_next_attempt_is_refused(
        tmp_path):
    site = Site(tmp_path, CLAUDE)
    first, second = site.request(action_id="act-1"), site.request(action_id="act-2")
    with site.owned() as owner:
        # After the child ran, as the runner does when it cannot prove the tree gone.
        site.runner.hooks["exit"] = lambda entry: owner.leased_login().hold()(False)
        with pytest.raises(OwnershipError, match="uncertain"):
            site.vendor.module.run_once(site.adapter, first)

    assert site.claimed(first) and site.leftovers() == [], "the home goes even then"
    site.runner.hooks.clear()
    receipt = site.run(second)
    assert receipt.outcome == "failed" and receipt.detail == LEASE_LOST
    assert len(site.rows()) == 3, "something was asked of the vendor under a lost lease"
    assert len(site.tasks()) == 1 and not site.claimed(second)


def test_the_readiness_is_spent_by_the_attempt_it_was_proved_for(tmp_path):
    """One preflight proves one attempt: a second attempt of the same road rests on nothing."""
    from conductor.command.adapters.relay_attempt import RelayNotStarted

    site = Site(tmp_path, CLAUDE)
    request = site.request()

    def attempt():
        # A relayed attempt is always handed the claim of its action (it takes it itself).
        return site.adapter._attempt(("--version",), "work", timeout=30, mode="dispatch",
                                     claim=site.adapter._claim_of(request))

    with site.owned():
        site.adapter._workspace.work_root()
        assert site.adapter._relay_start("dispatch") is None
        assert site.adapter._preflight(request) is None
        assert attempt().exit_code == 0, "the attempt the readiness was proved for did not run"
        with pytest.raises(RelayNotStarted) as refused:
            attempt()

    assert refused.value.code == "ready"
    assert [row["argv"] for row in site.rows()][-1] == ["--version"] and len(site.rows()) == 3
    assert site.leftovers() == [] and site.lease_is_free()


def test_a_readiness_the_road_did_not_spend_is_dropped_with_the_sample_of_that_road(tmp_path):
    site = Site(tmp_path, CODEX)

    with site.owned():
        assert site.adapter._preflight(site.request()) is None
        assert site.adapter._relay_ready is not None, "the preflight proved nothing"
        site.adapter._forget_login_sample()

    assert site.adapter._relay_ready is None


# -- 1b. a question to the real login that cannot be started -------------------------------------
#
# The version print and the login status are spawns under the same shared login lease as a task:
# an exception that leaves the guard makes the lease uncertain until the OS restarts. A runner that
# refuses to start them is the expected failure of a pin that cannot start (moved, damaged), not a
# loan the runner could not retire, so it must not poison the login.


def _refuse_the_question(site: Site, number: int, error: Exception) -> None:
    """The runner refuses the `number`th spawn that stands outside the boundary: a question."""
    real, asked = site.runner.run, []

    def run(spec):
        if spec.boundary is None:
            asked.append(spec.argv)
            if len(asked) == number:
                raise error
        return real(spec)

    site.runner.run = run


@pytest.mark.parametrize("number", [1, 2], ids=["version-print", "login-status"])
def test_a_question_to_the_real_login_that_the_runner_refuses_to_start_leaves_the_lease_clean(
        number, tmp_path):
    site = Site(tmp_path, CLAUDE)
    _refuse_the_question(site, number, CommandSpecError("the pinned build is not a command"))
    request, before = site.request(action_id="act-1"), digests(site.login)

    with pytest.raises(site.adapter.error, match="could not start the pinned build"):
        site.run(request)

    assert site.tasks() == [] and site.runner.entries == [] and not site.claimed(request)
    assert site.leftovers() == [] and digests(site.login) == before
    assert site.closed_leases() and site.lease_is_free(), "the login lease was left uncertain"
    del site.runner.run  # the runner starts what it is asked again
    assert site.run(site.request(action_id="act-2")).outcome == "succeeded"


def test_a_project_home_that_cannot_be_made_for_a_question_is_a_receipt_and_the_lease_is_clean(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    monkeypatch.setattr(
        HarnessWorkspace, "mint_home", _raising(WorkspaceNotContained("the homes are not local")))

    receipt = site.run()

    assert receipt.outcome == "failed" and receipt.detail == (
        "a name on the Claude Code workspace's own writable route is not locally contained, so "
        "nothing was minted, claimed or spawned")
    assert site.rows() == [] and site.runner.entries == [] and site.leftovers() == []
    assert site.closed_leases() and site.lease_is_free(), "the login lease was left uncertain"


# -- 2. a child that did not finish ----------------------------------------------------------


def test_a_timed_out_login_status_does_not_claim_a_missing_login_or_spawn_a_task(tmp_path):
    site = Site(tmp_path, CLAUDE)
    request, before = site.request(), digests(site.login)
    run = site.runner.run

    def slow_status(spec):
        if "auth" in spec.argv and "status" in spec.argv:
            return ProcessOutcome(
                status="timed_out", exit_code=None, output=b"private partial answer",
                output_truncated=False, output_limit=spec.output_limit, pid=1, token="status-token")
        return run(spec)

    site.runner.run = slow_status
    receipt = site.run(request)

    assert receipt.outcome == "failed"
    assert receipt.detail == (
        "the Claude Code subscription login check timed out, so no task was spawned")
    assert reason_words(receipt.detail) == "the subscription login check timed out before dispatch"
    assert not site.claimed(request) and site.tasks() == []
    assert site.leftovers() == [] and digests(site.login) == before and site.lease_is_free()


def test_a_child_that_overran_its_timeout_is_a_receipt_and_its_relay_home_is_gone(tmp_path):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.SLEEP: "30"})
    request, before = site.request(timeout=5), digests(site.login)

    receipt = site.run(request)

    assert receipt.outcome == "failed"
    assert receipt.detail == "the Claude Code prompt exceeded its timeout and was terminated"
    assert site.claimed(request) and len(site.tasks()) == 1
    assert site.leftovers() == [] and digests(site.login) == before and site.lease_is_free()


def test_a_child_the_runner_stopped_is_a_receipt_and_its_relay_home_is_gone(tmp_path):
    site = Site(tmp_path, CODEX)
    site.runner.outcome = ProcessOutcome(
        status="stopped", exit_code=None, output=b"", output_truncated=False, output_limit=1,
        pid=1, token="stopped-token")

    receipt = site.run()

    assert receipt.outcome == "cancelled"
    assert receipt.detail == "the Codex CLI task was stopped by the runner"
    assert site.leftovers() == [] and site.lease_is_free()


# -- 3. a home that cannot be removed --------------------------------------------------------


def test_a_relay_home_that_cannot_be_removed_is_counted_and_nothing_of_it_is_published(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done"})
    site.runner.hooks["run"] = lambda spec: _refuse_removal_of(
        monkeypatch, Path(spec.env[site.adapter.profile.home_env]).name)
    request = site.request()

    with site.owned():
        receipt = site.vendor.module.run_once(site.adapter, request)
        published = site.adapter.publish(request, receipt)
        site.adapter.release(request)

    assert receipt.outcome == "succeeded"
    assert receipt.detail.endswith(
        " an attempt home could not be discarded and was left standing, so the next dispatch is "
        "blocked until an operator has cleared the Claude Code home root")
    assert published.refusal == "home_retained", "work was offered over a home left standing"
    assert len(site.leftovers()) == 1


def test_the_home_left_standing_stops_the_next_road_until_it_can_be_removed(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    site.runner.hooks["run"] = lambda spec: _refuse_removal_of(
        monkeypatch, Path(spec.env[site.adapter.profile.home_env]).name)
    site.run(site.request(action_id="act-1"))
    site.runner.hooks.clear()
    held = len(site.rows())

    stopped = site.run(site.request(action_id="act-2"))

    assert stopped.outcome == "failed" and "may not delete" in stopped.detail
    assert len(site.rows()) == held, "something was asked of the vendor over a home left standing"
    monkeypatch.undo()
    assert site.run(site.request(action_id="act-3")).outcome == "succeeded"
    assert site.leftovers() == []


# -- 4. another project, and a quota read, meet the attempt -----------------------------------


def test_a_second_project_on_the_same_login_is_refused_before_it_asks_anything(tmp_path):
    first = Site(tmp_path, CLAUDE)
    second = Site(tmp_path, CLAUDE, root_name="root-b", name="b", login=first.login)
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with ProcessRunner.login_write_guard(first.root, str(first.login)):
            held.set()
            release.wait(30)

    request = second.request()
    with first.owned():
        holder = threading.Thread(target=hold)
        holder.start()
        try:
            assert held.wait(30)
            receipt = second.run(request)
        finally:
            release.set()
            holder.join(30)

    assert receipt.outcome == "failed" and receipt.detail == LEASE_BUSY
    assert second.rows() == [] and second.runner.entries == [] and not second.claimed(request)


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_a_quota_read_that_comes_while_an_attempt_holds_the_root_is_deferred_not_read(
        vendor, tmp_path, monkeypatch):
    monkeypatch.setattr(subscription_quota, "ROOT_WAIT_SECONDS", 0.3)
    site = Site(tmp_path, vendor)
    seen: list = []

    def read_meanwhile(spec) -> None:
        def read() -> None:
            try:
                site.adapter.quota_connection().read()
            except Exception as refused:  # noqa: BLE001 -- the kind of refusal is the answer
                seen.append(type(refused))

        worker = threading.Thread(target=read)
        worker.start()
        worker.join(30)

    site.runner.hooks["run"] = read_meanwhile
    receipt = site.run()

    assert receipt.outcome == "succeeded", receipt.detail
    assert seen == [NativeQuotaDeferred], "the quota read was not deferred by the busy root"
    assert len(site.tasks()) == 1 and len(site.rows()) == 3, "the quota read spawned something"
