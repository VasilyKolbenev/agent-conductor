"""The demo's command-side story: what it writes, and that the demo writes it.

`conduct demo` served a Studio with nothing in it. The packaged fixture is
Protocol v1 and the front door reads the command surface, so a person meeting
this product for the first time met an empty Overview, an empty workflow list
and an empty run list over a directory that held the whole demonstration.

Two claims are made here and they are different claims:

- `demo_scenario.build` writes a story that satisfies the product's OWN durable
  rules -- read back through `RunStore.read`, which re-validates every causal
  relation from the bytes on disk rather than trusting what was appended;
- `conduct demo` calls it. That second one is the regression: the builder can be
  perfect and the front door still empty if the command does not run it, which
  is exactly the shape the finding had.

Nothing here asserts against the builder's own return value where a durable
read can answer instead. `build` reporting "I wrote a run" is the claim under
test, not the evidence for it.
"""
from __future__ import annotations
from tests.human_situation_samples import READ_AT

from pathlib import Path

import pytest

from conductor import demo
from conductor.command import demo_scenario
from conductor.command.graph_projection import graph_payload
from conductor.command.graph_schedule import schedule
from conductor.command.run_store import RunStore
from conductor.command.template_store import TemplateStore

from tests.test_studio_wiring import _frozen_list

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: The five records the Runs screen draws as a progression, read out of the
#: window that draws them. Listed again here it would be a second opinion; read
#: from the source it is the same list, so a build that renames a step moves
#: this test with it and a build that stops writing one reds.
#: Declared in `studio-runwords.js` since `studio-runs.js` crossed the line cap
#: -- the screen re-exports it, but this reads the DECLARATION so it is still
#: one list read from its one owner rather than from a re-export that could
#: outlive it.
TIMELINE_STEPS = tuple(_frozen_list(
    (PANEL / "studio-runwords.js").read_text(encoding="utf-8"),
    "TIMELINE_STEPS"))


@pytest.fixture
def built(tmp_path):
    """The story, written into a real project, and replayed back off disk."""
    demo.materialize(tmp_path)
    named = demo.populate(tmp_path)
    return tmp_path, named


def _read(root):
    return RunStore(root).read(demo_scenario.RUN_ID)


# -- the five things the front door has to be able to show -------------------


def test_the_demo_project_holds_a_workflow_with_a_published_revision(built):
    root, _named = built
    templates = TemplateStore(root)

    assert templates.revisions(demo_scenario.WORKFLOW_ID) == (
        demo_scenario.REVISION,)
    published = templates.load(
        demo_scenario.WORKFLOW_ID, demo_scenario.REVISION)
    assert published.title == "Release review"
    assert published.nodes, "a published revision with no steps shows nothing"


def test_the_demo_run_replays_clean_off_its_own_durable_bytes(built):
    """`read` re-validates every relation, so a clean replay is the whole claim.

    A journal that only survived `append` would be one this process happened to
    write in an order nothing later checks; this is the reader that a restart,
    a second process and the Runs screen all use.
    """
    root, _named = built

    recovered = _read(root)

    assert recovered.warnings == ()
    assert recovered.envelope.run_id == demo_scenario.RUN_ID


def test_the_run_records_which_plan_it_followed_where_nothing_can_move_it(built):
    """The workflow identity is INSIDE the digested configuration.

    So the demo also demonstrates the property: replay re-digests the config and
    would refuse a tampered reference, and no later revision can change what
    this run followed.
    """
    from conductor.command.contracts import frozen_config_workflow

    root, _named = built

    recovered = _read(root)

    assert frozen_config_workflow(recovered.config) == (
        demo_scenario.WORKFLOW_ID, demo_scenario.REVISION)


def test_the_carried_step_writes_every_step_the_timeline_draws(built):
    """The five records `studio-runs.js` draws, in the order it draws them.

    Read out of the panel's own vocabulary rather than listed again here: a
    build that renamed a step would move this test with it, and a build that
    stopped writing one would red.
    """
    root, _named = built

    recovered = _read(root)
    drawn = []
    for row in recovered.records:
        if row.kind == "attempt_event":
            drawn.append(row.value.phase)
        elif row.kind in TIMELINE_STEPS:
            drawn.append(row.kind)

    assert tuple(drawn) == TIMELINE_STEPS


def test_the_demo_shows_one_answered_gate_and_one_still_waiting(built):
    """Both halves of a human decision, because they look nothing alike.

    A demo with only an answered gate never shows a person what is being asked
    of them; one with only a waiting gate never shows what an answer looks like
    afterwards. Waiting is not a record -- it is a gate no receipt has answered
    -- so it is read the way the product reads it, off the projection.
    """
    root, _named = built

    runtime = graph_payload(_read(root), computed_at=READ_AT)["runtime"]
    gates = {node["node_id"]: node["decision"]
             for node in runtime["nodes"] if "decision" in node}

    assert sorted(gates.values()) == ["idle", "satisfied"]


def test_the_carried_step_ends_verified_with_its_evidence(built):
    """`succeeded` is the one outcome that needs evidence, so the demo has it.

    A receipt that said succeeded with nothing behind it would demonstrate the
    exact confusion this product exists to remove -- an exit code standing in
    for proof.
    """
    root, _named = built

    recovered = _read(root)
    receipt = next(row.value for row in recovered.records
                   if row.kind == "action_result")
    evidence = {row.value.evidence_id: row.value for row in recovered.records
                if row.kind == "evidence"}

    assert receipt.outcome == "succeeded"
    assert receipt.evidence_refs, "a succeeded receipt with no evidence"
    for evidence_id in receipt.evidence_refs:
        assert evidence[evidence_id].verification == "verified"


def test_the_demo_run_belongs_to_a_named_task_and_a_second_task_is_not_run_yet(built):
    """The Runs header names a task only when the run froze one, so the demo freezes one.

    Read back through the task store and the frozen binding, the two readers the
    run route joins: a title written anywhere else would be a screen fixture.
    """
    from conductor.command.studio_routes import run_ids
    from conductor.command.task_contracts import frozen_config_task
    from conductor.command.task_store import TaskStore

    root, named = built
    tasks = TaskStore(root)
    binding = frozen_config_task(_read(root).config)
    bound = {frozen_config_task(RunStore(root).read(run_id).config).task_id
             for run_id in run_ids(RunStore(root))}

    assert set(tasks.tasks()) == {demo_scenario.TASK_ID, demo_scenario.SECOND_TASK_ID}
    assert (binding.task_id, binding.work_scope) == (demo_scenario.TASK_ID,) * 2
    assert tasks.read(binding.task_id).title == demo_scenario.TASK_TITLE
    assert named["task_id"] == demo_scenario.TASK_ID
    assert bound == {demo_scenario.TASK_ID}


def test_the_demo_roles_are_carried_by_three_participants_on_three_providers(built):
    root, _named = built
    recovered = _read(root)
    definition = next(row.value for row in recovered.records
                      if row.kind == "graph_definition")
    instances = {row["id"]: row["adapter"] for row in recovered.config["instances"]}

    assert set(instances) == set(demo_scenario.PARTICIPANTS)
    assert len(set(instances.values())) == 3
    assert {node.instance_id for node in definition.nodes
            if node.capability} == set(demo_scenario.PARTICIPANTS)


#: What the demo's journal holds, in order. Pinned exactly rather than by
#: membership: the calibration below is that the SCHEDULER did not change, and
#: a journal that grew or lost a record would be a different measurement
#: wearing the same assertion.
DEMO_KINDS = (
    "graph_definition", "decision", "action_proposal", "action_request",
    "attempt_event", "attempt_event", "evidence", "action_result")


def test_the_demo_journal_still_settles_the_gate_a_receipt_alone_answered(
        built):
    """The calibration for the decision doors: the SCHEDULER did not change.

    `_hold_gate_is_reached` refuses a decision for a gate whose roads are not
    all open -- at the LIVE door only. A gate still settles from its own
    receipts alone, which is what lets a receipt appended straight into a
    journal go on answering it: this demo writes exactly such a receipt,
    through `RunStore.append`, while `goal`, `identify`, `diagnose` and
    `design` have never run.

    So this is the two-sided half of that door. If a durable or scheduler-level
    rule had been written instead, `confirm-gate` here would read `blocked`,
    `do` would never have been reachable, and the demo a person meets first
    would show a gate answered by a receipt the plan says is impossible.
    """
    root, _named = built

    recovered = _read(root)
    definition = next(row.value for row in recovered.records
                      if row.kind == "graph_definition")
    computed = schedule(definition,
                        tuple(row.value for row in recovered.records))
    runtime = graph_payload(recovered, computed_at=READ_AT)["runtime"]

    assert recovered.warnings == ()
    assert tuple(row.kind for row in recovered.records) == DEMO_KINDS
    assert {node["node_id"]: node["decision"]
            for node in runtime["nodes"] if "decision" in node} == {
        "confirm-gate": "satisfied", "result-gate": "idle"}
    assert computed.state_of("confirm-gate") == "settled"
    assert computed.state_of("do") == "settled"
    assert computed.state_of("result-gate") == "runnable"
    assert computed.run_state == "open"


# -- the regression: the command has to actually call it ---------------------


def test_conduct_demo_writes_the_story_and_not_only_the_fixture(
        tmp_path, monkeypatch):
    """The finding itself: a perfect builder nothing calls is an empty demo.

    `_cmd_demo` is driven for real -- its own temp directory, its own
    materialize, its own populate -- and stopped at the serve. What is then
    asserted is the DIRECTORY it built, because that is what the front door
    would have read.
    """
    from conductor import __main__ as cli

    served: dict = {}

    def stop_at_the_socket(root, port):
        served.update(root=root, port=port)
        return 0

    monkeypatch.setattr(cli, "_serve", stop_at_the_socket)

    assert cli.main(["demo", "--port", "0"]) == 0

    root = served["root"]
    assert TemplateStore(root).revisions(demo_scenario.WORKFLOW_ID) == (
        demo_scenario.REVISION,)
    assert RunStore(root).read(demo_scenario.RUN_ID).warnings == ()
    # And the Protocol v1 half is still there beside it.
    assert (root / "conductor" / "map.toml").is_file()


def test_a_demo_that_cannot_build_its_story_refuses_instead_of_serving(
        tmp_path, monkeypatch, capsys):
    """The empty front door must never be reachable again by falling back.

    A `populate` that failed and was swallowed would serve exactly the demo
    this finding was about, and nothing on screen would say why.
    """
    from conductor import __main__ as cli
    from conductor.command.run_store import StoreError

    def refuse(_root):
        raise StoreError("the story is no longer one the rules admit")

    monkeypatch.setattr(demo, "populate", refuse)
    monkeypatch.setattr(cli, "_serve",
                        lambda *a, **k: pytest.fail("it served anyway"))

    assert cli.main(["demo", "--port", "0"]) == 1
    assert "cannot build the demo workflow and run" in capsys.readouterr().err
