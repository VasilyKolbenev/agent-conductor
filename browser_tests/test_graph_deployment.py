"""What a step really RUNS ON: the product and the model behind its instance.

Split from test_graph_rendered.py when that module crossed the 800-line cap, on
the seam the December Command's fifth item drew. A plan names a ROLE, a run's
binding names an INSTANCE, and only the frozen configuration says which product
serves that instance and which model it pins. This module is that last joint,
end to end on the screen -- the rendering circuit (geometry, cards, forms,
providers) stays next door, and the payload-refusal circuit is in
test_graph_boundary.py.

The product renders here as an ID and not as a display name, and that is the
default fixture's own rule rather than a shortfall: it ships an EMPTY registry
on purpose, because vendor rows are data the server supplies and a second copy
of that table in a fixture is drift this window refuses to own. The display
name is asserted in test_graph_wire.py, against a real server.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from browser_tests.test_graph_rendered import (  # noqa: F401 — fixtures register
    graph_page, graph_url)

def detail_text(page: Page) -> str:
    """The detail card as a reader sees it, headings included.

    The stylesheet uppercases every `h3`, so `inner_text` answers "DEPLOYMENT"
    where the source says "Deployment". Read through one helper so a case
    asserting on a heading cannot be written against the source spelling.
    """
    return page.locator("#detailCard").inner_text()


def test_every_step_is_drawn_as_the_product_its_own_instance_is_served_by(
        graph_page: Page) -> None:
    """The consistency the default used to break in four places at once.

    A step draws a product and binds an instance, and the two are different
    documents -- the plan names the instance, the deployment says which product
    serves it. They may not disagree, and they did: every thinking step bound
    `claude-dev` while drawing a different product, so one instance appeared as
    four products in one picture.

    Asserted as a join over EVERY bound step rather than over the one that was
    reported, because the reported one was the smaller half of the defect.
    """
    rows = graph_page.evaluate(
        "({nodes: window.conductGraph.state().nodes.map(n =>"
        " ({harness: n.harness, instance: n.binding && n.binding.instanceId})),"
        " deployment: window.conductGraph.state().deployment})")
    served = {row["instanceId"]: row["adapterId"] for row in rows["deployment"]}

    bound = [row for row in rows["nodes"] if row["instance"]]
    assert len(bound) == 5, bound
    for row in bound:
        assert row["instance"] in served, row
        assert served[row["instance"]] == row["harness"], row
    # And one instance is not four products: the map is one-to-one here.
    assert len(set(served.values())) == len(served)


def test_the_default_shows_the_product_and_the_model_a_binding_really_runs_on(
        graph_page: Page) -> None:
    """The product and Opus 5 for a `claude-dev` binding, on the screen.

    The chain the December Command asked for, read off the rendered detail
    card: the plan names an instance, the deployment names the product and the
    model, and the card shows both under a heading of their own so neither can
    be read as something the plan demanded.

    The product renders as `claude-code` here and not as "Claude Code", and
    that is the default's own rule rather than a shortfall: this fixture
    carries an EMPTY registry on purpose, because vendor rows are data the
    server supplies and a second copy of that table in a fixture is the drift
    this window refuses to own. With no row, a badge draws the id it was given
    -- which is a true statement about how much is known here. The display name
    is asserted where a registry really is loaded: see
    `test_graph_wire.py`, which drives a real server.

    Headings are uppercased by the stylesheet, so the rendered text is what a
    reader sees and what this reads back.
    """
    graph_page.locator('[data-node-id="do"]').click()
    card = detail_text(graph_page)

    assert "instance: claude-dev" in card
    assert "DEPLOYMENT" in card
    assert "claude-code" in card
    assert "model: claude-opus-5" in card
    # The model is NOT a resource: a plan makes no durable demand about one.
    rows = graph_page.locator("#detailCard .g-resources li")
    assert [rows.nth(i).inner_text() for i in range(rows.count())] == [
        "sandbox: project-root"]


def test_an_instance_that_pins_no_model_says_so_instead_of_showing_nothing(
        graph_page: Page) -> None:
    """`null` is a state a reader must be able to see, not a blank.

    Three of the default's four instances pin no model. A card that simply
    omitted the line would read exactly like one whose configuration this
    window could not read at all -- and those are different facts.
    """
    graph_page.locator('[data-node-id="identify"]').click()
    card = detail_text(graph_page)

    assert "instance: codex-review" in card
    assert "none pinned" in card
    assert "claude-opus-5" not in card


_FORGED = {"instance_id": "claude-dev", "adapter_id": "attacker-first",
           "model": "forged-model"}
_HONEST = {"instance_id": "claude-dev", "adapter_id": "claude-code",
           "model": "claude-opus-5"}
#: A second instance the default really binds, and one nothing disputes. It is
#: in every payload below so the refusal can be seen to reach ONE instance and
#: not the projection: a rule that emptied the whole document on any conflict
#: would satisfy the conflict cases and take an honest deployment down with it.
_BYSTANDER = {"instance_id": "codex-review", "adapter_id": "codex",
              "model": None}
#: Both orders, because "first row wins" is invisible in one of them. A rule
#: that kept the first would look correct whenever the honest row happened to
#: arrive first, which is exactly the arrangement nobody controls.
_CONFLICTS = (("forged-first", [_FORGED, _HONEST, _BYSTANDER]),
              ("honest-first", [_HONEST, _FORGED, _BYSTANDER]))


def _load_deployment(page: Page, rows: list[dict]) -> object:
    """Feed the shipped default with a deployment of this shape, one seam only.

    The default's own nodes, so the payload differs from the one this window
    boots with in exactly the rows under test.
    """
    return page.evaluate(
        """rows => import("./graph-default.js").then(module => {
             const payload = JSON.parse(JSON.stringify(module.DALIO_DEFAULT));
             payload.deployment = rows;
             return window.conductGraph.load(payload);
           })""", rows)


@pytest.mark.parametrize("label,rows", _CONFLICTS,
                         ids=[row[0] for row in _CONFLICTS])
def test_two_deployment_rows_for_one_instance_leave_neither_on_the_screen(
        graph_page: Page, label, rows) -> None:
    """Two answers to one question, and this window may not pick one.

    A server that answered twice for one instance has said something a reader
    cannot resolve, and the earlier rule -- keep the first, drop the rest --
    resolved it by ARRIVAL ORDER. That is not a fact about the deployment: it
    hands whichever row came first the authority to name a product and a model,
    so a Human is shown a provider that may be neither.

    Neither row survives. The instance falls back to the state this window
    already has for "the configuration was not read", which stays honest and
    leaves the graph readable -- refusing the whole projection would take a
    plan off the screen over a fact the plan does not depend on.
    """
    assert _load_deployment(graph_page, rows) is True

    shown = graph_page.evaluate("window.conductGraph.state().deployment")
    # The disputed instance is gone; the one nothing disputed is untouched.
    assert [row["instanceId"] for row in shown] == ["codex-review"], shown
    graph_page.locator('[data-node-id="do"]').click()
    card = detail_text(graph_page)
    assert "has not read this run's configuration" in card
    assert "attacker-first" not in card and "forged-model" not in card
    assert "claude-opus-5" not in card
    graph_page.locator('[data-node-id="identify"]').click()
    assert "none pinned" in detail_text(graph_page)


def test_a_single_row_for_that_instance_is_still_shown(graph_page: Page) -> None:
    """The control: the refusal above is about the CONFLICT, not the instance.

    Without this, a projection that dropped every row would satisfy both cases
    above and look like a working guard.
    """
    assert _load_deployment(graph_page, [_HONEST]) is True

    shown = graph_page.evaluate("window.conductGraph.state().deployment")
    assert [row["instanceId"] for row in shown] == ["claude-dev"]
    graph_page.locator('[data-node-id="do"]').click()
    card = detail_text(graph_page)
    assert "model: claude-opus-5" in card
    assert "has not read this run's configuration" not in card
