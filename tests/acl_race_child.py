"""The two processes of the one witness that two changes of one folder's DACL cannot lose a write.

Both run the PRODUCT's read-modify-write (`process_loans.change_dacl`) on the same real folder with
the real natives. The slow process stops right after its read, inside its change, until the fast
one has finished its whole change or `patience` seconds have passed. Without a mutex the fast
process reads, writes and finishes in that window and the slow one then writes over it from its
stale read: an entry is lost, and nothing raises. With the mutex the fast process cannot even read
until the slow one has written, so the window ends by `patience` and both entries stand.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace


def worker(folder: str, sid: str, role: str, gate, serialised: bool) -> None:
    """One process: `role` is `slow` or `fast`; `gate` carries the two events and the patience."""
    from conductor.command.adapters import _winlaunch
    from conductor.command.adapters.process_loans import change_dacl, loan_sddl
    from conductor.ownership_native import NativeHold

    stopped = []

    def snapshot(hold):
        found = _winlaunch.acl_snapshot(hold)
        if role == "slow" and not stopped:  # right after the first read, inside the change
            stopped.append(True)
            gate.slow_read.set()
            gate.fast_done.wait(gate.patience)
        return found

    native = SimpleNamespace(
        acl_snapshot=snapshot, acl_set=_winlaunch.acl_set, acl_equal=_winlaunch.acl_equal,
        acl_exclusive=_winlaunch.acl_exclusive if serialised else (lambda hold: nullcontext()))
    if role == "fast" and not gate.slow_read.wait(60):
        raise SystemExit("the slow process never read the DACL")
    hold = NativeHold(Path(folder), directory=True, grants=True)
    try:
        change_dacl(native, hold, lambda now: loan_sddl(now, sid, "modify"))
    finally:
        hold.close()
    if role == "fast":
        gate.fast_done.set()
