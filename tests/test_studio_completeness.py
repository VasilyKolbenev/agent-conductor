"""The completeness rule: what the inspector cannot store, and what it now can.

Split out of ``test_studio_canvas.py`` when that module crossed the project's
line cap. The seam is a real circuit rather than a convenient line, and it is
the one that GROWS: every field this product learns to store passes through it
exactly once, in three steps.

    1. while the field has no durable home, it SAYS so in one voice, and the
       set of such fields is `UNSUPPORTED_FIELDS` -- pinned in both directions,
       because a label quietly dropping off the screen is invisible otherwise;
    2. when the field becomes real, its label leaves that register -- and a
       positive witness arrives in its place, holding that it did not leave the
       SCREEN with it. Deleting the control entirely would satisfy the census
       and is exactly what these witnesses exist to refuse;
    3. the control is judged before it writes, in the grammar its Python
       contract already holds it to, and every closed vocabulary it offers is
       read out of the layer that owns it rather than written down here.

What stayed behind in ``test_studio_canvas.py`` is the SHAPE of the two
surfaces -- the module table, the pure-DOM rules, the keyboard roads, the
geometry, the six-section order. That file answers "is this still the same kind
of thing"; this one answers "is every field on it finished".

The helpers and the file constants are imported rather than re-spelled, so both
modules read the same inspector surface: ``INSPECTOR`` is a union of three
files, and a control that moved across one of those seams must stay under every
rule here.
"""
from __future__ import annotations

import re

from tests.test_studio_canvas import INSPECTOR, PANEL, ROOT, _code, _text

#: Every field of the six sections that has no durable home in this build. The
#: list is the report: a field named here SAYS so where it would have been, and
#: a field that stops saying so -- or a new one that quietly appears -- reds.
#: Two names left this register by becoming real rather than by being deleted:
#: `Timeout` and `Retry / attempt bound` are now `timeout_seconds` and
#: `attempt_bound` on the node, spent in `graph_causality` and in
#: `ControlRuntime._hold_budget`, and held by tests/test_command_plan_bounds.py.
#: The register shrinks as fields become real; it must never shrink because a
#: label was quietly dropped, which is what the two-directional check below is.
#: `Purpose / description` left this list when a step gained a durable purpose
#: that the Decisions and Runs screens read and that a dispatching step carries
#: into the frame its harness is handed --
#: `tests/test_command_step_purpose.py` drives that chain to a real child's
#: argv.
#: `Evidence requirements` left it when a step gained a durable
#: `required_evidence`: both node contracts store it, `materialize` freezes it
#: into the plan, `graph_causality.demanded_evidence` reads it back off those
#: frozen bytes, and four layers spend it -- the template refuses a word that
#: would ask for LESS, `ControlRuntime._causal_evidence` records
#: `verification_failed` rather than `succeeded` when a demanding step's
#: verification names nothing checked, and `run_store` makes the same refusal on
#: append and again on raw replay, so a hand-written journal cannot buy the
#: success either. tests/test_command_required_evidence.py and
#: tests/test_command_evidence_demand.py drive the two halves. The positive
#: witness that the label did not leave the SCREEN is below.
#: `Output budget` left it when the spawn started reading the profile
#: the plan already carried. It is not a field that became supported by being
#: relabelled: `tests/test_command_output_budget.py` drives a real dispatch and
#: reads the byte count off the CommandSpec the runner was handed.
#: `Verifier` left it when a step gained a durable `verifier_role_id`:
#: `TemplateNode` stores it, `GraphTemplate._roles_of` counts it so a binding
#: must assign it, `materialize` freezes it into the plan as
#: `verifier_instance_id`, and `graph_causality.permitted_verifier` spends it --
#: driven end to end by tests/test_command_plan_verifier.py. The positive
#: witness that it did not leave the SCREEN with the label is below.
#:
#: THREE MORE LEFT TOGETHER, and they are one fact rather than three:
#: `Required input artifacts`, `Produced artifacts` and `Handoff mapping`. None
#: of them became a field on a workflow step and none of them may -- they were
#: ALREADY durable, as the capability's own reviewed arguments. `artifact_refs`
#: and `target_artifact_refs` are resolved by `artifact_handoff.resolve`, and a
#: step whose input is unavailable is refused without spawning;
#: `result_artifact_ref` is where a step's output is published, and
#: `artifacts._artifact_answers_its_request` holds the document to it at append
#: and again at replay. What was missing was a way to SAY any of it, which is
#: what those three labels were admitting. The mapping is derived rather than
#: stored, and it is honest about the case the shipped starters really have: a
#: reference no step in the document produces, which a run receives from
#: outside. tests/test_command_artifact_flow.py drives one step's product into
#: another step's requirement end to end, through the real transport. The three
#: positive witnesses that none of them left the SCREEN are below.
#:
#: THREE MORE LEFT TOGETHER in the routing slice, and they are one fact as well:
#: `Edge conditions`, `Decision routing` and the edge panel's `Condition`. A
#: connection gained a durable `condition` -- `GraphEdge` stores it,
#: `graph_conditions` owns the eight words and refuses one a source cannot
#: produce, `materialize` freezes it into the plan, and `graph_schedule` opens
#: or closes the road on it. `Decision routing` is the only one of the three
#: that did NOT become a control, and deliberately: a gate's answer routes down
#: whichever road carries that word, so the place to change routing is the road,
#: and a second control would be a second authority over one edge. It became a
#: derived READING instead, which is what the three positive witnesses below
#: hold: two controls that write `set-edge-condition`, and one reading that
#: states where each answer sends the run.
UNSUPPORTED_FIELDS = (
    "Missing-artifact behaviour",
    "Success criteria",
    "Verification failure policy",
)


def test_every_field_with_no_durable_home_says_so_in_one_voice():
    """A control that writes inert data is forbidden; so is one that vanishes.

    One helper writes the sentence, so there is exactly one spelling of it and
    a reader learns the same thing everywhere. The labels are pinned because a
    field quietly dropping off the screen is the failure mode this rule exists
    for, and it is invisible by construction.
    """
    inspector = _code(*INSPECTOR)
    assert inspector.count("not supported by this harness") == 1
    assert inspector.count('"data-unsupported"') == 1
    found = re.findall(r'unsupported\(box, "([^"]+)"', inspector)
    # Held as a set with the length beside it, in both directions: a field that
    # stops saying so goes missing, a new one that quietly appears is unnamed,
    # and one said twice under one label is a duplicate row on screen.
    assert set(found) == set(UNSUPPORTED_FIELDS)
    assert len(found) == len(UNSUPPORTED_FIELDS) == len(set(UNSUPPORTED_FIELDS))


def test_every_edited_word_is_judged_before_it_is_written():
    """A control that posts a body for the server to reject is not validated.

    The grammars are the contract's own: the id pattern is held to
    `contract_values._ID_RE` next door, and the loop bound to the definition's
    own range.
    """
    inspector = _code(*INSPECTOR)
    checks = set(re.findall(r"^  (\w+): \(value\)", re.search(
        r"const CHECKS = Object\.freeze\(\{(.*?)\n\}\);", inspector,
        re.DOTALL).group(1), re.MULTILINE))
    assert checks == {"title", "role_id", "gate_id", "purpose",
                      "verifier_role_id"}
    assert "if (judge()) return;" in inspector
    # The purpose bound is the CONTRACT's, read from it rather than typed here.
    # A window that let somebody type past it would send a save the server
    # refuses, for a reason nothing on the screen explains.
    from conductor.command.graph_definition import MAX_PURPOSE

    held = re.search(r"export const MAX_PURPOSE = (\d+);", inspector)
    assert held and int(held.group(1)) == MAX_PURPOSE, held
    bound = re.search(r"bound\.addEventListener\(\"change\", \(\) => \{(.*?)\n  \}\)",
                      inspector, re.DOTALL).group(1)
    assert "Number.isInteger(value)" in bound
    assert "LOOP_BOUND.min" in bound and "LOOP_BOUND.max" in bound
    assert "return;" in bound.split("commit(")[0]


# -- the output budget: stated, then chosen ----------------------------------


def test_the_window_and_the_spawn_agree_what_an_output_profile_is_worth():
    """Two copies of one table, held equal, because a window may not invent one.

    The inspector states this step's budget in BYTES. Those numbers live in
    Python -- `deep_commands.OUTPUT_LIMIT_BYTES` is what the spawn spends -- so
    a window carrying its own idea would show a person a ceiling the child never
    had. The copy exists because the module table forbids the inspector reaching
    anything that could reach back; what it may not do is drift.
    """
    from conductor.command.adapters.deep_commands import OUTPUT_LIMIT_BYTES

    source = _code(*INSPECTOR)
    literal = re.search(
        r"const OUTPUT_LIMIT_BYTES = Object\.freeze\(\{(.*?)\}\);",
        source, re.DOTALL)
    assert literal, "the inspector no longer names what a profile is worth"
    held = {name: int(value) for name, value in
            re.findall(r"(\w+): (\d+)", literal.group(1))}
    assert held == dict(OUTPUT_LIMIT_BYTES), (held, dict(OUTPUT_LIMIT_BYTES))


def test_the_inspector_lets_the_output_budget_be_chosen_and_still_states_it():
    """A field that leaves the unsupported list must not leave the screen with it.

    This pinned the READ-ONLY shape first: two `context` arms, so a step that
    named a profile and a step that named none both said what bound them.
    Stating a durable field a person cannot reach is the same defect one step
    on -- the release verdict's own example was a field declared, validated,
    stored, shipped in both starters and changeable from nowhere -- so the
    control is pinned beside the statement now, and BOTH halves still are.

    The two arms survive, in their new places: the select shows what is chosen,
    and the `context` line says what it is worth in bytes for a named profile
    and what bounds the step for an unnamed one. Deleting either would satisfy
    the completeness census and leave a person guessing.
    """
    inspector = _code(*INSPECTOR)
    assert "outputBudget(box, form);" in inspector
    body = re.search(r"function outputBudget\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    # Both states still SAID: a schema that declares no profile, and -- in one
    # line with two arms -- a step that names one and a step that does not.
    assert body.count('context(box, "Output budget"') == 2, body
    assert "budgetLabel(named)" in body, body
    assert "names no output limit profile" in body, body
    # And now CHOSEN, through a control the section really mounts.
    assert "budgetSelect(box, form, choices, named);" in body, body
    control = re.search(
        r"function budgetSelect\(box, form, choices, named\) \{(.*?)\n\}",
        inspector, re.DOTALL).group(1)
    assert 'element("select"' in control, control
    assert "editable(control, form)" in control, control
    assert "OUTPUT_LIMIT_FIELD" in control, control
    assert "Output budget" not in re.sub(
        r"function (outputBudget|budgetSelect)\(box, form.*?\n\}", "",
        inspector, flags=re.DOTALL), "the budget is stated in more than one voice"
    # The edit carries the WHOLE map, rebuilt around one key. A change-detector
    # rather than a proof -- browser_tests/test_studio_budget.py is what really
    # counts the siblings -- but it localizes the break to the line that caused
    # it instead of to a reload three assertions later.
    spread = re.search(r"function withArgument\(node, field, chosen\) \{(.*?)\n\}",
                       inspector, re.DOTALL).group(1)
    assert "{...held}" in spread, spread


def test_the_budget_choices_are_the_reviewed_schema_s_own_words():
    """The control offers what the SCHEMA declares, never what this window wrote.

    Three artifacts and one vocabulary, and the chain is what makes the control
    honest: `deep_commands.OUTPUT_LIMIT_PROFILES` is what a dispatch payload is
    really validated against, `command-projection.CAPABILITY_FIELDS` is the
    projection of that schema the Cockpit's own proposal composer is built from,
    and the inspector reads the projection. Pinned here because the Studio is
    what made the middle link load-bearing -- the panel's own source guard holds
    every OTHER enum row in that table and never held this one.

    The anti-literal half is what pays. A control sourcing its options from a
    list written in the inspector would render identically and satisfy every
    rendered assertion ever made about it, so the profile words are asserted
    ABSENT from the inspector's own source: if the only way it can name them is
    to read the projection, then changing the projection is the only way to
    change the control.
    """
    from conductor.command.adapters.deep_commands import OUTPUT_LIMIT_PROFILES

    projection = _text(PANEL / "command-projection.js")
    row = re.search(r'\["output_limit_profile", "enum", \[([^\]]*)\]\]', projection)
    assert row, "the reviewed projection no longer declares the profile enum"
    declared = re.findall(r'"([a-z_]+)"', row.group(1))
    assert set(declared) == set(OUTPUT_LIMIT_PROFILES), (
        declared, OUTPUT_LIMIT_PROFILES)
    inspector = _code(*INSPECTOR)
    # Every word the control may offer has a byte count this build really has,
    # so no choice can reach the screen labelled with a number nobody spends.
    literal = re.search(r"const OUTPUT_LIMIT_BYTES = Object\.freeze\(\{(.*?)\}\);",
                        inspector, re.DOTALL)
    assert literal, "the inspector no longer names what a profile is worth"
    assert set(re.findall(r"(\w+): \d+", literal.group(1))) == set(declared)
    # And it reaches them through the projection and through nothing else.
    assert "CAPABILITY_FIELDS[capability]" in inspector
    for word in declared:
        assert f'"{word}"' not in inspector, (
            f"{word!r} is written into the inspector; the choices must come "
            "from the reviewed projection, not from a list beside the control")


# -- the verifier: stated, and typed rather than picked -----------------------


def test_the_inspector_states_the_verifier_it_stopped_calling_unsupported():
    """A field that leaves the unsupported list must not leave the screen with it.

    Deleting the line would satisfy the completeness census -- `Verifier` is not
    in `UNSUPPORTED_FIELDS` any more -- and leave a person with no way to name
    the role that confirms a step, which is a field the template stores, the
    binding must assign, `materialize` freezes into the plan and the runtime
    spends.

    The SHAPE of the control is asserted as well as its presence, because the
    easy way to get this wrong is a picker: offering only roles some step
    already carries out would refuse the one case this field exists for -- a
    reviewer role no step carries out, which is exactly what a separate reviewer
    is. So it is free text with a datalist beside it, and the offers are the
    union of both kinds of role, the same union `studio-runform.roleNames` reads
    one screen over.
    """
    inspector = _code(*INSPECTOR)
    assert "verifierControl(box, form);" in inspector
    verification = re.search(
        r"export function verificationSection\(form\) \{(.*?)\n\}",
        inspector, re.DOTALL).group(1)
    assert "verifierControl(box, form);" in verification, verification
    body = re.search(r"function verifierControl\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert '"Verifier role", "verifier_role_id"' in body, body
    assert "roleOffers(form)" in body, body
    # Offered and never enforced: the suggestions are a datalist over a text
    # input, so what the control commits is whatever was typed.
    offered = re.search(r"function suggestedField\((.*?)\n\}", inspector,
                        re.DOTALL).group(1)
    assert 'element("datalist"' in offered, offered
    assert "textField(mount, form, label, name, value, help)" in offered, offered
    union = re.search(r"function roleOffers\(form\) \{(.*?)\n\}", inspector,
                      re.DOTALL).group(1)
    assert "node.role_id, node.verifier_role_id" in union, union
    # The contract's pairing rule is said in place, not only met at the save.
    assert "has nothing to verify" in body, body
    # And in one voice: one label, one section.
    assert inspector.count('"Verifier role"') == 1


# -- the evidence requirement: stated, chosen, and only ever a tightening ------


def test_the_inspector_states_the_evidence_requirement_and_lets_it_be_chosen():
    """A field that leaves the unsupported list must not leave the screen with it.

    Deleting the control satisfies the census -- `Evidence requirements` is not
    in `UNSUPPORTED_FIELDS` any more -- and leaves a person with no way to say
    that a step's verification must name WHAT it checked, which is the one
    degree of freedom the evidence contract has left and the only thing a plan
    can honestly tighten about it.

    Both STATES are said and the control is mounted beside them: a step that
    binds no role, which is verified by nobody, and -- in one line with two arms
    -- a step that names a requirement and a step that does not. The section
    really mounts it, so a helper defined and never called cannot pass.
    """
    inspector = _code(*INSPECTOR)
    assert "evidenceRequirement(box, form);" in inspector
    verification = re.search(
        r"export function verificationSection\(form\) \{(.*?)\n\}",
        inspector, re.DOTALL).group(1)
    assert "evidenceRequirement(box, form);" in verification, verification
    body = re.search(r"function evidenceRequirement\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert body.count('context(box, "Evidence requirements"') == 2, body
    assert "nobody verifies it" in body, body
    assert "held to the runtime's own rule" in body, body
    # The control the section mounts, and it writes the NODE field rather than a
    # capability argument: this is a plan word, not a payload key.
    assert '"Evidence requirements", "required_evidence"' in body, body
    assert "REQUIRED_EVIDENCE.map(" in body, body
    # Both directions: an empty option is offered first, so a step that named a
    # requirement can stop naming one. A control that could only add is the
    # one-way door this suite refuses everywhere.
    assert '[{value: "", label:' in body, body
    # And in one voice: one label for the writable row, one section.
    assert inspector.count('"Evidence requirements", "required_evidence"') == 1


def test_the_requirement_the_open_run_follows_is_read_off_its_plan():
    """A durable demand comes from the DEFINITION, never from the projection.

    `run.position` is this run's runtime projection -- an outcome and a phase --
    and `run.planned` is the node of the plan it froze. A window reading the
    demand off the projection would be reading a durable intention out of the
    record of what happened, which is the split
    `graph_definition`/`graph_projection` exists to keep.
    """
    inspector = _code(*INSPECTOR)
    body = re.search(r"function runEvidenceRow\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert "run.planned.required_evidence" in body, body
    assert "run.position" not in body, body
    # Both arms: a run whose plan does not name this step says so rather than
    # reporting "nothing required", which would be a different claim.
    assert "if (!run.planned) {" in body, body
    assert "not name this step" in body, body
    assert body.count('context(box, "Required by the open run"') == 2, body


def test_the_requirement_may_only_ever_ask_for_more_than_the_runtime_does():
    """The choices are the CONTRACT's vocabulary, and it has no word for less.

    The control cannot offer a loosening because the list it maps over is the
    mirror of `graph_values.REQUIRED_EVIDENCE`, held to it by
    `tests/test_studio_canvas.py`. What is pinned here is the other half: every
    word the window can render has a sentence saying what it asks for, so no
    choice can reach the screen as a bare token.
    """
    from conductor.command.graph_values import REQUIRED_EVIDENCE

    inspector = _code(*INSPECTOR)
    demands = re.search(
        r"const EVIDENCE_DEMANDS = Object\.freeze\(\{(.*?)\n\}\);",
        inspector, re.DOTALL)
    assert demands, "the inspector no longer says what a requirement asks for"
    assert set(re.findall(r"^  (\w+):", demands.group(1), re.MULTILINE)) == set(
        REQUIRED_EVIDENCE)
    # The fallback is the shape `budgetLabel` already has: a word this build has
    # no sentence for is NAMED as that, never rendered as `undefined`.
    fallback = re.search(r"function evidenceLabel\(word\) \{(.*?)\n\}",
                         inspector, re.DOTALL).group(1)
    assert "Object.hasOwn(EVIDENCE_DEMANDS, word)" in fallback, fallback
    assert "no sentence for what it requires" in fallback, fallback


# -- the two labels that stayed, and had to stop being evasive -----------------


def test_the_success_criteria_line_says_why_there_is_nothing_left_to_add():
    """The old sentence was true and evasive; the new one is the actual reason.

    "an outcome is reported by the immutable result record" described where an
    outcome is WRITTEN, which is not why a plan may not state a criterion. The
    reason is that every criterion a plan could state is already demanded of
    every step -- verified, by the one adapter the plan makes authoritative,
    over evidence recorded after the work was observed -- so anything a plan
    could add beside it would be weaker than what it is already held to.

    The old wording is asserted GONE rather than merely not asserted present,
    which is the shape the missing-artifact line below already has.
    """
    inspector = _code(*INSPECTOR)
    assert "reported by the immutable result record" not in inspector, (
        "the success-criteria line still says where an outcome is written "
        "instead of why a plan may not state one")
    reason = re.search(r'unsupported\(box, "Success criteria", (.*?)\);',
                       inspector, re.DOTALL).group(1)
    assert "already demands of every step" in reason, reason
    assert "would be weaker" in reason, reason


def test_the_failure_policy_line_says_what_this_build_really_does_instead():
    """Its reason has now been false TWICE, and each time for a good reason.

    First it said "With no declared criteria there is no failure policy for a
    plan to carry" -- and a step can declare an evidence requirement, so the
    reason moved to: nothing in this build computes a next step, so there is no
    choice for a policy to make.

    Then that became false as well. The scheduler landed: an edge may carry a
    condition, `graph_schedule` opens or closes a road on the word a step
    produced, and `on_failed` is one of those words. So a plan CAN now say where
    a failure goes. What it still cannot say is HALT -- stop this whole run,
    including branches no road from this step reaches -- which is a tightening
    and not routing, and needs a durable field of its own.

    A CHANGE DETECTOR on the claim, not a proof of it. Twice now the claim has
    changed legitimately and this test has had to move with it, which is the
    point: what it buys is that the screen's sentence cannot go on asserting
    something the build stopped doing. The old false clause is asserted ABSENT
    for the same reason the first one is.
    """
    inspector = _code(*INSPECTOR)
    assert "With no declared criteria" not in inspector, (
        "the failure-policy line still rests on there being no declared criteria")
    reason = re.search(
        r'unsupported\(box, "Verification failure policy", (.*?)\);',
        inspector, re.DOTALL).group(1)
    assert "walks no connections" not in reason, (
        "the failure-policy line still claims this build walks no connections, "
        "which the schedule made false")
    assert "the schedule walks it" in reason, reason
    assert "HALT" in reason, reason
    assert "verification_failed" in reason, reason


# -- the artifact trio: required, produced, and where each one comes from ------


def test_the_inspector_states_the_required_inputs_and_lets_them_be_edited():
    """A field that leaves the unsupported list must not leave the screen with it.

    Deleting the control satisfies the census -- `Required input artifacts` is
    not in `UNSUPPORTED_FIELDS` any more -- and leaves a person with no way to
    say what a step must be handed, which is a fact the payload stores, the
    plan freezes, `artifact_handoff.resolve` spends, and the transport refuses
    a step for lacking.

    Both STATES are said, and the control is mounted beside them: a schema with
    no artifact input at all, and -- in one line with two arms -- a step that
    names references and a step that does not. The judging half is next door.
    """
    inspector = _code(*INSPECTOR)
    assert "requiredInputs(box, form);" in inspector
    section = re.search(r"export function artifactSection\(form\) \{(.*?)\n\}",
                        inspector, re.DOTALL).group(1)
    assert "requiredInputs(box, form);" in section, section
    body = re.search(r"function requiredInputs\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert body.count('context(box, "Required input artifacts"') == 2, body
    assert "declares no artifact input" in body, body
    assert "names no input artifact" in body, body
    # The two directions of the control the section really mounts. A list that
    # could only be added to is the one-way door this suite refuses everywhere.
    assert "inputRows(box, form, held, found.name);" in body, body
    assert "inputAdder(box, form, held, found.name);" in body, body
    # The schema's own asymmetry, stated rather than flattened: one of the two
    # kinds may be empty and the other may not, and the cost is said in place.
    assert "found.kind === NON_EMPTY" in body, body
    assert "no run of this workflow can be opened" in body, body
    assert "admits an EMPTY list" in body, body


def test_every_required_input_is_judged_before_it_reaches_the_draft():
    """The grammar and the duplicate, neither of them invented in this window.

    The grammar is `contract_values._ID_RE`, held to it next door. The
    duplicate is `latest_artifacts`' own rule -- it resolves through
    `_unique_ids`, so a list asking for one name twice is refused at the spawn,
    and a control that let one be typed would write a draft that saves and a
    run that will not resolve.

    Both refusals RETURN before the commit, so a rejected reference cannot
    reach the draft on its way to being reported; and both roads that do write
    carry the whole argument map, rebuilt around one key.
    """
    inspector = _code(*INSPECTOR)
    drop = re.search(r"function inputRows\(box, form, held, name\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert "held.filter((_, index) => index !== at)" in drop, drop
    add = re.search(r"function inputAdder\(box, form, held, name\) \{(.*?)\n\}",
                    inspector, re.DOTALL).group(1)
    assert "ID_PATTERN.test(input.value)" in add, add
    assert "held.includes(input.value)" in add, add
    assert "held.concat([input.value])" in add, add
    assert add.count("return;") == 2, add
    assert add.index("commit(form,") > add.rindex("return;"), add
    for source in (drop, add):
        assert 'commit(form, "arguments",' in source, source
        assert "withArgument(form.node, name," in source, source


def test_the_inspector_states_what_a_step_publishes_and_what_clearing_costs():
    """The other half of the pair, and the half with a real asymmetry in it.

    A step that carries work out publishes NO artifact -- its evidence is a
    digest of the change it made -- and a step that checks work publishes one.
    That difference is the reviewed schema's, so the control is drawn from a
    LOOKUP and the absent case is stated rather than left blank. Both arms are
    pinned, because the easy way to get this wrong is to draw the control
    everywhere and let a person name an output that nothing would ever publish.

    Clearing is allowed and its cost is said in place: a step of that kind
    naming no result artifact is refused when it is reached, with no task
    spawned. The FACT is what is pinned, not the sentence -- the transport's
    own wording is free to be rewritten, and
    `tests/test_command_artifact_flow.py` is what holds the behaviour.
    """
    inspector = _code(*INSPECTOR)
    assert "producedArtifacts(box, form);" in inspector
    body = re.search(r"function producedArtifacts\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert body.count('context(box, "Produced artifacts"') == 2, body
    assert "declares no result artifact reference" in body, body
    assert "names no result artifact" in body, body
    # The absent arm says what stands in its place, so a reader of such a step
    # learns what the run WILL leave rather than that there is nothing.
    assert "digests" in body and "work directory" in body, body
    assert "verification evidence" in body, body
    # The clearing cost, stated beside the control rather than met at a run.
    assert "no task is spawned" in body, body
    # The control itself, judged before it writes and writing the whole map.
    assert "producedControl(box, form, found.name, named);" in body, body
    control = re.search(
        r"function producedControl\(box, form, name, named\) \{(.*?)\n\}",
        inspector, re.DOTALL).group(1)
    assert "ID_PATTERN.test(control.value)" in control, control
    assert 'control.value === ""' in control, control
    assert "if (judge()) return;" in control, control
    assert 'commit(form, "arguments",' in control, control
    assert "withArgument(form.node, name, control.value)" in control, control


def test_the_handoff_mapping_is_derived_from_the_document_and_names_producers():
    """Where each requirement is met, computed rather than stored.

    Nothing durable holds a step-to-step artifact mapping and nothing should:
    it is the JOIN of two facts the document already carries, so storing it
    would be a third copy that can disagree with either. It is derived on every
    render out of `form.nodes`, the way `roleOffers` derives the roles this
    document names.

    Two arms and the second one is the one the shipped starters really need:
    `dalio-v2` produces four of its five references and receives
    `artifact-brief` from outside, and `dalio-v1` produces none of them at all.
    A mapping that could only say "produced by X" would be silent about every
    real external input, which is exactly the case a person needs told.

    The producing FIELD is looked up per node from that node's own capability.
    A walk that assumed one field name would find no producer on a document
    that mixes kinds of step -- and would report every reference as external,
    which reads as correct and is not.
    """
    inspector = _code(*INSPECTOR)
    assert "handoffMapping(box, form);" in inspector
    body = re.search(r"function handoffMapping\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert "producersOf(form.nodes, ref)" in body, body
    assert "produced by" in body, body
    assert "no step in this workflow produces it" in body, body
    assert "through the artifacts route" in body, body
    # The empty case is a third answer and not the external sentence: a step
    # that requires nothing is not a step whose requirement is unmet.
    assert 'context(box, "Handoff mapping"' in body, body
    assert "this step requires no artifact" in body, body
    producers = re.search(r"function producersOf\(nodes, ref\) \{(.*?)\n\}",
                          inspector, re.DOTALL).group(1)
    # Compared reference against reference, through the lookup, per node.
    assert "artifactField(node.capability, OUTPUT_KINDS)" in producers, producers
    assert "refOf(node, declared.name) === ref" in producers, producers


def test_the_missing_artifact_line_says_what_this_build_really_does():
    """The one label of the four that stayed -- and it had to stop lying.

    Its reason was "With no declared artifact requirement there is no
    missing-artifact case for a policy to answer", which was true while nothing
    could declare one and became false the moment the control above shipped.

    What is unsupported is the POLICY, not the behaviour: the behaviour is
    fixed and fail-closed, and it is what `artifact_transport` really does on
    both roads -- a dispatch whose input will not resolve and a review whose
    input will not resolve each answer `failed` with no task spawned. So the
    line now states the behaviour and names the absent field, and the old
    sentence is asserted GONE rather than merely not asserted present.
    """
    inspector = _code(*INSPECTOR)
    reason = re.search(
        r'unsupported\(box, "Missing-artifact behaviour", (.*?)\);',
        inspector, re.DOTALL).group(1)
    assert "no missing-artifact case" not in inspector, (
        "the missing-artifact line still says there is no such case")
    assert "fail-closed" in reason, reason
    assert "no task is spawned" in reason, reason
    assert "no per-step policy field" in reason, reason
    # A CHANGE DETECTOR on the two roads this line describes, not a proof of
    # them: the transport's own wording is free to be rewritten, and what
    # really holds the behaviour is
    # tests/test_command_artifact_dispatch.py, tests/test_command_claude_review.py
    # and the negative arm of tests/test_command_artifact_flow.py, each of
    # which drives a real transport and counts the spawns. What this adds is
    # that the screen's claim breaks HERE, beside the sentence making it,
    # rather than in a browser three modules away.
    transport = _text(
        ROOT / "src" / "conductor" / "command" / "adapters"
        / "artifact_transport.py")
    assert transport.count(
        "input was unavailable, so no task was spawned") == 2, (
        "the fail-closed input roads this line describes are no longer two")


def test_a_run_s_own_artifacts_are_joined_to_the_step_that_produced_them():
    """The runtime half, and it is a join no single record can answer.

    An `ArtifactDocument` names its source ACTION; an `ActionRequest` names the
    NODE it was bound to. So attributing an artifact to a step needs both rows,
    and a build that read either alone would either show a run's every artifact
    under every step or show none at all.

    The projection is what the frame hands over -- three facts and no road back
    to the records -- so no control below it can grow a second reading of the
    journal, or reach an artifact's CONTENT. The Runs screen shows the same
    three facts and no more, and that is deliberate.
    """
    inspector = _code(*INSPECTOR)
    join = re.search(r"function producedBy\(detail, nodeId\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert 'row.record_type !== "action_request"' in join, join
    assert 'row.record_type !== "artifact"' in join, join
    assert "boundTo.set(record.action_id, record.node_id)" in join, join
    assert "boundTo.get(record.source_action_id) !== nodeId" in join, join
    # Three facts carried, and the content is not among them.
    carried = set(re.findall(r"record\.(\w+)", join))
    assert carried == {"action_id", "node_id", "source_action_id",
                       "artifact_id", "artifact_ref", "media_type"}, carried
    assert "content" not in join, join
    # It reaches the section through `runContext`, and the section states both
    # arms: a step whose actions produced artifacts, and one whose did not.
    assert "products: producedBy(detail, nodeId)," in inspector
    body = re.search(r"function runProducts\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert "rows(run.products)" in body, body
    assert body.count('context(box, "Produced in this run"') == 2, body
    assert "was published by an action of this step" in body, body
    assert "row.artifactRef" in body and "row.mediaType" in body, body


# -- the three routing labels left the register, and not the screen -----------


def test_a_connection_offers_the_words_its_own_source_can_produce():
    """`Edge conditions` became a control, one per road out of the step.

    The words offered are the family the SOURCE's kind can produce, read from
    the vocabulary rather than typed beside the control -- and a step that
    carries out no work is offered none at all, because the contract refuses a
    condition on its roads and a select whose every use is refused on save is
    worse than no select.
    """
    inspector = _code(*INSPECTOR)
    control = re.search(r"function conditionControl\(form, edge\) \{(.*?)\n\}",
                        inspector, re.DOTALL).group(1)
    assert "conditionWords(form.node)" in control, control
    assert "carries out no work" in control, control
    assert 'element("select"' in control, control
    assert 'type: "set-edge-condition"' in control, control
    assert "editable(control, form)" in control, control
    words = re.search(r"function conditionWords\(node\) \{(.*?)\n\}",
                      inspector, re.DOTALL).group(1)
    assert 'node.kind === "task" && !node.capability' in words, words
    assert "CONDITIONS_BY_KIND[node.kind]" in words, words


def test_the_edge_panel_offers_that_same_control_and_not_a_second_one():
    """`Condition` became the SAME select, exported rather than rebuilt.

    Two surfaces building one control from two copies of one vocabulary is how
    they come to offer different words for one road.
    """
    inspector = _code(*INSPECTOR)
    assert "edgeConditionRow(box, form, parts[0], parts[1]);" in inspector
    body = re.search(
        r"export function edgeConditionRow\(box, form, fromId, toId\) \{(.*?)\n\}",
        inspector, re.DOTALL).group(1)
    assert "conditionWords(source)" in body, body
    assert 'type: "set-edge-condition"' in body, body
    assert "editable(control, form)" in body, body
    # A road this drawing does not carry is SAID, never offered a control.
    assert "does not carry that road" in body, body


def test_decision_routing_became_a_reading_and_not_a_second_control():
    """It states where each answer sends the run, off the roads already drawn.

    A control here would be a second authority over one edge. The reading is
    derived from the node's own out-edges, and the three cases a person can
    actually be in are each said: a gate that routes, a gate whose every answer
    opens the same step, and a step that is not a gate at all.
    """
    inspector = _code(*INSPECTOR)
    body = re.search(r"function decisionRouting\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert 'form.node.kind !== "gate"' in body, body
    assert "only a gate's answer routes" in body, body
    assert "every answer opens" in body, body
    assert 'typeof edge.condition === "string"' in body, body
    # Read-only: it writes no edit of any kind.
    assert "onEdit" not in body, body
    assert "decisionRouting(box, form);" in inspector


def test_a_blocked_join_says_that_ALL_incoming_roads_are_required():
    """Joins are AND-only, and the screen may not imply otherwise.

    "Waiting for a predecessor" reads as ANY. A person told that would expect
    the step to start as soon as one branch arrived, and would read the plan as
    doing something it never does.
    """
    runs = _code(PANEL / "studio-runs.js")
    sentence = re.search(r'const ALL_ROADS = "([^"]+)"', runs)
    assert sentence, "the Runs screen no longer states the join rule"
    assert sentence.group(1).startswith("ALL incoming roads must open")
    body = re.search(r"function planStanding\(item, standing\) \{(.*?)\n\}",
                     runs, re.DOTALL).group(1)
    assert "note(ALL_ROADS)" in body, body
    assert "waiting for a predecessor" not in runs.lower()


def test_the_plan_word_is_never_drawn_as_a_success():
    """`complete` says the plan has nothing left to open, never that it worked.

    A run that exhausted every retry and a run that was approved reach the same
    word, so the chip is the neutral channel and the two facts that tell them
    apart are stated beside it.
    """
    runs = _code(PANEL / "studio-runs.js")
    body = re.search(r"function planWord\(graph\) \{(.*?)\n\}",
                     runs, re.DOTALL).group(1)
    assert 'chip("none", word)' in body, body
    assert 'chip("pass"' not in body, body
    assert "bound reached" in body, body
    assert "Last gate answer" in body and "Last outcome" in body, body
    assert "does NOT mean the run " in runs
