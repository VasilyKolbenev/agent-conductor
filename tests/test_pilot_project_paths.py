"""The two-task pilot publishes the operator's receipt and can replay the original source."""
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory, gettempdir
from zipfile import ZipFile

import pytest

from conductor.command import run_store
from conductor.command.long_path import extended
from conductor.command.path_admission import WindowsNameError, WindowsPathError
from conductor.command.run_store import RunStore
from conductor.command.task_store import TaskStore
from tests.test_command_run_store import CONFIG, a_decision, a_run


CREATE = Path(__file__).resolve().parents[1] / "distribution/windows-two-task/first_task.py"


def test_windows_archive_verifies_the_same_offline_example_it_opens(tmp_path):
    builder = run_path(str(CREATE.with_name("build.py")))
    wheel = tmp_path / builder["WHEEL"]
    wheel.write_bytes(b"sample wheel bytes")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    archive = builder["build"](wheel, digest, tmp_path)
    assert archive.name == "Arachnid-Studio-Windows.zip"
    assert archive.with_suffix(".zip.sha256").read_text().split() == [
        hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name]
    extracted = tmp_path / "extracted"
    with ZipFile(archive) as package:
        package.extractall(extracted)
    launcher = run_path(str(extracted / "pilot.py"))
    assert launcher["verify"]() == digest
    project = tmp_path / "project"
    launcher["unpack_demo"](project)
    assert RunStore(project).read("demo-codex-grok").envelope.run_id == "demo-codex-grok"
    assert (project / "test-output.txt").is_file()
    (extracted / "demo.zip").write_bytes(b"unexpected demo")
    with pytest.raises(ValueError, match="demo.zip"):
        launcher["verify"]()
    manifest = extracted / "SHA256SUMS.txt"
    changed = hashlib.sha256(b"unexpected demo").hexdigest()
    manifest.write_text(manifest.read_text("ascii").replace(launcher["DEMO_SHA256"], changed),
                        encoding="ascii")
    with pytest.raises(ValueError, match="demo.zip"):
        launcher["verify"]()


@contextmanager
def personal_project(deep, pytest_base):
    # A runner may export RUNNER~1 as TEMP. Admission measures the expanded path.
    for base in dict.fromkeys((Path(gettempdir()).resolve(), pytest_base.resolve())):
        with TemporaryDirectory(dir=extended(base)) as temporary:
            parent = base / Path(temporary).name
            parent_units = len(str(parent).encode("utf-16-le")) // 2
            if parent_units >= 142:
                continue
            if deep:
                prefix = "Проверка "
                width = 142 - parent_units - 1
                if width < len(prefix):
                    continue
                parent = parent / (prefix + "я" * (width - len(prefix)))
                parent.mkdir()
                assert len(str(parent.resolve()).encode("utf-16-le")) == 142 * 2
            yield parent / "personal"
            return
    pytest.fail("The path fixture needs a shorter pytest --basetemp for its 142-unit parent.")


@pytest.mark.parametrize("deep", [False, True], ids=["short", "long"])
def test_pilot_reopens_both_tasks_and_the_same_accepted_procedure(deep, tmp_path_factory):
    with personal_project(deep, tmp_path_factory.getbasetemp()) as project:
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


def test_interrupted_publish_keeps_the_winning_project_and_removes_its_private_stage(
        monkeypatch, tmp_path_factory):
    rename = Path.rename
    with personal_project(True, tmp_path_factory.getbasetemp()) as project:
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


@pytest.mark.skipif(os.name != "nt", reason="Windows creation budgets")
def test_pilot_refuses_a_genuinely_over_budget_root_and_removes_its_stage(tmp_path_factory):
    with personal_project(True, tmp_path_factory.getbasetemp()) as admitted:
        parent = admitted.parent / "ЯЯ"
        parent.mkdir()
        assert len(str(parent.resolve()).encode("utf-16-le")) == 145 * 2
        with pytest.raises(WindowsPathError, match="run_id exceeds the Windows path budget"):
            run_path(str(CREATE))["create"](
                parent / "personal", "One", "Two", [("Check", "Seen")], "Owner", accepted=True)
        assert list(parent.iterdir()) == []


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
