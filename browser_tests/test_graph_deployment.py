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
