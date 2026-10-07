"""The panel's v1 lane drill-down and its canonical handoff copy path."""
import re

from tests.test_panel_cascade import function_body, panel_html


def properties(body: str, name: str) -> set[str]:
    """Every direct property the named local is read through."""
    return set(re.findall(rf"\b{re.escape(name)}\.([A-Za-z_$][\w$]*)", body))


def test_the_lane_drawer_reads_only_fields_protocol_v1_projects():
    body = function_body("renderLaneDetail")
    assert properties(body, "lane") == {"author", "now", "role", "updated"}
    assert properties(body, "role") == {"harness", "stage"}
    assert properties(body, "now") == {"phase", "task", "since"}
    assert properties(body, "f") == {"author", "id", "severity", "review_state", "title"}
    assert properties(body, "w") == {"sources", "kind", "id", "title"}


def test_capabilities_v1_does_not_project_have_no_drawer_placeholder():
    body = function_body("renderLaneDetail")
    for absent in ("model", "prompt", "skills", "runtime_actions"):
        assert absent not in body


def test_a_missing_drawer_value_is_named_as_unrecorded_not_drawn_as_empty():
    body = function_body("recorded")
    assert '"not recorded in state.json"' in body
    assert '"—"' not in body and '""' in body
    assert "value == null" in body


def test_every_agent_row_is_one_keyboard_selectable_lane_and_keeps_its_status_chip():
    body = function_body("renderAgents")
    assert 'role: "button"' in body and 'tabindex: "0"' in body
    assert '"aria-pressed": String(author === LANE_SEL)' in body
    assert "row.dataset.lane = author;" in body
    assert "laneChip(l)" in body
    assert "harnessBadge(harness)" in body


def test_selecting_a_lane_and_a_map_node_are_mutually_exclusive_views():
    body = function_body("activate")
    node = body[body.index('const node = target.closest("[data-node]")'):]
    lane = body[body.index('const lane = target.closest("[data-lane]")'):]
    assert "LANE_SEL = null;" in node[:node.index("return true;")]
    assert "SEL = null;" in lane[:lane.index("return true;")]
    assert "renderDetail(" in node[:node.index("return true;")]
    assert "renderLaneDetail(" in lane[:lane.index("return true;")]


def test_copy_asks_the_read_only_server_for_the_canonical_packet():
    body = function_body("copyHandoff")
    assert '"/handoff/" + encodeURIComponent(author) + ".md"' in body
    assert "await writeClipboard(await r.text())" in body
    assert "LAST" not in body and "state" not in body
    # The nested button is handled before its selectable lane, or a copy click
    # changes the drawer selection instead of only copying the packet.
    activate = function_body("activate")
    assert activate.index('target.closest("[data-handoff-copy]")') < \
        activate.index('target.closest("[data-lane]")')


def test_the_shipped_card_tells_a_new_user_where_both_detail_paths_start():
    html = panel_html()
    assert "select a lane for handoff" in html
    assert "map node or harness lane" in html
    assert "Copy handoff packet" in html
