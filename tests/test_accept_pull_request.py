"""The pull request step of an accepted result (spec 9.7): its door, its body and its first gate."""
import json

import pytest

from conductor.command.accept_pull_request import BODY_LIMIT, TITLE_LIMIT, parse_body
from conductor.command.accept_store import _bytes
from conductor.command.project_git import GitAnswer
from conductor.ownership import data_root
from tests import _fakegh
from tests.accept_remote import BRANCH, PULL_REQUEST as PATH, REF, TIMED_OUT, confirm, digest_of
from tests.git_repo_helpers import git, needs_git
from tests.test_accept_context import RUN
from tests.test_accept_push import (
    ACCEPTANCE, accepted_with_gh, active, code_of, moved_commit, reason_of)
from tests.test_command_http_api import get_headers, post
from tests.test_command_run_store import NOW

BODY = {"acceptance_id": ACCEPTANCE, "base": "main", "title": "Add the result",
        "body": "Line one\nLine two\n", "draft": False, "actor": "Owner"}


def test_a_server_started_to_view_the_project_refuses_the_pull_request_before_the_body(tmp_path):
    from tests.test_accept_context import prepared
    api = prepared(tmp_path)
    for body in (BODY, {}):
        assert code_of(post(api, PATH, body)) == ("project_not_active", {})


@pytest.mark.parametrize("change", [
    {"acceptance_id": "acc-short"}, {"base": ""}, {"base": "-main"}, {"base": "a..b"},
    {"base": "a//b"}, {"base": "main/"}, {"base": "x.lock"}, {"base": "has space"},
    {"base": 1}, {"title": ""}, {"title": "  "}, {"title": "two\nlines"}, {"title": "x" * 257},
    {"title": 1}, {"body": 1}, {"body": "x" * (BODY_LIMIT + 1)}, {"body": "nul\x00inside"},
    {"body": "bell\x07"}, {"body": "\ud800"}, {"draft": "false"}, {"draft": 0}, {"draft": None},
    {"actor": ""}, {"actor": 1}, {"check": False}, {"check": 1}, {"unknown": 1}])
def test_the_pull_request_body_is_exactly_its_closed_shape(tmp_path, change):
    answer = post(active(tmp_path), PATH, {**BODY, **change})
    assert answer.payload["error"]["code"] == "contract_invalid"


@pytest.mark.parametrize("missing", sorted(set(BODY)))
def test_a_pull_request_body_without_one_of_its_keys_is_refused(tmp_path, missing):
    body = {key: value for key, value in BODY.items() if key != missing}
    assert post(active(tmp_path), PATH, body).payload["error"]["code"] == "contract_invalid"


def test_an_exact_body_is_read_whole_and_a_check_press_is_the_same_body_with_one_key():
    plain, check = parse_body(BODY), parse_body({**BODY, "check": True})
    assert (plain.check, check.check) == (False, True)
    assert (plain.base, plain.title, plain.body, plain.draft) == (
        "main", "Add the result", "Line one\nLine two\n", False)
    assert parse_body({**BODY, "title": "x" * TITLE_LIMIT, "body": "", "base": "release/1.0"})
    assert parse_body({**BODY, "body": "ж" * BODY_LIMIT}).body == "ж" * BODY_LIMIT


def test_the_pull_request_needs_a_recorded_push_before_it_asks_anything_else(tmp_path):
    api = active(tmp_path)
    for body in (BODY, {**BODY, "check": True}):
        answer = post(api, PATH, body)
        assert answer.status == 409
        assert code_of(answer) == ("accept_refused", {"reason": "pr_requires_push"})


# -- the pull request itself: a pushed branch, a real bare remote, a scripted gh (spec 9.7, S3) ----

OTHER = "f" * 40
LISTED = "pr list"
CREATED = "pr create"


def pushed(tmp_path, script=None):
    """An accepted result whose branch is pushed; -> api, root, push record, remote, bare, gh."""
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path, script)
    answer = confirm(api, record, digest_of(api, record))
    assert answer.status == 201, answer.payload
    return api, root, answer.payload["push"], remote, bare, gh


def body_for(push, **changes):
    return {"acceptance_id": push["acceptance_id"], "base": "main", "title": "Add the result",
            "body": "Line one\nLine two\n", "draft": False, "actor": "Owner", **changes}


def press(api, push, **changes):
    return post(api, PATH, body_for(push, **changes))


def made(gh, key):
    return [row for row in _fakegh.calls(gh.dir) if row["key"] == key]


def keys(gh):
    return [row["key"] for row in _fakegh.calls(gh.dir) if row["key"] != "repo view"]


def row_of(push, number, **changes):
    return _fakegh.pr_row(number, push["commit"], head=BRANCH, **changes)


@needs_git
def test_pull_request_requires_a_recorded_push(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    answer = post(api, PATH, body_for(record))
    assert reason_of(answer) == "pr_requires_push"
    assert [row["key"] for row in _fakegh.calls(gh.dir)] == []
    assert "ls-remote" not in remote.verbs() and "push" not in remote.verbs()


@needs_git
@pytest.mark.parametrize("found,word", [
    (dict(base="dev"), "other_base"), (dict(head_oid=OTHER), "other_head"),
    (dict(cross=True), "cross_repository"), (dict(cross=True, head_oid=OTHER), "cross_repository")])
def test_pull_request_is_accepted_only_for_the_same_head_oid_base_and_repository(
        tmp_path, found, word):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    head_oid = found.pop("head_oid", push["commit"])
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(_fakegh.pr_row(
        4, head_oid, head=BRANCH, **found))]})
    answer = press(api, push)
    assert reason_of(answer) == "pr_mismatch"
    assert answer.payload["error"]["detail"] == {"reason": "pr_mismatch", "mismatch": word}
    assert keys(gh) == [LISTED]
    assert not (data_root(root) / "accept" / RUN / "pr.json").exists()


@needs_git
def test_the_pull_request_of_the_same_head_base_and_repository_is_the_one_that_is_recorded(
        tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(
        row_of(push, 3, base="dev"), row_of(push, 5, state="MERGED", draft=True))]})
    answer = press(api, push, base="main")
    assert answer.status == 200, answer.payload
    assert answer.payload["pull_request"] == {
        "schema_version": 1, "acceptance_id": push["acceptance_id"], "repo": "o/r", "number": 5,
        "url": "https://github.com/o/r/pull/5", "draft": True, "base": "main",
        "head_ref": BRANCH, "head_oid": push["commit"], "mismatch": None,
        "requested_by": "Owner", "created_at": NOW}
    assert keys(gh) == [LISTED] and made(gh, CREATED) == []


@needs_git
@pytest.mark.parametrize("move", ["other_commit", "deleted"])
def test_a_moved_remote_head_refuses_before_gh_pr_create_is_called(tmp_path, move):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    if move == "other_commit":
        git("push", "-q", "-f", str(bare), f"{moved_commit(root, push)}:{REF}", cwd=root)
    else:
        git("push", "-q", str(bare), f":{REF}", cwd=root)
    answer = press(api, push)
    assert reason_of(answer) == "pr_mismatch"
    assert answer.payload["error"]["detail"]["mismatch"] == "remote_head_moved"
    assert keys(gh) == [] and made(gh, CREATED) == []
    assert not (data_root(root) / "accept" / RUN / "pr.json").exists()


@needs_git
@pytest.mark.parametrize("moved_on", ["the_list", "the_remote"])
def \
test_a_pull_request_created_for_a_moved_branch_is_recorded_with_its_mismatch_and_never_recreated(
        tmp_path, moved_on):
    """The branch moves after the check and before the creation: the pull request exists, so it
    is recorded as what it is, whichever side shows the move (the list, or the remote head)."""
    api, root, push, remote, bare, gh = pushed(tmp_path)
    other = moved_commit(root, push)
    shown_by_list = other if moved_on == "the_list" else push["commit"]
    row = _fakegh.pr_row(7, shown_by_list, head=BRANCH, base="main")
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(), _fakegh.pr_list(row)],
                            CREATED: [_fakegh.created(7)]})
    looks = []

    def move_before_the_second_look(run):
        looks.append(1)
        if len(looks) == 2 and moved_on == "the_remote":
            git("push", "-q", "-f", str(bare), f"{other}:{REF}", cwd=root)
        return run()

    remote.on_look = move_before_the_second_look
    answer = press(api, push)
    assert answer.status == 201, answer.payload
    record = answer.payload["pull_request"]
    assert (record["number"], record["head_oid"], record["base"]) == (7, push["commit"], "main")
    assert record["mismatch"] == {"head_oid": other, "base": "main", "cross_repository": False}
    assert keys(gh) == [LISTED, CREATED, LISTED] and len(looks) == 2
    shown = api.handle("GET", f"/command/runs/{RUN}/accept", get_headers()).payload
    assert shown["pull_request"] == record
    again = press(api, push)
    assert (again.status, again.payload) == (200, answer.payload)
    assert keys(gh) == [LISTED, CREATED, LISTED] and len(made(gh, CREATED)) == 1


@needs_git
def test_an_uncertain_pr_create_is_reconciled_by_listing_before_any_retry(tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    landed = row_of(push, 9)
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(), _fakegh.pr_list(landed)],
                            CREATED: [_fakegh.said("", exit=1)]})
    answer = press(api, push)
    assert answer.status == 201, answer.payload
    assert answer.payload["pull_request"]["number"] == 9
    assert answer.payload["pull_request"]["mismatch"] is None
    assert keys(gh) == [LISTED, CREATED, LISTED] and len(made(gh, CREATED)) == 1
    assert press(api, push).status == 200 and len(made(gh, CREATED)) == 1


@needs_git
def test_an_uncertain_pr_create_that_the_list_does_not_show_may_be_created_again_after_a_check(
        tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {
        LISTED: [_fakegh.pr_list(), _fakegh.pr_list(), _fakegh.pr_list(),
                 _fakegh.pr_list(row_of(push, 11))],
        CREATED: [_fakegh.said("", exit=1), _fakegh.created(11)]})
    first = press(api, push)
    assert reason_of(first) == "pr_create_failed"
    assert not (data_root(root) / "accept" / RUN / "pr.json").exists()
    second = press(api, push)
    assert second.status == 201 and second.payload["pull_request"]["number"] == 11
    assert keys(gh) == [LISTED, CREATED, LISTED, LISTED, CREATED, LISTED]


@needs_git
def test_a_list_that_fails_after_an_unknown_create_is_never_followed_by_a_blind_create(tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {
        LISTED: [_fakegh.pr_list(), _fakegh.said("", exit=1), _fakegh.pr_list(row_of(push, 12))],
        CREATED: [_fakegh.said("", exit=1)]})
    assert reason_of(press(api, push)) == "pr_create_failed"
    second = press(api, push)
    assert second.status == 200 and second.payload["pull_request"]["number"] == 12
    assert len(made(gh, CREATED)) == 1


@needs_git
@pytest.mark.parametrize("draft", [False, True])
def test_the_create_is_the_command_of_the_spec_with_the_body_on_stdin_and_nowhere_else(
        tmp_path, draft):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    text = "Reviewed by Rev\nAccepted by Owner\n\n- one.txt\n"
    landed = row_of(push, 8, base="release/1.0")
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(), _fakegh.pr_list(landed)],
                            CREATED: [_fakegh.created(8)]})
    answer = press(api, push, body=text, title="-- Add it", draft=draft, base="release/1.0")
    assert answer.status == 201 and answer.payload["pull_request"]["mismatch"] is None
    listing = made(gh, LISTED)[0]
    assert listing["argv"] == ["pr", "list", "--repo", "o/r", "--head", BRANCH, "--state", "all",
                               "--json", "number,url,state,headRefName,headRefOid,baseRefName,"
                               "isCrossRepository,isDraft"]
    create, = made(gh, CREATED)
    assert create["argv"] == ["pr", "create", "--repo", "o/r", "--base", "release/1.0", "--head",
                              BRANCH, "--title", "-- Add it", "--body-file", "-",
                              *(["--draft"] if draft else [])]
    assert create["stdin"] == text and "Reviewed" not in " ".join(create["argv"])


@needs_git
def test_gh_not_signed_in_is_certain_so_it_creates_nothing_and_reads_nothing_after(tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list()], CREATED: [_fakegh.said("", exit=4)]})
    assert reason_of(press(api, push)) == "gh_not_logged_in"
    assert keys(gh) == [LISTED, CREATED]
    _fakegh.script(gh.dir, {LISTED: [_fakegh.said("", exit=4)]})
    assert reason_of(press(api, push)) == "gh_not_logged_in"


@needs_git
def test_a_press_that_only_checks_records_the_pull_request_that_exists_and_never_creates(
        tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(), _fakegh.pr_list(row_of(push, 6))]})
    nothing = press(api, push, check=True)
    assert (nothing.status, nothing.payload) == (200, {"pull_request": None})
    found = press(api, push, check=True)
    assert found.status == 200 and found.payload["pull_request"]["number"] == 6
    assert made(gh, CREATED) == []


@needs_git
def test_a_remote_that_does_not_answer_before_the_check_creates_nothing(tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    remote.on_look = lambda run: TIMED_OUT
    assert reason_of(press(api, push)) == "pr_create_failed"
    remote.on_look = lambda run: GitAnswer(128, b"fatal: Authentication failed for 'x'\n")
    assert reason_of(press(api, push)) == "push_auth_failed"
    assert keys(gh) == []


@needs_git
@pytest.mark.parametrize("listing", [
    _fakegh.said("not json"), _fakegh.said("{}"), _fakegh.said('[{"number":1}]'),
    _fakegh.said(json.dumps([_fakegh.pr_row(1, "z" * 40)])), _fakegh.said("", exit=1)])
def test_a_list_gh_cannot_give_or_that_is_not_the_shape_stops_the_press_with_nothing_created(
        tmp_path, listing):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {LISTED: [listing]})
    assert reason_of(press(api, push)) == "pr_create_failed"
    assert made(gh, CREATED) == []


@needs_git
def test_a_repeat_with_another_base_is_a_mismatch_and_the_same_base_is_the_standing_record(
        tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(), _fakegh.pr_list(row_of(push, 8))],
                            CREATED: [_fakegh.created(8)]})
    first = press(api, push)
    assert first.status == 201
    calls = len(_fakegh.calls(gh.dir))
    other = press(api, push, base="dev")
    assert other.payload["error"]["detail"] == {"reason": "pr_mismatch", "mismatch": "other_base"}
    assert press(api, push).payload == first.payload
    assert len(_fakegh.calls(gh.dir)) == calls


@needs_git
def test_a_pr_record_with_a_malformed_mismatch_is_damaged_and_never_read_as_a_fact(tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {LISTED: [_fakegh.pr_list(), _fakegh.pr_list(row_of(push, 8))],
                            CREATED: [_fakegh.created(8)]})
    record = press(api, push).payload["pull_request"]
    path = data_root(root) / "accept" / RUN / "pr.json"
    for damaged in ("free text", {"head_oid": "nope", "base": "main", "cross_repository": False},
                    {"head_oid": OTHER, "base": "main"},
                    {"head_oid": OTHER, "base": "main", "cross_repository": 1},
                    {"head_oid": OTHER, "base": "main", "cross_repository": False, "x": 1}):
        path.write_bytes(_bytes({**record, "mismatch": damaged}))
        shown = api.handle("GET", f"/command/runs/{RUN}/accept", get_headers())
        assert shown.payload["error"]["code"] == "run_corrupt", damaged
    path.write_bytes(_bytes({**record, "mismatch": None}))
    assert api.handle("GET", f"/command/runs/{RUN}/accept", get_headers()).status == 200
