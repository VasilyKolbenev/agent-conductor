"""The driver owes a task's seed before the first action of its run (spec 9.1.4, 9.1.6).

A run whose task has a seed may not propose its first action until that seed is in place: the
driver moves a staged one under the root's turn, performs one that a server in `view` left as a
request (from HEAD, at that moment), and when it cannot it proposes nothing and reads `stalled` /
`seed_blocked` until the next tick can. What owes nothing is not held: a run of no task, a task
never seeded (it started from an empty folder before seeds existed), and a run that performs no
dispatch (its review steps never read the work folder).

Two benches. A real server on the flow bench (scripted doubles, an empty seed, the gate held by a
thread) proves the driver's own behaviour end to end; the settler the API hands the driver is
proved on a real repository, where the requested seed is made from HEAD.
"""
from __future__ import annotations

import shutil

import pytest

from conductor.command import seed_routes, seed_stage
from conductor.command.contracts import ABSENT
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.graph_template import RunBinding, load_template, materialize
from conductor.command.product_names import SEED_STAGING_DIR
from conductor.command.seed_record import (
    SeedRequest, read_request, read_seed, seed_state, write_request, write_seed)
from tests.flow_driver_bench import FlowCycle
from tests.git_repo_helpers import commit, git, needs_git
from tests.test_command_flow_driver import DOER
from tests.test_command_materials_routes import RUN, TASK, NoGit, Project
from tests.test_command_project_doors import code_of
from tests.test_command_workflow_flow import chain, review, step
from tests.test_policy_runtime import ARGS, NOW
from tests.test_seed_move import gate_held
from tests.test_seed_routes import PATH, body, reason_of, seed

BENCH_TASK = "task-seed-drive"
ITEM = "work-001"
LINEAR = chain(review("analyst"), DOER, step("result", "human"))
REVIEWS = chain(review("plan"), review("ideas", role_id="role-reviewer"), step("result", "human"))


@pytest.fixture
def cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(seed_stage, "MOVE_WAIT_SECONDS", 0.05)
    made = []

    def make(flow, **script):
        made.append(FlowCycle(tmp_path / f"project-{len(made)}", flow, through_doors=True,
                              task=BENCH_TASK, **script))
        return made[-1]
    yield make
    for one in made:
        one.close()


def empty_seed(run):
    status, payload = run.post(f"/command/tasks/{BENCH_TASK}/seed", {
        "work_item_id": ITEM, "source": "empty", "expect_commit": None,
        "include_agent_instructions": False})
    return status, payload


def folder_of(run):
    return run.store.project_root / "work" / "_tasks" / BENCH_TASK / ITEM


def at_result_gate(run):
    return run.until("the result gate", lambda: run.plan_state() == "open" and run.reason() ==
                     "waiting")


# --- the driver on a real server -------------------------------------------------------------


def test_driver_moves_a_staged_seed_before_the_first_proposal(cycle):
    run = cycle(LINEAR)
    root, folder = run.store.project_root, folder_of(run)
    with gate_held(root):
        status, staged = empty_seed(run)
        assert status == 202 and staged["state"] == "staged" and not folder.exists()
    seen, real = [], run.doer.execute

    def watch(prepared):
        seen.append(folder.is_dir())
        return real(prepared)
    run.doer.execute = watch
    run.start()
    at_result_gate(run)
    assert seen and all(seen), "the folder stood when the first action was carried out"
    assert run.steps() == ["analyst", "do"] and not (root / SEED_STAGING_DIR).exists()
    assert seed_state(root, read_seed(root, BENCH_TASK)) == "seeded"


def test_driver_proposes_nothing_and_reports_seed_blocked_when_the_move_fails(cycle):
    run = cycle(LINEAR)
    root = run.store.project_root
    with gate_held(root):
        assert empty_seed(run)[0] == 202
        run.start()
        assert run.until("the seed block") == "seed_blocked"
        assert run.records("action_proposal") == [] and run.steps() == []
        assert run.automation() == ("stalled", "seed_blocked")
        assert run.holder() == "run", "the run keeps the slot, as any stalled run does"
        assert run.settle() == 0
    at_result_gate(run)
    assert run.steps() == ["analyst", "do"], "the next tick that could, did"
    assert folder_of(run).is_dir()


def test_a_seed_whose_task_folder_filled_up_blocks_the_run_until_it_empties(cycle):
    run = cycle(LINEAR)
    root, folder = run.store.project_root, folder_of(run)
    with gate_held(root):
        assert empty_seed(run)[0] == 202
    folder.mkdir(parents=True)
    (folder / "late.txt").write_bytes(b"written by something else")
    run.start()
    assert run.until("the seed block") == "seed_blocked" and run.steps() == []
    (folder / "late.txt").unlink()
    at_result_gate(run)
    assert run.steps() == ["analyst", "do"]


@pytest.mark.parametrize("boundary", ["http", "driver"])
@pytest.mark.parametrize("state", ["staged", "seeded"])
def test_a_saved_seed_cannot_substitute_another_scope_for_the_tasks_binding(cycle, boundary, state):
    run = cycle(LINEAR)
    root = run.store.project_root
    record = seed_stage.stage_empty(root, task_id=BENCH_TASK, work_scope="foreign-scope",
                                    work_item_id=ITEM, staged_at=NOW)
    staging = root / SEED_STAGING_DIR / record.staging
    (staging / "keep.txt").write_bytes(b"foreign bytes")
    write_seed(root, record)
    if state == "seeded":
        seed_stage.move_staged(root, record)
    foreign = root / "work" / "_tasks" / "foreign-scope" / ITEM
    held = staging if state == "staged" else foreign
    assert read_seed(root, BENCH_TASK) == record, "the stored schema alone permits this scope"
    if boundary == "http":
        status, payload = empty_seed(run)
        assert (status, payload.get("error", {}).get("code")) == (500, "store_error")
    else:
        assert not run.subject.command_api._policy.seeds.settle(run.graph.run_id)
        run.start()
        assert run.until("the seed binding block") == "seed_blocked"
        assert run.automation() == ("stalled", "seed_blocked")
    assert run.records("action_proposal") == [] and run.steps() == []
    assert (held / "keep.txt").read_bytes() == b"foreign bytes"
    assert not folder_of(run).exists()
    assert seed_state(root, record) == state and read_seed(root, BENCH_TASK) == record


def test_a_run_that_performs_no_dispatch_is_not_held_for_a_seed(cycle):
    run = cycle(REVIEWS)
    root = run.store.project_root
    with gate_held(root):
        assert empty_seed(run)[0] == 202
        run.start()
        at_result_gate(run)
    assert run.steps() == ["plan", "ideas"]
    record = read_seed(root, BENCH_TASK)
    assert seed_state(root, record) == "staged", "nothing asked for the seed, so nothing moved it"


def test_a_task_that_was_never_seeded_starts_from_its_folder_as_it_always_did(cycle):
    run = cycle(LINEAR)
    run.start()
    at_result_gate(run)
    assert run.steps() == ["analyst", "do"]
    assert read_seed(run.store.project_root, BENCH_TASK) is None


# --- the settler the API hands the driver, on a real repository ---------------------------


def dispatch_graph():
    nodes = (GraphNode("gate", "gate", "Approve", gate_id="gate-id"),
             GraphNode("do", "task", "do", instance_id="doer", capability="dispatch",
                       arguments=ARGS, timeout_seconds=30, attempt_bound=2))
    return GraphDefinition("graph-seed", RUN, NOW, nodes=nodes, edges=(
        GraphEdge("gate", "do", condition="on_approved"),), execution_contract=ABSENT)


def review_graph(project):
    template = load_template("desk-starter-docs")
    config = project.store.read(RUN).config
    return materialize(template, RunBinding(assignments={role: "doer" for role in template.roles}),
                       config, graph_id="graph-docs", run_id=RUN, created_at=NOW)


def desk(tmp_path, graph=None, **more):
    project = Project(tmp_path, **more)
    project.store.append(dispatch_graph() if graph is None else graph(project))
    return project


def settle(project):
    return project.api._policy.seeds.settle(RUN)


@needs_git
def test_the_api_hands_the_policy_the_settler_it_built(tmp_path):
    project = desk(tmp_path)
    assert isinstance(project.api._policy.seeds, seed_routes.SeedSettler)


@needs_git
def test_nothing_is_owed_when_the_task_was_never_seeded_and_no_request_was_left(tmp_path):
    project = desk(tmp_path, reader=NoGit())
    assert settle(project) is True and project.reader.asked == 0
    assert read_seed(project.root, TASK) is None


@needs_git
def test_a_staged_seed_is_moved_by_the_settler_and_then_nothing_is_owed(tmp_path, monkeypatch):
    project = desk(tmp_path)
    monkeypatch.setattr(seed_stage, "MOVE_WAIT_SECONDS", 0.05)
    with gate_held(project.root):
        assert seed(project).status == 202
        assert settle(project) is False, "the root is held, so the seed cannot be moved"
        assert seed_state(project.root, read_seed(project.root, TASK)) == "staged"
    assert settle(project) is True
    assert (project.root / "work" / "_tasks" / TASK / ITEM / "README.md").is_file()
    assert settle(project) is True


@needs_git
def test_driver_performs_a_requested_seed_from_head_before_the_first_proposal(tmp_path):
    project = desk(tmp_path)
    write_request(project.root, SeedRequest(TASK, ITEM, True, NOW))
    head = git("rev-parse", "HEAD", cwd=project.root).stdout.decode().strip()
    later = commit(project.root, {"after-the-request.txt": "made after the desk asked\n"})
    assert later != head and read_seed(project.root, TASK) is None
    assert settle(project) is True
    record = read_seed(project.root, TASK)
    assert record.base_commit == later, "the base is HEAD at the moment the seed is made"
    assert record.include_agent_instructions is True
    folder = project.root / "work" / "_tasks" / TASK / ITEM
    assert (folder / "after-the-request.txt").is_file() and (folder / "CLAUDE.md").is_file()
    assert read_request(project.root, TASK) is not None, "the request stays as history"


@needs_git
def test_a_failed_requested_seed_reports_stalled_seed_blocked_with_its_reason(tmp_path):
    project = desk(tmp_path, files={"ok.txt": "fine\n", "work/x.txt": "x\n"})
    write_request(project.root, SeedRequest(TASK, ITEM, False, NOW))
    assert settle(project) is False
    assert read_seed(project.root, TASK) is None
    assert not (project.root / SEED_STAGING_DIR).exists()
    asked = seed(project)
    assert code_of(asked) == (409, "seed_refused") and reason_of(asked) == "tracks_product_dir"


@needs_git
def test_a_lost_seed_holds_the_run_and_the_desk_learns_it_by_asking(tmp_path):
    project = desk(tmp_path)
    assert seed(project).status == 201
    shutil.rmtree(project.root / "work" / "_tasks" / TASK / ITEM)
    assert settle(project) is False
    assert reason_of(seed(project)) == "seed_lost"


@needs_git
def test_a_review_only_run_prepared_in_view_mode_needs_no_seed(tmp_path):
    project = desk(tmp_path, graph=review_graph, reader=NoGit())
    write_request(project.root, SeedRequest(TASK, ITEM, False, NOW))
    assert settle(project) is True
    assert project.reader.asked == 0 and read_seed(project.root, TASK) is None
    assert read_request(project.root, TASK) is not None
    assert not (project.root / "work" / "_tasks").exists()


@needs_git
def test_a_run_of_no_task_is_owed_nothing(tmp_path):
    project = desk(tmp_path, bound=False, reader=NoGit())
    write_request(project.root, SeedRequest(TASK, ITEM, False, NOW))
    assert settle(project) is True and project.reader.asked == 0
