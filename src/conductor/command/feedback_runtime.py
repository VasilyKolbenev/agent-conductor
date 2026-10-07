"""Assign rejection provenance from the running action, never from model output."""
import hashlib
import json

from .contracts import _thaw_json, ContractError
from .correction_feedback import CorrectionFeedback
from .feedback_history import source_lap
from .result_manifest import manifest_digest


def record_rejection(store, request, verifier, verification, published, *, clock):
    if verification.feedback is None:
        return
    manifest = verification.result_manifest
    if manifest is None or manifest != published.result_manifest:
        raise ContractError("checker feedback does not name the published result manifest")
    identity = hashlib.sha256((request.run_id + "/" + request.action_id + "/" +
                               verifier.instance_id).encode("utf-8")).hexdigest()
    feedback_id = "feedback-" + identity
    with store.transaction():
        recovered = store.read(request.run_id)
        values = tuple(row.value for row in recovered.records)
        previous = next((v for v in values if type(v) is CorrectionFeedback
                         and v.feedback_id == feedback_id), None)
        definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
        feedback = CorrectionFeedback(feedback_id=feedback_id, run_id=request.run_id,
            authorization_id=request.run_authorization_id,
            authorization_digest=request.run_authorization_digest,
            source_action_id=request.action_id, source_attempt_id=request.attempt_id,
            source_node_id=request.node_id, source_lap=source_lap(definition, values, request),
            checker_instance_id=verifier.instance_id, checker_adapter_id=verifier.adapter_id,
            result_manifest=_thaw_json(manifest), result_manifest_digest=manifest_digest(manifest),
            payload=json.loads(verification.feedback.decode("utf-8")),
            recorded_at=previous.recorded_at if previous else clock())
        store.append(feedback)
