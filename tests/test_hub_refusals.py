"""The hub's two closed lists of refusals, held to the tables of spec 4.6.5.

`HUB_ERROR_STATUS` are the refusals a route answers before any work begins; `OPERATION_ERROR_CODES`
are the codes of a step of a long operation. The tables of the spec are typed here, group by group
and step by step, and the module is held equal to them: no code outside, none missing. Every code of
both lists has one fixed English sentence on the server and a clause in each language in the page's
catalogue (`hub-copy.js`, read under Node the way `test_hub_copy` reads it). The codes of the hub
are not codes of the command vocabulary (`ERROR_STATUS`): the eight transport names are the only
ones the two share, with the same statuses.
"""
from __future__ import annotations

import importlib
import json

import pytest

from conductor import up_flags
from conductor.command.api_refusals import ERROR_STATUS as COMMAND_STATUS
from conductor.hub import lifecycle, refusals
from tests.desk_wizard_node import run_js

#: `HUB_ERROR_STATUS` of spec 4.6.5, group by group: (status, codes).
ROUTE_GROUPS = (
    (403, ("same_origin_denied", "csrf_denied")),
    (400, ("malformed_request",)),
    (404, ("route_not_found",)),
    (405, ("method_not_allowed",)),
    (422, ("contract_invalid", "windows_name_unsafe", "windows_path_too_long",
           "name_invalid", "folder_invalid", "repo_invalid")),
    (404, ("project_not_found", "operation_not_found", "pick_not_found", "login_not_found",
           "candidate_not_found")),
    (409, ("pick_invalid", "legacy_writers_unconfirmed", "folder_exists", "projects_home_invalid",
           "review_harness_missing", "operation_busy", "registry_busy", "registry_invalid",
           "dialog_busy", "dialog_unavailable", "profile_absent", "profile_invalid")),
    (409, ("git_not_pinned", "gh_not_pinned", "git_changed", "gh_changed", "git_too_old",
           "tool_version_unreadable", "gh_not_logged_in", "gh_unreachable", "gh_failed")),
    (409, ("project_busy", "project_running", "project_not_running", "project_unavailable",
           "already_active", "active_not_closed", "recovery_required", "recover_not_needed",
           "operation_not_cancellable", "project_queue_changed", "hub_in_kill_on_close_job")))
TRANSPORT = ("same_origin_denied", "csrf_denied", "malformed_request", "route_not_found",
             "method_not_allowed", "contract_invalid", "windows_name_unsafe",
             "windows_path_too_long")
#: `OPERATION_ERROR_CODES` of spec 4.6.5 by step. The `start` row is the list of `state_code`s.
OPERATION_STEPS = {
    "clone": ("projects_home_invalid", "folder_exists", "gh_not_pinned", "gh_changed",
              "gh_not_logged_in", "gh_unreachable", "gh_failed", "clone_timeout", "clone_failed",
              "clone_cleanup_incomplete"),
    "admit": ("root_invalid", "root_too_broad", "root_nested", "root_in_login_home",
              "root_already_registered", "root_path_too_long", "windows_name_unsafe",
              "conduct_home_invalid", "name_invalid"),
    "git": ("git_not_pinned", "git_changed", "git_too_old", "tool_version_unreadable",
            "project_not_repo_root", "tracks_product_dir"),
    "init_activate": ("legacy_writers_must_stop", "unsettled_action", "recovery_required",
                      "transition_conflict", "activation_present", "inventory_bound"),
    "exclude": ("git_exclude_failed",),
    "register": ("ports_exhausted", "registry_busy", "registry_invalid"),
    "providers": ("profile_absent", "profile_invalid", "owner_busy"),
    "drain": ("stop_uncertain",),
    "recover": ("recovery_required", "recovery_refused", "transition_conflict", "ownership_lost"),
    "recover_login": ("login_recovery_required", "login_owner_busy", "login_ownership_invalid",
                      "login_context_required"),
    "any": ("subprocess_failed",)}
#: The `state_code` list of 4.1.5: the start table and the two codes the hub adds.
START_CODES = frozenset(up_flags.START_CODES) | {"start_timeout", "active_not_closed"}


def _operation_codes() -> set[str]:
    return {code for codes in OPERATION_STEPS.values() for code in codes} | START_CODES


def test_the_route_refusals_are_exactly_the_48_codes_of_the_spec_with_their_statuses():
    wanted = {code: status for status, codes in ROUTE_GROUPS for code in codes}
    assert len(wanted) == 48
    assert dict(refusals.HUB_ERROR_STATUS) == wanted


def test_the_operation_codes_are_the_table_of_the_spec_by_step_and_nothing_else():
    assert {step: tuple(codes) for step, codes in refusals.OPERATION_CODES_BY_STEP.items()
            if step != "start"} == OPERATION_STEPS
    assert set(refusals.OPERATION_ERROR_CODES) == _operation_codes()
    assert len(_operation_codes()) == 61


def test_status_unreadable_is_a_state_code_but_not_yet_a_code_of_the_start_step():
    """The page has no clause for it yet (`test_hub_copy` holds the operation list inside its own
    typed table), so the `start` row is the spec's list and the new state code waits for D2."""
    assert "status_unreadable" in lifecycle.STATE_CODES
    assert "status_unreadable" not in refusals.OPERATION_ERROR_CODES
    assert set(refusals.OPERATION_CODES_BY_STEP["start"]) == START_CODES
    assert set(lifecycle.STATE_CODES) - START_CODES == {"status_unreadable"}


def test_every_code_of_both_lists_has_one_fixed_message_and_no_message_lacks_a_code():
    codes = set(refusals.HUB_ERROR_STATUS)
    assert set(refusals.hub_messages()) == codes
    for code in sorted(codes):
        message = refusals.hub_messages()[code]
        assert message and message == message.strip() and message.isascii(), code
        assert "_" not in message, f"{code}: a message that says a raw code"
    assert len(set(refusals.hub_messages().values())) == len(codes), "two codes share a sentence"


def _catalogue() -> dict[str, list[str]]:
    return run_js("console.log(JSON.stringify(copy.HUB_COPY));", None,
                  modules={"copy": "hub-copy.js"})


def test_every_code_of_both_lists_has_a_russian_and_an_english_clause_in_the_page_catalogue():
    rows = _catalogue()
    for code in sorted(set(refusals.HUB_ERROR_STATUS) | set(refusals.OPERATION_ERROR_CODES)):
        pair = rows.get(f"hub.code.{code}")
        assert pair and len(pair) == 2 and all(pair), f"hub.code.{code} is missing or empty"
        assert pair[0] != pair[1], f"hub.code.{code} is the same in both languages"


def test_a_refusal_is_the_envelope_of_code_message_and_detail_with_its_own_status():
    refusal = refusals.HubRefusal("project_busy", {"project_id": "a" * 32})
    assert refusal.status == 409
    assert refusal.as_dict() == {"error": {
        "code": "project_busy", "message": refusals.hub_messages()["project_busy"],
        "detail": {"project_id": "a" * 32}}}
    assert json.loads(json.dumps(refusal.as_dict())) == refusal.as_dict()
    bare = refusals.HubRefusal("route_not_found")
    assert bare.as_dict()["error"]["detail"] == {} and bare.status == 404


def test_a_code_outside_the_lists_cannot_be_built():
    for code in ("not_a_code", "project_not_found ", "", "name_taken", "tool_changed",
                 "projects_home_unset", "gh_unpinned", "clone_failed"):
        with pytest.raises(ValueError):
            refusals.HubRefusal(code)


def test_a_detail_that_could_carry_an_absolute_path_or_more_than_a_short_word_cannot_be_built():
    for detail in ({"folder": "C:\\Users\\me\\web"}, {"folder": "/home/me/web"},
                   {"folder": "\\\\host\\share\\x"}, {"reason": "x" * 201}, {"": "x"},
                   {"n": 3}, {"path": None}):
        with pytest.raises(ValueError):
            refusals.HubRefusal("folder_invalid", detail)
    refusals.HubRefusal("folder_invalid", {"reason": "web-app", "field": "folder"})


def test_the_hub_codes_are_not_the_command_vocabulary_except_the_eight_transport_names():
    shared = {code for code in refusals.HUB_ERROR_STATUS if code in COMMAND_STATUS}
    assert shared == set(TRANSPORT)
    for code in shared:
        assert refusals.HUB_ERROR_STATUS[code] == COMMAND_STATUS[code], code
    assert set(refusals.HUB_ERROR_STATUS) - shared, "control: the hub has codes of its own"


def test_every_code_projects_add_prints_is_a_code_of_the_operation_list():
    try:
        projects_add = importlib.import_module("conductor.hub.projects_add")
    except ModuleNotFoundError as error:
        if error.name != "conductor.hub.projects_add":
            raise
        pytest.skip("conduct projects add is not written yet (a later slice of lane H)")
    printed = set(projects_add.REFUSAL_CODES)
    assert printed <= set(refusals.OPERATION_ERROR_CODES), sorted(
        printed - set(refusals.OPERATION_ERROR_CODES))
