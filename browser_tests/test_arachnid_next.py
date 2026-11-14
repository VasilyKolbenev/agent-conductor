"""Atlas brings the selected run's next human action into its conversation."""
from contextlib import contextmanager
from copy import deepcopy
import json

import pytest
from playwright.sync_api import expect

from browser_tests.desk_identity import identified_server
from browser_tests.desk_hold import close_context
from browser_tests.test_desk_decisions import PROJECT, _gate_pair, _world
from browser_tests.test_studio_automation_browser import bounded_project  # noqa: F401
from conductor.command.run_store import RunStore
from tests.desk_progress_seed import seed_project
from tests.test_store import good_lane, write_project


@contextmanager
def operator(chromium, origin, run, project=PROJECT):
    context = chromium.new_context(locale="en-US", viewport={"width": 1280, "height": 880})
    page = context.new_page()
    posted, problems = [], []
    page.on("request", lambda req: posted.append(req.url) if req.method == "POST" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    try:
        claim = f"project={project}&" if project else ""
        page.goto(f"{origin.rstrip('/')}/#{claim}session={run}&lang=en")
        yield page, posted
        assert problems == []
    finally:
        close_context(context)


def test_archive_offers_its_reviewed_do_inside_atlas(chromium, tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    seed_project(root)
    with identified_server(root, PROJECT, mode="view") as origin:
        with operator(chromium, origin, "run-closed") as (page, posted):
            expect(page.locator('#orbitHere [data-step="do"]')).to_be_visible()
            atlas = page.locator("#chat")
            expect(atlas.get_by_text("Result accepted", exact=True)).to_be_visible()
            atlas.get_by_role("button", name="View Do result", exact=True).click()
            expect(page.locator("#inspection h2")).to_have_text("Do the work")
            page.goto(f"{origin}/#project={PROJECT}&session=run-working&lang=en")
            next_card = atlas.locator("#nextAction")
            expect(next_card).to_contain_text("Waiting for claude-code · Do the work")
            expect(next_card.locator("button:visible")).to_have_count(0)
            assert posted == []


def test_gate_belongs_to_the_reviewed_run_and_an_explicit_actor(chromium, tmp_path):
    root = _world(tmp_path)
    store = _gate_pair(root, "pair")
    _gate_pair(root, "another")
    with identified_server(root, PROJECT) as origin:
        with operator(chromium, origin, "pair") as (page, posted):
            next_card = page.locator("#nextAction")
            next_card.get_by_role("button", name="Review Confirm Do").click()
            expect(next_card.locator("h3").first).to_have_text("Confirm Do")
            who = next_card.locator('input[name="actor"]')
            expect(who).to_have_value("")
            who.press_sequentially("reviewer")
            expect(who).to_be_focused()
            expect(who).to_have_value("reviewer")
            assert posted == []
            page.evaluate("""() => {
                const button = document.querySelector('#nextAction button[type=submit]');
                location.hash = 'project=' + 'a'.repeat(32) + '&session=another&lang=en';
                button.click();
            }""")
            expect(page.locator('#sessions [aria-current=true]')).to_have_attribute(
                "data-session", "run/another")
            assert posted == []
            page.goto(f"{origin}/#project={PROJECT}&session=pair&lang=en")
            next_card.get_by_role("button", name="Review Confirm Do").click()
            next_card.locator('input[name="actor"]').fill("reviewer")

            def drop_recorded_receipt(route):
                result = route.fetch()
                assert result.status == 201
                route.abort("failed")

            page.route("**/command/runs/pair/decisions", drop_recorded_receipt)
            button = next_card.locator("button[type=submit]")
            button.evaluate("(b) => {b.click(); b.click()}")
            expect(next_card.get_by_role("button", name="Review Result Gate")).to_be_visible()
            receipts = [r.value for r in store.read("pair").records if r.kind == "decision"]
            assert [(r.gate_id, r.actor, r.supersedes) for r in receipts] == [
                ("gate-confirm-do", "reviewer", None)]
            assert sum(url.endswith("/decisions") for url in posted) == 1


def test_unknown_run_read_cannot_offer_an_unrelated_answerable_gate(chromium, tmp_path):
    root = _world(tmp_path)
    _gate_pair(root, "unclear")
    with identified_server(root, PROJECT) as origin:
        with operator(chromium, origin, "run-fix-new") as (page, posted):
            def replay_with_warning(route):
                value = route.fetch().json()
                situation = value["graph"]["situation"]
                assert any(g["needs_decision"] for g in situation["gates"])
                value["warnings"].append("Fixture warning")
                reason = next(row for row in situation["unknown_sources"]
                              if row["reason"] == "replay_warnings")
                reason["count"] = len(value["warnings"])
                situation.update(state="unknown", unknown_because=["replay_warnings"])
                route.fulfill(json=value)

            page.route("**/command/runs/unclear", replay_with_warning)
            page.goto(f"{origin}/#project={PROJECT}&session=unclear&lang=en")
            card = page.locator("#nextAction")
            expect(card).to_contain_text("The outcome is unclear")
            expect(card.locator("button:visible")).to_have_count(0)
            assert posted == []


@pytest.mark.parametrize("field,wrong", [
    ("scope_refs", ["other-scope"]),
    ("evidence_refs", ["other-evidence"]),
    ("run_id", "other-run"),
])
def test_lost_ack_needs_the_exact_gate_receipt(chromium, tmp_path, field, wrong):
    root = _world(tmp_path)
    _gate_pair(root, "pair")
    with identified_server(root, PROJECT) as origin:
        with operator(chromium, origin, "pair") as (page, posted):
            card = page.locator("#nextAction")
            card.get_by_role("button", name="Review Confirm Do").click()
            card.locator('input[name="actor"]').fill("reviewer")
            initial = page.request.get(origin + "/command/runs/pair").json()
            corrupt = True
            sent = {}

            def replay(route):
                value = route.fetch().json()
                receipts = [row for row in value["records"] if row["record_type"] == "decision"]
                if corrupt and receipts:
                    assert len(receipts) == 1
                    altered = deepcopy(receipts[0])
                    altered["record"][field] = wrong
                    if field == "run_id":
                        # A foreign record cannot be the standing receipt of this local graph.
                        value = deepcopy(initial)
                        value["records"].append(altered)
                    else:
                        receipts[0]["record"] = altered["record"]
                body = json.dumps(value)
                if corrupt and receipts:
                    sent[route.request] = body
                route.fulfill(body=body, headers={
                    "Content-Type": "application/json",
                    "X-Fixture-Receipt": "altered" if receipts and corrupt else "regular"})

            def lose_ack(route):
                assert route.fetch().status == 201
                route.abort("failed")

            page.route("**/command/runs/pair", replay)
            page.route("**/command/runs/pair/decisions", lose_ack)
            with page.expect_response(
                    lambda r: r.headers.get("x-fixture-receipt") == "altered") as read:
                card.locator("button[type=submit]").click()
            check = card.get_by_role("button", name="Check the run")
            response = read.value
            assert response.ok and response.headers["x-fixture-receipt"] == "altered"
            delivered = json.loads(sent[response.request])
            receipt, = [row["record"] for row in delivered["records"]
                        if row["record_type"] == "decision"]
            durable, = [r.value.as_dict() for r in RunStore(root).read("pair").records
                        if r.kind == "decision"]
            assert durable[field] != wrong
            assert receipt == {**durable, field: wrong}
            assert receipt["receipt_id"] == "receipt-gate-confirm-do-0-reviewer"
            expect(card).to_contain_text("Your decision has no matching receipt yet")
            expect(card.locator("form")).to_have_count(0)
            corrupt = False
            check.click()
            expect(card.get_by_role("button", name="Review Result Gate")).to_be_visible()
            assert sum(url.endswith("/decisions") for url in posted) == 1


@pytest.mark.parametrize("bounded_project", ["recovery"], indirect=True)
def test_policy_preview_and_lost_grant_reply_reconcile_only_by_reading(chromium, bounded_project):
    project, adapter = bounded_project
    with operator(chromium, project.url, "run", project=None) as (page, posted):
        card = page.locator("#nextAction")
        card.get_by_role("button", name="Review Human choice").click()
        card.locator('input[name="actor"]').fill("gate-reader")
        card.locator("button[type=submit]").click()
        card.get_by_role("button", name="Review run limits").click()
        expect(card.locator("[data-automation-state]")).to_have_attribute(
            "data-automation-state", "unconfigured")
        actor = card.get_by_role("textbox", name="Your name")
        expect(actor).to_have_value("")
        assert not any("/automation/" in url for url in posted)
        actor.press_sequentially("policy-reader")
        expect(actor).to_be_focused()
        card.get_by_role("button", name="Review bounded run").click()
        expect(card.locator("[data-automation-preview]")).to_be_visible()
        submitted = []

        def lose_reply(route):
            submitted.append(route.request.post_data_json)
            route.abort("failed")

        page.route("**/automation/authorize", lose_reply)
        grant = card.get_by_role("button", name="Authorize bounded run")
        grant.evaluate("(b) => { b.click(); b.click(); }")
        expect(card.get_by_text("The outcome is unclear")).to_be_visible()
        def read(response):
            return response.request.method == "GET" and response.url.endswith("/automation")

        with page.expect_response(read) as response:
            card.get_by_role("button", name="Check the run").click()
        expect(card.get_by_text("The outcome is unclear")).to_be_visible()
        assert len(submitted) == 1 and submitted[0]["authorized_by"] == "policy-reader"
        assert sum(url.endswith("/automation/preview") for url in posted) == 1
        assert sum(url.endswith("/automation/authorize") for url in posted) == 1
        journal = RunStore(project.root).read("run")
        assert all(r.kind != "run_authorization" for r in journal.records)
        assert adapter.execute_calls == 0

        # Replay the submitted identity at the read boundary only. Recorded authority can
        # itself be expired, revoked or spent. None of these observations can renew it.
        body = submitted[0]
        terms = {k: v for k, v in body["terms"].items() if k != "duration_seconds"}
        grant_value = dict(terms, schema_version=2, authorization_digest="sha256:" + "a" * 64,
                           authorization_id=body["authorization_id"], authorized_by="policy-reader",
                           supersedes=None, authorized_at="2026-02-01T10:00:00Z",
                           expires_at="2026-02-01T12:00:00Z")
        observed = dict(response.value.json(), state="expired", reason_code="expired",
                        authorization=grant_value, expires_at=grant_value["expires_at"],
                        remaining_actions=terms["max_actions"],
                        remaining_task_seconds=terms["max_total_task_seconds"])
        page.route("**/runs/run/automation", lambda route: route.fulfill(json=observed))
        page.reload()
        expect(card).to_contain_text("Permission expired")
        observed.update(state="revoked", reason_code="revoked", control={
            "schema_version": 2, "control_id": "stop", "run_id": "run",
            "authorization_id": body["authorization_id"],
            "authorization_digest": grant_value["authorization_digest"], "action": "revoke",
            "actor": "policy-reader", "recorded_at": "2026-02-01T11:00:00Z",
            "expected_control_id": None})
        page.reload()
        expect(card).to_contain_text("Permission revoked")
        observed.update(state="ready", reason_code="ready", control=None,
                        spent_actions=terms["max_actions"], remaining_actions=0)
        page.reload()
        expect(card).to_contain_text("The run budget is exhausted")
        expect(card.locator("button:visible")).to_have_count(0)
        assert sum(url.endswith("/automation/authorize") for url in posted) == 1
