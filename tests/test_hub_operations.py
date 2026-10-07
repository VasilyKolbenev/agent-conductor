"""The folder-add operation keeps progress and a safe result across the start step.

Every other kind of operation (a recovery, a login recovery, a profile copy) is a row of the same
ledger, with the form of spec 4.6.4 and a `detail` that holds only a typed reason.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

import pytest

from conductor.hub import events, operations, refusals

PROJECT = "a" * 32
PICK = operations.FolderPick("C:\\owner\\project", "none")
RESULT = {"project_id": PROJECT, "root": PICK.path, "folder": "project",
          "activated": "new", "providers": "absent", "git": "not_git",
          "exclude": "not_git", "exclude_names": None, "agent_instructions": [],
          "projects_home_created": False}


class Finished:
    def __init__(self, code=0):
        self.returncode = code

    def poll(self):
        return self.returncode


def fake_cli(*, result=RESULT, code=0, error="", steps=operations.STEPS):
    def launch(_argv, **kwargs):
        output = kwargs["stdout"]
        for step in steps:
            output.write((json.dumps({"step": step}) + "\n").encode())
        if code == 0:
            output.write((json.dumps({"result": result}) + "\n").encode())
        kwargs["stderr"].write(error.encode())
        return Finished(code)
    return launch


def settled(manager, ident):
    for _ in range(100):
        found = manager.get(ident)
        if found["state"] != "running":
            return found
        time.sleep(0.01)
    raise AssertionError("operation did not settle")


def test_result_hides_the_absolute_path_and_finishes_only_after_serving(tmp_path):
    started = []
    manager = operations.Operations(tmp_path, events.EventBus(),
        start=lambda project_id: started.append(project_id),
        status=lambda _project_id: ("running", None), popen=fake_cli())
    row = settled(manager, manager.begin(PICK, "Project", True))
    assert row["state"] == "succeeded" and row["step"] == "start"
    assert row["project_id"] == PROJECT and started == [PROJECT]
    assert row["result"]["folder"] == "project"
    assert "root" not in row["result"] and PICK.path not in json.dumps(row)


def test_start_refusal_keeps_the_completed_add_result(tmp_path):
    def refused(_project_id):
        raise refusals.HubRefusal("active_not_closed")

    manager = operations.Operations(tmp_path, events.EventBus(), start=refused,
        status=lambda _project_id: ("stopped", None), popen=fake_cli())
    row = settled(manager, manager.begin(PICK, "Project", True))
    assert row["state"] == "failed" and row["code"] == "active_not_closed"
    assert row["result"]["folder"] == "project" and row["project_id"] == PROJECT


def test_cli_refusal_names_its_failed_step_and_never_starts(tmp_path):
    manager = operations.Operations(tmp_path, events.EventBus(),
        start=lambda _project_id: (_ for _ in ()).throw(AssertionError("start after refusal")),
        status=lambda _project_id: ("stopped", None),
        popen=fake_cli(code=1, steps=("admit",),
                       error="conduct projects add: refused tracks_product_dir: work\n"))
    row = settled(manager, manager.begin(PICK, "Project", True))
    assert row["state"] == "failed" and row["code"] == "tracks_product_dir"
    assert row["step"] == "git"
    assert row["result"] is None and row["project_id"] is None


def test_real_delayed_utf8_writer_does_not_lose_a_later_line(tmp_path):
    folder = "проект"
    result = {**RESULT, "folder": folder}
    lines = [json.dumps({"step": "admit"}, ensure_ascii=False),
             json.dumps({"result": result}, ensure_ascii=False)]
    code = ("import os,time; "
            f"os.write(1, ({lines[0]!r} + '\\n').encode('utf-8')); "
            "time.sleep(.2); "
            f"os.write(1, ({lines[1]!r} + '\\n').encode('utf-8'))")

    def launch(_argv, **kwargs):
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        return subprocess.Popen([sys.executable, "-c", code], **kwargs)

    manager = operations.Operations(tmp_path, events.EventBus(),
        start=lambda _project_id: None, status=lambda _project_id: ("running", None),
        popen=launch)
    row = settled(manager, manager.begin(PICK, "Имя проекта", True))
    assert row["state"] == "succeeded" and row["step"] == "start"
    assert row["result"]["folder"] == folder
    assert list(tmp_path.iterdir()) == []


def test_oversized_protocol_line_waits_for_child_exit_before_failure(tmp_path):
    exited = tmp_path / "child-exited"
    code = ("import os,time,pathlib; "
            f"os.write(1, b'x' * {operations.MAX_LINE_BYTES + 1}); "
            "time.sleep(.15); "
            f"pathlib.Path({str(exited)!r}).write_text('done')")

    def launch(_argv, **kwargs):
        return subprocess.Popen([sys.executable, "-c", code], **kwargs)

    manager = operations.Operations(tmp_path, events.EventBus(),
        start=lambda _project_id: (_ for _ in ()).throw(AssertionError("started")),
        status=lambda _project_id: ("running", None), popen=launch)
    row = settled(manager, manager.begin(PICK, "Project", True))
    assert row["state"] == "failed" and row["code"] == "subprocess_failed"
    assert exited.read_text() == "done"


def test_trailing_partial_line_after_result_is_a_protocol_failure(tmp_path):
    def launch(_argv, **kwargs):
        fake_cli()(None, **kwargs)
        kwargs["stdout"].write(b'{"step":')
        return Finished()

    manager = operations.Operations(tmp_path, events.EventBus(),
        start=lambda _project_id: (_ for _ in ()).throw(AssertionError("started")),
        status=lambda _project_id: ("running", None), popen=launch)
    row = settled(manager, manager.begin(PICK, "Project", True))
    assert row["state"] == "failed" and row["code"] == "subprocess_failed"
    assert row["result"] is None


# -- one ledger for every kind of operation (the recoveries and the profile copy join the adds) --


def _ledger(tmp_path, **options):
    return operations.Operations(tmp_path, events.EventBus(), start=lambda _p: None,
                                 status=lambda _p: ("running", None), **options)


def _add_held_at_start(tmp_path):
    """An add that has registered its project and waits, at `start`, for the child to be running.

    The wait is the status poll: the ledger's lock is free there (the `start` call itself is made
    under it), so the test can read the row while the add is held.
    """
    gate = threading.Event()
    manager = operations.Operations(
        tmp_path, events.EventBus(), start=lambda _p: None,
        status=lambda _p: ("running", None) if gate.is_set() else ("starting", None),
        popen=fake_cli())
    ident = manager.begin(PICK, "Project", True)
    for _ in range(300):
        if manager.get(ident)["step"] == "start":
            return manager, ident, gate
        time.sleep(0.01)
    gate.set()
    raise AssertionError("the add did not reach its start step")


def test_a_row_of_another_kind_does_not_make_an_add_busy_and_an_add_does_not_block_it(tmp_path):
    manager = _ledger(tmp_path, popen=fake_cli())
    ident = manager.open_project_row("recover", PROJECT, "recover")
    row = settled(manager, manager.begin(PICK, "Project", True))       # an add runs beside it
    assert row["state"] == "succeeded"
    assert manager.get(ident)["state"] == "running" and manager.get(ident)["kind"] == "recover"


def test_a_running_row_of_another_kind_does_not_stop_the_parent_folder_being_set(tmp_path):
    manager = _ledger(tmp_path)
    manager.open_project_row("providers", PROJECT, "providers")
    manager.open_login_row()
    assert manager.configure_parent(lambda: "changed") == "changed"


def test_a_running_add_still_stops_the_parent_folder_being_set_and_a_second_add(tmp_path):
    manager, ident, gate = _add_held_at_start(tmp_path)
    try:
        for refused in (lambda: manager.configure_parent(lambda: "changed"),
                        lambda: manager.begin(PICK, "Project", True)):
            with pytest.raises(refusals.HubRefusal) as busy:
                refused()
            assert busy.value.code == "operation_busy"
    finally:
        gate.set()
    assert settled(manager, ident)["state"] == "succeeded"


def test_an_add_row_of_the_same_project_does_not_count_against_its_own_operation(tmp_path):
    manager, ident, gate = _add_held_at_start(tmp_path)
    try:
        assert manager.get(ident)["project_id"] == PROJECT and manager.running_for(PROJECT) is None
        other = manager.open_project_row("recover", PROJECT, "recover")
        assert manager.running_for(PROJECT) == other
    finally:
        gate.set()
    assert settled(manager, ident)["state"] == "succeeded"


def test_a_second_operation_on_a_project_is_refused_while_one_runs_and_another_project_is_not(
        tmp_path):
    manager = _ledger(tmp_path)
    manager.open_project_row("providers", PROJECT, "providers")
    with pytest.raises(refusals.HubRefusal) as busy:
        manager.open_project_row("recover", PROJECT, "recover")
    assert busy.value.code == "project_busy"
    manager.open_project_row("recover", "b" * 32, "recover")           # another project: fine


def test_two_claims_on_one_project_cannot_both_win_when_the_rival_arrives_mid_check(tmp_path):
    manager = _ledger(tmp_path)
    rival_outcome: list[str] = []

    def rival() -> None:
        try:
            rival_outcome.append(manager.open_project_row("recover", PROJECT, "recover"))
        except refusals.HubRefusal as refused:
            rival_outcome.append(refused.code)

    real, arrivals = manager.running_for, []

    def running_for(project_id):
        found = real(project_id)
        if not arrivals:                       # the rival comes between the check and the claim
            arrivals.append(threading.Thread(target=rival))
            arrivals[0].start()
            arrivals[0].join(0.3)
        return found

    manager.running_for = running_for
    first = manager.open_project_row("providers", PROJECT, "providers")
    arrivals[0].join(5)
    assert rival_outcome == ["project_busy"]
    assert real(PROJECT) == first


def test_a_project_operation_row_has_the_form_of_4_6_4_and_ends_when_it_is_updated(tmp_path):
    manager = _ledger(tmp_path)
    ident = manager.open_project_row("recover", PROJECT, "recover")
    assert manager.get(ident) == {
        "operation_id": ident, "kind": "recover", "source": None, "state": "running",
        "step": "recover", "project_id": PROJECT, "code": None, "detail": None, "result": None}
    assert manager.running_for(PROJECT) == ident
    manager.update_row(ident, state="failed", code="recovery_refused")
    assert manager.running_for(PROJECT) is None


def test_a_login_row_has_no_project_and_the_step_of_its_own_kind(tmp_path):
    manager = _ledger(tmp_path)
    ident = manager.open_login_row()
    row = manager.get(ident)
    assert (row["kind"], row["step"], row["project_id"], row["source"]) == (
        "recover_login", "recover_login", None, None)
    assert row["operation_id"].startswith("operation-") and len(row["operation_id"]) == 42


def test_an_add_row_carries_the_null_detail_key_of_every_row(tmp_path):
    manager, ident, gate = _add_held_at_start(tmp_path)
    try:
        row = manager.get(ident)
        assert row["detail"] is None and list(row)[-3:] == ["code", "detail", "result"]
    finally:
        gate.set()
    assert settled(manager, ident)["detail"] is None


def test_opening_and_updating_a_row_publish_the_one_operation_frame_of_that_row(tmp_path):
    bus = events.EventBus()
    box = bus.register()
    manager = operations.Operations(tmp_path, bus, start=lambda _p: None,
                                    status=lambda _p: ("running", None))
    ident = manager.open_login_row()
    assert box.drain() == (events.encode(events.frame("operation", operation_id=ident)),)
    manager.update_row(ident, state="succeeded")
    assert box.drain() == (events.encode(events.frame("operation", operation_id=ident)),)


def test_a_row_carries_a_typed_reason_only_from_the_closed_list_and_only_on_subprocess_failed(
        tmp_path):
    manager = _ledger(tmp_path)
    ident = manager.open_project_row("providers", PROJECT, "providers")
    manager.update_row(ident, state="failed", code="subprocess_failed",
                       detail={"reason": "recovery_required"})
    assert manager.get(ident)["detail"] == {"reason": "recovery_required"}
    for bad in ({"reason": "free text from a command"}, {"reason": "recovery_required", "x": 1},
                {"path": "C:/x"}, "recovery_required", {"reason": ["recovery_required"]}, {}):
        with pytest.raises(ValueError):
            manager.update_row(ident, detail=bad)
    other = manager.open_project_row("recover", "b" * 32, "recover")
    with pytest.raises(ValueError):                      # not on any other code
        manager.update_row(other, state="failed", code="recovery_refused",
                           detail={"reason": "recovery_required"})


def test_a_refused_update_changes_nothing_of_the_row(tmp_path):
    manager = _ledger(tmp_path)
    ident = manager.open_project_row("recover", PROJECT, "recover")
    before = manager.get(ident)
    with pytest.raises(ValueError):
        manager.update_row(ident, state="failed", code="recovery_refused",
                           detail={"reason": "restart_needed"})
    assert manager.get(ident) == before


def test_a_code_that_would_strand_the_reason_already_on_a_row_is_refused(tmp_path):
    manager = _ledger(tmp_path)
    ident = manager.open_project_row("recover", PROJECT, "recover")
    manager.update_row(ident, state="failed", code="recovery_required",
                       detail={"reason": "prepare_needed"})
    with pytest.raises(ValueError):
        manager.update_row(ident, code="recovery_refused")
    assert manager.get(ident)["code"] == "recovery_required"
    manager.update_row(ident, detail=None)
    assert manager.get(ident)["detail"] is None


# The four recovery words stand beside the restart-family code of their own step and beside no
# other code; the providers word never stands beside the restart code.
RECOVERY_WORDS = ["restart_needed", "prepare_needed", "other_environment", "not_proven"]


@pytest.mark.parametrize("word", RECOVERY_WORDS)
def test_a_recovery_reason_stands_beside_the_restart_code_of_its_step_and_beside_no_other(
        tmp_path, word):
    manager = _ledger(tmp_path)
    project = manager.open_project_row("recover", PROJECT, "recover")
    manager.update_row(project, state="failed", code="recovery_required", detail={"reason": word})
    assert manager.get(project)["detail"] == {"reason": word}
    login = manager.open_login_row()
    manager.update_row(login, state="failed", code="login_recovery_required",
                       detail={"reason": word})
    assert manager.get(login)["detail"] == {"reason": word}
    for number, code in enumerate(("recovery_refused", "subprocess_failed", "transition_conflict")):
        other = manager.open_project_row("recover", f"{number:032x}", "recover")
        with pytest.raises(ValueError):
            manager.update_row(other, state="failed", code=code, detail={"reason": word})
    last = manager.open_project_row("recover", "e" * 32, "recover")
    with pytest.raises(ValueError):          # the providers word never stands beside this code
        manager.update_row(last, state="failed", code="recovery_required",
                           detail={"reason": "recovery_required"})


def test_the_closed_list_of_reasons_names_the_codes_each_may_stand_beside():
    reasons = refusals.OPERATION_DETAIL_REASONS
    assert set(reasons) == {"recovery_required", *RECOVERY_WORDS}
    assert set(reasons["recovery_required"]) == {"subprocess_failed"}
    for word in RECOVERY_WORDS:
        assert set(reasons[word]) == {"recovery_required", "login_recovery_required"}
    assert all(code in refusals.OPERATION_ERROR_CODES
               for codes in reasons.values() for code in codes)


def test_the_ledger_keeps_the_fifty_latest_rows_of_every_kind(tmp_path):
    manager = _ledger(tmp_path)
    first = manager.open_login_row()
    for _ in range(operations.LIMIT):
        done = manager.open_login_row()
        manager.update_row(done, state="succeeded")
    with pytest.raises(refusals.HubRefusal) as gone:
        manager.get(first)
    assert gone.value.code == "operation_not_found"
    assert manager.get(done)["state"] == "succeeded"
