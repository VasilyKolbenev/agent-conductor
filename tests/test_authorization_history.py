"""Real durable grant/control history, including independently forged journals."""
from dataclasses import replace
import hashlib
import json

import pytest

from conductor.command.artifacts import ArtifactDocument
from conductor.command.authorization_history import journal_prefix_digest
from conductor.command.authorization_inputs import bind_inputs
from conductor.command.authorization_terms import AUTOMATION_CONTRACT, NodeLimit
from conductor.command.contracts import RunEnvelope, _thaw_json
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_authorization import RunAuthorization, RunAuthorizationControl
from conductor.command.run_store import CorruptRun, RunStore, StoreError, snapshot_digest


AT = "2026-09-21T16:00:00Z"
EXPIRES = "2026-09-21T17:00:00Z"
CONFIG = {"cycle": {"id": "cycle-one"}, "instances": [
    {"id": "doer", "adapter": "claude-code"},
    {"id": "checker", "adapter": "codex-cli"}],
    "workflow": {"id": "workflow-one", "revision": 1},
    "automation_contract": AUTOMATION_CONTRACT}


def tree(root, *, mode="policy", config=None):
    config = CONFIG if config is None else config
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id="run-one", cycle_id="cycle-one", created_at=AT,
        config_digest=snapshot_digest(config), mode=mode), config)
    definition = GraphDefinition(graph_id="graph-one", run_id="run-one", created_at=AT,
        nodes=(GraphNode(node_id="approve", kind="gate", title="Approve", gate_id="gate-one"),
               GraphNode(node_id="do", kind="task", title="Do", instance_id="doer",
                        capability="dispatch", arguments={"instruction_ref": "instructions"},
                        verifier_instance_id="checker", timeout_seconds=30, attempt_bound=2),),
        edges=(GraphEdge(from_node="approve", to_node="do", condition="on_approved"),))
    store.append(definition)
    store.append(ArtifactDocument(artifact_id="instructions-one", artifact_ref="instructions",
        run_id="run-one", created_at=AT, media_type="text/plain", content="Исправь файл.\n"))
    return store, definition


def grant(store, definition, **changes):
    recovered = store.read("run-one")
    instructions, inputs = bind_inputs(definition, tuple(r.value for r in recovered.records))
    fields = dict(authorization_id="grant-one", run_id="run-one", config_digest=snapshot_digest(
        _thaw_json(recovered.config)), graph_digest=definition.digest(), provider_config_digest="sha256:" + "1" * 64,
        source_prefix_digest=journal_prefix_digest(recovered.records), authorized_by="Owner",
        authorized_at=AT, expires_at=EXPIRES, supersedes=None,
        node_limits=(NodeLimit("do", 30, 2),), instruction_bindings=instructions,
        initial_input_bindings=inputs, max_actions=8, max_action_seconds=60,
        max_total_task_seconds=480)
    return RunAuthorization(**{**fields, **changes})


def control(authorization, action="pause", **changes):
    return RunAuthorizationControl(**{**dict(control_id="control-one", run_id="run-one",
        authorization_id=authorization.authorization_id,
        authorization_digest=authorization.authorization_digest, action=action,
        actor="Owner", recorded_at=AT, expected_control_id=None), **changes})


def snapshot(store):
    return {p.relative_to(store.project_root): p.read_bytes()
            for p in store.project_root.rglob("*") if p.is_file()}


def forged(store, kind, value):
    wrapper = {"record_type": kind, "record": value.as_dict()}
    raw = json.dumps(wrapper, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with (store.run_path("run-one") / "records.jsonl").open("ab") as stream:
        stream.write(raw.encode("utf-8") + b"\n")


def test_real_append_fresh_replay_pause_resume_and_irreversible_revoke(tmp_path):
    store, definition = tree(tmp_path)
    authorization = grant(store, definition)
    assert store.append(authorization)
    assert not store.append(authorization)
    pause = control(authorization)
    resume = control(authorization, "resume", control_id="resume", expected_control_id="control-one")
    revoke = control(authorization, "revoke", control_id="revoke", expected_control_id="resume")
    for value in (pause, resume, revoke):
        assert store.append(value)
    before = snapshot(store)
    reader = RunStore(tmp_path)
    assert [row.value for row in reader.read("run-one").records][-4:] == [
        authorization, pause, resume, revoke]
    assert not reader.append(revoke)
    with pytest.raises(StoreError, match="irreversible"):
        reader.append(control(authorization, "resume", control_id="late", expected_control_id="revoke"))
    assert snapshot(store) == before


@pytest.mark.parametrize("field", ["config_digest", "graph_digest", "source_prefix_digest"])
def test_wrong_digest_refuses_before_append_and_on_forged_replay(tmp_path, field):
    store, definition = tree(tmp_path)
    bad = grant(store, definition, **{field: "sha256:" + "2" * 64})
    before = snapshot(store)
    with pytest.raises(StoreError, match="digest|prefix"):
        store.append(bad)
    assert snapshot(store) == before
    forged(store, "run_authorization", bad)
    damaged = snapshot(store)
    with pytest.raises(CorruptRun, match="digest|prefix"):
        RunStore(tmp_path).read("run-one")
    assert snapshot(store) == damaged


@pytest.mark.parametrize("mode,marker", [("confirm", AUTOMATION_CONTRACT), ("policy", None),
                                        ("observe", AUTOMATION_CONTRACT)])
def test_no_implicit_upgrade_of_old_modes_or_unmarked_policy(tmp_path, mode, marker):
    config = {key: val for key, val in CONFIG.items() if key != "automation_contract"}
    if marker is not None:
        config["automation_contract"] = marker
    store, definition = tree(tmp_path, mode=mode, config=config)
    before = snapshot(store)
    with pytest.raises(StoreError, match="frozen Policy opt-in"):
        store.append(grant(store, definition))
    assert snapshot(store) == before


def test_prefix_digest_is_exact_canonical_wrappers_not_only_values(tmp_path):
    store, definition = tree(tmp_path)
    records = store.read("run-one").records
    raw = json.dumps([{"record_type": row.kind, "record": row.value.as_dict()} for row in records],
                     ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert grant(store, definition).source_prefix_digest == "sha256:" + hashlib.sha256(raw).hexdigest()


def test_new_instruction_after_preview_refuses_then_requires_explicit_rebinding(tmp_path):
    store, definition = tree(tmp_path)
    reviewed = grant(store, definition)
    store.append(ArtifactDocument(artifact_id="instructions-two", artifact_ref="instructions",
        run_id="run-one", created_at=AT, media_type="text/plain", content="Другая задача"))
    refreshed_prefix = journal_prefix_digest(store.read("run-one").records)
    stale = replace(reviewed, source_prefix_digest=refreshed_prefix, authorization_digest="")
    before = snapshot(store)
    with pytest.raises(StoreError, match="instructions differ"):
        store.append(stale)
    assert snapshot(store) == before
    replacement = grant(store, definition)
    assert replacement.instruction_bindings[0].artifact_id == "instructions-two"
    assert store.append(replacement)


@pytest.mark.parametrize("limits,reason", [
    ((NodeLimit("foreign", 30, 2),), "graph order"),
    ((NodeLimit("do", 31, 2),), "timeout exceeds"),
    ((NodeLimit("do", 30, 3),), "attempts exceed"),
])
def test_node_limits_cannot_enlarge_or_replace_frozen_work(tmp_path, limits, reason):
    store, definition = tree(tmp_path)
    before = snapshot(store)
    changes = {"node_limits": limits}
    if limits[0].node_id == "foreign":
        changes["instruction_bindings"] = ()
    candidate = grant(store, definition, **changes)
    with pytest.raises(StoreError, match=reason):
        store.append(candidate)
    assert snapshot(store) == before


def test_checker_time_is_reserved_in_addition_to_doer_time(tmp_path):
    store, definition = tree(tmp_path)
    with pytest.raises(StoreError, match="checker reservation"):
        store.append(grant(store, definition, max_action_seconds=59))
    assert store.append(grant(store, definition, max_action_seconds=60))


def test_stale_two_window_control_is_rejected_also_on_replay(tmp_path):
    store, definition = tree(tmp_path)
    authorization = grant(store, definition)
    store.append(authorization)
    store.append(control(authorization))
    stale = control(authorization, "revoke", control_id="stale", expected_control_id=None)
    before = snapshot(store)
    with pytest.raises(StoreError, match="predecessor is stale"):
        store.append(stale)
    assert snapshot(store) == before
    forged(store, "run_authorization_control", stale)
    with pytest.raises(CorruptRun, match="predecessor is stale"):
        RunStore(tmp_path).read("run-one")


def test_expired_resume_uses_recorded_instant_with_submicrosecond_precision(tmp_path):
    store, definition = tree(tmp_path)
    authorization = grant(store, definition, expires_at="2026-09-21T16:00:00.000000002Z")
    store.append(authorization)
    store.append(control(authorization))
    with pytest.raises(StoreError, match="expired"):
        store.append(control(authorization, "resume", control_id="late",
            expected_control_id="control-one", recorded_at=authorization.expires_at))
    assert store.append(control(authorization, "resume", control_id="before",
        expected_control_id="control-one", recorded_at="2026-09-21T16:00:00.000000001Z"))


def test_replacement_requires_revocation_or_expiry_and_exact_predecessor(tmp_path):
    store, definition = tree(tmp_path)
    first = grant(store, definition)
    store.append(first)
    with pytest.raises(StoreError, match="revoked or expired"):
        store.append(grant(store, definition, authorization_id="second", supersedes="grant-one"))
    store.append(control(first, "revoke"))
    with pytest.raises(StoreError, match="immediate predecessor"):
        store.append(grant(store, definition, authorization_id="second"))
    second = grant(store, definition, authorization_id="second", supersedes="grant-one")
    assert store.append(second)
    with pytest.raises(StoreError, match="current authorization"):
        store.append(control(first, "pause", control_id="stale", expected_control_id="control-one"))
    assert RunStore(tmp_path).read("run-one").records[-1].value == second


def test_subclass_cannot_bypass_registered_authorization_history_rules(tmp_path):
    class DerivedAuthorization(RunAuthorization):
        pass

    class DerivedControl(RunAuthorizationControl):
        pass

    store, definition = tree(tmp_path, mode="confirm")
    candidate = grant(store, definition)
    derived = DerivedAuthorization.from_dict(candidate.as_dict())
    derived_control = DerivedControl.from_dict(control(candidate).as_dict())
    before = snapshot(store)
    for value in (derived, derived_control):
        with pytest.raises(StoreError, match="exact record types"):
            store.append(value)
    assert snapshot(store) == before
