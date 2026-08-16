"""Source-level safety contract for the bounded read-only Cockpit foundation."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
HTML = PANEL / "index.html"
SCRIPT = PANEL / "command.js"
PROJECTION = PANEL / "command-projection.js"
VIEW = PANEL / "command-view.js"
STYLE = PANEL / "command.css"
#: The Cockpit's script surface is split across three packaged modules, so every
#: whole-surface guard below reads their union — a rule that a later split could
#: satisfy by moving a forbidden string into a sibling file would guard nothing.
SCRIPTS = (SCRIPT, PROJECTION, VIEW)
SOURCE = "\n".join(path.read_text(encoding="utf-8") for path in SCRIPTS)
IMPORTS = r'from "(\./[a-z-]+\.js)";'


def test_panel_mounts_packaged_command_assets_and_one_semantic_region():
    html = HTML.read_text(encoding="utf-8")
    assert html.count('id="commandCockpit"') == 1
    assert '<section class="card" id="commandCockpit"' in html
    assert "proposal-only control · durable history" in html
    assert '<link rel="stylesheet" href="/panel/command.css">' in html
    assert '<script src="/panel/command.js" type="module"></script>' in html
    assert html.count("<script src=") == 1
    assert html.index("/panel/command.js") < html.index("<body>")


def test_the_cockpit_module_graph_is_three_packaged_siblings_with_no_cycle():
    assert all(path.is_file() and path.parent == PANEL for path in SCRIPTS)
    assert sorted(re.findall(IMPORTS, SCRIPT.read_text(encoding="utf-8"))) == [
        "./command-projection.js", "./command-view.js"]
    assert re.findall(IMPORTS, VIEW.read_text(encoding="utf-8")) == [
        "./command-projection.js"]
    assert not re.findall(IMPORTS, PROJECTION.read_text(encoding="utf-8"))
    assert "document" not in PROJECTION.read_text(encoding="utf-8")
    assert "fetch(" not in VIEW.read_text(encoding="utf-8")


def test_command_script_has_one_proposal_only_mutation_door():
    source = SOURCE
    lowered = source.lower()
    for forbidden in (
            "innerhtml", "localstorage", "sessionstorage", "document.cookie",
            "console.", "/actions", "/decisions"):
        assert forbidden not in lowered
    assert source.count('method: "POST"') == 1
    assert source.count("/proposals") == 1
    assert source.count("fetch(") == 3
    assert "new EventSource" not in source
    assert "setInterval" not in source and "setTimeout" not in source
    assert 'readJson(`${base}/controls`)' in source
    assert "textContent" in source and "replaceChildren" in source
    assert 'csrfToken = ""' in source
    assert 'fetch("/command/session", {cache: "no-store"})' in source
    assert '"X-Conduct-CSRF": session.token' in source
    assert "No action was confirmed or executed." in source


def test_command_projection_is_closed_and_drops_sensitive_durable_fields():
    source = SOURCE
    table = re.search(
        r"const RECORD_FIELDS = Object\.freeze\(\{(.*?)\n\}\);", source, re.S)
    assert table
    fields = table.group(1)
    assert set(re.findall(r"^  ([a-z_]+):", fields, re.M)) == {
        "action_proposal", "action_request", "action_result",
        "adapter_observation", "attempt_event", "decision", "evidence",
    }
    for forbidden in (
            "detail", "label", "uri", "recovery_ref", "request_digest",
            "config", "stdout", "stderr", "pid"):
        assert forbidden not in fields
    assert "run.warnings.length" in source
    assert "run.warnings.join" not in source


def test_proposal_composer_has_only_reviewed_closed_fields():
    source = SOURCE
    assert 'name: "run_id"' in source
    assert 'pattern: "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"' in source
    for forbidden in ("argv", "cwd", "environment", "executable", "generic json"):
        assert forbidden not in source.lower()
    exact_fields = {
        "dispatch": (
            "work_item_id", "instruction_ref", "profile", "artifact_refs",
            "output_limit_profile"),
        "review": ("work_item_id", "target_artifact_refs", "review_profile"),
        "evidence": ("target_action_id", "kinds"),
        "stop": ("target_attempt_id", "reason"),
        "retry": ("prior_action_id", "reason"),
        "switch": ("prior_action_id", "target_instance_id", "handoff_ref"),
    }
    table = re.search(
        r"const CAPABILITY_FIELDS = Object\.freeze\(\{(.*?)\n\}\);", source, re.S)
    assert table
    body = table.group(1)
    assert set(re.findall(r"^  ([a-z]+): Object\.freeze", body, re.M)) == set(
        exact_fields)
    for capability, fields in exact_fields.items():
        start = body.index(f"  {capability}: Object.freeze")
        next_starts = [
            body.find(f"  {name}: Object.freeze", start + 1)
            for name in exact_fields if body.find(f"  {name}: Object.freeze", start + 1) >= 0
        ]
        section = body[start:min(next_starts) if next_starts else len(body)]
        assert tuple(re.findall(r'\["([a-z_]+)", "(?:id|ids|ids-required|enum|enum-list)"',
                                section)) == fields
    assert '"implement", "review"' in body
    assert '"quality", "security", "spec"' in body
    assert '"result", "diff", "tests", "status"' in body
    assert '"failed", "unknown", "verification_failed", "user"' in body


def test_proposal_response_is_bound_and_never_automatically_retried_or_confirmed():
    source = SOURCE
    assert source.count("submitProposal") == 2
    assert 'proposalForm.addEventListener("submit", onSubmit)' in source
    assert "canonicalJson(payload.arguments) !== canonicalJson(submitted.arguments)" in source
    assert "canonicalJson(payload.scope) !== canonicalJson(submitted.scope)" in source
    assert "session.generation !== sessionEpoch" in source
    assert '["csrf_denied", "same_origin_denied"].includes(code)' in source
    assert "Outcome unknown. Reload the authoritative run." in source
    assert '["submitting", "outcome-unknown"].includes(state.proposalPhase)' in source
    assert 'state.proposalNotice = "Authoritative run reloaded."' in source
    assert "Proposal created — review only" in source
    assert 'id: "commandReviewTitle"' in source
    for fact in (
            "proposal_id", "preview_digest", "config_digest", "instance",
            "capability", "arguments", "scope", "timeout_seconds", "rationale"):
        assert f"    {fact}:" in source


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
    source = SOURCE
    assert "refreshDirty = true" in source
    assert "if (refreshInFlight) return" in source
    assert "while (refreshDirty)" in source
    assert 'window.addEventListener("conduct:run"' in source
    assert 'window.addEventListener("conduct:connected"' in source
    assert 'window.addEventListener("conduct:disconnected"' in source
    assert '["ready", "refreshing", "stale"].includes(state.phase)' in source
    assert "Showing the last authoritative facts." in source


def test_human_gate_projection_is_closed_and_absence_is_idle():
    source = SOURCE
    states = re.search(
        r"const DECISION_STATES = Object\.freeze\(\{(.*?)\n\}\);", source, re.S)
    assert states
    assert dict(re.findall(r"^  ([a-z_]+): \"([a-z_]+)\"", states.group(1), re.M)) == {
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
