"""What a person has typed into the Studio survives everything but its own spend.

Split out of ``tests/test_studio_wiring.py`` when that module reached the line
cap, along the seam the reducer itself draws: a DRAFT -- the step's three
typed words, the document, the decision, the toolbar's folds and fields -- is
the reducer's, kept across every read, cleared only by a change of subject,
and spent only by the write minted from it. Every guard here is read off the
SOURCE; what a browser draws and posts under the same rules is measured in
``browser_tests/test_studio_step_races.py`` and its neighbours.

The paths and the comment stripper are the wiring module's own, imported
rather than spelled twice.
"""
from __future__ import annotations

import re

from tests.test_graph_source import _code
from tests.test_studio_wiring import BOOT, PANEL, RUNFORM, RUNWRITE, STORE, VIEW

WRITES = PANEL / "studio-runwrites.js"
TOOLBAR = PANEL / "studio-toolbardraft.js"


def test_the_step_draft_takes_three_typed_keys_and_no_fourth():
    """A control may fill in a person's words and nothing else.

    The plan owns the binding -- instance, capability, arguments, the step's own
    id -- and `writing` is the window's own bookkeeping. A patch loop that
    admitted either would let a control reach past what it is for, so the list
    is closed and pinned. Held in both directions: the three that may move, and
    the two names that may not appear in the loop at all.
    """
    source = _code(STORE)
    body = re.search(r"function stepDrafted\(state, patch\) \{(.*?)\n\}",
                     source, re.DOTALL)
    assert body is not None, "the reducer holds no step draft"
    keys = re.search(r"for \(const key of \[(.*?)\]\)", body.group(1))
    assert keys is not None, body.group(1)
    assert re.findall(r'"(\w+)"', keys.group(1)) == [
        "proposedBy", "rationale", "confirmedBy"]
    for forbidden in ("nodeId", "writing", "generation"):
        assert f'"{forbidden}"' not in keys.group(1), forbidden
    # And a write in flight is not a fact about the draft at all: the arm that
    # records one touches `runs.writes`, keyed by run and step, and leaves
    # every typed word exactly where it was. A flag on the draft was the
    # defect this replaced -- a read of the run turned it off under a pending
    # POST (R07A of the review of `8dec0e4`). The arm lives in the map's own
    # module now, and the map's rule reaches the draft not at all.
    writes = _code(WRITES)
    writing = re.search(r"export function stepWriting\(state, event\) \{(.*?)\n\}",
                        writes, re.DOTALL)
    assert writing is not None, "the map records no write in flight"
    assert "const held = keyOf(event);" in writing.group(1), writing.group(1)
    assert "return `${event.runId}/${event.nodeId}`;" in writes
    assert "writes[held] = ON_THE_WIRE" in writing.group(1)
    assert "delete writes[held]" in writing.group(1), writing.group(1)
    assert "runs.step" not in writes and "NO_STEP" not in writes, writes
    # The reducer imports the arm and names it in the table, and spells the
    # rule nowhere itself: exactly those two mentions.
    assert source.count("stepWriting") == 2, source.count("stepWriting")
    assert "function stepWriting(" not in source


def test_a_landed_read_of_the_same_run_leaves_what_a_person_is_typing_alone():
    """The rule that replaced an unconditional reset, and why it had to.

    Every road into `runMoved` is a READ: a `run` frame for an attempt event on
    another branch, a `state` frame, the reconnect's own re-read. Resetting both
    drafts there emptied the form under a person's hands while the control
    beside it promised that what they typed is kept -- and owner acceptance
    step 16 asks for the opposite in so many words.

    Held in BOTH directions, because either alone is a defect: a read of the
    same run keeps both drafts, and a read of another run or of none resets
    them. `writing` goes off whatever else is kept -- it is a fact about a
    request that is over once its answer has been read.
    """
    source = _code(STORE)
    assert "const NO_STEP = Object.freeze({" in source
    kept = re.search(r"function keptDrafts\(state, detail\) \{(.*?)\n\}",
                     source, re.DOTALL)
    assert kept is not None, "the reducer decides nothing about a kept draft"
    said = kept.group(1)
    assert "detail.run.run_id === state.runs.selectedId" in said, said
    assert "same ? state.runs.step : cleared(state.runs.step)" in said, said
    assert "same ? state.decisions.draft : NO_DRAFT" in said, said
    # A read says NOTHING about a write in flight: that fact left the draft
    # for `runs.writes` (R07A), so there is no flag here to turn off.
    assert "writing" not in said, said
    moved = re.search(r"function runMoved\(state, phase, detail, said\) \{(.*?)"
                      r"\n\}", source, re.DOTALL)
    assert moved is not None
    assert "const kept = keptDrafts(state, detail);" in moved.group(1)
    assert "step: kept.step" in moved.group(1), moved.group(1)
    assert "draft: kept.draft" in moved.group(1), moved.group(1)
    # The unconditional reset is gone from that arm, and the one road a draft
    # may not cross still resets outright: choosing ANOTHER run -- one
    # generation on, so a write minted from the old draft cannot spend the
    # new one; and the writes in flight are not that road's to touch.
    assert "step: NO_STEP" not in moved.group(1), moved.group(1)
    chosen = re.search(r"function runChosen\(state, runId\) \{(.*?)\n\}",
                       source, re.DOTALL)
    assert chosen is not None
    assert "step: cleared(state.runs.step)" in chosen.group(1), chosen.group(1)
    assert "writes" not in chosen.group(1), chosen.group(1)


def test_a_read_the_projection_refuses_keeps_both_drafts():
    """A read of the SAME run this build cannot project is not another run.

    `runLoaded` answered such a read through `runMoved` with no detail, and
    `keptDrafts` read "no detail" as "another run": both drafts were cleared
    on an error road, which is text lost to a fault the person did not cause
    (the slice-3 review's H). The failed road keeps the step draft, the
    document draft and the decision draft exactly as they were; the writes in
    flight were never that road's to touch.
    """
    source = _code(STORE)
    loaded = re.search(r"function runLoaded\(state, event\) \{(.*?)\n\}", source,
                       re.DOTALL)
    assert loaded is not None
    failed = re.search(r"if \(projectRunRead\(event\.read\) === null\) \{(.*?)\n  \}",
                       loaded.group(1), re.DOTALL)
    assert failed is not None, loaded.group(1)
    for kept in ("step: state.runs.step", "document: state.runs.document",
                 "draft: state.decisions.draft"):
        assert kept in failed.group(1), (kept, failed.group(1))
    assert "writes" not in failed.group(1), failed.group(1)


def test_the_two_write_roads_spend_their_own_draft_before_the_read():
    """A read cannot know the words are finished with; a write does.

    That is the whole seam. Once a landed read of the same run keeps a draft,
    something has to take it away when it really is spent -- and it is the two
    handlers that know: an accepted decision, an accepted step write, and the
    one refusal that says the screen is stale enough to re-read. Each clears
    BEFORE the read it provokes, so the form a person comes back to is the one
    the answer drew rather than the one they left.
    """
    writer = _code(RUNWRITE)
    # The decision road: the accepted arm and the `gate_unreached` recovery.
    assert writer.count('door.dispatch({type: "decision-chosen", key: null});') == 2
    for arm in ('door.dispatch({type: "status", notice: DECIDED});\n'
                '      door.dispatch({type: "decision-chosen", key: null});\n'
                "      door.refreshRun(asked);",
                'if (result.code !== "gate_unreached" || asked !== door.chosenRun())'
                " return;\n"
                '      door.dispatch({type: "decision-chosen", key: null});\n'
                "      door.refreshRun(asked);"):
        assert arm in writer, arm
    # The step road: the accepted arm only, and it spends ONLY the draft this
    # write was minted from -- run, step and generation fixed before the
    # request left -- so another step's unsent words survive its answer
    # (R07B). A refusal there keeps the words, which is the promise the shut
    # control makes.
    assert ('door.dispatch({type: "step-spent", ...spent});\n'
            "      door.refreshRun(asked);") in writer, writer
    assert writer.count('{type: "step-spent"') == 1, writer
    assert "const spent = {runId: asked, nodeId: row.nodeId," in writer, writer
    assert writer.index("const spent = ") < writer.index(
        '{type: "step-writing", ...spent, writing: true}'), writer
    assert '"step-chosen", nodeId: null' not in writer, writer
    # The ORDER inside the accepted carry is load-bearing (the fold review's
    # R6): `step-answered` renders first, and that render removes the focused
    # control -- whose `change` moves the generation -- BEFORE the spend
    # compares it, so words typed after the press without a blur survive.
    for road, spend in (("onStepWrite", '{type: "step-spent"'),
                        ("onDocumentWrite", '{type: "document-spent"')):
        body = re.search(rf"function {road}\((.*?)\n  \}}", writer, re.DOTALL)
        assert body is not None, road
        assert body.group(1).index('{type: "step-answered"') < body.group(1).index(
            spend), road


# -- the toolbar's own facts ---------------------------------------------------
#
# R08 folded the start box and the run form, open or folded BY STATE on every
# render -- so the next frame from anywhere closed a box a person had just
# opened, and the id typed into it went with it; the run form's fields had
# always been drawn from nothing (the slice-3 review's P4). Now: a touched
# fold is recorded and drawn back, the state deciding only while nobody has
# touched it; the start box and the run form draw their fields from the slice
# and commit on change; choosing another workflow is the one road that
# clears all three; and an opened run empties the form that opened it.


def test_the_toolbars_folds_and_fields_are_the_reducers():
    """The slice holds them, and the arms that move them are the draft's own."""
    store = _code(STORE)
    assert "folds: NO_FOLDS, starter: NO_STARTER, opening: NO_OPENING," in store
    for arm in ("fold: foldMoved,", '"opening-cleared": openingCleared,',
                '"opening-edit": (state, event) => openingEdited(state, event.patch),',
                '"starter-edit": (state, event) => starterEdited(state, event.patch),'):
        assert arm in store, arm
    draft = _code(TOOLBAR)
    assert 'export const NO_FOLDS = Object.freeze({start: null, run: null});' in draft
    assert 'if (!FOLDS.includes(event.name) || typeof event.open !== "boolean")' in draft
    assert "mode: \"observe\"" in draft
    boot = _code(BOOT)
    for wire in ('onFold: (name, open) => dispatch({type: "fold", name, open}),',
                 'editStarter: (patch) => dispatch({type: "starter-edit", patch},',
                 'editOpening: (patch) => dispatch({type: "opening-edit", patch},',
                 'dispatch({type: "opening-cleared"});'):
        assert wire in boot, wire


def test_the_toolbar_draws_its_folds_and_fields_from_the_slice_and_commits_back():
    """A touched fold is a person's; every field is drawn from, and committed
    into, the reducer's copy on its change; the summary carries a focus key so
    the render a toggle provokes gives the keyboard the summary back; and the
    run fold's summary names the state a person is in, in all four."""
    view = _code(VIEW)
    fold = re.search(r"function disclosure\(name, summary, open, body, handlers\) "
                     r"\{(.*?)\n\}", view, re.DOTALL)
    assert fold is not None, "the view's disclosure takes no handlers"
    assert ('box.addEventListener("toggle", () => {\n'
            "      if (box.open !== open) fold(name, box.open);") in fold.group(1)
    assert 'element("summary", {"data-focus": `fold:${name}`, text: summary})' in fold.group(1)
    assert 'const chosen = (object(held.folds) || {})[name];' in view
    assert view.count('foldOpen(held, "') == 2, view.count('foldOpen(held, "')
    # Committed on CHANGE, never on every keystroke: a render per keystroke
    # moved the caret to the end and doubled an IME's composition (the fold
    # review's R1/R2); the letters typed since are the boot net's to carry.
    assert 'name.addEventListener("change", () => edit({workflowId: name.value}));' in view
    assert 'addEventListener("input"' not in view
    assert "name.value = typeof held.workflowId === \"string\" ? held.workflowId : \"\";" in view
    form = _code(RUNFORM)
    assert 'runId.addEventListener("change", () => edit({runId: runId.value}));' in form
    assert 'cycleId.addEventListener("change", () => edit({cycleId: cycleId.value}));' in form
    assert 'addEventListener("input"' not in form
    assert "runId.value = typeof opening.runId === \"string\" ? opening.runId : \"\";" in form
    assert 'mode.value = CONTROL_MODES.includes(opening.mode) ? opening.mode : "observe";' in form
    assert "edit({roles: Object.fromEntries(" in form
    summary = re.search(r"function runSummary\(held\) \{(.*?)\n\}", view, re.DOTALL)
    assert summary is not None
    assert 'const chosen = typeof held.selectedId === "string" && held.selectedId !== "";' in summary.group(1)
    for said in ("Open a run — choose or start a workflow first",
                 "Open a run — this workflow has not been read",
                 "Open a run — publish a revision first",
                 "Open a run — revision ${published.revision} is published"):
        assert said in summary.group(1), said


def test_the_focus_net_carries_the_words_and_the_caret_and_never_guesses():
    """The net under every mount, and what it carries.

    A pass replaces the focused control; the successor is drawn from the
    reducer, which holds what `change` committed. So the net carries the
    live value and the caret of a text control into its successor (the fold
    review's R1/R5). A step field stays scoped to the form it came from;
    shell-wide uniqueness cannot establish ownership after that form has
    vanished and left a sibling as the sole holder of the same key (R4).

    The two functions left the boot module at its line cap, and the claim
    moved with them. The boot still takes the key before every pass and hands
    it back after, inside the shell -- that half is held on the boot.
    """
    boot, net = _code(BOOT), _code(PANEL / "studio-focus.js")
    assert "const key = focusTarget();" in boot
    assert "restoreFocus(shell, key);" in boot
    target = re.search(r"export function focusTarget\(\) \{(.*?)\n\}", net, re.DOTALL)
    assert target is not None
    assert "start: typed ? active.selectionStart : null," in target.group(1)
    assert "value: typed ? active.value : null" in target.group(1)
    assert 'const form = active.closest("[data-step]");' in target.group(1)
    assert 'step: form === null ? null : form.getAttribute("data-step")' in target.group(1)
    restore = re.search(r"export function restoreFocus\(shell, held\) \{(.*?)\n\}",
                        net, re.DOTALL)
    assert restore is not None
    assert "if (found.length !== 1) return;" in restore.group(1)
    assert 'const within = held.step === null ? "" : `[data-step="${held.step}"] `;' in restore.group(1)
    assert "if (successor.value !== held.value) successor.value = held.value;" in restore.group(1)
    assert "successor.setSelectionRange(held.start, held.end);" in restore.group(1)
    # The Runs screen's own restore carries the caret too.
    runs = _code(PANEL / "studio-runs.js")
    assert "start: typed ? active.selectionStart : null," in runs
    assert "successor.setSelectionRange(key.start, key.end);" in runs


def test_a_model_is_a_roles_optional_harness_bound_draft_not_a_catalogue():
    """The existing nullable participant field is filled from a typed control.

    These source change detectors hold the intended seam; the layout browser
    module measures model POSTs, frozen read-back, resets and syntax refusal.
    Provider-specific availability is deliberately not guessed by this form.
    """
    form = _code(RUNFORM)
    assert '"data-focus": `model-${role}`, maxlength: "128"' in form
    assert 'pattern: ID_PATTERN, placeholder: "Harness default (unpinned)"' in form
    assert 'model: models.get(role).value.trim() || null' in form
    assert 'model.addEventListener("change", () => edit({models:' in form
    assert 'model.disabled = !pick.value;' in form
    assert 'if (open === null || !box.reportValidity()) return;' in form
    draft = _code(TOOLBAR)
    assert 'models: Object.freeze({})' in draft
    assert 'const models = typedMap(patch, "models");' in draft
    assert 'bindings[role] && bindings[role] === held.roles[role]' in draft
    assert 'models: Object.freeze(pinned)' in draft
    boot = _code(BOOT)
    assert '&& !Object.hasOwn(patch, "models")' in boot
