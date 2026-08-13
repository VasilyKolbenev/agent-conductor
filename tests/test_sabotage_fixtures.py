"""Unit proofs for the sabotage fixture library, plus two CMD-4 spot-proofs.

Every builder in :mod:`tests.sabotage_fixtures` claims to construct exactly one
hostile state. Each test here holds that claim with a witness it computes
itself — ``os.readlink`` and ``st_reparse_tag`` for a portal, ``samefile`` and
``st_nlink`` for an alias, ``json.loads`` for tampered bytes, path resolution
for an escape — never the builder's own word. Both sides of a check are drawn
from different code.

The last two tests are the anti-decoration proofs the slice requires: the
portal planter and the outward-hard-link planter are driven against the real
CMD-4 route-containment gate in :mod:`conductor.command.preview`. If a fixture
did not actually construct the state the gate refuses, the gate would return a
proposal and these tests would fail.

Every other test proves only the fixture named by the test. In particular, a
test showing that a confirmation is expired or a browser envelope is hostile
does not claim CONF-1 or API-1 rejects it: those production seams do not exist
on this branch and stay PENDING in the threat matrix.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import stat
import subprocess
import sys

import pytest

from conductor.command import preview
from conductor.command.contracts import ActionRequest, ContractError, RunEnvelope
from conductor.command.run_store import CorruptRun, RunStore, snapshot_digest

from tests import sabotage_fixtures as sf


#: A junction's reparse tag; the constant exists on every platform since 3.8.
_JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


# --- portal and alias planters, witnessed by the standard library ---


def test_plant_symlink_makes_a_link_whose_bytes_resolve_at_the_target(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    (target / "inside.txt").write_bytes(b"content that lies elsewhere")
    with sf.skip_when_unavailable():
        link = sf.plant_symlink(tmp_path / "portal", target, directory=True)
    # Witness: the link is a symlink and os.readlink names the target we passed.
    assert link.is_symlink()
    assert Vp(os.readlink(link)) == Vp(str(target))


def test_plant_junction_makes_a_reparse_dir_that_is_not_the_target_directory(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    (target / "inside.txt").write_bytes(b"content behind the junction")
    with sf.skip_when_unavailable():
        link = sf.plant_junction(tmp_path / "portal", target)
    # Witness: it answers is_dir() True (why a naive walk recurses through it)
    # yet carries the junction reparse tag lstat can see without following it.
    assert link.is_dir()
    assert getattr(link.lstat(), "st_reparse_tag", 0) == _JUNCTION_TAG


def test_plant_outward_hard_link_gives_inside_bytes_a_second_outside_name(tmp_path):
    inside = tmp_path / "run" / "records.jsonl"
    inside.parent.mkdir()
    inside.write_bytes(b"durable line\n")
    outside = tmp_path / "outside" / "laundered.jsonl"
    outside.parent.mkdir()
    with sf.skip_when_unavailable():
        planted = sf.plant_outward_hard_link(inside, outside)
    # Witness: one inode under two names, and a second link on the inside file.
    assert os.path.samefile(inside, planted)
    assert os.lstat(inside).st_nlink == 2
    assert planted.read_bytes() == b"durable line\n"


def Vp(value: str) -> str:
    """Normalise a filesystem path string for comparison across separators."""
    normal = os.path.normcase(os.path.normpath(value))
    # Windows may expose the same absolute target through the extended-length
    # spelling returned by readlink; that prefix changes no path identity.
    return normal[4:] if normal.startswith("\\\\?\\") else normal


# --- decision-receipt bytes: honest, tampered, uncontracted, stale ---


def test_receipt_bytes_are_the_canonical_wrapper_of_the_honest_decision():
    decision = sf.decision_receipt()
    wrapper = json.loads(sf.receipt_bytes(decision))
    assert wrapper == {"record": decision.as_dict(), "record_type": "decision"}
    assert sf.receipt_bytes(decision).endswith(b"\n")


def test_tampered_receipt_keeps_the_identity_but_flips_the_recorded_decision():
    honest = sf.decision_receipt()
    tampered = json.loads(sf.tampered_receipt_bytes(honest))["record"]
    assert tampered["receipt_id"] == honest.receipt_id
    assert tampered["run_id"] == honest.run_id
    assert tampered["gate_id"] == honest.gate_id
    # The relation that makes it a tamper: same identity, a changed decision.
    assert honest.action == "approve" and tampered["action"] == "reject"
    assert sf.tampered_receipt_bytes(honest) != sf.receipt_bytes(honest)


def test_uncontracted_receipt_smuggles_a_field_the_wrapper_does_not_define():
    honest = sf.decision_receipt()
    wrapper = json.loads(sf.uncontracted_receipt_bytes(honest))
    # The record round-trips, but a key rides beside it that the contract's
    # two-key wrapper never carries.
    assert wrapper["record"] == honest.as_dict()
    assert set(wrapper) == {"record", "record_type", "action"}


def test_stale_receipt_names_a_different_run_than_the_gate_it_would_satisfy():
    honest = sf.decision_receipt(run_id="run-001")
    stale = json.loads(sf.stale_receipt_bytes(honest, foreign_run_id="run-old"))["record"]
    assert honest.run_id == "run-001"
    assert stale["run_id"] == "run-old"
    assert stale["gate_id"] == honest.gate_id  # same gate, a foreign run


@pytest.mark.parametrize(
    "damage, message",
    [(sf.tampered_receipt_bytes, "disagrees with records.jsonl"),
     (sf.uncontracted_receipt_bytes, "non-canonical or uncontracted fields")],
)
def test_receipt_damage_fixture_trips_real_run_store_replay(damage, message, tmp_path):
    """Our hostile bytes reach CMD-2's durable receipt-reconciliation door."""
    config = {"cycle": {"id": "orbit-001"}}
    digest = snapshot_digest(config)
    store = RunStore(tmp_path)
    store.create_run(
        RunEnvelope(
            run_id="run-001", cycle_id="orbit-001",
            created_at="2026-08-13T08:00:00Z", config_digest=digest),
        config)
    decision = sf.decision_receipt(config_digest=digest)
    store.append(decision)
    path = store.run_path("run-001") / "decisions" / "decision-001.json"
    journal = store.run_path("run-001") / "records.jsonl"
    journal_before = journal.read_bytes()
    path.write_bytes(damage(decision))
    damaged_before = path.read_bytes()

    with pytest.raises(CorruptRun, match=message):
        store.read("run-001")
    assert path.read_bytes() == damaged_before
    assert journal.read_bytes() == journal_before


# --- Confirm freshness and duplicate-idempotency inputs ---


def _instant(value):
    """Parse one fixture timestamp without using any future production clock."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_confirmation_fixtures_change_only_the_stale_or_digest_fact():
    now = datetime(2026, 8, 13, 8, 1, tzinfo=timezone.utc)
    fresh = sf.fresh_confirmation()
    expired = sf.expired_confirmation()
    changed = sf.changed_digest_confirmation()

    assert _instant(fresh.confirmed_at) <= now < _instant(fresh.expires_at)
    assert _instant(expired.expires_at) < now
    assert changed.preview_digest != fresh.preview_digest
    assert (changed.run_id, changed.action_id, changed.confirmed_at, changed.expires_at) == (
        fresh.run_id, fresh.action_id, fresh.confirmed_at, fresh.expires_at)


def test_duplicate_idempotency_fixture_is_two_different_actions_under_one_key():
    first, second = sf.conflicting_idempotency_requests()
    assert first.action_id != second.action_id
    assert first.attempt_id != second.attempt_id
    assert first.arguments != second.arguments
    assert first.idempotency_key == second.idempotency_key


# --- path-escape scopes/cwds and shell-injection strings ---


_NOW = "2026-08-11T07:30:00Z"
_PREVIEW = "sha256:" + "b" * 64


def _an_action(**changes) -> ActionRequest:
    values = {
        "action_id": "action-001", "run_id": "run-001", "attempt_id": "attempt-001",
        "instance_id": "claude-dev", "capability": "dispatch",
        "arguments": {"handoff": "packet-001"}, "scope": ("src",),
        "requested_by": "owner", "requested_at": _NOW,
        "idempotency_key": "dispatch-001", "timeout_seconds": 900,
        "preview_digest": _PREVIEW, "mode": "confirm"}
    values.update(changes)
    return ActionRequest(**values)


def _scope_component_escapes(component: str) -> bool:
    """Test-local witness: this path component is not canonical-and-contained."""
    return (component == ""
            or component.startswith("/")
            or "\\" in component
            or ".." in component.split("/")
            or (len(component) > 1 and component[1] == ":"))


def test_path_escape_scopes_trip_the_contract_gate():
    scopes = sf.path_escape_scopes()
    assert len(scopes) == len({tuple(s) for s in scopes})  # each a distinct shape
    for scope in scopes:
        # Test-local relation: some component escapes a canonical project scope.
        assert any(_scope_component_escapes(c) for c in scope), scope
        # And the real frozen contract gate refuses it — a second, independent side.
        with pytest.raises(ContractError, match="scope"):
            _an_action(scope=scope)


def test_path_escape_cwds_each_resolve_outside_the_project_root(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    resolved_root = root.resolve()
    cwds = sf.path_escape_cwds(root)
    assert len(cwds) >= 5
    for cwd in cwds:
        resolved = cwd.resolve()
        assert not resolved.is_relative_to(resolved_root), resolved


def test_shell_injection_payloads_each_carry_a_shell_control_operator():
    operators = (";", "&&", "||", "|", "$(", "`", "\n", "&")
    payloads = sf.shell_injection_payloads()
    for payload in payloads:
        assert any(op in payload for op in operators), payload
    # Coverage relation the test owns: the set exercises separation, piping,
    # substitution, backgrounding and a raw newline, not one trick repeated.
    joined = "".join(payloads)
    for family in (";", "&&", "|", "$(", "`", "&", "\n"):
        assert family in joined, family


def test_argv_probe_receives_injection_payloads_as_unchanged_elements(tmp_path):
    payloads = sf.shell_injection_payloads()
    probe = sf.write_argv_probe(tmp_path)
    result = subprocess.run(
        [sys.executable, str(probe), *payloads], capture_output=True, timeout=30)
    assert result.returncode == 0 and result.stderr == b""
    assert json.loads(result.stdout) == list(payloads)


# --- foreign / recycled process ownership ---


def test_process_ownership_variants_never_match_the_recorded_owner():
    owner = sf.recorded_owner()
    foreign = sf.foreign_pid(owner)
    recycled = sf.recycled_pid(owner)
    # A foreign process shares neither the PID nor the start token.
    assert foreign.pid != owner.pid and foreign.start_token != owner.start_token
    # A recycled PID is the dangerous one: same number, a stranger's token — a
    # check reading only the PID would stop it, the token relation refuses it.
    assert recycled.pid == owner.pid and recycled.start_token != owner.start_token
    assert foreign != owner and recycled != owner


# --- output-bomb fake executable ---


def test_output_bomb_emits_exactly_the_byte_count_it_names(tmp_path):
    script = sf.write_output_bomb(tmp_path, size_bytes=2048)
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, timeout=30)
    assert result.returncode == 0
    assert len(result.stdout) == 2048  # exactly the flood it claims, no more
    assert result.stderr == b""


def test_output_bomb_can_target_stderr_and_rejects_a_bad_size_or_stream(tmp_path):
    script = sf.write_output_bomb(tmp_path, size_bytes=1024, stream="stderr")
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, timeout=30)
    assert len(result.stderr) == 1024 and result.stdout == b""
    with pytest.raises(ValueError):
        sf.write_output_bomb(tmp_path, size_bytes=-1)
    with pytest.raises(ValueError):
        sf.write_output_bomb(tmp_path, size_bytes=10, stream="socket")


def test_blocking_executable_announces_started_before_a_caller_times_out(tmp_path):
    script = sf.write_blocking_executable(tmp_path, wait_seconds=5)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        subprocess.run(
            [sys.executable, str(script)], capture_output=True, timeout=1,
            check=False)
    assert json.loads(caught.value.stdout.splitlines()[0]) == {
        "attempt_id": "attempt-001", "event": "started"}
    with pytest.raises(ValueError):
        sf.write_blocking_executable(tmp_path, wait_seconds=0)


# --- explicit verification failure ---


def test_mismatched_verification_is_not_success_and_carries_no_invented_evidence():
    mismatch = sf.mismatched_verification()
    assert mismatch.state == "mismatch"
    assert mismatch.action_id == "action-001"
    assert mismatch.evidence_refs == ()
    assert "does not match" in mismatch.detail


# --- hostile browser mutation envelopes ---


def _browser_relation_holds(request, *, host, origin, csrf_token):
    """Test-owned future API-1 relation; not a production authorization call."""
    return (request.host == host and request.origin == origin
            and request.csrf_token == csrf_token)


def test_each_browser_mutation_breaks_one_required_authorization_factor():
    expected = {
        "host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765",
        "csrf_token": "csrf-process-001"}
    mutations = sf.hostile_browser_mutations(**expected)
    assert {case.name for case in mutations} == {
        "cross-origin", "missing-origin", "foreign-host", "missing-token", "wrong-token"}
    for case in mutations:
        assert not _browser_relation_holds(case, **expected), case


# --- CMD-4 spot-proofs: the two planters against the real containment gate ---


def _seed_preview_identity(root):
    """Create the empty, resumable run the preview would otherwise adopt."""
    RunStore(root).create_run(
        RunEnvelope(run_id="preview-run", cycle_id="preview-orbit",
                    created_at="2026-08-11T00:00:00Z",
                    config_digest=snapshot_digest(preview.FROZEN_CONFIG),
                    mode="propose"),
        preview.FROZEN_CONFIG)
    return root / "conductor" / "runs" / "preview-run"


def _tree_state(root):
    """Every durable fact under root, recording a portal by target, never entering it."""
    state = {}
    stack = [root]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            key = path.relative_to(root).as_posix()
            if path.is_symlink() or getattr(
                    path.lstat(), "st_reparse_tag", 0) == _JUNCTION_TAG:
                state[key] = ("link", os.readlink(path))
            elif path.is_dir():
                state[key] = ("dir",)
                stack.append(path)
            else:
                state[key] = ("file", path.read_bytes())
    return state


@pytest.mark.parametrize("kind", ["junction", "symlink"])
def test_portal_planter_trips_preview_route_gate(kind, tmp_path):
    """A portal planted at the run boundary makes render_dispatch_preview refuse.

    The owner's exact reproduction: behind the portal is a valid, empty run;
    the pre-gate baseline adopted it and appended into the EXTERNAL journal.
    The fixture must construct that portal well enough that the real gate
    refuses (exit-1: PreviewError) and the external run stays byte-for-byte inert.
    """
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    target = _seed_preview_identity(outside)
    assert (target / "records.jsonl").read_bytes() == b""
    runs = project / "conductor" / "runs"
    runs.mkdir(parents=True)
    with sf.skip_when_unavailable():
        sf.plant_route_portal(runs / "preview-run", target, kind=kind)

    outside_before = _tree_state(outside)
    with pytest.raises(preview.PreviewError):
        preview.render_dispatch_preview(str(project))
    # External inertness: nothing landed behind the portal.
    assert _tree_state(outside) == outside_before
    assert (target / "records.jsonl").read_bytes() == b""


def test_outward_hard_link_planter_trips_preview_route_gate(tmp_path):
    """An owned file aliased outward makes render_dispatch_preview refuse to adopt.

    ``run.json`` given a second name outside the run replays cleanly, so the
    pre-gate baseline adopted the run and appended while its envelope bytes
    also answered to an external name. The fixture must produce that two-named
    inode; the real gate then refuses (PreviewError) and the outside file is
    untouched.
    """
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    outside.mkdir()
    run_dir = _seed_preview_identity(project)
    kept = outside / "kept-envelope.json"
    with sf.skip_when_unavailable():
        sf.plant_outward_hard_link(run_dir / "run.json", kept)
    assert os.lstat(run_dir / "run.json").st_nlink == 2

    kept_before = kept.read_bytes()
    outside_before = _tree_state(outside)
    with pytest.raises(preview.PreviewError):
        preview.render_dispatch_preview(str(project))
    assert _tree_state(outside) == outside_before
    assert kept.read_bytes() == kept_before
