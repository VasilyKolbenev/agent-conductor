"""The first task can recover a readable source without re-entering the goal or material."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from multiprocessing import get_context
from threading import Thread
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from conductor import ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore
from conductor.tool_pins import pin_tool
from tests.git_repo_helpers import GIT, git
from tests.test_command_workflow_routes import contracts
from tests.test_policy_runtime import PD
from tests.test_standard_cycle_checker import _StandardAdapter
from tests.test_store import good_lane, write_project


def serve_project(root, port, ready, stop, subscriptions):
    names = () if subscriptions is False else ("claude-code", "codex")
    adapters = [_StandardAdapter(RunStore(root), adapter_id=name) for name in names]
    http = server.build(root, port, registry=AdapterRegistry(adapters))
    declared = contracts(reachable=names, known=names)
    http.command_api._providers = tuple(replace(row, auth="subscription") for row in declared) if subscriptions else declared
    http.command_api._offered_provider_ids = frozenset(names)
    http.command_api._policy.provider_digest = lambda _: PD
    http.command_api._policy.provider_facts = None
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        ready.put(http.server_port)
        stop.wait()
    finally:
        http.shutdown()
        thread.join(timeout=5)
        http.server_close()
        assert not thread.is_alive()


@contextmanager
def active_project(root, port=0, subscriptions=None):
    # A real restart ends the old process and its keep-alive HTTP connections.
    ctx = get_context("spawn")
    ready, stop = ctx.Queue(), ctx.Event()
    worker = ctx.Process(target=serve_project, args=(root, port, ready, stop, subscriptions))
    worker.start()
    try:
        yield ready.get(timeout=30)
    finally:
        stop.set()
        worker.join(15)
        assert worker.exitcode == 0


@pytest.mark.parametrize(("lang", "width"), [("ru", 375), ("en", 1280)])
def test_pin_git_then_resume_the_source_in_the_open_form(chromium, tmp_path, monkeypatch, lang, width):
    pin_home = tmp_path / "test-tools"
    monkeypatch.setenv("CONDUCT_HOME", str(pin_home))
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    git("init", cwd=root)
    contents = b"A committed source file.\n"
    (root / "source.txt").write_bytes(contents)
    git("add", "--", "source.txt", cwd=root)
    git("commit", "-m", "Add source for the local wizard test", cwd=root)
    context = chromium.new_context(viewport={"width": width, "height": 900})
    try:
        page = context.new_page()
        posts = []
        page.on("request", lambda req: posts.append((urlsplit(req.url).path, req.post_data_json))
                if req.method == "POST" else None)
        with active_project(root) as port:
            page.goto(f"http://127.0.0.1:{port}/panel/desk.html#lang={lang}")
            page.locator('[data-focus-key="pult:actor-change"]').click()
            page.locator('[data-focus-key="pult:actor-name"]').fill("owner")
            page.locator('[data-focus-key="pult:actor-save"]').click()
            page.locator("#deskNewTask").click()
            form = page.locator("#deskWizard")

            def field(name):
                return form.locator(f'[data-focus="wizard:{name}"]')

            goal = "Check the committed source."
            material = "Read source.txt from the committed version."
            field("brief").fill(goal)
            form.locator('[data-guide-details="optional"] summary').click()
            field("add:plan").click()
            card = form.locator('[data-card][data-kind="plan"]')
            card.locator('input[name="title"]').fill("Review")
            card.locator('textarea[name="content"]').fill(material)
            panel = form.locator('[data-git-state="unavailable"]')
            expect(panel).to_be_visible()
            expect(field("next")).to_be_disabled()
            expect(panel).to_contain_text("Hub")
            expect(panel).to_contain_text("conduct tools pin git --path")
            expect(panel).to_contain_text("перезапуст" if lang == "ru" else "restart", ignore_case=True)
            expect(field("git:run_without_git")).to_have_count(0)
            expect(field("git:reread")).to_be_visible()
            assert not any(path == "/command/tasks" for path, _ in posts)
            pin_tool("git", GIT, folder=pin_home)
            field("git:reread").click()
            expect(panel).to_be_visible()  # The first server checked its pin once for its lifetime.
        with active_project(root, port):
            observed = page.request.get(f"http://127.0.0.1:{port}/command/project/git").json()["git"]
            assert observed["state"] == "repo", observed
            with page.expect_response(lambda res: urlsplit(res.url).path == "/command/project/git", timeout=8000) as reading:
                field("git:reread").click()
            answer = reading.value
            assert answer.ok and answer.json()["git"]["state"] == "repo", (answer.status, answer.json())
            expect(form.locator('[data-git-state="repo"]')).to_be_visible()
            expect(field("brief")).to_have_value(goal)
            expect(card.locator('textarea[name="content"]')).to_have_value(material)
            # The restarted server has a new in-memory draft store.
            expect(form.locator('[data-draft="saved"]')).to_be_visible()
            page.reload()
            expect(field("brief")).to_have_value(goal)
            form.locator('[data-guide-details="optional"] summary').click()
            expect(card.locator('textarea[name="content"]')).to_have_value(material)
            field("next").click()
            expect(form.locator('[data-guide-stage="team"]')).to_have_attribute("aria-current", "step")
            field("next").click()
            field("prepare:go").click()
            expect(form.locator('[data-guide-executors]')).to_be_visible(timeout=15000)
            assert any(path.endswith("/automation/preview") for path, _ in posts)
            seed = next((path, data) for path, data in posts if path.endswith("/seed"))
            assert seed[1]["source"] == "git" and seed[1]["expect_commit"]
            task = seed[0].split("/")[-2]
            assert (root / "work" / "_tasks" / task / "work-001" / "source.txt").read_bytes() == contents
            assert any(path.endswith("/materials") and material in str(data) for path, data in posts)
            assert not any(path.endswith("/automation/authorize") for path, _ in posts)
    finally:
        context.close()
