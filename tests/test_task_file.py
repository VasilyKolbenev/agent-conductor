"""The task of a file-channel provider is written once, exactly, into a home this build minted (I1).

A vendor whose headless mode reads its prompt only from a file (`--prompt-file <path>`) gets the
task as one new file in the home of its attempt. What is held here, at the module's own seam:

- the path is a function of the home and of one constant name, and carries nothing of the task;
- the bytes in the file are the bytes asked for, whole, and nothing is appended;
- the home must be an attempt home of the project (a direct child of its home root) or a relay
  home (`<relay>/<16 hex>/<letter>-<16 hex>`): never a login folder, the work tree, or any other
  place the path could be pointed at;
- the payload is refused before anything is written unless it is bytes, in the stdin bound, free
  of NUL, strict UTF-8 and not only white space;
- the file is created new and is read back; a file that is not exactly what was asked for, or has
  a second link, is removed, and so is a file whose write failed;
- EVERY failure of the disk is the module's own refusal, because a raw OS error raised under the
  shared login lease would poison that login until the machine restarts (`relay_attempt`).

The expected names and sentences are spelled here by hand and never read from the module.
"""
from __future__ import annotations

import os
import types
from pathlib import Path

import pytest

from conductor.command.adapters import task_file
from conductor.command.adapters.process import STDIN_LIMIT, ProcessRunnerError

NAME = "conduct-task.txt"
KEY = "0123456789abcdef"
SENTENCE = "the task file could not be placed"


class _Os:
    """`os` for the module under test alone, with some names replaced.

    The module reaches the disk only through the name `os`, so replacing THAT name in the module
    changes nothing for the test runner, the temporary folder or any other module.
    """

    def __init__(self, **replaced) -> None:
        self._replaced = replaced

    def __getattr__(self, name):
        return self._replaced[name] if name in self._replaced else getattr(os, name)


def _homes(tmp_path: Path) -> Path:
    root = tmp_path / ".probe-home"
    root.mkdir()
    return root


def _project_home(tmp_path: Path) -> tuple[Path, Path]:
    root = _homes(tmp_path)
    home = root / "probe-home-1"
    home.mkdir()
    return home, root


def _relay_home(tmp_path: Path, letter: str = "x") -> Path:
    home = tmp_path / "DecemberCommand" / "relay" / KEY / f"{letter}-fedcba9876543210"
    home.mkdir(parents=True)
    return home


def _standing(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def test_the_path_is_the_one_name_beneath_the_home_and_nothing_else(tmp_path):
    home = tmp_path / "an-attempt-home"

    assert task_file.path_in(home) == str(home / NAME)
    assert task_file.path_in(str(home)) == str(home / NAME)


@pytest.mark.parametrize("payload", [
    b"plain task text",
    "Задача: прочитать файл и ответить. \U0001F642\r\n".encode("utf-8"),
    b"  leading and trailing space is the task's own  \n",
    b"x" * STDIN_LIMIT,
], ids=["ascii", "utf8", "spaces", "at-the-bound"])
def test_a_project_home_receives_exactly_the_bytes_and_nothing_else(tmp_path, payload):
    home, root = _project_home(tmp_path)

    placed = task_file.place(home, payload, root)

    assert placed == str(home / NAME)
    assert (home / NAME).read_bytes() == payload
    assert os.stat(home / NAME).st_nlink == 1
    assert _standing(home) == [NAME]


@pytest.mark.parametrize("letter", ["c", "x"])
def test_a_relay_home_receives_the_bytes_too(tmp_path, letter):
    home = _relay_home(tmp_path, letter)

    placed = task_file.place(home, b"the relay task", _homes(tmp_path))

    assert placed == str(home / NAME)
    assert (home / NAME).read_bytes() == b"the relay task"
    assert _standing(home) == [NAME]


def _elsewhere(tmp_path: Path) -> dict[str, Path]:
    """Folders that stand, that a path could be pointed at, and that are no attempt home."""
    root = _homes(tmp_path)
    keyed = tmp_path / "DecemberCommand" / "relay" / KEY
    named = {
        "the home root itself": root,
        "a grandchild of the home root": root / "probe-home-1" / "nested",
        "a login folder": tmp_path / "DecemberCommand" / "logins" / "grok-build",
        "the work tree": tmp_path / "root" / "work" / "work-001",
        "a relay-named folder outside a relay": tmp_path / "x-fedcba9876543210",
        "a relay-named folder in logins": tmp_path / "DecemberCommand" / "logins" / KEY / "x-1",
        "a relay home with a key that is no key": (
            tmp_path / "DecemberCommand" / "relay" / "not-a-key" / "x-fedcba9876543210"),
        "a relay folder with another letter": keyed / "z-fedcba9876543210",
        "a relay folder with a short name": keyed / "x-fedcba987654321",
        "a relay folder with an upper-case name": keyed / "x-FEDCBA9876543210",
    }
    for folder in named.values():
        folder.mkdir(parents=True, exist_ok=True)
    return named


@pytest.mark.parametrize("which", [
    "the home root itself", "a grandchild of the home root", "a login folder", "the work tree",
    "a relay-named folder outside a relay", "a relay-named folder in logins",
    "a relay home with a key that is no key", "a relay folder with another letter",
    "a relay folder with a short name", "a relay folder with an upper-case name"])
def test_a_folder_that_is_no_attempt_home_is_refused_and_nothing_is_written(tmp_path, which):
    named = _elsewhere(tmp_path)

    with pytest.raises(task_file.TaskFileRefused) as refused:
        task_file.place(named[which], b"a task", tmp_path / ".probe-home")

    assert sorted(path.name for path in tmp_path.rglob(NAME)) == []
    assert str(refused.value).startswith(SENTENCE)


def test_a_home_that_does_not_stand_is_the_modules_refusal_and_not_an_os_error(tmp_path):
    root = _homes(tmp_path)

    with pytest.raises(task_file.TaskFileRefused):
        task_file.place(root / "probe-home-1", b"a task", root)


@pytest.mark.parametrize("payload", [
    b"", b" \r\n\t ", b"a\x00b", b"\xff\xfe\xfa", b"x" * (STDIN_LIMIT + 1),
    "text, not bytes", None, bytearray(b"bytes of another type"), 7,
], ids=["empty", "blank", "nul", "not-utf8", "over-the-bound", "str", "none", "bytearray", "int"])
def test_a_payload_that_is_not_a_task_is_refused_before_anything_is_written(tmp_path, payload):
    home, root = _project_home(tmp_path)

    with pytest.raises(task_file.TaskFileRefused):
        task_file.place(home, payload, root)

    assert _standing(home) == []


def test_a_file_that_already_stands_is_refused_and_is_neither_replaced_nor_removed(tmp_path):
    home, root = _project_home(tmp_path)
    (home / NAME).write_bytes(b"somebody else's file")

    with pytest.raises(task_file.TaskFileRefused):
        task_file.place(home, b"a task", root)

    assert (home / NAME).read_bytes() == b"somebody else's file"


def test_a_write_that_takes_a_few_bytes_at_a_time_still_lands_whole(monkeypatch, tmp_path):
    home, root = _project_home(tmp_path)
    real = os.write
    monkeypatch.setattr(task_file, "os", _Os(
        write=lambda descriptor, data: real(descriptor, bytes(data[:3]))))

    task_file.place(home, b"0123456789 whole task", root)

    assert (home / NAME).read_bytes() == b"0123456789 whole task"


def test_a_write_that_takes_no_byte_is_a_refusal_and_not_a_loop(monkeypatch, tmp_path):
    home, refused = _refused_with(monkeypatch, tmp_path, write=lambda descriptor, data: 0)

    assert not (home / NAME).exists()
    assert str(refused).startswith(SENTENCE)


def _refused_with(monkeypatch, tmp_path, **replaced):
    """Place a task with some of the module's disk calls replaced; what it raised."""
    home, root = _project_home(tmp_path)
    monkeypatch.setattr(task_file, "os", _Os(**replaced))
    with pytest.raises(task_file.TaskFileRefused) as refused:
        task_file.place(home, b"a task with a private sentence", root)
    return home, refused.value


def _tell(name):
    def raising(*arguments, **options):
        raise PermissionError(13, f"{name} said no to a path under the temporary folder")
    return raising


def _close_then_fail(descriptor):
    """A close that really closes (Windows cannot remove an open file) and then says it failed."""
    os.close(descriptor)
    raise PermissionError(13, "close said no to a path under the temporary folder")


@pytest.mark.parametrize("call", ["open", "write", "lseek", "read", "fstat", "close"])
def test_every_failure_of_the_disk_is_the_modules_refusal_and_leaves_no_file(
        monkeypatch, tmp_path, call):
    failing = _close_then_fail if call == "close" else _tell(call)
    home, refused = _refused_with(monkeypatch, tmp_path, **{call: failing})

    assert isinstance(refused, ProcessRunnerError) and not isinstance(refused, OSError)
    assert not (home / NAME).exists(), "a file the write could not finish was left standing"
    said = str(refused)
    assert said.startswith(SENTENCE)
    assert str(tmp_path) not in said and "private sentence" not in said and "said no" not in said


def test_a_value_error_of_the_disk_is_wrapped_as_well(monkeypatch, tmp_path):
    def broken(*arguments):
        raise ValueError("a descriptor the kernel refused to count")
    home, refused = _refused_with(monkeypatch, tmp_path, write=broken)

    assert not (home / NAME).exists()
    assert "kernel" not in str(refused)


def test_a_read_back_that_is_not_the_payload_removes_the_file(monkeypatch, tmp_path):
    home, _refused = _refused_with(
        monkeypatch, tmp_path, read=lambda descriptor, size: b"another task altogether")

    assert not (home / NAME).exists()


def test_a_file_longer_than_the_payload_is_not_the_payload(monkeypatch, tmp_path):
    real = os.read
    home, _refused = _refused_with(
        monkeypatch, tmp_path, read=lambda descriptor, size: real(descriptor, size) + b"!")

    assert not (home / NAME).exists()


def test_a_second_hard_link_removes_the_file(monkeypatch, tmp_path):
    real = os.fstat

    def linked(descriptor):
        found = real(descriptor)
        return types.SimpleNamespace(st_nlink=2, st_size=found.st_size, st_mode=found.st_mode)
    home, _refused = _refused_with(monkeypatch, tmp_path, fstat=linked)

    assert not (home / NAME).exists()


def test_a_removal_that_fails_after_a_refusal_is_not_what_the_caller_sees(monkeypatch, tmp_path):
    home, refused = _refused_with(
        monkeypatch, tmp_path, read=lambda descriptor, size: b"not it", unlink=_tell("unlink"))

    assert isinstance(refused, task_file.TaskFileRefused)
    assert "unlink" not in str(refused)
    assert (home / NAME).exists(), "the removal was made to fail, so the file must still stand"


def test_a_refused_placement_does_not_remove_a_file_it_did_not_create(monkeypatch, tmp_path):
    home, root = _project_home(tmp_path)
    (home / NAME).write_bytes(b"theirs")
    seen = []
    monkeypatch.setattr(task_file, "os", _Os(unlink=lambda path: seen.append(path)))

    with pytest.raises(task_file.TaskFileRefused):
        task_file.place(home, b"a task", root)

    assert seen == [] and (home / NAME).read_bytes() == b"theirs"
