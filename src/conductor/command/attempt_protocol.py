"""Immutable test claims and pre-check seals. These objects never grant acceptance."""
import hashlib
import json
import os
from pathlib import Path

from ..ownership import write_guard
from .accept_manifest import SnapshotRefused
from .accept_snapshot import _folder, _hold, _put, _read, read_snapshot
from .contract_values import _digest, _id, _thaw_json
from .feedback_payload import payload_bytes, settled_payload
from .path_admission import admit_file, admit_name
from .result_manifest import manifest_digest, rebuild_manifest
from .run_store import _exclusive_bytes, _fsync_dir, _root_gate

_LIMIT = 512 * 1024
_IDENTITY = ("run", "action", "attempt", "instance", "grant", "grant_digest")
_SEED_KEYS = ("source", "task_id", "work_scope", "work_item_id", "base_commit", "base_tree",
              "object_format")
_SEAL_KEYS = frozenset({"version", "run", "node", "action", "attempt", "instance", "grant",
    "grant_digest", "input_artifact_ids", "result_manifest", "result_manifest_digest", "seed",
    "snapshot_digest", "workspace_tree", "subtree_tree", "work_modes", "test_report_digest",
    "policy", "toolpin", "checker"})
_OUTCOME_KEYS = frozenset({"version", "run", "action", "attempt", "seal_digest", "checker",
                           "state", "detail", "feedback_digest"})


def _bad():
    return SnapshotRefused("attempt_protocol_invalid")


def canonical(value):
    return json.dumps(_thaw_json(value), sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def _unique(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise _bad()
    return value


def _path(root, request, kind):
    action = _id("action_id", request.action_id)
    admit_name(action, "action_id")
    folder, suffix = {"claim": ("tests", ".started.json"),
                      "report": ("tests", ".protocol.json"),
                      "seal": ("actions", ".json"),
                      "outcome": ("actions", ".outcome.json")}[kind]
    return _folder(root, request.run_id) / folder / (action + suffix)


def _read_optional(root, path):
    try:
        value = json.loads(_read(root, path, _LIMIT), object_pairs_hook=_unique)
        if type(value) is not dict:
            raise _bad()
        return value
    except FileNotFoundError:
        return None


def _write(root, request, kind, value):
    payload = canonical(value)
    if len(payload) > _LIMIT:
        raise _bad()
    _put(root, _path(root, request, kind), payload)


def _identity(request):
    value = dict(zip(_IDENTITY, (request.run_id, request.action_id, request.attempt_id,
        request.instance_id, request.run_authorization_id, request.run_authorization_digest)))
    for key in _IDENTITY[:-1]:
        _id(key, value[key])
    _digest("grant_digest", value["grant_digest"])
    return value


def _binding(request, binding):
    value = _thaw_json(binding)
    if (type(value) is not dict or set(value) != set(_IDENTITY) | {
            "policy", "toolpin", "workspace_tree", "work_modes"}
            or any(value.get(k) != v for k, v in _identity(request).items())):
        raise _bad()
    for key in ("policy", "toolpin", "workspace_tree", "work_modes"):
        _digest(key, value[key])
    return value


def claim_test_run(root, request, binding):
    """Reserve this exact action once; even an incomplete existing marker refuses respawn."""
    root = Path(root).resolve()
    value = {"version": 1, "binding": _binding(request, binding)}
    with write_guard(root), _root_gate(root).lock:
        path = _path(root, request, "claim")
        _hold(root, path)
        if os.path.lexists(path) or os.path.lexists(_path(root, request, "report")):
            return False
        admit_file(path, "test claim")
        path.parent.mkdir(parents=True, exist_ok=True)
        _hold(root, path)
        try:
            _exclusive_bytes(path, canonical(value))
        except FileExistsError:
            return False
        _fsync_dir(path.parent)
        return True


def _report(value):
    from .adapters.local_test_receipt import settled_report
    return settled_report(value)


def record_test_run(root, request, report):
    root = Path(root).resolve()
    report = _report(report)
    binding = _binding(request, report["binding"])
    with write_guard(root), _root_gate(root).lock:
        claim = _read_optional(root, _path(root, request, "claim"))
        if claim != {"version": 1, "binding": binding}:
            raise _bad()
        _write(root, request, "report", report)


def read_test_run(root, request):
    root = Path(root).resolve()
    claim = _read_optional(root, _path(root, request, "claim"))
    report = _read_optional(root, _path(root, request, "report"))
    if claim is None and report is None:
        return None
    if report is None:
        raise _bad()
    report = _report(report)
    binding = _binding(request, report["binding"])
    if claim != {"version": 1, "binding": binding}:
        raise _bad()
    return report


def _checker(verifier):
    return {"instance": _id("checker_instance", verifier.instance_id),
            "adapter": _id("checker_adapter", verifier.adapter_id)}


def _seed(seed):
    return {key: getattr(seed, key) for key in _SEED_KEYS}


def anchor_extra(request, seal):
    """The ledger anchor names an attempt; its digest seals all of the prepared facts."""
    return {"action_id": request.action_id, "attempt_id": request.attempt_id,
            "instance_id": request.instance_id, "node_id": request.node_id,
            "authorization_id": request.run_authorization_id,
            "authorization_digest": request.run_authorization_digest,
            "snapshot_digest": seal["snapshot_digest"],
            "test_report_digest": seal["test_report_digest"],
            "checker_instance_id": seal["checker"]["instance"],
            "checker_adapter_id": seal["checker"]["adapter"]}


def _ledger_anchor(values, request, seal, result, proof):
    from .contracts import ActionRequest, ActionResultReceipt, EvidenceRef
    from .correction_feedback import CorrectionFeedback
    anchors = [(i, value) for i, value in enumerate(values) if isinstance(value, EvidenceRef)
               and value.uri == "attempt-seal/" + request.action_id]
    requests = [i for i, value in enumerate(values) if isinstance(value, ActionRequest)
                and value.action_id == request.action_id]
    results = [i for i, value in enumerate(values) if isinstance(value, ActionResultReceipt)
               and value.action_id == request.action_id]
    if len(anchors) != 1 or len(requests) != 1 or len(results) != 1:
        raise _bad()
    position, anchor = anchors[0]
    if (not requests[0] < position < results[0] or values[results[0]] != result
            or anchor.kind != "attempt_seal" or anchor.run_id != request.run_id
            or anchor.created_by != "runtime" or anchor.verification != "unverified"
            or anchor.digest != digest(seal) or anchor.verified_by is not None
            or anchor.verified_at is not None or anchor.verifier_instance_id is not None
            or _thaw_json(anchor.extra) != anchor_extra(request, seal)):
        raise _bad()
    feedback = [i for i, value in enumerate(values) if type(value) is CorrectionFeedback
                and value.source_action_id == request.action_id]
    if any(i <= position for i in feedback):
        raise _bad()
    if proof is not None:
        signatures = [i for i, value in enumerate(values) if value == proof]
        if len(signatures) != 1 or signatures[0] <= position:
            raise _bad()


def _settled_seal(request, wrapped):
    if (type(wrapped) is not dict or set(wrapped) != {"version", "seal", "digest"}
            or type(wrapped["version"]) is not int or wrapped["version"] != 1):
        raise _bad()
    seal = wrapped["seal"]
    if (type(seal) is not dict or set(seal) != _SEAL_KEYS
            or type(seal["version"]) is not int or seal["version"] != 1
            or any(seal.get(k) != v for k, v in _identity(request).items())
            or seal["node"] != request.node_id or digest(seal) != wrapped["digest"]
            or type(seal["seed"]) is not dict or set(seal["seed"]) != set(_SEED_KEYS)
            or type(seal["checker"]) is not dict
            or set(seal["checker"]) != {"instance", "adapter"}):
        raise _bad()
    for key in ("snapshot_digest", "workspace_tree", "subtree_tree", "work_modes",
                "test_report_digest", "policy", "toolpin", "result_manifest_digest"):
        _digest(key, seal[key])
    _id("checker_instance", seal["checker"]["instance"])
    _id("checker_adapter", seal["checker"]["adapter"])
    if seal["checker"]["instance"] == request.instance_id:
        raise _bad()
    manifest = rebuild_manifest(seal["result_manifest"])
    if (manifest_digest(manifest) != seal["result_manifest_digest"]
            or (manifest["action_id"], manifest["attempt_id"]) != (
                request.action_id, request.attempt_id)
            or list(manifest["input_artifact_ids"]) != seal["input_artifact_ids"]):
        raise _bad()
    return seal


def seal_attempt(root, request, verifier, material, frame, seed, test_report):
    """Publish a prepared snapshot/report binding before the checker, without a verdict."""
    root = Path(root).resolve()
    report = read_test_run(root, request)
    if report is None or report != _report(test_report):
        raise _bad()
    binding = report["binding"]
    manifest = _thaw_json(rebuild_manifest(material.result_manifest))
    seed_value = _seed(seed)
    snapshot = read_snapshot(root, request.run_id, frame.accept_manifest_digest,
                             object_format=seed.object_format or "sha1")
    modes = _thaw_json(frame.work_modes)
    if (digest(_thaw_json(material.after)) != binding["workspace_tree"]
            or digest(modes) != binding["work_modes"]
            or manifest["input_artifact_ids"] != list(material.input_artifact_ids)
            or report["status"] not in {"passed", "failed", "zero_tests"}):
        raise _bad()
    seal = {"version": 1, **_identity(request), "node": request.node_id,
            "input_artifact_ids": list(material.input_artifact_ids),
            "result_manifest": manifest, "result_manifest_digest": manifest_digest(manifest),
            "seed": seed_value, "snapshot_digest": snapshot.digest,
            "workspace_tree": binding["workspace_tree"], "subtree_tree": frame.work_tree_digest,
            "work_modes": binding["work_modes"], "test_report_digest": digest(report),
            "policy": binding["policy"], "toolpin": binding["toolpin"],
            "checker": _checker(verifier)}
    wrapped = {"version": 1, "seal": seal, "digest": digest(seal)}
    _settled_seal(request, wrapped)
    with write_guard(root), _root_gate(root).lock:
        _write(root, request, "seal", wrapped)
    return wrapped


def finish_attempt(root, request, seal, verifier, verification):
    """Record what the checker actually returned, including a typed rejection's hash."""
    root = Path(root).resolve()
    body = _settled_seal(request, seal)
    if (body["checker"] != _checker(verifier) or verification.action_id != request.action_id
            or verification.adapter_id != verifier.adapter_id):
        raise _bad()
    feedback = verification.feedback
    feedback_digest = None
    if feedback is not None:
        payload = settled_payload(json.loads(feedback))
        if (verification.state, verification.detail) != ("mismatch", "rejected"):
            raise _bad()
        if _thaw_json(verification.result_manifest) != body["result_manifest"]:
            raise _bad()
        feedback_digest = "sha256:" + hashlib.sha256(payload_bytes(payload)).hexdigest()
    outcome = {"version": 1, "run": request.run_id, "action": request.action_id,
               "attempt": request.attempt_id, "seal_digest": seal["digest"],
               "checker": _checker(verifier), "state": verification.state,
               "detail": verification.detail, "feedback_digest": feedback_digest}
    with write_guard(root), _root_gate(root).lock:
        if _read_optional(root, _path(root, request, "seal")) != seal:
            raise _bad()
        _write(root, request, "outcome", outcome)


def read_attempt_seal(root, request):
    """Return the unique prepared/completed pair; absence is different from corruption."""
    root = Path(root).resolve()
    wrapped = _read_optional(root, _path(root, request, "seal"))
    outcome = _read_optional(root, _path(root, request, "outcome"))
    if wrapped is None:
        if outcome is not None:
            raise _bad()
        return None
    seal = _settled_seal(request, wrapped)
    if (outcome is None or set(outcome) != _OUTCOME_KEYS or type(outcome["version"]) is not int
            or outcome["version"] != 1 or outcome["run"] != request.run_id
            or outcome["action"] != request.action_id or outcome["attempt"] != request.attempt_id
            or outcome["seal_digest"] != wrapped["digest"]
            or outcome["checker"] != seal["checker"]):
        raise _bad()
    if outcome["state"] not in {"verified", "unavailable", "mismatch", "error"}:
        raise _bad()
    if type(outcome["detail"]) is not str:
        raise _bad()
    if outcome["feedback_digest"] is not None:
        _digest("feedback_digest", outcome["feedback_digest"])
    return seal, outcome


def _source_documents(recovered, request):
    from .artifacts import latest_artifacts, settled_products
    from .attempt_replay import proposal_named_by, values_the_proposal_saw
    values = tuple(row.value for row in recovered.records)
    cut = values_the_proposal_saw(values, proposal_named_by(request))
    if cut is None:
        raise _bad()
    refs = (request.arguments["instruction_ref"], *request.arguments["artifact_refs"])
    return tuple(latest_artifacts(settled_products(cut), (ref,))[0] for ref in refs)


def read_bound_protocol(root, recovered, request, seed, result, *, proof=None):
    """Validate historical source, checker, report and result before projecting sealed bytes."""
    from .contracts import frozen_config_bindings
    from .correction_feedback import CorrectionFeedback
    from .graph_definition import GraphDefinition
    from .verify_holds import CHECKER_REJECTED
    pair = read_attempt_seal(root, request)
    if pair is None:
        return None
    seal, outcome = pair
    values = tuple(row.value for row in recovered.records)
    _ledger_anchor(values, request, seal, result, proof)
    graph = next((v for v in values if isinstance(v, GraphDefinition)), None)
    node = next((n for n in graph.nodes if n.node_id == request.node_id), None) if graph else None
    checker = seal["checker"]
    if (result is None or node is None or node.instance_id != request.instance_id
            or node.verifier_instance_id != checker["instance"]
            or frozen_config_bindings(recovered.config).get(
                checker["instance"]) != checker["adapter"]
            or seal["seed"] != _seed(seed)):
        raise _bad()
    documents = _source_documents(recovered, request)
    if [doc.artifact_id for doc in documents] != seal["input_artifact_ids"]:
        raise _bad()
    report = read_test_run(root, request)
    if (report is None or digest(report) != seal["test_report_digest"]
            or any(report["binding"][key] != seal[key] for key in (
                "policy", "toolpin", "workspace_tree", "work_modes"))):
        raise _bad()
    # Re-parse the bound instruction, never a later replacement document.
    from .adapters.local_test_plan import plan_for
    plan = plan_for(documents[0])
    if plan is None or plan.as_dict() != report["policy"]:
        raise _bad()
    feedback = None
    if (result.outcome, result.detail) == ("verification_failed", CHECKER_REJECTED):
        if (outcome["state"], outcome["detail"]) != ("mismatch", "rejected"):
            raise _bad()
        candidates = [v for v in values if type(v) is CorrectionFeedback
                      and v.source_action_id == request.action_id]
        if len(candidates) != 1:
            raise _bad()
        feedback = candidates[0]
        if ((feedback.run_id, feedback.source_attempt_id, feedback.source_node_id,
             feedback.authorization_id, feedback.authorization_digest) != (
                request.run_id, request.attempt_id, request.node_id,
                request.run_authorization_id, request.run_authorization_digest)
                or (feedback.checker_instance_id, feedback.checker_adapter_id) != (
                    checker["instance"], checker["adapter"])
                or feedback.result_manifest_digest != seal["result_manifest_digest"]
                or _thaw_json(feedback.result_manifest) != seal["result_manifest"]
                or "sha256:" + hashlib.sha256(payload_bytes(
                    _thaw_json(feedback.payload))).hexdigest() != outcome["feedback_digest"]):
            raise _bad()
    elif result.outcome == "succeeded":
        if (outcome["state"] != "verified" or proof is None
                or proof.verification != "verified"
                or proof.extra.get("attempt_seal_digest") != digest(seal)
                or proof.extra.get("accept_manifest_digest") != seal["snapshot_digest"]
                or proof.extra.get("work_tree_digest") != seal["subtree_tree"]
                or report["status"] != "passed"):
            raise _bad()
    else:
        raise _bad()
    return seal, report, feedback
