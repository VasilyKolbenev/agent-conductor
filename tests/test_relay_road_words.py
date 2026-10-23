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
    COMMAND, HOME_ENV, PHRASES, RE_LOGIN, WORDS, sentence)


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
