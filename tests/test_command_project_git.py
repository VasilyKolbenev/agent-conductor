"""The read-only admission of a repository before a project is added (spec 9.2, 8.2 step 2).

Two kinds of witness. A scripted reader answers from a table and records every call, so each
branch and each argv is judged without git. Real repositories in a temporary folder then confirm
that the answers are the ones git gives and that admission writes nothing into `.git`.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conductor.command import product_names, project_git
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="git is not installed")
ISOLATED = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C"}


class Script:
    """A git reader that answers from a table and records what it was asked."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, args, separate_stderr=False):
        self.calls.append((tuple(args), separate_stderr))
        return self.answers.pop(0)


def said(output=b"", code=0, **flags):
    return project_git.GitAnswer(exit_code=code, output=output, **flags)


@pytest.fixture
def root(tmp_path):
    """A folder that has a `.git` entry, which is all a scripted reader needs to be asked."""
    folder = tmp_path / "project"
    (folder / ".git").mkdir(parents=True)
    return folder


def toplevel(folder):
    return str(folder).replace("\\", "/").encode() + b"\n"


def test_a_folder_with_no_git_directory_up_the_tree_answers_not_git_without_running_git(
        root, monkeypatch):
    monkeypatch.setattr(project_git.os.path, "lexists", lambda path: False)
    script = Script()
    assert project_git.repository_admission(root, script).state == "not_git"
    assert script.calls == []


@pytest.mark.parametrize("relative", ["project", "./project", "sub/project", Path("project"),
                                      Path("..") / "project", ""])
def test_a_relative_root_is_refused_before_anything_is_looked_at(relative, monkeypatch):
    looked = []
    monkeypatch.setattr(project_git.os.path, "lexists", lambda path: looked.append(path) or True)
    script = Script()
    with pytest.raises(ValueError, match="absolute"):
        project_git.repository_admission(relative, script)
    assert script.calls == [] and looked == []


@pytest.mark.skipif(os.name != "nt", reason="only Windows has rooted and drive-relative spellings")
@pytest.mark.parametrize("spelling", ["\\project", "/project", "C:project"])
def test_a_windows_spelling_that_names_no_drive_and_folder_together_is_refused(spelling):
    script = Script()
    with pytest.raises(ValueError, match="absolute"):
        project_git.repository_admission(spelling, script)
    assert script.calls == []


def test_an_absolute_root_given_as_text_is_admitted_like_a_path(root):
    script = Script(said(toplevel(root)), said(b""))
    assert project_git.repository_admission(str(root), script).state == "repo"


def test_a_toplevel_that_is_not_the_root_answers_not_repo_root(root):
    script = Script(said(toplevel(root.parent)))
    admission = project_git.repository_admission(root, script)
    assert (admission.state, admission.refusal) == ("not_repo_root", "project_not_repo_root")
    assert len(script.calls) == 1  # nothing is listed in a folder that is not the root


def test_tracked_product_names_answer_unsupported_and_name_them(root):
    tracked = b"instructions/plan.md\0work/a/b.txt\0work/c.txt\0.claude-home/x\0"
    script = Script(said(toplevel(root)), said(tracked))
    admission = project_git.repository_admission(root, script)
    assert (admission.state, admission.refusal) == ("unsupported", "tracks_product_dir")
    assert admission.tracked == (".claude-home", "instructions", "work")


def test_a_clean_root_answers_repo(root):
    admission = project_git.repository_admission(root, Script(said(toplevel(root)), said(b"")))
    assert (admission.state, admission.refusal, admission.tracked) == ("repo", None, ())


def test_dubious_ownership_answers_unsafe_directory(root):
    refusal = b"fatal: detected dubious ownership in repository at 'X'\n"
    script = Script(said(refusal, code=128))
    assert project_git.repository_admission(root, script).state == "unsafe_directory"


@pytest.mark.parametrize("answer,code", [
    (said(b"fatal: something else\n", code=128), "git_failed"),
    (said(b"", code=None, timed_out=True), "git_timed_out"),
])
def test_a_failed_or_timed_out_git_raises_git_read_failed(root, answer, code):
    with pytest.raises(project_git.GitReadFailed) as failed:
        project_git.repository_admission(root, Script(answer))
    assert failed.value.code == code


def test_a_failed_listing_raises_git_read_failed(root):
    with pytest.raises(project_git.GitReadFailed) as failed:
        project_git.repository_admission(root, Script(said(toplevel(root)), said(b"x", code=1)))
    assert failed.value.code == "git_failed"


def test_admission_runs_only_read_commands(root):
    script = Script(said(toplevel(root)), said(b""))
    project_git.repository_admission(root, script)
    verbs = [args[2:4] for args, _ in script.calls]
    assert verbs == [("rev-parse", "--show-toplevel"), ("ls-files", "-z")]
    for args, _ in script.calls:
        assert args[:2] == ("-C", str(root))


def test_the_pathspec_of_ls_files_is_exactly_the_product_top_names(root):
    script = Script(said(toplevel(root)), said(b""))
    project_git.repository_admission(root, script)
    listing = script.calls[1][0]
    assert listing[2:] == ("ls-files", "-z", "--", *product_names.PRODUCT_TOP_NAMES)


def test_the_listing_is_read_from_stdout_alone_and_the_probe_from_the_merged_stream(root):
    script = Script(said(toplevel(root)), said(b""))
    project_git.repository_admission(root, script)
    assert [flag for _, flag in script.calls] == [False, True]


def test_a_truncated_listing_still_refuses(root):
    script = Script(said(toplevel(root)), said(b"work/a.txt\0", truncated=True))
    assert project_git.repository_admission(root, script).state == "unsupported"


def test_process_git_read_puts_the_permanent_flags_before_the_arguments(tmp_path):
    seen = []

    class Runner:
        def run(self, spec):
            seen.append(spec)
            return ProcessOutcome(status="completed", exit_code=0, output=b"ok",
                                  output_truncated=False, output_limit=spec.output_limit,
                                  pid=1, token="t")
    read = project_git.process_git_read(Runner(), "/pinned/git", str(tmp_path))
    answer = read(["rev-parse", "--show-toplevel"], separate_stderr=True)
    spec = seen[0]
    assert spec.argv[:1] == ("/pinned/git",)
    assert spec.argv[1:7] == project_git.GIT_FLAGS
    assert spec.argv[7:] == ("rev-parse", "--show-toplevel")
    assert spec.separate_stderr is True and spec.timeout_seconds == project_git.READ_TIMEOUT_SECONDS
    assert (answer.exit_code, answer.output, answer.timed_out) == (0, b"ok", False)


# --- real repositories ----------------------------------------------------------------------


def git(*args, cwd):
    environment = {**os.environ, **ISOLATED}
    return subprocess.run([GIT, *args], cwd=cwd, env=environment, capture_output=True, text=True)


@pytest.fixture
def reader(tmp_path):
    """A reader over the real runner, standing in the folder a caller would give it."""
    home = tmp_path / "runner-home"
    (home / "cwd").mkdir(parents=True)
    kept = ("SystemRoot", "PATH", "HOME", "USERPROFILE", "TEMP", "TMP")
    runner = ProcessRunner(home, environ={name: os.environ[name] for name in kept
                                          if name in os.environ})
    return project_git.process_git_read(runner, GIT, str(home / "cwd"), env_allow=kept,
                                        env=ISOLATED)


def repository(tmp_path, name="repo"):
    folder = tmp_path / name
    folder.mkdir()
    assert git("init", "-q", cwd=folder).returncode == 0
    return folder


def snapshot(git_dir):
    return {path.relative_to(git_dir).as_posix(): path.read_bytes()
            for path in sorted(git_dir.rglob("*")) if path.is_file()}


@needs_git
def test_a_subfolder_of_a_repository_is_not_a_repo_root(tmp_path, reader):
    inside = repository(tmp_path) / "packages" / "app"
    inside.mkdir(parents=True)
    assert project_git.repository_admission(inside, reader).state == "not_repo_root"


@needs_git
def test_a_repository_that_tracks_work_and_instructions_is_unsupported(tmp_path, reader):
    folder = repository(tmp_path)
    for relative in ("work/a.txt", "instructions/b.md", "src/ok.py"):
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_text("x")
    assert git("add", "-A", cwd=folder).returncode == 0
    admission = project_git.repository_admission(folder, reader)
    assert (admission.state, admission.tracked) == ("unsupported", ("instructions", "work"))


@needs_git
def test_a_clean_repository_is_admitted_and_admission_writes_nothing(tmp_path, reader):
    folder = repository(tmp_path)
    (folder / "src").mkdir()
    (folder / "src" / "main.py").write_text("print()")
    assert git("add", "-A", cwd=folder).returncode == 0
    before = snapshot(folder / ".git")
    assert project_git.repository_admission(folder, reader).state == "repo"
    assert snapshot(folder / ".git") == before


@needs_git
def test_an_unborn_repository_is_admitted(tmp_path, reader):
    assert project_git.repository_admission(repository(tmp_path), reader).state == "repo"


@needs_git
def test_untracked_product_folders_do_not_stop_admission(tmp_path, reader):
    folder = repository(tmp_path)
    (folder / "work").mkdir()
    (folder / "work" / "task.txt").write_text("x")
    assert project_git.repository_admission(folder, reader).state == "repo"


@needs_git
def test_process_git_read_runs_git_through_the_runner(reader):
    answer = reader(["--version"], separate_stderr=True)
    assert answer.exit_code == 0 and answer.output.startswith(b"git version")
    assert not answer.timed_out and not answer.truncated
