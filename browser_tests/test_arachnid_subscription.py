"""The root chat prepares a real policy run. Only the vendor boundary is a double."""
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from conductor import ownership, ownership_transition, server
from conductor.command import operator_config
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.run_store import RunStore
from conductor.tool_pins import pin_tool
from tests._fakeboundary import recording_runners
from tests.fake_process_fixtures import registered_fake_processes  # noqa: F401 (registered harness fixtures)
from tests.git_repo_helpers import GIT, commit, git
from tests.relay_credentials import codex_leaf, epoch_seconds, jwt, put
from tests.test_command_codex_transport import _executable as codex_binary
from tests.test_command_grok_transport import _executable as grok_binary
from tests.test_grok_relay import _document
from tests.test_patch_do_policy import reply
from tests.test_store import good_lane, write_project


@pytest.mark.parametrize("case", ["authorize", "replace", "operator"])
def test_codex_chat_prepares_grok_and_leaves_main_authority_to_operator(
        tmp_path, chromium, monkeypatch, case):
    root = write_project(tmp_path / "project", lanes={"test": good_lane()})
    hub = tmp_path / "hub"
    hub.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(hub))
    pin_tool("git", GIT, folder=hub)
    git("init", "-q", cwd=root)
    revision = commit(root, {"count.py": "def count(xs): return len(xs)\n"})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    expiry = datetime.now(timezone.utc) + timedelta(hours=4)
    providers = []
    for name, binary, auth in (
            ("codex", codex_binary, codex_leaf(access_token=jwt(
                {"sub": "only-a-test", "exp": epoch_seconds(expiry)}))),
            ("grok-build", grok_binary, _document(expires_at=expiry.isoformat()))):
        home = tmp_path / "DecemberCommand/logins" / name
        put(home, "auth.json", auth)
        providers.append(ProviderConfig(provider_id=name, protocol=name + "-headless-v1",
            executable=str(binary(tmp_path / "tools")), auth="subscription", auth_home=str(home),
            env_allow=("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")))
    with ownership.acquire_owner(root):
        operator_config.save_provider_configs(operator_config.provider_config_path(
            ownership.data_root(root)), providers, project_root=root)
    runners = recording_runners(monkeypatch, tmp_path / "attempts")
    monkeypatch.setattr(server.QuotaCollector, "start", lambda self: None)
    monkeypatch.setattr(server.QuotaCollector, "stop", lambda self: None)
    http = server.build(root, 0, providers=providers)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    calls = []
    for runner in runners:
        runner.auth_homes = tuple(tmp_path / "DecemberCommand/logins" / p.provider_id
                                  for p in providers)
        normal = runner.run
        def answer(spec, fallback=normal):
            if "exec" not in spec.argv:
                return fallback(spec)
            calls.append(spec)
            if len(calls) == 1:
                assert b"COUNT_CORRECT" in spec.stdin_bytes
                return reply(json.dumps({"criterion": "Count only accepted rows", "question": None,
                    "cycle_id": None, "roles": {}, "depth": "balanced"}).encode("ascii"))
            return reply(b"Goal recorded")
        runner.run = answer
    context = chromium.new_context(viewport={"width": 1280, "height": 840})
    try:
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{http.server_address[1]}/#lang=ru")
        expect(page.locator("#new")).to_be_enabled()
        page.locator("#new").click()
        page.locator("#lead").select_option("codex")
        page.locator("#command").fill("COUNT_CORRECT: исправь тест и подсчёт принятых строк")
        page.locator("#command").press("Enter")
        advisor = page.locator('[data-planner-action="authorizeAdvice"]')
        expect(advisor).to_be_enabled(timeout=10000)
        if case == "operator":
            page.locator("#planner input").fill("Alice")
        assert not calls
        advisor.click()
        prepare = page.locator('[data-planner-action="prepareMain"]')
        expect(prepare).to_be_enabled(timeout=30000)
        assert len(calls) == 1
        first_url = page.url
        if case == "replace":
            page.route("**/command/workflows", lambda route: route.fulfill(status=503, body="{}"))
            page.locator("#command").fill("A different task")
            page.locator("#command").press("Enter")
            page.locator('[data-planner-action="refresh"]').click()
            expect(page.locator("#planner")).to_have_attribute("data-planner-phase", "idle")
            expect(prepare).to_have_count(0)
            records = RunStore(root).read(first_url.split("advice=")[1].split("&")[0]).records
            assert not any(row.kind == "decision" for row in records)
            assert len(calls) == 1
            assert page.locator("#sessions button", has_text="Далио").count() == 0
            return
        if case == "operator":
            page.locator("#new").click()
            page.locator("#command").fill("Prepare another task")
            page.locator("#command").press("Enter")
            expect(advisor).to_be_enabled()
            page.locator("#planner input").fill("Bob")
            page.go_back()
            expect(prepare).to_be_enabled(timeout=15000)
            prepare.click()
            expect(page.locator('[data-planner-action="authorizeMain"]')).to_be_enabled(
                timeout=20000)
            expect(page.locator("#planner input")).to_have_value("Alice")
            return
        page.reload()
        expect(prepare).to_be_enabled(timeout=15000)
        page.locator("#sessions button", has_text="План Атласа").click()
        page.get_by_role("link", name="Вернуться к плану Атласа").click()
        expect(prepare).to_be_enabled(timeout=15000)
        expect(page.locator("#planner")).to_contain_text("Count only accepted rows")
        prepare.click()
        authorize = page.locator('[data-planner-action="authorizeMain"]')
        expect(authorize).to_be_enabled(timeout=20000)
        expect(page.locator("#planner")).to_contain_text("grok-build")
        expect(page.locator("#planner")).to_contain_text("3600")
        base = f"http://127.0.0.1:{http.server_address[1]}/command"
        runs = page.request.get(base + "/runs").json()["runs"]
        assert len(runs) == 2
        target, = [r["run_id"] for r in runs if not r["run_id"].startswith("advice-")]
        state = page.request.get(f"{base}/runs/{target}/automation").json()
        assert not state["authorization"] and len(calls) == 1
        detail = page.request.get(f"{base}/runs/{target}").json()
        graph = detail["graph"]["definition"]["nodes"]
        do, = [n for n in graph if n["node_id"] == "do"]
        diagnose, = [n for n in graph if n["node_id"] == "diagnose"]
        instances = {item["id"]: item["adapter"] for item in detail["config"]["instances"]}
        assert instances[diagnose["instance_id"]] == "grok-build"
        assert do["instance_id"] != do["verifier_instance_id"]
        assert instances[do["instance_id"]] == instances[do["verifier_instance_id"]] == "codex"
        source = page.request.get(f'{base}/tasks/{detail["task"]["id"]}/preparation').json()
        assert source["seed"]["base_commit"] == revision
        assert not any(row["record_type"] in ("action_request", "run_authorization")
                       for row in detail["records"])
        authorize.click()
        expect(page.locator('[data-planner-action="openRun"]')).to_be_visible(timeout=15000)
        record = RunStore(root).read(target)
        grants = [row.value for row in record.records if row.kind == "run_authorization"]
        assert len(grants) == 1 and grants[0].authorized_by == "local-operator"
        page.reload()
        expect(page.locator("#planner")).to_have_attribute(
            "data-planner-phase", "authorized", timeout=15000)
        expect(page.locator("#planner")).to_contain_text(target)
        assert sum(r.kind == "run_authorization" for r in RunStore(root).read(target).records) == 1
    finally:
        close_context(context)
        http.shutdown()
        worker.join(timeout=5)
        http.server_close()
