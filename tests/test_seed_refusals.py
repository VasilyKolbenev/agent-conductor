"""The refusals `seed_refused` and `tool_unavailable` in every place of 11.1.

Spec 9.1.3 and 9.3 give two codes that carry a detail: a refused seed names one reason of a closed
list of fourteen (and the commit, for the two reasons that have one); an unusable tool names which
tool and one of three reasons. A new code goes into EVERY place of the vocabulary in one commit, and
`tool_unavailable` is the first code outside `{400, 403, 404, 405, 409, 422, 500}` (503), so the
freeze's status set widens in the same commit. This file is the "test of the code" that names each
place readable from Python or from a file, and walks the one door that refuses today: the project's
documents door, where a pinned tool that is gone used to read as a broken run store. The seed door
itself arrives with the seed route and is tested there.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from conductor import server_git
from conductor.command import api_refusals
from conductor.command.api_contracts import ERROR_STATUS, _FIXED_MESSAGES, ApiRefusal
from conductor.command.api_refusals import (
    SEED_COMMIT_REASONS, SEED_REASONS, TOOL_REASONS, TOOLS, _REFUSAL_BUILD, _REVIEWED_FACTS)
from conductor.command.project_git import GitReadFailed
from tests.alpha1_live_extensions import REFUSALS
from tests.git_repo_helpers import needs_git
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS
from tests.test_command_materials_routes import Project
from tests.test_command_project_doors import DOCS, code_of, request

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
#: The code, its status and the source the canon document gives it.
CODES = {"seed_refused": (409, "service"), "tool_unavailable": (503, "service")}
COMMIT = "ab" * 20


def test_the_seed_reasons_are_the_fourteen_of_spec_9_1_3_in_its_order():
    assert SEED_REASONS == (
        "not_a_git_repository", "unborn_head", "project_not_repo_root", "tracks_product_dir",
        "empty_not_allowed", "base_moved", "seed_exists", "work_not_empty", "seed_lost",
        "seed_too_large", "too_many_skips", "case_collision", "git_failed", "git_timed_out")
    assert SEED_COMMIT_REASONS == ("base_moved", "seed_exists")


def test_the_tool_words_are_git_and_gh_and_the_three_reasons_the_reader_already_says():
    assert TOOLS == ("git", "gh")
    assert TOOL_REASONS == ("not_pinned", "version_changed", "missing")
    assert tuple(server_git.REASONS) == TOOL_REASONS


@pytest.mark.parametrize("reason", SEED_REASONS)
def test_a_seed_refusal_is_409_and_names_its_reason_and_nothing_else(reason):
    refusal = ApiRefusal.seed_refused(reason)
    assert (refusal.status, dict(refusal.detail)) == (409, {"reason": reason})
    assert refusal.message == f"the work folder was not seeded: {reason}"
    assert refusal.as_dict() == {"error": {"code": "seed_refused", "message": refusal.message,
                                           "detail": {"reason": reason}}}


@pytest.mark.parametrize("reason", SEED_COMMIT_REASONS)
def test_a_moved_base_and_a_standing_seed_name_the_commit_that_explains_them(reason):
    refusal = ApiRefusal.seed_refused(reason, COMMIT)
    assert dict(refusal.detail) == {"reason": reason, "commit": COMMIT}
    assert refusal.message == f"the work folder was not seeded: {reason} at {COMMIT}"


@pytest.mark.parametrize("reason", [r for r in SEED_REASONS if r not in SEED_COMMIT_REASONS])
def test_a_reason_with_no_commit_to_name_refuses_to_be_given_one(reason):
    with pytest.raises(ValueError, match="commit"):
        ApiRefusal.seed_refused(reason, COMMIT)


@pytest.mark.parametrize("commit", ["HEAD", "abc", COMMIT.upper(), "ab" * 20 + "\n", 7])
def test_a_commit_that_is_not_an_object_id_is_a_fault_of_the_caller(commit):
    with pytest.raises(ValueError, match="commit"):
        ApiRefusal.seed_refused("base_moved", commit)


@pytest.mark.parametrize("reason", ["", "base_movedd", "seed_blocked", None, 3])
def test_a_seed_reason_outside_the_closed_list_is_a_fault_of_the_caller(reason):
    with pytest.raises(ValueError, match="reason"):
        ApiRefusal.seed_refused(reason)


@pytest.mark.parametrize("tool, reason", list(itertools.product(TOOLS, TOOL_REASONS)))
def test_a_tool_refusal_is_503_and_names_the_tool_and_why(tool, reason):
    refusal = ApiRefusal.tool_unavailable(tool, reason)
    assert (refusal.status, dict(refusal.detail)) == (503, {"tool": tool, "reason": reason})
    assert refusal.message == f"{tool} cannot be used: {reason}"


@pytest.mark.parametrize("tool, reason", [("hg", "missing"), ("git", "gone"), ("", ""),
                                          ("git", None), (None, "missing")])
def test_a_tool_or_a_reason_outside_the_closed_lists_is_a_fault_of_the_caller(tool, reason):
    with pytest.raises(ValueError):
        ApiRefusal.tool_unavailable(tool, reason)


@pytest.mark.parametrize("code", CODES)
def test_a_refusal_of_either_code_with_a_detail_no_reviewed_row_names_is_refused(code):
    with pytest.raises(ValueError, match="reviewed"):
        ApiRefusal(_REFUSAL_BUILD, code, "whatever", {"reason": "base_moved", "tool": "git"})
    with pytest.raises(ValueError, match="reviewed"):
        ApiRefusal(_REFUSAL_BUILD, code, "another sentence", {"reason": "base_moved"})


def test_each_detail_the_two_codes_carry_has_its_own_reviewed_row():
    rows = {(code, tuple(fields)) for code, fields, _sentence in _REVIEWED_FACTS}
    assert {("seed_refused", ("reason",)), ("seed_refused", ("reason", "commit")),
            ("tool_unavailable", ("tool", "reason"))} <= rows


@pytest.mark.parametrize("code", CODES)
def test_a_bare_refusal_of_either_code_reads_its_vocabulary_sentence_and_no_detail(code):
    refusal = ApiRefusal.fixed(code)
    assert (refusal.status, dict(refusal.detail)) == (CODES[code][0], {})
    assert refusal.message == _FIXED_MESSAGES[code] and refusal.message.strip()


def test_the_two_vocabulary_sentences_are_two_different_sentences():
    assert _FIXED_MESSAGES["seed_refused"] != _FIXED_MESSAGES["tool_unavailable"]


# --- 11.1: each code stands in every place of the vocabulary --------------------------------------


@pytest.mark.parametrize("code, row", CODES.items())
def test_a_code_stands_in_every_place_of_the_vocabulary_python_can_read(code, row):
    status, source = row
    assert ERROR_STATUS[code] == status                    # place 1
    assert _FIXED_MESSAGES[code].strip()                   # place 2
    assert EXPECTED_ERRORS[code] == (status, source)       # place 5
    assert REFUSALS[code] == status                        # place 6


@pytest.mark.parametrize("code, row", CODES.items())
def test_a_code_stands_in_the_canon_the_labels_and_both_languages_of_the_notice(code, row):
    status, source = row
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{code}",\s+"status": {status},\s+"source": "{source}"', canon)
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert len(re.findall(rf"^  {code}: ", labels, re.MULTILINE)) == 1                   # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.findall(rf'"error\.{code}": \["([^"]+)", "([^"]+)"\]', notice)             # 8
    assert len(found) == 1 and all(found[0]) and found[0][0] != found[0][1]


def test_the_freeze_admits_the_one_status_outside_its_old_set_that_a_code_now_uses():
    freeze = (REPO / "tests" / "test_cockpit_command_api_freeze.py").read_text(encoding="utf-8")
    assert "{400, 403, 404, 405, 409, 422, 500, 503}" in freeze
    assert {status for status, _source in EXPECTED_ERRORS.values()} - {
        400, 403, 404, 405, 409, 422, 500} == {503}
    assert api_refusals.ERROR_STATUS["tool_unavailable"] == 503


# --- the door that refuses today: the project documents ----------------------------------------


class Gone:
    """A reader whose pinned tool is unusable, as the server's own reader raises it."""

    def __init__(self, failure):
        self.failure = failure

    def __call__(self, args, separate_stderr=False):
        raise self.failure


@needs_git
@pytest.mark.parametrize("reason", TOOL_REASONS)
def test_the_documents_door_answers_503_naming_git_and_the_reason_the_reader_gave(
        tmp_path, reason):
    project = Project(tmp_path, reader=Gone(server_git.ToolUnavailable(reason)))
    answer = request(project, "GET", DOCS)
    assert code_of(answer) == (503, "tool_unavailable")
    assert answer.payload["error"]["detail"] == {"tool": "git", "reason": reason}


@needs_git
@pytest.mark.parametrize("failure", [GitReadFailed("git_failed", 128),
                                     GitReadFailed("git_timed_out")])
def test_the_documents_door_still_answers_store_error_for_a_git_that_ran_and_failed(
        tmp_path, failure):
    project = Project(tmp_path, reader=Gone(failure))
    assert code_of(request(project, "GET", DOCS)) == (500, "store_error")
