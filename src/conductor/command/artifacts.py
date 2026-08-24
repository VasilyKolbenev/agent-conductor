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
    schema_version: int = 2

    _FIELDS = frozenset({
        "schema_version", "artifact_id", "artifact_ref", "run_id",
        "created_at", "media_type", "content", "source_action_id",
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
