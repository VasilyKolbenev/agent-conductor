"""Which plan a run followed, recorded where nothing can quietly change it.

Before this, a run recorded no template identity at all. `studio_routes.run_row`
said so in its own docstring -- *"this build cannot say which revision a run came
from without guessing"* -- and the Runs screen printed an `unsupported` marker
where the revision belonged. That was the honest answer to a real gap: a
materialized `GraphDefinition` carries `graph_id`, which is minted per run and
names no workflow.

The reference now lives in the run's FROZEN CONFIGURATION, and the choice of
document is the whole design. `config_digest` is taken over that snapshot, so
three properties come for free rather than needing three mechanisms:

- **replay** re-digests the config on every `RunStore.read` and refuses a
  mismatch, so a reference edited on disk cannot be read back;
- **idempotency and conflict** compare the whole config, so a second open of the
  same run id naming a different revision is a `RecordConflict`;
- **immutability** needs no rule at all -- nothing rewrites a frozen config, so
  publishing revision 3 cannot move a run that started on revision 1.

The reference is OMITTED, never null, when a run follows no workflow. That is
what keeps every stored run readable: `conduct preview` and the control loop
both open runs with no plan, and their frozen bytes are exactly what they were.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.contracts import ContractError, frozen_config_workflow
from conductor.command.graph_template import RunBinding
from conductor.command.studio_contracts import Participant, RunInput


def an_input(*, workflow_id="release-check", revision=1, run_id="run-a"):
    return RunInput(
        run_id=run_id, cycle_id="cycle-a", mode="confirm",
        participants=(Participant(instance_id="dev", provider_id="claude-code",
                                  model=None),),
        workflow_id=workflow_id, revision=revision,
        binding=RunBinding.from_dict({"assignments": {}}))


# -- the snapshot carries it, and only when there is one to carry ------------


def test_a_run_that_follows_a_workflow_freezes_which_one_and_which_revision():
    snapshot = an_input(workflow_id="release-check", revision=3).snapshot()

    assert snapshot["workflow"] == {"id": "release-check", "revision": 3}


def test_a_run_that_follows_no_workflow_freezes_exactly_the_bytes_it_always_did():
    """The other side, and the reason every stored run still reads.

    `conduct preview` and the control loop open runs with no plan. A reference
    spelled `null` would change their frozen bytes, move every digest they have
    ever written, and make each of them a run this build could no longer replay.
    """
    snapshot = an_input(workflow_id=None, revision=None).snapshot()

    assert "workflow" not in snapshot
    assert set(snapshot) == {"cycle", "instances"}


def test_the_reference_is_inside_the_document_the_digest_is_taken_over():
    """Provenance and digest are one fact, not two that could disagree.

    If the reference sat beside the snapshot rather than inside it, a run could
    replay with a verified configuration and an unverified claim about which
    plan it followed -- which is the shape of every provenance defect worth
    having.
    """
    from conductor.command.run_store import snapshot_digest

    one = an_input(revision=1).snapshot()
    two = an_input(revision=2).snapshot()

    assert snapshot_digest(one) != snapshot_digest(two)


# -- the reader: strict, and absent is a real answer -------------------------


def test_a_configuration_naming_no_workflow_reports_none_rather_than_guessing():
    assert frozen_config_workflow({"cycle": {"id": "c"}, "instances": []}) is None


def test_the_reference_this_product_writes_is_the_one_the_reader_reads():
    """Writer and reader held together, so neither can drift alone."""
    snapshot = an_input(workflow_id="flow-x", revision=7).snapshot()

    assert frozen_config_workflow(snapshot) == ("flow-x", 7)


@pytest.mark.parametrize("reference", [
    {"id": "flow-x"},                       # half of one: no revision
    {"revision": 1},                        # half of one: no workflow
    {"id": "flow-x", "revision": 0},        # a revision starts at 1
    {"id": "flow-x", "revision": True},     # bool is an int and True is not 1
    {"id": "flow-x", "revision": "1"},      # a numeral is not a number
    {"id": "flow x", "revision": 1},        # not an id
    {"id": "flow-x", "revision": 1, "extra": 1},   # a key nobody wrote
])
def test_a_malformed_reference_is_refused_rather_than_half_read(reference):
    """Half a provenance is worse than none: a reader would act on it.

    Every row here is a document some future road could write by accident, and
    each must be a refusal rather than a partial answer.
    """
    config = {"cycle": {"id": "c"}, "instances": [], "workflow": reference}

    with pytest.raises(ContractError):
        frozen_config_workflow(config)


# -- the three properties the frozen document buys --------------------------


def test_a_second_open_naming_a_different_revision_is_a_conflict(tmp_path):
    """Idempotency covers the plan because the plan is inside the digest.

    Without the reference in the snapshot, opening `run-a` again against
    revision 9 would produce an identical config, an identical digest, and a
    silent 200 adopting the standing run as though it followed revision 9.
    """
    from conductor.command.run_store import RunStore
    from conductor.command.store_errors import RecordConflict
    from conductor.command.studio_routes import _repeats_the_standing_run

    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    store = RunStore(root)
    first = an_input(revision=1)
    snapshot = first.snapshot()
    envelope = first.build(snapshot, "2026-01-01T00:00:00Z")
    store.create_run(envelope, snapshot)
    standing = store.read("run-a")

    assert _repeats_the_standing_run(
        first, snapshot, standing).run_id == "run-a"

    later = an_input(revision=9)
    with pytest.raises(RecordConflict):
        _repeats_the_standing_run(later, later.snapshot(), standing)


def test_the_reference_survives_a_restart_because_replay_re_verifies_it(tmp_path):
    """A fresh store over the same directory is the restarted process."""
    from conductor.command.run_store import RunStore

    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    asked = an_input(workflow_id="flow-x", revision=4)
    snapshot = asked.snapshot()
    RunStore(root).create_run(asked.build(snapshot, "2026-01-01T00:00:00Z"),
                              snapshot)

    recovered = RunStore(root).read("run-a")

    assert frozen_config_workflow(recovered.config) == ("flow-x", 4)


def test_a_reference_edited_on_disk_is_refused_by_the_digest(tmp_path):
    """The claim and the digest stand or fall together.

    This is what makes the reference a FROZEN fact rather than a stored string:
    rewriting it out of band does not produce a run that followed another plan,
    it produces a run that will not replay at all.
    """
    from conductor.command.run_store import CorruptRun, RunStore

    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    asked = an_input(workflow_id="flow-x", revision=4)
    snapshot = asked.snapshot()
    RunStore(root).create_run(asked.build(snapshot, "2026-01-01T00:00:00Z"),
                              snapshot)
    config = RunStore(root).run_path("run-a") / "config.json"
    tampered = json.loads(config.read_text(encoding="utf-8"))
    tampered["workflow"]["revision"] = 99
    config.write_text(json.dumps(tampered), encoding="utf-8", newline="\n")

    with pytest.raises(CorruptRun):
        RunStore(root).read("run-a")


def test_publishing_a_later_revision_does_not_move_a_standing_run(tmp_path):
    """The run follows the plan it started with, and nothing edits that.

    No mechanism is asserted here on purpose: the point is that there is none
    to assert. A frozen config is never rewritten, so a later revision cannot
    reach a run that already opened.
    """
    from conductor.command.graph_template import GraphTemplate
    from conductor.command.run_store import RunStore
    from conductor.command.template_store import TemplateStore

    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    document = {"schema_version": 1, "template_id": "flow-x", "revision": 1,
                "title": "Flow", "nodes": [
                    {"node_id": "step", "kind": "task", "title": "Step",
                     "resources": []}], "edges": []}
    templates = TemplateStore(root)
    templates.save(GraphTemplate.from_dict(document))
    asked = an_input(workflow_id="flow-x", revision=1)
    snapshot = asked.snapshot()
    RunStore(root).create_run(asked.build(snapshot, "2026-01-01T00:00:00Z"),
                              snapshot)

    templates.save(GraphTemplate.from_dict({**document, "revision": 2,
                                            "title": "Flow, revised"}))

    assert templates.revisions("flow-x") == (1, 2)
    assert frozen_config_workflow(RunStore(root).read("run-a").config) == (
        "flow-x", 1)


# -- what the list row reports ----------------------------------------------


def test_the_run_row_reports_the_revision_it_froze(tmp_path):
    from conductor.command.run_store import RunStore
    from conductor.command.studio_routes import run_row

    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    asked = an_input(workflow_id="flow-x", revision=2)
    snapshot = asked.snapshot()
    store = RunStore(root)
    store.create_run(asked.build(snapshot, "2026-01-01T00:00:00Z"), snapshot)

    row = run_row(store, "run-a")

    assert (row["workflow_id"], row["revision"]) == ("flow-x", 2)


def test_a_run_with_no_workflow_reports_both_halves_null(tmp_path):
    """Null together, so no reader can find one half and infer the other."""
    from conductor.command.run_store import RunStore
    from conductor.command.studio_routes import run_row

    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    asked = an_input(workflow_id=None, revision=None)
    snapshot = asked.snapshot()
    store = RunStore(root)
    store.create_run(asked.build(snapshot, "2026-01-01T00:00:00Z"), snapshot)

    row = run_row(store, "run-a")

    assert (row["workflow_id"], row["revision"]) == (None, None)


def test_an_unreadable_run_reports_the_reference_as_unknown_not_as_absent(tmp_path):
    """The shape a reader gets when the run cannot be read carries both keys.

    A row missing the keys entirely would make "unreadable" and "followed no
    workflow" the same answer on screen.
    """
    from conductor.command.run_store import RunStore
    from conductor.command.studio_routes import run_row

    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    store = RunStore(root)
    store.runs_root.mkdir(parents=True, exist_ok=True)
    (store.runs_root / "ghost").mkdir()

    row = run_row(store, "ghost")

    assert row["unreadable"] is True
    assert "workflow_id" in row and row["workflow_id"] is None
    assert "revision" in row and row["revision"] is None
