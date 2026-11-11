"""A subscription attempt of Claude Code and Codex runs on a RELAY home and nowhere else (I2b).

The owner's decision of 23.10.2026 (H5-SUB-R5, access-only): the child of a task is handed a fresh
relay home that holds the credential WITHOUT its refresh token, and never the real login home. What
is held here, end to end over a real activated project, its live owner, the real shared login lease
of a login home and the product's own transport (`tests/relay_roads.py`):

- the child's home variable names the relay home; the version and login-status questions, which
  precede the task, still name the real login home, and nothing of the relay is asked before them;
- the relay home holds exactly the copy and no refresh token at the moment the child runs, and is
  gone afterwards, while the real login home is byte for byte what it was;
- the order is: lease, copy-in, boundary entered, claim, run. The claim is taken only after the
  boundary was entered, and the lease stands at both moments;
- Codex's final-message file is written into, and read from, the relay home;
- a review and an independent checker (Claude checked by another Claude instance, and Codex checked
  after a Claude doer) take the same road, and a real verdict decides the run;
- a login value only the relay home could hold (a token the vendor renewed) joins what is scanned.

A doubled boundary stands in for the AppContainer (`tests/_fakeboundary.py`); the native witness of
that boundary is `tests/test_relay_home_native.py`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conductor.command import verify_holds
from conductor.command.adapters.codex_cli import ANSWER_DETAIL, ANSWER_WRITTEN
from conductor.command.adapters.headless_values import attempt_relation
from conductor.command.runtime import AttemptState

from tests import _fakeclaude, _fakecodex
from tests import test_command_claude_transport as claude_t
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests.relay_roads import CLAUDE, CODEX, Site, digests
from tests.test_command_claude_review import (
    CONFIG, INPUT_REF, RUN_ID, SEED_CONTENT, _confirmation, _Ids, _proposal)
from tests.test_harness_login_leaks import CHILD_ONLY, documents_holding
from tests.test_independent_checker_transport import CHECKER, RUN, _run_state

REVIEW_KNOBS = {_fakeclaude.EMIT_REVIEW: "enabled-review-output",
                _fakeclaude.LEAK_CHECK: "enabled-review-leak-check"}
#: What the copy holds when the child runs, spelled out: every key of the real credential but the
#: refresh token and its deadline.
CLAUDE_COPY = {"claudeAiOauth": {
    "accessToken": "fake-claude-access-token-AAAAAAAAAAAA", "expiresAt": 1787414400000,
    "scopes": ["user:inference", "user:profile"], "subscriptionType": "max",
    "rateLimitTier": "default_claude_max_5x", "clientId": "fake-claude-client-id-0000"}}
CLAUDE_PROFILE_COPY = {"oauthAccount": {
    "accountUuid": "00000000-0000-4000-8000-00000000000a",
    "emailAddress": "fake.person@example.invalid",
    "organizationUuid": "00000000-0000-4000-8000-00000000000b", "displayName": "Fake Person",
    "organizationName": "Fake Organization", "organizationRole": "admin"}}
ROTATED = "fake-claude-rotated-token-NNNNNNNNNNNN"
HOME_NAME = re.compile(r"[cx]-[0-9a-f]{16}\Z")
#: Where each harness's credential keeps its section, and the keys of it that are secrets.
SECRET_FIELDS = {"claude-code": ("claudeAiOauth", ("accessToken", "refreshToken")),
                 "codex": ("tokens", ("id_token", "access_token", "refresh_token"))}


def _snapshot_the_home_when_the_child_runs(site: Site) -> dict:
    """What the relay home holds at the moment the runner is asked to start the child."""
    seen: dict = {}

    def look(spec) -> None:
        home = Path(spec.env[site.adapter.profile.home_env])
        seen.update({path.name: path.read_bytes() for path in home.iterdir()})

    site.runner.hooks["run"] = look
    return seen


# -- 1. the home the child is told about -------------------------------------------------------


def test_a_claude_dispatch_runs_on_a_relay_home_and_leaves_the_real_login_as_it_was(tmp_path):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done"})
    held = _snapshot_the_home_when_the_child_runs(site)
    before, request = digests(site.login), site.request()

    receipt = site.run(request)

    assert receipt.outcome == "succeeded", receipt.detail
    (task,) = site.tasks()
    relay = Path(task["claude_home"])
    assert (relay.parent, bool(HOME_NAME.fullmatch(relay.name)), relay.name[0]) == (
        site.relay_dir, True, "c")
    assert [row["claude_home"] for row in site.preflights()] == [
        str(site.login)] * 2, "the version and the login status stand on the real login"
    assert task["home_report"] == {"files": [".claude.json", ".credentials.json"], "refresh": False}
    assert {name: json.loads(text) for name, text in held.items()} == {
        ".credentials.json": CLAUDE_COPY, ".claude.json": CLAUDE_PROFILE_COPY}
    assert site.leftovers() == [], "the relay home outlived its attempt"
    assert digests(site.login) == before, "the real login home changed"
    assert site.claimed(request)


def test_a_codex_dispatch_runs_on_a_relay_home_and_reads_its_final_message_from_it(tmp_path):
    site = Site(tmp_path, CODEX)
    held = _snapshot_the_home_when_the_child_runs(site)
    before = digests(site.login)

    receipt = site.run()

    assert receipt.outcome == "succeeded", receipt.detail
    (task,) = site.tasks()
    relay = Path(task["codex_home"])
    assert (relay.parent, bool(HOME_NAME.fullmatch(relay.name)), relay.name[0]) == (
        site.relay_dir, True, "x")
    assert task["last_message"] == str(relay / "last-message.txt")
    assert ANSWER_DETAIL[ANSWER_WRITTEN] in receipt.detail, "the final message was not read"
    assert task["home_report"] == {"files": ["auth.json", "last-message.txt"], "refresh": False}
    copy = json.loads(held["auth.json"])
    assert sorted(copy) == ["OPENAI_API_KEY", "last_refresh", "tokens"]
    assert (copy["OPENAI_API_KEY"], copy["last_refresh"]) == (None, "2026-10-23T11:00:00Z")
    assert sorted(copy["tokens"]) == ["access_token", "account_id", "id_token", "refresh_token"]
    assert (copy["tokens"]["refresh_token"], copy["tokens"]["account_id"]) == (
        "", "fake-codex-account-0001")
    assert "fake-codex-refresh-token-RRRRRRRRRRRR" not in held["auth.json"].decode("utf-8")
    assert [row["codex_home"] for row in site.preflights()] == [str(site.login)] * 2
    assert site.leftovers() == [] and digests(site.login) == before


def test_the_home_a_spawn_is_told_about_is_the_relay_home_only_for_a_confined_task_attempt(
        tmp_path):
    site = Site(tmp_path, CLAUDE)
    home = tmp_path / "attempt-home"
    plain, _root, _log = claude_t.a_harness(
        tmp_path / "plain", auth="subscription", auth_home=str(site.login))

    assert site.adapter._home_value(home) == str(site.login), "a preflight stands on the login"
    assert site.adapter._home_value(home, "dispatch") == str(home)
    assert site.adapter._home_value(home, "review") == str(home)
    assert plain._home_value(home, "dispatch") == str(site.login), (
        "a transport never confined launches as it did before the boundary: on the login")


# -- 2. the order -------------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_the_road_asks_for_the_relay_folder_first_and_proves_the_login_after_its_last_question(
        vendor, tmp_path):
    site = Site(tmp_path, vendor)

    receipt = site.run()

    assert receipt.outcome == "succeeded", receipt.detail
    assert site.runner.events == [
        "relay-root", "run-outside", "run-outside", "acl", "acl-home", "enter", "run-inside",
        "exit"]


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_the_action_is_claimed_only_after_the_boundary_is_entered_and_the_lease_stands_at_both(
        vendor, tmp_path):
    site = Site(tmp_path, vendor)
    request, seen = site.request(), []
    with site.owned() as owner:
        site.runner.hooks["enter"] = lambda entry: seen.append(
            ("enter", site.claimed(request), owner.leased_login().home))
        site.runner.hooks["run"] = lambda spec: seen.append(
            ("run", site.claimed(request), owner.leased_login().home))
        receipt = vendor.module.run_once(site.adapter, request)

    assert receipt.outcome == "succeeded", receipt.detail
    assert seen == [("enter", False, site.login), ("run", True, site.login)]
    (entry,) = site.runner.entries
    assert (entry.mode, entry.internet_client) == ("dispatch", True)
    assert Path(entry.folders.home).is_absolute() and Path(entry.folders.home).parent == (
        site.relay_dir)


def test_the_readiness_of_the_login_is_proved_after_the_status_question_that_could_change_it(
        tmp_path):
    """The status spawn runs on the real login, so a login it spoilt is a login not ready."""
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.PREFLIGHT_HOME_FILE: ".credentials.json:{}"})
    request = site.request()

    receipt = site.run(request)

    assert receipt.outcome == "failed"
    assert receipt.detail == (
        "the Claude Code login is not ready for an isolated attempt: the credential file holds "
        "credentials this build does not copy, so no task was spawned")
    assert site.tasks() == [] and site.runner.entries == [] and not site.claimed(request)


# -- 3. a review, and an independent checker ---------------------------------------------------


def _confirmed_review(site: Site):
    """One review step driven through Confirm over the relay road, inside the project's owner."""
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.artifacts import ArtifactDocument
    from conductor.command.contracts import RunEnvelope
    from conductor.command.run_store import RunStore, snapshot_digest
    from conductor.command.runtime import Budget, ControlRuntime

    with site.owned():
        store = RunStore(site.root)
        store.create_run(RunEnvelope(
            run_id=RUN_ID, cycle_id="review-cycle", created_at=claude_t.NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"), CONFIG)
        store.append(ArtifactDocument(
            artifact_id="artifact-source-1", artifact_ref=INPUT_REF, run_id=RUN_ID,
            created_at=claude_t.NOW, media_type="text/markdown", content=SEED_CONTENT))
        proposal = _proposal()
        store.append(proposal)
        runtime = ControlRuntime(
            store, AdapterRegistry([site.adapter]), clock=lambda: claude_t.NOW, ids=_Ids())
        budget = Budget(
            max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
        return runtime.execute(runtime.authorize(_confirmation(proposal), budget=budget)), store


def test_a_claude_review_runs_on_a_relay_home_and_its_text_is_published(tmp_path):
    site = Site(tmp_path, CLAUDE, **REVIEW_KNOBS)
    before = digests(site.login)

    attempt, store = _confirmed_review(site)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    (task,) = site.tasks()
    assert Path(task["claude_home"]).parent == site.relay_dir
    assert task["home_report"]["refresh"] is False
    (entry,) = site.runner.entries
    assert entry.mode == "review" and site.claimed(attempt.request)
    assert len(documents_holding(store, CHILD_ONLY)) == 1
    assert site.leftovers() == [] and digests(site.login) == before


def _checked_run(site: Site, doer, checker, cross: bool):
    """A doer's step and its independent check, through the runtime, inside the owner."""
    with site.owned():
        runtime, authorization, store = _run_state(
            site.root, doer, checker, cross, False, None, None, None)
        attempt = runtime.execute(authorization)
        evidence = [row.value for row in store.read(RUN).records if row.kind == "evidence"]
        accounts = [row for row in evidence if row.kind == "subscription_account_v1"]
        assert all(row.verification == "unverified" for row in accounts)
        assert not {row.evidence_id for row in accounts} & set(attempt.receipt.evidence_refs)
        return attempt, [row for row in evidence if row.kind != "subscription_account_v1"]


def test_claude_is_checked_by_another_claude_instance_each_on_its_own_relay_home(tmp_path):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done",
                                     _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
    before = digests(site.login)

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    doer, check = site.tasks()
    assert {Path(row["claude_home"]).parent for row in (doer, check)} == {site.relay_dir}
    assert doer["claude_home"] != check["claude_home"], "the checker reused the doer's home"
    assert "--permission-mode" in check["argv"] and "plan" in check["argv"]
    assert [entry.mode for entry in site.runner.entries] == ["dispatch", "review"]
    (row,) = evidence
    assert (row.verified_by, row.verifier_instance_id) == ("claude-code", CHECKER)
    assert attempt.request.instance_id != CHECKER, "the same instance checked itself"
    assert site.adapter.verification_started(attempt.request), "the check was never claimed"
    assert site.leftovers() == [] and digests(site.login) == before


def test_a_rejecting_verdict_of_the_relay_checker_is_a_failed_check_and_no_evidence(tmp_path):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done",
                                     _fakeclaude.EMIT_VERDICT: "enabled-verdict-reject"})

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert verify_holds.CHECKER_REJECTED in attempt.receipt.detail
    assert evidence == [] and len(site.tasks()) == 2


@pytest.mark.usefixtures("boundary_assumed")
def test_codex_checks_a_claude_result_on_a_relay_home_of_its_own(tmp_path):
    site = Site(tmp_path, CODEX, **{_fakecodex.EMIT_VERDICT: "enabled-verdict-accept"})
    doer, _root, doer_log = claude_t.a_harness(
        tmp_path / "doer", root=site.root, **{_fakeclaude.WRITE_FILE: "result.txt:done"})
    before = digests(site.login)

    attempt, evidence = _checked_run(site, doer, site.adapter, True)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    (check,) = site.tasks()
    assert Path(check["codex_home"]).parent == site.relay_dir
    assert check["home_report"] == {"files": ["auth.json", "last-message.txt"], "refresh": False}
    assert "read-only" in check["argv"]
    assert len(_fakeclaude.prompt_spawns(doer_log)) == 1
    assert [entry.mode for entry in site.runner.entries] == ["review"]
    (row,) = evidence
    assert (row.verified_by, row.verifier_instance_id) == ("codex", CHECKER)
    assert site.adapter.verification_started(attempt.request), "the check was never claimed"
    assert site.leftovers() == [] and digests(site.login) == before


# -- 4. a login value only the relay home could hold --------------------------------------------


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_a_token_the_vendor_renewed_in_the_relay_home_joins_what_is_scanned_for(
        vendor, tmp_path):
    fresh = ROTATED
    site = Site(tmp_path, vendor, **{vendor.fake.ROTATE_ACCESS: fresh.encode("utf-8").hex()})
    request = site.request()
    before = digests(site.login)

    receipt = site.run(request)

    assert receipt.outcome == "succeeded", receipt.detail
    assert digests(site.login) == before, "the renewed token reached the real login"
    assert fresh.encode("utf-8") in site.adapter._sensitive_values(attempt_relation(request)), (
        "a value only the relay home held was not read back before the home was discarded")
    assert fresh.encode("utf-8") not in site.adapter._sensitive_values()
    site.adapter.release(request)


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_the_runner_and_the_road_hold_both_copies_of_the_login_even_if_the_file_cannot_be_read(
        vendor, tmp_path):
    """The credential of the real login and the copy are scanned for by the values readiness and
    copy-in saw, not only by a second reading of the real file at the moment of the spawn."""
    site = Site(tmp_path, vendor)
    site.adapter._login_secrets = lambda: ()  # the real file cannot be read at that moment
    section, fields = SECRET_FIELDS[vendor.name]
    body = json.loads(site.leaf_path().read_text(encoding="utf-8"))[section]
    wanted = {body[field].encode("utf-8") for field in fields}
    seen, request = [], site.request()
    site.runner.hooks["run"] = lambda spec: seen.append(set(spec.sensitive_extra))

    receipt = site.run(request)

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(wanted) == len(fields) and seen and wanted <= seen[0], (
        "the runner was not handed the values of both copies to scan its output for")
    assert wanted <= set(site.adapter._sensitive_values(attempt_relation(request))), (
        "what the road saw of both copies is not held for the publication scans")
    site.adapter.release(request)


def test_a_credential_the_child_spoilt_in_its_relay_home_is_taken_as_echoed(tmp_path):
    """A relay credential that cannot be read back, or has left its shape, is not known to be
    harmless: nothing the child said can be trusted not to carry what it held."""
    site = Site(tmp_path, CLAUDE, **REVIEW_KNOBS, **{_fakeclaude.HOME_FILE: ".credentials.json:{x"})

    attempt, store = _confirmed_review(site)

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert documents_holding(store, CHILD_ONLY) == [], "a review was published over a spoilt login"
    assert site.adapter._login_echo is True


#: A text only a key the build was not reviewed against holds: not a named secret field of the
#: credential, so only a reading of EVERY text of the document finds it.
UNREVIEWED = "fake-claude-unreviewed-text-UUUUUUUUUUUU"


def test_every_text_of_a_relay_credential_that_left_its_shape_joins_what_is_scanned_for(tmp_path):
    """A document that still parses but is no longer the credential the relay admits (a key the
    build was not reviewed against): which of its texts is a token cannot be said, so all of them
    are looked for, and not only the fields the reviewed shape names as secret. The text sits
    under a key outside the schema and outside the secret fields, and nowhere else: it is no
    value of the environment the scan already holds."""
    spoilt = ('.credentials.json:{"claudeAiOauth": {"accessToken": "tiny", '
              f'"unreviewed": "{UNREVIEWED}"}}}}')
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.HOME_FILE: spoilt})
    request = site.request()

    site.run(request)

    held = site.adapter._sensitive_values(attempt_relation(request))
    assert UNREVIEWED.encode("utf-8") in held, "a text of a credential out of its shape is not held"
    assert site.adapter._login_echo is True
    site.adapter.release(request)


def test_a_review_that_prints_the_token_its_relay_home_renewed_is_not_published(tmp_path):
    fresh = ROTATED.encode("utf-8").hex()
    site = Site(tmp_path, CLAUDE, **REVIEW_KNOBS, **{_fakeclaude.ROTATE_ACCESS: fresh})

    attempt, store = _confirmed_review(site)

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert documents_holding(store, CHILD_ONLY) == [], "a review was published over a login value"
    assert site.adapter._login_echo is True


def test_a_review_that_prints_the_access_token_of_its_copy_is_not_published(tmp_path):
    """The control of the test above, with the token the real login holds too.

    A control: it also passes where no review can run at all, so it asks that the child ran
    (`len(site.tasks()) == 1`) and that the output was seen to carry the token (`_login_echo`).
    """
    token = "fake-claude-access-token-AAAAAAAAAAAA".encode("utf-8").hex()
    site = Site(tmp_path, CLAUDE, **REVIEW_KNOBS, **{_fakeclaude.EMIT_HEX: token})

    attempt, store = _confirmed_review(site)

    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert documents_holding(store, CHILD_ONLY) == []
    assert len(site.tasks()) == 1, "no review ran, so nothing was withheld"
    assert site.adapter._login_echo is True


def test_the_review_of_the_control_runs_clean_and_is_published(tmp_path):
    site = Site(tmp_path, CLAUDE, **REVIEW_KNOBS)

    attempt, store = _confirmed_review(site)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert site.adapter._login_echo is False
    assert len(documents_holding(store, CHILD_ONLY)) == 1
