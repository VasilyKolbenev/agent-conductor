"""The refusal `project_not_active` stands in every place of the vocabulary (spec 4.3.1, 11.1).

By 11.1 the code is lane H's and lane H writes it into the vocabulary. This branch carries the
same lines, byte for byte, in the same order, so that merging the two lanes is a union of
identical lines and the words stay the owner's; it adds no wording of its own. This file is a
test of presence only: each place holds the code once (a label or a notice key written twice
would merge cleanly and silently), the status is 409 and the source is `lifecycle`. The exact
words are pinned where 11.1 puts them (`test_command_api_contracts.py`), and the doors that
refuse with the code are tested where they are built: the documents and materials routes
(`test_command_project_documents_routes.py`, `test_command_materials_routes.py`).
"""
from __future__ import annotations

import re
from pathlib import Path

from conductor.command.api_contracts import ERROR_STATUS, _FIXED_MESSAGES
from conductor.command.api_refusals import _REVIEWED_FACTS, ApiRefusal
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
CODE = "project_not_active"


def test_project_not_active_is_a_fixed_409_refusal_with_an_empty_detail():
    refusal = ApiRefusal.fixed(CODE)
    assert refusal.status == 409
    assert refusal.as_dict() == {"error": {
        "code": CODE, "message": _FIXED_MESSAGES[CODE], "detail": {}}}


def test_project_not_active_stands_in_every_place_of_the_vocabulary_that_python_can_read():
    assert ERROR_STATUS[CODE] == 409                        # place 1
    assert _FIXED_MESSAGES[CODE].strip()                    # place 2
    assert not [row for row in _REVIEWED_FACTS if row[0] == CODE], "it carries no detail"  # 3
    assert EXPECTED_ERRORS[CODE] == (409, "lifecycle")      # place 5
    assert REFUSALS[CODE] == 409                            # place 6


def test_project_not_active_stands_in_the_canon_the_labels_and_both_languages_of_the_notice():
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    row = rf'"code": "{CODE}",\s+"status": 409,\s+"source": "lifecycle"'
    assert len(re.findall(row, canon)) == 1
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert len(re.findall(rf"^  {CODE}: ", labels, re.MULTILINE)) == 1                   # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.findall(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)             # 8
    assert len(found) == 1 and all(found[0]) and found[0][0] != found[0][1]
