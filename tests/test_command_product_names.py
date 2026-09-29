"""The product's own top-level names and the block that keeps them out of a repository (spec 9.2).

`PRODUCT_TOP_NAMES` is derived from the constants that own each name. The guards here rebuild the
expected list from those owners, and from the provider catalog for the harness folders, so a
harness added to the catalog and forgotten in the module turns a test red (L14).
"""
import ast
import fnmatch
import importlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conductor import ownership_records
from conductor.command import product_names as names
from conductor.command import work_layout
from conductor.command.adapters import agent_instructions, harness_workspace
from conductor.command.providers import PROVIDER_CATALOG

SOURCE = Path(names.__file__).resolve().parent
ADAPTERS = SOURCE / "adapters"
#: Spelled from spec 9.2 and 8.1: the first five lines of the block, then one folder line and one
#: marker line per harness.
BLOCK_HEAD = ["/conductor/", "/conductor.v3/", "/.conduct*", "/work/", "/instructions/"]


def harness_names():
    """Every catalogued harness's (home folder, marker), read off its own adapter module."""
    modules = {entry.adapter_class.__module__ for entry in PROVIDER_CATALOG.values()}
    return {(module.HOME_DIR, module.MARKER_DIR)
            for module in map(importlib.import_module, sorted(modules))}


def test_product_top_names_are_rebuilt_from_the_constants_that_own_them():
    expected = [ownership_records.HOME, ownership_records.LEGACY, ownership_records.ACTIVE,
                f"{ownership_records.HOME}-retired-*", ".conduct-seed",
                work_layout.WORK_DIR, harness_workspace.INSTRUCTION_DIR]
    for home, marker in harness_names():
        expected += [home, marker]
    assert len(harness_names()) == len(PROVIDER_CATALOG) == 5
    assert sorted(names.PRODUCT_TOP_NAMES) == sorted(expected)


def test_every_module_that_declares_a_harness_home_is_a_catalogued_adapter_module():
    declaring = set()
    for path in sorted(ADAPTERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assigned = {target.id for node in tree.body if isinstance(node, ast.Assign)
                    for target in node.targets if isinstance(target, ast.Name)}
        if {"HOME_DIR", "MARKER_DIR"} <= assigned:
            declaring.add(f"conductor.command.adapters.{path.stem}")
    catalogued = {entry.adapter_class.__module__ for entry in PROVIDER_CATALOG.values()}
    assert declaring == catalogued


def test_the_retired_pattern_is_the_name_ownership_transition_renames_to():
    source = (SOURCE.parent / "ownership_transition.py").read_text(encoding="utf-8")
    assert 'HOME + "-retired-"' in source
    assert names.RETIRED_PATTERN == f"{ownership_records.HOME}-retired-*"


def test_harness_folder_names_are_read_from_the_catalog_and_never_spelled_in_the_module():
    source = Path(names.__file__).read_text(encoding="utf-8")
    for home, marker in harness_names():
        assert home not in source and marker not in source
    assert names._HARNESS_NAMES == tuple(sorted(harness_names()))


def test_product_top_names_are_single_components_without_repeats():
    assert isinstance(names.PRODUCT_TOP_NAMES, tuple)
    assert len(set(names.PRODUCT_TOP_NAMES)) == len(names.PRODUCT_TOP_NAMES) == 17
    assert not [name for name in names.PRODUCT_TOP_NAMES if "/" in name or "\\" in name or not name]


def test_agent_instruction_names_are_the_six_of_spec_9_2():
    assert names.AGENT_INSTRUCTION_NAMES == (
        "AGENTS.md", "CLAUDE.md", ".claude/", ".codex/", ".grok/", ".kimi/")


def test_agent_instruction_names_live_beside_the_adapters_and_product_names_hands_them_on():
    assert names.AGENT_INSTRUCTION_NAMES is agent_instructions.AGENT_INSTRUCTION_NAMES
    source = Path(names.__file__).read_text(encoding="utf-8")
    assert "CLAUDE" not in source and ".codex" not in source, (
        "the request path names no vendor: the names are the adapters' to spell")


def test_exclude_lines_are_the_single_spelling_of_spec_9_2():
    lines = list(names.EXCLUDE_LINES)
    assert lines[:5] == BLOCK_HEAD
    assert lines[5:7] == ["/.claude-home/", "/.claude-marker"]  # the example of spec 8.1
    tail = []
    for home, marker in sorted(harness_names()):  # by name, so a new harness slots in by itself
        tail += [f"/{home}/", f"/{marker}"]
    assert lines[5:] == tail


def test_the_exclude_lines_name_the_folder_and_marker_of_every_harness_exactly_once():
    lines = set(names.EXCLUDE_LINES)
    for home, marker in harness_names():
        assert f"/{home}/" in lines and f"/{marker}" in lines
    assert len(lines) == len(names.EXCLUDE_LINES)


def test_the_exclude_lines_cover_every_product_top_name():
    patterns = [line.strip("/") for line in names.EXCLUDE_LINES]
    for name in names.PRODUCT_TOP_NAMES:
        sample = name.replace("*", "x")
        assert any(fnmatch.fnmatchcase(sample, pattern) for pattern in patterns), name


# --- write_exclude_block --------------------------------------------------------------------

BEGIN, END = b"# conduct", b"# /conduct"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def the_block(newline=b"\n"):
    """The block the writer must produce, spelled from the module's own lines."""
    body = [BEGIN, names.BLOCK_NOTE.encode(), *(line.encode() for line in names.EXCLUDE_LINES), END]
    return newline.join(body) + newline


def repo_dir(tmp_path):
    """A `.git` directory with no `info` folder yet: as small as a repository can be."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return git_dir


def exclude_file(git_dir):
    return git_dir / "info" / "exclude"


def with_owner_file(tmp_path, content):
    git_dir = repo_dir(tmp_path)
    (git_dir / "info").mkdir()
    exclude_file(git_dir).write_bytes(content)
    return git_dir


def test_a_missing_git_dir_answers_not_git_and_writes_nothing(tmp_path):
    assert names.write_exclude_block(tmp_path / ".git") == "not_git"
    assert list(tmp_path.iterdir()) == []


def test_a_git_dir_that_is_a_file_answers_deferred_and_writes_nothing(tmp_path):
    linked = tmp_path / ".git"
    linked.write_bytes(b"gitdir: ../elsewhere/.git/worktrees/w\n")
    assert names.write_exclude_block(linked) == "deferred"
    assert linked.read_bytes() == b"gitdir: ../elsewhere/.git/worktrees/w\n"
    assert [path.name for path in tmp_path.iterdir()] == [".git"]


def test_a_first_write_creates_the_block_and_answers_written(tmp_path):
    git_dir = repo_dir(tmp_path)
    assert names.write_exclude_block(git_dir) == "written"
    assert exclude_file(git_dir).read_bytes() == the_block()
    assert [path.name for path in (git_dir / "info").iterdir()] == ["exclude"]


def test_the_owner_lines_before_and_after_the_block_are_kept_byte_for_byte(tmp_path):
    before, after = b"# mine\n*.log\n", b"secret.txt\n  spaced  \n"
    old_block = b"# conduct\n/old-name/\n# /conduct\n"
    git_dir = with_owner_file(tmp_path, before + old_block + after)
    assert names.write_exclude_block(git_dir) == "written"
    assert exclude_file(git_dir).read_bytes() == before + the_block() + after


def test_writing_the_same_block_again_answers_present_and_leaves_the_bytes_alone(tmp_path):
    git_dir = with_owner_file(tmp_path, b"*.log\n")
    assert names.write_exclude_block(git_dir) == "written"
    written = exclude_file(git_dir).read_bytes()
    stamp = exclude_file(git_dir).stat().st_mtime_ns
    assert names.write_exclude_block(git_dir) == "present"
    assert exclude_file(git_dir).read_bytes() == written
    assert exclude_file(git_dir).stat().st_mtime_ns == stamp
    assert written.count(BEGIN + b"\n") == 1


def test_a_block_that_differs_is_replaced_and_nothing_else_moves(tmp_path):
    git_dir = with_owner_file(tmp_path, b"keep-1\n" + the_block().replace(
        b"/work/", b"/elsewhere/") + b"keep-2\n")
    assert names.write_exclude_block(git_dir) == "written"
    assert exclude_file(git_dir).read_bytes() == b"keep-1\n" + the_block() + b"keep-2\n"


def test_a_file_without_a_final_newline_gets_one_before_the_block(tmp_path):
    git_dir = with_owner_file(tmp_path, b"*.log")
    assert names.write_exclude_block(git_dir) == "written"
    assert exclude_file(git_dir).read_bytes() == b"*.log\n" + the_block()


def test_a_crlf_file_keeps_its_line_endings_and_is_recognised(tmp_path):
    git_dir = with_owner_file(tmp_path, b"*.log\r\n")
    assert names.write_exclude_block(git_dir) == "written"
    assert exclude_file(git_dir).read_bytes() == b"*.log\r\n" + the_block(b"\r\n")
    assert names.write_exclude_block(git_dir) == "present"


def test_an_unterminated_block_is_refused_and_the_file_is_untouched(tmp_path):
    damaged = b"a\n# conduct\n/old/\nowner-line\n"
    git_dir = with_owner_file(tmp_path, damaged)
    with pytest.raises(names.ExcludeWriteError) as refused:
        names.write_exclude_block(git_dir)
    assert refused.value.code == "git_exclude_failed"
    assert exclude_file(git_dir).read_bytes() == damaged


def test_the_block_writer_starts_no_process(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the exclude block is a file write; no process may start")
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(os, "system", refuse)
    assert names.write_exclude_block(repo_dir(tmp_path)) == "written"


def test_an_info_exclude_that_is_a_symlink_is_refused_and_untouched(tmp_path):
    git_dir = repo_dir(tmp_path)
    (git_dir / "info").mkdir()
    shared = tmp_path / "shared-exclude"
    shared.write_bytes(b"shared\n")
    try:
        os.symlink(shared, exclude_file(git_dir))
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let the test create a symlink")
    with pytest.raises(names.ExcludeWriteError):
        names.write_exclude_block(git_dir)
    assert shared.read_bytes() == b"shared\n" and exclude_file(git_dir).is_symlink()


def test_an_info_that_is_a_file_is_refused(tmp_path):
    git_dir = repo_dir(tmp_path)
    (git_dir / "info").write_bytes(b"not a folder")
    with pytest.raises(names.ExcludeWriteError):
        names.write_exclude_block(git_dir)


def test_a_failed_replace_raises_the_exclude_error_and_leaves_no_temporary_file(
        tmp_path, monkeypatch):
    git_dir = with_owner_file(tmp_path, b"*.log\n")

    def broken(source, target):
        raise OSError("the disk went away")
    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(names.ExcludeWriteError) as refused:
        names.write_exclude_block(git_dir)
    assert str(tmp_path) not in str(refused.value)
    assert [path.name for path in (git_dir / "info").iterdir()] == ["exclude"]
    assert exclude_file(git_dir).read_bytes() == b"*.log\n"


def git(*args, cwd):
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], cwd=cwd, env=environment, capture_output=True, text=True)


@needs_git
def test_git_honours_the_block_it_is_given(tmp_path):
    assert git("init", "-q", cwd=tmp_path).returncode == 0
    assert names.write_exclude_block(tmp_path / ".git") == "written"
    made = [f"{name.replace('*', 'x')}/inside.txt" for name in names.PRODUCT_TOP_NAMES]
    for relative in made:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print()")
    for relative in made:
        assert git("check-ignore", "-q", relative, cwd=tmp_path).returncode == 0, relative
    for _home, marker in harness_names():  # a marker is excluded as a file too
        assert git("check-ignore", "-q", marker, cwd=tmp_path).returncode == 0, marker
    assert git("check-ignore", "-q", "src/main.py", cwd=tmp_path).returncode == 1
    status = git("status", "--porcelain", "--untracked-files=all", cwd=tmp_path).stdout
    assert status.split() == ["??", "src/main.py"]
