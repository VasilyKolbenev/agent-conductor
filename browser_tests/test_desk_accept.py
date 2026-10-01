"""One live Desk acceptance path: saved result, real Git preview, local branch and commit."""
from __future__ import annotations

import threading
import os
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, expect

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
def accept_server(tmp_path, monkeypatch) -> Iterator[tuple[str, object]]:
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
        yield f"http://{host}:{port}/panel/desk.html", root
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


@needs_git
def test_accept_preview_then_exact_human_confirmation_creates_only_local_branch(
        chromium: Browser, accept_server):
    url, root = accept_server
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
