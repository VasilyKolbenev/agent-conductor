"""The deterministic per-lane handoff packet, over Protocol v1 §6.1 only."""
import copy
import json
import urllib.error

import pytest

from conductor import report
from tests.test_report import FORGERY, _gapless_state
from tests.test_server import get, start
from tests.test_store import good_lane, write_project


def test_the_same_lane_document_renders_the_same_handoff_bytes():
    state = _gapless_state()
    round_tripped = json.loads(json.dumps(state, ensure_ascii=False))
    assert report.handoff(state, "claude").encode("utf-8") == \
        report.handoff(round_tripped, "claude").encode("utf-8")


def test_a_handoff_groups_only_the_selected_lanes_work():
    state = _gapless_state()
    claude = report.handoff(state, "claude")
    assert claude.startswith("# Conduct handoff — claude\n")
    assert "## Findings from this lane — 2" in claude
    assert "`D-1`" in claude and "`D-2`" in claude
    assert "## Human requests from this lane — 1" in claude
    assert "`w-1`" in claude

    reviewer = report.handoff(state, "zed")
    assert "## Findings from this lane — 0" in reviewer
    assert "## Human requests from this lane — 0" in reviewer
    assert "`D-1`" not in reviewer and "`w-1`" not in reviewer


def test_lane_role_and_now_values_are_copied_without_promoting_stage_to_runtime():
    state = _gapless_state()
    text = report.handoff(state, "claude")
    assert "- Role: `impl`" in text
    assert "- Harness: `cc`" in text
    assert "- Assigned stage: `implement`" in text
    assert "- Runtime phase: `implement`" in text

    drifted = copy.deepcopy(state)
    drifted["lanes"][0]["now"]["phase"] = "review"
    moved = report.handoff(drifted, "claude")
    assert "- Assigned stage: `implement`" in moved
    assert "- Runtime phase: `review`" in moved


def test_fields_protocol_v1_does_not_define_never_become_capability_placeholders():
    state = _gapless_state()
    state["lanes"][0].update({"model": "SECRET-MODEL",
                               "prompt": "SECRET-PROMPT",
                               "skills": ["SECRET-SKILL"]})
    state["cycle"]["roles"][0]["runtime_actions"] = ["SECRET-ACTION"]
    text = report.handoff(state, "claude")
    for value in ("SECRET-MODEL", "SECRET-PROMPT", "SECRET-SKILL", "SECRET-ACTION"):
        assert value not in text


def test_authored_text_cannot_forge_a_handoff_heading():
    state = _gapless_state()
    state["lanes"][0]["now"]["task"] = FORGERY
    text = report.handoff(state, "claude")
    assert text.count("\n## Lane\n") == 1
    assert text.count("\n## Findings from this lane") == 1
    assert text.count("\n## Human requests from this lane") == 1
    assert "shown here as `\\n`" in text


def test_an_author_the_document_has_no_lane_for_is_not_an_empty_handoff():
    with pytest.raises(KeyError, match="nobody"):
        report.handoff(_gapless_state(), "nobody")


def test_the_read_only_route_serves_the_packet_of_the_same_state_document(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        state = json.loads(get(base + "/state.json")[1])
        status, body, headers = get(base + "/handoff/claude.md")
        assert status == 200
        assert headers["Content-Type"] == "text/markdown; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"
        assert body == report.handoff(state, "claude").encode("utf-8")
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.parametrize("path", ["/handoff/nobody.md", "/handoff/..%2fmap.md",
                                   "/handoff/claude.json", "/handoff/we!rd.md"])
def test_the_handoff_route_refuses_unknown_or_non_author_segments(tmp_path, path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        with pytest.raises(urllib.error.HTTPError) as rejected:
            get(base + path)
        assert rejected.value.code == 404
    finally:
        srv.shutdown()
        srv.server_close()
