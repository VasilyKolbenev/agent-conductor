"""A Human gate may be shown as satisfied only for a receipt production accepts.

``projectGates`` decides what a Human decided. It reads a ``DecisionReceipt``
straight off the wire, and the wire is not the store: a proxy, a newer server or
a broken one can hand the Cockpit a receipt whose ``decided_at`` names no
instant that ever existed. Production refuses such a receipt outright
(``DecisionReceipt.__post_init__`` -> ``contracts._timestamp``), so the panel
showing it as an approval would be the panel inventing an authorization.

Two facts are pinned here, in the browser that actually executes the module:

* an impossible instant makes the gate relation *corrupt*, never satisfied; and
* the four instant forms production does accept — a trailing ``Z``, an explicit
  ``+00:00`` offset, a fractional second, and the ISO end-of-day ``24:00:00Z`` —
  still project as satisfied, each checked against the production contract in
  the same test so the two validators cannot drift apart silently.

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
from conductor.command.contracts import DecisionReceipt
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_adapters import FakeAdapter
from tests.test_command_run_store import CONFIG, a_run
from tests.test_store import good_lane, write_project


RUN_ID = "run-cockpit-gates"
TOKEN = "browser-only-process-token"
GATE_ID = "gate-release"
DIGEST = "sha256:" + "0" * 64
IMPOSSIBLE = "2026-99-99T99:99:99Z"
ACCEPTED_INSTANTS = [
    "2026-08-17T12:00:00Z",
    "2026-08-17T12:00:00+00:00",
    "2026-08-17T12:00:00.123456Z",
    "2026-08-17T24:00:00Z",
]
REFUSED_INSTANTS = [
    IMPOSSIBLE,
    "2026-13-01T00:00:00Z",
    "2026-02-29T00:00:00Z",
    "2026-08-17T25:00:00Z",
    "2026-08-17T12:60:00Z",
    "2026-08-17T12:00:60Z",
    "2026-08-17T24:00:01Z",
    "2026-08-17T12:00:00+05:00",
    "yesterday",
    "",
]


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


@pytest.mark.parametrize("instant", REFUSED_INSTANTS)
def test_an_instant_production_refuses_is_corrupt_and_never_satisfied(
        gate_page: Page, instant: str) -> None:
    """What the durable contract will not store, the Cockpit will not display."""
    with pytest.raises(Exception):
        DecisionReceipt.from_dict(receipt(instant)["record"])
    assert project_gates(gate_page, [receipt(instant)]) == {
        "corrupt": True, "rows": []}


@pytest.mark.parametrize("instant", ACCEPTED_INSTANTS)
def test_an_instant_production_accepts_still_projects_the_gate_as_satisfied(
        gate_page: Page, instant: str) -> None:
    """The refusal is of impossible instants, not of the forms production takes."""
    assert DecisionReceipt.from_dict(receipt(instant)["record"]).decided_at == instant
    assert project_gates(gate_page, [receipt(instant)]) == {
        "corrupt": False, "rows": [{"gateId": GATE_ID, "state": "satisfied"}]}


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
