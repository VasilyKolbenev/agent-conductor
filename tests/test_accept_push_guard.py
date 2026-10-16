"""The one remote a push by address is given on its command line (spec 9.7, Git 2.56).

From Git 2.56 a push to an address updates the remote-tracking ref of the one configured remote
whose push address is that address, which spec 9.7 promises it never does. A second remote that
exists on the command of the push only, with the same address and no fetch refspec, makes the match
not unique. It must be a name that no configured remote uses: a remote of that name, or one that
has a `pushurl` of its own, leaves the project's own remote the only match. One builder makes the
words after `git` for the terms and for the run, so the command the card shows is the command that
runs, and when the name or any fact changes the digest changes and the terms are read again.

This host's git is older than 2.56 and writes the tracking ref either way: the effect is witnessed
by the git 2.56 job (see `test_push_argv_sends_no_tags_and_no_submodules`, which prints the git
version); the tests here hold the condition (how many remotes have the pushed address) and the
command.
"""
import hashlib
import json

import pytest

from conductor.command import accept_push
from conductor.command.accept_github import PublishRefused
from conductor.command.project_git import GitAnswer, GitReadFailed
from tests.accept_remote import (
    GUARD, REF, URL, config_text, confirm, digest_of, guard_of, guard_pair, refs_text,
    remotes_with_push_address, terms, words_of)
from tests.git_repo_helpers import git, needs_git
from tests.test_accept_push import accepted_with_gh, reason_of

OTHER = "https://example.invalid/other.git"
OTHER_PUSH = "https://example.invalid/other-push.git"
CONFIG_READ = ["-C", "/project", "config", "-z", "--name-only", "--get-regexp", r"^remote\."]


class Config:
    """A git reader that answers the read of the remote settings and records what it was asked."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, args, separate_stderr=False, **keywords):
        self.calls.append((list(args), separate_stderr))
        return self.answer


def keys(*names):
    """The output of `config -z --name-only --get-regexp`: the keys, each ended by a NUL."""
    return "".join(name + "\0" for name in names).encode()


def chosen(answer):
    return accept_push.guard_name(Config(answer), "/project")


# -- the choice of the name (R1): free among the settings git resolves now ---------------------

def test_the_name_is_read_from_the_settings_git_resolves_and_nothing_is_written():
    reader = Config(GitAnswer(1, b""))
    assert accept_push.guard_name(reader, "/project") == GUARD
    assert reader.calls == [(CONFIG_READ, True)]


def test_no_remote_in_the_settings_leaves_the_first_name_free():
    assert chosen(GitAnswer(1, b"")) == GUARD
    assert chosen(GitAnswer(0, keys("remote.pushdefault"))) == GUARD


@pytest.mark.parametrize("taken, expected", [
    (["remote.conduct-no-tracking.url"], "conduct-no-tracking-2"),
    (["remote.conduct-no-tracking.pushurl"], "conduct-no-tracking-2"),
    (["remote.conduct-no-tracking.fetch"], "conduct-no-tracking-2"),
    (["remote.Conduct-No-Tracking.url"], "conduct-no-tracking-2"),
    (["remote.conduct-no-tracking.url", "remote.conduct-no-tracking-2.pushurl"],
     "conduct-no-tracking-3"),
    (["remote.origin.url", "remote.origin.fetch", "remote.my.remote.url"], GUARD)])
def test_the_name_is_the_first_that_no_setting_of_any_remote_uses(taken, expected):
    assert chosen(GitAnswer(0, keys(*taken))) == expected


def test_the_choice_is_the_same_while_the_settings_are_the_same():
    answer = GitAnswer(0, keys("remote.origin.url", "remote.conduct-no-tracking.url"))
    assert chosen(answer) == chosen(answer) == "conduct-no-tracking-2"


@pytest.mark.parametrize("answer, code", [
    (GitAnswer(128, b"fatal: bad config\n"), "git_failed"),
    (GitAnswer(None, b"", timed_out=True), "git_timed_out"),
    (GitAnswer(0, keys("remote.origin.url"), truncated=True), "git_failed")])
def test_a_read_of_the_settings_that_fails_is_a_failure_of_git_and_no_name_is_guessed(
        answer, code):
    with pytest.raises(GitReadFailed) as failed:
        chosen(answer)
    assert failed.value.code == code


def test_when_every_name_asked_for_is_taken_the_push_is_refused_and_not_run():
    taken = [GUARD] + [f"{GUARD}-{turn}" for turn in range(2, accept_push.GUARD_TRIES + 1)]
    with pytest.raises(PublishRefused) as refused:
        chosen(GitAnswer(0, keys(*(f"remote.{name}.url" for name in taken))))
    assert refused.value.reason == "git_failed"


# -- the collision, on a real repository (R1 witness) ------------------------------------------

def collided_with_pushurl(root):
    """A remote named like the guard, with a url, a fetch refspec and a pushurl of its own."""
    git("remote", "add", GUARD, OTHER, cwd=root)
    git("config", f"remote.{GUARD}.pushurl", OTHER_PUSH, cwd=root)
    return "origin"


def origin_named_like_the_guard(root):
    """The remote the owner picks is itself called what the guard would be called."""
    git("remote", "rename", "origin", GUARD, cwd=root)
    return GUARD


def left_as_they_were(root, refs, config):
    """What a push by address leaves in the project: every ref and every setting as they were,
    and no remote-tracking ref, which Git 2.56 writes for the one remote with the pushed address.
    The effect shows only on a git of 2.56 or later; this host's git writes none either way."""
    assert refs_text(root) == refs
    assert config_text(root) == config
    assert git("for-each-ref", "refs/remotes", cwd=root).stdout == b""


@needs_git
@pytest.mark.parametrize("collide, still_there", [
    (collided_with_pushurl, ["origin"]), (origin_named_like_the_guard, [GUARD])])
def test_a_remote_called_like_the_guard_does_not_defeat_it(tmp_path, collide, still_there):
    """The fixed name leaves ONE remote with the pushed address (the guard is void); the name
    the product picks leaves two, and the settings of the remote that held the name are as they
    were."""
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    selected = collide(root)
    refs, config = refs_text(root), config_text(root)
    digest = terms(api, record, selected).payload["push_terms"]["push_digest"]
    answer = confirm(api, record, digest, remote=selected)
    assert answer.status == 201, answer.payload
    left_as_they_were(root, refs, config)
    pushed, = remote.pushes()
    name = guard_of(pushed)
    assert name == "conduct-no-tracking-2"
    assert remotes_with_push_address(root, guard_pair(GUARD), URL) == still_there
    assert remotes_with_push_address(root, words_of(pushed)[:2], URL) == sorted(
        [*still_there, name])


@needs_git
def test_the_guard_is_added_beside_a_project_whose_own_remote_has_a_pushurl(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    git("remote", "set-url", "origin", OTHER, cwd=root)
    git("config", "remote.origin.pushurl", URL, cwd=root)
    refs, config = refs_text(root), config_text(root)
    digest = digest_of(api, record)
    assert confirm(api, record, digest).status == 201
    left_as_they_were(root, refs, config)
    pushed, = remote.pushes()
    assert guard_of(pushed) == GUARD
    assert remotes_with_push_address(root, words_of(pushed)[:2], URL) == [GUARD, "origin"]


# -- one builder for the shown command and the run (R2) ----------------------------------------

@needs_git
def test_the_command_the_terms_show_is_the_command_the_push_runs_word_for_word(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    shown = terms(api, record).payload["push_terms"]
    assert confirm(api, record, shown["push_digest"]).status == 201
    pushed, = remote.pushes()
    assert shown["command"] == " ".join(["git", *words_of(pushed)])
    assert shown["command"].startswith(f"git -c remote.{GUARD}.url={URL} push ")


@needs_git
def test_the_digest_is_of_the_facts_and_of_the_command_that_will_run(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    shown = terms(api, record).payload["push_terms"]
    core = {"acceptance_id": record["acceptance_id"], "commit": record["commit"],
            "remote": "origin", "push_url": URL, "repo": "o/r", "ref": REF,
            "command": shown["command"]}
    assert shown["push_digest"] == "sha256:" + hashlib.sha256(json.dumps(
        core, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


@needs_git
def test_a_name_taken_after_the_terms_were_shown_refuses_the_press_and_renews_the_terms(tmp_path):
    """Between the terms and the press a remote takes the guard's name. The press does not run
    the other command: it is refused as changed terms, nothing leaves, and the terms read next
    show the other name and the other digest, which then runs, as shown."""
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    first = terms(api, record).payload["push_terms"]
    git("remote", "add", GUARD, OTHER, cwd=root)
    git("config", f"remote.{GUARD}.pushurl", OTHER_PUSH, cwd=root)
    assert reason_of(confirm(api, record, first["push_digest"])) == "push_terms_changed"
    assert remote.pushes() == [] and "ls-remote" not in remote.verbs()
    assert refs_text(bare) == b""
    renewed = terms(api, record).payload["push_terms"]
    assert renewed["push_digest"] != first["push_digest"]
    assert renewed["command"] == first["command"].replace(
        f"remote.{GUARD}.url", f"remote.{GUARD}-2.url")
    assert confirm(api, record, renewed["push_digest"]).status == 201
    pushed, = remote.pushes()
    assert renewed["command"] == " ".join(["git", *words_of(pushed)])
    assert guard_of(pushed) == f"{GUARD}-2"


@needs_git
def test_a_name_freed_after_the_terms_were_shown_also_renews_them(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    git("remote", "add", GUARD, OTHER, cwd=root)
    taken = terms(api, record).payload["push_terms"]
    assert f"remote.{GUARD}-2.url" in taken["command"]
    git("remote", "remove", GUARD, cwd=root)
    assert reason_of(confirm(api, record, taken["push_digest"])) == "push_terms_changed"
    assert remote.pushes() == []
    freed = terms(api, record).payload["push_terms"]
    assert freed["push_digest"] != taken["push_digest"]
    assert f"remote.{GUARD}.url" in freed["command"]


@needs_git
def test_the_terms_read_the_settings_and_write_none(tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    config, refs = config_text(root), refs_text(root)
    for _ in range(2):
        assert terms(api, record).status == 200
    assert config_text(root) == config and refs_text(root) == refs
    assert "push" not in remote.verbs() and "ls-remote" not in remote.verbs()


@needs_git
def test_while_the_push_runs_two_configured_remotes_have_the_pushed_address(tmp_path):
    """The condition of the Git 2.56 tracking rule (`repo_remote_for_push_tracking`): the
    project's own remote alone is the one match, which writes `refs/remotes/origin/...`; with the
    guard there are two, which write none."""
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    assert confirm(api, record, digest_of(api, record)).status == 201
    pushed, = remote.pushes()
    assert remotes_with_push_address(root, [], URL) == ["origin"]
    assert remotes_with_push_address(root, words_of(pushed)[:2], URL) == [GUARD, "origin"]
