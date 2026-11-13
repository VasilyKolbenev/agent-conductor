"""The root chat prepares a real policy run. Only the vendor boundary is a double."""
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context, until
from browser_tests.test_studio_lifecycle import _STREAM_DOUBLE
from conductor import ownership, ownership_transition, server
from conductor.command import operator_config
from conductor.command import providers as provider_factory
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.run_store import RunStore
from conductor.tool_pins import pin_tool
from tests._fakeboundary import recording_runners
from tests.fake_process_fixtures import registered_fake_processes  # noqa: F401
from tests.git_repo_helpers import GIT, commit, git
from tests.relay_credentials import codex_leaf, epoch_seconds, jwt, put
from tests.test_command_codex_transport import _executable as codex_binary
from tests.test_command_grok_transport import _executable as grok_binary
from tests.test_grok_relay import _document
from tests.test_patch_do_policy import reply
from tests.test_store import good_lane, write_project


def finish_during_planner_read(page, run_id, advisor, case, calls, release_answer):
    """Deliver the final frame while the grant response or a prior journal read is in transit."""
    journal = page.url.split("/#")[0] + "/command/runs/" + run_id
    held = []

    def hold_reply(route):
        held.append((route, route.fetch()))

    def frame():
        page.evaluate("id => __stream.emit(JSON.stringify({kind:'run', run_id:id}))", run_id)

    def completed():
        rows = page.request.get(journal).json()["records"]
        return any(r["record_type"] == "action_result" and r["record"]["outcome"] == "succeeded"
                   for r in rows) and any(r["record_type"] == "artifact" and
                   r["record"]["artifact_ref"] == "draft-suggestion" for r in rows)

    if case == "grant_signal":
        page.route(journal + "/automation/authorize", hold_reply, times=1)
        advisor.click()
    else:
        with page.expect_response(lambda reply: reply.url == journal + "/automation/authorize"):
            advisor.click()
        until(page, "the fake vendor received the request", lambda: calls)
        page.route(journal, hold_reply, times=1)
        frame()
    until(page, "a reply is in transit", lambda: held)
    route, response = held[0]
    assert response.ok
    if case == "read_signal":
        assert not any(r["record_type"] == "action_result" for r in response.json()["records"])
        release_answer.set()
    until(page, "the result and suggestion are in the journal", completed)
    frame()
    route.fulfill(response=response)


@pytest.mark.parametrize("case", [
    "authorize", "replace", "operator", "grant_signal", "read_signal"])
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
    monkeypatch.setattr(provider_factory, "host_platform", lambda: "win32")
    monkeypatch.setattr(server.QuotaCollector, "start", lambda self: None)
    monkeypatch.setattr(server.QuotaCollector, "stop", lambda self: None)
    http = server.build(root, 0, providers=providers)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    calls = []
    release_answer = threading.Event()
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
                if case == "read_signal":
                    assert release_answer.wait(timeout=20)
                return reply(json.dumps({"criterion": "Count only accepted rows", "question": None,
                    "cycle_id": None, "roles": {}, "depth": "balanced"}).encode("ascii"))
            return reply(b"Goal recorded")
        runner.run = answer
    context = chromium.new_context(viewport={"width": 1280, "height": 840})
    try:
        page = context.new_page()
        if case in ("grant_signal", "read_signal"):
            page.add_init_script(_STREAM_DOUBLE)
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
        if case in ("grant_signal", "read_signal"):
            run_id = page.url.split("advice=")[1].split("&")[0]
            finish_during_planner_read(page, run_id, advisor, case, calls, release_answer)
        else:
            advisor.click()
        prepare = page.locator('[data-planner-action="prepareMain"]')
        expect(prepare).to_be_enabled(timeout=30000)
        assert len(calls) == 1
        if case in ("grant_signal", "read_signal"):
            expect(page.locator("#planner")).to_contain_text("Count only accepted rows")
            assert not any(r.kind == "decision" for r in RunStore(root).read(run_id).records)
            return
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
        release_answer.set()
        close_context(context)
        http.shutdown()
        worker.join(timeout=5)
        http.server_close()
