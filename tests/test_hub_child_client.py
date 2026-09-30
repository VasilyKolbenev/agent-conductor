"""The hub reads its children by one table and can write nothing to them (spec 4.1.9, 4.5.6).

A fake child on a real socket (`tests/_hub_fake_child.py`) writes down every request. The tests say
what the hub asked: only rows of `CHILD_READS`, each with `X-Conduct-Project` and the child's own
Host, in `active` and in `view`, never a POST and never the session route; what it did with a child
that is another project (`identity_mismatch`, no data read after the first answer) or another hub's
or mode (`busy_elsewhere`); that a missing queue or flag is `null` and not an error; that a run is
read only for a `required` row that changed; and that one failed read leaves the cycle incomplete.
The source of the hub is held to the same rule: one module opens connections, and it has no POST.
"""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import pytest

from conductor.hub import attention, child_client
from tests._hub_fake_child import (
    HUB_ORIGIN, FakeChild, run_detail, run_row, serve_standard, task_row)

PROJECT = "3f9c0d5a7b2e4c168a90d3e1f4b7a625"
OTHER = "8a41b6e2c9d04f7385e1a2b6c0d94f13"
HUB = Path(__file__).resolve().parents[1] / "src" / "conductor" / "hub"

#: The table of 4.5.6, row by row: (method, path).
TABLE = [
    ("GET", "/command/project"), ("GET", "/command/tasks"), ("GET", "/command/runs"),
    ("GET", "/command/runs/<run_id>/automation"), ("GET", "/command/runs/<run_id>"),
    ("GET", "/command/queue"), ("GET", "/command/project/auto-continue"),
    ("GET", "/command/quotas"), ("GET", "/events")]


@pytest.fixture
def child():
    made = []

    def make(**kwargs) -> FakeChild:
        made.append(FakeChild(kwargs.pop("project_id", PROJECT), **kwargs))
        return made[-1]

    yield make
    for one in made:
        one.close()


def _standard(one: FakeChild) -> None:
    tasks = [task_row("task-001", "Fix the payment form"), task_row("task-002", "Dark theme")]
    runs = [run_row("run-001", "task-001"),
            run_row("run-002", "task-002", human_state="required", undecided_gates=1)]
    details = {"run-002": run_detail("run-002", {"gate_decision": ["review"]},
                                     [{"node_id": "review", "gate_id": "gate-review",
                                       "needs_decision": True}])}
    serve_standard(one, tasks, runs, details)


def _cycle(one: FakeChild, *, mode: str = "active", previous=None) -> child_client.Cycle:
    client = child_client.ChildClient(one.port, PROJECT)
    return child_client.read_cycle(client, hub_origin=HUB_ORIGIN, mode=mode,
                                   previous=previous or {})


def test_the_table_of_reads_is_the_one_of_the_spec_row_by_row():
    assert [(row.method, row.path) for row in child_client.CHILD_READS] == TABLE
    assert all(row.when and row.why for row in child_client.CHILD_READS)
    assert isinstance(child_client.CHILD_READS, tuple)


@pytest.mark.parametrize("mode", ["active", "view"])
def test_every_request_of_a_cycle_is_a_get_of_the_table_with_the_claim_and_the_childs_host(
        child, mode):
    one = child(mode=mode)
    _standard(one)
    cycle = _cycle(one, mode=mode)
    assert cycle.verdict == "live" and cycle.failures == ()
    assert {request.method for request in one.log} == {"GET"}
    allowed = {"/command/project", "/command/tasks", "/command/runs", "/command/queue",
               "/command/project/auto-continue", "/command/quotas",
               "/command/runs/run-001/automation", "/command/runs/run-002/automation",
               "/command/runs/run-002"}
    assert set(one.targets()) == allowed
    assert one.targets()[0] == "/command/project", "identity is the first read of a cycle"
    for request in one.log:
        assert request.headers["x-conduct-project"] == PROJECT
        assert request.headers["host"] == f"127.0.0.1:{one.port}"
    assert "/command/session" not in one.targets()


def test_a_path_outside_the_table_cannot_be_read_and_the_client_has_no_way_to_write(child):
    one = child()
    client = child_client.ChildClient(one.port, PROJECT)
    for path in ("/command/session", "/command/runs/../session", "/command/queue?x=1",
                 "/command/runs/run-001/controls", "/state.json", "", "command/tasks",
                 "/command/runs/" + "x" * 129, "/command/runs/-bad"):
        with pytest.raises(ValueError):
            client.get(path)
    assert one.log == [], "a refused path was not even sent"
    public = {name for name in dir(client) if not name.startswith("_")}
    assert public == {"get", "port", "project_id"}, public


def test_a_child_that_is_another_project_is_an_identity_mismatch_and_no_data_is_read(child):
    wrong, conflict = (child(shown_project_id=OTHER), child())
    _standard(wrong)
    _standard(conflict)
    conflict.project_status = 409
    for one in (wrong, conflict):
        cycle = _cycle(one)
        assert cycle.verdict == "identity_mismatch" and cycle.tasks == ()
        assert one.targets() == ["/command/project"], "data of another project was read"


def test_a_child_with_another_hubs_origin_or_another_mode_is_busy_elsewhere(child):
    cases = [child(hub_origin="http://127.0.0.1:7711"), child(hub_origin=None),
             child(mode="view")]
    for one in cases:
        _standard(one)
        cycle = _cycle(one, mode="active")
        assert cycle.verdict == "busy_elsewhere" and cycle.tasks == (), one.identity
        assert one.targets() == ["/command/project"]


def test_a_queue_and_a_flag_the_child_does_not_have_are_null_and_not_an_error(child):
    one = child()
    _standard(one)
    cycle = _cycle(one)
    assert one.count("/command/queue") == one.count("/command/project/auto-continue") == 1
    assert cycle.queue is None and cycle.auto_continue is None
    assert cycle.failures == () and cycle.verdict == "live"
    one.put("/command/queue", {"schema_version": 1, "revision": 2,
                               "slot": {"state": "free", "run_id": None, "reason_code": None},
                               "entries": []})
    one.put("/command/project/auto-continue", {"schema_version": 2, "enabled": False})
    again = _cycle(one)
    assert again.queue["slot"]["state"] == "free" and again.auto_continue["enabled"] is False


def test_the_newest_run_of_each_task_is_chosen_and_only_it_has_its_automation_read(child):
    one = child()
    tasks = [task_row("task-001", "A"), task_row("task-002", "B"), task_row("task-003", "C")]
    runs = [run_row("run-a1", "task-001", created_at="2026-09-30T09:00:00Z"),
            run_row("run-a2", "task-001", created_at="2026-09-30T09:30:00Z"),
            run_row("run-b1", "task-002", created_at="2026-09-30T09:10:00Z"),
            {**run_row("run-bad", None), "unreadable": True, "created_at": None}]
    serve_standard(one, tasks, runs)
    cycle = _cycle(one)
    assert [(row.task["task_id"], row.run and row.run["run_id"]) for row in cycle.tasks] == [
        ("task-001", "run-a2"), ("task-002", "run-b1"), ("task-003", None)]
    asked = {target for target in one.targets() if target.endswith("/automation")}
    assert asked == {"/command/runs/run-a2/automation", "/command/runs/run-b1/automation"}
    assert cycle.tasks[2].automation is None and cycle.tasks[0].automation["state"] == "waiting"
    assert set(cycle.tasks[0].automation) == {"state", "reason_code", "expires_at"}


def test_a_run_is_read_only_for_a_required_row_and_only_when_the_row_changed(child):
    one = child()
    _standard(one)
    first = _cycle(one)
    assert one.count("/command/runs/run-002") == 1
    assert one.count("/command/runs/run-001") == 0, "a row that needs no one is never read"
    second = _cycle(one, previous=first.memory)
    assert one.count("/command/runs/run-002") == 1, "the same row was read again"
    assert second.tasks[1].detail == first.tasks[1].detail is not None
    changed = [run_row("run-001", "task-001"),
               run_row("run-002", "task-002", human_state="required", undecided_gates=2)]
    one.put("/command/runs", {"runs": changed, "providers": []})
    third = _cycle(one, previous=second.memory)
    assert one.count("/command/runs/run-002") == 2, "a changed row was not read again"
    assert third.tasks[1].detail is not None


def test_a_run_read_that_fails_is_kept_as_failed_and_is_tried_again_at_the_next_cycle(child):
    one = child()
    _standard(one)
    one.put("/command/runs/run-002", {"error": {"code": "service_refused"}}, status=409)
    first = _cycle(one)
    assert first.verdict == "live" and first.tasks[1].detail is None
    assert first.tasks[1].detail_failed is True and first.failures == ()
    assert attention.attention_of(first.tasks[1].detail, "2026-09-30T10:00:00Z")["unreadable"]
    one.put("/command/runs/run-002", run_detail("run-002", {"confirmation": ["p1"]}))
    second = _cycle(one, previous=first.memory)
    assert second.tasks[1].detail is not None and not second.tasks[1].detail_failed


def test_the_five_reasons_are_read_reconcile_included_and_a_gate_id_belongs_to_a_gate_only(child):
    one = child()
    reasons = {"gate_decision": ["review"], "confirmation": ["p1"], "input_document": ["doc"],
               "reconcile": ["n1"], "attempt_bound": ["do"], "run_ended": ["t1"]}
    tasks = [task_row("task-001", "A")]
    runs = [run_row("run-001", "task-001", human_state="required")]
    detail = run_detail("run-001", reasons,
                        [{"node_id": "review", "gate_id": "gate-review", "needs_decision": True},
                         {"node_id": "other", "gate_id": "gate-other", "needs_decision": False}])
    serve_standard(one, tasks, runs, {"run-001": detail})
    (row,) = _cycle(one).tasks
    got = attention.attention_of(row.detail, "2026-09-30T10:00:00Z")
    assert [entry["reason"] for entry in got["reasons"]] == [
        "gate_decision", "confirmation", "input_document", "reconcile", "attempt_bound"]
    assert got["gates"] == [{"node_id": "review", "gate_id": "gate-review"}]


def test_one_failed_read_leaves_the_cycle_live_but_incomplete_and_names_the_read(child):
    one = child()
    _standard(one)
    one.put("/command/runs/run-001/automation", {"error": {}}, status=500)
    one.put("/command/quotas", b"not json at all")
    cycle = _cycle(one)
    assert cycle.verdict == "live" and not cycle.complete
    assert set(cycle.failures) == {"automation", "quotas"}
    assert cycle.tasks[0].automation is None and cycle.quotas is None


@pytest.mark.parametrize("broken", ["/command/tasks", "/command/runs"])
def test_a_list_that_cannot_be_read_makes_the_cycle_unreadable_with_no_rows(child, broken):
    one = child()
    _standard(one)
    one.put(broken, {"not": "the list"})
    cycle = _cycle(one)
    assert cycle.verdict == "unreadable" and cycle.tasks == () and not cycle.complete
    assert cycle.failures == (broken.rsplit("/", 1)[1],)


def test_a_child_that_is_not_there_or_is_too_slow_or_too_big_is_a_failed_read(child):
    one = child()
    _standard(one)
    gone = FakeChild(PROJECT)
    port = gone.port
    gone.close()
    away = child_client.read_cycle(child_client.ChildClient(port, PROJECT), hub_origin=HUB_ORIGIN,
                                   mode="active", previous={})
    assert away.verdict == "unreadable" and away.failures == ("project",)
    one.delay["/command/project"] = 0.6
    slow = child_client.read_cycle(child_client.ChildClient(one.port, PROJECT, timeout=0.2),
                                   hub_origin=HUB_ORIGIN, mode="active", previous={})
    assert slow.verdict == "unreadable" and slow.failures == ("project",)
    one.delay.clear()
    one.put("/command/tasks", b'{"tasks": ["' + b"x" * (child_client.MAX_BYTES + 10) + b'"]}')
    big = _cycle(one)
    assert big.verdict == "unreadable" and big.failures == ("tasks",)


def test_the_size_and_the_time_the_spec_allows_are_ten_seconds_and_eight_mebibytes():
    assert child_client.TIMEOUT_SECONDS == 10 and child_client.MAX_BYTES == 8 * 1024 * 1024
    assert child_client.HEADER == "X-Conduct-Project"


# -- the stream ---------------------------------------------------------------------------------


def test_the_pause_before_a_reconnect_doubles_from_one_second_to_thirty():
    pauses, now = [], None
    for _ in range(8):
        now = child_client.next_pause(now)
        pauses.append(now)
    assert pauses == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def _follow(one: FakeChild, signals: list, stop: threading.Event,
            pauses: list[float]) -> threading.Thread:
    events = child_client.ChildEvents(
        one.port, PROJECT, lambda: signals.append(time.monotonic()),
        sleep=lambda seconds: pauses.append(seconds) or stop.wait(0.05))
    thread = threading.Thread(target=events.follow, args=(stop,), daemon=True)
    thread.start()
    return thread


def _wait(condition, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert condition()


def test_a_frame_of_the_stream_is_a_signal_and_nothing_in_it_is_read(child):
    one = child()
    signals, pauses, stop = [], [], threading.Event()
    thread = _follow(one, signals, stop, pauses)
    _wait(lambda: len(signals) >= 1)                       # the frame a child sends on connect
    one.send_frame({"kind": "run", "run_id": "run-001", "secret": "kept out"})
    one.send_frame(b": a comment line\n\n")
    one.send_frame(b"data: not json at all\n\n")
    _wait(lambda: len(signals) >= 3)
    stop.set()
    thread.join(5)
    request = one.log[0]
    assert (request.method, request.target) == ("GET", "/events")
    assert request.headers["x-conduct-project"] == PROJECT
    assert request.headers["host"] == f"127.0.0.1:{one.port}"


def test_a_stream_that_ends_is_opened_again_after_a_pause_and_the_pause_starts_over_on_a_frame(
        child):
    one = child()
    signals, pauses, stop = [], [], threading.Event()
    thread = _follow(one, signals, stop, pauses)
    _wait(lambda: len(signals) >= 1)
    one.drop_streams()
    _wait(lambda: len(signals) >= 2)                       # reconnected: a new connect frame
    assert pauses and pauses[0] == 1.0
    one.drop_streams()
    _wait(lambda: len(signals) >= 3)
    assert pauses[1] == 1.0, "a frame after a reconnect restarts the pause"
    stop.set()
    thread.join(5)
    assert one.count("/events") >= 3


def test_a_stream_that_cannot_connect_backs_off_and_stops_when_told():
    def refuse(*_args, **_kwargs):
        raise ConnectionRefusedError("nothing listens")

    stop, pauses = threading.Event(), []
    events = child_client.ChildEvents(1, PROJECT, lambda: None, connect=refuse,
                                      sleep=lambda seconds: pauses.append(seconds) or False)
    thread = threading.Thread(target=events.follow, args=(stop,), daemon=True)
    thread.start()
    _wait(lambda: len(pauses) >= 6)
    stop.set()
    thread.join(5)
    assert not thread.is_alive() and pauses[:6] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]


# -- the source ---------------------------------------------------------------------------------


def _hub_sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(HUB.glob("*.py"))}


def test_no_source_of_the_hub_names_the_childs_session_route():
    needle = "/command/" + "session"
    assert [name for name, text in _hub_sources().items() if needle in text] == []


def test_only_the_child_client_opens_a_connection_and_it_has_no_post():
    openers = ("http.client", "urllib.request", "create_connection", "requests", "socket.socket",
               "HTTPConnection", "HTTPSConnection", "urlopen")
    assert "child_client.py" in _hub_sources()
    for name, text in _hub_sources().items():
        if name == "child_client.py":
            continue
        assert not any(word in text for word in openers), name
    tree = ast.parse(_hub_sources()["child_client.py"])
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not {"POST", "PUT", "PATCH", "DELETE"} & literals
    assert "post" not in {node.name.lower() for node in ast.walk(tree)
                          if isinstance(node, ast.FunctionDef)}
