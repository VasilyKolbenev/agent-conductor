"""The dsh harness adapter, proved against a deterministic fake dsh entrypoint.

Every claim here is a RELATION driven through the real provider door, the real
owned-process runner and a real child process: the fake stands in for the pinned
build, never for the adapter. Nothing in this module reads a name or a type and
calls it a proof -- a spawn is counted by the line the child itself wrote, an
isolated home is read out of the child's own environment, and the absence of a
planted secret is checked against every value the adapter can hand onward.

The fake is driven through the SAME two pins the real contract needs: an
absolute interpreter (``sys.executable``) and an absolute entrypoint
(``tests/_fakedsh.py``), because the published dsh CLI ships its ``dsh`` bin as
``lib/bin.js`` -- a Node script that an interpreter must run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conductor.command.adapters.base import AdapterVerification
from conductor.command.adapters.dsh_harness import (
    DSH_PROTOCOL,
    HOME_DIR,
    INSTRUCTION_DIR,
    MARKER_DIR,
    REVIEWED_DSH_VERSION,
    DshHarnessAdapter,
    DshHarnessError,
    DshPin,
)
from conductor.command.adapters.provider import (
    ProviderCatalogEntry,
    ProviderConfig,
    ProviderConfigError,
    ProviderRegistry,
)
from conductor.command.contracts import ActionRequest
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers

from tests import _fakedsh

NOW = "2026-08-17T12:00:00Z"
DIGEST = "sha256:" + "a" * 64
PROVIDER_ID = "deepseek-harness"
SECRET = "sk-live-planted-secret-value"


class _Ids:
    """A deterministic id mint that never repeats a value."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count}"


def _config(node: str, entrypoint: str, names: tuple[str, ...]) -> ProviderConfig:
    return ProviderConfig(
        provider_id=PROVIDER_ID, executable=node, protocol=DSH_PROTOCOL,
        env_allow=names, entrypoint=entrypoint)


#: The instruction body every dispatch below materializes. A dispatch that
#: cannot read one refuses, so seeding it is part of standing a harness up --
#: which is exactly the relation `test_command_dsh_trust_scale` holds from the
#: other side by taking it away again.
INSTRUCTION_BODY = "Add the missing guard and prove it with one failing test."


def a_harness(tmp_path: Path, **knobs: str):
    """A registered, available harness over the fake, plus its root and spawn log."""
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    instructions = root / INSTRUCTION_DIR
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    log = tmp_path / "spawns.log"
    node, entrypoint = _fakedsh.fake_pins()
    environ = {_fakedsh.SPAWN_LOG: str(log), **knobs}
    resolution = resolve_providers(
        [_config(node, entrypoint, tuple(sorted(environ)))], root=root,
        clock=lambda: NOW, ids=_Ids(), environ=environ)
    return resolution.registry.resolve(PROVIDER_ID), root, log


def a_request(*, action_id="act-1", capability="dispatch", timeout=30,
              work_item_id="work-001", arguments=None) -> ActionRequest:
    body = arguments if arguments is not None else {
        "work_item_id": work_item_id, "instruction_ref": "instr-001",
        "profile": "implement", "artifact_refs": ["art-001"],
        "output_limit_profile": "normal"}
    return ActionRequest(
        action_id=action_id, run_id="run-1", attempt_id="att-1",
        instance_id="inst-1", capability=capability, arguments=body,
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key=f"idem-{action_id}", timeout_seconds=timeout,
        preview_digest=DIGEST, mode="confirm")


def run_once(adapter, request: ActionRequest):
    """Drive prepare -> execute exactly as the runtime does, and return the receipt."""
    return adapter.execute(adapter.prepare(request))


# --- the two pins are the whole command surface ---


def test_only_the_two_operator_pins_and_code_owned_flags_ever_reach_the_argv(tmp_path):
    adapter, _root, log = a_harness(tmp_path)
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "succeeded"
    node, entrypoint = _fakedsh.fake_pins()
    task = _fakedsh.task_spawns(log)
    assert len(task) == 1
    # The child reports the argv it was handed AFTER the two pins, which the
    # runner passes positionally: profile flags this module never supplied and a
    # single task token built from identifiers.
    assert task[0]["argv"][:2] == ["--profile", "headless"]
    assert len(task[0]["argv"]) == 3
    # The pins are absolute and are the executable/entrypoint the operator set.
    assert Path(node).is_absolute() and Path(entrypoint).is_absolute()
    for row in _fakedsh.spawns(log):
        rendered = " ".join(row["argv"]).lower()
        for banned in ("npx", "npm", ".cmd", "-c ", "&&", "|"):
            assert banned not in rendered


def test_a_relative_pin_is_refused_before_any_child_can_exist():
    node, entrypoint = _fakedsh.fake_pins()
    for bad in ("node", "./node", "lib/bin.js"):
        with pytest.raises(DshHarnessError, match="absolute operator pin"):
            DshPin(node_executable=bad, entrypoint=entrypoint)
        with pytest.raises(DshHarnessError, match="absolute operator pin"):
            DshPin(node_executable=node, entrypoint=bad)
    with pytest.raises(DshHarnessError, match="NUL-free"):
        DshPin(node_executable=node, entrypoint=entrypoint + "\x00evil")


def test_a_harness_with_no_entrypoint_pinned_owns_no_adapter_and_cannot_spawn(tmp_path):
    """An interpreter with nothing to run is unavailable, never half-configured."""
    root = tmp_path / "root"
    root.mkdir()
    node, _entrypoint = _fakedsh.fake_pins()
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=PROVIDER_ID, executable=node, protocol=DSH_PROTOCOL)],
        root=root, clock=lambda: NOW, ids=_Ids())
    contract = next(row for row in resolution.contracts if row.provider_id == PROVIDER_ID)
    assert contract.availability == "executable_absent" and contract.available is False
    assert resolution.spawn_capable(PROVIDER_ID) is False


def test_an_entrypoint_that_is_not_on_disk_is_unavailable_even_with_a_real_node(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    node, _entrypoint = _fakedsh.fake_pins()
    missing = str(tmp_path / "absent" / "bin.js")
    resolution = resolve_providers(
        [_config(node, missing, ())], root=root, clock=lambda: NOW, ids=_Ids())
    contract = next(row for row in resolution.contracts if row.provider_id == PROVIDER_ID)
    assert contract.availability == "executable_absent"
    assert resolution.spawn_capable(PROVIDER_ID) is False
    assert not (root / HOME_DIR).exists()


# --- the isolated, single-use home ---


def test_every_spawn_mints_a_fresh_home_that_no_earlier_spawn_used(tmp_path):
    adapter, root, log = a_harness(tmp_path)
    run_once(adapter, a_request(action_id="act-1"))
    run_once(adapter, a_request(action_id="act-2", work_item_id="work-002"))
    homes = [row["dsh_home"] for row in _fakedsh.spawns(log)]
    assert len(homes) == 4  # two preflights and two tasks
    assert len(set(homes)) == 4, "a home was reused across spawns"
    for home in homes:
        # The child recorded the home it actually ran in, and every one of them
        # stood directly beneath the ONE root this workspace cleans up within.
        assert Path(home).parent == (root / HOME_DIR).resolve() or Path(
            home).parent == root / HOME_DIR
        # None of them survives the spawn: retention is per-attempt by relation,
        # which `test_command_dsh_containment` holds against planted model text.
        assert not Path(home).exists()


def test_the_child_never_inherits_the_operator_home_and_telemetry_stays_disabled(
        tmp_path):
    """The durable config names the variables; the VALUES are minted here."""
    poisoned = str(tmp_path / "operator-home")
    adapter, root, log = a_harness(tmp_path, DSH_HOME=poisoned)
    run_once(adapter, a_request())
    for row in _fakedsh.spawns(log):
        assert row["dsh_home"] != poisoned
        assert Path(row["dsh_home"]).is_relative_to(root / HOME_DIR)
        assert row["telemetry_disabled"] == "1"


def test_the_child_environment_holds_only_the_allowlist_and_the_two_minted_names(
        tmp_path):
    adapter, _root, log = a_harness(tmp_path)
    run_once(adapter, a_request())
    names = set(_fakedsh.spawns(log)[0]["env_names"])
    assert names == {_fakedsh.SPAWN_LOG, "DSH_HOME", "DSH_TELEMETRY_DISABLED"}


# --- owner gate F, clause 1: an exact version preflight ---


def test_a_version_mismatch_spawns_the_task_zero_times(tmp_path):
    adapter, root, log = a_harness(tmp_path, FAKEDSH_VERSION="0.1.0-rc.6")
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed" and receipt.exit_code is None
    assert REVIEWED_DSH_VERSION in receipt.detail
    assert _fakedsh.task_spawns(log) == []
    assert len(_fakedsh.spawns(log)) == 1, "only the preflight may have run"
    # Nothing durable was claimed either: a refused action leaves no marker.
    assert not (root / MARKER_DIR).exists()


def test_a_preflight_that_cannot_answer_at_all_spawns_the_task_zero_times(tmp_path):
    adapter, root, log = a_harness(tmp_path, FAKEDSH_VERSION_FAILS="1")
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed"
    assert "version preflight" in receipt.detail
    assert _fakedsh.task_spawns(log) == []
    assert not (root / MARKER_DIR).exists()


def test_the_reviewed_version_lets_exactly_one_task_through(tmp_path):
    adapter, _root, log = a_harness(tmp_path, FAKEDSH_VERSION=REVIEWED_DSH_VERSION)
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "succeeded"
    assert len(_fakedsh.task_spawns(log)) == 1


def test_the_preflight_runs_before_the_task_and_not_after_it(tmp_path):
    adapter, _root, log = a_harness(tmp_path)
    run_once(adapter, a_request())
    ordered = [row["argv"][:1] for row in _fakedsh.spawns(log)]
    assert ordered == [["--version"], ["--profile"]]


# --- the argv is code-owned: the DEEP-1 relation ---


def test_no_caller_value_can_be_read_by_the_launcher_as_one_of_its_own_flags(tmp_path):
    """A leading dash is the whole injection surface, and it is closed twice."""
    adapter, _root, log = a_harness(tmp_path)
    # The contract id grammar refuses it first: an id must start alphanumeric.
    with pytest.raises(DshHarnessError, match="closed deep dispatch schema"):
        adapter.prepare(a_request(work_item_id="--patch"))
    assert _fakedsh.spawns(log) == []
    # And the argv boundary refuses it again, whatever reached it. The check
    # lives in the shared headless transport now; what matters here is that dsh
    # still refuses through it, with dsh's OWN error type and dsh's own launcher
    # named -- a shared helper that widened either would be a change of
    # behaviour wearing a refactor's clothes.
    from conductor.command.adapters.headless_cli import flagless

    for hostile in ("--patch", "-V", "--profile"):
        with pytest.raises(DshHarnessError, match="own flags"):
            flagless(hostile, "task text", "dsh launcher", DshHarnessError)


def test_the_prepared_payload_carries_no_argv_no_cwd_and_no_pinned_path(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)
    prepared = adapter.prepare(a_request())
    assert set(prepared.adapter_payload) == {
        "work_item_id", "instruction_ref", "profile", "artifact_refs",
        "output_limit_profile"}
    node, entrypoint = _fakedsh.fake_pins()
    blob = json.dumps(dict(prepared.adapter_payload))
    for banned in ("argv", "cwd", "env", node, entrypoint, "--profile"):
        assert banned not in blob


def test_a_body_that_is_not_the_closed_dispatch_schema_never_reaches_a_spawn(tmp_path):
    adapter, _root, log = a_harness(tmp_path)
    for hostile in (
            {"argv": ["node", "-e", "1"], "cwd": "work"},
            {"work_item_id": "work-001"},
            {"work_item_id": "work-001", "instruction_ref": "instr-001",
             "profile": "implement", "artifact_refs": ["art-001"],
             "output_limit_profile": "normal", "extra": "smuggled"}):
        with pytest.raises(DshHarnessError, match="closed deep dispatch schema"):
            adapter.prepare(a_request(arguments=hostile))
    assert _fakedsh.spawns(log) == []


def test_the_adapter_prepares_only_the_one_control_it_declares(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)
    assert set(adapter.manifest.capabilities) == {"observe", "dispatch"}
    for absent in ("stop", "retry", "switch", "pause", "resume"):
        assert absent not in adapter.manifest.capabilities


def test_the_door_refuses_a_declared_control_this_adapter_cannot_back(tmp_path):
    """Session 1's door closes the class; this only proves it still does."""
    adapter, _root, _log = a_harness(tmp_path)
    entry = ProviderCatalogEntry(
        provider_id=PROVIDER_ID, display_name="dsh", vendor="DeepSeek",
        protocol=DSH_PROTOCOL, capabilities=("observe", "dispatch", "stop"),
        schema_pairs=(("dispatch", "deep-arguments-v1"), ("stop", "deep-arguments-v1")),
        lifecycle=("observe", "prepare", "execute", "verify"),
        adapter_class=DshHarnessAdapter)
    with pytest.raises(ProviderConfigError, match="adapter's own exact argument schema"):
        ProviderRegistry().register(entry, availability="available", adapter=adapter)


def test_the_catalogued_harness_declares_exactly_one_control(tmp_path):
    entry = PROVIDER_CATALOG[PROVIDER_ID]
    assert entry.capabilities == ("observe", "dispatch")
    assert entry.schema_pairs == (("dispatch", "deep-arguments-v1"),)
    adapter, _root, _log = a_harness(tmp_path)
    assert dict(type(adapter).argument_schemas) == {"dispatch": "deep-arguments-v1"}


# --- owner gate F, clause 2: raw output reaches nothing ---


def _everything_the_adapter_produced(adapter, receipt, verification, root: Path) -> str:
    """Every value the adapter can hand onward, plus everything it left on disk.

    The runtime records, serves and streams ONLY what an adapter returns, so a
    secret absent from all of it is absent from the journal, the API payloads and
    the SSE frames that are built from those records.
    """
    parts = [
        json.dumps(receipt.as_dict(), sort_keys=True),
        json.dumps({
            "state": verification.state, "detail": verification.detail,
            "refs": list(verification.evidence_refs)}, sort_keys=True),
        repr(adapter.__dict__),
    ]
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            parts.append(path.read_bytes().decode("utf-8", errors="replace"))
    return "\n".join(parts)


def test_a_planted_secret_in_stdout_and_stderr_reaches_nothing(tmp_path):
    adapter, root, _log = a_harness(
        tmp_path, FAKEDSH_STDOUT=SECRET, FAKEDSH_STDERR=SECRET,
        FAKEDSH_WRITE_FILE="touched.txt:done")
    request = a_request()
    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)
    assert receipt.outcome == "succeeded"
    assert SECRET not in _everything_the_adapter_produced(
        adapter, receipt, verification, root)


def test_a_secret_planted_where_a_version_belongs_is_never_echoed_back(tmp_path):
    adapter, root, _log = a_harness(tmp_path, FAKEDSH_VERSION=SECRET)
    request = a_request()
    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)
    assert receipt.outcome == "failed"
    assert SECRET not in _everything_the_adapter_produced(
        adapter, receipt, verification, root)


def test_a_secret_never_survives_into_the_exception_graph(tmp_path):
    """A child really emitted the secret; then a spawn fails and must say nothing."""
    adapter, _root, log = a_harness(tmp_path, FAKEDSH_STDOUT=SECRET)
    first = run_once(adapter, a_request(action_id="act-1"))
    assert first.outcome == "succeeded"  # the secret was genuinely captured
    assert len(_fakedsh.task_spawns(log)) == 1

    # Now break the pin so the very next spawn cannot be built at all.
    object.__setattr__(adapter._pin, "entrypoint", "C:/dsh/lib/bin.js\x00evil")
    with pytest.raises(DshHarnessError) as caught:
        run_once(adapter, a_request(action_id="act-2", work_item_id="work-002"))
    chain: list[str] = []
    error: BaseException | None = caught.value
    while error is not None:
        chain.extend([repr(error), str(error)])
        error = error.__cause__ or error.__context__
    joined = "\n".join(chain)
    assert SECRET not in joined
    # The refusal names the rule, never the child's words or the pinned path.
    assert joined.count("could not start the pinned build") >= 1
    assert "bin.js" not in joined


def test_a_broken_entrypoint_pin_fails_the_preflight_and_spawns_no_task(tmp_path):
    adapter, root, log = a_harness(tmp_path)
    object.__setattr__(
        adapter._pin, "entrypoint", str(Path(_fakedsh.FAKE_DSH).parent / "absent.py"))
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed"
    assert "version preflight" in receipt.detail
    assert _fakedsh.task_spawns(log) == []
    assert not (root / MARKER_DIR).exists()


def test_an_output_bomb_is_bounded_and_never_reported_as_a_success(tmp_path):
    adapter, root, log = a_harness(
        tmp_path, FAKEDSH_BOMB_BYTES=str(4 * 1024 * 1024), FAKEDSH_STDOUT=SECRET)
    request = a_request()
    receipt = run_once(adapter, request)
    assert receipt.outcome == "failed"
    assert "capture bound" in receipt.detail
    assert len(_fakedsh.task_spawns(log)) == 1
    verification = adapter.verify(request, receipt)
    assert SECRET not in _everything_the_adapter_produced(
        adapter, receipt, verification, root)
    # The receipt is small no matter how much the child wrote.
    assert len(json.dumps(receipt.as_dict())) < 2000


# --- owner gate F, clause 3: a timeout is a fixed failure ---


def test_a_task_that_overruns_its_timeout_is_a_fixed_failure_with_no_child_left(
        tmp_path):
    adapter, _root, log = a_harness(tmp_path, FAKEDSH_SLEEP="30")
    receipt = run_once(adapter, a_request(timeout=1))
    assert receipt.outcome == "failed" and receipt.exit_code is None
    assert "timeout" in receipt.detail
    assert len(_fakedsh.task_spawns(log)) == 1
    assert adapter._runner.active_tokens() == ()


def test_a_non_zero_exit_is_a_failure_and_carries_no_child_text(tmp_path):
    adapter, _root, _log = a_harness(
        tmp_path, FAKEDSH_EXIT="9", FAKEDSH_STDOUT=SECRET)
    receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed" and receipt.exit_code == 9
    assert SECRET not in receipt.detail


# --- owner gate F, clause 4: the marker never lets a task repeat ---


def _markers(root: Path) -> list[Path]:
    return sorted((root / MARKER_DIR).glob("*.marker"))


def test_a_crash_after_the_marker_never_repeats_the_dsh_task(tmp_path):
    """The marker is 1 before the crash and 1 after it; the task ran once."""
    adapter, root, log = a_harness(tmp_path, FAKEDSH_WRITE_FILE="touched.txt:done")
    request = a_request()
    first = run_once(adapter, request)
    assert first.outcome == "succeeded"
    assert len(_markers(root)) == 1
    assert len(_fakedsh.task_spawns(log)) == 1

    # The crash: a brand-new adapter over the same root, holding no memory of
    # the attempt -- exactly what a restarted process has.
    node, entrypoint = _fakedsh.fake_pins()
    restarted = DshHarnessAdapter(
        DshPin(node_executable=node, entrypoint=entrypoint,
               env_allow=(_fakedsh.SPAWN_LOG,)),
        adapter._runner, root=root, clock=lambda: NOW, ids=_Ids(),
        adapter_id=PROVIDER_ID)
    second = run_once(restarted, request)
    assert second.outcome == "unknown"
    assert "never repeated" in second.detail
    assert len(_markers(root)) == 1, "the marker must stay 1 -> 1"
    assert len(_fakedsh.task_spawns(log)) == 1, "the task must not run twice"


def test_the_marker_is_written_before_the_task_and_not_after_it(tmp_path):
    """A crash DURING the task must still be covered, so the marker precedes it."""
    adapter, root, log = a_harness(tmp_path, FAKEDSH_EXIT="9")
    run_once(adapter, a_request())
    # The task failed, yet the marker exists: it guards the SPAWN, not the result.
    assert len(_markers(root)) == 1
    assert len(_fakedsh.task_spawns(log)) == 1


# --- owner gate F, clause 5: a retry is causally fresh ---


def test_a_new_action_uses_fresh_causal_ids_and_a_fresh_home(tmp_path):
    adapter, _root, log = a_harness(tmp_path)
    first = run_once(adapter, a_request(action_id="act-1"))
    second = run_once(adapter, a_request(action_id="act-2", work_item_id="work-002"))
    assert first.receipt_id != second.receipt_id
    homes = [row["dsh_home"] for row in _fakedsh.task_spawns(log)]
    assert len(homes) == 2 and homes[0] != homes[1]


# --- verification reads the workspace, never the task's own account ---


def test_exit_zero_with_no_workspace_change_is_never_a_verified_success(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)
    request = a_request()
    receipt = run_once(adapter, request)
    assert receipt.outcome == "succeeded"
    assert "not a verification" in receipt.detail
    verification = adapter.verify(request, receipt)
    assert isinstance(verification, AdapterVerification)
    # `error`, not `unavailable`: the runtime resolves an unavailable verifier to
    # observed success, which is exactly what absence of proof may never buy.
    assert verification.state == "error"
    assert verification.state != "unavailable"
    assert verification.evidence_refs == ()


def test_a_real_change_is_read_but_this_build_can_verify_no_success_from_it(tmp_path):
    """The change is seen; the claim is not made, because nothing durable backs it."""
    adapter, root, _log = a_harness(
        tmp_path, FAKEDSH_WRITE_FILE="src/added.txt:written by the task")
    request = a_request()
    receipt = run_once(adapter, request)
    assert (root / "work" / "work-001" / "src" / "added.txt").exists()
    verification = adapter.verify(request, receipt)
    assert verification.state == "error"
    assert verification.state not in {"verified", "unavailable"}
    assert verification.evidence_refs == (), "an unbacked identifier is not evidence"
    assert "no durable evidence record" in verification.detail


def test_a_change_outside_the_authorized_subtree_is_a_mismatch(tmp_path):
    adapter, root, _log = a_harness(
        tmp_path, FAKEDSH_WRITE_FILE="inside.txt:ok",
        FAKEDSH_ESCAPE_FILE="other-item/stolen.txt:outside")
    request = a_request()
    receipt = run_once(adapter, request)
    assert receipt.outcome == "succeeded"
    verification = adapter.verify(request, receipt)
    assert verification.state == "mismatch"
    assert verification.evidence_refs == ()
    assert (root / "work" / "other-item" / "stolen.txt").exists()


def test_verification_without_a_snapshot_is_an_error_not_an_absent_verifier(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)
    request = a_request()
    receipt = run_once(adapter, request)
    fresh = DshHarnessAdapter(
        adapter._pin, adapter._runner, root=adapter._root, clock=lambda: NOW,
        ids=_Ids(), adapter_id=PROVIDER_ID)
    verification = fresh.verify(request, receipt)
    assert verification.state == "error"
    assert verification.state != "unavailable"
    assert "no pre-task snapshot" in verification.detail


# --- observation claims nothing ---


def test_observing_the_harness_spawns_nothing_and_claims_nothing(tmp_path):
    adapter, _root, log = a_harness(tmp_path)
    observed = adapter.observe("inst-1", "run-1")
    assert observed.health == "unknown"
    assert observed.available_capabilities == ()
    assert _fakedsh.spawns(log) == []


def test_no_child_is_left_owned_after_any_of_these_relations(tmp_path):
    adapter, _root, _log = a_harness(tmp_path)
    run_once(adapter, a_request())
    assert adapter._runner.active_tokens() == ()
