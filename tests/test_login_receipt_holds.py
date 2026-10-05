"""The receipt checker of a login lease holds each preparation file before it reads it.

`ownership_login._receipts` pins every `prepared-<nonce>[-k].json` of a lease natively before the
file is opened, so a name that is unlinked or replaced between the read and the use is not the file
that was checked, and the pin lasts while the chain decides. Nothing else of the login road
witnessed it: with the pin gone every other login test stayed green.

Two witnesses stand on it, over the three roads that read a chain (a preparation that writes the
next receipt, a repeat that returns the standing one, and the recovery). The ordering witness runs
on every platform: it wraps `NativeHold` and `_read` and says that each receipt is read while a
hold on that very path is open, and is still open at the moment the chain is judged. The effect
witness is Windows-only (a hold is a share mode there): at the same two moments it tries to rename
the file away, which a native hold must refuse. A receipt a call creates is pinned the same way
(`_write_receipt`), and has its own witness. Every restart is a model
(`ownership_boot.current_boot`). No test reads a token or a login file.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import boot_witness, ownership_login as login
from tests._boot_world import OTHER_GUID, counter, measure
from tests.test_login_scope_change import NOW_B, receipt_in_a


def movable(path):
    """Whether the name can be renamed away right now (put back at once); `None` off Windows."""
    if os.name != "nt":
        return None
    moved = Path(path).with_name(Path(path).name + ".probe")
    try:
        os.rename(path, moved)
    except OSError:
        return False
    os.rename(moved, path)
    return True


def watch(monkeypatch, box, nonce, decision):
    """Record, per receipt file, whether it is held and movable when read and when judged."""
    seen = SimpleNamespace(open=[], reads=[], judged=[], written=[])
    real_hold, real_read, real_decision = (login.NativeHold, login._read,
                                           getattr(boot_witness, decision))
    real_write = login._write_receipt

    class Spied(real_hold):
        def __init__(self, path, **options):
            super().__init__(path, **options)
            self.spied = Path(path)
            seen.open.append(self.spied)

        def close(self):
            if getattr(self, "spied", None) in seen.open:
                seen.open.remove(self.spied)
            super().close()

    def probe(path):
        return (Path(path), Path(path) in seen.open, movable(path))

    def read(path, *rest):
        if Path(path).name.startswith("prepared-"):
            seen.reads.append(probe(path))
        return real_read(path, *rest)

    def judge(*args, **options):
        seen.judged.extend(probe(path) for path in sorted(box.glob(f"prepared-{nonce}*")))
        return real_decision(*args, **options)

    def write(stack, folder, bound, record, current, chain):
        made = real_write(stack, folder, bound, record, current, chain)
        seen.written.append(probe(login._receipt_path(folder, record, len(chain))))
        return made

    monkeypatch.setattr(login, "NativeHold", Spied)
    monkeypatch.setattr(login, "_write_receipt", write)
    monkeypatch.setattr(login, "_read", read)
    monkeypatch.setattr(boot_witness, decision, judge)
    return seen


def preparation_that_writes_the_next(tmp_path, monkeypatch):
    home, box, record = receipt_in_a(tmp_path, monkeypatch)
    measure(monkeypatch, NOW_B)
    return home, box, record, login.prepare_login_recovery, "preparation_needed", 1


def two_receipts(tmp_path, monkeypatch):
    home, box, record, *_ = preparation_that_writes_the_next(tmp_path, monkeypatch)
    login.prepare_login_recovery(str(home))
    return home, box, record


def repeat_that_returns_the_standing(tmp_path, monkeypatch):
    home, box, record = two_receipts(tmp_path, monkeypatch)
    return home, box, record, login.prepare_login_recovery, "preparation_needed", 2


def recovery_after_a_restart(tmp_path, monkeypatch):
    home, box, record = two_receipts(tmp_path, monkeypatch)
    measure(monkeypatch, counter(501, OTHER_GUID))
    return home, box, record, login.recover_login, "prove_restart", 2


ROADS = pytest.mark.parametrize("road", [
    preparation_that_writes_the_next, repeat_that_returns_the_standing, recovery_after_a_restart],
    ids=["preparation-writes-the-next", "repeat-returns-the-standing", "recovery"])


def run(road, tmp_path, monkeypatch):
    home, box, record, call, decision, existing = road(tmp_path, monkeypatch)
    seen = watch(monkeypatch, box, record["nonce"], decision)
    call(str(home))
    return seen, existing


@ROADS
def test_every_receipt_is_read_while_a_hold_on_that_path_is_open(tmp_path, monkeypatch, road):
    seen, existing = run(road, tmp_path, monkeypatch)
    assert len(seen.reads) == existing, "each receipt that stood before the call is read once"
    assert [held for _, held, _ in seen.reads] == [True] * existing, seen.reads


@ROADS
def test_every_receipt_is_still_held_when_the_chain_is_judged(tmp_path, monkeypatch, road):
    seen, existing = run(road, tmp_path, monkeypatch)
    assert len(seen.judged) == existing, "the chain is judged once, over every receipt"
    assert [held for _, held, _ in seen.judged] == [True] * existing, seen.judged


@pytest.mark.skipif(os.name != "nt", reason="a native file hold is a Windows share mode")
@ROADS
def test_a_receipt_cannot_be_renamed_away_while_it_is_read_or_judged(tmp_path, monkeypatch, road):
    seen, existing = run(road, tmp_path, monkeypatch)
    probes = seen.reads + seen.judged
    assert len(probes) == 2 * existing
    assert [moved for _, _, moved in probes] == [False] * len(probes), probes


def test_a_receipt_this_call_creates_is_held_when_the_write_returns(tmp_path, monkeypatch):
    seen, _ = run(preparation_that_writes_the_next, tmp_path, monkeypatch)
    [(path, held, moved)] = seen.written
    assert path.name.endswith("-1.json") and held is True
    assert moved in (False, None), "the call holds what it created: no rename (Windows)"
