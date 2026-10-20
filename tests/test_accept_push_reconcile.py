"""The push step when the answer is not a plain yes: what it asks the remote, what it refuses.

The rule under every test here (spec 9.7): the look at the ref on the remote comes BEFORE any
push and AFTER every push, and only the look decides. So an unknown answer is never repeated
blindly, a press that only checks never pushes, and a record is written only for a ref seen.
"""
import threading

import pytest

from conductor.command import accept_github as github
from conductor.command import accept_push
from conductor.command.accept_gh import GhUnavailable
from conductor.command.project_git import GitAnswer
from conductor.command.run_store import StoreError
from conductor.ownership import data_root
from tests import _fakegh
from tests.accept_remote import (
    PUSH, REF, SSH_URL, TIMED_OUT, URL, confirm, digest_of, remote_oid, seed_remote_ref, terms)
from tests.git_repo_helpers import git, needs_git
from tests.test_accept_context import RUN
from tests.test_accept_push import accepted_with_gh, code_of, moved_commit, reason_of
from tests.test_command_http_api import get_headers, post
from tests.test_command_run_store import NOW

AUTH_WORDS = b"fatal: could not read Username for 'https://github.com': terminal prompts disabled\n"
PUSH_JSON = "push.json"


def verbs(remote):
    """The network verbs the product used, in order."""
    return [verb for verb in remote.verbs() if verb in ("ls-remote", "push")]


def stands(root):
    return (data_root(root) / "accept" / RUN / PUSH_JSON).exists()


@needs_git
def test_a_push_that_never_arrived_is_known_absent_before_it_is_sent_again(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    remote.on_push = lambda run: TIMED_OUT                       # the push never ran
    answer = confirm(api, record, digest)
    assert reason_of(answer) == "push_timed_out"
    assert remote_oid(bare) is None and not stands(root)
    remote.on_push = None
    assert confirm(api, record, digest).status == 201 and remote_oid(bare) == record["commit"]
    assert verbs(remote) == ["ls-remote", "push", "ls-remote", "ls-remote", "push", "ls-remote"]


@needs_git
def test_when_neither_the_push_nor_the_look_answers_nothing_is_written_and_a_check_records_it(
        tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    looks = []

    def second_look_is_silent(run):
        looks.append(1)
        return TIMED_OUT if len(looks) == 2 else run()

    def landed_then_silence(run):
        run()
        return TIMED_OUT

    remote.on_look, remote.on_push = second_look_is_silent, landed_then_silence
    answer = confirm(api, record, digest)
    assert reason_of(answer) == "push_unconfirmed"
    assert remote_oid(bare) == record["commit"] and not stands(root)
    checked = confirm(api, record, digest, check=True)
    assert checked.status == 201, checked.payload
    assert checked.payload["push"]["remote_oid"] == record["commit"] and stands(root)
    assert remote.verbs().count("push") == 1


@needs_git
def test_a_press_that_only_checks_never_pushes_and_says_nothing_was_sent(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    answer = confirm(api, record, digest_of(api, record), check=True)
    assert (answer.status, answer.payload) == (200, {"push": None})
    assert verbs(remote) == ["ls-remote"] and remote_oid(bare) is None and not stands(root)


@needs_git
def test_an_exit_with_no_porcelain_line_for_the_ref_and_no_ref_is_a_git_failure_to_send_again(
        tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    remote.on_push = lambda run: GitAnswer(128, b"fatal: unable to access: could not resolve\n")
    assert reason_of(confirm(api, record, digest)) == "git_failed"
    assert remote_oid(bare) is None and not stands(root)
    assert verbs(remote) == ["ls-remote", "push", "ls-remote"]


@needs_git
def test_a_git_that_cannot_sign_in_is_push_auth_failed_after_the_look_finds_no_ref(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    remote.on_push = lambda run: GitAnswer(128, AUTH_WORDS)
    assert reason_of(confirm(api, record, digest_of(api, record))) == "push_auth_failed"
    assert verbs(remote) == ["ls-remote", "push", "ls-remote"] and not stands(root)
    assert remote_oid(bare) is None


@needs_git
@pytest.mark.parametrize("silence, reason", [
    (GitAnswer(128, b"fatal: Authentication failed for 'x'\n"), "push_auth_failed"),
    (TIMED_OUT, "push_unconfirmed")], ids=["look_cannot_sign_in", "look_no_answer"])
def test_a_push_that_could_not_sign_in_and_a_look_that_is_silent_write_nothing_and_push_once(
        tmp_path, silence, reason):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    looks = []

    def second_look_is_silent(run):
        looks.append(1)
        return silence if len(looks) == 2 else run()

    remote.on_look = second_look_is_silent
    remote.on_push = lambda run: GitAnswer(128, AUTH_WORDS)
    assert reason_of(confirm(api, record, digest_of(api, record))) == reason
    assert verbs(remote) == ["ls-remote", "push", "ls-remote"] and not stands(root)
    assert remote_oid(bare) is None and remote.verbs().count("push") == 1


@needs_git
def test_a_push_that_landed_and_said_it_could_not_sign_in_is_recorded_by_the_look_after_it(
        tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)

    def landed_then_could_not_sign_in(run):
        run()
        return GitAnswer(128, AUTH_WORDS)

    remote.on_push = landed_then_could_not_sign_in
    answer = confirm(api, record, digest_of(api, record))
    assert answer.status == 201, answer.payload
    assert answer.payload["push"]["remote_oid"] == record["commit"]
    assert remote_oid(bare) == record["commit"] and stands(root)
    assert verbs(remote) == ["ls-remote", "push", "ls-remote"]
    assert remote.verbs().count("push") == 1


@needs_git
def test_another_commit_the_look_finds_after_a_push_that_could_not_sign_in_is_rejected(
        tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    other = moved_commit(root, record)

    def another_landed_then_could_not_sign_in(run):
        seed_remote_ref(root, bare, other)
        return GitAnswer(128, AUTH_WORDS)

    remote.on_push = another_landed_then_could_not_sign_in
    assert reason_of(confirm(api, record, digest_of(api, record))) == "push_rejected"
    assert verbs(remote) == ["ls-remote", "push", "ls-remote"] and not stands(root)
    assert remote_oid(bare) == other and remote.verbs().count("push") == 1


@needs_git
def test_a_look_that_cannot_sign_in_says_so_and_no_push_follows(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    remote.on_look = lambda run: GitAnswer(128, b"fatal: Authentication failed for 'x'\n")
    assert reason_of(confirm(api, record, digest_of(api, record))) == "push_auth_failed"
    assert verbs(remote) == ["ls-remote"]


@needs_git
@pytest.mark.parametrize("silence, reason", [
    (TIMED_OUT, "push_unconfirmed"),
    (GitAnswer(128, b"fatal: Authentication failed for 'x'\n"), "push_auth_failed")],
    ids=["no_answer", "cannot_sign_in"])
def test_a_press_that_only_checks_and_gets_no_answer_from_its_look_asks_no_push(
        tmp_path, silence, reason):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    remote.on_look = lambda run: silence
    answer = confirm(api, record, digest_of(api, record), check=True)
    assert reason_of(answer) == reason
    assert verbs(remote) == ["ls-remote"] and remote_oid(bare) is None and not stands(root)


@needs_git
def test_a_branch_already_there_with_another_commit_is_rejected_before_any_push(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    existing = moved_commit(root, record)
    seed_remote_ref(root, bare, existing)
    assert reason_of(confirm(api, record, digest_of(api, record))) == "push_rejected"
    assert verbs(remote) == ["ls-remote"] and remote_oid(bare) == existing and not stands(root)


@needs_git
def test_a_press_that_only_checks_finds_another_commit_there_and_rejects_with_no_push(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    existing = moved_commit(root, record)
    seed_remote_ref(root, bare, existing)
    answer = confirm(api, record, digest_of(api, record), check=True)
    assert reason_of(answer) == "push_rejected"
    assert verbs(remote) == ["ls-remote"] and remote_oid(bare) == existing and not stands(root)


@needs_git
def test_a_branch_already_there_with_the_accepted_commit_is_recorded_and_not_pushed_again(
        tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    seed_remote_ref(root, bare, record["commit"])
    answer = confirm(api, record, digest_of(api, record))
    assert answer.status == 201 and answer.payload["push"]["remote_oid"] == record["commit"]
    assert verbs(remote) == ["ls-remote"]


@needs_git
@pytest.mark.parametrize("permission,archived", [
    ("READ", False), ("TRIAGE", False), ("WRITE", True), ("ADMIN", True)])
def test_an_owner_who_may_not_push_gets_push_not_permitted_and_nothing_leaves(
        tmp_path, permission, archived):
    script = {"repo view": [_fakegh.repo_view(permission=permission, archived=archived)]}
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path, script)
    assert reason_of(terms(api, record)) == "push_not_permitted"
    assert reason_of(confirm(api, record, "sha256:" + "c" * 64)) == "push_not_permitted"
    assert verbs(remote) == [] and remote_oid(bare) is None


@needs_git
def test_more_than_one_push_address_is_ambiguous_and_nothing_is_asked_of_gh(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    git("config", "--add", "remote.origin.pushurl", URL, cwd=root)
    git("config", "--add", "remote.origin.pushurl", SSH_URL, cwd=root)
    assert reason_of(terms(api, record)) == "push_url_ambiguous"
    assert _fakegh.calls(gh.dir) == [] and verbs(remote) == []


@needs_git
@pytest.mark.parametrize("address", [
    "https://gitlab.com/o/r.git", "http://github.com/o/r.git", "git@gitlab.com:o/r.git"])
def test_a_remote_that_is_not_the_github_of_the_spec_is_a_destination_mismatch(tmp_path, address):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    git("remote", "set-url", "origin", address, cwd=root)
    assert reason_of(terms(api, record)) == "push_destination_mismatch"
    assert _fakegh.calls(gh.dir) == [] and verbs(remote) == []


@needs_git
def test_a_remote_that_is_not_there_and_a_repository_gh_names_otherwise_are_mismatches(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(
        tmp_path, {"repo view": [_fakegh.repo_view(name="o/renamed")]})
    assert reason_of(terms(api, record, remote="nowhere")) == "push_destination_mismatch"
    assert _fakegh.calls(gh.dir) == []
    assert reason_of(terms(api, record)) == "push_destination_mismatch"
    assert verbs(remote) == []


@needs_git
def test_gh_not_signed_in_is_named_and_gh_failing_is_a_failure_of_the_tool(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(
        tmp_path, {"repo view": [_fakegh.said(exit=4), _fakegh.said(exit=1), _fakegh.said("{")]})
    assert reason_of(terms(api, record)) == "gh_not_logged_in"
    assert reason_of(terms(api, record)) == "git_failed"
    assert reason_of(terms(api, record)) == "git_failed"
    assert verbs(remote) == []


@needs_git
def test_a_server_with_no_usable_gh_or_git_refuses_with_tool_unavailable(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    reader, api._project_gh = api._project_gh, None
    answer = terms(api, record)
    assert (answer.status, code_of(answer)) == (503, (
        "tool_unavailable", {"tool": "gh", "reason": "not_pinned"}))
    api._project_gh = reader
    git_reader, api._project_git = api._project_git, None
    assert code_of(terms(api, record)) == (
        "tool_unavailable", {"tool": "git", "reason": "not_pinned"})
    api._project_git = git_reader

    def changed(args, **keywords):
        raise GhUnavailable("version_changed")

    api._project_gh = changed
    answer = terms(api, record)
    assert (answer.status, code_of(answer)) == (503, (
        "tool_unavailable", {"tool": "gh", "reason": "version_changed"}))


@needs_git
def test_the_acceptance_id_must_be_the_one_of_this_run(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    other = "acc-" + "0" * 32
    for body in ({"acceptance_id": other, "remote": "origin", "preview": True},
                 {"acceptance_id": other, "remote": "origin", "push_digest": "sha256:" + "c" * 64,
                  "actor": "Owner"}):
        assert code_of(post(api, PUSH, body))[0] == "contract_invalid"
    assert _fakegh.calls(gh.dir) == [] and verbs(remote) == []


@needs_git
def test_the_record_names_the_commit_the_credential_free_address_and_the_remote_oid(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    answer = confirm(api, record, digest)
    assert answer.status == 201, answer.payload
    assert answer.payload["push"] == {
        "schema_version": 1, "acceptance_id": record["acceptance_id"], "remote": "origin",
        "push_url": URL, "remote_repo": "o/r", "ref": REF, "commit": record["commit"],
        "push_digest": digest, "remote_oid": record["commit"], "requested_by": "Owner",
        "pushed_at": NOW}
    stored = (data_root(root) / "accept" / RUN / PUSH_JSON).read_bytes()
    assert stored.endswith(b"\n") and stored.isascii() and b"\r" not in stored
    shown = api.handle("GET", f"/command/runs/{RUN}/accept", get_headers()).payload
    assert shown["push"] == answer.payload["push"] and shown["pull_request"] is None


@needs_git
def test_the_exact_repeat_gives_the_standing_record_and_no_other_press_does(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    first = confirm(api, record, digest)
    calls = len(remote.calls)
    again = confirm(api, record, digest)
    assert (again.status, again.payload) == (200, first.payload)
    assert reason_of(confirm(api, record, "sha256:" + "d" * 64)) == "push_terms_changed"
    assert reason_of(confirm(api, record, digest, actor="Other")) == "acceptance_exists"
    assert len(remote.calls) == calls and remote.verbs().count("push") == 1


@needs_git
def test_a_record_that_could_not_be_written_is_written_by_the_next_press_without_a_second_push(
        tmp_path, monkeypatch):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    real = accept_push.write_push
    monkeypatch.setattr(accept_push, "write_push",
                        lambda *args: (_ for _ in ()).throw(StoreError("interrupted")))
    assert confirm(api, record, digest).status == 500
    assert remote_oid(bare) == record["commit"] and not stands(root)
    monkeypatch.setattr(accept_push, "write_push", real)
    assert confirm(api, record, digest).status == 201
    assert remote.verbs().count("push") == 1


@needs_git
def test_the_network_call_runs_outside_the_store_transaction(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    free = []

    def probe(run):
        taken = threading.Event()

        def take():
            with api._store.transaction():
                taken.set()

        worker = threading.Thread(target=take, daemon=True)
        worker.start()
        free.append(taken.wait(10))
        return run()

    remote.on_look = probe
    remote.on_push = probe
    assert confirm(api, record, digest).status == 201
    assert free == [True, True, True]


class SpyLock:
    """The run's lock, telling when a second press arrives at it."""

    def __init__(self):
        self.held, self.arrivals, self.second = threading.Lock(), 0, threading.Event()
        self.count = threading.Lock()

    def __enter__(self):
        with self.count:
            self.arrivals += 1
            if self.arrivals == 2:
                self.second.set()
        self.held.acquire()

    def __exit__(self, *exc):
        self.held.release()


@needs_git
def test_two_presses_on_one_run_act_one_at_a_time_and_the_second_finds_the_first(
        tmp_path, monkeypatch):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    spy, inside, answers = SpyLock(), threading.Event(), {}
    monkeypatch.setattr(github, "publish_lock", lambda *args: spy)

    def wait_for_the_second(run):
        inside.set()
        answers["arrived"] = spy.second.wait(10)
        return run()

    remote.on_push = wait_for_the_second
    first = threading.Thread(target=lambda: answers.update(first=confirm(api, record, digest)))
    second = threading.Thread(target=lambda: answers.update(second=confirm(api, record, digest)))
    first.start()
    assert inside.wait(10)
    second.start()
    first.join(30)
    second.join(30)
    assert answers["arrived"] is True
    assert (answers["first"].status, answers["second"].status) == (201, 200)
    assert answers["first"].payload == answers["second"].payload
    assert remote.verbs().count("push") == 1
