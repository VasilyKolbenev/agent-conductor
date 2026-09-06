"""Resolve immutable role inputs and publish post-observation verification facts."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from .artifacts import ArtifactDocument, latest_artifacts
from .attempt_replay import proposal_named_by, values_the_proposal_saw
from .contract_values import _unique_ids
from .contracts import ActionRequest, EvidenceRef
from .run_store import RecordConflict, RecoveredRun, RunStore, StoreError


class ArtifactHandoff:
    """One store-backed handoff seam shared by provider-neutral role execution."""

    def __init__(
            self, store: RunStore, *, clock: Callable[[], str],
            ids: Callable[[str], str]) -> None:
        if type(store) is not RunStore or not callable(clock) or not callable(ids):
            raise TypeError("ArtifactHandoff requires a RunStore, clock and id source")
        self._store = store
        self._clock = clock
        self._ids = ids

    def resolve(
            self, run_id: str, artifact_refs: object) -> tuple[ArtifactDocument, ...]:
        asked = _unique_ids("artifact_refs", artifact_refs)
        if not asked:
            return ()
        recovered = self._store.read(run_id)
        if recovered.warnings:
            raise StoreError("artifact resolution refuses unjudged durable bytes")
        documents = (
            row.value for row in recovered.records if row.kind == "artifact")
        return tuple(ArtifactDocument.from_dict(row.as_dict()) for row in (
            latest_artifacts(documents, asked)))

    # -- what stood when the proposal was written --------------------------------
    #
    # A source is bound when it is confirmed, never chosen again at execution
    # (the owner's correction, 2026-09-06; R04 of the review of `8dec0e4`).
    # `resolve` answers "the latest document under the ref" at the moment it is
    # asked, so a document published between a confirmation and its execution
    # substituted the material the person had confirmed. These two answer from
    # the records standing BEFORE the proposal the request was minted from, so
    # the same journal binds the same bytes on every read, replay included.

    @staticmethod
    def named_proposal(request: ActionRequest) -> str | None:
        """The proposal a request was minted from, or None for one naming none.

        ONE spelling of the link, and it is the replay's
        (`attempt_replay.proposal_named_by`), reached through this seam because
        the adapters' value modules may import no relation module: the transport
        binds a request's inputs to the journal position the replay judges them
        against, so the two cannot drift. A request naming no proposal -- a
        transport test's, say -- is handed the file road and the latest document
        under each ref, byte-for-byte as before the binding existed.
        """
        return proposal_named_by(request)

    def bound(
            self, run_id: str, proposal_id: str,
            artifact_refs: object) -> tuple[ArtifactDocument, ...]:
        """The latest document under each ref among those the proposal saw."""
        asked = _unique_ids("artifact_refs", artifact_refs)
        if not asked:
            return ()
        return tuple(ArtifactDocument.from_dict(row.as_dict()) for row in (
            latest_artifacts(self._before(run_id, proposal_id), asked)))

    def instruction(
            self, run_id: str, proposal_id: str,
            instruction_ref: str) -> ArtifactDocument | None:
        """The latest document under the instruction's ref the proposal saw, or None.

        None is the file road's answer and not a refusal: a step whose
        instruction was never published as a document is read from the
        workspace file, byte-for-byte as before the durable road existed.
        """
        standing = [row for row in self._before(run_id, proposal_id)
                    if row.artifact_ref == instruction_ref]
        return ArtifactDocument.from_dict(standing[-1].as_dict()) if standing else None

    def _before(self, run_id: str, proposal_id: str) -> tuple[ArtifactDocument, ...]:
        """Every document appended before the named proposal, in journal order.

        Cut where the replay cuts (`attempt_replay.values_the_proposal_saw`),
        so what the transport hands a child and what `artifacts` later judges
        a review's inputs against are one answer.
        """
        recovered = self._store.read(run_id)
        if recovered.warnings:
            raise StoreError("artifact resolution refuses unjudged durable bytes")
        seen = values_the_proposal_saw(
            tuple(row.value for row in recovered.records), proposal_id)
        if seen is None:
            raise StoreError(f"proposal {proposal_id!r} is not in run {run_id!r}")
        return tuple(value for value in seen if isinstance(value, ArtifactDocument))

    def record_review(
            self, request: ActionRequest, artifact_ref: str, *,
            input_artifact_ids: Iterable[str] | None,
            content: str | None, adapter_id: str) -> EvidenceRef | None:
        """Publish one review output and its evidence, or recover either half.

        The inputs arrive as IDS. This seam only ever recorded their identity,
        so taking documents gave a caller a reason to hold an operator's whole
        durable material in memory between `execute` and `verify` -- and one
        did. Narrowing the parameter removes the reason rather than asking the
        caller to remember.
        """
        with self._store.transaction():
            recovered = self._store.read(request.run_id)
            artifact = self._review_artifact(
                recovered, request, artifact_ref, input_artifact_ids, content)
            if artifact is None:
                return None
            evidence = self._standing_evidence(recovered, request.action_id)
            if evidence is None:
                evidence = self._verified_evidence(
                    request, adapter_id, artifact.digest())
                self._store.append(evidence)
            self._hold_evidence(evidence, request, adapter_id, artifact.digest())
            return EvidenceRef.from_dict(evidence.as_dict())

    def record_dispatch(
            self, request: ActionRequest, *, adapter_id: str,
            digest: str | None) -> EvidenceRef | None:
        """Publish bounded tree-change evidence, or recover its durable row."""
        with self._store.transaction():
            recovered = self._store.read(request.run_id)
            evidence = self._standing_evidence(recovered, request.action_id)
            if evidence is None:
                if digest is None:
                    return None
                evidence = self._verified_evidence(request, adapter_id, digest)
                self._store.append(evidence)
            self._hold_evidence(evidence, request, adapter_id, digest)
            return EvidenceRef.from_dict(evidence.as_dict())

    def _review_artifact(
            self, recovered: RecoveredRun, request: ActionRequest,
            artifact_ref: str, input_artifact_ids: Iterable[str] | None,
            content: str | None) -> ArtifactDocument | None:
        standing = [
            row.value for row in recovered.records
            if row.kind == "artifact"
            and row.value.source_action_id == request.action_id]
        if len(standing) > 1:
            raise StoreError("one action produced more than one artifact")
        if standing:
            artifact = standing[0]
            if artifact.artifact_ref != artifact_ref:
                raise RecordConflict("review action records another artifact reference")
            if content is not None and artifact.content != content:
                raise RecordConflict("review action records different content")
            if input_artifact_ids is not None and (
                    artifact.input_artifact_ids != tuple(input_artifact_ids)):
                raise RecordConflict("review action records different input artifacts")
            return artifact
        if content is None or input_artifact_ids is None:
            return None
        artifact = ArtifactDocument(
            artifact_id=self._ids("artifact"), artifact_ref=artifact_ref,
            run_id=request.run_id, created_at=self._clock(),
            media_type="text/markdown", content=content,
            source_action_id=request.action_id,
            input_artifact_ids=tuple(input_artifact_ids))
        self._store.append(artifact)
        return artifact

    @staticmethod
    def _standing_evidence(
            recovered: RecoveredRun, action_id: str) -> EvidenceRef | None:
        uri = f"verification/{action_id}"
        rows = [
            row.value for row in recovered.records
            if row.kind == "evidence" and row.value.uri == uri]
        if len(rows) > 1:
            raise StoreError("one action carries more than one verification evidence")
        return rows[0] if rows else None

    def _verified_evidence(
            self, request: ActionRequest, adapter_id: str, digest: str) -> EvidenceRef:
        now = self._clock()
        return EvidenceRef(
            evidence_id=self._ids("evidence"), run_id=request.run_id,
            kind="verification", uri=f"verification/{request.action_id}",
            label="Bound adapter verification", created_by=adapter_id,
            observed_at=now, digest=digest, verification="verified",
            verified_by=adapter_id, verified_at=now)

    @staticmethod
    def _hold_evidence(
            evidence: EvidenceRef, request: ActionRequest,
            adapter_id: str, digest: str | None) -> None:
        if (evidence.run_id != request.run_id
                or evidence.uri != f"verification/{request.action_id}"
                or evidence.kind != "verification"
                or evidence.created_by != adapter_id
                or evidence.verification != "verified"
                or evidence.verified_by != adapter_id
                or evidence.digest is None
                or digest is not None and evidence.digest != digest):
            raise RecordConflict("action verification evidence records different facts")
