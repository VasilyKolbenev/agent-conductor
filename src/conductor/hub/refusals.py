"""The hub's two closed lists of refusals (spec 4.6.5), apart from the command vocabulary.

`HUB_ERROR_STATUS` are the refusals a route answers before it starts any work, each with its HTTP
status; `OPERATION_ERROR_CODES` are the codes of a step of a long operation (`code` of an operation,
4.6.4). They are not the codes of `/command/*` (`ERROR_STATUS`, the canon, the desk's labels): the
desk and the hub are different surfaces, and only the eight transport names are spelled the same,
with the same statuses. Words for a person are the page's (`hub-copy.js`, both languages); the
sentence here is the fixed English one the envelope carries.

The envelope is the commands' one, `{"error": {"code", "message", "detail"}}`. `detail` is a small
map of short words (an id, a reason): never an absolute path and never text a caller sent, because
the hub shows the last folder name and nothing more of a path (4.6.2).
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from conductor.hub import lifecycle

_ROUTE_GROUPS = (
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

#: The refusals of a route, by code, with the HTTP status of each: a closed list.
HUB_ERROR_STATUS: Mapping[str, int] = MappingProxyType(
    {code: status for status, codes in _ROUTE_GROUPS for code in codes})

#: The `start` step's codes are the `state_code` list of 4.1.5 (the start table and the two codes
#: the hub adds). `status_unreadable` is a `state_code` too (lifecycle) and is left out of this row
#: on purpose until the page has a clause for it (`tests/test_hub_copy.py` holds the operation list
#: inside its own typed table): the handoff to lane D2 names it, and the test that pins this
#: says why.
_START_STEP = tuple(sorted(lifecycle.STATE_CODES - {"status_unreadable"}))

#: The codes of a failed step of an operation, by step (4.6.5).
OPERATION_CODES_BY_STEP: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "clone": ("projects_home_invalid", "folder_exists", "gh_not_pinned", "gh_changed",
              "gh_not_logged_in", "gh_unreachable", "gh_failed", "clone_timeout", "clone_failed",
              "clone_cleanup_incomplete"),
    "admit": ("root_invalid", "root_too_broad", "root_nested", "root_in_login_home",
              "root_already_registered", "root_path_too_long", "windows_name_unsafe",
              "conduct_home_invalid"),
    "git": ("git_not_pinned", "git_changed", "git_too_old", "tool_version_unreadable",
            "project_not_repo_root", "tracks_product_dir"),
    "init_activate": ("legacy_writers_must_stop", "unsettled_action", "recovery_required",
                      "transition_conflict", "activation_present", "inventory_bound"),
    "exclude": ("git_exclude_failed",),
    "register": ("ports_exhausted", "registry_busy", "registry_invalid"),
    "providers": ("profile_absent", "profile_invalid", "owner_busy"),
    "drain": ("stop_uncertain",),
    "start": _START_STEP,
    "recover": ("recovery_required", "recovery_refused", "transition_conflict", "ownership_lost"),
    "recover_login": ("login_recovery_required", "login_owner_busy", "login_ownership_invalid",
                      "login_context_required"),
    "any": ("subprocess_failed",)})

#: Every code a step of an operation can fail with: a closed list.
OPERATION_ERROR_CODES = frozenset(
    code for codes in OPERATION_CODES_BY_STEP.values() for code in codes)

_HUB_MESSAGES: Mapping[str, str] = MappingProxyType({
    "same_origin_denied": "the request does not come from this hub's own page",
    "csrf_denied": "the request does not carry this hub's current token",
    "malformed_request": "the request is not one JSON object in the form this hub accepts",
    "route_not_found": "this hub has no such route",
    "method_not_allowed": "this route does not take that method",
    "contract_invalid": "the body does not have exactly the fields this route takes",
    "windows_name_unsafe": "the name is one Windows does not allow for a folder",
    "windows_path_too_long": "the folder's path would be too long for Windows",
    "name_invalid": "the project name is not one this hub accepts",
    "folder_invalid": "the folder name is not one this hub accepts",
    "repo_invalid": "the repository name is not one this hub accepts",
    "project_not_found": "no project of this hub has that id",
    "operation_not_found": "this hub does not hold an operation with that id",
    "pick_not_found": "this hub does not hold a folder choice with that id",
    "login_not_found": "this hub does not know a login folder with that key",
    "candidate_not_found": "this hub does not hold a tool candidate with that id",
    "pick_invalid": "the chosen folder cannot be used",
    "legacy_writers_unconfirmed": ("the folder holds an older project whose writers are not "
                                   "confirmed stopped"),
    "folder_exists": "a folder of that name already exists",
    "projects_home_invalid": "the folder for new projects cannot be used",
    "review_harness_missing": "no harness is set up to review a project started from scratch",
    "operation_busy": "another project is being added",
    "registry_busy": "the project list is being changed by another process",
    "registry_invalid": "the project list file is not in the form this hub accepts",
    "dialog_busy": "a folder dialog is already open",
    "dialog_unavailable": "this machine cannot show a folder dialog",
    "profile_absent": "no harness profile is set up",
    "profile_invalid": "the harness profile is not in the form this hub accepts",
    "git_not_pinned": "git is not pinned",
    "gh_not_pinned": "the GitHub CLI is not pinned",
    "git_changed": "the pinned git has changed",
    "gh_changed": "the pinned GitHub CLI has changed",
    "git_too_old": "the pinned git is older than this product needs",
    "tool_version_unreadable": "the version of the tool cannot be read",
    "gh_not_logged_in": "the GitHub CLI is not logged in",
    "gh_unreachable": "GitHub cannot be reached",
    "gh_failed": "the GitHub CLI failed",
    "project_busy": "another change to this project is under way",
    "project_running": "this project already has a running child",
    "project_not_running": "this project has no running child",
    "project_unavailable": "this project's folder is missing or is now another project",
    "already_active": "this project is already the active one",
    "active_not_closed": "the active project has not closed yet",
    "recovery_required": "this project must be recovered first",
    "recover_not_needed": "there is nothing to recover",
    "operation_not_cancellable": "this operation cannot be cancelled now",
    "project_queue_changed": "the order is not the current queue of projects",
    "hub_in_kill_on_close_job": "this hub runs inside a Windows job that would end its children",
})

_MAX_DETAIL = 200
_ALL = frozenset(HUB_ERROR_STATUS) | OPERATION_ERROR_CODES


def hub_messages() -> Mapping[str, str]:
    """The fixed English sentence of each route refusal, by code."""
    return _HUB_MESSAGES


def _short_word(value: object) -> bool:
    if not isinstance(value, str) or len(value) > _MAX_DETAIL:
        return False
    return not (value[:1] in "/\\" or value[1:3] in (":\\", ":/") or "\\\\" in value[:2])


class HubRefusal(Exception):
    """One refusal of a route: a code of `HUB_ERROR_STATUS` and a small detail.

    Raises:
        ValueError: `code` is not a route refusal, or `detail` is not a map of non-empty keys to
            short words (text of at most 200 characters that is not an absolute path).
    """

    def __init__(self, code: str, detail: Mapping[str, str] | None = None) -> None:
        if code not in HUB_ERROR_STATUS:
            raise ValueError(f"{code!r} is not a refusal of a hub route")
        facts = dict(detail or {})
        if not all(isinstance(key, str) and key and _short_word(value)
                   for key, value in facts.items()):
            raise ValueError("a refusal's detail is a map of names to short words, no paths")
        self.code, self.detail = code, MappingProxyType(facts)
        super().__init__(code)

    @property
    def status(self) -> int:
        """The HTTP status of this refusal."""
        return HUB_ERROR_STATUS[self.code]

    @property
    def message(self) -> str:
        """The fixed English sentence of this refusal."""
        return _HUB_MESSAGES[self.code]

    def as_dict(self) -> dict[str, object]:
        """The envelope of a refusal: exactly `{"error": {code, message, detail}}`."""
        return {"error": {"code": self.code, "message": self.message,
                          "detail": dict(self.detail)}}


def is_hub_code(code: object) -> bool:
    """Whether `code` is in either closed list."""
    return code in _ALL
