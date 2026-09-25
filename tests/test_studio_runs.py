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
from tests.studio_source_messages import rendered_source

from conductor.command.adapters.provider import (
    AVAILABILITY_STATES,
    CONTRACT_AUTH_STATES,
    IMPLEMENTATION_STATES,
)
from conductor.command.contract_values import _DECISION_ACTIONS, ContractError
from conductor.command.contracts import DecisionReceipt, gate_decision
from conductor.command.graph_projection import GATE_STATES
from conductor.command.operator_config import (
    _OPTIONAL_KEYS,
    _REQUIRED_KEYS,
    PROVIDER_CONFIG_FILENAME,
)
from conductor.command.providers import PROVIDER_CATALOG

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
RUNS_FILE = PANEL / "studio-runs.js"
#: The closed vocabularies this screen is held to moved next door when
#: `studio-runs.js` crossed the line cap. The parity guards below read THAT
#: file against their Python owners; everything about how the screen
#: RENDERS is still read from the screen itself. Two files, one screen, and
#: the split is invisible to every other reader because `studio-runs.js`
#: re-exports every name.
WORDS_FILE = PANEL / "studio-runwords.js"
PEOPLE_FILE = PANEL / "studio-people.js"
#: The two controls that WRITE, split off the Runs screen when the propose and
#: confirm road arrived and `studio-runs.js` had no room for it. It is a screen
#: FRAGMENT rather than a screen: it mounts nothing, owns no container and
#: carries no state vocabulary of its own, so the guards below that are about
#: a MOUNT read `MOUNTED` and the guards that are about a file read `OWNED`.
STEP_FILE = PANEL / "studio-runstep.js"
#: The other write on the Runs screen, a document into the run; a fragment too.
DOCS_FILE = PANEL / "studio-rundocs.js"
#: Every file this slice owns, and the only files it may write.
OWNED = (RUNS_FILE, STEP_FILE, PEOPLE_FILE, DOCS_FILE)
#: The two of them that own a screen container: one mount, one focus pass, one
#: set of state words each.
MOUNTED = (RUNS_FILE, PEOPLE_FILE)
#: Where each screen's closed words are DECLARED. Only the Runs screen's
#: moved, so this is a lookup rather than a rule: a guard that asked the
#: rendering file for a vocabulary would red for the wrong reason, and one
#: that asked the words file about rendering would pass for the wrong one.
WORDS_OF = {RUNS_FILE: PANEL / "studio-runwords.js",
            PEOPLE_FILE: PEOPLE_FILE}
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
#: Every callback name these files invoke. They define none of them. The Runs
#: screen's four step callbacks are NOT on its row: it hands `handlers` through
#: to the step control and looks none of them up, which is exactly what keeps
#: the offer rule and the write in one file.
HANDLER_NAMES = {
    RUNS_FILE: {"selectRun", "refreshRuns", "showDecisions"},
    STEP_FILE: {"chooseStep", "editStep", "proposeStep", "confirmStep"},
    PEOPLE_FILE: {"selectDecision", "editDecision", "submitDecision",
                  "refreshAgents"},
    DOCS_FILE: {"editDocument", "publishDocument"},
}
#: How many controls in each file answer a missing handler by disabling
#: themselves. Pinned exactly rather than "at least one": presence alone let a
#: deleted disable through, because a sibling still carried the phrase.
DISABLED_CONTROLS = {RUNS_FILE: 2, STEP_FILE: 2, PEOPLE_FILE: 5, DOCS_FILE: 4}
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
#: What each of these files may import, as a permission table. It used to be
#: one name for both -- `command-view.js`, the shared DOM builder -- and the
#: guard below only ever saw single-line imports, so the words module
#: `studio-runs.js` already read from went unnoticed because its import spans
#: lines. The guard now reads BOTH shapes, and the table is PER FILE because
#: the three rows are no longer one permission: the Runs screen may reach the
#: step control it draws, the step control may reach the canonical-text
#: function it shows a plan's arguments with, and the Decisions screen may
#: reach neither. None may reach a transport, a model, or another screen, and
#: nothing may import `studio-runs.js`: it imports the step control, so a
#: permission the other way is what would close the pair into a ring.
ALLOWED_IMPORTS = {
    RUNS_FILE: frozenset({"./studio-i18n.js", "./command-view.js", "./studio-runwords.js", "./command-projection.js",
                          "./studio-participants.js", "./studio-runhead.js",
                          "./studio-runread.js", "./studio-runstep.js",
                          "./studio-rundocs.js"}),
    STEP_FILE: frozenset({"./studio-i18n.js", "./command-view.js", "./command-projection.js",
                          "./studio-runwords.js", "./studio-runread.js",
                          "./studio-rundocs.js", "./studio-isolation.js"}),
    PEOPLE_FILE: frozenset({"./studio-i18n.js", "./command-view.js", "./studio-runwords.js",
                            "./studio-quotas.js"}),
    DOCS_FILE: frozenset({"./studio-i18n.js", "./command-view.js", "./command-projection.js",
                          "./studio-runwords.js", "./studio-runread.js"}),
}
#: The tags a listener may be attached to. A click on a `div` is not operable
#: by a keyboard, and no amount of `tabindex` makes it a control.
LISTENABLE_TAGS = frozenset({"button", "form", "input", "select", "textarea"})
LINE_CAP = 800


def source(path: Path) -> str:
    return rendered_source(path.read_text(encoding="utf-8"))


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
    """These modules read state and write text; they own no transport.

    Both import SHAPES are read. The pattern used to stop at a newline, so a
    multi-line import list was invisible to it -- and `studio-runs.js` has read
    its vocabularies out of `studio-runwords.js` through exactly such a list
    the whole time. A guard that cannot see half the imports is not a guard on
    imports, so the match spans lines and the permitted set says what may be
    there.
    """
    permitted = ALLOWED_IMPORTS[path]
    imports = set(re.findall(r'^import\s[\s\S]*?from "([^"]+)";', source(path),
                             flags=re.MULTILINE))
    assert imports, f"{path.name} imports nothing at all"
    assert imports <= permitted, (
        f"{path.name} imports {sorted(imports - permitted)}")
    # And nothing here may import the screen that draws it: the Runs screen
    # imports the step control, so the reverse edge is a cycle.
    assert "./studio-runs.js" not in imports, path.name


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


@pytest.mark.parametrize("path", MOUNTED, ids=lambda path: path.name)
def test_every_exported_function_of_a_screen_module_is_one_of_its_mounts(
        path: Path) -> None:
    """No second entry point, and no default export to guess at."""
    exported = set(re.findall(r"export function (\w+)\(", source(path)))
    expected = {name for owner, name in MOUNT_SIGNATURES if owner == path}
    assert exported == expected
    assert "export default" not in source(path)


def test_the_step_control_exports_one_builder_and_mounts_nothing() -> None:
    """The fragment's own shape, which is not a mount's.

    It is handed a row's facts and answers with nodes; the screen next door
    owns the container and the focus pass. So the guards above read `MOUNTED`
    and this reads the one file they cannot: exactly one exported FUNCTION,
    no default, no container of its own, and no chip -- a channel drawn here
    would be a state carried by colour outside the module whose glyph table
    the colour guard reads.
    """
    text = source(STEP_FILE)
    # One builder. `offeredControl` is the row's decision -- which form it draws -- exported so the
    # Runs header asks the row instead of keeping a second copy of the rule; it answers a word and
    # builds nothing.
    assert set(re.findall(r"export function (\w+)\(", text)) == {"stepControls", "offeredControl"}
    decision = text[text.index("export function offeredControl("):]
    decision = decision[:decision.index("\n}\n")]
    assert "element(" not in decision and "note(" not in decision and "Form(" not in decision
    assert "export default" not in text
    assert "mount.replaceChildren(" not in text
    assert "focusKey(" not in text and "restoreFocus(" not in text
    assert "chip(" not in text
    assert ("export function stepControls(node, runtime, standing, detail, "
            "state, handlers) {") in text


@pytest.mark.parametrize("path", MOUNTED, ids=lambda path: path.name)
def test_a_mount_replaces_its_whole_subtree_exactly_once(path: Path) -> None:
    """Idempotent re-render: the subtree is replaced, never appended to."""
    text = source(path)
    mounts = {name for owner, name in MOUNT_SIGNATURES if owner == path}
    assert text.count("mount.replaceChildren(") == len(mounts)


@pytest.mark.parametrize("path", MOUNTED, ids=lambda path: path.name)
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
    # The Runs screen draws one `field:proposed_by` per runnable step, so it
    # restores WITHIN the form focus stood in; the Decisions screen draws
    # one form and restores by key alone.
    assert FOCUS_SELECTOR[path] in text, path.name


#: How each mount finds the control drawn in a focused one's place.
FOCUS_SELECTOR = {
    RUNS_FILE: '`${within}[data-focus-key="${key.key}"]`',
    PEOPLE_FILE: 'querySelector(`[data-focus-key="${key}"]`)',
}


@pytest.mark.parametrize("path", OWNED, ids=lambda path: path.name)
def test_a_screen_module_invokes_only_the_callbacks_it_declares(
        path: Path) -> None:
    """The handler names are the wire to slice D, and they are exact."""
    text = source(path)
    named = set(re.findall(r'handlerOf\(handlers, "(\w+)"\)', text))
    # The Runs screen's button takes the state first, for the sentence it
    # says when its wire is missing; the people screens' takes it last.
    named |= set(re.findall(r'actionButton\((?:state, )?handlers, "(\w+)"', text))
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
    # The sentence is what the reached call renders, with the handler's name
    # spliced in -- in all four files, whichever catalogue row each reaches.
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


# -- the closed vocabularies -------------------------------------------------
#
# Each derived from its Python owner, in `tests/test_studio_runwords.py` since
# this module reached the line cap; the readers above are what it spends.


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


def test_the_agents_screen_spells_the_login_a_row_pinned() -> None:
    assert frozen_list(PEOPLE_FILE, "AUTH_STATES") == sorted(CONTRACT_AUTH_STATES)
    assert sorted(frozen_keys(PEOPLE_FILE, "AUTH_MEANINGS")) == sorted(
        CONTRACT_AUTH_STATES)
    assert frozen_list(PANEL / "studio-model.js", "PROVIDER_AUTH") == sorted(
        CONTRACT_AUTH_STATES)


def test_the_machine_the_build_and_the_login_never_share_a_word() -> None:
    """Three questions, three vocabularies. A shared value would let a reader
    take one answer for another."""
    assert not set(AVAILABILITY_STATES) & set(IMPLEMENTATION_STATES)
    assert not set(CONTRACT_AUTH_STATES) & set(AVAILABILITY_STATES)
    assert not set(CONTRACT_AUTH_STATES) & set(IMPLEMENTATION_STATES)
    assert not (set(frozen_list(PEOPLE_FILE, "AVAILABILITY_STATES"))
                & set(frozen_list(PEOPLE_FILE, "IMPLEMENTATION_STATES")))
    assert not (set(frozen_list(PEOPLE_FILE, "AUTH_STATES"))
                & set(frozen_list(PEOPLE_FILE, "AVAILABILITY_STATES")))


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


@pytest.mark.parametrize("path", MOUNTED, ids=lambda path: path.name)
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
            "return unreadableDetail(state, row);") in text
    assert "conductor/runs/${show(state, row.run_id)}/" in text
    assert "What you can do:" in text


def test_verification_failed_never_appears_without_its_explanation() -> None:
    """Exit 0 proves the process finished, not that the work was verified.

    This used to be held by COUNTING: every comparison against the word had to
    be matched by a sentence written beside it. Five containers each spelled the
    rule out, and when the schedule brought a SIXTH container into the run
    detail it was written without either half -- so the count still balanced
    and this stayed green while the screen showed the word bare. The browser
    sweep in `test_studio_run_journal` caught it; this did not.

    The shape changed in response, and what is held now cannot have that hole:
    there is exactly ONE place the word is compared, that place is also the only
    place the sentence is written, and every container that can show an outcome
    spends it. A new container cannot forget the rule without failing to call
    the only thing that renders the outcome's explanation at all.
    """
    # The SENTENCE is reached through the catalogue now, and the one-voice
    # emitter that spends it is unchanged. What is read is what the emitter
    # RENDERS, so the rule -- one comparison, one writer, one emitter, spent
    # by every container -- is held on the reached call rather than on a
    # constant nothing draws.
    text = source(RUNS_FILE)
    emitter = re.search(r"function alsoSay\(state, outcome\) \{(.*?)\n\}",
                        text, re.DOTALL)
    assert emitter, "the one-voice emitter is gone"
    said = re.search(r'\? \[note\("(.+?)"\)\] : \[\];', emitter.group(1))
    assert said, emitter.group(1)
    assert "exit 0" in said.group(1)
    assert "not that the work was verified" in said.group(1)
    # One comparison, one writer, and they are the same function.
    assert len(re.findall(r'=== "verification_failed"', text)) == 1, text
    assert '=== "verification_failed"' in emitter.group(1)
    assert text.count(said.group(1)) == 1
    # One sentence, one owner: the words module's constant and every catalogue copy are the same words.
    from tests.test_studio_routing_labels import _js_constant
    owner = _js_constant(PANEL / "studio-runwords.js", "VERIFICATION_FAILED_NOTE")
    assert said.group(1) == owner
    # And it is SPENT by every container that can show an outcome word: the run
    # row, the plan section, the position row, the outcome section and the
    # timeline row, and now an artifact's source outcome. A declaration with
    # missing consumers is the same defect, so the call sites are counted too.
    assert text.count("alsoSay(") == 7, text.count("alsoSay(")


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


@pytest.mark.parametrize("path", MOUNTED, ids=lambda path: path.name)
def test_no_state_is_carried_by_colour_alone(path: Path) -> None:
    """Every chip draws a glyph and a word. A channel with no glyph could
    reach the screen as colour and nothing else."""
    # The chips are drawn HERE and the channels are declared THERE, which
    # for one screen is now two files. Both halves are still asked, so a
    # channel that mapped to no glyph would still be caught wherever the
    # table lives.
    text, words = source(path), source(WORDS_OF[path])
    glyphs = set(frozen_keys(WORDS_OF[path], "CHANNEL_GLYPHS"))
    assert glyphs == {"pass", "wait", "fail", "none"}
    used = set(re.findall(r'chip\("(\w+)"', text))
    assert used <= glyphs, f"{path.name} draws {sorted(used - glyphs)}"
    for name in re.findall(r"const (\w+_CHANNEL) = Object\.freeze", words):
        values = set(frozen_pairs(WORDS_OF[path], name).values())
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
    # What this used to end with, and why it could not stay: "at least one
    # owned screen still has such a field, so this guard cannot pass by every
    # marker quietly disappearing". That was the right instinct while there
    # WERE such fields -- it is what stopped the census being satisfied by
    # deleting rows instead of building them. It became a rule that a lie must
    # survive somewhere, and the last one on these two screens is now true.
    #
    # So the floor moved rather than being removed. What must not vanish is not
    # a marker but a STATEMENT: the one row on these screens that still says a
    # fact is unavailable must go on saying WHY, in words a reader can check.
    assert _the_surviving_statement_is_true()


def _the_surviving_statement_is_true() -> bool:
    """The one remaining `unsupported` row on these screens, judged.

    `Roles it carries` on the Agents screen. It is TRUE as written, and that was
    measured rather than assumed: `materialize` substitutes roles for instances
    and the result is what becomes durable, `RunEnvelope` carries no
    assignments, and nothing else in a run's records keeps the binding. A run's
    own journal genuinely cannot name the roles it was opened with.

    It is also INCOMPLETE, and that is a residual rather than a lie: the run's
    frozen configuration names the workflow and revision it froze, so the
    mapping is recoverable by joining the plan's `instance_id` per node to the
    template's `role_id` per node. That join is a feature this build does not
    have, not a sentence this build gets wrong -- and the row already shows the
    roles whenever a payload carries them.
    """
    text = source(PEOPLE_FILE)
    return ('unsupported("Roles it carries",\n      "A materialized plan names '
            "instances, not roles: the role is a workflow document's word and "
            "it is not carried into the run's plan.\", state)" in text
            and 'localizedFact(state, "agents.roles", row.role_ids)' in text)


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
    assert 'fact(state, "Revision", followed === null' in text
    assert "detail.config" in text
    # Both halves refuse together, so no reader can find one and infer the other.
    assert 'fact(state, "Workflow", followed === null' in text


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


def test_a_gate_asks_with_the_workflows_own_words_when_the_plan_carried_any():
    """A person asked to decide is entitled to why the plan says the gate exists.

    The purpose is frozen into the plan the run followed, so this is the only
    place that sentence still exists after the drawing was published. Two halves
    are held, because they fail apart: the row must CARRY it out of the frozen
    definition, and the screen must SAY it -- attributed, because everything
    else on that screen is a fact the product derived and an unattributed
    sentence beside those reads as one more of them.
    """
    read = (PANEL / "studio-runread.js").read_text(encoding="utf-8")
    # The three fields the DRAWING contributes moved into `drawnFacts` when the
    # row builder crossed the fifty-line rule; the row still spreads them in.
    carried = re.search(
        r"function drawnFacts\(node, titles, planned\) \{(.*?)\n\}",
        read, re.DOTALL).group(1)
    assert "...drawnFacts(node, titles, planned)," in read, read
    assert 'purpose: typeof node.purpose === "string" ? node.purpose : null,' in (
        carried), carried

    people = PEOPLE_FILE.read_text(encoding="utf-8")
    why = re.search(r"function whyAsked\(row, state\) \{(.*?)\n\}", people,
                    re.DOTALL).group(1)
    assert 'localizedFact(state, "agents.workflow_says", row.purpose)' in why, why
    # And only when there IS one: an empty attribution is worse than silence.
    assert 'typeof row.purpose === "string" && row.purpose' in why, why
