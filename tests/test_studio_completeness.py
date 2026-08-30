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

from tests.test_studio_canvas import INSPECTOR, PANEL, _code, _text

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
#: argv. `Output budget` left it when the spawn started reading the profile
#: the plan already carried. It is not a field that became supported by being
#: relabelled: `tests/test_command_output_budget.py` drives a real dispatch and
#: reads the byte count off the CommandSpec the runner was handed.
#: `Verifier` left it when a step gained a durable `verifier_role_id`:
#: `TemplateNode` stores it, `GraphTemplate._roles_of` counts it so a binding
#: must assign it, `materialize` freezes it into the plan as
#: `verifier_instance_id`, and `graph_causality.permitted_verifier` spends it --
#: driven end to end by tests/test_command_plan_verifier.py. The positive
#: witness that it did not leave the SCREEN with the label is below.
UNSUPPORTED_FIELDS = (
    "Required input artifacts",
    "Produced artifacts",
    "Handoff mapping",
    "Missing-artifact behaviour",
    "Evidence requirements",
    "Success criteria",
    "Verification failure policy",
    "Edge conditions",
    "Decision routing",
    "Condition",
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
