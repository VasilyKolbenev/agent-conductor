"""Source-level safety contract for the bounded read-only Cockpit foundation."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
HTML = PANEL / "index.html"
SCRIPT = PANEL / "command.js"
STYLE = PANEL / "command.css"


def test_panel_mounts_packaged_command_assets_and_one_semantic_region():
    html = HTML.read_text(encoding="utf-8")
    assert html.count('id="commandCockpit"') == 1
    assert '<section class="card" id="commandCockpit"' in html
    assert '<link rel="stylesheet" href="/panel/command.css">' in html
    assert '<script src="/panel/command.js" defer></script>' in html
    assert html.index("/panel/command.js") < html.index("<body>")


def test_command_script_has_no_mutation_or_browser_persistence_door():
    source = SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in (
            "innerhtml", "localstorage", "sessionstorage", "document.cookie",
            "console.", 'method: "post"', "/proposals", "/actions", "/decisions",
            "csrf_token"):
        assert forbidden not in lowered
    assert source.count("fetch(") == 1
    assert "new EventSource" not in source
    assert "setInterval" not in source and "setTimeout" not in source
    assert 'readJson(`${base}/controls`)' in source
    assert "textContent" in source and "replaceChildren" in source


def test_command_projection_is_closed_and_drops_sensitive_durable_fields():
    source = SCRIPT.read_text(encoding="utf-8")
    table = re.search(
        r"const RECORD_FIELDS = Object\.freeze\(\{(.*?)\n  \}\);", source, re.S)
    assert table
    fields = table.group(1)
    assert set(re.findall(r"^    ([a-z_]+):", fields, re.M)) == {
        "action_proposal", "action_request", "action_result",
        "adapter_observation", "attempt_event", "decision", "evidence",
    }
    for forbidden in (
            "detail", "label", "uri", "recovery_ref", "request_digest",
            "config", "stdout", "stderr", "pid"):
        assert forbidden not in fields
    assert "run.warnings.length" in source
    assert "run.warnings.join" not in source


def test_only_the_run_selector_is_an_input_and_it_matches_the_server_id_shape():
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count('element("input"') == 1
    assert 'name: "run_id"' in source
    assert 'pattern: "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"' in source
    for forbidden in ("argv", "cwd", "environment", "executable", "generic json"):
        assert forbidden not in source.lower()


def test_command_styles_are_scoped_responsive_and_keyboard_visible():
    css = STYLE.read_text(encoding="utf-8")
    selectors = [
        line.strip() for line in css.splitlines()
        if line.strip().endswith("{") and not line.lstrip().startswith("@")
    ]
    assert selectors and all(line.startswith("#commandCockpit") for line in selectors)
    assert "@media (max-width:760px)" in css
    assert "@media (prefers-reduced-motion:reduce)" in css
    assert ":focus-visible" in css and "min-height:44px" in css


def test_one_existing_sse_boundary_relays_only_valid_run_identifiers():
    html = HTML.read_text(encoding="utf-8")
    assert html.count('new EventSource("/events")') == 1
    assert 'frame.kind !== "run"' in html
    assert 'typeof frame.run_id !== "string"' in html
    assert "COMMAND_RUN_SIGNAL.test(frame.run_id)" in html
    assert 'new CustomEvent("conduct:run", { detail })' in html
    assert 'Object.freeze({ run_id: frame.run_id })' in html
    assert 'es.addEventListener("message", relayCommandRun)' in html


def test_run_signals_coalesce_to_authoritative_gets_and_disconnect_preserves_facts():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "refreshDirty = true" in source
    assert "if (refreshInFlight) return" in source
    assert "while (refreshDirty)" in source
    assert 'window.addEventListener("conduct:run"' in source
    assert 'window.addEventListener("conduct:connected"' in source
    assert 'window.addEventListener("conduct:disconnected"' in source
    assert '["ready", "refreshing", "stale"].includes(state.phase)' in source
    assert "Showing the last authoritative facts." in source


def test_human_gate_projection_is_closed_and_absence_is_idle():
    source = SCRIPT.read_text(encoding="utf-8")
    states = re.search(
        r"const DECISION_STATES = Object\.freeze\(\{(.*?)\n  \}\);", source, re.S)
    assert states
    assert dict(re.findall(r"^    ([a-z_]+): \"([a-z_]+)\"", states.group(1), re.M)) == {
        "approve": "satisfied",
        "reject": "failed",
        "request_changes": "changes_requested",
        "waive": "waived",
    }
    assert 'gateRow("idle", "No Human decision receipt.")' in source
    assert "current.length !== 1" in source
    assert "byId.size !== receipts.length" in source
    assert "prior.runId !== runId || prior.gateId !== gateId" in source


def test_gate_projection_does_not_render_reasons_or_unreviewed_receipt_data():
    source = SCRIPT.read_text(encoding="utf-8")
    render = re.search(r"function render\(\) \{(.*?)\n  \}", source, re.S)
    assert render
    body = render.group(1)
    for forbidden in (
            ".reason", ".actor", ".config_digest", ".evidence_refs",
            ".scope_refs", ".supersedes"):
        assert forbidden not in body
    assert "gate.gateId" in body and "gate.state" in body
    assert 'gateRow("corrupt", "Decision receipt relation is corrupt.")' in body
