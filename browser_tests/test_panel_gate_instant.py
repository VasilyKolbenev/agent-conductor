"""A Human gate may be shown as satisfied only for a receipt production accepts.

``projectGates`` decides what a Human decided. It reads a ``DecisionReceipt``
straight off the wire, and the wire is not the store: a proxy, a newer server or
a broken one can hand the Cockpit a receipt whose ``decided_at`` names no
instant that ever existed. Production refuses such a receipt outright
(``DecisionReceipt.__post_init__`` -> ``contracts._timestamp``), so the panel
showing it as an approval would be the panel inventing an authorization.

This is binding four of four on the shared instant corpus: every row is driven
through the browser's own gate relation, and through the production contract in
the same test, so the two validators cannot drift apart silently. An accepted
instant must still project the gate as satisfied — otherwise a suite that
refused everything would pass — and a refused one must make the relation
*corrupt*, never satisfied.

The ISO end-of-day ``24:00:00Z`` is in that corpus as a refusal now. It used to
be accepted on both sides, because both delegated to ``datetime.fromisoformat``,
which refuses it on Python 3.11 and 3.12 and accepts it on 3.14 — so the set of
receipts the store would hold depended on the interpreter it ran under.

It lives outside pytest's configured ``testpaths`` for the same reason as
``test_panel_rendered``: Playwright stays an explicit development/CI dependency.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import ContractError, DecisionReceipt
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_adapters import FakeAdapter
from tests.test_command_run_store import CONFIG, a_run
from tests.test_store import good_lane, write_project
from tests.utc_instant_corpus import IDS, PARAMS


RUN_ID = "run-cockpit-gates"
TOKEN = "browser-only-process-token"
GATE_ID = "gate-release"
DIGEST = "sha256:" + "0" * 64
IMPOSSIBLE = "2026-99-99T99:99:99Z"


def receipt(instant: str) -> dict[str, object]:
    """One approval wrapper, identical but for the instant under test."""
    return {"record_type": "decision", "record": {
        "schema_version": 2, "receipt_id": "receipt-001", "run_id": RUN_ID,
        "gate_id": GATE_ID, "action": "approve", "actor": "release-owner",
        "decided_at": instant, "reason": "", "scope_refs": [],
        "config_digest": DIGEST, "evidence_refs": [], "supersedes": None,
    }}


@pytest.fixture(scope="module")
def gate_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Serve one confirm-mode run through the real loopback server."""
    root = write_project(
        tmp_path_factory.mktemp("cockpit-gates"), lanes={"claude": good_lane()})
    store = RunStore(root)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    httpd = server.build(
        root, 0, registry=AdapterRegistry([FakeAdapter()]),
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}/"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "cockpit server did not stop"


@pytest.fixture
def gate_page(chromium: Browser, gate_url: str) -> Iterator[Page]:
    context = chromium.new_context()
    page = context.new_page()
    page.goto(gate_url, wait_until="load")
    try:
        yield page
    finally:
        context.close()


def project_gates(page: Page, wrappers: list[dict[str, object]]) -> dict[str, object]:
    """Call the shipped projection directly, in the browser that ships it."""
    return page.evaluate(
        """async ([wrappers, runId]) => {
             const module = await import("/panel/command-projection.js");
             return module.projectGates(wrappers, runId);
           }""",
        [wrappers, RUN_ID])


@pytest.mark.parametrize("value,accepted", PARAMS, ids=IDS)
def test_the_gate_relation_answers_the_shared_instant_corpus_for_decided_at(
        gate_page: Page, value: str, accepted: bool) -> None:
    """What the durable contract will not store, the Cockpit will not display.

    And the converse in the same test, so the refusal cannot quietly become a
    refusal of everything: each row is put to the production contract and to the
    browser's relation, and the two must return the same verdict.
    """
    if accepted:
        assert DecisionReceipt.from_dict(
            receipt(value)["record"]).decided_at == value
        assert project_gates(gate_page, [receipt(value)]) == {
            "corrupt": False, "rows": [{"gateId": GATE_ID, "state": "satisfied"}]}
        return
    with pytest.raises(ContractError):
        DecisionReceipt.from_dict(receipt(value)["record"])
    assert project_gates(gate_page, [receipt(value)]) == {
        "corrupt": True, "rows": []}


def test_a_wire_receipt_with_an_impossible_instant_renders_corrupt_not_approved(
        gate_page: Page) -> None:
    """The rendered gate reads the response, so the response is where it is tested."""
    def doctor(route) -> None:
        payload = route.fetch().json()
        payload["records"] = [*payload.get("records", []), receipt(IMPOSSIBLE)]
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(payload))

    gate_page.route(f"**/command/runs/{RUN_ID}", doctor)
    gate_page.locator("#commandRunId").fill(RUN_ID)
    gate_page.get_by_role("button", name="Load run").click()
    gate_page.locator('[data-gate-state]').first.wait_for()

    states = gate_page.locator("[data-gate-state]")
    assert states.evaluate_all(
        "nodes => nodes.map(node => node.dataset.gateState)") == ["corrupt"]
    assert "approved" not in (states.first.text_content() or "")
