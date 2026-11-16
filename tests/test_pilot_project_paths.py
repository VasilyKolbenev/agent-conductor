"""The two-task pilot publishes the operator's receipt and can replay the original source."""
import json
import os
from contextlib import contextmanager
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory, gettempdir

import pytest

from conductor.command import run_store
from conductor.command.long_path import extended
from conductor.command.path_admission import WindowsNameError
from conductor.command.run_store import RunStore
from conductor.command.task_store import TaskStore
from tests.test_command_run_store import CONFIG, a_decision, a_run


CREATE = Path(__file__).resolve().parents[1] / "distribution/windows-two-task/first_task.py"


@contextmanager
def personal_project(deep):
    with TemporaryDirectory(dir=extended(gettempdir())) as temporary:
        parent = Path(gettempdir()) / Path(temporary).name
        if deep:
            prefix = "Проверка "
            width = 142 - len(str(parent).encode("utf-16-le")) // 2 - 1
            if width < len(prefix):
                pytest.skip("temporary base exceeds the controlled Windows admission boundary")
            parent = parent / (prefix + "я" * (width - len(prefix)))
            assert len(str(parent).encode("utf-16-le")) == 142 * 2
            parent.mkdir()
        yield parent / "personal"


@pytest.mark.parametrize("deep", [False, True], ids=["short", "long"])
def test_pilot_reopens_both_tasks_and_the_same_accepted_procedure(deep):
    with personal_project(deep) as project:
        run, second = run_path(str(CREATE))["create"](
            project, "Первая", "Вторая", [("Сверить сумму", "Итого 20")], "Василий", accepted=True)
        store = RunStore(project)
        saved = store.read(run)
        assert [row.kind for row in saved.records] == [
            "graph_definition", "artifact", "decision", "run_terminal"]
        note = json.loads(saved.records[1].value.content)
        assert note["checks"] == [{"step": "Сверить сумму", "result": "Итого 20"}]
        assert TaskStore(project).read(note["task_id"]).title == "Первая"
        assert TaskStore(project).read(second).title == "Вторая"
        receipt = saved.records[2].value
        assert receipt.action == "approve" and saved.records[-1].value.state == "complete"
        path = store.run_path(run) / "decisions" / (receipt.receipt_id + ".json")
        if deep:
            assert len(str(path).encode("utf-16-le")) >= 260 * 2
        assert json.loads(Path(extended(path)).read_bytes())["record"] == receipt.as_dict()
        assert RunStore(project).read(run) == saved


def test_interrupted_publish_keeps_the_winning_project_and_removes_its_private_stage(monkeypatch):
    rename = Path.rename
    with personal_project(True) as project:
        def another_publisher_wins(source, target):
            if target == project:
                target.mkdir()
                (target / "winner.txt").write_bytes(b"existing project")
            return rename(source, target)

        monkeypatch.setattr(Path, "rename", another_publisher_wins)
        with pytest.raises(OSError):
            run_path(str(CREATE))["create"](
                project, "One", "Two", [("Check", "Seen")], "Reviewer", accepted=True)
        assert list(project.parent.iterdir()) == [project]
        assert [p.name for p in project.iterdir()] == ["winner.txt"]
        assert (project / "winner.txt").read_bytes() == b"existing project"


@pytest.mark.skipif(os.name != "nt", reason="Windows device-name semantics")
def test_a_reserved_receipt_name_is_refused_before_windows_file_publication(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)

    def unexpected_write(*args):
        pytest.fail("a DOS device name reached file publication")

    monkeypatch.setattr(run_store, "_exclusive_bytes", unexpected_write)
    with pytest.raises(WindowsNameError, match="reserved Windows basename"):
        store.append(a_decision(receipt_id="NUL"))
    assert store.read("run-001").records == ()
