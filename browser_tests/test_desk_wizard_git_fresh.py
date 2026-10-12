"""Two fresh pages finish what an earlier life left, on a real project server over real Git.

These are the two scenarios lane L's contract (section 7) leaves to this lane, with no fake in the
way: the desk's own modules, the real transport, a real server, a real temporary repository and
the product's own Git reader. Each starts from a page with NO memory of the first call: the first
life is made over the wire, then a new browser context opens the wizard on step 2 and the page has
only what the git read says.

1. A fresh page finishes a wait for a signature. The first confirm answers `signing_required` and
   the product stores the intent. The page reads `awaiting_signature`, shows the two commands from
   the read alone, the test runs THOSE lines in the project folder with a throwaway key, and
   "Check again" posts the continue body: `201`, `signature: "present"`, and the next read is
   `null` and `repo`.
2. A fresh page finishes a crash after the branch moved. The first life dies right after the
   branch moved; the page reads `repo` with `unfinished`, shows the stored terms, and "Continue"
   answers `201`, with exactly ONE move of the branch across both lives.

What the test serves differently from the product, and why. The switch of the confirm
(`FIRST_COMMIT_CONFIRM_OPEN`) is one literal that the tech lead flips when lane L opens the route;
the route's own switch is held open by the fixture, and the page gets the module with its literal
set. The write door's target `gitSetup` is lane D1's two lines in `desk-transport.js`; until they
are in the product the page gets the transport with exactly those two lines. Each change is made
only while the product lacks it and is asserted to have happened once, so the day the product has
them the page is served the product's own bytes with no edit here.

Requirements, stated because a browser module may not skip: the current Git and `ssh-keygen`.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Request, Route, expect

from conductor import ownership_transition, server
from conductor.command import git_setup
from conductor.ownership import data_root
from tests.git_first_bench import Spy, crash_after
from tests.git_first_readers import product_reader
from tests.git_first_signing import SSH_KEYGEN, run_owner
from tests.git_repo_helpers import GIT, git
from tests.test_store import good_lane, write_project

SETUP = "/command/project/git/setup"
PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
FILES = {"a.txt": b"one\n", "docs/b.md": b"two\n", "owner.txt": b"mine\n"}
MODES = ("snapshot", "empty")
JS = "text/javascript; charset=utf-8"
SWITCH = "export const FIRST_COMMIT_CONFIRM_OPEN = false;"


def call(base: str, method: str, path: str, token: str | None = None,
         body: Any = None) -> tuple[int, Any]:
    """One request as a client with no memory makes it; the answer's status and JSON."""
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["X-Conduct-CSRF"] = token
        headers["Origin"] = base
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


class Real:
    """One project folder, its real server, the product's Git reader and a client."""

    def __init__(self, root: Path, base: str, spy: Spy) -> None:
        self.root, self.base, self.spy = root, base, spy
        self.token = call(base, "GET", "/command/session")[1]["csrf_token"]

    def post(self, body: dict[str, Any]) -> tuple[int, Any]:
        return call(self.base, "POST", SETUP, self.token, body)

    def read(self) -> dict[str, Any]:
        status, payload = call(self.base, "GET", "/command/project/git")
        assert status == 200, payload
        return payload["git"]

    def preview(self, mode: str) -> dict[str, Any]:
        status, shown = self.post({"step": "first_commit", "mode": mode, "preview": True})
        assert status == 200, shown
        return shown["setup"]

    def confirm_body(self, mode: str, actor: str = "Owner") -> dict[str, Any]:
        digest = self.preview(mode)["paths_digest"] if mode == "snapshot" else None
        return {"step": "first_commit", "mode": mode, "paths_digest": digest, "actor": actor}

    def moves(self) -> int:
        """How many times the branch was moved by the product, across every life."""
        return len(self.spy.argv("update-ref"))

    def tree(self) -> list[str]:
        shown = git("ls-tree", "-r", "--name-only", "HEAD", cwd=self.root)
        return [line for line in shown.stdout.decode().splitlines() if line]


@pytest.fixture
def throwaway_key(tmp_path: Path) -> Path:
    """A throwaway ed25519 key made beside (never in) the project; it never leaves the test.

    A machine without `ssh-keygen` FAILS here, with the reason: a browser module may not skip."""
    if SSH_KEYGEN is None:
        pytest.fail("ssh-keygen is required by test_desk_wizard_git_fresh.py")
    import subprocess
    key = tmp_path / "throwaway-key"
    made = subprocess.run([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                          capture_output=True, check=False)
    assert made.returncode == 0, made.stderr.decode(errors="replace")
    return key


@pytest.fixture
def real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, throwaway_key: Path) -> Iterator[Real]:
    """A real one-project server whose route has its confirm door held open and whose Git is the
    product's own reader (no account settings, no hooks), over a repository this test makes."""
    if GIT is None:
        pytest.fail("git is required by test_desk_wizard_git_fresh.py")
    monkeypatch.setattr(git_setup, "_CONFIRM_OPEN", True, raising=False)
    root = tmp_path / "project"
    root.mkdir()
    write_project(root, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        cwd = data_root(root) / "git" / "cwd"
        cwd.mkdir(parents=True)
        hooks = cwd.parent / "hooks-empty"
        hooks.mkdir()
        env = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.hooksPath",
               "GIT_CONFIG_VALUE_0": str(hooks), "GIT_CONFIG_KEY_1": "init.defaultBranch",
               "GIT_CONFIG_VALUE_1": "trunk"}
        spy = Spy(product_reader(root, GIT, cwd, env=env, index_root=root))
        httpd.command_api._project_git = spy
        host, port = httpd.server_address[:2]
        project = Real(root, f"http://{host}:{port}", spy)
        assert project.post({"step": "init", "actor": "Owner"})[0] == 201
        for name, value in (("user.name", "First Author"), ("user.email", "first@example.invalid"),
                            ("core.autocrlf", "false")):
            git("config", name, value, cwd=root)
        for relative, data in FILES.items():
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_bytes(data)
        yield project
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "the project server did not stop"


def signing(project: Real, key: Path) -> None:
    """Make the repository ask for a signature, with the throwaway key."""
    for name, value in (("commit.gpgsign", "true"), ("gpg.format", "ssh"),
                        ("user.signingkey", key.as_posix()), ("gpg.ssh.program", SSH_KEYGEN)):
        git("config", name, value, cwd=project.root)


def modules() -> dict[str, bytes]:
    """The two modules the page is served with an edit, while the product lacks the edit."""
    served: dict[str, bytes] = {}
    transport = (PANEL / "desk-transport.js").read_text(encoding="utf-8")
    if "gitSetup" not in transport:
        for old, new in (('  git: () => "/command/project/git",\n',
                          '  git: () => "/command/project/git",\n'
                          '  gitSetup: () => "/command/project/git/setup",\n'),
                         ('"acceptPreview", "acceptCommit"]);',
                          '"acceptPreview", "acceptCommit", "gitSetup"]);')):
            assert transport.count(old) == 1, old
            transport = transport.replace(old, new)
        served["desk-transport.js"] = transport.encode("utf-8")
    switch = (PANEL / "desk-wizard-git.js").read_text(encoding="utf-8")
    if SWITCH in switch:
        served["desk-wizard-git.js"] = switch.replace(SWITCH, SWITCH.replace("false", "true")
                                                      ).encode("utf-8")
    return served


def fresh_page(chromium: Browser) -> tuple[Page, list[str], list[tuple[str, str]]]:
    """A new browser context with no memory of anything; what its page reports as a fault; and
    every request it makes, as (method, path)."""
    context = chromium.new_context(viewport={"width": 1100, "height": 1500})
    page = context.new_page()
    page.set_default_timeout(15000)
    faults: list[str] = []
    asked: list[tuple[str, str]] = []
    page.on("request", lambda request: asked.append((request.method, urlsplit(request.url).path)))
    page.on("pageerror", lambda error: faults.append(str(error)))
    page.on("console", lambda message: faults.append(message.text)
            if message.type == "error" else None)
    for name, body in modules().items():
        page.route(f"**/panel/{name}", served(body))
    return page, faults, asked


def served(body: bytes) -> Callable[[Route, Request], None]:
    """A route handler that answers with `body` as JavaScript. Playwright hands a handler the
    route AND the request, so the body is closed over and never a defaulted parameter."""
    return lambda route, _request: route.fulfill(status=200, content_type=JS, body=body)


def wizard_at_materials(page: Page, project: Real) -> None:
    """The person's own path: the desk, their name, the new task, the first step, 'Далее'."""
    page.goto(f"{project.base}/panel/desk.html#lang=en", wait_until="load")
    page.locator('[data-focus-key="pult:actor-change"]').click()
    page.locator('[data-focus-key="pult:actor-name"]').fill("Owner")
    page.locator('[data-focus-key="pult:actor-save"]').click()
    new = page.locator("#deskNewTask")
    expect(new).to_be_enabled()
    new.click()
    wizard = page.locator("#deskWizard [data-wizard]")
    expect(wizard).to_have_attribute("data-wizard-current", "task")
    page.locator('[data-focus="wizard:title"]').fill("Finish the first commit")
    page.locator('[data-focus="wizard:brief"]').fill("Open the project.")
    page.locator('[data-focus="wizard:next"]').click()
    expect(wizard).to_have_attribute("data-wizard-current", "materials")


def posts(asked: list[tuple[str, str]]) -> list[str]:
    """The paths of the writes a page made to the setup route."""
    return [path for method, path in asked if method == "POST" and path.endswith("/git/setup")]


def typed_commands(page: Page) -> dict[str, str]:
    return page.evaluate("""() => Object.fromEntries([...document.querySelectorAll(
      '[data-git-command]')].map((node) => [node.dataset.gitCommand, node.value]))""")


def the_owner_runs(project: Real, shown: dict[str, str]) -> str:
    """Run the two lines the PAGE showed, in the project folder; the second takes the first's id."""
    folder = SimpleNamespace(root=project.root)
    made = run_owner(folder, shown["commit"])
    assert made.returncode == 0, made.stderr.decode(errors="replace")
    oid = made.stdout.decode().strip()
    moved = run_owner(folder, shown["update"].replace("<oid>", oid))
    assert moved.returncode == 0, moved.stderr.decode(errors="replace")
    return oid


def test_the_fixture_serves_a_page_whose_git_read_answers(chromium, real):
    page, faults, asked = fresh_page(chromium)
    try:
        wizard_at_materials(page, real)
        expect(page.locator('[data-git-state="unborn"]')).to_have_count(1)
        expect(page.locator('[data-focus="wizard:git:first_commit"]')).to_be_enabled()
        assert faults == []
    finally:
        page.context.close()


@pytest.mark.parametrize("mode", MODES)
def test_a_fresh_page_finishes_a_wait_for_a_signature(chromium, real, throwaway_key, mode):
    signing(real, throwaway_key)
    status, refused = real.post(real.confirm_body(mode))
    assert status == 409 and refused["error"]["detail"]["reason"] == "signing_required"
    page, faults, asked = fresh_page(chromium)
    try:
        wizard_at_materials(page, real)
        waiting = page.locator('[data-git-pending="awaiting_signature"]')
        expect(waiting).to_have_count(1)
        assert posts(asked) == [], "a page that loads and reads sends nothing"
        shown = typed_commands(page)
        assert set(shown) == {"commit", "update"}
        the_owner_runs(real, shown)
        page.locator('[data-focus="wizard:git:continue"]').click()
        expect(page.locator('[data-git-result="done"]')).to_have_count(1)
        assert posts(asked) == [SETUP], "Check again is one request"
        assert "Signature present, not verified." in page.locator(
            "[data-git-result]").inner_text()
        facts = real.read()
        assert facts["first_commit_pending"] is None and facts["state"] == "repo"
        expect(page.locator('[data-git-state="repo"]')).to_have_count(1)
        assert page.locator("[data-git-pending]").count() == 0
        assert real.tree() == (sorted(FILES) if mode == "snapshot" else [])
        assert faults == []
    finally:
        page.context.close()


@pytest.mark.parametrize("mode", MODES)
def test_a_fresh_page_finishes_a_crash_after_the_branch_moved(chromium, real, monkeypatch, mode):
    body = real.confirm_body(mode)
    restart = crash_after(monkeypatch, "_do_mark_ref_moved")
    status, answer = real.post(body)
    restart()
    assert status == 500, answer
    facts = real.read()
    assert facts["state"] == "repo" and facts["first_commit_pending"]["state"] == "unfinished"
    page, faults, asked = fresh_page(chromium)
    try:
        wizard_at_materials(page, real)
        panel = page.locator('[data-git-pending="unfinished"]')
        expect(panel).to_have_count(1)
        assert page.locator('[data-git-term="by"]').inner_text() == "Confirmed by: Owner"
        assert posts(asked) == [], "a page that loads and reads sends nothing"
        page.locator('[data-focus="wizard:git:continue"]').click()
        expect(page.locator('[data-git-result="done"]')).to_have_count(1)
        assert posts(asked) == [SETUP], "Continue is one request"
        assert real.moves() == 1, "the branch moved once across both lives"
        facts = real.read()
        assert facts["first_commit_pending"] is None and facts["state"] == "repo"
        assert real.tree() == (sorted(FILES) if mode == "snapshot" else [])
        assert re.search(r"[0-9a-f]{7}", page.locator("[data-git-result]").inner_text())
        assert faults == []
    finally:
        page.context.close()
