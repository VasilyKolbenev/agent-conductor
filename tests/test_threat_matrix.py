"""Structural guard for the v1 alpha release threat matrix.

The v2 early matrix (``docs/audits/2026-08-13-v2-threat-matrix.md``) recorded a
posture that was true of its own base and was then overtaken by the product. Its
guard could not notice. The held ids were hand-copied into this module, so
promoting a row meant editing the document and the literal in one commit and
nothing independent ever asked whether the promotion was earned; and the only
ratchet on an unheld row was a textual search for a reserved test name, so a
protection that shipped under any other name left the row unheld and the guard
green. All fourteen shipped under another name.

So this module asks the world instead of a literal. Every release row must name a
production door and a witness a parser can resolve: the file must exist, the
symbol must be defined in it, no two rows may lean on one witness, and a witness
must be a test rather than any function that happens to be defined nearby. The
status vocabulary of a release matrix is closed to ``HELD`` -- a threat that is
not held is not a row in the shipped posture, it is a release blocker.

The derivation is a pure function of matrix text and a source corpus, so the
calibration tests below can run it over synthetic inputs and show it failing on a
row whose witness does not exist and on a malformed or duplicated row, next to a
sound synthetic control that passes. A guard that has never been seen red is not
a guard, and a red that the scaffolding could have produced by itself proves
nothing about the fault it claims to catch.

The v2 document is kept, unchanged, as a historical snapshot. Rewriting a dated
record so it reads like today's posture destroys the only evidence of what was
true then; the guard therefore holds it to its own statuses and to its banner.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tests import sabotage_fixtures as sf


ROOT = Path(__file__).parents[1]
AUDITS = ROOT / "docs" / "audits"
RELEASE_MATRIX = AUDITS / "2026-08-28-v1-alpha-release-threat-matrix.md"
HISTORICAL_MATRIX = AUDITS / "2026-08-13-v2-threat-matrix.md"

START_FENCE = "<!-- THREAT-MATRIX:START -->"
END_FENCE = "<!-- THREAT-MATRIX:END -->"
#: The banner the superseded document must keep, so a reader who opens it first
#: is sent to the release posture before reading a single row.
HISTORICAL_MARKER = "<!-- THREAT-MATRIX:HISTORICAL -->"

#: Exactly the fields a release row carries. A row with more or fewer is not a
#: row this guard can judge, so it is refused rather than partially read.
RELEASE_FIELDS = ("Status", "Door", "Fixture", "Expected invariant", "Witness")

#: A reference is one module path and one dotted definition path inside it.
#: Directory and file stems carry no dots, so no reference can climb out of the
#: repository through ``..`` and read a file this guard was never pointed at.
_REFERENCE_RE = re.compile(
    r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.py"
    r"::[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")

#: The release posture, id -> (status, door, witness). This is a change detector
#: and nothing else: the tests around it derive every claim from the document and
#: the source tree, and this literal only makes an edit to a row deliberate. It
#: cannot promote anything by itself -- a row it agrees with still has to resolve.
EXPECTED_ROWS = {
    "CONF-STALE": (
        "HELD",
        "src/conductor/command/runtime.py::ControlRuntime._hold_freshness",
        "tests/test_command_runtime_authorize.py"
        "::test_a_confirmation_older_than_the_freshness_budget_is_refused"),
    "CONF-DIGEST": (
        "HELD",
        "src/conductor/command/contracts.py::ActionProposal.__post_init__",
        "tests/test_command_proposals.py"
        "::test_a_durable_proposal_whose_field_was_edited_without_its_digest_is_refused"),
    "PATH-SCOPE": (
        "HELD",
        "src/conductor/command/contract_values.py::_scope",
        "tests/test_sabotage_fixtures.py::test_path_escape_scopes_trip_the_contract_gate"),
    "PATH-CWD": (
        "HELD",
        "src/conductor/command/containment.py::assess_cwd_route",
        "tests/test_command_process_containment.py::test_a_cwd_outside_the_root_is_refused"),
    "SHELL-INJECT": (
        "HELD",
        "src/conductor/command/adapters/process.py::ProcessRunner._spawn",
        "tests/test_command_process_runner.py"
        "::test_shell_metacharacters_in_an_argument_reach_the_child_as_one_inert_token"),
    "TIMEOUT": (
        "HELD",
        "src/conductor/command/adapters/process.py::ProcessRunner.run",
        "tests/test_command_process_runner.py"
        "::test_a_child_exceeding_its_timeout_is_terminated_and_reported_timed_out"),
    "OUTPUT-BOMB": (
        "HELD",
        "src/conductor/command/adapters/process.py::_Owned._drain",
        "tests/test_command_process_runner.py"
        "::test_output_beyond_the_bound_is_truncated_and_flagged_never_silently_dropped"),
    "DUPLICATE-IDEMPOTENCY": (
        "HELD",
        "src/conductor/command/run_store.py::RunStore.append",
        "tests/test_command_run_store.py"
        "::test_identical_append_is_idempotent_but_ids_and_idempotency_keys_cannot_change_meaning"),
    "FOREIGN-PID": (
        "HELD",
        "src/conductor/command/adapters/process.py::ProcessRunner.stop",
        "tests/test_command_process_ownership.py"
        "::test_a_process_the_runner_did_not_start_is_never_touched"),
    "PORTAL-PREVIEW": (
        "HELD",
        "src/conductor/command/preview.py::render_dispatch_preview",
        "tests/test_sabotage_fixtures.py::test_portal_planter_trips_preview_route_gate"),
    "HARDLINK-PREVIEW": (
        "HELD",
        "src/conductor/command/containment.py::owned_file_violations",
        "tests/test_sabotage_fixtures.py"
        "::test_outward_hard_link_planter_trips_preview_route_gate"),
    "PORTAL-CONFIRM": (
        "HELD",
        "src/conductor/command/containment.py::run_route_violations",
        "tests/test_command_control_loop.py"
        "::test_integration_smoke_refuses_route_portal_before_spawn_and_leaves_sides_inert"),
    "HARDLINK-CONFIRM": (
        "HELD",
        "src/conductor/command/containment.py::owned_file_violations",
        "tests/test_command_control_loop.py"
        "::test_integration_smoke_refuses_hard_linked_journal_before_spawn_and_changes_no_alias"),
    "RECEIPT-TAMPER": (
        "HELD",
        "src/conductor/command/run_store.py::RunStore._validate_records",
        "tests/test_sabotage_fixtures.py"
        "::test_receipt_damage_fixture_trips_real_run_store_replay"),
    "RESTART": (
        "HELD",
        "src/conductor/command/runtime.py::ControlRuntime._replayed_attempt",
        "tests/test_command_runtime_restart.py"
        "::test_restart_after_lease_before_effect_records_unknown_without_execute"),
    "DISCONNECT": (
        "HELD",
        "src/conductor/command/coordinator.py::ExecutionCoordinator",
        "tests/test_server_async_execution.py"
        "::test_a_client_that_vanishes_mid_effect_neither_cancels_nor_repeats_it"),
    "VERIFY-FAIL": (
        "HELD",
        "src/conductor/command/runtime.py::ControlRuntime._verify",
        "tests/test_command_runtime_verify.py"
        "::test_a_verify_that_refutes_success_reaches_verification_failed"),
    "CSRF-ORIGIN": (
        "HELD",
        "src/conductor/command/http_transport.py::validate_command_mutation",
        "tests/test_command_http_transport.py"
        "::test_structured_csrf_fixtures_drive_the_real_transport"),
    "CHECKER-ONCE": (
        "HELD", "src/conductor/command/verify_road.py::verify_independently",
        "tests/test_command_independent_runtime.py"
        "::test_restart_with_no_checker_evidence_never_spends_a_second_grant"),
    "CHECKER-WRITES": (
        "HELD", "src/conductor/command/adapters/artifact_transport.py"
        "::ArtifactAwareTransport._check_owned",
        "tests/test_independent_checker_transport.py"
        "::test_checker_refusal_no_verdict_or_write_never_becomes_success"),
    "WORKTREE-CONTENT": (
        "HELD", "src/conductor/command/adapters/harness_workspace.py"
        "::HarnessWorkspace.read_work_tree",
        "tests/test_sabotage_fixtures.py"
        "::test_work_item_portal_fixture_is_not_opened_by_the_checker"),
}
EXPECTED_IDS = frozenset(EXPECTED_ROWS)

#: What the v2 snapshot said at its own base, which is what it must go on saying.
HISTORICAL_IDS = frozenset({
    "CONF-STALE", "CONF-DIGEST", "PATH-SCOPE", "PATH-CWD", "SHELL-INJECT",
    "TIMEOUT", "OUTPUT-BOMB", "DUPLICATE-IDEMPOTENCY", "FOREIGN-PID",
    "PORTAL-PREVIEW", "HARDLINK-PREVIEW", "PORTAL-CONFIRM", "HARDLINK-CONFIRM",
    "RECEIPT-TAMPER", "RESTART", "DISCONNECT", "VERIFY-FAIL", "CSRF-ORIGIN",
})
HISTORICAL_HELD = frozenset({
    "PATH-SCOPE", "PORTAL-PREVIEW", "HARDLINK-PREVIEW", "RECEIPT-TAMPER"})


def parse_records(text: str) -> dict[str, dict[str, str]]:
    """Read the delimited records out of a threat-matrix document.

    Only the fenced block is read, so the surrounding prose can explain the
    document without being mistaken for data. Anything a careless editor could
    leave behind that a lenient parser would silently drop -- a second fence, a
    repeated id, a repeated field, a line that is neither a field nor a
    continuation -- raises here instead, because a row this guard cannot read is
    a row it cannot vouch for.

    Args:
        text: The whole document.

    Returns:
        Threat id mapped to its field names and their raw values.
    """
    assert text.count(START_FENCE) == 1, "the start fence must appear exactly once"
    assert text.count(END_FENCE) == 1, "the end fence must appear exactly once"
    body = text.split(START_FENCE, 1)[1].split(END_FENCE, 1)[0]
    chunks = body.split("\n### ")
    assert chunks[0].strip() == "", f"prose sits inside the fences: {chunks[0]!r}"
    records: dict[str, dict[str, str]] = {}
    for chunk in chunks[1:]:
        heading, *lines = chunk.strip().splitlines()
        assert " — " in heading, f"a record heading needs an em dash: {heading!r}"
        threat_id, title = heading.split(" — ", 1)
        assert threat_id.strip() == threat_id and threat_id, f"bad id in {heading!r}"
        assert title.strip(), f"a record heading needs a title: {heading!r}"
        assert threat_id not in records, f"duplicate threat id {threat_id!r}"
        records[threat_id] = _parse_fields(threat_id, lines)
    return records


def _parse_fields(threat_id: str, lines: list[str]) -> dict[str, str]:
    """Read one record's ``- Name: value`` lines, wrapped values included."""
    fields: dict[str, str] = {}
    wrapped: str | None = None
    for line in lines:
        if line.startswith("- ") and ": " in line:
            name, value = line[2:].split(": ", 1)
            assert name not in fields, f"{threat_id}: repeated field {name!r}"
            fields[name] = value
            wrapped = None
        elif line.startswith("- ") and line.endswith(":"):
            wrapped = line[2:-1]
            assert wrapped not in fields, f"{threat_id}: repeated field {wrapped!r}"
            fields[wrapped] = ""
        elif wrapped is not None and line.startswith("  ") and line.strip():
            fields[wrapped] = (fields[wrapped] + " " + line.strip()).strip()
        elif not line.strip():
            wrapped = None
        else:
            raise AssertionError(f"{threat_id}: unreadable record line {line!r}")
    return fields


def _code_span(value: str) -> str | None:
    """Return the one code span a field holds, or None if it is not exactly one."""
    match = re.fullmatch(r"`([^`]+)`", value.strip())
    return match.group(1) if match is not None else None


def code_spans(value: str) -> tuple[str, ...]:
    """Return every code span in a comma-separated field, refusing loose prose.

    Args:
        value: The raw field text.

    Returns:
        The code spans in document order.
    """
    spans = tuple(re.findall(r"`([^`]+)`", value))
    assert spans, f"expected at least one code span, got {value!r}"
    outside = re.sub(r"`[^`]+`", "", value).replace(",", "").strip()
    assert outside == "", f"unquoted text beside the code spans: {value!r}"
    return spans


def defines(source: str, dotted: str) -> bool:
    """Answer whether one module's source defines a dotted definition path.

    The question is asked of the syntax tree, never of the text, so a name that
    only appears in a docstring, a comment or a string cannot answer for a
    definition that is not there.

    Args:
        source: The module's source text.
        dotted: A definition path such as ``ClassName.method_name``.

    Returns:
        True when every part resolves to a nested definition.
    """
    node: ast.AST = ast.parse(source)
    for part in dotted.split("."):
        found = next(
            (child for child in ast.iter_child_nodes(node)
             if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and child.name == part),
            None)
        if found is None:
            return False
        node = found
    return True


def release_problems(
        records: dict[str, dict[str, str]],
        corpus: dict[str, str]) -> tuple[str, ...]:
    """Judge parsed release rows against a corpus of module sources.

    Args:
        records: Rows as ``parse_records`` returns them.
        corpus: Module relative path mapped to that module's source text. A path
            absent from the corpus is a file that does not exist.

    Returns:
        One line per problem found, empty when every row holds.
    """
    problems: list[str] = []
    claimed: dict[str, str] = {}
    for threat_id, row in sorted(records.items()):
        missing = [name for name in RELEASE_FIELDS if name not in row]
        extra = sorted(set(row) - set(RELEASE_FIELDS))
        if missing or extra:
            problems.append(f"{threat_id}: fields missing {missing}, unexpected {extra}")
            continue
        status = _code_span(row["Status"])
        if status != "HELD":
            problems.append(
                f"{threat_id}: release status {status!r} is not HELD; a threat that is "
                "not held is a release blocker, not a row")
        if not row["Expected invariant"].strip():
            problems.append(f"{threat_id}: the expected invariant is empty")
        for label in ("Door", "Witness"):
            problems.extend(_reference_problems(threat_id, label, row[label], corpus, claimed))
    return tuple(problems)


def _reference_problems(
        threat_id: str, label: str, value: str,
        corpus: dict[str, str], claimed: dict[str, str]) -> list[str]:
    """Resolve one ``<path>::<symbol>`` field and record what it fails to be."""
    reference = _code_span(value)
    if reference is None or not _REFERENCE_RE.fullmatch(reference):
        return [f"{threat_id}: {label} {value!r} is not one `<path>::<symbol>` span"]
    relative, symbol = reference.split("::", 1)
    source = corpus.get(relative)
    if source is None:
        return [f"{threat_id}: {label} names {relative}, which is not a file"]
    if not defines(source, symbol):
        return [f"{threat_id}: {label} {symbol!r} is not defined in {relative}"]
    if label != "Witness":
        return []
    problems = []
    if not symbol.rpartition(".")[2].startswith("test_"):
        problems.append(
            f"{threat_id}: witness {symbol!r} is not a test; a defined function is "
            "not the same thing as a test that runs")
    owner = claimed.setdefault(reference, threat_id)
    if owner != threat_id:
        problems.append(f"{threat_id}: witness {reference} already stands for {owner}")
    return problems


def _corpus(records: dict[str, dict[str, str]]) -> dict[str, str]:
    """Read exactly the modules the matrix points at, and only those that exist."""
    sources: dict[str, str] = {}
    for row in records.values():
        for label in ("Door", "Witness"):
            reference = _code_span(row.get(label, ""))
            if reference is None or not _REFERENCE_RE.fullmatch(reference):
                continue
            relative = reference.split("::", 1)[0]
            if relative in sources:
                continue
            path = ROOT / relative
            if path.is_file():
                sources[relative] = path.read_text(encoding="utf-8")
    return sources


def _release_records() -> dict[str, dict[str, str]]:
    return parse_records(RELEASE_MATRIX.read_text(encoding="utf-8"))


def test_every_release_row_resolves_to_a_real_door_and_a_real_test():
    records = _release_records()
    assert set(records) == EXPECTED_IDS, set(records) ^ EXPECTED_IDS
    assert release_problems(records, _corpus(records)) == ()


def test_the_release_matrix_still_carries_the_doors_and_witnesses_signed_off():
    """Change-detect the triple, so moving a row is a decision and not a slip.

    The claim that a row holds is derived elsewhere in this module. This test
    only refuses a quiet substitution: swapping one real witness for another real
    witness resolves just as well and would otherwise pass unnoticed.
    """
    records = _release_records()
    actual = {
        threat_id: (
            _code_span(row["Status"]), _code_span(row["Door"]), _code_span(row["Witness"]))
        for threat_id, row in records.items()}
    assert actual == EXPECTED_ROWS


def test_every_matrix_fixture_in_both_documents_resolves_to_executable_support():
    used = set()
    for document in (RELEASE_MATRIX, HISTORICAL_MATRIX):
        for row in parse_records(document.read_text(encoding="utf-8")).values():
            for name in code_spans(row["Fixture"]):
                fixture = getattr(sf, name, None)
                assert callable(fixture), f"{document.name}: {name}"
                used.add(name)
    public = {name for name, value in vars(sf).items()
              if callable(value) and not name.startswith("_")}
    assert used <= public


def test_the_v2_matrix_stays_a_historical_snapshot_and_never_the_release_posture():
    """Hold the superseded document to its own base, and to naming its successor.

    Its rows were true of `63d261a` and are the only record of what was true
    then. Editing them to read like today would be a second, contradictory
    release posture wearing a 2026-08-13 date; leaving them unmarked would let a
    reader take the older file for the current one.
    """
    historical = HISTORICAL_MATRIX.read_text(encoding="utf-8")
    release = RELEASE_MATRIX.read_text(encoding="utf-8")
    assert HISTORICAL_MARKER in historical
    assert HISTORICAL_MARKER not in release
    assert RELEASE_MATRIX.name in historical, "the snapshot must name what superseded it"
    statuses = {threat_id: _code_span(row["Status"])
                for threat_id, row in parse_records(historical).items()}
    assert set(statuses) == HISTORICAL_IDS
    assert {name for name, held in statuses.items() if held == "HELD"} == HISTORICAL_HELD
    assert set(statuses.values()) == {"HELD", "PENDING"}


# --- calibration: the derivation run over synthetic text and synthetic sources ---

_SOUND_CORPUS = {
    "src/thing.py": "class Door:\n    def gate(self):\n        return True\n",
    "tests/test_thing.py": "def test_the_gate_refuses():\n    pass\n\ndef helper():\n    pass\n",
}


def _synthetic(*records: str) -> str:
    return f"prose\n\n{START_FENCE}\n\n" + "\n\n".join(records) + f"\n\n{END_FENCE}\n"


_SOUND_RECORD = (
    "### ONLY-ROW — a synthetic threat\n"
    "\n"
    "- Status: `HELD`\n"
    "- Door: `src/thing.py::Door.gate`\n"
    "- Fixture: `expired_confirmation`\n"
    "- Expected invariant: The gate refuses.\n"
    "- Witness: `tests/test_thing.py::test_the_gate_refuses`\n"
)


def test_the_derivation_passes_a_synthetic_row_whose_door_and_witness_both_exist():
    """Calibrate the harness before trusting any red it produces.

    Without this control, the inversions below could be red for a defect in the
    synthetic scaffolding rather than for the fault each one injects.
    """
    records = parse_records(_synthetic(_SOUND_RECORD))
    assert set(records) == {"ONLY-ROW"}
    assert release_problems(records, _SOUND_CORPUS) == ()


def test_the_derivation_reds_on_a_held_row_whose_witness_is_not_defined():
    absent = _SOUND_RECORD.replace(
        "::test_the_gate_refuses", "::test_the_gate_refuses_but_nobody_wrote_it")
    problems = release_problems(parse_records(_synthetic(absent)), _SOUND_CORPUS)
    assert len(problems) == 1
    assert "is not defined in tests/test_thing.py" in problems[0]

    gone = _SOUND_RECORD.replace("tests/test_thing.py", "tests/test_absent.py")
    missing_file = release_problems(parse_records(_synthetic(gone)), _SOUND_CORPUS)
    assert len(missing_file) == 1
    assert "which is not a file" in missing_file[0]


def test_the_derivation_reds_on_a_malformed_or_duplicated_row():
    duplicate_witness = _SOUND_RECORD.replace("ONLY-ROW", "SECOND-ROW")
    both = parse_records(_synthetic(_SOUND_RECORD, duplicate_witness))
    problems = release_problems(both, _SOUND_CORPUS)
    assert [line for line in problems if "already stands for ONLY-ROW" in line]

    dropped = _SOUND_RECORD.replace("- Door: `src/thing.py::Door.gate`\n", "")
    lost_field = release_problems(parse_records(_synthetic(dropped)), _SOUND_CORPUS)
    assert len(lost_field) == 1
    assert "fields missing ['Door']" in lost_field[0]

    unheld = _SOUND_RECORD.replace("- Status: `HELD`", "- Status: `PENDING`")
    still_pending = release_problems(parse_records(_synthetic(unheld)), _SOUND_CORPUS)
    assert len(still_pending) == 1
    assert "'PENDING' is not HELD" in still_pending[0]

    for broken, complaint in (
            (_SOUND_RECORD.replace("ONLY-ROW — ", "ONLY-ROW - "), "needs an em dash"),
            (_SOUND_RECORD + "loose prose\n", "unreadable record line"),
            (_SOUND_RECORD.replace("- Fixture:", "- Status:"), "repeated field 'Status'")):
        try:
            parse_records(_synthetic(broken))
        except AssertionError as refusal:
            assert complaint in str(refusal), refusal
        else:
            raise AssertionError(f"the parser accepted a record it cannot read: {complaint}")

    twice = _SOUND_RECORD + "\n" + _SOUND_RECORD
    try:
        parse_records(_synthetic(twice))
    except AssertionError as refusal:
        assert "duplicate threat id 'ONLY-ROW'" in str(refusal)
    else:
        raise AssertionError("the parser accepted one id twice")


def test_the_derivation_refuses_a_witness_that_is_merely_a_defined_function():
    """The over-correction control: resolving is necessary and is not sufficient.

    A guard that only asked whether the named symbol exists would accept a
    fixture builder, a helper, or a class as the thing that proves a threat is
    held. ``helper`` is genuinely defined in the synthetic corpus and must still
    be refused.
    """
    helper = _SOUND_RECORD.replace("::test_the_gate_refuses", "::helper")
    problems = release_problems(parse_records(_synthetic(helper)), _SOUND_CORPUS)
    assert len(problems) == 1
    assert "is not a test" in problems[0]

    a_class = _SOUND_RECORD.replace(
        "tests/test_thing.py::test_the_gate_refuses", "src/thing.py::Door")
    as_class = release_problems(parse_records(_synthetic(a_class)), _SOUND_CORPUS)
    assert len(as_class) == 1
    assert "is not a test" in as_class[0]
