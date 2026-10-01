"""Deterministic preview terms. Only the derived acceptance trailer is outside its digest."""
from __future__ import annotations

import difflib
import hashlib
import json
from datetime import datetime

from .contract_values import ContractError, _id
from .contracts import DecisionReceipt, EvidenceRef
from .task_contracts import _title

PATCH_LIMIT = 256 * 1024


def asked(body):
    if type(body) is not dict or set(body) - {"branch", "title", "documents"}:
        raise ContractError("accept preview has only branch, title and documents")
    result = dict(body)
    if "title" in result:
        result["title"] = _title(result["title"])
    if "branch" in result and (type(result["branch"]) is not str or len(result["branch"]) > 240):
        raise ContractError("branch must be bounded text")
    docs = result.get("documents")
    if docs is not None:
        if type(docs) is not list or len(docs) > 2000:
            raise ContractError("documents must be a bounded list")
        for ref in docs:
            _id("artifact_ref", ref)
        if len(set(docs)) != len(docs):
            raise ContractError("documents must be distinct")
    return result


def basis_and_message(context, title):
    basis = context.basis
    values = tuple(row.value for row in context.recovered.records)
    decision = next(row for row in values if isinstance(row, DecisionReceipt)
                    and row.receipt_id == basis.decision_id)
    proof = next((row for row in values if isinstance(row, EvidenceRef)
                  and row.uri == f"verification/{basis.verified_action}"), None)
    signer = None if proof is None else proof.verifier_instance_id
    cycle = context.recovered.envelope.cycle_id if context.workflow is None else (
        f"{context.workflow[0]} revision {context.workflow[1]}")
    local_time = datetime.fromisoformat(decision.decided_at.replace("Z", "+00:00")).astimezone().isoformat()
    message = (f"{title}\n\nCycle: {cycle}\nVerified by: {signer or 'none'}\n"
               f"Accepted by: {decision.actor}\nFinal gate: {decision.gate_id}\n"
               f"Decided at: {local_time}\n\nConduct-Task: {context.task.task_id}\n"
               f"Conduct-Run: {context.recovered.envelope.run_id}\n")
    return {"final_gate": basis.final_gate, "decided_at": basis.decided_at,
            "verified_action": basis.verified_action, "verifier_instance_id": signer,
            "accept_manifest_digest": basis.accept_manifest_digest}, message


def seal_terms(preview):
    fields = {key: preview[key] for key in (
        "run_id", "kind", "basis", "branch", "author", "message", "documents", "skipped")}
    fields["base"] = preview["base"]["commit"]
    fields["files"] = [{key: row[key] for key in ("path", "state", "mode", "git_oid")}
                       for row in preview["files"]]
    encoded = json.dumps(fields, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    identity = "acc-" + hashlib.sha256((preview["run_id"] + digest).encode("ascii")).hexdigest()[:32]
    preview["accept_digest"] = digest
    preview["message"] += f"Conduct-Acceptance: {identity}\n"


def binary(data):
    try:
        return "\0" in data.decode("utf-8")
    except UnicodeDecodeError:
        return True


def patch(files, before, after):
    result, size = [], 0
    for row in files:
        path = row["path"]
        old, new = before.get(path, b""), after.get(path, b"")
        if binary(old) or binary(new):
            lines = [f"Binary file {path}: {row['state']}\n"]
        else:
            lines = difflib.unified_diff(old.decode("utf-8").splitlines(keepends=True),
                                        new.decode("utf-8").splitlines(keepends=True),
                                        fromfile="a/" + path, tofile="b/" + path)
        for line in lines:
            if not line.endswith("\n"):
                line += "\n\\ No newline at end of file\n"
            length = len(line.encode("utf-8"))
            if size + length > PATCH_LIMIT:
                return {"text": "".join(result), "truncated": True}
            result.append(line)
            size += length
    return {"text": "".join(result), "truncated": False}
