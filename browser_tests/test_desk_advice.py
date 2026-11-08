"""A subscribed review may propose fields, but only the person changes the main draft."""
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from playwright.sync_api import expect

from conductor import ownership, ownership_transition, server
from conductor.command import operator_config
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.run_store import RunStore
from tests._fakeboundary import recording_runners
from tests.relay_credentials import codex_leaf, epoch_seconds, jwt, put
from tests.test_command_codex_transport import _executable
from tests.test_patch_do_policy import reply
from tests.test_store import write_project, good_lane


@pytest.mark.parametrize(("lang", "width", "case"), [
    ("ru", 375, "accept"), ("en", 1280, "accept"), ("ru", 375, "invalid"),
    ("en", 1280, "edited"), ("ru", 375, "before_grant")])
def test_subscription_advice_has_its_own_grant_and_only_edits_the_open_draft(
        tmp_path, chromium, monkeypatch, lang, width, case):
    root = write_project(tmp_path / "project", lanes={"test": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    home = tmp_path / "DecemberCommand/logins/codex"
    expiry = datetime.now(timezone.utc) + timedelta(hours=3)
    put(home, "auth.json", codex_leaf(access_token=jwt(
        {"sub": "fixture-only", "exp": epoch_seconds(expiry)})))
    binary = _executable(tmp_path / "tools")
    config = ProviderConfig(provider_id="codex", protocol="codex-headless-v1",
        executable=str(binary), auth="subscription", auth_home=str(home),
        env_allow=("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"))
    with ownership.acquire_owner(root):
        operator_config.save_provider_configs(operator_config.provider_config_path(
            ownership.data_root(root)), [config], project_root=root)
    made = recording_runners(monkeypatch, tmp_path / "attempts")
    monkeypatch.setattr(server.QuotaCollector, "start", lambda self: None)
    monkeypatch.setattr(server.QuotaCollector, "stop", lambda self: None, raising=False)
    http = server.build(root, 0, providers=[config])
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    runner, = made
    runner.auth_homes = (home,)
    normal = runner.run
    calls = []
    allow_reply = threading.Event()
    def answer(spec):
        if "exec" not in spec.argv:
            return normal(spec)
        calls.append(spec)
        assert b"COUNT_CASE_42" in spec.stdin_bytes and b"advice" in str(spec.cwd).encode()
        if case == "edited":
            assert allow_reply.wait(15)
        if case == "invalid":
            return reply(b'{"criterion":"take control","question":null,"cycle_id":null,"roles":{},"authorize":true}')
        return reply(b'{"criterion":"Only successful rows count","question":"Should empty input return zero?","cycle_id":null,"roles":{},"depth":"quick"}')
    runner.run = answer
    context = chromium.new_context(viewport={"width": width, "height": 840})
    try:
        page = context.new_page()
        refusals = []
        page.on("response", lambda res: refusals.append((res.url, res.status, res.json()))
                if res.status >= 400 and "/command/" in res.url else None)
        page.goto(f"http://127.0.0.1:{http.server_port}/panel/desk.html#new=task&lang={lang}")
        brief = page.locator('[data-focus="wizard:brief"]')
        brief.fill("COUNT_CASE_42: count successful rows")
        toggle = page.locator("[data-advice-open]")
        expect(toggle).to_be_visible(timeout=3500)
        toggle.click()
        panel = page.locator("[data-launch-advice]")
        panel.locator("[data-advice-prepare]").click()
        grant = panel.locator("[data-advice-grant]")
        panel.locator("[data-advice-grant], [role=alert]").first.wait_for()
        assert grant.is_visible(), [(url.split("/command/")[-1], status, reply["error"]["code"])
                                    for url, status, reply in refusals]
        assert not calls
        run_id = panel.get_attribute("data-advice-run")
        store = RunStore(root)
        assert not any(r.kind in {"run_authorization", "action_request"} for r in store.read(run_id).records)
        panel.locator("[data-advice-actor]").fill("reviewer-test")
        if case == "before_grant":
            pending = []
            page.route(f"**/command/runs/{run_id}/automation", lambda route: pending.append(route))
            with page.expect_request(lambda req: req.url.endswith("/automation") and req.method == "GET"):
                grant.click()
            brief.fill("Changed before the read returned")
            expect(panel).to_contain_text("Черновик изменился")
            with page.expect_response(lambda res: res.url.endswith("/automation")):
                pending[0].continue_()
            assert not any(r.kind == "run_authorization" for r in store.read(run_id).records)
            assert not grant.is_visible() and not calls
            return
        with page.expect_response(lambda res: res.url.endswith("/automation/authorize")
                                  and res.request.method == "POST") as accepted:
            grant.click()
        assert accepted.value.status == 201
        apply = panel.locator("[data-advice-apply]")
        if case == "edited":
            brief.fill("A different task in this same draft")
            allow_reply.set()
            expect(panel).to_contain_text("The draft changed")
            assert not apply.is_visible()
            expect(brief).to_have_value("A different task in this same draft")
            assert sum(r.kind == "run_authorization" for r in store.read(run_id).records) == 1
            return
        if case == "invalid":
            expect(panel.locator("[role=alert]")).to_contain_text("формате", timeout=18000)
            assert not apply.is_visible()
            assert not panel.locator("[data-advice-prepare]").is_visible()
            panel.locator("[data-advice-close]").click()
            toggle.click()
            panel.locator("[data-advice-prepare]").click()
            expect(panel.locator("[role=alert]")).to_be_visible()
            expect(brief).to_have_value("COUNT_CASE_42: count successful rows")
            assert len(calls) == 1
            return
        expect(apply).to_be_visible(timeout=18000)
        # Another note can reuse the output reference in a projection. It cannot speak for the review.
        def shadow_note(route):
            response = route.fetch()
            actual = response.json()
            suggestion, = [row["record"] for row in actual["records"] if row["record_type"] == "artifact"
                           and row["record"]["artifact_ref"] == "draft-suggestion"]
            actual["records"].append({"record_type": "artifact", "record": {
                **suggestion, "artifact_id": "later-note", "source_action_id": None,
                "content": "Unrelated later suggestion"}})
            route.fulfill(response=response, json=actual)
        page.route(f"**/command/runs/{run_id}", shadow_note)
        # Reopening the same inquiry reads the prior result without another grant.
        panel.locator("[data-advice-close]").click()
        toggle.click()
        panel.locator("[data-advice-prepare]").click()
        expect(apply).to_be_visible()
        expect(panel).to_contain_text("Only successful rows count")
        expect(brief).to_have_value("COUNT_CASE_42: count successful rows")
        with page.expect_response(lambda res: res.url.endswith("/project/task-draft")
                                  and (res.request.post_data_json or {}).get("answers", {}).get("budgetDepth") == "quick") as saved:
            apply.click()
        assert saved.value.status in (200, 201)
        expect(brief).to_have_value("COUNT_CASE_42: count successful rows")
        hint = page.locator('[data-focus="wizard:hint"]')
        if not hint.is_visible():
            page.locator('[data-guide-details="optional"] summary').click()
        expect(hint).to_have_value("Only successful rows count")
        assert len(calls) == 1
        records = store.read(run_id).records
        assert sum(r.kind == "run_authorization" for r in records) == 1
        assert sum(r.kind == "action_request" for r in records) == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        allow_reply.set()
        context.close()
        http.shutdown()
        worker.join(timeout=5)
        http.server_close()
