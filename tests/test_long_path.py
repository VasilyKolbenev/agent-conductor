"""`extended`: the one place that decides how a path that may be deep is named to the system.

Every walk and removal of a tree a child writes in passes its path through it
(`test_long_path_attempt`, `test_long_path_homes`), so what it answers is pinned here, on its own.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from conductor.command.long_path import extended
from tests._deep_tree import named, odd_name, reads_as_another, remove, standing, without_long_paths

windows = pytest.mark.skipif(os.name != "nt", reason="the extended-length form is a Windows name")


@windows
def test_a_drive_path_is_named_with_the_prefix_and_nothing_else_changes():
    assert extended("C:\\Users\\x\\file.txt") == "\\\\?\\C:\\Users\\x\\file.txt"


@windows
def test_a_path_object_is_named_as_its_text_is():
    assert extended(Path("C:\\Users\\x")) == "\\\\?\\C:\\Users\\x"


@windows
def test_a_name_in_the_extended_form_is_left_as_it_is_so_the_form_is_asked_for_once():
    once = extended("C:\\a\\b")

    assert extended(once) == once == "\\\\?\\C:\\a\\b"
    assert extended("\\\\?\\UNC\\server\\share\\x") == "\\\\?\\UNC\\server\\share\\x"


@windows
@pytest.mark.parametrize("name", ("foo ", "foo.", "...", ".. ", "a.\\b", "a \\b", "a..\\b"))
def test_a_name_in_the_extended_form_is_the_name_a_listing_gave_and_is_not_cleaned_again(name):
    """The system cleans a plain name once, and `foo.` becomes `foo`, `...` the folder above it.

    A listing hands back the names as they stand. Cleaning a name that has the prefix again
    would name another entry than the one the listing found: that is where an operator's file
    is removed in place of a spawn's, and a junction passes for the folder it is spelled like.
    """
    written = "\\\\?\\C:\\x\\" + name

    assert extended(written) == written
    assert extended(Path(written)) == written
    assert extended("\\\\?\\UNC\\server\\share\\" + name) == "\\\\?\\UNC\\server\\share\\" + name


@windows
def test_a_network_path_is_named_through_the_unc_form():
    assert extended("\\\\server\\share\\dir") == "\\\\?\\UNC\\server\\share\\dir"


@windows
def test_a_device_name_is_not_taken_for_a_network_path_and_is_left_in_its_own_form():
    """`\\\\.\\X` also starts with two backslashes, and `\\\\?\\UNC\\.\\X` is no device: the prefix
    would name a share called `.`. The system reads a device name itself, so it is only cleaned."""
    assert extended("\\\\.\\C:\\x") == "\\\\.\\C:\\x"
    device = r"\\.\PhysicalDrive0"
    assert extended(device) == device
    device_path = Path(device)
    # pathlib on Python 3.11 adds a trailing separator to this device root.
    assert extended(device_path) == os.fspath(device_path)
    assert extended("//./C:/x") == "\\\\.\\C:\\x"
    assert extended("//?/C:/x") == "\\\\?\\C:\\x"  # the extended form spelt with `/` is no share


@windows
def test_the_prefix_switches_the_system_off_from_cleaning_the_name_so_it_is_cleaned_first():
    """`\\\\?\\` passes the name on as written: `/`, `.` and `..` would be taken as characters."""
    assert extended("C:/a/./b/../c") == "\\\\?\\C:\\a\\c"


@windows
def test_a_relative_path_is_named_from_the_working_folder():
    assert extended("x\\y") == "\\\\?\\" + os.path.join(os.getcwd(), "x", "y")


def test_the_tests_own_remover_refuses_the_working_folder_and_every_folder_above_it():
    """It runs `rd /s /q` on a deep name: an empty name must not be the project."""
    for path in ("", ".", os.getcwd(), os.path.dirname(os.getcwd())):
        with pytest.raises(ValueError, match="refusing to remove"):
            remove(path)


@windows
def test_the_machine_without_long_paths_the_tests_ask_for_refuses_the_plain_name_only(
        tmp_path, monkeypatch):
    """`without_long_paths` is what lets a machine that allows long names show the failure.

    Its limit is lowered here to the length of a short file, which every machine serves in both
    forms, so what is shown is the refusal the helper makes and not the setting of the machine.
    """
    short = tmp_path / "short.txt"
    short.write_bytes(b"x")
    without_long_paths(monkeypatch, limit=len(str(short)))

    with pytest.raises(FileNotFoundError):
        os.lstat(short)
    assert os.lstat(named(short)).st_size == 1, "the extended-length name is refused too"
    assert os.lstat(tmp_path).st_mode, "a name shorter than the limit is refused"


@reads_as_another
def test_the_helpers_ask_about_the_name_they_are_given_not_the_folder_it_is_read_as(tmp_path):
    """`...` is the folder it stands in to a plain name. `named` and `standing` leave a name that
    has the prefix as it is, or a test asking if `...` is gone is told about the folder above."""
    odd = odd_name(tmp_path, "...")

    assert named(odd) == odd
    assert not standing(odd), "a folder that is not there was answered for the one above it"
    os.makedirs(odd)
    try:
        assert standing(odd)
    finally:
        os.rmdir(odd)
    assert standing(tmp_path) and not standing(odd)


def test_the_name_is_text_and_absolute_wherever_it_is_asked(tmp_path):
    found = extended(tmp_path / "x")

    assert isinstance(found, str) and os.path.isabs(found.removeprefix("\\\\?\\"))
    assert found.endswith(os.path.join("x"))
