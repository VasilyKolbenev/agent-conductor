"""A tiny verified first-commit file must not reserve the 32 MiB index ceiling."""
import builtins
import os
from pathlib import Path

import pytest

from conductor.command import git_setup_first_lock as locks
from conductor.command import git_setup_first_records as records
from conductor.command.git_setup_records import SetupRefused
from tests.test_git_setup_first_records import DATA, NONCE, an_op, install_file


@pytest.fixture(params=("install", "copy"))
def verified_file(tmp_path, request):
    if request.param == "install":
        path = install_file(tmp_path)
        def read(expected):
            return records.read_install(tmp_path, an_op(expected))
    else:
        path = locks.copy_path(tmp_path, NONCE)
        def read(expected):
            locks.ensure_copy(tmp_path, NONCE, expected)
            return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(DATA)
    return path, read, request.param


def test_read_request_uses_the_admitted_size_and_one_growth_byte(verified_file, monkeypatch):
    path, read, kind = verified_file
    original = Path.open if kind == "install" else builtins.open
    sizes = []

    def observe(target, *args, **kwargs):
        stream = original(target, *args, **kwargs)
        if target == path:
            raw_read = stream.read
            def measured(size=-1):
                sizes.append(size)
                return raw_read(size)
            stream.read = measured
        return stream

    if kind == "install":
        monkeypatch.setattr(Path, "open", observe)
    else:
        monkeypatch.setattr(locks, "open", observe, raising=False)
    assert read(DATA) == DATA
    assert sizes == [len(DATA) + 1]


@pytest.mark.parametrize("final", [DATA + b"x", DATA[:-1]], ids=["grew", "shrank"])
def test_size_change_refuses_even_when_final_bytes_match_the_expected_digest(
        verified_file, monkeypatch, final):
    path, read, _ = verified_file
    real_stat = os.fstat
    def resize_after_stat(fd):
        observed = real_stat(fd)
        path.write_bytes(final)
        return observed
    monkeypatch.setattr(os, "fstat", resize_after_stat)
    with pytest.raises(SetupRefused, match="setup_damaged"):
        read(final)
    assert path.read_bytes() == final


def test_size_ceiling_is_inclusive_and_oversize_bytes_are_untouched(verified_file, monkeypatch):
    path, read, kind = verified_file
    module = records if kind == "install" else locks
    monkeypatch.setattr(module, "INDEX_LIMIT", len(DATA))
    assert read(DATA) == DATA
    large = DATA + b"x"
    path.write_bytes(large)
    with pytest.raises(SetupRefused, match="setup_damaged"):
        read(large)
    assert path.read_bytes() == large


def test_oversized_replacement_before_index_copy_is_opened_is_never_read(tmp_path, monkeypatch):
    path = locks.copy_path(tmp_path, NONCE)
    path.write_bytes(DATA)
    large = DATA + b"x"
    monkeypatch.setattr(locks, "INDEX_LIMIT", len(DATA))

    def changed_before_open(target, mode):
        assert target == path
        path.write_bytes(large)
        stream = builtins.open(target, mode)
        stream.read = lambda *_: pytest.fail("opened file exceeds the admitted size")
        return stream

    monkeypatch.setattr(locks, "open", changed_before_open, raising=False)
    with pytest.raises(SetupRefused, match="setup_damaged"):
        locks.ensure_copy(tmp_path, NONCE, large)
    assert path.read_bytes() == large
