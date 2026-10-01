"""The folder-add operation keeps progress and a safe result across the start step."""
from __future__ import annotations

import json
import subprocess
import sys
import time

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
