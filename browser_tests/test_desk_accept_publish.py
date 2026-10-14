"""The accepted result goes to GitHub and into a pull request on the real desk (spec 9.7).

One real server over a finished run, the product's own Git reader, a bare repository on disk for
the remote, and a scripted `gh` as a real executable. The project's remote really is
`https://github.com/o/r.git`: the test-only wrapper of `tests/accept_remote.py` rewrites that
address to the bare repository for `push` and `ls-remote` ONLY, and refuses any other address for
those two, so no step here can reach a real host. The person does what a person does: preview,
review, commit, then the push (terms, review, send) and the pull request (review, create), each
a press of its own. A result of this file is the card on a fake `gh`, not the live GitHub.

What is held, in both languages: the full path, with the command the card shows being the command
that was run; an answer that is not known leaves only "Check again", and the check looks and never
acts, so the branch is pushed once and the pull request is created once.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, expect

from browser_tests.test_desk_accept import (  # noqa: F401  (accept_server is a fixture)
    COMMIT, PREVIEW, REVIEW, _Desk, _desk, accept_server)
from tests import _fakegh
from tests.accept_remote import BRANCH, TIMED_OUT, URL, Remote, remote_oid, with_gh
from tests.git_repo_helpers import git, needs_git
from tests.test_accept_context import RUN

PUSH_PATH = f"/command/runs/{RUN}/accept/push"
PULL_PATH = f"/command/runs/{RUN}/accept/pull-request"
PULL_URL = "https://github.com/o/r/pull/"
#: A step's controls are keyed by language-free names, so one selector serves both languages.
PUSH = {name: f'[data-focus-key="accept:push:desk.accept.{name}"]'
        for name in ("push.terms", "review", "push.action", "check", "push.again")}
PULL = {name: f'[data-focus-key="accept:pr:desk.accept.{name}"]'
        for name in ("review", "pr.action", "check", "pr.again")}
BODY = '[data-focus-key="desk.accept.pr.body"]'
ANY_PUSH_BUTTON = '[data-focus-key^="accept:push:"]'
ANY_PULL_BUTTON = '[data-focus-key^="accept:pr:"]'
LANGUAGES = ["en", "ru"]
#: What the card says in each language, as the catalogue spells it.
SENT = {"en": "Sent to GitHub", "ru": "Отправлено на GitHub"}
UNKNOWN_PUSH = {"en": "The outcome of the send is unknown.", "ru": "Исход отправки неизвестен."}
UNKNOWN_PULL = {"en": "The outcome of the creation is unknown.",
                "ru": "Исход создания неизвестен."}


@dataclass
class Rig:
    """What the test holds beside the page: the project, its remote and the scripted gh."""

    root: Path
    bare: Path
    remote: Remote
    gh: SimpleNamespace

    def oid(self) -> str:
        """The commit the accepted branch holds in the project."""
        return git("rev-parse", BRANCH, cwd=self.root).stdout.decode().strip()

    def base(self) -> str:
        """The branch the project stands on, which the card offers as the base."""
        return git("symbolic-ref", "--short", "HEAD", cwd=self.root).stdout.decode().strip()

    def gh_calls(self, key: str) -> list[dict]:
        return [call for call in _fakegh.calls(self.gh.dir) if call["key"] == key]

    def script(self, replies: dict) -> None:
        _fakegh.script(self.gh.dir, {"repo view": [_fakegh.repo_view()], **replies})


@pytest.fixture
def published(tmp_path, accept_server) -> tuple[str, Rig]:
    """The accept server of the existing witness, with a GitHub-shaped remote that is a bare
    repository on disk and a scripted gh pinned for the child."""
    url, root, httpd = accept_server
    git("remote", "add", "origin", URL, cwd=root)
    bare = tmp_path / "remote.git"
    git("init", "--bare", "-q", str(bare), cwd=tmp_path)
    remote = Remote(httpd.command_api._project_git, bare)
    httpd.command_api._project_git = remote
    gh = with_gh(tmp_path, httpd.command_api, root)
    return url, Rig(root, bare, remote, gh)


def _into_the_branch(desk: _Desk) -> None:
    """Preview, review and commit, as the person does; the push step shows when it is done."""
    desk.card.locator(PREVIEW).click()
    expect(desk.card).to_contain_text("new.txt")
    desk.card.locator(REVIEW).click()
    desk.card.locator(COMMIT).click()
    expect(desk.card.locator(PUSH["push.terms"])).to_be_enabled()


def _read_terms(desk: _Desk) -> dict:
    """Press "read the terms"; the card must show the command the server named."""
    with desk.page.expect_response(lambda r: urlsplit(r.url).path == PUSH_PATH) as seen:
        desk.card.locator(PUSH["push.terms"]).click()
    terms = seen.value.json()["push_terms"]
    expect(desk.card.locator("pre")).to_have_text(terms["command"])
    for fact in (terms["repo"], terms["push_url"], terms["ref"], terms["commit"]):
        expect(desk.card).to_contain_text(fact)
    return terms


def _send(desk: _Desk) -> None:
    desk.card.locator(PUSH["review"]).click()
    desk.card.locator(PUSH["push.action"]).click()


def _accept_and_send(desk: _Desk) -> None:
    """Commit, read the terms and press send."""
    _into_the_branch(desk)
    _read_terms(desk)
    _send(desk)


@needs_git
@pytest.mark.parametrize("language", LANGUAGES)
def test_the_accepted_result_is_sent_to_github_and_opened_as_a_pull_request_one_press_each(
        chromium: Browser, published, language: str):
    url, rig = published
    head = git("rev-parse", "HEAD", cwd=rig.root).stdout
    with _desk(chromium, url, language) as desk:
        _into_the_branch(desk)
        oid, base = rig.oid(), rig.base()
        rig.script({"pr list": [_fakegh.pr_list(),
                                _fakegh.pr_list(_fakegh.pr_row(7, oid, base=base, head=BRANCH))],
                    "pr create": [_fakegh.created(7)]})
        assert rig.remote.pushes() == [] and rig.gh_calls("pr create") == []
        _read_terms(desk)
        assert rig.remote.pushes() == []
        _send(desk)
        expect(desk.card).to_contain_text(SENT[language])
        expect(desk.card.locator(PULL["review"])).to_be_enabled()
        assert remote_oid(rig.bare) == oid and len(rig.remote.pushes()) == 1
        assert rig.gh_calls("pr create") == []
        command = desk.card.locator("pre").inner_text()
        body = desk.card.locator(BODY).input_value()
        desk.card.locator(PULL["review"]).click()
        desk.card.locator(PULL["pr.action"]).click()
        link = desk.card.locator("a")
        expect(link).to_have_attribute("href", PULL_URL + "7")
        (made,) = rig.gh_calls("pr create")
        assert made["argv"] == shlex.split(command)[1:] and made["stdin"] == body
        assert f"--base {base} --head {BRANCH}" in command and "--draft" not in command
        for name, count in ((PUSH_PATH, 2), (PULL_PATH, 1)):
            assert desk.count("POST", name) == count, name
        desk.page.reload(wait_until="load")
        expect(desk.page.locator("#deskShell")).to_have_attribute("data-connection", "open")
        expect(link).to_have_attribute("href", PULL_URL + "7")
        expect(desk.card.locator(ANY_PUSH_BUTTON)).to_have_count(0)
        expect(desk.card.locator(ANY_PULL_BUTTON)).to_have_count(0)
        assert git("rev-parse", "HEAD", cwd=rig.root).stdout == head
        assert len(rig.remote.pushes()) == 1 and len(rig.gh_calls("pr create")) == 1
        assert desk.errors == []


@needs_git
@pytest.mark.parametrize("language", LANGUAGES)
def test_a_push_whose_answer_is_not_known_is_checked_and_the_branch_is_never_sent_twice(
        chromium: Browser, published, language: str):
    url, rig = published
    looks: list[int] = []

    def on_look(run):
        looks.append(1)
        return TIMED_OUT if len(looks) == 2 else run()

    rig.remote.on_look = on_look
    with _desk(chromium, url, language) as desk:
        _accept_and_send(desk)
        expect(desk.card).to_contain_text(UNKNOWN_PUSH[language])
        expect(desk.card.locator(ANY_PUSH_BUTTON)).to_have_count(1)
        expect(desk.card.locator(PUSH["check"])).to_be_enabled()
        assert remote_oid(rig.bare) == rig.oid() and len(rig.remote.pushes()) == 1
        desk.card.locator(PUSH["check"]).click()
        expect(desk.card).to_contain_text(SENT[language])
        assert len(looks) == 3 and len(rig.remote.pushes()) == 1
        assert desk.count("POST", PUSH_PATH) == 3
        assert desk.errors == []


@needs_git
@pytest.mark.parametrize("language", LANGUAGES)
def test_a_pull_request_whose_answer_is_not_known_is_checked_and_created_only_once(
        chromium: Browser, published, language: str):
    url, rig = published
    with _desk(chromium, url, language) as desk:
        _accept_and_send(desk)
        oid, base = rig.oid(), rig.base()
        rig.script({"pr list": [_fakegh.pr_list(), _fakegh.pr_list(),
                                _fakegh.pr_list(_fakegh.pr_row(8, oid, base=base, head=BRANCH))],
                    "pr create": [_fakegh.said(exit=1)]})
        expect(desk.card.locator(PULL["review"])).to_be_enabled()
        desk.card.locator(PULL["review"]).click()
        desk.card.locator(PULL["pr.action"]).click()
        expect(desk.card).to_contain_text(UNKNOWN_PULL[language])
        expect(desk.card.locator(ANY_PULL_BUTTON)).to_have_count(1)
        expect(desk.card.locator(PULL["check"])).to_be_enabled()
        assert len(rig.gh_calls("pr create")) == 1
        desk.card.locator(PULL["check"]).click()
        expect(desk.card.locator("a")).to_have_attribute("href", PULL_URL + "8")
        assert len(rig.gh_calls("pr create")) == 1 and len(rig.gh_calls("pr list")) == 3
        assert desk.count("POST", PULL_PATH) == 2
        assert desk.errors == []
