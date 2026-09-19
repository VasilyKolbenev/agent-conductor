"""A child that changed another task's directory is never reported as verified work.

The doors decide where a child STANDS. They cannot stop a process that stands in
its own directory from writing through `..` into another's -- that is what the
verification after the effect is for: every change the child made is compared
with its action's authorized subtree (`HarnessWorkspace.subtree`), on the plain
Confirm road (`ArtifactAwareTransport._verify_dispatch`) and on the road an
independent checker is called on (`ArtifactAwareTransport.publish`). A change
anywhere else, even beside a legitimate one, ends the attempt
`verification_failed` with no durable evidence, and no checker is ever shown it.

The subtree is the WHOLE route of the task's item, `_tasks/<scope>/<item>/`, so a
task's action is never authorized over the container every task shares. And what
the checker is shown is the task's own tree: its frame is built from the task's
directory, never from the task-less one beside it.

A child's bytes elsewhere are a fact the build can only detect, never undo; these
witnesses assert that the victim's file WAS written (the scenario happened), and
that nothing certified it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import ActionProposal, DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, ControlRuntime
from tests import _fakeclaude, _fakecodex
from tests.test_command_claude_transport import NOW, _Ids, a_harness
from tests.test_command_codex_transport import a_harness as codex_harness
from tests.test_command_runtime_authorize import a_budget, a_confirmation
from tests.test_command_task_scope_authority import DISPATCH, OLD, place

RUN, DOER, CHECKER = "run-verify-001", "claude-dev", "codex-review"
MINE = "the task's own result, written where it may be"
ELSEWHERE = "written through .. into a directory this action was never given"
HISTORY = "history.txt"
TASKS = [pytest.param("own", id="task-own"), pytest.param(None, id="task-less")]
ROADS = [pytest.param(False, id="confirmed"), pytest.param(True, id="independently-checked")]
WRITES = [pytest.param("mine-and-elsewhere", id="mine-and-elsewhere"),
          pytest.param("only-elsewhere", id="only-elsewhere")]


def _victim(root: Path) -> Path:
    return root.joinpath(*place("victim")) / "result.txt"


def _elsewhere(task: str | None) -> str:
    """The victim's file, spelled relative to where this action's child stands."""
    here = Path(*place(task))
    return Path(os.path.relpath(Path(*place("victim")) / "result.txt", here)).as_posix()


def _a_run(tmp_path, task: str | None, *, writes: dict, checked: bool,
           probes: list[str] | None = None) -> SimpleNamespace:
    doer, root, log = a_harness(tmp_path / "doer", auth="api_key", **writes)
    instances = [{"id": DOER, "adapter": doer.manifest.adapter_id}]
    adapters, check_log = [doer], None
    if checked:
        knobs = {_fakecodex.EMIT_VERDICT: "enabled-verdict-accept"}
        if probes is not None:
            listed = tmp_path / "checker-probes.json"
            listed.write_text(json.dumps(probes), encoding="utf-8")
            knobs[_fakecodex.STDIN_PROBES] = str(listed)
        checker, _, check_log = codex_harness(tmp_path / "checker", root=root,
                                              auth="api_key", **knobs)
        instances.append({"id": CHECKER, "adapter": checker.manifest.adapter_id,
                          "model": "checker-model"})
        adapters.append(checker)
    config = {"cycle": {"id": "default-orbit", "phases": ["implement", "review"]},
              "instances": instances}
    if task is not None:
        config["task"] = {"id": task, "work_scope": task}
    victim = _victim(root)
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text(OLD, encoding="utf-8")
    digest = snapshot_digest(config)
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id=RUN, cycle_id="default-orbit", created_at=NOW,
                                 config_digest=digest, mode="confirm"), config)
    arguments = dict(DISPATCH, **({} if task is None else {"work_scope": task}))
    node = {}
    if checked:
        store.append(GraphDefinition(
            graph_id="graph-001", run_id=RUN, created_at=NOW,
            nodes=(GraphNode(node_id="confirm-gate", kind="gate", title="Human",
                             gate_id="gate-confirm-do"),
                   GraphNode(node_id="do", kind="task", title="Do the work",
                             instance_id=DOER, capability="dispatch", arguments=arguments,
                             verifier_instance_id=CHECKER)),
            edges=(GraphEdge(from_node="confirm-gate", to_node="do"),)))
        store.append(DecisionReceipt(
            receipt_id="decision-gate-confirm-do", run_id=RUN, gate_id="gate-confirm-do",
            action="approve", actor="owner", decided_at=NOW, reason="Let the work through",
            scope_refs=("work",), config_digest=digest))
        node = {"node_id": "do"}
    proposal = ActionProposal(
        proposal_id="proposal-001", run_id=RUN, attempt_id="attempt-001", instance_id=DOER,
        capability="dispatch", arguments=arguments, scope=("work",), proposed_by="owner",
        proposed_at=NOW, timeout_seconds=60, rationale="Carry the work out.",
        config_digest=digest, input_binding="proposal-v1", **node)
    store.append(proposal)
    return SimpleNamespace(store=store, root=root, log=log, check_log=check_log,
                           victim=victim, proposal=proposal,
                           runtime=ControlRuntime(store, AdapterRegistry(adapters),
                                                  clock=lambda: NOW, ids=_Ids()))


def _carried_out(run: SimpleNamespace):
    granted = run.runtime.authorize(a_confirmation(run.proposal, confirmed_at=NOW),
                                    budget=a_budget())
    return run.runtime.execute(granted)


def _evidence(store: RunStore) -> list:
    return [row.value for row in store.read(RUN).records if row.kind == "evidence"]


@pytest.mark.parametrize("checked", ROADS)
@pytest.mark.parametrize("where", WRITES)
@pytest.mark.parametrize("task", TASKS)
def test_a_child_that_changed_another_tasks_directory_is_never_verified(
        tmp_path, task, where, checked):
    """Task `own`'s child (or a task-less run's) writes into task `victim`'s
    directory -- beside its own result, or instead of one. On both roads the
    attempt ends `verification_failed`, no evidence is recorded, and on the
    checked road no checker is ever spawned to certify it.

    Mutations: either outside-subtree check asks whether ALL changes are outside
    instead of ANY -> the mixed rows verify -> red; the subtree is the first
    component of the item's route (`_tasks/`) -> every task's directory is
    inside a task's action -> red.
    """
    writes = ({_fakeclaude.WRITE_FILE: f"result.txt:{MINE}",
               _fakeclaude.FIX_WHEN: f"work-001|{_elsewhere(task)}:{ELSEWHERE}"}
              if where == "mine-and-elsewhere"
              else {_fakeclaude.WRITE_FILE: f"{_elsewhere(task)}:{ELSEWHERE}"})
    run = _a_run(tmp_path, task, writes=writes, checked=checked)

    attempt = _carried_out(run)
    assert run.victim.read_text(encoding="utf-8") == ELSEWHERE, "the scenario did not happen"
    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt
    assert _evidence(run.store) == []
    if checked:
        assert _fakecodex.task_spawns(run.check_log) == []


def test_the_independent_check_is_shown_its_tasks_own_work_and_nothing_else(tmp_path):
    """A task's checker is shown the task's own result and not the task-less
    history standing in `work/<item>` beside it -- measured on what the checker
    process READ, as booleans, never as copied text. The control is the same run
    certified: the checker accepts what it was really shown.

    Mutations: the checker's frame is read without the scope, at the call site
    or inside `read_work_tree` -> the frame lists the task-less history and none
    of the task's work -> red.
    """
    history = tmp_path / "doer" / "root" / "work" / "work-001" / HISTORY
    history.parent.mkdir(parents=True)
    history.write_text("task-less history nobody in task own owns", encoding="utf-8")
    run = _a_run(tmp_path, "own", writes={_fakeclaude.WRITE_FILE: f"result.txt:{MINE}"},
                 checked=True, probes=[MINE, HISTORY])
    assert history.parent.resolve() == run.root.resolve().joinpath(*place(None))

    attempt = _carried_out(run)
    shown = [row["stdin"]["probes"] for row in _fakecodex.task_spawns(run.check_log)]
    assert shown == [[True, False]]
    assert attempt.state is AttemptState.SUCCEEDED, attempt
