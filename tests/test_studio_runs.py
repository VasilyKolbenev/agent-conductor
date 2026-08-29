"""The structural contract of the Studio's Runs, Decisions and Agents screens.

These two modules are pure DOM writers: they are handed a frozen state and a
bag of callbacks, they write text nodes, and they reach neither the network nor
the clock. Everything this module asserts is read off the SOURCE, which is the
house model for the fast suite -- rendered claims live in ``browser_tests/``.

The interesting half is the vocabulary equalities. Every closed word list these
screens spell is a copy of exactly one Python owner, and each test below
DERIVES the owner's answer rather than restating it: the decision effects come
from calling :func:`~conductor.command.contracts.gate_decision`, the
reason-required set comes from asking ``DecisionReceipt`` which actions refuse
an empty reason, and the record kinds come from the store's own table. A word
added on either side and not the other reds one of these.

Named ``test_studio_*`` on purpose. ``tests/test_panel_smoke.py`` machine-checks
that ``index.html``'s file-size waiver names, as a pattern, exactly the set of
``test_panel_*.py`` modules in the tree, so a new module under that prefix would
red a file this slice does not own.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conductor.command.adapters.provider import (
    AVAILABILITY_STATES,
    IMPLEMENTATION_STATES,
)
from conductor.command.attempts import ATTEMPT_PHASES
from conductor.command.contract_values import (
    _DECISION_ACTIONS,
    _RESULT_OUTCOMES,
    _RUN_STATES,
    _VERIFICATION_STATES,
    ContractError,
    ControlMode,
)
from conductor.command.contracts import DecisionReceipt, gate_decision
from conductor.command.graph_projection import GATE_STATES, NODE_PHASES
from conductor.command.operator_config import (
    _OPTIONAL_KEYS,
    _REQUIRED_KEYS,
    PROVIDER_CONFIG_FILENAME,
)
from conductor.command.providers import PROVIDER_CATALOG
from conductor.command.run_store import _RECORDS

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
RUNS_FILE = PANEL / "studio-runs.js"
PEOPLE_FILE = PANEL / "studio-people.js"
#: Both files this slice owns, and the only files it may write.
OWNED = (RUNS_FILE, PEOPLE_FILE)
#: The seven words a Studio screen container may stand in, from the frontend
#: contract. Both modules must say all seven and no eighth.
SCREEN_STATES = frozenset({
    "empty", "loading", "ready", "stale", "refused", "failed", "disconnected"})
#: The mount API slice D wires and cannot negotiate.
MOUNT_SIGNATURES = (
    (RUNS_FILE, "mountRuns"),
    (PEOPLE_FILE, "mountDecisions"),
    (PEOPLE_FILE, "mountAgents"),
)
#: Every callback name these screens invoke. They define none of them.
HANDLER_NAMES = {
    RUNS_FILE: {"selectRun", "refreshRuns", "showDecisions"},
    PEOPLE_FILE: {"selectDecision", "editDecision", "submitDecision",
                  "refreshAgents"},
}
#: How many controls in each file answer a missing handler by disabling
#: themselves. Pinned exactly rather than "at least one": presence alone let a
#: deleted disable through, because a sibling still carried the phrase.
DISABLED_CONTROLS = {RUNS_FILE: 2, PEOPLE_FILE: 5}
#: Nothing in a pure DOM writer may reach the network, the clock, storage, the
#: console, a parser of markup, or a dynamic module. Matched case-insensitively
#: against the whole source, comments included: a banned call written in a
#: comment is a banned call somebody will uncomment.
BANNED_APIS = (
    "innerhtml", "outerhtml", "insertadjacenthtml", "localstorage",
    "sessionstorage", "document.cookie", "console.", "eval(", "import(",
    "settimeout", "setinterval", "fetch(", "new eventsource",
    "xmlhttprequest", "websocket", "navigator.", "createelement",
)
#: The one module either file may import.
ALLOWED_IMPORT = "./command-view.js"
#: The tags a listener may be attached to. A click on a `div` is not operable
#: by a keyboard, and no amount of `tabindex` makes it a control.
LISTENABLE_TAGS = frozenset({"button", "form", "input"})
LINE_CAP = 800


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _balanced(text: str, start: int, opener: str, closer: str) -> str:
    """The substring from ``start`` to the matching close, exclusive."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    raise AssertionError(f"unbalanced {opener!r} from {start}")


def frozen_list(path: Path, name: str) -> list[str]:
    """The strings of ``export const NAME = Object.freeze([...])``."""
    text = source(path)
    marker = re.search(rf"const {name} = Object\.freeze\(\s*\[", text)
    assert marker is not None, f"{path.name} declares no list {name}"
    body = _balanced(text, marker.end() - 1, "[", "]")
    return re.findall(r'"([^"]*)"', body)


def frozen_keys(path: Path, name: str) -> list[str]:
    """The keys of ``const NAME = Object.freeze({...})``, in source order.

    The string values are removed before the keys are read, so a colon inside
    a sentence can never be counted as one -- and so a key written on the same
    line as its neighbour is found exactly as one written on its own.
    """
    text = source(path)
    marker = re.search(rf"const {name} = Object\.freeze\(\s*\{{", text)
    assert marker is not None, f"{path.name} declares no object {name}"
    body = _balanced(text, marker.end() - 1, "{", "}")
    bare = re.sub(r'"[^"]*"', '""', body)
    assert "{" not in bare, f"{name} is not a flat object"
    return re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", bare)


def frozen_arrays(path: Path, name: str) -> dict[str, list[str]]:
    """The array-valued entries of ``const NAME = Object.freeze({...})``."""
    text = source(path)
    marker = re.search(rf"const {name} = Object\.freeze\(\s*\{{", text)
    assert marker is not None, f"{path.name} declares no object {name}"
    body = _balanced(text, marker.end() - 1, "{", "}")
    return {key: re.findall(r'"([^"]*)"', values) for key, values
            in re.findall(r"([A-Za-z_][A-Za-z0-9_]*):\s*\[([^\]]*)\]", body)}


def frozen_pairs(path: Path, name: str) -> dict[str, str]:
    """The string-valued entries of ``const NAME = Object.freeze({...})``."""
    text = source(path)
    marker = re.search(rf"const {name} = Object\.freeze\(\s*\{{", text)
    assert marker is not None, f"{path.name} declares no object {name}"
    body = _balanced(text, marker.end() - 1, "{", "}")
    return dict(re.findall(r'([A-Za-z_][A-Za-z0-9_]*):\s*"([^"]*)"', body))


# -- the file itself ---------------------------------------------------------


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_each_studio_screen_module_sits_under_the_line_cap(path: Path) -> None:
    lines = source(path).splitlines()
    assert len(lines) <= LINE_CAP, f"{path.name} is {len(lines)} lines"


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_each_studio_screen_module_is_written_as_utf8_with_unix_endings(
        path: Path) -> None:
    """A BOM or a CR is a defect here, and both are silent in an editor."""
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} carries a BOM"
    assert b"\r" not in raw, f"{path.name} carries a carriage return"


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_neither_screen_module_reaches_a_banned_api(path: Path) -> None:
    text = source(path).casefold()
    found = sorted(name for name in BANNED_APIS if name in text)
    assert not found, f"{path.name} reaches {found}"


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_each_screen_module_imports_only_the_shared_dom_builder(
        path: Path) -> None:
    """These modules read state and write text; they own no transport."""
    imports = re.findall(r'^import .*? from "([^"]+)";', source(path),
                         flags=re.MULTILINE)
    assert imports == [ALLOWED_IMPORT], f"{path.name} imports {imports}"


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_no_screen_module_writes_a_second_dom_helper(path: Path) -> None:
    """`element` from command-view is the one builder; there is no other."""
    text = source(path)
    assert "document.createElement" not in text
    assert re.search(r"\bdocument\.(?!activeElement\b|body\b)", text) is None


# -- the mount API slice D wires ---------------------------------------------


@pytest.mark.parametrize(
    "path,name", MOUNT_SIGNATURES, ids=[name for _, name in MOUNT_SIGNATURES])
def test_each_mount_is_exported_with_the_frozen_signature(
        path: Path, name: str) -> None:
    signature = f"export function {name}(mount, state, handlers) {{"
    assert signature in source(path), f"{path.name} lacks {signature}"


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_every_exported_function_of_a_screen_module_is_one_of_its_mounts(
        path: Path) -> None:
    """No second entry point, and no default export to guess at."""
    exported = set(re.findall(r"export function (\w+)\(", source(path)))
    expected = {name for owner, name in MOUNT_SIGNATURES if owner == path}
    assert exported == expected
    assert "export default" not in source(path)


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_a_mount_replaces_its_whole_subtree_exactly_once(path: Path) -> None:
    """Idempotent re-render: the subtree is replaced, never appended to."""
    text = source(path)
    mounts = {name for owner, name in MOUNT_SIGNATURES if owner == path}
    assert text.count("mount.replaceChildren(") == len(mounts)


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_a_mount_captures_focus_before_the_pass_and_restores_it_after(
        path: Path) -> None:
    """A keyboard Human is never dropped to the top by their own re-render.

    The two calls are counted line-anchored at the mount body's own indent, so
    a call commented out still reds this: `// restoreFocus(mount, key);`
    contains the call and executes none of it.
    """
    text = source(path)
    mounts = {name for owner, name in MOUNT_SIGNATURES if owner == path}
    captured = re.findall(r"(?m)^  const key = focusKey\(mount\);$", text)
    restored = re.findall(r"(?m)^  restoreFocus\(mount, key\);$", text)
    assert len(captured) == len(mounts), captured
    assert len(restored) == len(mounts), restored
    assert 'querySelector(`[data-focus-key="${key}"]`)' in text


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_a_screen_module_invokes_only_the_callbacks_it_declares(
        path: Path) -> None:
    """The handler names are the wire to slice D, and they are exact."""
    text = source(path)
    named = set(re.findall(r'handlerOf\(handlers, "(\w+)"\)', text))
    named |= set(re.findall(r'actionButton\(handlers, "(\w+)"', text))
    assert named == HANDLER_NAMES[path]


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_a_control_whose_handler_is_missing_is_disabled_and_says_so(
        path: Path) -> None:
    """A vanished control teaches the wrong lesson; a disabled one teaches
    the right one.

    Two-sided, because presence alone was not a gate: every callback this file
    looks up is tested for absence, and the number of controls that answer that
    absence by disabling themselves is pinned exactly. Deleting one reds this,
    and adding a control without one reds it too -- the count is re-pinned
    deliberately or not at all.
    """
    text = source(path)
    looked_up = re.findall(r"const (\w+) = handlerOf\(handlers,", text)
    assert looked_up, f"{path.name} looks up no handler"
    for name in sorted(set(looked_up)):
        assert f"{name} === null" in text, f"{path.name}: {name} is never tested"
    # A lookup coalesced to a fallback -- `handlerOf(...) || (() => {})` -- is
    # the defect wearing the guard's clothes: the null test below it can never
    # be true again, so the control silently does nothing instead of saying it
    # cannot act. No lookup may carry a default.
    for line in text.splitlines():
        if "handlerOf(handlers" in line:
            assert "||" not in line and "??" not in line, line
    assert text.count(".disabled = ") == DISABLED_CONTROLS[path]
    assert "This screen was mounted without a ${name} handler." in text


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_every_listener_is_attached_to_a_real_form_control(path: Path) -> None:
    """Keyboard operability by construction: a click on a `div` cannot happen
    because nothing in these files ever builds one to listen on."""
    text = source(path)
    receivers = set(re.findall(r"(\w+)\.addEventListener\(", text))
    assert receivers, f"{path.name} attaches no listener at all"
    for receiver in sorted(receivers):
        built = set(re.findall(
            rf'const {receiver} = element\(\s*"(\w+)"', text))
        assert built, f"{path.name}: {receiver} is not built by element()"
        assert built <= LISTENABLE_TAGS, f"{path.name}: {receiver} is {built}"


# -- the closed vocabularies, each derived from its Python owner --------------


def test_the_runs_screen_spells_the_projections_node_phases() -> None:
    assert frozen_list(RUNS_FILE, "NODE_PHASES") == list(NODE_PHASES)


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_both_screens_spell_the_projections_gate_states(path: Path) -> None:
    assert sorted(frozen_list(path, "GATE_STATES")) == sorted(GATE_STATES)


def test_the_runs_screen_spells_the_contracts_result_outcomes() -> None:
    assert frozen_list(RUNS_FILE, "RESULT_OUTCOMES") == sorted(_RESULT_OUTCOMES)


def test_the_runs_screen_spells_the_contracts_verification_states() -> None:
    assert frozen_list(RUNS_FILE, "VERIFICATION_STATES") == sorted(
        _VERIFICATION_STATES)


def test_the_runs_screen_spells_the_contracts_run_states() -> None:
    assert frozen_list(RUNS_FILE, "RUN_STATES") == sorted(_RUN_STATES)


def test_the_runs_screen_spells_both_durable_attempt_phases() -> None:
    assert frozen_list(RUNS_FILE, "ATTEMPT_PHASES") == sorted(ATTEMPT_PHASES)


def test_the_runs_screen_names_every_record_kind_the_store_can_hold() -> None:
    """The timeline renders the journal, so it must know every kind of it."""
    assert frozen_keys(RUNS_FILE, "RECORD_KINDS") == sorted(_RECORDS)


@pytest.mark.parametrize("name", ["INSTANT_FIELDS", "ROW_FACTS"])
def test_every_timeline_table_is_keyed_by_real_record_kinds(name: str) -> None:
    assert frozen_keys(RUNS_FILE, name) == sorted(_RECORDS)


def test_every_field_a_timeline_row_shows_is_one_the_record_really_has() -> None:
    """A misspelled field renders nothing and looks like an empty record. The
    names are held against each contract's own exact field set."""
    facts = frozen_arrays(RUNS_FILE, "ROW_FACTS")
    assert set(facts) == set(_RECORDS)
    for kind, names in sorted(facts.items()):
        contract, _ = _RECORDS[kind]
        unknown = sorted(set(names) - set(contract._FIELDS))
        assert not unknown, f"{kind} has no field {unknown}"
        assert names, f"{kind} shows no field at all"


def test_every_instant_a_timeline_row_stamps_is_the_records_own() -> None:
    stamps = frozen_pairs(RUNS_FILE, "INSTANT_FIELDS")
    assert set(stamps) == set(_RECORDS)
    for kind, stamp in sorted(stamps.items()):
        contract, _ = _RECORDS[kind]
        assert stamp in contract._FIELDS, f"{kind} has no field {stamp!r}"


def test_the_runs_screen_spells_the_whole_authority_ladder_in_order() -> None:
    """A mode a run can hold and this screen cannot describe is a silent gap,
    and the ladder's own order is the enum's declaration order."""
    assert frozen_keys(RUNS_FILE, "CONTROL_MODES") == [
        mode.value for mode in ControlMode]


def test_the_five_progression_steps_are_records_and_attempt_phases() -> None:
    """The progression is not a story this screen tells: three of its five
    names are record kinds and two are the attempt event's own phases."""
    steps = frozen_list(RUNS_FILE, "TIMELINE_STEPS")
    assert steps == ["action_proposal", "action_request", "effect_lease",
                     "execution_observed", "action_result"]
    assert {steps[0], steps[1], steps[4]} <= set(_RECORDS)
    assert {steps[2], steps[3]} == set(ATTEMPT_PHASES)


def _effect_of(action: str) -> str:
    """What the ONE decision function says this answer causes."""
    receipt = DecisionReceipt(
        receipt_id="receipt-1", run_id="run-1", gate_id="gate-1",
        action=action, actor="operator", decided_at="2026-01-01T00:00:00Z",
        reason="stated", scope_refs=(), config_digest="sha256:" + "0" * 64)
    return gate_decision([receipt], "run-1", "gate-1")


def _reason_is_required(action: str) -> bool:
    """Whether the receipt contract refuses this answer with a blank reason."""
    try:
        DecisionReceipt(
            receipt_id="receipt-1", run_id="run-1", gate_id="gate-1",
            action=action, actor="operator", decided_at="2026-01-01T00:00:00Z",
            reason="", scope_refs=(), config_digest="sha256:" + "0" * 64)
    except ContractError:
        return True
    return False


def test_every_choice_the_decisions_screen_offers_causes_what_it_claims() -> None:
    """Derived by asking `gate_decision`, never by copying its table."""
    offered = frozen_pairs(PEOPLE_FILE, "DECISION_ACTIONS")
    assert offered == {action: _effect_of(action) for action in offered}
    assert set(offered) == {row for row in offered}
    for action in offered:
        assert _effect_of(action) in GATE_STATES


def test_the_decisions_screen_offers_every_answer_the_contract_admits() -> None:
    """A fifth answer added to the contract must reach the screen, and an
    answer removed must leave it."""
    offered = set(frozen_pairs(PEOPLE_FILE, "DECISION_ACTIONS"))
    assert offered == set(_DECISION_ACTIONS)


def test_the_two_answers_that_need_a_reason_are_the_contracts_own() -> None:
    offered = sorted(frozen_pairs(PEOPLE_FILE, "DECISION_ACTIONS"))
    required = sorted(frozen_list(PEOPLE_FILE, "REASON_REQUIRED"))
    assert required == sorted(a for a in offered if _reason_is_required(a))


def test_every_offered_answer_is_explained_in_the_users_own_words() -> None:
    offered = sorted(frozen_pairs(PEOPLE_FILE, "DECISION_ACTIONS"))
    assert sorted(frozen_keys(PEOPLE_FILE, "DECISION_MEANINGS")) == offered


def test_the_agents_screen_spells_the_machines_availability_states() -> None:
    assert frozen_list(PEOPLE_FILE, "AVAILABILITY_STATES") == sorted(
        AVAILABILITY_STATES)
    assert sorted(frozen_keys(PEOPLE_FILE, "AVAILABILITY_MEANINGS")) == sorted(
        AVAILABILITY_STATES)


def test_the_agents_screen_spells_the_builds_implementation_states() -> None:
    assert frozen_list(PEOPLE_FILE, "IMPLEMENTATION_STATES") == sorted(
        IMPLEMENTATION_STATES)
    assert sorted(
        frozen_keys(PEOPLE_FILE, "IMPLEMENTATION_MEANINGS")) == sorted(
        IMPLEMENTATION_STATES)


def test_the_machine_and_the_build_never_share_a_word() -> None:
    """Two questions, two vocabularies. A shared value would let a reader take
    one answer for the other."""
    assert not set(AVAILABILITY_STATES) & set(IMPLEMENTATION_STATES)
    assert not (set(frozen_list(PEOPLE_FILE, "AVAILABILITY_STATES"))
                & set(frozen_list(PEOPLE_FILE, "IMPLEMENTATION_STATES")))


def test_the_no_participant_state_names_the_real_file_keys_and_command() -> None:
    """"No participant" is actionable only if the next action is spelled."""
    text = source(PEOPLE_FILE)
    assert f'PROVIDER_CONFIG_FILE = "conductor/{PROVIDER_CONFIG_FILENAME}"' in text
    assert frozen_list(PEOPLE_FILE, "PROVIDER_CONFIG_REQUIRED") == sorted(
        _REQUIRED_KEYS)
    assert frozen_list(PEOPLE_FILE, "PROVIDER_CONFIG_OPTIONAL") == sorted(
        _OPTIONAL_KEYS)
    assert 'PROVIDER_CONFIG_COMMAND = "conduct up"' in text
    assert "noProviders" in text
    # The setup command is named BEFORE the file, because the file is what the
    # command writes rather than what a person has to compose. A panel that
    # listed the keys first would still be teaching the schema. Read out of the
    # panel's own body rather than the whole module, so the export line above
    # cannot satisfy the ordering on its own.
    assert 'PROVIDER_SETUP_COMMAND = "conduct providers"' in text
    body = text[text.index("function noProviders("):]
    body = body[:body.index("\n}")]
    assert body.index("PROVIDER_SETUP_COMMAND") < body.index(
        "PROVIDER_CONFIG_FILE"), (
        "the empty roster names the file before the command that writes it")


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_each_screen_says_all_seven_states_and_no_eighth(path: Path) -> None:
    assert set(frozen_keys(path, "PHASE_SENTENCES")) == SCREEN_STATES


# -- the honesty rules the backend is built on -------------------------------


def test_the_creation_time_word_is_never_rendered_as_a_live_position() -> None:
    """`envelope_status` says what a run was OPENED as. The screen says that."""
    text = source(RUNS_FILE)
    assert "Opened as" in text
    assert "current status" not in text.casefold()
    assert "immutable, so it never reports where the run now stands" in text


def test_an_unreadable_run_is_drawn_with_what_the_operator_can_do() -> None:
    """A run you cannot see is worse than one you cannot read.

    The marker must be REACHED, not merely written: a declared renderer nothing
    calls is a screen that shows the unreadable run as empty.
    """
    text = source(RUNS_FILE)
    assert text.count("unreadableDetail(") == 2, "declared once, called once"
    assert ("  if (row !== null && row.unreadable === true) "
            "return unreadableDetail(row);") in text
    assert "conductor/runs/${show(row.run_id)}/" in text
    assert "What you can do:" in text


def test_verification_failed_never_appears_without_its_explanation() -> None:
    """Exit 0 proves the process finished, not that the work was verified."""
    note = re.search(
        r'VERIFICATION_FAILED_NOTE = "(.+?)";', source(RUNS_FILE), re.DOTALL)
    assert note is not None
    words = note.group(1).replace('"\n  + "', "")
    assert "exit 0" in words
    assert "not that the work was verified" in words
    text = source(RUNS_FILE)
    # Every place the word is TESTED for is a place the sentence is written.
    compared = len(re.findall(r'=== "verification_failed"', text))
    explained = text.count("note(VERIFICATION_FAILED_NOTE)")
    assert compared >= 3, compared
    assert explained == compared, (compared, explained)


def test_a_loop_reads_its_position_and_its_ceiling_from_two_documents() -> None:
    """`pass` is the runtime's; `bound` is the definition's. "pass N of B" may
    never be computed from one of them alone."""
    text = source(RUNS_FILE)
    assert "`pass ${runtime.pass} of ${loop.bound}`" in text
    assert "runtime.bound_reached === true" in text
    assert re.search(r"loop\.bound\s*[-+*/]", text) is None
    assert re.search(r"runtime\.pass\s*[-+*/]", text) is None


def test_a_record_kind_this_build_does_not_know_is_named_not_dropped() -> None:
    text = source(RUNS_FILE)
    assert "This build does not know this record kind." in text
    assert "shown by the name the journal gave it" in text
    # Every wrapper becomes a row; nothing filters the list by kind first.
    assert "records.forEach((wrapper, index) => list.append(" in text


def test_the_timeline_never_decides_that_a_step_is_missing() -> None:
    """`stepOf` names a step a record carries, or nothing. There is no third
    answer and no absent-step branch to invent one."""
    text = source(RUNS_FILE)
    assert "function stepOf(kind, record) {" in text
    body = text[text.index("function stepOf(kind, record) {"):]
    body = body[:body.index("\n}\n")]
    assert body.count("return") == 2
    assert "null" in body


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_no_screen_branches_on_a_provider_name(path: Path) -> None:
    """Capability comes from the payload, never from an id."""
    text = source(path).casefold()
    named = sorted(row for row in PROVIDER_CATALOG if row.casefold() in text)
    assert not named, f"{path.name} names {named}"


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_no_state_is_carried_by_colour_alone(path: Path) -> None:
    """Every chip draws a glyph and a word. A channel with no glyph could
    reach the screen as colour and nothing else."""
    text = source(path)
    glyphs = set(frozen_keys(path, "CHANNEL_GLYPHS"))
    assert glyphs == {"pass", "wait", "fail", "none"}
    used = set(re.findall(r'chip\("(\w+)"', text))
    assert used <= glyphs, f"{path.name} draws {sorted(used - glyphs)}"
    for name in re.findall(r"const (\w+_CHANNEL) = Object\.freeze", text):
        values = set(frozen_pairs(path, name).values())
        assert values <= glyphs, f"{path.name}: {name} maps to {values}"


def test_a_field_with_no_durable_home_is_marked_on_screen() -> None:
    """Not blank, not guessed, and never quietly absent.

    Counted as CALL SITES, never as mentions. This guard used to run over both
    owned files and assert `text.count("unsupported(") >= 2`; when the Runs
    screen's last unsupported field became a real one, lowering that to `>= 1`
    left it passing on the FUNCTION DEFINITION alone -- a guard green over a
    helper nobody called. The definition is excluded here, so a file that
    declares the helper and uses it nowhere reds instead of reassuring.

    The relation is per-file and two-directional: a file that calls it must
    carry the marker text, and a file that calls it nowhere must not carry the
    helper at all, because an unreachable renderer is dead code that reads like
    a promise.
    """
    for path in OWNED:
        text = source(path)
        calls = len(re.findall(r"(?<!function )unsupported\(", text))
        if calls:
            assert 'text: "not recorded by this build"' in text, path.name
        else:
            assert "unsupported" not in text, (
                f"{path.name} declares an unsupported renderer it never calls")
    # And at least one owned screen still has such a field, so this whole guard
    # cannot pass by every marker quietly disappearing.
    assert any(re.search(r"(?<!function )unsupported\(", source(path))
               for path in OWNED)


def test_the_runs_screen_reports_the_revision_the_run_froze() -> None:
    """The positive witness that replaced a marker for something unknowable.

    This screen used to carry `unsupported("Workflow revision", ...)` because a
    materialized plan records no template identity and the run recorded none
    either -- so the honest answer was that no revision could be shown. The run
    now freezes the reference into the configuration `config_digest` is taken
    over, so the screen reads it instead of marking it.

    Asserted here as SOURCE structure, and end to end in
    `tests/test_command_run_identity.py` and the browser gate. What this holds
    is that the screen reads the frozen configuration and never the plan: a
    revision taken off a graph would be a guess wearing a number.
    """
    text = source(RUNS_FILE)
    assert 'unsupported("Workflow revision",' not in text
    assert 'fact("Revision", followed === null' in text
    assert "detail.config" in text
    # Both halves refuse together, so no reader can find one and infer the other.
    assert 'fact("Workflow", followed === null' in text


def test_the_agents_screen_marks_the_roles_a_plan_does_not_carry() -> None:
    text = source(PEOPLE_FILE)
    assert 'unsupported("Roles it carries",' in text
    assert "names instances, not roles" in text


def test_a_provider_row_and_an_instance_row_answer_different_questions() -> None:
    """The two arrays are joined by identity and never merged into one."""
    text = source(PEOPLE_FILE)
    assert "a consumer joins them by identity, never by a displayed label" in text
    assert "roster.get(providerId)" in text
    assert "providerSection" in text and "participantSection" in text
