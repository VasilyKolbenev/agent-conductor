"""A relay attempt that cannot be prepared is refused BEFORE its claim, and says why (I2b).

The expected failures of preparing a relay attempt are values and never exceptions raised inside the
shared login lease: such an exception makes the lease uncertain and the login unusable until the OS
restarts (design F3, ruling C3 of the Codex review of 23.10.2026). So every case below ends the same
way, and the test of each asserts all of it: a `failed` receipt with the closed sentence and the
runtime's own words for it, no task child, no marker for the action, no relay home left standing,
and the lease taken again at once. The sentences and the words are spelled here by hand; the cases
are driven through the product's transport over a real activated project and a real login lease
(`tests/relay_roads.py`).

The cases fall in three places on the road: the start (the relay folder and the sweep, before the
version question), the readiness (after the status question, which is the login's last use on the
real home), and the attempt itself (under the lease: the copy, the home, the boundary entry).
"""
from __future__ import annotations

import os
import shutil
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from conductor.command.adapters import harness_attempt
from conductor.command.adapters.harness_workspace import HarnessWorkspace, WorkspaceNotContained
from conductor.command.adapters.process import CommandSpecError, OwnershipError
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.quota_connection import NativeQuotaReadError
from conductor.command.failure_reasons import reason_words
from conductor.command.runtime import AttemptState
from conductor.command import verify_holds
from conductor.ownership_errors import OwnerRefused
from conductor.ownership_login import LeasedLogin
from conductor.ownership import ProjectOwner

from tests import _fakeclaude
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests.relay_credentials import claude_leaf, claude_profile, codex_leaf, millis, put
from tests.relay_roads import CLAUDE, CLOCK, CODEX, LIFE, Site, codex_access, digests
from tests.test_relay_road_success import REVIEW_KNOBS, _checked_run, _confirmed_review

#: Every refusal of a login, as the sentence says it and as the runtime words it.
PHRASES = {
    "leaf_absent": "the login holds no credential file this build can copy",
    "leaf_unsafe": "the credential file is not an ordinary file with a single name",
    "leaf_too_large": "the credential file is larger than a credential file is",
    "leaf_malformed": "the credential file is not one JSON object in UTF-8",
    "foreign_credentials": "the credential file holds credentials this build does not copy",
    "unknown_shape": "the credential file is not in a shape this build was reviewed against",
    "no_access_token": "the credential file holds no access token",
    "api_key": "the login holds an API key, which is not a subscription",
    "plan_unknown": "the login does not say which plan it is on",
    "console_plan": "the login is on the API-billing plan, which is not a subscription",
    "account_unknown": "the account of the login could not be established",
    "credman": "the vendor would keep the refreshed login in the Windows credential manager",
    "credman_unknown": "whether the vendor uses the Windows credential manager is not known",
    "expiry_unknown": "when the access token expires could not be established",
    "expiry_short": "the access token expires before the attempt would end",
    "changed": "the credential file changed after it was checked",
    "refresh_leak": "the copy would carry a refresh token",
    "relay_unusable": "the attempt home is not a folder this build can copy into",
    "not_empty": "the attempt home is not empty",
    "write_failed": "the credential could not be written into the attempt home",
    "root": "the relay folder of the login is not usable",
    "acl": "a folder of the login or of its relay is open to an isolated child",
    "env": "the environment of the attempt carries a name that replaces the login or "
           "reroutes its traffic",
    "ready": "the login was not proved ready for this attempt",
    "lease": "the login lease of the attempt does not name this login",
    "mint": "the relay home of the attempt could not be made",
    "spec": "the command of the attempt could not be built for its relay home",
    "enter": "the execution boundary refused the relay home of the attempt",
    "claim": "the action could not be claimed for the attempt",
    "claim_standing": "the claim of the action could not be completed but its marker stands, and "
                      "a repeat of the action is unknown",
}
WORDS = {
    "leaf_absent": "the pinned login has no credential file to copy",
    "leaf_unsafe": "the pinned login's credential file is not an ordinary file",
    "leaf_too_large": "the pinned login's credential file is too large",
    "leaf_malformed": "the pinned login's credential file is damaged",
    "foreign_credentials": "the pinned login holds credentials this build does not copy",
    "unknown_shape": "the pinned login's credential file is in a shape this build does not know",
    "no_access_token": "the pinned login holds no access token",
    "api_key": "the pinned login holds an API key, which is not a subscription",
    "plan_unknown": "the pinned login does not say which plan it is on",
    "console_plan": "the pinned login is on the API-billing plan",
    "account_unknown": "the account of the pinned login could not be established",
    "credman": "the pinned login would be kept in the Windows credential manager",
    "credman_unknown": "it is not known whether the pinned login is kept in the Windows "
                       "credential manager",
    "expiry_unknown": "when the pinned login expires is not known; sign in again",
    "expiry_short": "the pinned login expires before the attempt would end; sign in again",
    "changed": "the pinned login changed while the attempt was prepared",
    "refresh_leak": "the copy of the pinned login would carry a refresh token",
    "relay_unusable": "the attempt's relay home could not be used",
    "not_empty": "the attempt's relay home was not empty",
    "write_failed": "the login could not be copied into the attempt's relay home",
    "root": "the relay folder of the pinned login is not usable",
    "acl": "a folder of the pinned login or of its relay is open to an isolated child",
    "env": "the environment of the attempt replaces the pinned login or reroutes its traffic",
    "ready": "the pinned login was not proved ready for the attempt",
    "lease": "the login lease of the attempt does not name the pinned login",
    "mint": "the attempt's relay home could not be made",
    "spec": "the attempt's command could not be built",
    "enter": "the execution boundary refused the attempt's relay home",
    "claim": "the action could not be claimed for the attempt",
    "claim_standing": "the claim of the action could not be completed and its marker stands",
}
#: The vendor's own login command, and the variable that points the vendor at a login folder.
COMMAND = {CLAUDE: "auth login --claudeai", CODEX: '-c cli_auth_credentials_store="file" login'}
HOME_ENV = {CLAUDE: "CLAUDE_CONFIG_DIR", CODEX: "CODEX_HOME"}
#: What the sentence adds where only a new sign-in repairs the login: the command with the variable,
#: so that the person signs in to the folder this provider pins and not to the vendor's own profile.
SIGN_IN = {
    CLAUDE: "CLAUDE_CONFIG_DIR set to the login directory this provider pins and run "
            "auth login --claudeai",
    CODEX: "CODEX_HOME set to the login directory this provider pins and run "
           '-c cli_auth_credentials_store="file" login'}
RE_LOGIN = ("expiry_short", "expiry_unknown")
#: The refusals that say nothing against the login: the attempt could not be started inside the
#: isolation (the relay home, the command, the boundary, the claim). Every other refusal is about
#: the login or its folders, and says the login is not ready.
NOT_THE_LOGIN = ("mint", "spec", "enter", "claim", "claim_standing")


def sentence(vendor, code: str) -> str:
    again = f"; sign in again with {SIGN_IN[vendor]}" if code in RE_LOGIN else ""
    head = (f"the {vendor.tool} attempt could not start in isolation: " if code in NOT_THE_LOGIN
            else f"the {vendor.tool} login is not ready for an isolated attempt: ")
    return f"{head}{PHRASES[code]}, so no task was spawned{again}"


def assert_refused_before_the_claim(site: Site, request, receipt, code: str, *, entered=False):
    """The whole of what a refusal before the claim means; see the module docstring."""
    assert receipt.outcome == "failed", receipt.detail
    assert receipt.detail == sentence(site.vendor, code)
    assert reason_words(receipt.detail) == WORDS[code]
    assert site.tasks() == [], "a task child was started"
    assert len(site.runner.entries) == (1 if entered else 0)
    assert not site.claimed(request), "the action was claimed"
    assert site.leftovers() == [], "a relay home was left standing"
    assert site.lease_is_free(), "the login lease was left unusable"


# -- 1. a login that cannot be copied ---------------------------------------------------------


def _leaf(site: Site, document) -> None:
    put(site.login, site.vendor.leaf, document)


def _claude(**oauth):
    return claude_leaf(expiresAt=millis(CLOCK + LIFE), **oauth)


def _without(document: dict, key: str) -> dict:
    del document["claudeAiOauth"][key]
    return document


def _two_names(site: Site) -> None:
    os.link(site.leaf_path(), site.login / "second-name.json")


def _credman(site: Site) -> None:
    put(site.login, ".config.json", {"cachedGrowthBookFeatures": {"tengu_windows_credman": True}})


def _codex(**tokens):
    return codex_leaf(access_token=codex_access(), **tokens)


CLAUDE_CASES = [
    ("leaf_absent", lambda site: site.leaf_path().unlink()),
    ("leaf_unsafe", _two_names),
    ("leaf_too_large", lambda site: site.leaf_path().write_text(
        '{"claudeAiOauth": {"accessToken": "' + "A" * 70000 + '"}}', encoding="utf-8")),
    ("leaf_malformed", lambda site: site.leaf_path().write_text("{not json", encoding="utf-8")),
    ("foreign_credentials", lambda site: _leaf(site, {**_claude(), "mcpOAuth": {}})),
    ("unknown_shape", lambda site: _leaf(site, _claude(unexpected="x"))),
    ("no_access_token", lambda site: _leaf(site, _claude(accessToken=""))),
    ("plan_unknown", lambda site: _leaf(site, _without(_claude(), "subscriptionType"))),
    ("console_plan", lambda site: _leaf(site, _claude(subscriptionType="console"))),
    ("account_unknown", lambda site: put(
        site.login, ".claude.json", claude_profile(oauthAccount={"displayName": "nobody"}))),
    ("credman", _credman),
    ("credman_unknown", lambda site: (site.login / ".config.json").write_text(
        "{broken", encoding="utf-8")),
    ("expiry_unknown", lambda site: _leaf(site, _without(_claude(), "expiresAt"))),
]
CODEX_CASES = [
    ("api_key", lambda site: _leaf(site, {**_codex(), "OPENAI_API_KEY": "fake-codex-api-key"})),
    ("account_unknown", lambda site: _leaf(site, _codex(account_id=""))),
    ("no_access_token", lambda site: _leaf(site, codex_leaf(access_token=""))),
    ("expiry_unknown", lambda site: _leaf(site, codex_leaf(access_token="not-a-token-at-all"))),
]


@pytest.mark.parametrize("code,change", CLAUDE_CASES, ids=[row[0] for row in CLAUDE_CASES])
def test_a_claude_login_that_cannot_be_copied_is_refused_before_the_claim(code, change, tmp_path):
    site = Site(tmp_path, CLAUDE)
    change(site)
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, code)
    assert len(site.rows()) == 2, "the version and the status are the only questions asked"


@pytest.mark.parametrize("code,change", CODEX_CASES, ids=[row[0] for row in CODEX_CASES])
def test_a_codex_login_that_cannot_be_copied_is_refused_before_the_claim(code, change, tmp_path):
    site = Site(tmp_path, CODEX)
    change(site)
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, code)


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_a_login_that_ends_before_the_attempt_is_refused_and_a_new_sign_in_is_asked_for(
        vendor, tmp_path):
    site = Site(tmp_path, vendor, life=timedelta(minutes=5))
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "expiry_short")
    assert receipt.detail.endswith(f"; sign in again with {SIGN_IN[vendor]}")


@pytest.mark.parametrize("timeout,seconds,accepted", [
    (60, 660, True), (60, 659, False), (3000, 3600, True), (3000, 3599, False)])
def test_the_login_must_outlast_the_timeout_of_this_attempt_by_ten_minutes(
        timeout, seconds, accepted, tmp_path):
    site = Site(tmp_path, CLAUDE, life=timedelta(seconds=seconds))
    request = site.request(timeout=timeout)

    receipt = site.run(request)

    if accepted:
        assert receipt.outcome == "succeeded", receipt.detail
    else:
        assert_refused_before_the_claim(site, request, receipt, "expiry_short")


def test_the_readiness_is_asked_again_for_every_attempt_and_is_never_kept(tmp_path):
    site = Site(tmp_path, CLAUDE)
    first, second = site.request(action_id="act-1"), site.request(action_id="act-2")
    assert site.run(first).outcome == "succeeded"

    _leaf(site, claude_leaf(expiresAt=millis(CLOCK + timedelta(minutes=5))))
    receipt = site.run(second)

    assert receipt.detail == sentence(CLAUDE, "expiry_short")
    assert site.claimed(first) and not site.claimed(second) and len(site.tasks()) == 1


def test_the_independent_check_asks_for_the_login_again_after_the_doer_has_finished(tmp_path):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done",
                                     _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
    short = claude_leaf(expiresAt=millis(CLOCK + timedelta(minutes=5)))
    site.runner.hooks["exit"] = lambda entry: (
        _leaf(site, short) if entry.mode == "dispatch" else None)

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == "the checker's login is not ready for an isolated attempt"
    assert evidence == [] and len(site.tasks()) == 1, "the checker ran on a login not ready"
    assert not site.adapter.verification_started(attempt.request)
    assert site.leftovers() == [] and site.lease_is_free()


# -- 2. the readiness of the login and of its folders, before the claim -----------------------


def test_a_login_the_status_question_rewrote_is_a_login_not_ready(tmp_path):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.PREFLIGHT_HOME_FILE: ".credentials.json:{}"})
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "foreign_credentials")


def test_a_relay_folder_that_cannot_be_proved_is_refused_before_any_question_is_asked(tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.runner.relay_root_error = ProfileRefused(
        "profile_acl_invalid", "the relay folder (DecemberCommand/relay) is not protected")
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "root")
    assert site.rows() == [] and site.runner.events == ["relay-root"]


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_a_folder_that_could_open_the_login_to_a_container_is_refused_before_the_claim(
        vendor, tmp_path):
    site = Site(tmp_path, vendor)
    site.runner.acl_refusal = "the login home has an entry for ALL APPLICATION PACKAGES"
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "acl")
    assert "acl-home" not in site.runner.events and len(site.rows()) == 2
    assert str(site.login) not in receipt.detail and "PACKAGES" not in receipt.detail


def test_a_folder_found_open_after_the_relay_home_was_made_is_refused_and_the_home_goes(tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.runner.acl_refusal = lambda home: None if home is None else "the key folder has an entry"
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "acl")
    assert site.runner.events[-1] == "acl-home"


@pytest.mark.parametrize("name", [
    "ANTHROPIC_BASE_URL", "https_proxy", "CLAUDE_CODE_OAUTH_TOKEN", "NODE_EXTRA_CA_CERTS"])
def test_a_name_that_replaces_the_login_or_reroutes_it_is_refused_where_it_is_really_selected(
        name, tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.adapter._pin = replace(site.adapter._pin, env_allow=(*site.adapter._pin.env_allow, name))
    site.runner._environ[name] = "http://route.invalid"
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "env")
    assert "route.invalid" not in receipt.detail and name not in receipt.detail
    assert site.rows() == [], "the real login home was asked something in an environment refused"
    assert site.runner.events == ["relay-root"]


@pytest.mark.parametrize("vendor", [CLAUDE, CODEX], ids=lambda vendor: vendor.name)
def test_a_quota_read_in_an_environment_that_reroutes_the_login_is_not_supported(vendor, tmp_path):
    site = Site(tmp_path, vendor)
    name = "ANTHROPIC_BASE_URL" if vendor is CLAUDE else "OPENAI_BASE_URL"
    site.adapter._pin = replace(site.adapter._pin, env_allow=(*site.adapter._pin.env_allow, name))
    site.runner._environ[name] = "http://route.invalid"

    with pytest.raises(NativeQuotaReadError) as refused:
        site.adapter.quota_connection().read()

    assert refused.value.reason == "not_supported"
    assert site.rows() == [], "the real login home was asked something in an environment refused"


def test_the_same_name_allowed_but_not_present_in_the_environment_is_not_selected(tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.adapter._pin = replace(
        site.adapter._pin, env_allow=(*site.adapter._pin.env_allow, "ANTHROPIC_BASE_URL"))

    receipt = site.run()

    assert receipt.outcome == "succeeded", receipt.detail


# -- 3. the start: leftovers of earlier attempts --------------------------------------------


def _leftover(site: Site, name: str = "c-0123456789abcdef") -> Path:
    home = site.relay_dir / name
    home.mkdir(parents=True)
    (home / ".credentials.json").write_text("{}", encoding="utf-8")
    return home


def _refuse_removal_of(monkeypatch, name: str) -> None:
    """The file system refuses to remove anything on a path that names `name`."""
    def guarded(real):
        def refuse(path, *arguments, **options):
            if name in str(path):
                raise PermissionError(13, "the file system refuses the removal")
            return real(path, *arguments, **options)
        return refuse

    for function in ("unlink", "remove", "rmdir"):
        monkeypatch.setattr(os, function, guarded(getattr(os, function)))


def test_a_relay_home_an_earlier_attempt_left_is_removed_by_the_sweep_and_the_run_goes_on(
        tmp_path):
    site = Site(tmp_path, CLAUDE)
    left = _leftover(site)

    receipt = site.run()

    assert receipt.outcome == "succeeded", receipt.detail
    assert not left.exists() and site.leftovers() == []


def test_a_leftover_the_sweep_cannot_remove_stops_the_attempt_before_anything_is_asked(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    left = _leftover(site)
    _refuse_removal_of(monkeypatch, left.name)
    request = site.request()

    receipt = site.run(request)

    assert receipt.outcome == "failed"
    assert receipt.detail == (
        "the Claude Code home root holds state this build did not mint and may not delete, so "
        "nothing was preflighted, claimed or spawned; a dispatch runs again once an operator has "
        "cleared it")
    assert site.rows() == [] and site.runner.entries == [] and not site.claimed(request)
    assert left.exists() and site.lease_is_free()


def test_a_standing_leftover_stops_the_checker_too_and_the_doer_is_not_blamed(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done",
                                     _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
    left = site.relay_dir / "c-0123456789abcdef"

    def leave(entry) -> None:
        if entry.mode == "dispatch":
            left.mkdir()
            _refuse_removal_of(monkeypatch, left.name)

    site.runner.hooks["exit"] = leave

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == verify_holds.CHECKER_HOMES_REFUSED
    assert evidence == [] and len(site.tasks()) == 1


def test_a_relay_folder_that_cannot_be_proved_for_the_checker_is_a_login_not_ready(tmp_path):
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done",
                                     _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})

    def refuse(entry) -> None:
        if entry.mode == "dispatch":
            site.runner.relay_root_error = ProfileRefused("profile_acl_invalid", "not protected")

    site.runner.hooks["exit"] = refuse

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == "the checker's login is not ready for an isolated attempt"
    assert evidence == [] and len(site.tasks()) == 1


# -- 4. under the lease: the copy, the home, the entry ---------------------------------------


def test_a_login_that_changed_between_its_proof_and_its_copy_is_refused_and_the_lease_is_clean(
        tmp_path):
    site = Site(tmp_path, CLAUDE)
    other = claude_leaf(accessToken="fake-claude-access-token-CHANGED0000",
                        expiresAt=millis(CLOCK + LIFE))
    site.runner.hooks["acl"] = lambda home: _leaf(site, other) if home is not None else None
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "changed")
    assert site.runner.events[-1] == "acl-home", "the boundary was entered for a changed login"
    assert site.closed_leases(), "the lease did not close as a clean lease does"


def test_a_copy_that_would_carry_a_refresh_token_is_refused_and_nothing_is_started(tmp_path):
    site = Site(tmp_path, CLAUDE)
    _leaf(site, claude_leaf(
        expiresAt=millis(CLOCK + LIFE), clientId="fake-claude-refresh-token-RRRRRRRRRRRR"))
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "refresh_leak")


def test_a_relay_home_that_is_not_empty_is_refused_and_removed(tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.runner.hooks["acl"] = lambda home: (
        (home / "stowaway.txt").write_text("x", encoding="utf-8") if home is not None else None)
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "not_empty")


def test_a_relay_home_that_vanished_is_refused(tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.runner.hooks["acl"] = lambda home: shutil.rmtree(home) if home is not None else None
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "relay_unusable")


def test_a_relay_home_that_cannot_be_made_is_refused(tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.runner.hooks["acl"] = lambda home: shutil.rmtree(site.relay_root) if home is None else None
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "mint")


def test_a_project_without_a_live_owner_holds_no_lease_and_the_attempt_is_refused(tmp_path):
    site = Site(tmp_path, CLAUDE, activate=False)
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "lease")


def test_a_lease_that_names_another_folder_than_the_login_is_refused(tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    elsewhere = LeasedLogin(tmp_path / "elsewhere", (1, 2))
    monkeypatch.setattr(ProjectOwner, "leased_login", lambda self: elsewhere)
    request = site.request()

    receipt = site.run(request)
    monkeypatch.undo()  # the lease of the login is asked about as it really stands

    assert_refused_before_the_claim(site, request, receipt, "lease")


def test_an_entry_of_the_boundary_that_is_refused_starts_nothing_and_leaves_no_marker(tmp_path):
    site = Site(tmp_path, CLAUDE)
    site.runner.enter_error = ProfileRefused("profile_acl_invalid", "not the recorded object")
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "enter", entered=True)
    assert site.runner.events[-1] == "enter" and site.closed_leases()


def _raising(error: BaseException):
    """A function that refuses with `error` whatever it is asked."""
    def refuse(*arguments, **options):
        raise error
    return refuse


@pytest.mark.parametrize("error", [
    WorkspaceNotContained("the marker route is not contained"),
    OSError(13, "the marker folder may not be written"),
    OwnerRefused("ownership_lost", "the project is no longer owned by this process"),
    OwnershipError("the runner holds no such child")],
    ids=["not-contained", "os-error", "owner-refused", "runner-error"])
def test_a_claim_that_cannot_be_taken_inside_the_boundary_starts_nothing(
        error, tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    monkeypatch.setattr(HarnessWorkspace, "claim", _raising(error))
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "claim", entered=True)
    assert site.runner.events[-2:] == ["enter", "exit"]


def test_a_marker_that_cannot_be_looked_at_after_a_failed_claim_is_taken_as_standing(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)

    def refuse(self, run_id, action_id):
        monkeypatch.setattr(HarnessWorkspace, "is_claimed", _raising(
            WorkspaceNotContained("the marker route cannot be walked")))
        raise OSError(28, "no space left on the device")

    monkeypatch.setattr(HarnessWorkspace, "claim", refuse)

    receipt = site.run()

    assert receipt.detail == sentence(CLAUDE, "claim_standing")
    assert site.tasks() == [] and site.leftovers() == [] and site.lease_is_free()


def test_a_claim_that_fails_after_its_marker_was_written_says_that_the_marker_stands(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    real = Path.write_text

    def half_written(self, data, *arguments, **options):
        real(self, data, *arguments, **options)
        if self.suffix == ".marker":
            raise OSError(28, "no space left on the device")

    monkeypatch.setattr(Path, "write_text", half_written)
    request = site.request()

    receipt = site.run(request)
    monkeypatch.undo()

    assert receipt.outcome == "failed" and receipt.detail == sentence(CLAUDE, "claim_standing")
    assert reason_words(receipt.detail) == WORDS["claim_standing"]
    assert site.tasks() == [] and site.leftovers() == [] and site.lease_is_free()
    assert site.claimed(request), "the receipt speaks of a marker that does stand"
    again = site.run(request)
    assert again.outcome == "unknown", "the repeat the sentence announces as unknown"


def test_a_command_that_cannot_be_built_for_the_relay_home_is_refused_before_the_boundary(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    monkeypatch.setattr("conductor.command.adapters.relay_attempt.attempt_spec",
                        _raising(CommandSpecError("a pin that is no argv")))
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "spec")


def test_a_command_that_cannot_be_made_for_the_boundary_is_refused_before_the_claim(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    monkeypatch.setattr(
        harness_attempt, "confined_spec", _raising(CommandSpecError("a runtime that is no path")))
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "spec", entered=True)
    assert site.runner.events[-2:] == ["enter", "exit"]


def test_the_login_directory_of_a_new_sign_in_is_named_by_its_variable_and_never_by_its_path(
        tmp_path):
    site = Site(tmp_path, CODEX, life=timedelta(minutes=5))

    receipt = site.run()

    assert receipt.detail.endswith(
        '; sign in again with CODEX_HOME set to the login directory this provider pins and run '
        '-c cli_auth_credentials_store="file" login')
    assert str(site.login) not in receipt.detail and str(tmp_path) not in receipt.detail


def test_a_review_on_a_login_that_ends_too_soon_is_refused_before_its_claim(tmp_path):
    site = Site(tmp_path, CLAUDE, life=timedelta(minutes=5), **REVIEW_KNOBS)

    attempt, _store = _confirmed_review(site)

    assert attempt.state is AttemptState.FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == f"adapter reported failed: {WORDS['expiry_short']}"
    assert site.tasks() == [] and site.runner.entries == [] and site.leftovers() == []
    assert not site.claimed(attempt.request)


def test_a_review_whose_boundary_entry_is_refused_fails_before_its_claim(tmp_path):
    site = Site(tmp_path, CLAUDE, **REVIEW_KNOBS)
    site.runner.enter_error = ProfileRefused("profile_acl_invalid", "not the recorded object")

    attempt, _store = _confirmed_review(site)

    assert attempt.state is AttemptState.FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == f"adapter reported failed: {WORDS['enter']}"
    assert site.tasks() == [] and len(site.runner.entries) == 1 and site.leftovers() == []
    assert not site.claimed(attempt.request) and site.lease_is_free()


def test_the_login_of_every_refused_attempt_is_byte_for_byte_what_it_was(tmp_path):
    site = Site(tmp_path, CLAUDE)
    before = digests(site.login)
    site.runner.enter_error = ProfileRefused("profile_acl_invalid", "not the recorded object")

    site.run()

    assert len(site.runner.entries) == 1, "the road was refused before it reached the boundary"
    assert digests(site.login) == before


# -- 5. the checker: its own entry, its own claim, its own exit ---------------------------------

CHECKER_KNOBS = {_fakeclaude.WRITE_FILE: "result.txt:done",
                 _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"}


def _for_the_checker_only(error: BaseException):
    """A hook that refuses only the checker's read-only attempt, never the doer's."""
    def refuse(entry) -> None:
        if entry.mode == "review":
            raise error
    return refuse


def test_a_checker_whose_entry_is_refused_claims_nothing_and_leaves_the_lease_clean(tmp_path):
    site = Site(tmp_path, CLAUDE, **CHECKER_KNOBS)
    site.runner.hooks["enter"] = _for_the_checker_only(
        ProfileRefused("profile_acl_invalid", "not the recorded object"))

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == verify_holds.CHECKER_LOGIN_NOT_READY
    assert evidence == [] and len(site.tasks()) == 1, "the checker ran, or left evidence"
    assert [entry.mode for entry in site.runner.entries] == ["dispatch", "review"]
    assert not site.adapter.verification_started(attempt.request), "a refused entry left a marker"
    assert site.leftovers() == [] and site.lease_is_free()


def test_a_checker_that_cannot_leave_the_boundary_has_claimed_its_check_and_is_not_repeated(
        tmp_path):
    site = Site(tmp_path, CLAUDE, **CHECKER_KNOBS)
    site.runner.hooks["exit"] = _for_the_checker_only(
        ProfileRefused("profile_acl_unproven", "a token is still alive"))

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    # The checker road answers any exception of its attempt with its one closed key for it.
    assert attempt.receipt.detail == verify_holds.CHECKER_MATERIAL_UNAVAILABLE
    assert evidence == [] and len(site.tasks()) == 2, "the checker did not run"
    assert site.adapter.verification_started(attempt.request), "the check is not claimed"
    assert site.leftovers() == [] and site.lease_is_free()


#: A checker that does not start, by what is true of its marker: the sentence of the receipt,
#: spelled out (each sentence has its own closed key, `test_relay_road_words`). Without a marker
#: nothing was reserved and no marker stands (`claim_refused`); a marker that stands before the
#: claim, was written by a claim that failed, or cannot be looked at, is a check that is claimed
#: and is not repeated (`marker_standing`, Q13).
STANDING = "this action already claimed its independent checker; no second check was started"
CLAIM_NOT_TAKEN = {
    "no-marker": "the checker could not reserve its check, so nothing was started",
    "marker-before": STANDING, "marker-written": STANDING, "marker-unreadable": STANDING,
}


@pytest.mark.parametrize("case", list(CLAIM_NOT_TAKEN))
def test_a_checker_whose_claim_cannot_be_taken_starts_nothing_and_names_what_is_true(
        case, tmp_path, monkeypatch):
    words = CLAIM_NOT_TAKEN[case]
    site = Site(tmp_path, CLAUDE, **CHECKER_KNOBS)
    claim, real = HarnessWorkspace.claim, HarnessWorkspace.claim_verification

    def claimed_before(self, run_id, action_id):
        claim(self, run_id, action_id)
        real(self, run_id, action_id)  # the real marker of the check, there before the checker

    def refuse(self, run_id, action_id):
        if case == "marker-written":
            real(self, run_id, action_id)
            raise OSError(28, "no space left on the device")
        if case == "marker-unreadable":
            monkeypatch.setattr(HarnessWorkspace, "is_verification_claimed", _raising(
                WorkspaceNotContained("the marker route cannot be walked")))
            raise OSError(28, "no space left on the device")
        raise WorkspaceNotContained("the marker route is not contained")

    monkeypatch.setattr(HarnessWorkspace, "claim_verification", refuse)
    if case == "marker-before":  # the check was claimed before the checker began: not again
        monkeypatch.setattr(HarnessWorkspace, "claim", claimed_before)

    attempt, evidence = _checked_run(site, site.adapter, site.adapter, False)
    monkeypatch.undo()

    # The two sentences are told apart by their own words (`test_relay_road_words`): the sentence
    # of the receipt is the key the transport answered with.
    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == words
    assert evidence == [] and len(site.tasks()) == 1, "the checker ran, or left evidence"
    # Real markers: the one before and the one the failed claim wrote. The unreadable one is taken
    # as standing, not found, and the refused claim left none.
    assert site.adapter.verification_started(attempt.request) is (
        case in ("marker-before", "marker-written"))
    assert site.leftovers() == [] and site.lease_is_free()
