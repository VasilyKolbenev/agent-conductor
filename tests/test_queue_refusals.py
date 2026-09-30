"""The refusals `queue_changed`, `queue_full` and `queue_not_ready` in every place of 11.1.

Spec 4.4.7: three codes the project queue introduces, each a 409 with a fixed sentence and no
detail (the reason a run is not ready is read from the preparation, not from the refusal). A new
code goes into EVERY place of the vocabulary in one commit; this file is the "test of the code"
that names each place readable from Python or from a file. The doors that refuse with them are
tested where they are: `test_command_queue.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conductor.command.api_contracts import ERROR_STATUS, _FIXED_MESSAGES, ApiRefusal
from conductor.command.api_refusals import _REVIEWED_FACTS
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
#: The code, and the source the canon document gives it.
CODES = {"queue_changed": "concurrency", "queue_full": "service", "queue_not_ready": "plan"}


@pytest.mark.parametrize("code", CODES)
def test_a_queue_refusal_is_409_with_its_fixed_sentence_and_no_detail(code):
    refusal = ApiRefusal.fixed(code)
    assert (refusal.status, dict(refusal.detail)) == (409, {})
    assert refusal.message == _FIXED_MESSAGES[code] and refusal.message.strip()
    assert refusal.as_dict() == {"error": {"code": code, "message": refusal.message,
                                           "detail": {}}}


def test_the_three_sentences_are_three_different_sentences():
    assert len({_FIXED_MESSAGES[code] for code in CODES}) == 3


@pytest.mark.parametrize("code", CODES)
def test_no_queue_code_is_a_reviewed_fact_because_none_of_them_carries_a_detail(code):
    assert not any(row[0] == code for row in _REVIEWED_FACTS)


# --- 11.1: the code stands in every place of the vocabulary ---------------------------------------


@pytest.mark.parametrize("code, source", CODES.items())
def test_a_queue_code_stands_in_every_place_of_the_vocabulary_python_can_read(code, source):
    assert ERROR_STATUS[code] == 409                       # place 1
    assert _FIXED_MESSAGES[code].strip()                   # place 2
    assert EXPECTED_ERRORS[code] == (409, source)          # place 5
    assert REFUSALS[code] == 409                           # place 6


@pytest.mark.parametrize("code, source", CODES.items())
def test_a_queue_code_stands_in_the_canon_the_labels_and_both_languages_of_the_notice(
        code, source):
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{code}",\s+"status": 409,\s+"source": "{source}"', canon)  # 4
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert len(re.findall(rf"^  {code}: ", labels, re.MULTILINE)) == 1                   # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.findall(rf'"error\.{code}": \["([^"]+)", "([^"]+)"\]', notice)             # 8
    assert len(found) == 1 and all(found[0]) and found[0][0] != found[0][1]
