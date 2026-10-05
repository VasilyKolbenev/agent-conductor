"""One live Desk acceptance path: saved result, real Git preview, local branch and commit."""
from __future__ import annotations

import threading
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Locator, Page, Route, expect

from conductor import ownership_transition, server
from conductor.command.adapters.process import ProcessRunner
from conductor.command.project_git import process_git_read
from conductor.ownership import data_root
from tests.git_repo_helpers import GIT, ISOLATED, KEPT, git, needs_git
from tests.test_accept_commit import prepared
from tests.test_accept_context import RUN, TASK
from tests import test_accept_context as accept_fixture
from tests.test_store import write_project


@pytest.fixture
def accept_server(tmp_path, monkeypatch) -> Iterator[tuple[str, object, object]]:
    # The reusable acceptance fixture predates the Desk and freezes token_env
    # fields into its sample run. A Desk run read admits only public instance
    # id/adapter/model, so this live witness writes that production shape.
    config = {**accept_fixture.CONFIG, "instances": [
        {"id": row["id"], "adapter": row["adapter"]}
        for row in accept_fixture.CONFIG["instances"]]}
    with monkeypatch.context() as patch:
        patch.setattr(accept_fixture, "CONFIG", config)
        _api, root, _work, _saved = prepared(tmp_path)
    write_project(root)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    httpd = server.build(root, 0)
    # Activation moves conductor/ to conductor.v3/. Build this test-scoped real
    # Git reader afterwards, so its contained cwd names the active data root.
    cwd = data_root(root) / "git" / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    hooks = cwd.parent / "hooks-empty"
    hooks.mkdir(exist_ok=True)
    runner = ProcessRunner(root, environ={name: os.environ[name] for name in KEPT if name in os.environ})
    httpd.command_api._project_git = process_git_read(runner, GIT, str(cwd), env_allow=KEPT,
        index_root=root, env={**ISOLATED, "GIT_CONFIG_COUNT": "1",
                              "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(hooks)})
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/panel/desk.html", root, httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


@needs_git
def test_accept_preview_then_exact_human_confirmation_creates_only_local_branch(
        chromium: Browser, accept_server):
    url, root, _httpd = accept_server
    head = git("rev-parse", "HEAD", cwd=root).stdout
    context = chromium.new_context(viewport={"width": 1280, "height": 1000})
    try:
        page = context.new_page()
        page.set_default_timeout(10000)
        requests, errors, run_answers = [], [], []
        page.on("request", lambda request: requests.append(
            (request.method, urlsplit(request.url).path)))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: run_answers.append(
            (response.status, response.json()))
            if urlsplit(response.url).path == f"/command/runs/{RUN}" else None)
        page.goto(f"{url}#task={TASK}&run={RUN}&panel=run&lang=en", wait_until="load")
        # The stream's first full refresh reads the chosen run again. It is over when the
        # connection says open, so the person acts after it and not while it is under way.
        expect(page.locator("#deskShell")).to_have_attribute(
            "data-connection", "open", timeout=10000)
        page.locator('[data-focus-key="pult:actor-change"]').click()
        page.locator('[data-focus-key="pult:actor-name"]').fill("Owner")
        page.locator('[data-focus-key="pult:actor-save"]').click()
        card = page.locator("#deskRun .desk-accept")
        expect(card).to_be_visible()
        try:
            expect(card.locator('[data-focus-key="accept:detail:desk.accept.preview"]')).to_be_enabled()
        except AssertionError as failure:
            raise AssertionError({"run_answers": run_answers, "requests": requests,
                                  "page_errors": errors}) from failure
        assert ("GET", f"/command/runs/{RUN}/accept") in requests
        card.locator('[data-focus-key="accept:detail:desk.accept.preview"]').click()
        expect(card).to_contain_text("new.txt")
        expect(card).to_contain_text("Preview Author")
        expect(card.locator("pre").last).to_contain_text("+reviewed")
        card.locator('[data-focus-key="accept:detail:desk.accept.review"]').click()
        expect(card).to_contain_text("The current branch stays unchanged")
        card.locator('[data-focus-key="accept:detail:desk.accept.commit_action"]').click()
        record = card.locator(".desk-accept__fact")
        expect(record.filter(has_text="Created commit")).to_have_count(1)
        assert ("POST", f"/command/runs/{RUN}/accept/preview") in requests
        assert ("POST", f"/command/runs/{RUN}/accept/commit") in requests
        assert git("rev-parse", "HEAD", cwd=root).stdout == head
        branch = git("rev-parse", f"conduct/{RUN}", cwd=root).stdout.decode().strip()
        expect(record.filter(has_text="Created commit")).to_contain_text(branch)
        assert errors == []
    finally:
        context.close()


# -- the run read again while a person is partway through the acceptance --------------------------
#
# Every full refresh the desk makes (the stream's open and the first frame the server sends on it,
# any later state frame, the run panel's refresh door) reads the chosen run again, and while that
# read is out the scene says the run is "stale". What the person entered, the preview they read and
# the confirmation they gave belong to the run they were looking at, so a re-read that brings the
# same run in the same state keeps them. The scene's read is the run and its controls together, and
# the controls read is the one that is held here: it is made for the scene alone (the closing reads
# of finished tasks read the run too), so a held controls read is a scene that stands as stale until
# it lands. Nothing is slowed and nothing is raced: every window of the re-read can be judged.

ACCEPT_PATH = f"/command/runs/{RUN}/accept"
PREVIEW_PATH, COMMIT_PATH = f"{ACCEPT_PATH}/preview", f"{ACCEPT_PATH}/commit"
PREVIEW = '[data-focus-key="accept:detail:desk.accept.preview"]'
REVIEW = '[data-focus-key="accept:detail:desk.accept.review"]'
COMMIT = '[data-focus-key="accept:detail:desk.accept.commit_action"]'
BRANCH = '[data-focus-key="desk.accept.branch"]'
TITLE = '[data-focus-key="desk.accept.title"]'
CONFIRMING = "The current branch stays unchanged"
#: A press on a control that says it is unavailable: the host must refuse it on its own account.
FORCE_PRESS = "(node) => { node.disabled = false; node.click(); }"


class _Hold:
    """The answers of one URL: passed on until `hold()`, then kept back until `land()`.

    A set `rewrite` changes the JSON body of every answer that is passed on.
    """

    def __init__(self, page: Page, pattern: str) -> None:
        self.rewrite: Callable[[dict], dict] | None = None
        self._holding, self._kept = False, []
        page.route(pattern, self._answer)

    def _answer(self, route: Route) -> None:
        if self._holding:
            self._kept.append(route)
        else:
            self._pass_on(route)

    def _pass_on(self, route: Route) -> None:
        if self.rewrite is None:
            route.continue_()
        else:
            response = route.fetch()
            route.fulfill(response=response, json=self.rewrite(response.json()))

    def hold(self) -> None:
        self._holding = True

    def reached(self) -> bool:
        return bool(self._kept)

    def land(self) -> None:
        self._holding = False
        kept, self._kept = self._kept, []
        for route in kept:
            self._pass_on(route)

    def abort(self) -> None:
        kept, self._kept = self._kept, []
        for route in kept:
            route.abort()


@dataclass
class _Desk:
    """One window on the run, what it asked, and the answers a test may hold or rewrite."""

    page: Page
    requests: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_read = _Hold(self.page, f"**/command/runs/{RUN}")
        self.controls_read = _Hold(self.page, f"**/command/runs/{RUN}/controls")
        self.preview_post = _Hold(self.page, f"**{PREVIEW_PATH}")

    @property
    def card(self) -> Locator:
        return self.page.locator("#deskRun .desk-accept")

    @property
    def scene(self) -> Locator:
        return self.page.locator("#deskScene")

    def count(self, method: str, path: str) -> int:
        return self.requests.count((method, path))

    def until(self, what: str, done: Callable[[], Any]) -> None:
        """Wait, pumping the page, until a fact of this side of the wire holds."""
        for _ in range(160):
            if done():
                return
            self.page.wait_for_timeout(50)
        raise AssertionError(f"the page never reached: {what}")

    def reread(self, start: Callable[[], None]) -> None:
        """`start` makes a full refresh; the desk stands on its earlier read of the run until
        `land()`: the controls read the new one needs is held."""
        self.controls_read.hold()
        start()
        self.until("the scene's read of the run is held", self.controls_read.reached)
        expect(self.scene).to_have_attribute("data-state", "stale")

    def land(self) -> None:
        """The held read lands and the scene is ready again."""
        self.controls_read.land()
        expect(self.scene).to_have_attribute("data-state", "ready")


@contextmanager
def _desk(chromium: Browser, url: str) -> Iterator[_Desk]:
    """A window on the run with a name given, once the stream has opened: the person acts after
    the first refresh of the connection and not while it is under way."""
    context = chromium.new_context(viewport={"width": 1280, "height": 1000})
    desk = None
    try:
        page = context.new_page()
        page.set_default_timeout(10000)
        desk = _Desk(page)
        page.on("request", lambda request: desk.requests.append(
            (request.method, urlsplit(request.url).path)))
        page.on("pageerror", lambda error: desk.errors.append(str(error)))
        page.goto(f"{url}#task={TASK}&run={RUN}&panel=run&lang=en", wait_until="load")
        expect(page.locator("#deskShell")).to_have_attribute(
            "data-connection", "open", timeout=10000)
        page.locator('[data-focus-key="pult:actor-change"]').click()
        page.locator('[data-focus-key="pult:actor-name"]').fill("Owner")
        page.locator('[data-focus-key="pult:actor-save"]').click()
        expect(desk.card).to_be_visible()
        expect(desk.card.locator(PREVIEW)).to_be_enabled()
        yield desk
    finally:
        if desk is not None:
            for held in (desk.run_read, desk.controls_read, desk.preview_post):
                held.abort()
        context.close()


def _enter_and_read_preview(desk: _Desk) -> None:
    desk.card.locator(BRANCH).fill("conduct/chosen")
    desk.card.locator(TITLE).fill("Chosen title")
    desk.card.locator(PREVIEW).click()
    expect(desk.card).to_contain_text("new.txt")


def _entries_and_preview_stand(desk: _Desk) -> None:
    expect(desk.card.locator(BRANCH)).to_have_value("conduct/chosen")
    expect(desk.card.locator(TITLE)).to_have_value("Chosen title")
    expect(desk.card).to_contain_text("new.txt")
    expect(desk.card).to_contain_text("conduct/chosen")


@needs_git
def test_a_re_read_of_the_same_run_keeps_the_entries_and_the_preview_and_refuses_presses_meanwhile(
        chromium: Browser, accept_server):
    url, _root, httpd = accept_server
    with _desk(chromium, url) as desk:
        _enter_and_read_preview(desk)
        desk.reread(httpd.clients.publish_state)
        _entries_and_preview_stand(desk)
        expect(desk.card.locator(REVIEW)).to_be_disabled()
        expect(desk.card.locator(PREVIEW)).to_be_disabled()
        desk.card.locator(REVIEW).evaluate(FORCE_PRESS)
        desk.card.locator(PREVIEW).evaluate(FORCE_PRESS)
        expect(desk.card).not_to_contain_text(CONFIRMING)
        _entries_and_preview_stand(desk)
        desk.land()
        _entries_and_preview_stand(desk)
        expect(desk.card.locator(REVIEW)).to_be_enabled()
        expect(desk.card.locator(PREVIEW)).to_be_enabled()
        desk.card.locator(REVIEW).click()
        expect(desk.card).to_contain_text(CONFIRMING)
        assert desk.count("GET", ACCEPT_PATH) == 1 and desk.count("POST", PREVIEW_PATH) == 1
        assert desk.errors == []


@needs_git
def test_a_re_read_of_the_same_run_keeps_the_confirmation_and_commits_only_once_it_has_landed(
        chromium: Browser, accept_server):
    url, root, httpd = accept_server
    head = git("rev-parse", "HEAD", cwd=root).stdout
    with _desk(chromium, url) as desk:
        _enter_and_read_preview(desk)
        desk.card.locator(REVIEW).click()
        expect(desk.card).to_contain_text(CONFIRMING)
        desk.reread(httpd.clients.publish_state)
        _entries_and_preview_stand(desk)
        expect(desk.card).to_contain_text(CONFIRMING)
        expect(desk.card.locator(COMMIT)).to_be_disabled()
        desk.card.locator(COMMIT).evaluate(FORCE_PRESS)
        expect(desk.card).to_contain_text(CONFIRMING)
        desk.land()
        expect(desk.card).to_contain_text(CONFIRMING)
        expect(desk.card.locator(COMMIT)).to_be_enabled()
        assert desk.count("GET", ACCEPT_PATH) == 1
        desk.card.locator(COMMIT).click()
        record = desk.card.locator(".desk-accept__fact")
        expect(record.filter(has_text="Created commit")).to_have_count(1)
        assert desk.count("POST", COMMIT_PATH) == 1
        assert git("rev-parse", "HEAD", cwd=root).stdout == head
        git("rev-parse", "conduct/chosen", cwd=root)
        assert desk.errors == []


@needs_git
def test_a_preview_answer_that_lands_while_the_run_is_read_again_is_kept(
        chromium: Browser, accept_server):
    url, _root, httpd = accept_server
    with _desk(chromium, url) as desk:
        desk.card.locator(BRANCH).fill("conduct/chosen")
        desk.card.locator(TITLE).fill("Chosen title")
        desk.preview_post.hold()
        desk.card.locator(PREVIEW).click()
        desk.until("the preview request is held", desk.preview_post.reached)
        desk.reread(httpd.clients.publish_state)
        desk.preview_post.land()
        expect(desk.card).to_contain_text("new.txt")
        expect(desk.scene).to_have_attribute("data-state", "stale")
        desk.land()
        _entries_and_preview_stand(desk)
        expect(desk.card.locator(REVIEW)).to_be_enabled()
        assert desk.count("GET", ACCEPT_PATH) == 1 and desk.count("POST", PREVIEW_PATH) == 1
        assert desk.errors == []


@needs_git
def test_the_run_panels_own_refresh_of_the_same_run_keeps_the_entries_and_the_preview(
        chromium: Browser, accept_server):
    url, _root, _httpd = accept_server
    with _desk(chromium, url) as desk:
        _enter_and_read_preview(desk)
        refresh = desk.page.locator('#deskRun [data-focus-key="action:refreshRuns"]')
        desk.reread(refresh.click)
        _entries_and_preview_stand(desk)
        expect(desk.card.locator(REVIEW)).to_be_disabled()
        desk.land()
        _entries_and_preview_stand(desk)
        expect(desk.card.locator(REVIEW)).to_be_enabled()
        assert desk.count("GET", ACCEPT_PATH) == 1
        assert desk.errors == []


@needs_git
def test_a_re_read_that_lands_with_a_changed_run_state_resets_the_entries_and_reads_facts_again(
        chromium: Browser, accept_server):
    url, _root, httpd = accept_server
    with _desk(chromium, url) as desk:
        _enter_and_read_preview(desk)
        # From here on the server's run reads say the run is active: the next full refresh lands
        # with another state of the run than the one the person was looking at, and every
        # refresh after it lands with that same state.
        desk.run_read.rewrite = lambda body: {**body, "run": {**body["run"], "status": "active"}}
        desk.reread(httpd.clients.publish_state)
        desk.land()
        expect(desk.card.locator(PREVIEW)).to_be_enabled()
        expect(desk.card.locator(BRANCH)).to_have_value("")
        expect(desk.card.locator(TITLE)).to_have_value("")
        expect(desk.card).not_to_contain_text("new.txt")
        assert desk.count("GET", ACCEPT_PATH) == 2
        assert desk.errors == []
