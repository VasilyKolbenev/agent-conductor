"""What the Studio may put on the wire when a person drives a planned step.

The Runs screen can now propose a step and confirm the proposal standing on it.
That is the first control in this window whose body decides what a machine
somewhere is about to do, and this module holds it to the two rules that make
it safe to have at all:

1. **the binding is the PLAN's.** `node_id`, `instance_id`, `capability` and
   `arguments` are read out of the frozen graph node the SERVER's schedule
   chose, and there is no control anywhere that could change one of them. The
   server already refuses the alternative -- `graph_causality._matches_its_node`
   refuses arguments that are not the node's own bytes, and
   `authorize_holds._hold_node_is_eligible` refuses a node the schedule does not
   call runnable -- so a window that offered a control over either would be
   composing a body that is bound to be refused and calling it a form.
2. **the key sets are the API's own.** Both are DERIVED from
   `conductor.command.api_contracts` rather than written down here, so a field
   added or removed on the durable side reds this until the window moves with
   it. A tenth key in the proposal body or a seventh in the confirm body is a
   body the boundary refuses whole, with nothing on screen able to say why.

Everything here is SOURCE. What a browser really draws and really posts is
`browser_tests/test_studio_step.py`, and neither module can stand in for the
other: this one cannot see a control that is never reached, and that one cannot
see a key set that happens to be right for the one fixture in front of it.
"""
from __future__ import annotations

import re
from pathlib import Path

from conductor.command.api_contracts import _CONFIRM_FIELDS, _PROPOSAL_REQUIRED
from conductor.command.contract_values import ControlMode

from tests.test_graph_source import _code
from tests.test_studio_runs import _balanced

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
STEP = PANEL / "studio-runstep.js"
BOOT = PANEL / "studio.js"
RUNS = PANEL / "studio-runs.js"
#: The two places a person reads the authority ladder in words: the run form's
#: meanings, chosen from before a run is opened, and the Runs screen's notes,
#: read beside `Authority (mode)` once it is.
FORM = PANEL / "studio-runform.js"
WORDS = PANEL / "studio-runwords.js"
#: What a press on a step control MEANS, split off the boot module when that
#: file reached the line cap. The wire stayed behind: this file is handed a
#: `write` and reaches no socket, which is why the door counts next door are
#: unchanged by the split.
WRITER = PANEL / "studio-runwrite.js"
#: Where the draft and the writes in flight live, and the rule that keeps them
#: apart.
STORE = PANEL / "studio-store.js"
#: Which writes are in flight and until when: the ownership map's own rules,
#: split off the reducer at the line cap when an accepted write learned to
#: stay shut until the run it wrote to has been read again.
WRITES = PANEL / "studio-runwrites.js"
#: The nine keys a proposal from this window carries: everything the frozen API
#: requires, plus the one optional field that binds the action to the plan. Read
#: off the contract, never spelled a second time.
PROPOSAL_KEYS = frozenset(_PROPOSAL_REQUIRED) | {"node_id"}
#: The three fields a PERSON supplies, and the whole of what they may supply.
TYPED_FIELDS = ("proposed_by", "rationale", "confirmed_by")


def _body(source: str, name: str) -> str:
    """The object literal one body builder returns."""
    found = re.search(
        rf"function {name}\([^)]*\) \{{\n  return \{{\n(.*?)\n  \}};", source,
        re.DOTALL)
    assert found is not None, f"studio-runstep.js builds no {name}"
    return found.group(1)


def _keys(body: str) -> list[str]:
    """The literal's own keys, in source order, sentences blanked first."""
    bare = re.sub(r'"[^"]*"', '""', body)
    return re.findall(r"^    ([A-Za-z_][A-Za-z0-9_]*):", bare, re.MULTILINE)


def test_the_body_builders_are_read_before_anything_is_asserted_about_them():
    """Calibration: the reader must find a literal and its keys, or say so.

    Every assertion below is `_keys(_body(...))`, so a reader that answered
    an empty list would turn each of them into a claim about nothing. It is
    driven on a known shape here, both ways.
    """
    assert _keys("    alpha: one,\n    beta: `x:${y}`,") == ["alpha", "beta"]
    assert _keys('    alpha: "not: a key",') == ["alpha"]
    found = _body(_code(STEP), "confirmBody")
    assert "proposal_id:" in found and "function" not in found


def test_the_studios_proposal_body_carries_the_schedules_node_and_never_a_typed_binding():
    """The nine keys, and where each of the four binding ones comes from.

    `node_id` is the one that closes the hole this control could otherwise
    open: an unbound proposal on a planned run is authority the plan never
    gave, and it mis-resolves the verifier besides -- both verifier doors key
    off the request's binding. It is ALWAYS the node the schedule chose, and
    the three facts beside it are that same node's, so the body cannot describe
    a step the plan does not hold.
    """
    step = _code(STEP)
    body = _body(step, "proposalBody")

    assert set(_keys(body)) == PROPOSAL_KEYS, sorted(
        set(_keys(body)) ^ PROPOSAL_KEYS)
    assert len(_keys(body)) == len(PROPOSAL_KEYS), "the literal repeats a key"
    # The four the PLAN owns, read off the node and off nothing else.
    for line in ("node_id: node.node_id,", "instance_id: node.instance_id,",
                 "capability: node.capability,", "arguments: node.arguments,"):
        assert line in body, (line, body)
    # The two a PERSON owns, and they are the only two draft reads in it.
    assert sorted(set(re.findall(r"draft\.(\w+)", body))) == [
        "proposedBy", "rationale"]


def test_the_step_the_body_names_is_the_one_the_servers_schedule_chose():
    """The offer rule, read from a durable fact and never from a refusal.

    `stepControls` is handed the schedule ROW the server computed for this
    node, and it returns nothing at all unless that row says `runnable`. A
    window that offered on anything weaker -- a phase, an absent outcome, the
    plan's shape walked here -- would offer work `authorize` is bound to
    refuse, which is the defect the schedule exists to remove.
    """
    step = _code(STEP)
    offer = re.search(
        r"export function stepControls\([^)]*\) \{(.*?)\n\}", step, re.DOTALL)
    assert offer is not None, "studio-runstep.js exports no stepControls"
    body = offer.group(1)
    assert 'standing === null || standing.state !== "runnable"' in body, body
    assert "return [];" in body, body
    # And a step the plan binds to nothing is offered nothing either: a node
    # with no instance and no capability has no body to build.
    assert 'typeof node.instance_id !== "string"' in body, body
    assert 'typeof node.capability !== "string"' in body, body
    # `runnable` is read in exactly one place, so a second reading cannot
    # disagree with the first about one row.
    assert step.count('"runnable"') == 1, step.count('"runnable"')


def test_the_step_controls_ask_a_person_for_three_facts_and_no_binding():
    """No select, no argument control, and no way to type a binding.

    The point is not that the current controls happen to be text boxes. It is
    that there is no control here for any field the plan owns -- so the class
    of defect where a person is invited to compose work the plan never
    described cannot be reached from this file at all.
    """
    step = _code(STEP)
    named = re.findall(r'textControl\("(\w+)"', step)

    assert named == list(TYPED_FIELDS), named
    assert step.count('element("input"') == 1, "a second control was built"
    assert 'element("select"' not in step
    assert 'element("textarea"' not in step
    for forbidden in ("field:instance", "field:capability", "field:arguments",
                      "field:node", "field:scope", "argument:"):
        assert forbidden not in step, forbidden
    # A read that never landed is a THIRD answer and says so. "No adapter
    # serves this" and "this window was not told" send a person to two
    # different places, and answering the first while the second is true sends
    # them looking for a provider they already have.
    join = re.search(r"function whyNoAdapter\(detail, node\) \{(.*?)\n\}", step,
                     re.DOTALL)
    assert join is not None, "nothing joins the plan node to the controls read"
    assert "if (controls === null) {" in join.group(1), join.group(1)
    assert "controls read has not landed here" in join.group(1)
    assert "This build serves no adapter for" in join.group(1)
    # The two submit controls, keyed by the node the schedule chose, so the
    # keyboard road to each is derivable rather than positional.
    assert "`propose:${node.node_id}`" in step
    assert "`confirm:${node.node_id}`" in step


def test_the_confirm_body_is_the_apis_own_six_fields_and_names_no_node():
    """`_CONFIRM_FIELDS`, derived, and every one of them read off the RECORD.

    Five of the six restate the stored proposal, and the runtime refuses a
    confirmation that differs in any of them -- so they are copied from the
    journal rather than from anything this window remembers about the write
    that made it. And a confirm body may not name a node at all: `node_id` is
    copied from the stored proposal at authorize time, so a body that could
    name one could name a different one.
    """
    body = _body(_code(STEP), "confirmBody")

    assert set(_keys(body)) == set(_CONFIRM_FIELDS), sorted(
        set(_keys(body)) ^ set(_CONFIRM_FIELDS))
    assert "node_id" not in body
    for name in ("proposal_id", "preview_digest", "capability", "scope",
                 "config_digest"):
        assert f"{name}: proposal.{name}," in body, name
    assert sorted(set(re.findall(r"draft\.(\w+)", body))) == ["confirmedBy"]


def test_the_proposal_it_confirms_is_read_out_of_the_run_not_out_of_a_reply():
    """What is judged must be what was appended.

    The standing proposal is found in `detail.records` -- the run READ -- and
    the request that would have taken it is matched by `preview_digest`, which
    is the identity the runtime itself holds the pair to. A window that
    confirmed the body a POST answered with would be confirming a document it
    never re-read.
    """
    step = _code(STEP)
    finder = re.search(
        r"function standingProposal\(detail, nodeId\) \{(.*?)\n\}", step,
        re.DOTALL)
    assert finder is not None, "nothing finds the proposal standing on a step"
    body = finder.group(1)
    assert "rows(detail.records)" in body, body
    assert 'row.record_type === "action_proposal"' in body, body
    assert 'row.record_type === "action_request"' in body, body
    assert "taken.has(record.preview_digest)" in body, body
    assert "record.node_id === nodeId" in body, body
    # The last one standing, never the first: a step a loop reopened has more
    # than one proposal in its journal and the older ones are history.
    assert "open[open.length - 1]" in body, body


def _handler_names(boot: str) -> set[str]:
    """Every name the boot module publishes in its one handler table."""
    table = re.search(r"const handlers = Object\.freeze\(\{(.*?)\n  \}\);",
                      boot, re.DOTALL)
    assert table is not None, "the boot module publishes no handler table"
    return set(re.findall(r"^    (\w+)[:,]", table.group(1), re.MULTILINE))


def _function(boot: str, name: str) -> str:
    """One of the boot module's own functions, by name, body only."""
    found = re.search(
        rf"^  (?:async )?function {name}\([^)]*\) \{{\n(.*?)\n  \}}$", boot,
        re.DOTALL | re.MULTILINE)
    assert found is not None, f"the boot module declares no {name}"
    return found.group(1)


def test_the_reader_that_finds_the_handler_table_and_a_function_is_calibrated():
    """Both instruments below, proven on the file they are about to judge.

    A table reader that answered an empty set, or a function reader that
    answered an empty string, would turn every assertion built on them green
    while proving nothing at all.
    """
    boot = _code(BOOT)
    named = _handler_names(boot)
    assert {"selectRun", "submitDecision", "proposeStep"} <= named, sorted(named)
    assert "onStepWrite" not in named, "a private function reached the table"
    assert "await loadRun(chosenRun);" in _function(boot, "refreshRun")
    assert "function" not in _function(boot, "loadRun")
    assert "door.refreshRun(asked);" in _function(_code(WRITER), "onStepWrite")


def test_only_a_human_press_reaches_the_two_new_write_targets():
    """The rule this window states at its head, held for the step road.

    No load, no frame, no reconnect and no read may write. What this used to
    pin was a SPELLING -- that the private helper's name is absent from the
    stream -- and a frame calling `handlers.proposeStep(frame.step)` survived
    it, because that road never mentions the helper at all. So the four step
    handler names are DERIVED from the table the controls are handed, and every
    way of reaching one is looked for: the table's own name, and the private
    door beneath it, in the stream and in all three read paths.

    The door moved next door when the boot module reached its line cap, and the
    claim did not move with it: the boot still owns every socket, so the boot is
    still where a frame or a read could reach a write, and it is the boot that
    is searched.
    """
    boot, writer = _code(BOOT), _code(WRITER)
    step = {"chooseStep", "editStep", "proposeStep", "confirmStep"}
    assert step <= _handler_names(boot), sorted(step - _handler_names(boot))
    for target in ('write("proposals"', 'write("actions"'):
        assert boot.count(target) == 0 and writer.count(target) == 0, target
    assert writer.count("door.write(target, asked, row.body,") == 1
    assert writer.count("onStepWrite(") == 3, writer.count("onStepWrite(")
    assert 'proposeStep: (row) => onStepWrite("proposals", row,' in writer
    assert 'confirmStep: (row) => onStepWrite("actions", row,' in writer
    # The boot builds the four and hands them on; it takes none of them itself.
    assert "const step = stepWriters({" in boot
    for name in sorted(step):
        assert f"handlers.{name}(" not in boot, name
        assert f"step.{name}(" not in boot, name
    # And no read, no frame and no reconnect reaches a handler, the factory, or
    # the private door. Named sections, because "absent from this file" would
    # pass on a file that had no handlers at all.
    sections = {"the stream": boot[boot.index("const stream = new EventSource"):]}
    for name in ("loadRun", "loadRuns", "refreshRun"):
        sections[name] = _function(boot, name)
    for where, section in sorted(sections.items()):
        for name in sorted(step | {"onStepWrite", "stepWriters"}):
            assert name not in section, (where, name)


def test_the_attempt_id_counts_up_from_what_the_run_already_holds():
    """A derivable, BOUNDED identity that cannot collide with one already spent.

    Both halves were unwitnessed while the only seeded run had zero attempts:
    `attempt-<node>-0` came out right whatever the body did. The body is pinned
    here and driven for real next door.

    What it must NOT be is the COUNT of the set. `_hold_attempt_is_not_taken`
    refuses an id this run already holds, and that refusal is permanent because
    the same journal mints the same id every time -- so one `attempt-goal-1` in
    a journal of one attempt made the next mint collide with it forever. The
    greatest number already spelled plus one cannot, and a foreign id in
    another grammar is skipped rather than counted.

    And it is BOUNDED (R09 of the review of `8dec0e4`): the named form spends
    the node's own name, so a node of 119 characters minted an id the contract
    refuses. Two forms now, and they cannot meet -- every named id begins
    `attempt-`, every digest id begins `attempt.` -- so a node literally named
    like another node's digest never shares an id with it. The counter is read
    under BOTH of this node's forms, and the minted id is checked against the
    run's whole set before it is offered.
    """
    step = _code(STEP)
    body = re.search(r"function attemptId\(node, runtime\) \{(.*?)\n\}",
                     step, re.DOTALL)
    assert body is not None, "studio-runstep.js mints no attempt id"
    said = body.group(1)
    assert 'const NAMED = "attempt-";' in step, step
    assert 'const DIGESTED = "attempt.";' in step, step
    assert "const ID_LIMIT = 128;" in step, step
    # Both forms are scanned for the counter, and the counter is max + 1.
    assert "countersUnder(forms.named, ids)" in said, said
    assert "countersUnder(forms.digested, ids)" in said, said
    assert "Math.max(...taken) + 1" in said, said
    # The fit rule chooses the form per counter, never truncating the name.
    assert "named.length <= ID_LIMIT ? named" in said, said
    # The free-id check against the whole run, not only this node's forms.
    assert "while (ids.includes(minted))" in said, said
    # The digest is a fixed, documented function over the UTF-8 bytes.
    assert "function fnv64(text)" in step, step
    assert "0xcbf29ce484222325n" in step and "0x100000001b3n" in step, step
    # The count is what this replaced, in either spelling.
    assert ".length}`" not in said, said
    assert "attempt_ids).length" not in said, said
    # No truncation of a plan id anywhere in the minting road.
    assert "slice(0" not in said and "substring(" not in said, said


def test_the_window_asks_for_the_smaller_of_the_two_ceilings():
    """The plan's is not the only one, and honouring it alone was a trap.

    `graph_causality._within_the_planned_ceiling` refuses a document asking for
    more than its STEP allows; `runtime._hold_budget` refuses a proposal past
    the RUN's `max_action_seconds`, and it does so at AUTHORIZE. A plan naming
    7200s therefore proposed cleanly and made every Confirm 409 -- under a
    sentence blaming a plan that had not moved. The window asks for the smaller
    of the two, and says so where the number is drawn.
    """
    step = _code(STEP)
    body = re.search(r"function timeoutOf\(node\) \{(.*?)\n\}", step, re.DOTALL)
    assert body is not None, "studio-runstep.js asks for no ceiling at all"
    said = body.group(1)
    assert "Number.isInteger(node.timeout_seconds)" in said, said
    assert "Math.min(node.timeout_seconds, DEFAULT_TIMEOUT)" in said, said
    assert ": DEFAULT_TIMEOUT;" in said, said
    assert "const DEFAULT_TIMEOUT = 900;" in step
    # And the sentence beside it says both halves of the rule.
    assert "whichever is smaller" in step
    assert 'note(TIMEOUT_NOTE),' in step


def test_a_standing_proposal_is_never_described_as_going_stale():
    """The freshness budget judges the CONFIRMATION, not the proposal.

    `runtime._hold_freshness` measures `confirmed_at`, which the server mints
    at the moment of the press (`confirmed_at=self._clock()`), so a proposal
    written last year is confirmed exactly as one written a second ago. The
    sentence that said otherwise sent a person to propose again over a control
    that works, and it is pinned ABSENT so it cannot come back; the API witness
    beside it holds the fact the absence rests on.
    """
    step = _code(STEP)
    for gone in ("freshness budget", "FRESHNESS", "left standing long enough"):
        assert gone not in step, gone
    # `Proposed at` stays. It is history, and the row draws it as history.
    assert 'fact("Proposed at", proposal.proposed_at),' in step


def test_the_stale_screen_sentence_names_the_run_as_well_as_the_plan():
    """One refusal class, five reasons, and the wire keeps none of the prose.

    `authorization_refused` covers the plan's own eligibility AND the run's
    budget, its changed facts, its attempt identity and a sandbox it cannot
    provide. A sentence naming only the plan was wrong for four of the five,
    and sent a person to look at a plan that had not moved.
    """
    step = _code(STEP)
    named = re.search(r"STEP_MOVED = Object\.freeze\(\s*\[(.*?)\]\)", step,
                      re.DOTALL)
    assert named is not None
    assert set(re.findall(r'"(\w+)"', named.group(1))) == {
        "authorization_refused", "service_refused", "run_terminal",
        "proposal_rebind_required"}
    # `route_unsafe` is refused: the sentence promises a read, and `_hold_route`
    # refuses that read on the way in too. A promise this window cannot keep is
    # worse than reporting the refusal and reopening nothing.
    assert "route_unsafe" not in named.group(1), named.group(1)
    # Read on the RAW text: what is pinned here is the reason, and a reason
    # lives in prose. Its absence is what would let the word back on the list.
    assert "that read is refused too" in STEP.read_text(encoding="utf-8")
    assert ("READ_AGAIN = \"Read again: this step is offered only while the \"\n"
            "  + \"run's plan calls it runnable and the request fits what the "
            "run allows; \"\n  + \"the run was read again.\";") in step, step
    # Every code on that list is one this window can translate, so the sentence
    # never stands beside a refusal it has no words for.
    labels = _code(PANEL / "command-projection.js")
    for code in re.findall(r'"(\w+)"', named.group(1)):
        assert re.search(rf"^  {code}: ", labels, re.MULTILINE), code


def test_a_refusal_gives_the_control_back_with_what_was_typed_still_in_it():
    """The draft is marked, never destroyed, and the mark is what shuts it.

    Clearing the draft at the door did make a second press impossible -- and it
    also emptied the form beside a sentence promising that what was typed is
    kept, on every refusal that brings no read: the line down, a body the
    boundary refuses, a session that rotated. So the flag is dispatched BEFORE
    the request and cleared on the refusal path, and only the accepting read
    takes the draft away.
    """
    door = _function(_code(WRITER), "onStepWrite")
    # Marked BEFORE the request goes out: that ordering is the whole of the
    # double-press guard, and reversing it makes a second press a second
    # durable proposal.
    marked = door.index(
        'door.dispatch({type: "step-writing", ...spent, writing: true});')
    assert marked < door.index("door.write(target, asked, row.body,"), door
    # …and cleared from the ONE exit every road shares. It used to be cleared
    # on the refusal arm alone, which left the flag set on the two roads that
    # reach neither arm: a write retired by another write's generation bump,
    # and one never sent because the line was down.
    assert door.rstrip().endswith(
        '}).finally(() => door.dispatch({type: "step-writing", ...spent,\n'
        "      writing: false}));"), door
    assert door.count('writing: false') == 1, door
    # Both arms end in the read that is what really says what happened.
    assert door.count("door.refreshRun(asked);") == 2, door
    step = _code(STEP)
    assert "shut: submit === null || edit === null || !live || writing" in step
    assert "if (wire.writing) said.push(note(WRITING_NOTE));" in step
    # The sentence is declared once, with the words two fragments say.
    assert "What you have typed here is kept." in _code(WORDS)


def test_the_screen_hands_the_step_control_the_row_and_decides_nothing():
    """One caller, in the position row, after the sentence that says why.

    The offer rule lives in one file. A screen that decided any part of it
    would be a second authority over which step may be driven, and the two
    would disagree the first time either moved.
    """
    runs = _code(RUNS)
    assert runs.count("stepControls(") == 1
    assert ("item.append(...stepControls(node, runtime, plan, detail, state, "
            "handlers));") in runs
    assert 'from "./studio-runstep.js";' in runs
    # And the screen types no binding of its own either.
    assert 'element("input"' not in runs
    assert 'element("form"' not in runs


def test_the_controls_offer_only_what_the_runs_frozen_authority_permits():
    """R06 of the review of `8dec0e4`: the mode is read before a write is drawn.

    The controls read the schedule and never the run's `mode`, so an observe
    run offered a Propose the server refused (`service.propose`, 409) and a
    propose run offered a Confirm it refused (`runtime.authorize` admits
    `confirm` alone, 409) -- each under a sentence sending a person to a plan
    that had not moved. The rule is a closed table over the server's own
    ladder, and a word the table does not carry permits nothing.
    """
    step = _code(STEP)
    offer = re.search(
        r"export function stepControls\([^)]*\) \{(.*?)\n\}", step, re.DOTALL)
    assert offer is not None, "studio-runstep.js exports no stepControls"
    body = offer.group(1)
    # The schedule's word still comes FIRST: a blocked row of an observe run is
    # told why it is blocked by the sentence next door, not that it is
    # unwritable -- the authority sentence stands where a control would have.
    assert body.index('standing.state !== "runnable"') < body.index(
        "authorityOf(detail)"), body
    assert ('if (authority.permits === "nothing") {\n'
            "    return [nothingPermitted(authority)];") in body, body
    assert re.search(r'authority\.permits === "confirmations"\s*\n\s*'
                     r"\? confirmForm\(", body), body
    assert ": [proposalsOnly(authority)]" in body, body
    assert body.count("confirmForm(") == 1 and body.count("proposeForm(") == 2
    assert body.index('authority.permits === "nothing"') < body.index(
        "needsMaterialReproposal(standingProposal(detail, node.node_id), detail)")
    # The table is the server's whole ladder, and what each rung permits is
    # the server's two refusals restated: observe proposes nothing, confirm
    # alone confirms, and policy -- a word nothing serves -- is propose.
    table = re.search(r"const PERMITS = Object\.freeze\(\{(.*?)\}\);", step,
                      re.DOTALL)
    assert table is not None, "studio-runstep.js declares no PERMITS"
    permits = dict(re.findall(r'([a-z]+): "([a-z]+)"', table.group(1)))
    assert set(permits) == {mode.value for mode in ControlMode}, permits
    assert permits == {"observe": "nothing", "propose": "proposals",
                       "policy": "proposals", "confirm": "confirmations"}
    assert 'permits: PERMITS[run.mode] || "nothing"' in step
    assert "const run = object(detail.run) || {};" in step
    # Every sentence that withholds a control names where the authority is
    # granted, and the propose form under a lesser authority says what its
    # record will and will not do.
    assert step.count("${authority.road}") == 2, step.count("${authority.road}")
    assert "Open a run form on the Workflow screen" in step
    assert "nothing can confirm it here" in step
    assert ('...(authority.permits === "proposals"\n'
            "        ? [proposedUnder(authority.mode)] : [])") in step


def test_the_confirm_road_names_what_the_run_form_really_opens():
    """A run of the workflow's PUBLISHED revision, and not "this revision".

    The Open a run form offers no way to choose a revision once a newer one
    is published (the slice-3 review's #22), and a run that follows no
    workflow -- which the API admits -- has no workflow to reopen at all: it
    is told to publish one and open a run of it (the fold review's H4). Both
    sentences name the one form that grants authority.
    """
    step = _code(STEP)
    assert "open a new run of this workflow's " in step
    assert "published revision with authority confirm" in step
    assert "new run of this revision" not in step
    assert 'const NO_WORKFLOW_ROAD = "This run follows no workflow. ' in step
    assert step.count("the Open a run form on the Workflow screen grants it explicitly.") == 2
    assert ('road: typeof run.workflow_id === "string" ? CONFIRM_ROAD : NO_WORKFLOW_ROAD'
            in step)


def test_a_write_in_flight_is_its_run_and_steps_own_and_spends_only_its_draft():
    """R07 of the review of `8dec0e4`, A and B, and the owner's control C.

    The write flag lived on the ONE draft, so a landed read turned it off
    under a pending POST (A: two proposals from one press and a Read), the
    accepted road cleared the whole draft (B: alpha's answer emptied omega's
    fields), and a map cleared on a change of run would have handed the
    control back on the way back to run A (C). Now a write in flight is a
    fact about one step of one run, kept in `runs.writes` apart from the
    draft; the control reads membership there; and the accepted road spends
    only the draft it was minted from, by run, step and generation.
    """
    step = _code(STEP)
    writing = re.search(r"function writingOf\((.*?)\) \{(.*?)\n\}", step,
                        re.DOTALL)
    assert writing is not None, "studio-runstep.js reads no write in flight"
    assert writing.group(1) == "state, detail, node", writing.group(1)
    assert ("Object.hasOwn(writes, `${runOf(detail)}/${node.node_id}`)"
            in writing.group(2)), writing.group(2)
    # Both roads read it there, and only there.
    assert step.count(", writingOf(state, detail, node));") == 2, step
    assert "writingOf(draft)" not in step, step
    # Both roads hand the door what their draft's generation was.
    assert step.count("generation: draft.generation") == 2, step
    store = _code(STORE)
    assert "writes: Object.freeze({})" in store, "the run screen holds no writes"
    assert '"step-spent": stepSpent,' in store, store
    spent = re.search(r"function stepSpent\(state, event\) \{(.*?)\n\}", store,
                      re.DOTALL)
    assert spent is not None, "the reducer spends no draft"
    for held in ("state.runs.selectedId !== event.runId",
                 "step.nodeId !== event.nodeId",
                 "step.generation !== event.generation"):
        assert held in spent.group(1), (held, spent.group(1))
    assert "step: cleared(step)" in spent.group(1), spent.group(1)
    # Every road that resets the draft moves it one generation on, so a write
    # minted from the old draft can never mistake the new one for its own.
    cleared = re.search(r"function cleared\(step\) \{(.*?)\n\}", store,
                        re.DOTALL)
    assert cleared is not None, "the reducer clears no draft by generation"
    assert "generation: step.generation + 1" in cleared.group(1)
    chosen = re.search(r"function stepChosen\(state, event\) \{(.*?)\n\}",
                       store, re.DOTALL)
    assert chosen is not None
    assert "generation: state.runs.step.generation + 1" in chosen.group(1)


def test_what_a_person_is_typing_is_carried_across_a_render():
    """A frame in the middle of a word must not cost the letters before it.

    Measured on the propose road, six drained runs: `release-owner` reached
    the wire as `er`, `r` and `ner` three times in six. A render replaces the
    control and draws the new one from the draft, which holds only what
    `change` has committed; and the control drawn first, on its own change,
    chose the step again and reset what a later control had committed. So
    the control drawn in a focused control's place inherits its live value --
    of the SAME form, so three runnable steps never share one person's word --
    and choosing the step already chosen moves nothing.
    """
    step = _code(STEP)
    carry = re.search(r"function liveValue\(step, name, fallback\) \{(.*?)\n\}",
                      step, re.DOTALL)
    assert carry is not None, "studio-runstep.js carries no live value"
    assert "document.activeElement" in carry.group(1)
    assert 'active.getAttribute("name") !== name' in carry.group(1)
    assert 'form.getAttribute("data-step") === step' in carry.group(1)
    assert step.count('liveValue(step, "') == 3, step.count('liveValue(step, "')
    for name in ("proposed_by", "rationale", "confirmed_by"):
        assert f'liveValue(step, "{name}",' in step, name
    chosen = re.search(r"function stepChosen\(state, event\) \{(.*?)\n\}",
                       _code(STORE), re.DOTALL)
    assert chosen is not None
    assert ("if (nodeId !== null && state.runs.step.nodeId === nodeId) "
            "return state;") in chosen.group(1), chosen.group(1)


def test_every_typed_word_moves_the_generation_so_an_answer_spends_only_what_it_sent():
    """The slice-3 review's D: words typed UNDER a pending write were spent.

    The generation moved only on a choice or a clearing, so a name typed into
    the Confirm form the proposal's own frame drew -- while that proposal's
    answer was still on the wire -- was spent by the answer as "the draft this
    write was minted from" (studio-store.js:694 at `ff04172`). Every typed
    word now moves the generation, on both drafts, so a write spends exactly
    the draft it sent and nothing typed since; a patch that moves nothing
    moves the generation nothing either.
    """
    store = _code(STORE)
    drafted = re.search(r"function stepDrafted\(state, patch\) \{(.*?)\n\}",
                        store, re.DOTALL)
    assert drafted is not None, "the reducer holds no step draft"
    body = drafted.group(1)
    assert "next.generation = state.runs.step.generation + 1;" in body, body
    assert "if (!moved) return state;" in body, body
    assert body.index("if (!moved) return state;") < body.index(
        "next.generation = "), body
    draft = _code(PANEL / "studio-rundraft.js")
    edited = re.search(r"export function documentEdited\(state, patch\) \{(.*?)\n\}",
                       draft, re.DOTALL)
    assert edited is not None, "the document draft has no edit arm"
    assert "next.generation = held.generation + 1;" in edited.group(1), edited.group(1)
    assert "if (!moved) return state;" in edited.group(1), edited.group(1)


def test_an_accepted_write_keeps_its_control_shut_until_the_run_is_read_again():
    """The slice-3 review's E, and the map's value given its consumer.

    The accepted write's entry left `runs.writes` the moment the server
    answered, so the control was redrawn over the stale screen and stayed
    shut only because the spent draft left a required field empty -- a draft
    NOT spent would have opened it to a second press. Now the accepted road
    marks the entry answered and only a landed read of THAT run removes it;
    every other end removes it at once. The map's value is what says which,
    so it is no longer a generation nothing read.
    """
    writes = _code(WRITES)
    assert 'export const ON_THE_WIRE = "writing";' in writes
    assert 'export const ANSWERED = "answered";' in writes
    writing = re.search(r"export function stepWriting\(state, event\) \{(.*?)\n\}",
                        writes, re.DOTALL)
    assert writing is not None, "the map records no write in flight"
    assert "writes[held] = ON_THE_WIRE" in writing.group(1), writing.group(1)
    assert "else if (writes[held] === ON_THE_WIRE) delete writes[held]" in writing.group(1)
    assert "generation" not in writing.group(1), writing.group(1)
    answered = re.search(r"export function stepAnswered\(state, event\) \{(.*?)\n\}",
                         writes, re.DOTALL)
    assert answered is not None, "the map has no answered arm"
    assert "if (state.runs.writes[held] !== ON_THE_WIRE) return state;" in answered.group(1)
    assert "[held]: ANSWERED" in answered.group(1), answered.group(1)
    read = re.search(r"export function readWrites\(writes, runId\) \{(.*?)\n\}",
                     writes, re.DOTALL)
    assert read is not None, "a landed read removes no answered write"
    assert ("if (value !== ANSWERED || !held.startsWith(`${runId}/`)) "
            "kept[held] = value;") in read.group(1), read.group(1)


def test_the_reducer_and_both_write_roads_wire_the_answered_entry():
    """The map's three arms reach the reducer, and the two roads mark first.

    The reducer wires the two arms by name and removes answered entries on
    the ready road of `runLoaded`, for the run just read; both write roads
    mark the entry answered BEFORE asking whether the person is still looking
    at that run -- the run was written to whether or not they are, and its
    next read is what gives the control back.
    """
    store = _code(STORE)
    assert '"step-answered": stepAnswered,' in store
    assert '"step-writing": stepWriting,' in store
    assert "function stepWriting(" not in store, "the map's rule is spelled twice"
    loaded = re.search(r"function runLoaded\(state, event\) \{(.*?)\n\}", store,
                       re.DOTALL)
    assert loaded is not None
    assert ("writes: readWrites(moved.runs.writes, detail.run.run_id)"
            in loaded.group(1)), loaded.group(1)
    writer = _code(WRITER)
    for road, owner in (("onStepWrite", "row.nodeId"),
                        ("onDocumentWrite", "DOCUMENT_KEY")):
        body = re.search(rf"function {road}\((.*?)\n  \}}", writer, re.DOTALL)
        assert body is not None, road
        mark = f'{{type: "step-answered", runId: asked, nodeId: {owner}}}'
        assert body.group(1).count(mark) == 1, (road, body.group(1))
        assert body.group(1).index(mark) < body.group(1).index(
            "if (asked !== door.chosenRun()) return;"), road


def _sentences(path: Path, name: str) -> dict[str, str]:
    """The string values of ``const NAME = Object.freeze({...})``, whole.

    `tests.test_studio_runs.frozen_pairs` reads one quoted fragment per key;
    a sentence too long for one line is spelled as fragments joined by `+`,
    and this reader joins them back, so what is judged is what a person reads.
    """
    text = _code(path)
    marker = re.search(rf"const {name} = Object\.freeze\(\s*\{{", text)
    assert marker is not None, f"{path.name} declares no object {name}"
    body = _balanced(text, marker.end() - 1, "{", "}")
    return {key: "".join(re.findall(r'"([^"]*)"', value)) for key, value in
            re.findall(r'([A-Za-z_][A-Za-z0-9_]*):((?:\s*"[^"]*"\s*\+?)+)',
                       body)}


def test_no_rung_of_the_ladder_claims_an_executor_this_build_does_not_ship():
    """`policy` is a word the vocabulary carries and nothing serves.

    Both places the ladder is read in words said a policy decides or
    authorizes -- an unsupported label described as an implementation. Each
    now says the executor is not shipped and that the run behaves as propose;
    and the propose rung says nothing can confirm in it, which is
    `runtime.authorize`'s own rule (`confirm` alone).
    """
    meanings = _sentences(FORM, "MODE_MEANINGS")
    # The reader calibrated on a sentence spelled in two fragments.
    assert meanings["propose"] == ("Steps may be proposed, and nothing can "
                                   "confirm one here. Nothing is carried out.")
    notes = _sentences(WORDS, "CONTROL_MODES")
    for name, said in (("MODE_MEANINGS", meanings), ("CONTROL_MODES", notes)):
        assert set(said) == {mode.value for mode in ControlMode}, (name, said)
        assert "no policy executor" in said["policy"], (name, said["policy"])
        assert "as a propose run" in said["policy"], (name, said["policy"])
    assert "Nothing can be authorized in this run" in notes["propose"], notes
