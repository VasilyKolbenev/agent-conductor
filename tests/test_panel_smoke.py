"""Smoke tests for the packaged panel (Task 14) — served HTML references the protocol."""
import urllib.request

from tests.test_server import start
from tests.test_store import write_project, good_lane


def _fetch_panel(root):
    srv, base = start(root)
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            return r.read().decode()
    finally:
        srv.shutdown()
        # Not in the mandated snippet: prevents socket leaks across the suite —
        # same documented teardown-hygiene deviation Task 13 made.
        srv.server_close()


def test_panel_serves_and_references_state(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for token in ("state.json", "EventSource", "id=\"map\"", "id=\"queue\"",
                  "id=\"findings\"", "id=\"warnings\"", "prefers-color-scheme"):
        assert token in html


def test_panel_has_all_tooling_ids(tmp_path):
    # The full id contract promised to future tooling (plan Task 14, delta 5).
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for element_id in ("map", "cycle", "kpis", "queue", "findings", "feed", "warnings"):
        assert f'id="{element_id}"' in html


def test_panel_pins_review_vocabulary_tokens(tmp_path):
    # Pin the mandated vocabulary so dropping a chip state or the uncovered
    # hint cannot slip through green (quality-review follow-up).
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for token in ("suspended", "disagreement", "uncovered", "no reviewer assigned",
                  "contested_by", "Conduct — "):
        assert token in html


def test_panel_findings_scannable_title_and_card_fields(tmp_path):
    # C6.2: title is the scannable table column; claim moves into the expanded
    # card alongside the new detail and evidence fields, each with a label.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    assert '<th>title</th>' in html
    assert '<th>claim</th>' not in html
    for label in ('"Claim"', '"Detail"', '"Evidence"'):
        assert label in html


def test_panel_a11y_and_live_title_markers(tmp_path):
    # Reduced-motion support and the live document title are part of the delta list.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    assert "prefers-reduced-motion" in html
    assert "waiting on you" in html


def test_panel_attention_zone_and_agents_block(tmp_path):
    # C6.3: the action loop — attention zone, agents block, copy decision brief.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for token in ('id="attention"', 'id="agents"', "Reply to:", "Copy decision brief",
                  "Nothing needs you right now.", "No lanes yet."):
        assert token in html


def test_panel_decision_first_section_order(tmp_path):
    # Attention (holding the queue) sits above agents, which sit above the map.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    order = [html.index(f'id="{i}"')
             for i in ("attention", "queue", "agents", "map", "findings", "feed")]
    assert order == sorted(order)
