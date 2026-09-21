"""Source-level safety contract for the bounded read-only Cockpit foundation."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

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


def test_command_script_has_one_post_door_reaching_two_named_routes():
    source = SOURCE
    lowered = source.lower()
    for forbidden in (
            "innerhtml", "localstorage", "sessionstorage", "document.cookie",
            "console.", "/decisions"):
        assert forbidden not in lowered
    assert lowered.count("/actions") == 1
    assert re.findall(r'submitJson\(runTarget\("(/[a-z]+)"\)', source) == [
        "/proposals", "/actions"]
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
    # The ESCAPED hyphen, and this expectation was updated deliberately rather
    # than widened: it used to pin the unescaped form, which is what kept the
    # defect in place. A browser compiles `pattern` with the RegExp `v` flag
    # first, where a bare trailing `-` in a class is a syntax error, and a
    # pattern that fails to compile is IGNORED rather than enforced. This is a
    # change detector on the spelling; the FACT -- that the shipped attribute
    # really refuses a bad id in a real engine -- is held in
    # `browser_tests/test_panel_confirm.py`, because no Python regex library
    # has `v` semantics to answer it with.
    assert r'pattern: "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}"' in source
    for forbidden in ("argv", "cwd", "environment", "executable", "generic json"):
        assert forbidden not in source.lower()
    exact_fields = {
        "dispatch": (
            "work_item_id", "instruction_ref", "profile", "artifact_refs",
            "output_limit_profile"),
        "review": (
            "work_item_id", "target_artifact_refs", "result_artifact_ref",
            "review_profile"),
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
        # The `artifact-` prefix is ADMITTED here and judged below for what it
        # means: this is about which fields are declared and in what order.
        assert tuple(re.findall(
            r'\["([a-z_]+)", "(?:artifact-)?(?:id|ids|ids-required|enum'
            r'|enum-list)"', section)) == fields
    assert '"implement", "review"' in body
    assert '"quality", "security", "spec"' in body
    assert '"result", "diff", "tests", "status"' in body
    assert '"failed", "unknown", "verification_failed", "user"' in body


def test_the_task_scope_is_attached_from_the_run_and_never_typed():
    """A CHANGE DETECTOR on the wiring, not the proof. The facts -- the exact
    frozen scope in the POST, none for a task-less run, a binding that does not
    read disabling the composer, and no late answer drawn into another run --
    are held in `browser_tests/test_panel_task_scope.py`, because only a real
    engine against the real server can answer them. Here: the scope is never
    one of the typed fields, the view never names it, the capabilities that
    carry it are derived from the table, and the body's arguments are the
    scoped ones built from the selected run's own read.
    """
    table = re.search(
        r"const CAPABILITY_FIELDS = Object\.freeze\(\{(.*?)\n\}\);", SOURCE, re.S)
    assert table and "work_scope" not in table.group(1)
    assert "work_scope" not in VIEW.read_text(encoding="utf-8")
    assert "Object.keys(CAPABILITY_FIELDS).filter(" in PROJECTION.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    assert "arguments: scoped," in script
    assert "state.task = projectTaskBinding(run);" in script


def test_the_cockpit_bounds_a_task_binding_exactly_as_the_task_contract_does():
    """The one number the Cockpit copies from the Python task contract, held equal
    to it across the language boundary: a bound that drifted on either side would
    read a binding the server refuses as bound, or the other way round."""
    from conductor.command.task_contracts import MAX_TASK_ID
    declared = re.findall(r"^const MAX_TASK_ID = (\d+);$",
                          PROJECTION.read_text(encoding="utf-8"), re.M)
    assert declared == [str(MAX_TASK_ID)]


def _artifact_marks() -> dict[str, list[tuple[str, str]]]:
    """Every ``artifact-`` marked field of every capability, per capability."""
    body = re.search(
        r"const CAPABILITY_FIELDS = Object\.freeze\(\{(.*?)\n\}\);",
        PROJECTION.read_text(encoding="utf-8"), re.S).group(1)
    heads = list(re.finditer(r"^  ([a-z]+): Object\.freeze", body, re.M))
    marked: dict[str, list[tuple[str, str]]] = {}
    for at, head in enumerate(heads):
        end = heads[at + 1].start() if at + 1 < len(heads) else len(body)
        marked[head.group(1)] = re.findall(
            r'\["([a-z_]+)", "(artifact-[a-z-]+)"', body[head.start():end])
    return marked


#: A payload each argument type ACCEPTS whole, so a refusal driven below is
#: caused by the one field that was replaced and by nothing else.
_WHOLE_PAYLOAD = {
    "dispatch": {
        "work_item_id": "work-1", "instruction_ref": "instr-1",
        "profile": "implement", "artifact_refs": ["a-1"],
        "output_limit_profile": "normal"},
    "review": {
        "work_item_id": "work-1", "target_artifact_refs": ["a-1"],
        "result_artifact_ref": "a-2", "review_profile": "quality"},
}


def test_exactly_three_fields_are_marked_as_carrying_artifact_references():
    """Which field carries artifacts is READ off the projection, so pin it.

    The Studio's inputs-and-outputs section finds both of its controls by the
    ``artifact-`` prefix and names no capability at all -- which is the whole
    point, because a capability is a word the provider roster supplies at run
    time. That makes these three rows load-bearing in a way no row in this
    table was before: mark the wrong field and a person edits the wrong
    argument, in a window that would look entirely correct.

    The last relation is the sharpest. The field marked as a step's own OUTPUT
    belongs to exactly the capability ``artifacts.REVIEW_CAPABILITY`` names --
    the one whose action publishes a durable artifact -- and it is held in BOTH
    directions, because the reachable mistake is marking a second capability as
    publishing one when its evidence is a change digest and no artifact exists
    to name at all.
    """
    from conductor.command import artifacts

    marked = _artifact_marks()
    assert marked["dispatch"] == [("artifact_refs", "artifact-ids")]
    assert marked["review"] == [
        ("target_artifact_refs", "artifact-ids-required"),
        ("result_artifact_ref", "artifact-id")]
    # Every OTHER capability marks nothing, so the lookup finds no control to
    # draw on a step whose schema has no artifact seam at all.
    assert {name for name, found in marked.items() if found} == {
        "dispatch", "review"}
    produced = {
        capability for capability, found in marked.items()
        if any(kind == "artifact-id" for _, kind in found)}
    assert produced == {artifacts.REVIEW_CAPABILITY}, produced


def test_each_artifact_mark_is_what_the_python_schema_really_enforces():
    """The marks, driven against the argument types rather than read beside them.

    Three relations, and each is a claim the window makes out loud:

    - a field marked as a LIST is one the type refuses a bare string for;
    - a field marked ``-required`` is one it refuses an EMPTY list for, and one
      marked without that suffix is one it ACCEPTS an empty list for. That is a
      real difference between the two shipped schemas -- a step that carries
      work out may require nothing, a step that checks work may not -- and the
      window states it beside the control, so flattening it here would let the
      window flatten it too;
    - a field marked as a scalar is one the type refuses a list for.
    """
    from conductor.command.adapters.deep_commands import (
        DEEP_ARGUMENT_TYPES,
        DeepContractError,
    )

    for capability, found in _artifact_marks().items():
        if not found:
            continue
        whole = _WHOLE_PAYLOAD[capability]
        argument_type = DEEP_ARGUMENT_TYPES[capability]
        assert argument_type.from_dict(dict(whole)) is not None
        for name, kind in found:
            if kind == "artifact-id":
                with pytest.raises(DeepContractError):
                    argument_type.from_dict({**whole, name: ["a-2"]})
                continue
            with pytest.raises(DeepContractError):
                argument_type.from_dict({**whole, name: "a-1"})
            empty = {**whole, name: []}
            if kind.endswith("-required"):
                with pytest.raises(DeepContractError):
                    argument_type.from_dict(empty)
            else:
                assert argument_type.from_dict(empty) is not None


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


def test_the_only_action_route_is_the_separate_human_confirm_submission():
    source = SCRIPT.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert SOURCE.count("/actions") == 1
    body = re.search(
        r"  async function confirmProposal\(event\) \{(.*?)\n  \}", source, re.S)
    assert body
    assert body.group(1).count('runTarget("/actions")') == 1
    assert body.group(1).lstrip().startswith("event.preventDefault();")
    assert source.count("confirmProposal") == 2
    assert (
        "renderConfirm(confirmMount, confirmStatus, state, draft, confirmProposal)"
        in source)
    assert view.count("onConfirm") == 2
    assert 'form.addEventListener("submit", onConfirm)' in view
    tail = source[source.index('window.addEventListener("conduct:run"'):]
    assert "confirmProposal" not in tail and "/actions" not in tail


def test_the_confirmation_body_is_copied_only_from_the_frozen_snapshot():
    projection = PROJECTION.read_text(encoding="utf-8")
    source = SCRIPT.read_text(encoding="utf-8")
    snapshot = re.search(
        r"  const confirmation = Object\.freeze\(\{(.*?)\n  \}\);", projection, re.S)
    assert snapshot
    assert set(re.findall(r"^    ([a-z_]+):", snapshot.group(1), re.M)) == {
        "proposal_id", "preview_digest", "capability", "scope", "config_digest"}
    assert all(
        f"{name}: payload.{name}" in snapshot.group(1)
        for name in ("proposal_id", "preview_digest", "capability", "config_digest"))
    body = re.search(
        r"export function confirmationBody\(proposal, confirmedBy\) \{(.*?)\n\}",
        projection, re.S)
    assert body
    assert set(re.findall(r"^    ([a-z_]+):", body.group(1), re.M)) == {
        "proposal_id", "preview_digest", "capability", "scope", "config_digest",
        "confirmed_by"}
    assert "const snapshot = proposal.confirmation;" in body.group(1)
    assert body.group(1).count("snapshot.") == 5
    assert re.findall(r"^    confirmed_by: (\w+),", body.group(1), re.M) == ["actor"]
    for live in ("draft", "state.", "document", "FormData", "composer"):
        assert live not in body.group(1)
    # The whole confirmed body, pinned as one statement: a spread that overrides
    # a field from the live composer is exactly what this refuses to admit.
    assert (
        "\n    const submitted = confirmationBody(\n"
        '      state.proposal, String(data.get("confirmed_by") || ""));\n'
    ) in source
    assert SOURCE.count("confirmationBody") == 3


def test_the_confirm_control_is_named_human_work_that_never_claims_execution():
    view = VIEW.read_text(encoding="utf-8")
    source = SCRIPT.read_text(encoding="utf-8")
    projection = PROJECTION.read_text(encoding="utf-8")
    confirm = re.search(
        r"export function renderConfirm\(.*?\n\}", view, re.S)
    assert confirm
    for fact in (
            'text: "Confirm unchanged proposal"', 'id: "commandConfirmTitle"',
            '"aria-describedby": "commandConfirmNote"', 'name: "confirmed_by"',
            r'pattern: "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}"', 'element("form"',
            'type: "submit"', "state.action"):
        assert fact in confirm.group(0)
    action = re.search(
        r"export function projectAction\(payload, submitted, runId, binding\) "
        r"\{(.*?)\n\}", projection, re.S)
    assert action
    assert set(re.findall(r"^    ([a-z_]+):", action.group(1), re.M)) == {
        "action_id", "capability", "mode"}
    # The load-bearing fact: an accepted authorization projects request identity
    # only, so no execution outcome exists for the Cockpit to render or imply.
    for outcome in ("outcome", "result", "stdout", "stderr", "exit_code",
                    "finished_at", "receipt_id", "verification"):
        assert outcome not in action.group(1)
    # Change-detectors for the two sentences that carry that fact to the Human.
    assert "Action request accepted and recorded. Nothing was executed." in source
    assert "Acceptance records one authorized request; nothing is executed." in view


ACTION_ARMS = [
    'if (payload.mode !== "confirm") return null;',
    "if (payload.requested_by !== submitted.confirmed_by) return null;",
    "if (!actionEchoesSnapshot(payload, binding)) return null;",
    "if (!binding || payload.idempotency_key !== binding.idempotency_key) return null;",
]
ECHOED = {
    "attempt_id", "instance_id", "capability", "preview_digest",
    "timeout_seconds", "arguments", "scope",
}


def test_an_accepted_action_must_be_a_confirm_by_the_named_human_on_the_snapshot():
    """The four refusals, each its own statement, none of them a default."""
    projection = PROJECTION.read_text(encoding="utf-8")
    body = re.search(
        r"export function projectAction\(payload, submitted, runId, binding\) "
        r"\{(.*?)\n\}", projection, re.S)
    assert body
    assert [
        line.strip() for line in body.group(1).splitlines()
        if line.startswith("  if (") and line.rstrip().endswith("return null;")
    ] == ACTION_ARMS
    # The endpoint is Confirm-only; Policy is a separate authority seam that no
    # Human click stands in for, so the old two-value admission is gone.
    assert '["confirm", "policy"].includes(payload.mode)' not in projection
    assert "projectAction(result.payload, submitted, state.runId, binding)" in (
        SCRIPT.read_text(encoding="utf-8"))


def test_the_frozen_snapshot_carries_every_fact_the_action_response_must_echo():
    projection = PROJECTION.read_text(encoding="utf-8")
    binding = re.search(
        r"function proposalBinding\(payload\) \{(.*?)\n\}", projection, re.S)
    assert binding
    assert set(re.findall(r"^    ([a-z_]+):", binding.group(1), re.M)) == (
        ECHOED | {"idempotency_key"})
    assert all(f"{name}: payload.{name}" in binding.group(1) for name in (
        "attempt_id", "instance_id", "capability", "preview_digest",
        "timeout_seconds"))
    echo = re.search(
        r"function actionEchoesSnapshot\(payload, binding\) \{(.*?)\n\}",
        projection, re.S)
    assert echo
    assert set(re.findall(r"payload\.([a-z_]+)", echo.group(1))) == ECHOED
    assert "if (!binding || typeof binding !== \"object\") return false;" in echo.group(1)
    assert (
        "  return Object.freeze({binding: proposalBinding(payload), "
        "confirmation, facts});") in projection
    # The confirmed body is still copied from `confirmation` alone: the binding
    # is a fact the Cockpit checks against, never a field it sends.
    assert "binding" not in re.search(
        r"export function confirmationBody\(proposal, confirmedBy\) \{(.*?)\n\}",
        projection, re.S).group(1)


def test_the_cockpit_recomputes_the_runtime_idempotency_derivation_it_checks():
    """The key is derived, never echoed — so both sides of it are pinned here."""
    runtime = (ROOT / "src" / "conductor" / "command" / "runtime.py").read_text(
        encoding="utf-8")
    assert 'idempotency_key=f"dispatch-{proposal.proposal_id}"' in runtime
    projection = PROJECTION.read_text(encoding="utf-8")
    assert "idempotency_key: `dispatch-${payload.proposal_id}`," in projection
    assert "payload.idempotency_key !== binding.idempotency_key" in projection


def test_the_action_response_must_carry_every_mandatory_id_and_one_utc_instant():
    projection = PROJECTION.read_text(encoding="utf-8")
    ids = re.search(
        r"const ACTION_IDS = Object\.freeze\(\[(.*?)\]\);", projection, re.S)
    assert ids
    assert set(re.findall(r'"([a-z_]+)"', ids.group(1))) == {
        "action_id", "run_id", "attempt_id", "instance_id", "capability",
        "requested_by", "idempotency_key"}
    present = re.search(
        r"function actionFactsPresent\(payload\) \{(.*?)\n\}", projection, re.S)
    assert present
    assert "ACTION_IDS.every((name) => isId(payload[name]))" in present.group(1)
    assert "UTC_INSTANT.test(payload.requested_at)" in present.group(1)
    assert "DIGEST.test(payload.preview_digest" in present.group(1)
    assert "Number.isInteger(payload.timeout_seconds)" in present.group(1)


def test_the_requested_at_instant_is_validated_by_calendar_not_only_the_regex():
    """A UTC_INSTANT match is a shape; a real instant is a calendar fact too.

    The projection must accept for ``requested_at`` exactly what the production
    ActionRequest contract accepts (``command/contracts.py`` ``_timestamp``): so
    the regex can never stand in for the fact, and a value like
    ``2026-99-99T99:99:99Z`` is refused, not accepted. This pins the semantic
    gate so a revert to regex-only reds a source guard too. *Which* instants the
    two sides agree on is not pinned by these substrings but by the shared
    corpus, driven through both validators in the fast suite and the browser.
    """
    projection = PROJECTION.read_text(encoding="utf-8")
    present = re.search(
        r"function actionFactsPresent\(payload\) \{(.*?)\n\}", projection, re.S)
    assert present
    # Both gates, in order: the shape, then the instant it must name.
    assert "UTC_INSTANT.test(payload.requested_at)" in present.group(1)
    assert "instantIsValid(payload.requested_at)" in present.group(1)
    body = re.search(
        r"function instantIsValid\(value\) \{(.*?)\n\}", projection, re.S)
    assert body
    checks = body.group(1)
    # The proleptic-Gregorian leap rule and the month and day bounds. The clock
    # fields carry no special case: 24:00:00 is outside the frozen grammar, so
    # an hour above 23 is refused like any other impossible field.
    assert "year % 4 === 0 && year % 100 !== 0" in checks and "year % 400" in checks
    assert "month < 1 || month > 12" in checks
    assert "day < 1 || day > maxDay" in checks
    assert "hour <= 23 && minute <= 59 && second <= 59" in checks
    assert "24" not in checks


def test_mutation_controls_are_disabled_while_disconnected_stale_or_uncertain():
    """Which phases may still be worked, and which may not.

    This used to pin `state.phase !== "ready"` by its spelling, which made it a
    change detector on a rule rather than a guard on a fact -- and the rule was
    wrong: a BACKGROUND refresh disabled the form, and disabling a form blurs
    whatever is focused in it, so a signal took the keyboard away from whoever
    was typing for the length of a read. The fact held now is the allowlist.

    Putting `refreshing` on it opened a hole of its own, which is the second
    fact here: a phase says what the last READ did and any later read overwrites
    it, so a refresh starting after the stream dropped replaced `stale` with
    `refreshing` and the write door came back open on a dead connection. The
    LINE is tracked apart from the phase and asked first.
    """
    view = VIEW.read_text(encoding="utf-8")
    source = SCRIPT.read_text(encoding="utf-8")
    workable = re.search(
        r"const WORKABLE_PHASES = Object\.freeze\(\[(.*?)\]\)", view)
    assert workable, "the phase allowlist is gone"
    allowed = set(re.findall(r'"([a-z-]+)"', workable.group(1)))
    assert allowed == {"ready", "refreshing"}, allowed
    # The line is asked FIRST, and by a helper both forms spend -- a second
    # copy of this question is how one form comes to open while the other shuts.
    gate = re.search(r"function workable\(state\) \{(.*?)\n\}", view, re.S)
    assert gate, "the workable-state helper is gone"
    assert "state.connected !== false" in gate.group(1), gate.group(1)
    assert "WORKABLE_PHASES.includes(state.phase)" in gate.group(1)
    # And whether the facts are known current: `refreshing` is set when a read
    # STARTS, so the retry after a failed read looked like an ordinary refresh.
    assert "state.current === true" in gate.group(1), gate.group(1)
    for fact in ("state.current = true", "state.current = false"):
        assert fact in source, fact
    # Both forms are held to it, and both still shut on the uncertain arm.
    assert view.count("!workable(state)") == 2
    # And nothing but the stream's own two signals moves the line.
    assert source.count("state.connected = false") == 1
    assert source.count("state.connected = true") == 1
    assert "connected: true," in source
    assert view.count('["submitting", "outcome-unknown"].includes') == 2
    assert view.count("for (const control of ") == 2
    assert "includes(state.confirmPhase)" in view
    disconnected = source[
        source.index('window.addEventListener("conduct:disconnected"'):]
    for fact in ("epoch += 1", "sessionEpoch += 1", 'csrfToken = ""',
                 "state.connected = false", 'state.phase = "stale"'):
        assert fact in disconnected
    fresh = re.search(
        r"if \(explicit && runId !== state\.runId\) \{(.*?)\n    \}", source, re.S)
    assert fresh
    for reset in ("state.action = null", 'state.confirmPhase = "idle"',
                  'state.confirmNotice = ""'):
        assert reset in fresh.group(1)
    assert 'state.confirmNotice = "Authoritative run reloaded."' in source



def test_the_keyboard_is_given_back_where_the_person_actually_was():
    """The other half of the same render, and its own fact.

    A form that may be worked is no use to somebody the render threw out of it.
    Both forms give the place back through ONE helper -- two call sites and the
    one declaration -- because two copies of a restoration is how they come to
    disagree about what "where a person was" means. By NAME rather than by
    position, and with the CARET rather than just the field: a control handed
    back with the caret at the end moves a person who was correcting a letter
    to the end of their own word.
    """
    view = VIEW.read_text(encoding="utf-8")

    assert view.count("restoreFocus(") == 3, view.count("restoreFocus(")
    assert view.count("focusedPlace(") == 3, view.count("focusedPlace(")
    # Change detector on the lookup: by comparison, never a selector built from a
    # name -- that spelling threw on `argument:<field>` names and froze the panel
    # (the fact is held in browser_tests/test_panel_task_scope.py).
    assert "[...form.elements].find((row) =>" in view
    assert "form.querySelector(" not in view
    assert "control.setSelectionRange(place.caret.start, place.caret.end)" in view
    # Read BEFORE the replacement, on both forms: the node is about to stop
    # existing, so nothing about it can be read afterwards.
    for mount in ("composer", "confirm"):
        before = view.index(f"focusedPlace({mount})")
        assert before < view.index(f"{mount}.replaceChildren()"), mount
    # A form nobody was working in answers null, so no focus is taken from
    # wherever it really is.
    assert "if (!mount.contains(active) || active === mount) return null;" in view

def test_the_local_session_token_is_only_ever_a_header_value_in_memory():
    for forbidden in (
            "localStorage", "sessionStorage", "document.cookie", "searchParams",
            "URLSearchParams", "location.search", "history.replaceState"):
        assert forbidden not in SOURCE
    assert "csrf" not in VIEW.read_text(encoding="utf-8").lower()
    assert "token" not in PROJECTION.read_text(encoding="utf-8").lower()
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count('"X-Conduct-CSRF": session.token') == 1
    # Every line that touches the token, enumerated: a DOM, URL or storage sink
    # cannot be added without appearing here.
    assert [line.strip() for line in source.splitlines() if "csrfToken" in line] == [
        'let epoch = 0, csrfToken = "", sessionEpoch = 0;',
        "if (csrfToken) return {generation: sessionEpoch, token: csrfToken};",
        "csrfToken = payload.csrf_token;",
        "return {generation, token: csrfToken};",
        'csrfToken = "";',
        'csrfToken = "";',
    ]


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
    # One door for every frame. A second message listener cannot read the same
    # frame under a second set of rules if there is nowhere for it to attach.
    assert html.count("es.onmessage") == 1
    assert 'addEventListener("message"' not in html
    assert 'frame.kind !== "run"' in html
    assert 'typeof frame.run_id !== "string"' in html
    assert "COMMAND_RUN_SIGNAL.test(frame.run_id)" in html
    assert 'new CustomEvent("conduct:run", { detail })' in html
    assert 'Object.freeze({ run_id: frame.run_id })' in html


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
