"""The destination of a push as git names it and gh confirms it (spec 9.7), and the shared look."""
import pytest

from conductor.command import accept_github as github
from conductor.command.accept_gh import GhUnavailable
from conductor.command.accept_manifest import SnapshotRefused
from conductor.command.api_refusals import ApiRefusal
from conductor.command.project_git import GitReadFailed
from tests import _fakegh
from tests.gh_script import ScriptGh, answer
from tests.git_repo_helpers import Script, said

URL = "https://github.com/o/r.git"
SECRET = "hunter2-token"
OID = "a" * 40
REF = "refs/heads/conduct/run-001"
FIELDS = "nameWithOwner,defaultBranchRef,viewerPermission,isArchived"


def view(**changes):
    return answer(_fakegh.repo_view(**changes)["stdout"])


def facts(address, gh_answers=None):
    git = Script(said((address + "\n").encode()))
    gh = ScriptGh(*(gh_answers or [view()]))
    return github.read_facts(git, gh, "ROOT", "origin"), git, gh


def refused(address, *, gh_answers=None, git_answer=None):
    git = Script(git_answer or said((address + "\n").encode()))
    gh = ScriptGh(*(gh_answers or [view()]))
    with pytest.raises(github.PublishRefused) as caught:
        github.read_facts(git, gh, "ROOT", "origin")
    return caught.value, gh


def test_the_push_address_is_read_with_get_url_push_all_and_the_one_address_is_the_answer():
    found, git, gh = facts(URL)
    assert git.calls == [(("-C", "ROOT", "remote", "get-url", "--push", "--all", "origin"), True)]
    assert git.keywords == [{"timeout": github.GIT_TIMEOUT_SECONDS}]
    assert gh.calls == [{"argv": ["repo", "view", "o/r", "--json", FIELDS], "stdin": None,
                         "timeout": None}]
    assert (found.push_url, found.repo, found.can_push, found.default_branch) == (
        URL, "o/r", True, "main")


@pytest.mark.parametrize("address", [
    "https://github.com/o/r", "https://github.com/o/r.git", "https://github.com/o/r/",
    "git@github.com:o/r", "git@github.com:o/r.git", "ssh://git@github.com/o/r.git"])
def test_the_forms_of_spec_9_7_are_admitted_and_each_is_confirmed_by_gh(address):
    found, _git, gh = facts(address)
    assert found.push_url == address and found.repo == "o/r" and len(gh.calls) == 1


def test_more_than_one_push_address_is_ambiguous_and_none_or_no_remote_is_a_mismatch():
    two = said(f"{URL}\nhttps://github.com/o/other.git\n".encode())
    error, gh = refused("", git_answer=two)
    assert error.reason == "push_url_ambiguous" and gh.calls == []
    for nothing in (said(b""), said(b"\n"), said(b"error: No such remote 'origin'\n", 2)):
        error, gh = refused("", git_answer=nothing)
        assert error.reason == "push_destination_mismatch" and gh.calls == []


def test_git_failing_or_timing_out_is_a_fault_of_git_and_not_a_verdict_on_the_remote():
    with pytest.raises(GitReadFailed) as failed:
        refused("", git_answer=said(b"fatal: not a repository\n", 128))
    assert failed.value.code == "git_failed"
    with pytest.raises(GitReadFailed) as timed:
        refused("", git_answer=said(b"", None, timed_out=True))
    assert timed.value.code == "git_timed_out"
    with pytest.raises(GitReadFailed):
        refused("", git_answer=said(b"x", 0, truncated=True))


@pytest.mark.parametrize("address", [
    f"https://user:{SECRET}@github.com/o/r.git", f"https://{SECRET}@github.com/o/r.git",
    f"https://github.com/o/r.git?token={SECRET}", f"https://github.com/o/r.git#{SECRET}",
    f"ssh://{SECRET}@github.com/o/r.git"])
def test_a_remote_address_with_credentials_is_refused_before_gh_and_never_echoed(address):
    error, gh = refused(address)
    assert error.reason == "remote_url_has_credentials" and gh.calls == []
    assert SECRET not in str(error) and SECRET not in repr(error)
    wire = github.refusal(error).as_dict()
    assert SECRET not in repr(wire) and wire["error"]["detail"] == {
        "reason": "remote_url_has_credentials"}


@pytest.mark.parametrize("address", [
    "https://gitlab.com/o/r.git", "http://github.com/o/r.git", "https://github.com:8443/o/r.git",
    "https://www.github.com/o/r.git", "git@gitlab.com:o/r.git", "ssh://git@github.com:22/o/r.git",
    "file:///srv/o/r.git", "/srv/o/r.git", "C:/srv/r.git", "https://github.com/-x/r.git",
    "https://github.com/o", "https://github.com/o/r/extra"])
def test_an_address_outside_the_three_forms_is_a_mismatch_and_gh_is_not_asked(address):
    error, gh = refused(address)
    assert error.reason == "push_destination_mismatch" and gh.calls == []


def test_gh_confirming_another_repository_or_none_is_a_mismatch_and_a_case_only_is_not():
    error, _gh = refused(URL, gh_answers=[view(name="o/renamed")])
    assert error.reason == "push_destination_mismatch"
    found, _git, _gh = facts(URL, [view(name="O/R")])
    assert found.repo == "o/r"


@pytest.mark.parametrize("permission,archived,expected", [
    ("ADMIN", False, True), ("MAINTAIN", False, True), ("WRITE", False, True),
    ("TRIAGE", False, False), ("READ", False, False), ("WRITE", True, False),
    ("ADMIN", True, False)])
def test_the_owner_may_push_with_admin_maintain_or_write_on_a_repository_not_archived(
        permission, archived, expected):
    found, _git, _gh = facts(URL, [view(permission=permission, archived=archived)])
    assert found.can_push is expected


def test_a_repository_with_no_default_branch_yet_is_still_confirmed():
    gh = answer('{"nameWithOwner":"o/r","defaultBranchRef":null,"viewerPermission":"WRITE",'
                '"isArchived":false}')
    found, _git, _gh = facts(URL, [gh])
    assert found.default_branch is None


@pytest.mark.parametrize("reply,reason", [
    (answer("", 4), "gh_not_logged_in"), (answer("", None, timed_out=True), "git_timed_out"),
    (answer("", 1), "git_failed"), (answer("{}", 0, truncated=True), "git_failed"),
    (answer("{}", 0, hidden=True), "git_failed"), (answer("not json"), "git_failed"),
    (answer("[]"), "git_failed"), (answer('{"nameWithOwner":"o/r"}'), "git_failed"),
    (answer('{"nameWithOwner":1,"defaultBranchRef":null,"viewerPermission":"READ",'
            '"isArchived":false}'), "git_failed"),
    (answer(b"\xff\xfe"), "git_failed")])
def test_a_failed_or_unreadable_answer_of_gh_is_one_refusal_of_the_closed_list(reply, reason):
    error, _gh = refused(URL, gh_answers=[reply])
    assert error.reason == reason


def listed(*rows):
    return said("".join(f"{oid}\t{name}\n" for oid, name in rows).encode())


def test_the_remote_look_reads_exactly_the_ref_it_asked_for():
    git = Script(listed((OID, REF)))
    assert github.ls_remote(git, "ROOT", URL, REF) == OID
    assert git.calls == [(("-C", "ROOT", "ls-remote", URL, REF), False)]
    assert git.keywords == [{"timeout": github.GIT_TIMEOUT_SECONDS}]
    other = Script(listed(("b" * 40, "refs/heads/other/" + REF)))
    assert github.ls_remote(other, "ROOT", URL, REF) is None
    assert github.ls_remote(Script(said(b"")), "ROOT", URL, REF) is None
    noisy = said(f"remote: counting\n{OID}\t{REF}\n".encode())
    assert github.ls_remote(Script(noisy), "ROOT", URL, REF) == OID
    sha256 = "c" * 64
    assert github.ls_remote(Script(listed((sha256, REF))), "ROOT", URL, REF) == sha256


@pytest.mark.parametrize("reply,auth", [
    (said(b"", None, timed_out=True), False), (said(b"x", 0, truncated=True), False),
    (said(b"fatal: unable to access\n", 128), False),
    (said(b"fatal: Authentication failed for 'x'\n", 128), True),
    (said(b"fatal: could not read Username for 'https://github.com': terminal prompts "
          b"disabled\n", 128), True),
    (said(b"git@github.com: Permission denied (publickey).\n", 128), True),
    (said(b"fatal: unable to access: The requested URL returned error: 403\n", 128), True),
    (listed((OID, REF), ("b" * 40, REF)), False)])
def test_a_remote_that_did_not_answer_says_whether_it_refused_to_sign_git_in(reply, auth):
    with pytest.raises(github.RemoteUnanswered) as caught:
        github.ls_remote(Script(reply), "ROOT", URL, REF)
    assert caught.value.auth is auth


def test_one_refusal_answers_for_every_fault_of_the_road_and_names_nothing_but_a_reason():
    def wire(error):
        return github.refusal(error).as_dict()["error"]

    assert wire(github.PublishRefused("push_rejected"))["detail"] == {"reason": "push_rejected"}
    assert wire(github.PublishRefused("pr_mismatch", "other_base"))["detail"] == {
        "reason": "pr_mismatch", "mismatch": "other_base"}
    assert wire(SnapshotRefused("snapshot_damaged"))["detail"] == {"reason": "snapshot_damaged"}
    assert wire(GhUnavailable("version_changed"))["detail"] == {
        "tool": "gh", "reason": "version_changed"}
    assert wire(GitReadFailed("tool_unavailable", reason="missing"))["detail"] == {
        "tool": "git", "reason": "missing"}
    assert wire(GitReadFailed("git_timed_out"))["detail"] == {"reason": "git_timed_out"}
    assert wire(OSError("disk"))["detail"] == {"reason": "git_failed"}
    assert wire(UnicodeError("x"))["detail"] == {"reason": "git_failed"}
    assert isinstance(github.refusal(OSError()), ApiRefusal)


def test_a_server_without_one_of_its_two_readers_refuses_with_tool_unavailable_naming_it():
    api = type("Api", (), {"_project_git": object(), "_project_gh": object()})()
    assert github.readers(api) == (api._project_git, api._project_gh)
    api._project_gh = None
    with pytest.raises(ApiRefusal) as no_gh:
        github.readers(api)
    assert no_gh.value.as_dict()["error"]["detail"] == {"tool": "gh", "reason": "not_pinned"}
    api._project_git = None
    with pytest.raises(ApiRefusal) as no_git:
        github.readers(api)
    assert no_git.value.as_dict()["error"]["detail"] == {"tool": "git", "reason": "not_pinned"}
    assert github.FAULTS == (github.PublishRefused, SnapshotRefused, GhUnavailable,
                             GitReadFailed, OSError, UnicodeError)


def test_a_terminal_reads_a_word_back_as_the_same_text_and_a_run_has_one_lock():
    assert github.shell_word("refs/heads/conduct/run-001") == "refs/heads/conduct/run-001"
    assert github.shell_word("a b") == "'a b'"
    assert github.shell_word("it's;rm") == "'it'\\''s;rm'"
    assert github.publish_lock("/r", "run-1") is github.publish_lock("/r", "run-1")
    assert github.publish_lock("/r", "run-1") is not github.publish_lock("/r", "run-2")
    assert github.publish_lock("/r", "run-1") is not github.publish_lock("/s", "run-1")
