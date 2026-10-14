"""The push step of an accepted result (spec 9.7): its door, its bodies and what it asks first."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from conductor import tool_env, tool_pins
from conductor.command.adapters import AdapterRegistry
from conductor.command.api_refusals import (
    ACCEPT_REASONS, PR_MISMATCH_REASONS, ApiRefusal, _reviewed_fact)
from conductor.command.command_routes import Route, match_route
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.ownership import data_root
from tests import _fakegh
from tests.accept_remote import (
    BRANCH, OWNER, REF, SSH_URL, TIMED_OUT, URL, accepted, confirm, digest_of, remote_oid,
    seed_remote_ref, terms, with_gh)
from tests.git_repo_helpers import git, needs_git
from tests.test_accept_context import RUN, prepared
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, api as http_api, get_headers, ids, post

PATH = f"/command/runs/{RUN}/accept/push"
ACCEPTANCE = "acc-" + "a" * 32
TERMS = {"acceptance_id": ACCEPTANCE, "remote": "origin", "preview": True}
CONFIRM = {"acceptance_id": ACCEPTANCE, "remote": "origin",
           "push_digest": "sha256:" + "b" * 64, "actor": "Owner"}
NEW_REASONS = (
    "push_requires_commit", "push_not_permitted", "push_rejected", "push_terms_changed",
    "push_url_ambiguous", "push_destination_mismatch", "remote_url_has_credentials",
    "push_auth_failed", "push_timed_out", "push_unconfirmed", "pr_requires_push",
    "gh_not_logged_in", "pr_mismatch", "pr_create_failed")
NOTICE = Path(__file__).parents[1] / "src/conductor/panel/studio-notice-copy.js"


def active(tmp_path):
    """A finished run whose project is served for work; its git reader fails the test if asked."""
    api = prepared(tmp_path)
    api._identity = ProjectIdentity("a" * 32, None, False, "active", None, None)
    return api


def code_of(answer):
    return answer.payload["error"]["code"], answer.payload["error"].get("detail")


def test_the_push_and_the_pull_request_are_two_routes_that_take_post_only():
    for tail, name in (("push", "accept_push"), ("pull-request", "accept_pull_request")):
        path = f"/command/runs/{RUN}/accept/{tail}"
        assert match_route("POST", path) == Route(name, RUN)
        with pytest.raises(ApiRefusal) as wrong:
            match_route("GET", path)
        assert wrong.value.code == "method_not_allowed"
        with pytest.raises(ApiRefusal) as absent:
            match_route("POST", path + "ed")
        assert absent.value.code == "route_not_found"
    assert match_route("GET", f"/command/runs/{RUN}/accept") == Route("accept", RUN)


def test_a_server_started_to_view_the_project_refuses_the_push_before_it_reads_the_body(tmp_path):
    api = prepared(tmp_path)                    # a view server: its git reader fails if asked
    for body in (TERMS, CONFIRM, {}):
        assert code_of(post(api, PATH, body)) == ("project_not_active", {})


@pytest.mark.parametrize("body", [
    {}, {**TERMS, "actor": "Owner"}, {**TERMS, "preview": False}, {**TERMS, "preview": 1},
    {**TERMS, "check": True}, {"acceptance_id": ACCEPTANCE, "remote": "origin"},
    {k: v for k, v in CONFIRM.items() if k != "actor"},
    {k: v for k, v in CONFIRM.items() if k != "push_digest"},
    {**CONFIRM, "preview": True}, {**CONFIRM, "check": False}, {**CONFIRM, "check": 1},
    {**CONFIRM, "unknown": 1}, {**CONFIRM, "acceptance_id": "acc-" + "A" * 32},
    {**CONFIRM, "acceptance_id": "acc-" + "a" * 31}, {**CONFIRM, "remote": "-origin"},
    {**CONFIRM, "remote": ""}, {**CONFIRM, "remote": 1}, {**CONFIRM, "actor": ""},
    {**CONFIRM, "push_digest": "sha256:" + "B" * 64}, {**CONFIRM, "push_digest": None}])
def test_the_push_body_is_exactly_the_terms_or_the_confirmation(tmp_path, body):
    assert post(active(tmp_path), PATH, body).payload["error"]["code"] == "contract_invalid"


def test_a_check_press_is_the_confirmation_with_one_more_key():
    from conductor.command.accept_push import parse_body
    assert parse_body(CONFIRM).check is False and parse_body(CONFIRM).preview is False
    assert parse_body({**CONFIRM, "check": True}).check is True
    assert parse_body(TERMS).preview is True


@pytest.mark.parametrize("body", [TERMS, CONFIRM, {**CONFIRM, "check": True}])
def test_the_push_needs_a_recorded_commit_before_it_asks_anything_else(tmp_path, body):
    answer = post(active(tmp_path), PATH, body)
    assert answer.status == 409
    assert code_of(answer) == ("accept_refused", {"reason": "push_requires_commit"})


def test_every_reason_of_the_push_and_the_pull_request_stands_with_both_languages():
    copy = NOTICE.read_text(encoding="utf-8")
    for reason in NEW_REASONS:
        assert reason in ACCEPT_REASONS
        assert f'"accept.reason.{reason}": [' in copy
        assert ApiRefusal.accept_refused(reason).as_dict()["error"]["detail"] == {"reason": reason}
    assert len(set(ACCEPT_REASONS)) == len(ACCEPT_REASONS)


def test_a_pull_request_mismatch_names_one_word_of_the_closed_list():
    assert PR_MISMATCH_REASONS == (
        "remote_head_moved", "other_head", "other_base", "cross_repository")
    for word in PR_MISMATCH_REASONS:
        refusal = ApiRefusal.pr_mismatch(word)
        assert refusal.status == 409
        assert refusal.as_dict()["error"]["detail"] == {"reason": "pr_mismatch", "mismatch": word}
    for forged in ("", "head moved", "other_head ", None, 1):
        with pytest.raises(ValueError):
            ApiRefusal.pr_mismatch(forged)
    message = "the result cannot be accepted: pr_mismatch (other_head)"
    assert _reviewed_fact("accept_refused", message,
                          {"reason": "pr_mismatch", "mismatch": "other_head"})
    assert not _reviewed_fact("accept_refused", message,
                              {"reason": "git_failed", "mismatch": "other_head"})
    assert not _reviewed_fact("accept_refused", message,
                              {"reason": "pr_mismatch", "mismatch": "free text"})


def test_the_command_api_holds_a_gh_reader_beside_the_git_reader(tmp_path):
    subject, store, _events = http_api(tmp_path)
    assert subject._project_gh is None

    def build(**more):
        return CommandApi(store, AdapterRegistry([FakeAdapter()]), session=CommandSession(
            PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
            publish_run=lambda _: None, **more)

    def reader(args, **keywords):
        return None

    assert build(project_gh=reader)._project_gh is reader
    with pytest.raises(TypeError, match="gh reader"):
        build(project_gh="gh")


# -- the push itself: a real repository, a real bare remote, a scripted gh (spec 9.7, R7) ----------

def accepted_with_gh(tmp_path, script=None):
    api, root, record, remote, bare = accepted(tmp_path)
    return api, root, record, remote, bare, with_gh(tmp_path, api, root, script)


def reason_of(answer):
    assert answer.status == 409, answer.payload
    return answer.payload["error"]["detail"]["reason"]


def moved_commit(root, record, message="elsewhere"):
    """A commit that is not the accepted one: the same tree, another message, no parent."""
    tree = git("rev-parse", f"{record['commit']}^{{tree}}", cwd=root).stdout.decode().strip()
    return git("commit-tree", tree, "-m", message, cwd=root).stdout.decode().strip()


@needs_git
def test_commit_route_never_pushes(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    assert remote.calls, "the commit itself ran through the wrapped reader"
    assert "push" not in remote.verbs() and "ls-remote" not in remote.verbs()
    assert git("for-each-ref", cwd=bare).stdout == b""
    assert _fakegh.calls(gh.dir) == []
    shown = api.handle("GET", f"/command/runs/{RUN}/accept", get_headers()).payload
    assert shown["commit"] == record and shown["push"] is None


@needs_git
def test_the_terms_name_the_three_facts_and_the_exact_command_and_change_nothing(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    answer = terms(api, record)
    assert answer.status == 200, answer.payload
    shown = answer.payload["push_terms"]
    assert set(shown) == {"commit", "remote", "push_url", "repo", "ref", "command", "push_digest"}
    assert (shown["commit"], shown["remote"], shown["push_url"], shown["repo"], shown["ref"]) == (
        record["commit"], "origin", URL, "o/r", REF)
    assert shown["command"] == (
        f"git push --porcelain --no-follow-tags --recurse-submodules=no "
        f"--force-with-lease={REF}: {URL} {record['commit']}:{REF}")
    core = {"acceptance_id": record["acceptance_id"], "commit": record["commit"],
            "remote": "origin", "push_url": URL, "repo": "o/r", "ref": REF}
    assert shown["push_digest"] == "sha256:" + hashlib.sha256(json.dumps(
        core, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    assert terms(api, record).payload == answer.payload
    assert "push" not in remote.verbs() and "ls-remote" not in remote.verbs()
    assert [row["argv"][:2] for row in _fakegh.calls(gh.dir)] == [["repo", "view"]] * 2
    assert git("for-each-ref", cwd=bare).stdout == b""


@needs_git
def test_gh_receives_no_token_env_and_pinned_path_only(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    assert terms(api, record).status == 200
    row, = _fakegh.calls(gh.dir)
    assert row["argv"] == ["repo", "view", "o/r", "--json",
                           "nameWithOwner,defaultBranchRef,viewerPermission,isArchived"]
    assert not set(row["env_names"]) & set(OWNER)
    assert {"GH_PROMPT_DISABLED", "GH_NO_UPDATE_NOTIFIER", "NO_COLOR"} <= set(row["env_names"])
    pins = tool_pins.ToolPins(gh=tool_pins.ToolPin("gh", str(gh.exe), "2.50.0"))
    assert row["path"] == tool_env.tool_env(gh.source, pins, gh.hub)["PATH"]
    assert Path(row["path"].split(os.pathsep)[0]) == gh.dir


@needs_git
def test_remote_url_with_credentials_is_refused_and_not_echoed(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    secret = "s3cret-pass"
    git("remote", "set-url", "origin", f"https://owner:{secret}@github.com/o/r.git", cwd=root)
    for answer in (terms(api, record), confirm(api, record, "sha256:" + "c" * 64)):
        assert reason_of(answer) == "remote_url_has_credentials"
        assert secret not in json.dumps(answer.payload) and "owner:" not in repr(answer.payload)
    assert _fakegh.calls(gh.dir) == []
    assert "push" not in remote.verbs() and "ls-remote" not in remote.verbs()
    assert git("for-each-ref", cwd=bare).stdout == b""


@needs_git
def test_push_sends_the_recorded_oid_even_after_the_local_branch_moved(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    other = moved_commit(root, record, "moved")
    git("update-ref", f"refs/heads/{BRANCH}", other, cwd=root)
    answer = confirm(api, record, digest)
    assert answer.status == 201, answer.payload
    assert remote_oid(bare) == record["commit"] != other
    pushed, = remote.pushes()
    assert pushed[-1] == f"{record['commit']}:{REF}" and other not in " ".join(pushed)
    assert answer.payload["push"]["remote_oid"] == record["commit"]


@needs_git
def test_push_confirmation_is_refused_when_the_resolved_push_url_changed(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    git("config", "remote.origin.pushurl", SSH_URL, cwd=root)       # the same repository, said
    answer = confirm(api, record, digest)                           # another way
    assert reason_of(answer) == "push_terms_changed"
    shown = terms(api, record).payload["push_terms"]
    assert shown["push_url"] == SSH_URL and shown["push_digest"] != digest
    assert "push" not in remote.verbs() and "ls-remote" not in remote.verbs()
    assert git("for-each-ref", cwd=bare).stdout == b""
    git("config", "--unset", "remote.origin.pushurl", cwd=root)
    assert confirm(api, record, digest).status == 201               # the terms came back


@needs_git
@pytest.mark.parametrize("held", ["fast_forward", "diverged"])
def test_push_to_an_existing_remote_branch_changes_nothing_and_is_rejected(tmp_path, held):
    """The lease, on a real bare repository, after the look that said the ref was absent.

    The remote branch appears between the look and the push, which is the race the lease is for;
    it holds either an ancestor of the commit (a fast-forward could have moved it) or a commit of
    its own. The push itself must be refused by the remote, and the branch must not move.
    """
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    existing = record["base_commit"] if held == "fast_forward" else moved_commit(root, record)
    seen = []

    def race(run):
        seed_remote_ref(root, bare, existing)
        seen.append(run())
        return seen[-1]

    remote.on_push = race
    answer = confirm(api, record, digest)
    assert reason_of(answer) == "push_rejected"
    assert seen[0].exit_code == 1 and b"[rejected] (stale info)" in seen[0].output
    assert remote_oid(bare) == existing
    assert not (data_root(root) / "accept" / RUN / "push.json").exists()


@needs_git
def test_push_argv_sends_no_tags_and_no_submodules(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    git("tag", "-a", "v1", "-m", "release", record["commit"], cwd=root)
    git("config", "push.followTags", "true", cwd=root)
    assert confirm(api, record, digest_of(api, record)).status == 201
    pushed, = remote.pushes()
    assert pushed[2:] == ["push", "--porcelain", "--no-follow-tags", "--recurse-submodules=no",
                          f"--force-with-lease={REF}:", URL, f"{record['commit']}:{REF}"]
    assert not {"--tags", "--force", "-f", "-u", "--set-upstream", "--mirror", "--all",
                "--prune", "--delete"} & set(pushed)
    assert git("for-each-ref", "refs/tags", cwd=bare).stdout == b""
    assert git("for-each-ref", "refs/remotes", cwd=root).stdout == b""
    assert git("config", "--get-regexp", r"^branch\.", cwd=root, check=False).stdout == b""


@needs_git
def test_an_uncertain_push_is_reconciled_by_the_remote_oid_before_any_retry(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)

    def landed_then_silence(run):
        run()
        return TIMED_OUT

    remote.on_push = landed_then_silence
    answer = confirm(api, record, digest)
    assert answer.status == 201, answer.payload
    assert answer.payload["push"]["remote_oid"] == record["commit"] == remote_oid(bare)
    assert remote.verbs().count("push") == 1
    assert confirm(api, record, digest).status == 200 and remote.verbs().count("push") == 1
