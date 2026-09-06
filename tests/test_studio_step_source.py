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

from tests.test_graph_source import _code

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
STEP = PANEL / "studio-runstep.js"
BOOT = PANEL / "studio.js"
RUNS = PANEL / "studio-runs.js"
#: What a press on a step control MEANS, split off the boot module when that
#: file reached the line cap. The wire stayed behind: this file is handed a
#: `write` and reaches no socket, which is why the door counts next door are
#: unchanged by the split.
WRITER = PANEL / "studio-runwrite.js"
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
        "authorization_refused", "service_refused", "run_terminal"}
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
    marked = door.index('door.dispatch({type: "step-writing", writing: true});')
    assert marked < door.index("door.write(target, asked, row.body,"), door
    # …and cleared from the ONE exit every road shares. It used to be cleared
    # on the refusal arm alone, which left the flag set on the two roads that
    # reach neither arm: a write retired by another write's generation bump,
    # and one never sent because the line was down.
    assert door.rstrip().endswith(
        '}).finally(() => door.dispatch({type: "step-writing", '
        "writing: false}));"), door
    assert door.count('writing: false') == 1, door
    # Both arms end in the read that is what really says what happened.
    assert door.count("door.refreshRun(asked);") == 2, door
    step = _code(STEP)
    assert "shut: submit === null || edit === null || !live || writing" in step
    assert "if (wire.writing) said.push(note(WRITING_NOTE));" in step
    assert "What you have typed here is kept." in step


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
