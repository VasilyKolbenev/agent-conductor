"""The child process of the drain witnesses: the real `conduct up`, with fake dispatch.

Run as ``python tests/_drain_child.py <conduct argv>``. It swaps exactly one thing,
`conductor.server.build`, for a wrapper that hands the real builder two fake
adapters, and then calls the real `main`. Everything the parent needs to hold
still is a file it owns (``DRAIN_CONTROL``), never a sleep:

* the doer's effect runs inside the real `ProcessRunner.login_write_guard`, so
  the real ownership borrow and the real shared-login lease stand for as long as
  the attempt runs, and it waits for ``release-<n>`` before it finishes;
* ``entered-<n>`` appears once attempt ``n`` is inside its effect;
* the production clock is kept and every record the fakes write is stamped with
  it, because the drain deadline is a time on that clock.

Optional knobs, all environment: ``DRAIN_AUTO_RELEASE`` (never hold),
``DRAIN_FAULT=quota_uncertain`` (the quota collector cannot prove its retirement),
``DRAIN_MARGIN`` (seconds that replace the drain margin, when the drain module
exists), ``DRAIN_SETTLE_DELAY`` (seconds a worker lingers after each attempt's
receipt), ``DRAIN_CTRL_C=ignored|enabled`` (a known Ctrl+C state on entry, whatever
the parent's own state was: `ignored` is what a harness child inherits, and the
product's standalone `up` must clear it for itself), ``DRAIN_QUOTA=poll|hold-<n>``
(the REAL quota collector over one fake source, polling every second: `quota-poll-<n>`
marks the start of poll `n`, and `hold-<n>` keeps that poll running until
`quota-release-<n>` exists).
"""
from __future__ import annotations

import importlib.util
import itertools
import os
import signal
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from conductor import quota_collectors, server
from conductor.__main__ import main
from conductor.command.adapters import AdapterRegistry, AdapterVerification
from conductor.command.adapters.process import ProcessRunner
from conductor.command.contracts import EvidenceRef
from tests.test_policy_driver import Signing
from tests.test_policy_runtime import PD

HOLD_LIMIT_SECONDS = 90.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def set_console_ctrl_c(state: str) -> None:
    """Put this process in a known Ctrl+C state before `main` runs.

    `ignored` is the attribute a child of a harness or a GUI inherits (Windows;
    on POSIX the default disposition is what a plain child has). `enabled` clears
    it, which is what the product's standalone `up` must do for itself.
    """
    if os.name != "nt":
        if state == "enabled":
            signal.signal(signal.SIGINT, signal.default_int_handler)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
    if not kernel.SetConsoleCtrlHandler(None, state == "ignored"):
        raise ctypes.WinError(ctypes.get_last_error())


class _Stamped(Signing):
    """A signing adapter whose evidence carries the production clock."""

    def _sign(self, request, verifier_instance_id=None):
        adapter_id, now = self.manifest.adapter_id, _now()
        evidence_id = f"evidence-{request.action_id}-{adapter_id}"
        self._store.append(EvidenceRef(
            evidence_id=evidence_id, run_id=request.run_id, kind="verification",
            uri=f"verification/{request.action_id}", label="Checked result",
            created_by=adapter_id, observed_at=now, verification="verified",
            verified_by=adapter_id, verified_at=now,
            verifier_instance_id=verifier_instance_id))
        return AdapterVerification(
            adapter_id=adapter_id, action_id=request.action_id, state="verified",
            observed_at=now, detail="", evidence_refs=(evidence_id,))


class _HeldDoer(_Stamped):
    """A doer whose effect waits for the parent, inside a real login lease."""

    def __init__(self, store, *, root: Path, login: str, control: Path,
                 auto_release: bool, **knobs) -> None:
        super().__init__(store, **knobs)
        self._root, self._login, self._control = root, login, control
        self._auto, self._entered = auto_release, 0

    def execute(self, prepared):
        self._entered += 1
        number = self._entered
        with ProcessRunner.login_write_guard(self._root, self._login):
            (self._control / f"entered-{number}").write_text("1", encoding="ascii")
            self._hold(self._control / f"release-{number}")
            receipt = super().execute(prepared)
        return replace(receipt, observed_at=_now())

    def _hold(self, release: Path) -> None:
        deadline = time.monotonic() + HOLD_LIMIT_SECONDS
        while not self._auto and time.monotonic() < deadline:
            if release.exists():
                return
            time.sleep(0.02)


class _UncertainQuota:
    """A quota collector that never proves its retirement (the existing seam)."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        raise quota_collectors.QuotaStartupUncertain(
            "quota worker retirement is unconfirmed")


def _polling_quota(real_collector, mode: str):
    """The real collector, with its plans replaced by one whose fetch marks every poll."""
    from tests.test_quota_collectors import balance, ready
    control = Path(os.environ["DRAIN_CONTROL"])
    hold = int(mode.split("-", 1)[1]) if mode.startswith("hold-") else None
    numbers = itertools.count(1)

    def fetch(endpoint, bearer):
        number = next(numbers)
        (control / f"quota-poll-{number}").write_text("1", encoding="ascii")
        deadline = time.monotonic() + HOLD_LIMIT_SECONDS
        while number == hold and time.monotonic() < deadline:
            if (control / f"quota-release-{number}").exists():
                break
            time.sleep(0.02)
        return balance()

    def build(service, plans, **kwargs):
        return real_collector(service, (ready(),), fetch=fetch, interval_seconds=1, **kwargs)
    return build


def _shorten_drain_margin() -> None:
    margin = os.environ.get("DRAIN_MARGIN")
    if margin is None or importlib.util.find_spec("conductor.server_drain") is None:
        return
    from conductor import server_drain
    if not hasattr(server_drain, "DRAIN_MARGIN_SECONDS"):
        raise SystemExit("conductor.server_drain has no DRAIN_MARGIN_SECONDS (spec 4.1.6 step 4)")
    server_drain.DRAIN_MARGIN_SECONDS = float(margin)


def _fake_build(real_build):
    root_of = Path(os.environ["DRAIN_ROOT"])
    control, login = Path(os.environ["DRAIN_CONTROL"]), os.environ["DRAIN_LOGIN"]
    auto = os.environ.get("DRAIN_AUTO_RELEASE") == "1"

    def build(root, port, **kwargs):
        doer = _HeldDoer(None, root=root_of, login=login, control=control,
                         auto_release=auto)
        checker = _Stamped(None, adapter_id="codex-cli")
        subject = real_build(root, port, registry=AdapterRegistry([doer, checker]),
                             **kwargs)
        doer._store = checker._store = subject.command_store
        policy = subject.command_api._policy
        policy.provider_digest, policy.provider_facts = (lambda config: PD), None
        _linger_after_each_attempt(subject.command_api.runtime)
        return subject
    return build


def _linger_after_each_attempt(runtime) -> None:
    """Keep every worker busy for `DRAIN_SETTLE_DELAY` after its attempt's receipt is durable.

    The runtime wakes the policy driver when the receipt is appended, and the worker
    only settles when `execute` returns. This widens the gap between those two moments
    so that a driver which is NOT held from proposing has time to propose the next
    step before the drain can see the server idle.
    """
    delay = float(os.environ.get("DRAIN_SETTLE_DELAY", "0"))
    if not delay:
        return
    real_execute = runtime.execute

    def execute(authorization):
        try:
            return real_execute(authorization)
        finally:
            time.sleep(delay)

    runtime.execute = execute


def _install() -> None:
    if os.environ.get("DRAIN_CTRL_C") in {"ignored", "enabled"}:
        set_console_ctrl_c(os.environ["DRAIN_CTRL_C"])
    if os.environ.get("DRAIN_FAULT") == "quota_uncertain":
        server.QuotaCollector = _UncertainQuota
    if os.environ.get("DRAIN_QUOTA"):
        server.QuotaCollector = _polling_quota(server.QuotaCollector, os.environ["DRAIN_QUOTA"])
    _shorten_drain_margin()
    server.build = _fake_build(server.build)


if __name__ == "__main__":
    _install()
    raise SystemExit(main(sys.argv[1:]))
