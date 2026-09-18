"""The release cycle, end to end: task -> harness -> independent check -> fix -> result.

Driven over a real loopback socket through the product's own routes -- the ones the
Studio posts to -- with the real provider factory resolving Claude Code as the doer
and Codex as the independent checker. Both run as real child processes through their
real adapters; only the vendor PROGRAM is scripted (`tests/_fakeclaude.py`,
`tests/_fakecodex.py`). That is the whole of what is not the product here, and it is
said plainly because the release plan forbids passing a synthetic show off as the
live cycle: this is the product path with the vendors scripted, and the live run with
the operator's own Claude Code and Codex is a separate act.

Neither vendor is told the outcome. The doer writes a first draft always, and the
fix ONLY when the task it read contains the correction a person wrote
(`FAKECLAUDE_FIX_WHEN`); the checker accepts only when the doer's real `result.txt`
holds that fix (`FAKECODEX_VERDICT_REQUIRES`). So the chain is causal end to end: a
correction dropped, truncated or replaced on the way leaves the draft standing and
the checker refusing. Which instruction each attempt carried is read off the child's
own log as booleans (`FAKECLAUDE_STDIN_PROBES`), and every directory claim is
checked against the one full path the product's contract names.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from conductor import server
from conductor.command.adapters.claude_code import CLAUDE_PROTOCOL, CLAUDE_PROVIDER_ID
from conductor.command.adapters.codex_cli import CODEX_PROTOCOL
from conductor.command.adapters.provider import ProviderConfig
from tests import _fakeclaude, _fakecodex
from tests.test_command_codex_transport import CODEX_PROVIDER_ID
from tests.test_command_run_socket import request
from tests.test_store import good_lane, write_project

WORKFLOW = "workflow-checked-fix"
RUN = "run-cycle-001"
TASK = "task-cycle-001"
DOER, CHECKER = "claude-dev", "codex-review"
WAIT = 120
BRIEF = "Add the missing guard and prove it."
CORRECTION = ("The independent check found the guard missing. "
              "Add the guard and the failing test that proves it.")
DRAFT = "draft -- the guard is missing"
FIXED = "fixed -- guard added, failing test now passes"
#: The directory the contract names for this task's item, spelled HERE and not
#: read from any helper: `work/_tasks/<task>/<item>` under the project root.
WORK = ("work", "_tasks", TASK, "work-001")


def a_workflow() -> dict:
    """A person's own workflow: work, checked by ANOTHER participant, then a gate.

    `verifier_role_id` is what makes the check independent -- the document refuses a
    verifier that is the doer's own role. The loop is how a person sends the work
    back: the result gate answered `request_changes` reopens `do` for one more lap.
    """
    return {
        "schema_version": 1,
        "title": "Work, independent check, fix",
        "nodes": [
            {"kind": "gate", "node_id": "confirm-gate", "title": "Human gate",
             "gate_id": "gate-confirm-do", "resources": []},
            {"kind": "task", "node_id": "do", "title": "Do the work", "stage": "do",
             "role_id": "role-implementer", "verifier_role_id": "role-checker",
             "attempt_bound": 2, "capability": "dispatch",
             "arguments": {"work_item_id": "work-001", "instruction_ref": "instruction-plan",
                           "profile": "implement", "artifact_refs": [],
                           "output_limit_profile": "normal"},
             "resources": [{"kind": "sandbox", "name": "project-root"}]},
            {"kind": "gate", "node_id": "result-gate", "title": "Result gate",
             "gate_id": "gate-result", "resources": []},
            {"kind": "loop", "node_id": "fix-loop", "title": "Fix what the checker found",
             "loop": {"bound": 2, "back_to": "do"}, "resources": []},
        ],
        "edges": [{"from_node": "confirm-gate", "to_node": "do"},
                  {"from_node": "do", "to_node": "result-gate"},
                  {"from_node": "result-gate", "to_node": "fix-loop",
                   "condition": "on_changes_requested"}],
    }


class _Cycle:
    """One served project with a scripted doer and a scripted independent checker."""

    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        tools = tmp_path / "tools"
        tools.mkdir()
        probes = tools / "stdin-probes.json"
        probes.write_text(json.dumps([BRIEF, CORRECTION]), encoding="utf-8")
        self.doer_log = tools / "claude-spawns.log"
        self.checker_log = tools / "codex-spawns.log"
        claude_exe = _fakeclaude.build_executable(tools / "claude-bin")
        codex_exe = _fakecodex.build_executable(tools / "codex-bin")
        if claude_exe is None or codex_exe is None:
            pytest.skip("no console-script launcher stub to build a fake executable")
        knobs = {_fakeclaude.SPAWN_LOG: str(self.doer_log),
                 _fakeclaude.WRITE_FILE: f"result.txt:{DRAFT}",
                 _fakeclaude.FIX_WHEN: f"{CORRECTION}|result.txt:{FIXED}",
                 _fakeclaude.STDIN_PROBES: str(probes),
                 _fakecodex.SPAWN_LOG: str(self.checker_log),
                 _fakecodex.EMIT_VERDICT: "enabled-verdict-reject",
                 _fakecodex.VERDICT_REQUIRES: "result.txt:fixed"}
        for name, value in knobs.items():
            monkeypatch.setenv(name, value)
        self.root = write_project(tmp_path / "project", lanes={"claude": good_lane()})
        self.server = server.build(self.root, port=0, providers=[
            ProviderConfig(provider_id=CLAUDE_PROVIDER_ID, executable=str(claude_exe),
                           protocol=CLAUDE_PROTOCOL, auth="api_key",
                           env_allow=tuple(sorted(n for n in knobs if "CLAUDE" in n))),
            ProviderConfig(provider_id=CODEX_PROVIDER_ID, executable=str(codex_exe),
                           protocol=CODEX_PROTOCOL, auth="api_key",
                           env_allow=tuple(sorted(n for n in knobs if "CODEX" in n)))])
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def call(self, method: str, path: str, body: dict | None = None):
        token = self.token if body is not None else None
        return request(self.base, method, path, token=token, body=body)

    def run(self) -> dict:
        status, body = self.call("GET", f"/command/runs/{RUN}")
        assert status == 200, body
        return body

    def states(self) -> dict[str, str]:
        return {row["node_id"]: row["state"]
                for row in self.run()["graph"]["schedule"]["nodes"]}

    def spawns(self, log: Path) -> list[dict]:
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        return [row for row in rows if row.get("argv") != ["--version"]]


@pytest.fixture
def cycle(tmp_path, monkeypatch):
    bench = _Cycle(tmp_path, monkeypatch)
    thread = threading.Thread(target=bench.server.serve_forever, daemon=True)
    thread.start()
    try:
        status, session = request(bench.base, "GET", "/command/session")
        assert status == 200
        bench.token = session["csrf_token"]
        yield bench
    finally:
        bench.server.shutdown()
        bench.server.server_close()


def _open_the_task_and_its_run(cycle: _Cycle) -> None:
    """Draw, publish, create the task, open a run bound to it -- the Studio's roads."""
    assert cycle.call("POST", f"/command/workflows/{WORKFLOW}/draft",
                      {"document": a_workflow(), "expected_absent": True})[0] == 201
    draft = cycle.call("GET", f"/command/workflows/{WORKFLOW}")[1]["draft"]
    assert cycle.call("POST", f"/command/workflows/{WORKFLOW}/revisions",
                      {"revision": 1, "reviewed_digest": draft["digest"]})[0] == 201
    assert cycle.call("POST", "/command/tasks",
                      {"task_id": TASK, "title": "Add the missing guard"})[0] == 201
    status, opened = cycle.call("POST", "/command/runs", {
        "run_id": RUN, "cycle_id": "default-orbit", "mode": "confirm",
        "participants": [{"instance_id": DOER, "provider_id": CLAUDE_PROVIDER_ID,
                          "model": None},
                         {"instance_id": CHECKER, "provider_id": CODEX_PROVIDER_ID,
                          "model": None}],
        "workflow_id": WORKFLOW, "revision": 1,
        "assignments": {"role-implementer": DOER, "role-checker": CHECKER},
        "task_id": TASK})
    assert status == 201, opened


def _decide(cycle: _Cycle, receipt_id: str, gate_id: str, action: str,
            supersedes: str | None = None) -> None:
    status, body = cycle.call("POST", f"/command/runs/{RUN}/decisions", {
        "receipt_id": receipt_id, "gate_id": gate_id, "action": action,
        "actor": "owner", "reason": f"{action}, having read the result",
        "scope_refs": ["work"], "evidence_refs": [], "supersedes": supersedes})
    assert status == 201, body


def _instruct(cycle: _Cycle, artifact_id: str, text: str) -> None:
    status, body = cycle.call("POST", f"/command/runs/{RUN}/artifacts", {
        "artifact_id": artifact_id, "artifact_ref": "instruction-plan",
        "media_type": "text/markdown", "content": text})
    assert status == 201, body


def _attempt(cycle: _Cycle, attempt_id: str) -> dict:
    """Propose exactly what the plan carries for `do`, confirm it, and wait it out."""
    do = next(node for node in cycle.run()["graph"]["definition"]["nodes"]
              if node["node_id"] == "do")
    status, proposal = cycle.call("POST", f"/command/runs/{RUN}/proposals", {
        "instance_id": do["instance_id"], "attempt_id": attempt_id,
        "capability": do["capability"], "arguments": do["arguments"],
        "scope": ["work"], "proposed_by": "owner", "rationale": "Carry out Do.",
        "timeout_seconds": 60, "node_id": "do"})
    assert status == 201, proposal
    status, confirmed = cycle.call("POST", f"/command/runs/{RUN}/actions", {
        "proposal_id": proposal["proposal_id"], "preview_digest": proposal["preview_digest"],
        "capability": proposal["capability"], "scope": proposal["scope"],
        "config_digest": proposal["config_digest"], "confirmed_by": "owner"})
    assert status == 201, confirmed
    assert cycle.server.command_execution.wait_idle(WAIT) is True
    results = [row["record"] for row in cycle.run()["records"]
               if row["record_type"] == "action_result"
               and row["record"]["attempt_id"] == attempt_id]
    assert len(results) == 1, results
    return results[0]


def _drive(cycle: _Cycle) -> dict:
    """Carry the cycle through the product's roads, asserting ROADS and nothing else.

    Every status a person's action gets is asserted here, because a refused road
    is not a cycle at all. What the attempts CAME TO is left to the tests below,
    so each of them fails on the claim it names and not on another's.
    """
    _open_the_task_and_its_run(cycle)
    _decide(cycle, "decision-confirm-1", "gate-confirm-do", "approve")
    _instruct(cycle, "brief-1", BRIEF)
    seen = {"first": _attempt(cycle, "attempt-do-1"), "first_result": _result_or_none(cycle),
            "states_after_first": cycle.states()}
    _decide(cycle, "decision-result-1", "gate-result", "request_changes")
    seen["states_after_request"] = cycle.states()
    _instruct(cycle, "brief-2", CORRECTION)
    seen["second"] = _attempt(cycle, "attempt-do-2")
    seen["second_result"] = _result_or_none(cycle)
    _decide(cycle, "decision-result-2", "gate-result", "approve",
            supersedes="decision-result-1")
    seen["final"] = cycle.run()["graph"]["schedule"]["run_state"]
    return seen


def _result_or_none(cycle: _Cycle) -> str | None:
    path = cycle.root.joinpath(*WORK) / "result.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def test_a_refused_result_is_fixed_and_the_fix_is_what_the_checker_accepts(cycle):
    """What the cycle came to, judged on the records and on the file at the
    contract's own path.

    Mutation: the doer is handed anything but the correction (its length, the
    first brief again) -> the draft stands and the checker refuses the second
    attempt -> red at its outcome.
    """
    seen = _drive(cycle)
    assert seen["first"]["outcome"] == "verification_failed", seen["first"]
    assert seen["first"]["detail"] == "the independent checker rejected the doer's result"
    assert seen["first_result"] == DRAFT
    assert seen["states_after_first"]["result-gate"] == "runnable"
    assert seen["states_after_request"]["do"] == "runnable", "the loop did not send it back"
    assert seen["second"]["outcome"] == "succeeded", seen["second"]
    assert seen["second"]["detail"] == (
        "the plan's independent participant verified the observed result")
    assert seen["second"]["evidence_refs"], "a success must carry the checker's evidence"
    assert seen["second_result"] == FIXED
    assert seen["final"] == "complete"


def test_each_attempt_read_its_own_instruction_in_the_tasks_own_directory(cycle):
    """What each child READ and where it STOOD, off its own spawn log.

    The first attempt carried the brief and not the correction; the second the
    correction and not the brief -- the latest document under the ref, as the
    binding promises. Every child, doer and checker alike, stood in the full path
    the contract names for this task's item, compared whole: a work tree moved
    to another root keeps the same last component and would pass a name check.

    Mutation: the task is handed its length instead of its text -> the probes are
    all false -> red. Mutation: the work tree's root is renamed -> every cwd is
    elsewhere -> red.
    """
    _drive(cycle)
    doer, checker = cycle.spawns(cycle.doer_log), cycle.spawns(cycle.checker_log)
    assert [row["stdin"]["probes"] for row in doer] == [[True, False], [False, True]]
    expected = cycle.root.resolve().joinpath(*WORK)
    assert [Path(row["cwd"]).resolve() for row in doer + checker] == [expected] * 4
    assert all("read-only" in row["argv"] for row in checker), "the checker could write"
