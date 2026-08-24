"""Immutable text artifacts passed between roles without filesystem authority."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any

from .attempt_replay import action_request_for
from .attempts import AttemptEvent
from .contract_values import (
    ABSENT,
    ContractError,
    _bound_id,
    _content_digest,
    _enum,
    _id,
    _raw,
    _schema,
    _take,
    _text,
    _timestamp,
    _unique_ids,
)


ARTIFACT_CONTENT_LIMIT = 49_152
ARTIFACT_MEDIA_TYPES = frozenset({"text/markdown", "text/plain"})


@dataclass(frozen=True)
class ArtifactDocument:
    """One immutable text result addressed by both identity and logical role.

    ``artifact_id`` names these exact bytes. ``artifact_ref`` is the stable
    handoff name a graph can carry across bounded passes; a consumer resolves
    its latest document in append order. Content is deliberately durable and
    is never inferred from a path, URI, process stream, or environment value.
    """

    artifact_id: str
    artifact_ref: str
    run_id: str
    created_at: str
    media_type: str
    content: str
    source_action_id: str | None = None
    input_artifact_ids: tuple[str, ...] | list[str] = ()
    schema_version: int = 2

    _FIELDS = frozenset({
        "schema_version", "artifact_id", "artifact_ref", "run_id",
        "created_at", "media_type", "content", "source_action_id",
        "input_artifact_ids",
    })

    def __post_init__(self) -> None:
        for name in ("artifact_id", "artifact_ref", "run_id"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "created_at", _timestamp("created_at", self.created_at))
        object.__setattr__(self, "media_type", _enum(
            "media_type", self.media_type, ARTIFACT_MEDIA_TYPES))
        content = _text("content", self.content)
        if len(content.encode("utf-8")) > ARTIFACT_CONTENT_LIMIT:
            raise ContractError(
                f"content must be at most {ARTIFACT_CONTENT_LIMIT} UTF-8 bytes")
        object.__setattr__(self, "content", content)
        if self.source_action_id is not None:
            object.__setattr__(self, "source_action_id", _id(
                "source_action_id", self.source_action_id))
        object.__setattr__(self, "input_artifact_ids", _unique_ids(
            "input_artifact_ids", self.input_artifact_ids))
        if self.source_action_id is None and self.input_artifact_ids:
            raise ContractError(
                "input_artifact_ids require a runtime source_action_id")
        object.__setattr__(self, "schema_version", _schema(self.schema_version))

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_ref": self.artifact_ref,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "media_type": self.media_type,
            "content": self.content,
        }
        if self.source_action_id is not None:
            out["source_action_id"] = self.source_action_id
        if self.input_artifact_ids:
            out["input_artifact_ids"] = list(self.input_artifact_ids)
        return out

    def digest(self) -> str:
        """Digest the canonical document; no second digest fact is stored."""
        return _content_digest(self.as_dict())

    @classmethod
    def from_dict(cls, value: object) -> "ArtifactDocument":
        data = _raw(value)
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(f"artifact carries unsupported field(s) {unknown!r}")
        return cls(
            artifact_id=_take(data, "artifact_id"),
            artifact_ref=_take(data, "artifact_ref"),
            run_id=_take(data, "run_id"),
            created_at=_take(data, "created_at"),
            media_type=_take(data, "media_type"),
            content=_take(data, "content"),
            source_action_id=_bound_id(
                "source_action_id", data.pop("source_action_id", ABSENT)),
            input_artifact_ids=data.pop("input_artifact_ids", ()),
            schema_version=data.pop("schema_version", 2),
        )


def latest_artifacts(
        documents: Iterable[ArtifactDocument],
        artifact_refs: object) -> tuple[ArtifactDocument, ...]:
    """Resolve logical refs to their latest immutable document, in asked order."""
    asked = _unique_ids("artifact_refs", artifact_refs)
    latest: dict[str, ArtifactDocument] = {}
    for document in documents:
        if type(document) is not ArtifactDocument:
            raise ContractError("artifact collection must contain ArtifactDocument values")
        if document.artifact_ref in asked:
            latest[document.artifact_ref] = document
    missing = [artifact_ref for artifact_ref in asked if artifact_ref not in latest]
    if missing:
        raise ContractError(f"artifact_refs name unavailable artifact(s) {missing!r}")
    return tuple(latest[artifact_ref] for artifact_ref in asked)


def validate_artifact_source(
        document: ArtifactDocument, prior_values: tuple[object, ...]) -> None:
    """A produced artifact follows the observed action that produced it."""
    if document.source_action_id is None:
        return
    source = action_request_for(prior_values, document.source_action_id)
    if source is None:
        raise ContractError(
            f"artifact names unknown source action {document.source_action_id!r}")
    observed = any(
        isinstance(prior, AttemptEvent)
        and prior.action_id == document.source_action_id
        and prior.phase == "execution_observed"
        for prior in prior_values)
    if not observed:
        raise ContractError(
            f"artifact source action {document.source_action_id!r} is not observed")
    known_artifacts = {
        prior.artifact_id for prior in prior_values
        if isinstance(prior, ArtifactDocument)}
    missing = sorted(set(document.input_artifact_ids) - known_artifacts)
    if missing:
        raise ContractError(
            f"artifact names unknown input artifact(s) {missing!r}")
    same_source = [
        prior for prior in prior_values
        if isinstance(prior, ArtifactDocument)
        and prior.source_action_id == document.source_action_id]
    if same_source:
        raise ContractError(
            f"source action {document.source_action_id!r} already produced an artifact")
    _artifact_answers_its_request(document, source, prior_values)


#: The one capability whose action publishes a durable artifact of its own. A
#: dispatch changes the work tree and its evidence is a digest of that change;
#: only a review turns material into a new document.
REVIEW_CAPABILITY = "review"


def _artifact_answers_its_request(
        document: ArtifactDocument, source: Any,
        prior_values: tuple[object, ...]) -> None:
    """The artifact is the one THIS request asked for, from the inputs it named.

    Existence was all that was held before: the source action was known, it was
    observed, and every input id was some artifact this run knows. None of that
    says the document is the one the action asked for. A journal could name a
    review's output under another reference, or claim it consumed artifacts the
    request never asked for, or claim it read an older revision of a reference
    that had since moved -- and every one of those replayed as sound.

    Three relations close it, and each is read from the REQUEST rather than from
    the document, because the request is what the operator authorized:

    - the action is a review. Nothing else produces an artifact;
    - the reference is the one the request named as its result;
    - the inputs are exactly the documents the request's own references resolve
      to, IN THE ORDER the request named them. Resolution is `latest_artifacts`
      -- the same function the transport resolves with -- against the records
      standing BEFORE this artifact, so "latest" means what it meant then.
    """
    if source.capability != REVIEW_CAPABILITY:
        raise ContractError(
            f"source action {document.source_action_id!r} is a "
            f"{source.capability!r} action and publishes no artifact")
    arguments = source.arguments
    if arguments.get("result_artifact_ref") != document.artifact_ref:
        raise ContractError(
            f"artifact {document.artifact_ref!r} is not the result reference "
            f"action {document.source_action_id!r} asked for")
    prior_artifacts = [
        prior for prior in prior_values if isinstance(prior, ArtifactDocument)]
    try:
        resolved = latest_artifacts(
            prior_artifacts, arguments.get("target_artifact_refs", ()))
    except ContractError as error:
        raise ContractError(
            f"action {document.source_action_id!r} names inputs this run cannot "
            f"resolve: {error}") from None
    expected = tuple(row.artifact_id for row in resolved)
    if document.input_artifact_ids != expected:
        raise ContractError(
            f"artifact input ids do not match what action "
            f"{document.source_action_id!r} asked for")


def validate_review_evidence(
        evidence: Any, prior_values: tuple[object, ...]) -> None:
    """Verification evidence for a review carries THAT review's own digest.

    The writer already refused a mismatch, and the writer is not the subject: a
    journal is bytes on a disk, and replay is where a build decides whether to
    believe them. Without this, a raw journal could carry a real artifact, a
    verification pointing at a different digest, and a succeeded result -- and
    the run replayed as verified work nobody could reproduce.

    Evidence for an action that produced no artifact is left alone. A dispatch's
    verification digests the CHANGE it made, which is a different fact with no
    document behind it.
    """
    action_id = _verified_action(evidence)
    if action_id is None:
        return
    produced = next(
        (prior for prior in prior_values
         if isinstance(prior, ArtifactDocument)
         and prior.source_action_id == action_id), None)
    if produced is None:
        return
    if evidence.digest != produced.digest():
        raise ContractError(
            f"verification evidence for action {action_id!r} does not digest "
            f"the artifact that action produced")


def validate_review_result(
        result: Any, prior_values: tuple[object, ...]) -> None:
    """A succeeded review names the verification evidence standing for it.

    The last link of the chain. An artifact and its evidence can both be honest
    and the RESULT still claim success without pointing at either, which is a
    receipt whose own journal cannot show what it rests on.
    """
    if result.outcome != "succeeded":
        return
    produced = next(
        (prior for prior in prior_values
         if isinstance(prior, ArtifactDocument)
         and prior.source_action_id == result.action_id), None)
    if produced is None:
        return
    evidence_ids = {
        prior.evidence_id for prior in prior_values
        if _verified_action(prior) == result.action_id}
    if not evidence_ids:
        raise ContractError(
            f"action {result.action_id!r} produced an artifact and succeeded "
            "with no verification evidence")
    if not evidence_ids & set(result.evidence_refs):
        raise ContractError(
            f"succeeded action {result.action_id!r} does not name the "
            "verification evidence recorded for it")


def _verified_action(value: object) -> str | None:
    """The action one verification evidence row stands for, or None.

    Read from the URI, which is where the writer puts it, and guarded by the
    kind so an evidence row of another kind that happens to share the shape is
    not mistaken for one.
    """
    kind = getattr(value, "kind", None)
    uri = getattr(value, "uri", None)
    if kind != "verification" or not isinstance(uri, str):
        return None
    prefix = "verification/"
    return uri[len(prefix):] if uri.startswith(prefix) else None
