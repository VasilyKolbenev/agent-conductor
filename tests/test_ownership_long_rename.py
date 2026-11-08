"""Windows must publish the exact held object under a long receipt name without replacement."""
from contextlib import closing
import os
from pathlib import Path

import pytest

from conductor.command.long_path import extended
from conductor.ownership_native import NativeHold, NativeOwnershipError, identity


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows FILE_RENAME_INFO")


def destination(directory, width):
    units = len(os.fspath(directory).encode("utf-16-le")) // 2
    return directory / ("closed-" + "x" * max(8, width - units - 16) + "-😀.json")


@pytest.mark.parametrize("width", [259, 260, 263])
def test_checked_rename_keeps_the_file_and_the_hold_above_the_classic_limit(tmp_path, width):
    original = Path(extended(tmp_path / "active.json"))
    target = destination(tmp_path, width)
    original.write_bytes(b"one attempt")
    with closing(NativeHold(original, movable=True)) as hold:
        initial = hold.identity
        hold.rename(target)
        hold.check()
        assert hold.identity == identity(Path(extended(target))) == initial
    assert not original.exists()
    assert Path(extended(target)).read_bytes() == b"one attempt"


def test_existing_long_receipt_refuses_both_its_real_name_and_its_win32_alias(tmp_path):
    original = Path(extended(tmp_path / "active.json"))
    original.write_bytes(b"new")
    target = destination(tmp_path, 270)
    existing = Path(extended(target))
    existing.write_bytes(b"earlier")
    before = identity(existing)
    with closing(NativeHold(original, movable=True)) as hold:
        for name in (target, target.with_name(target.name + ".")):
            with pytest.raises(NativeOwnershipError):
                hold.rename(name)
            hold.check()
    assert existing.read_bytes() == b"earlier" and identity(existing) == before
    assert original.read_bytes() == b"new"
