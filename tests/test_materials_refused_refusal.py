"""The refusal `materials_refused` in every place of the vocabulary (spec 6.2.3, 9.5, 11.1).

A materials list the server will not turn into a document is refused with one code whose detail
is one word from a closed list: the composer's six reasons (`command/materials.py`) and the one
only the seed's own record can give, `doc_not_seeded`. The list is closed in the factory, so a
reason that is not on it can never be rendered into a browser, and it is compared with the
composer's own list in both directions, so a reason added there is a red test here. The doors that
refuse with it are tested where they are: `test_command_materials_routes.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conductor.command import materials
from conductor.command.api_contracts import ERROR_STATUS, _FIXED_MESSAGES
from conductor.command.api_refusals import (
    _REFUSAL_BUILD, _REVIEWED_FACTS, MATERIALS_REASONS, ApiRefusal)
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
CODE = "materials_refused"


def test_the_reasons_are_the_composers_six_and_doc_not_seeded_and_no_other():
    assert set(MATERIALS_REASONS) == set(materials.REFUSALS) | {"doc_not_seeded"}
    assert len(MATERIALS_REASONS) == len(set(MATERIALS_REASONS)) == 7


@pytest.mark.parametrize("reason", MATERIALS_REASONS)
def test_a_materials_refusal_is_409_and_names_its_reason_and_nothing_else(reason):
    refusal = ApiRefusal.materials_refused(reason)
    assert refusal.status == 409
    assert refusal.as_dict() == {"error": {
        "code": CODE, "message": f"the materials were not accepted: {reason}",
        "detail": {"reason": reason}}}


@pytest.mark.parametrize("reason", ["", "no_such_reason", "Too Many", None, 3, "doc_unknown "])
def test_a_reason_off_the_closed_list_cannot_be_built_into_a_refusal(reason):
    with pytest.raises(ValueError):
        ApiRefusal.materials_refused(reason)


def test_the_reviewed_fact_of_the_code_is_its_reason_and_no_other_shape_passes():
    reason = MATERIALS_REASONS[0]
    with pytest.raises(ValueError):
        ApiRefusal(_REFUSAL_BUILD, CODE, "some other words", {"reason": reason})
    with pytest.raises(ValueError):
        ApiRefusal(_REFUSAL_BUILD, CODE, f"the materials were not accepted: {reason}",
                   {"reason": reason, "path": "docs/a.md"})
    with pytest.raises(ValueError):
        ApiRefusal(_REFUSAL_BUILD, CODE, f"the materials were not accepted: {reason}",
                   {"reason": "a reason with spaces!"})


def test_the_fixed_sentence_of_the_code_is_the_vocabulary_complete_one():
    refusal = ApiRefusal.fixed(CODE)
    assert (refusal.status, dict(refusal.detail)) == (409, {})
    assert refusal.message == _FIXED_MESSAGES[CODE]


# --- 11.1: the code stands in every place of the vocabulary ---------------------------------------


def test_materials_refused_stands_in_every_place_of_the_command_vocabulary_python_can_read():
    assert ERROR_STATUS[CODE] == 409                        # place 1
    assert _FIXED_MESSAGES[CODE].strip()                    # place 2
    assert any(row[0] == CODE and row[1] == ("reason",) for row in _REVIEWED_FACTS)  # place 3
    assert EXPECTED_ERRORS[CODE] == (409, "service")        # place 5
    assert REFUSALS[CODE] == 409                            # place 6


def test_materials_refused_stands_in_the_canon_the_labels_and_both_languages_of_the_notice():
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{CODE}",\s+"status": 409,\s+"source": "service"', canon)  # 4
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert re.search(rf"^  {CODE}: ", labels, re.MULTILINE)                              # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.search(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)              # 8
    assert found and all(found.groups()) and found.group(1) != found.group(2)
