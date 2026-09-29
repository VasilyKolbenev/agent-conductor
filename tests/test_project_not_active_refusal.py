"""The refusal `project_not_active` in every place of the vocabulary (spec 4.3.1, 9.1.6, 11.1).

A server started in `view` mode creates no child process, git included, so a door that needs git
or starts work says so with this word: the request is well formed and there is nothing to correct,
the project has to be made active first. By 11.1 the code is lane H's; it is introduced here, by
the lane whose routes (the documents of the project) refuse with it first, and lane H's own doors
(`authorize`, `resume`) will find it standing. It carries no detail, so it has no reviewed-fact
row. The doors that refuse with it are tested where they are: the documents routes of
`test_command_project_documents.py`.
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
    assert re.search(rf'"code": "{CODE}",\s+"status": 409,\s+"source": "lifecycle"', canon)
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert re.search(rf"^  {CODE}: ", labels, re.MULTILINE)                              # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.search(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)              # 8
    assert found and all(found.groups()) and found.group(1) != found.group(2)
