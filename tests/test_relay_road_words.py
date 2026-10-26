"""The sentences a refused relay attempt writes, and the words the runtime gives them (I2b).

A transport writes a fixed sentence per refusal; the runtime never forwards it, it recognizes a
fragment and answers with its own closed words (`failure_reasons`). So the table has to hold, for
every refusal of the relay road, a fragment the transport really writes and words no other refusal
shares, and it has to stand after the two rows an observed outcome earns, so that a sentence about
what a child did is never shadowed by a sentence about why none was started. The checker has one
closed key of its own for it (`login_not_ready`), so that a login that is not ready is not reported
as a build that failed its preflight.

The sentences and the words are the literals of `tests/test_relay_road_refusals.py`; they are asked
of the transport through the receipts there, and here the whole table is asked at once.
"""
from __future__ import annotations

import pytest

from conductor.command import verify_holds, verify_road
from conductor.command.adapters import independent_check
from conductor.command.adapters.base import AdapterVerification
from conductor.command.adapters.login_relay import REFUSALS
from conductor.command.failure_reasons import REASONS, reason_words

from tests.relay_roads import CLAUDE, CODEX
from tests.test_relay_road_refusals import (
    COMMAND, HOME_ENV, NOT_THE_LOGIN, PHRASES, RE_LOGIN, WORDS, sentence)


def test_the_phrases_this_suite_spells_are_the_ones_the_product_writes_for_every_login_refusal():
    assert {code: PHRASES[code] for code in REFUSALS} == dict(REFUSALS)


@pytest.mark.parametrize("code", sorted(PHRASES))
def test_every_refusal_sentence_earns_the_words_the_runtime_owns(code):
    from conductor.command.adapters.relay_attempt import refusal_sentence

    for vendor in (CLAUDE, CODEX):
        said = refusal_sentence(vendor.tool, code, COMMAND[vendor], HOME_ENV[vendor])
        assert said == sentence(vendor, code)
        assert reason_words(said) == WORDS[code]
        if code not in RE_LOGIN:
            assert HOME_ENV[vendor] not in said, "only a new sign-in names the login variable"


#: The sentences of the refusals that are not about the login, spelled out for Claude Code, whole.
NOT_THE_LOGIN_SENTENCES = {
    "mint": "the Claude Code attempt could not start in isolation: the relay home of the attempt "
            "could not be made, so no task was spawned",
    "spec": "the Claude Code attempt could not start in isolation: the command of the attempt "
            "could not be built for its relay home, so no task was spawned",
    "enter": "the Claude Code attempt could not start in isolation: the execution boundary "
             "refused the relay home of the attempt, so no task was spawned",
    "claim": "the Claude Code attempt could not start in isolation: the action could not be "
             "claimed for the attempt, so no task was spawned",
    "claim_standing": "the Claude Code attempt could not start in isolation: the claim of the "
                      "action could not be completed but its marker stands, and a repeat of the "
                      "action is unknown, so no task was spawned",
}
#: And two of the refusals about the login, whose words are not changed.
LOGIN_SENTENCES = {
    "acl": "the Claude Code login is not ready for an isolated attempt: a folder of the login or "
           "of its relay is open to an isolated child, so no task was spawned",
    "lease": "the Claude Code login is not ready for an isolated attempt: the login lease of the "
             "attempt does not name this login, so no task was spawned",
}


@pytest.mark.parametrize("code", sorted(NOT_THE_LOGIN_SENTENCES))
def test_a_refusal_that_is_not_about_the_login_says_the_attempt_could_not_start_in_isolation(code):
    from conductor.command.adapters.relay_attempt import refusal_sentence

    said = refusal_sentence("Claude Code", code, "auth login --claudeai", "CLAUDE_CONFIG_DIR")

    assert said == NOT_THE_LOGIN_SENTENCES[code]
    assert "login is not ready" not in said
    assert reason_words(said) == WORDS[code], "the runtime's words follow the phrase, not the head"


@pytest.mark.parametrize("code", sorted(LOGIN_SENTENCES))
def test_a_refusal_about_the_login_or_its_folders_still_says_the_login_is_not_ready(code):
    from conductor.command.adapters.relay_attempt import refusal_sentence

    said = refusal_sentence("Claude Code", code, "auth login --claudeai", "CLAUDE_CONFIG_DIR")

    assert said == LOGIN_SENTENCES[code]
    assert "could not start in isolation" not in said


def test_the_refusals_that_are_not_about_the_login_are_exactly_the_five_of_the_attempt():
    """Every code of the closed table is one or the other, and the five are named here by hand:
    the set the product holds is the one this suite spells, and it names only codes the attempt
    itself owns (none of the login's own refusals)."""
    from conductor.command.adapters.login_relay import REFUSALS
    from conductor.command.adapters.relay_attempt import NOT_THE_LOGIN as PRODUCT_SET, OWN_PHRASES

    assert sorted(PRODUCT_SET) == sorted(NOT_THE_LOGIN) == sorted(NOT_THE_LOGIN_SENTENCES)
    assert set(PRODUCT_SET) <= set(OWN_PHRASES) and not set(PRODUCT_SET) & set(REFUSALS)
    others = sorted(set(PHRASES) - set(NOT_THE_LOGIN))
    assert len(others) == 25 and len(PHRASES) == 30


def test_no_two_refusals_share_their_words_and_none_names_a_path_or_a_vendor_value():
    assert len(set(WORDS.values())) == len(WORDS) == len(PHRASES)
    for words in WORDS.values():
        assert "\\" not in words and "/" not in words and "{" not in words
    kept = [words for fragment, words in REASONS if fragment in set(PHRASES.values())]
    assert sorted(kept) == sorted(WORDS.values()), "the table of the product is not this one"


def test_the_relay_rows_stand_after_the_rows_of_what_a_child_did():
    fragments = [fragment for fragment, _words in REASONS]
    after = max(fragments.index("exceeded its timeout"),
                fragments.index("was observed to exit non-zero"))

    assert [code for code, phrase in PHRASES.items() if fragments.index(phrase) <= after] == []


def test_a_sentence_of_what_a_child_did_is_never_taken_for_a_refusal():
    assert reason_words("the Claude Code prompt exceeded its timeout and was terminated") == (
        "it exceeded its timeout")
    assert reason_words("the Claude Code prompt was observed to exit non-zero") == (
        "the process exited non-zero")


#: The whole closed set of reasons a checker's transport may answer with, spelled out: a new one
#: is a decision, and is added here by hand together with its words (`verify_road.CHECK_REASONS`).
CHECKER_REASONS = frozenset({
    "verified", "homes_refused", "preflight_refused", "marker_standing", "claim_refused",
    "no_verdict", "tree_changed", "rejected", "frame_over_limit", "frame_env_echo",
    "material_unavailable", "login_residue", "rejected_findings_refused", "snapshot_damaged",
    "object_format_changed", "base_missing", "reserved_path", "irregular_result",
    "result_too_large", "unportable_name", "case_collision", "boundary_unavailable",
    "login_not_ready"})
MARKER_STANDING_WORDS = (
    "this action already claimed its independent checker; no second check was started")
CLAIM_REFUSED_WORDS = "the checker could not reserve its check, so nothing was started"


def _checker_answer(reason: str) -> AdapterVerification:
    return AdapterVerification(
        adapter_id="claude-code", action_id="act-1", state="error",
        observed_at="2026-08-22T12:00:00Z", detail=reason, evidence_refs=())


def test_a_checker_that_could_not_reserve_its_check_is_not_one_whose_marker_stands():
    """Two refusals, two keys, two sentences: a claim refused leaves no marker, so it never says
    that the action already claimed its check (Q13)."""
    assert verify_road.check_reason(_checker_answer("claim_refused"), "default") == (
        CLAIM_REFUSED_WORDS)
    assert verify_road.check_reason(_checker_answer("marker_standing"), "default") == (
        MARKER_STANDING_WORDS)
    assert verify_holds.CHECKER_CLAIM_REFUSED == CLAIM_REFUSED_WORDS
    assert verify_holds.CHECKER_MARKER_STANDING == MARKER_STANDING_WORDS
    assert independent_check.CheckFrameError("claim_refused").reason == "claim_refused"
    assert "marker" not in CLAIM_REFUSED_WORDS and "already" not in CLAIM_REFUSED_WORDS


def test_the_closed_set_of_checker_reasons_has_words_for_every_reason_it_answers_with():
    assert independent_check.REASONS == CHECKER_REASONS
    assert {reason for _state, reason in verify_road.CHECK_REASONS} <= CHECKER_REASONS
    assert len(set(verify_road.CHECK_REASONS.values())) == len(verify_road.CHECK_REASONS)
    assert ("error", "claim_refused") in verify_road.CHECK_REASONS
    assert ("error", "marker_standing") in verify_road.CHECK_REASONS


def test_a_checker_whose_login_is_not_ready_has_a_closed_key_and_a_sentence_of_its_own():
    verification = AdapterVerification(
        adapter_id="claude-code", action_id="act-1", state="error",
        observed_at="2026-08-22T12:00:00Z", detail="login_not_ready", evidence_refs=())

    assert "login_not_ready" in independent_check.REASONS
    assert independent_check.CheckFrameError("login_not_ready").reason == "login_not_ready"
    assert verify_holds.CHECKER_LOGIN_NOT_READY == (
        "the checker's login is not ready for an isolated attempt")
    assert verify_road.check_reason(verification, "default") == (
        "the checker's login is not ready for an isolated attempt")
    assert verify_holds.CHECKER_LOGIN_NOT_READY != verify_holds.CHECKER_PREFLIGHT_REFUSED
