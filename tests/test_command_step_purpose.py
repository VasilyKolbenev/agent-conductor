"""A step's purpose: from the drawing, into the plan, into the child's frame.

The mandate asks for `purpose/description` to be a real editable field, and the
owner ruled how: for a task it is *bounded, explicitly-marked project-authored
context inside a code-owned task frame -- not argv and not a privileged
instruction*; for a gate or a loop it is read by the surfaces a person looks at.

That makes it the only piece of prose a workflow author writes that reaches a
vendor binary, so the chain is held end to end here:

    TemplateNode.purpose -> settled_purpose -> materialize
      -> GraphNode.purpose            (every step, for the Inspector/Decisions)
      -> arguments["step_purpose"]    (only a step that carries something out)
      -> DeepDispatchArgs/DeepReviewArgs, omittable
      -> the code-owned frame `_task_text` builds
      -> the argv or stdin a real child is handed

Three properties fail in different ways and are therefore held separately:

- **it is bounded, single-line and NUL-free.** Not tidiness: an unbounded
  multi-line value in that frame stops being context and starts being an
  instruction. Refused by the plan contract before freezing, and again at the
  argument door, because an adapter driven with a hand-made request reaches no
  plan;
- **absent stays absent.** Both shipped starters name no purpose, so their
  revision digests must not move and a step without one must be handed exactly
  the frame it was handed before this field existed;
- **the plan is the authority.** `graph_causality` refuses any proposal whose
  arguments are not byte-identical to the node's payload, so a purpose the plan
  did not author cannot be smuggled into a child by whoever composes a proposal.
  That witness lives in `tests/test_command_graph_binding.py`, beside the rule.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.deep_commands import DeepDispatchArgs
from conductor.command.adapters.deep_contracts import (
    MAX_STEP_PURPOSE,
    OMITTED,
    DeepContractError,
)
from conductor.command.contracts import ContractError
from conductor.command.graph_definition import MAX_PURPOSE, GraphNode, settled_purpose
from conductor.command.graph_template import (
    GraphTemplate,
    RunBinding,
    TemplateNode,
    load_template,
    materialize,
)

from tests.test_command_kimi_transport import (
    INSTRUCTION_BODY,
    NOW,
    _Ids,
    _RecordingRunner,
    _executable,
    a_request,
    run_once,
)

SOLO = {"instances": [{"id": "solo", "adapter": "claude-code"}]}
MADE = {"graph_id": "graph-run", "run_id": "run-001",
        "created_at": "2026-08-30T10:00:00Z"}
PURPOSE = "Frame the goal before anything is built."
#: Every shape a purpose may not take, and the one property each one protects.
#: A NUL and a line break are refused because this value is interpolated into a
#: frame handed to a vendor binary; a too-long one because that frame has to
#: stay a frame.
#: The three shapes that would let a purpose stop being one line of
#: context inside a frame handed to a vendor binary.
BAD_TEXT = ["a\nb", "a\rb", "a\x00b"]
#: Those three, plus the two shapes that are not text at all.
BAD = BAD_TEXT + ["x" * (MAX_PURPOSE + 1), 5, b"bytes"]


# -- the grammar, and the two spellings of it --------------------------------


@pytest.mark.parametrize("bad", BAD)
def test_a_purpose_that_could_stop_being_context_is_refused(bad):
    with pytest.raises(ContractError):
        settled_purpose(bad)


def test_the_plan_and_the_argument_door_refuse_the_same_purposes():
    """Two spellings, pinned equal in BOTH directions.

    They are two because `tests/test_command_deep_contracts.py` fixes the
    reviewed import surface of the deep value modules by name, and a contract
    module is not on it -- the same reason `EFFECTING_CAPABILITIES` is spelled
    twice. What that costs is exactly this test: the alternative to one import
    is two doors that can come to disagree, and nothing noticing.
    """
    assert MAX_STEP_PURPOSE == MAX_PURPOSE

    def carried(value):
        return DeepDispatchArgs(
            work_item_id="work-001", instruction_ref="instr-001",
            profile="implement", artifact_refs=[],
            output_limit_profile="normal", step_purpose=value)

    for bad in BAD:
        with pytest.raises(ContractError):
            settled_purpose(bad)
        with pytest.raises(DeepContractError):
            carried(bad)
    # And both admit the same good one, at the boundary length.
    at_cap = "x" * MAX_PURPOSE
    assert settled_purpose(at_cap) == at_cap
    assert carried(at_cap).step_purpose == at_cap


@pytest.mark.parametrize("blank", [None, "", "   ", "\t"])
def test_saying_nothing_and_saying_whitespace_are_one_answer(blank):
    """Absent has ONE spelling, or a digest moves for a value nobody typed."""
    assert settled_purpose(blank) is None
    if blank is not None:
        assert DeepDispatchArgs(
            work_item_id="work-001", instruction_ref="instr-001",
            profile="implement", artifact_refs=[],
            output_limit_profile="normal", step_purpose=blank
        ).step_purpose is OMITTED


def test_a_purpose_is_trimmed_and_round_trips_through_the_document():
    node = TemplateNode(node_id="goal", kind="task", title="Set the goal",
                        resources=(), purpose=f"  {PURPOSE}  ")
    assert node.purpose == PURPOSE
    assert node.as_dict()["purpose"] == PURPOSE
    assert TemplateNode.from_dict(node.as_dict()) == node
    plain = TemplateNode(node_id="goal", kind="task", title="Set the goal",
                         resources=())
    assert plain.purpose is None and "purpose" not in plain.as_dict()


# -- materialization: who gets it, and who does not --------------------------


def _with_purposes(starter: str = "dalio-v2") -> GraphTemplate:
    document = load_template(starter).as_dict()
    for node in document["nodes"]:
        node["purpose"] = f"Why {node['node_id']} exists."
    return GraphTemplate.from_dict(document)


def _materialized(template: GraphTemplate):
    binding = RunBinding(assignments={role: "solo" for role in template.roles})
    return materialize(template, binding, SOLO, **MADE)


def test_every_step_carries_its_purpose_into_the_runs_frozen_plan():
    """The Decisions, Runs and Inspector surfaces all read one frozen sentence."""
    definition = _materialized(_with_purposes())

    assert [node.purpose for node in definition.nodes] == [
        f"Why {node.node_id} exists." for node in definition.nodes]
    # And it survives the document's own spelling, which is what a replay reads.
    again = definition.from_dict(definition.as_dict())
    assert [node.purpose for node in again.nodes] == [
        node.purpose for node in definition.nodes]


def test_only_a_step_that_carries_something_out_carries_it_into_its_payload():
    """A gate and a loop reach no child, so nothing is added to nothing.

    Putting it in the payload of a step with no capability would be inventing a
    capability payload for a step that has none -- and `graph_causality` would
    then demand that payload of a proposal no gate can ever have.
    """
    definition = _materialized(_with_purposes())

    for node in definition.nodes:
        carried = node.payload().get("step_purpose")
        if node.capability is None:
            assert carried is None, node.node_id
            assert node.purpose is not None, node.node_id
        else:
            assert carried == node.purpose, node.node_id


def test_a_template_that_names_no_purpose_materializes_byte_for_byte_as_before():
    """The backward-compatibility measurement.

    Both shipped starters predate this field. If `as_dict` had started writing
    it, or `materialize` had started injecting one, every frozen revision digest
    in this suite would move -- and a frozen byte pin is the one thing this
    build may never break to add a feature.
    """
    for starter in ("dalio-v1", "dalio-v2"):
        template = load_template(starter)
        assert all(node.purpose is None for node in template.nodes)
        assert all("purpose" not in node for node in template.as_dict()["nodes"])
        definition = _materialized(template)
        assert all(node.purpose is None for node in definition.nodes)
        assert all("step_purpose" not in node.payload()
                   for node in definition.nodes)


def test_a_purpose_the_plan_would_refuse_never_reaches_a_definition():
    """The template proves itself by materializing, so one door judges both."""
    document = load_template("dalio-v2").as_dict()
    document["nodes"][0]["purpose"] = "line one\nline two"
    # `ContractError`, not `TemplateError`: the template calls the DEFINITION's
    # grammar and lets its refusal through unchanged, exactly as it does for
    # `settled_bounds`. One rule, one message, wherever it is broken.
    with pytest.raises(ContractError):
        GraphTemplate.from_dict(document)
    with pytest.raises(ContractError):
        GraphNode(node_id="n", kind="task", title="T",
                  purpose="x" * (MAX_PURPOSE + 1))


# -- the frame a child is actually handed ------------------------------------


def _task_text(tmp_path, **arguments) -> str:
    """Drive a real dispatch and return the task text the child was handed.

    Read off the spec the runner was given, because that is where the whole
    command exists: Kimi takes its task on argv, so the text is argv[4] of the
    task spawn -- the version probe is spawn 0.
    """
    from conductor.command.adapters.kimi_code import (
        INSTRUCTION_DIR, KimiCodeAdapter, kimi_pin)

    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / INSTRUCTION_DIR).mkdir()
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    runner = _RecordingRunner(root)
    adapter = KimiCodeAdapter(
        kimi_pin(str(exe)), runner, root=root, clock=lambda: NOW, ids=_Ids())
    body = {"work_item_id": "work-001", "instruction_ref": "instr-001",
            "profile": "implement", "artifact_refs": [],
            "output_limit_profile": "normal"}
    body.update(arguments)
    run_once(adapter, a_request(arguments=body))
    return runner.specs[1].argv[4]


def test_the_plans_words_reach_the_child_labelled_as_the_plans_words(tmp_path):
    """It is context, and the frame says whose context it is.

    The label is the whole of the owner's ruling: everything else in that frame
    is a code-owned identifier the request validated, and an unmarked sentence
    beside those reads as this build's own instruction rather than as something
    a project wrote.
    """
    said = _task_text(tmp_path, step_purpose=PURPOSE)

    assert f"the workflow says this step's purpose is: {PURPOSE}." in said
    # Before the instruction, never after it: the ordering that keeps an
    # instruction out of a flag position keeps this out of one too.
    assert said.index("purpose is") < said.index("instruction instr-001 reads")
    assert INSTRUCTION_BODY in said


def test_a_step_with_no_purpose_is_handed_the_frame_it_always_was(tmp_path):
    """The over-correction control, and it is measured as a byte difference.

    Two dispatches, identical but for the field, and the ONLY difference in the
    text is the clause. A frame that gained a label, an empty sentence or a
    stray space for a step that named nothing would be a change to every task
    this build has ever sent.
    """
    without = _task_text(tmp_path / "a")
    with_one = _task_text(tmp_path / "b", step_purpose=PURPOSE)

    assert "purpose" not in without, without
    assert with_one.replace(
        f" the workflow says this step's purpose is: {PURPOSE}.", "") == without


def test_a_purpose_too_long_for_the_frame_never_reaches_a_child(tmp_path):
    """The argument door is the second lock, and this is the road it locks.

    In production `graph_causality` has already refused a payload the plan did
    not author, so this door is shut twice. It is shut here anyway because an
    adapter driven with a hand-made request -- which is what this test is --
    reaches no plan and no causality check at all.
    """
    from conductor.command.adapters.kimi_code import KimiCodeError

    # The refusal arrives as the PROVIDER's error rather than as the argument
    # door's: `_dispatch_args` catches whatever the closed schema raised and
    # restates it, deliberately, so no untrusted body's exception graph travels
    # onward. What matters is that it is refused before any child exists.
    for at, bad in enumerate([chr(120) * (MAX_STEP_PURPOSE + 1)] + BAD_TEXT):
        with pytest.raises(KimiCodeError, match="closed deep dispatch schema"):
            _task_text(tmp_path / f"case-{at}", step_purpose=bad)
