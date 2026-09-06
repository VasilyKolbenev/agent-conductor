"""Immutable text artifacts passed between roles without filesystem authority."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any

from .attempt_replay import (
    action_request_for,
    proposal_named_by,
    values_the_proposal_saw,
)
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

#: The one capability whose action is given artifacts without publishing one.
DISPATCH_CAPABILITY = "dispatch"

#: WHICH argument key of each capability names the documents a step must be
#: GIVEN before it can do anything. Two keys and no third: the reviewed argument
#: schemas mark exactly these two as artifact inputs, and the two differ on one
#: real rule -- a dispatch's list may be empty, a review's may not -- which is
#: why they are two entries and not one shared name.
#:
#: This map is the ONE Python authority on the question, and it exists because
#: two readers now need the same answer: the chain rule below, which resolves a
#: published artifact's inputs against what its request asked for, and the
#: SCHEDULE, which refuses to call a step runnable while a document it needs
#: does not exist. Those two disagreeing would be a screen offering work the
#: store is about to refuse, or a store admitting a chain the plan never
#: authorized. `graph_schedule` therefore learns no argument key of its own; it
#: asks here.
#:
#: A capability with no entry requires no input DOCUMENT at all. That is not an
#: omission: `evidence`, `stop`, `retry` and `switch` each name an action or an
#: attempt, and `observe` carries no arguments this build reads.
_INPUT_REF_KEYS = MappingProxyType({
    DISPATCH_CAPABILITY: "artifact_refs",
    REVIEW_CAPABILITY: "target_artifact_refs",
})


def requires_input_artifacts(capability: object) -> bool:
    """Whether this capability's schema carries an artifact-input field at all.

    The pairing rule both node contracts ask before letting a step name a
    missing-artifact policy: a step that is never GIVEN a document cannot be
    waiting for one, and a policy stored on it would be a word with no
    behaviour -- which is worse than no field, because a person would read it as
    doing something.
    """
    return capability in _INPUT_REF_KEYS


def required_input_refs(capability: object,
                        arguments: Mapping[str, Any]) -> object:
    """What one step's arguments say it must be GIVEN, unjudged.

    Answers the RAW value under whichever key this capability owns, so that each
    caller applies its own judgement to it and this function adds none. The
    chain rule hands it to `latest_artifacts`, which refuses a malformed one by
    the grammar it already held; the schedule reads it through
    `unresolved_input_refs` below, which may not raise at all.

    Returning the raw value rather than a settled tuple is deliberate. A tuple
    settled here would have to decide what a malformed value means, and the two
    callers need different answers: a store validating a durable record must
    REFUSE it, and a pure reading recomputed on every question must not.

    Args:
        capability: The capability this step carries out, or None.
        arguments: The step's own argument map.

    Returns:
        The value under this capability's input key, or `()` when the
        capability names no such key or the arguments carry none.
    """
    key = _INPUT_REF_KEYS.get(capability)
    return () if key is None else arguments.get(key, ())


def unresolved_input_refs(
        documents: Iterable[ArtifactDocument], capability: object,
        arguments: Mapping[str, Any]) -> tuple[str, ...]:
    """Which of this step's required inputs no document stands for yet.

    A READING and never a refusal: it is recomputed from the journal on every
    question, so it answers for a plan whose arguments are malformed rather than
    raising at a caller that has no way to report it. Entries that are not text
    are not references and are passed over here; the argument schema refuses
    them at the door where a receipt can say so.

    Args:
        documents: Every value the run holds; non-artifacts are ignored.
        capability: The capability this step carries out, or None.
        arguments: The step's own argument map.

    Returns:
        The refs this step needs that no artifact stands for, in the order the
        step named them, with repeats collapsed to their first mention.
    """
    asked = required_input_refs(capability, arguments)
    if not isinstance(asked, (list, tuple)):
        return ()
    standing = {document.artifact_ref for document in documents
                if type(document) is ArtifactDocument}
    missing: list[str] = []
    for ref in asked:
        if type(ref) is str and ref not in standing and ref not in missing:
            missing.append(ref)
    return tuple(missing)


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
      standing when the request's PROPOSAL was written (`_the_request_saw`):
      "latest" means what it meant when a person confirmed it, and a document
      published after that proposal was never this review's material.
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
        prior for prior in _the_request_saw(source, prior_values)
        if isinstance(prior, ArtifactDocument)]
    try:
        resolved = latest_artifacts(
            prior_artifacts,
            required_input_refs(source.capability, arguments))
    except ContractError as error:
        raise ContractError(
            f"action {document.source_action_id!r} names inputs this run cannot "
            f"resolve: {error}") from None
    expected = tuple(row.artifact_id for row in resolved)
    if document.input_artifact_ids != expected:
        raise ContractError(
            f"artifact input ids do not match what action "
            f"{document.source_action_id!r} asked for")


def _the_request_saw(
        source: Any, prior_values: tuple[object, ...]) -> tuple[object, ...]:
    """The records a request's inputs are resolved over.

    Those standing when the request's proposal was written, for a request the
    runtime minted; everything standing before the artifact, for one that
    names no proposal -- so every journal written before the binding existed
    replays exactly as it did. The transport binds with the same two answers
    (`ArtifactHandoff.bound`, `.resolve`), which is what makes a review's
    recorded inputs and this judgement agree on every journal.
    """
    named = proposal_named_by(source)
    seen = None if named is None else values_the_proposal_saw(prior_values, named)
    return prior_values if seen is None else tuple(seen)


#: What each rule calls itself when it refuses a record naming no action. The
#: nouns are the rules' own, because a message saying "verification evidence"
#: under a result would send a reader to the wrong record.
EVIDENCE_NOUN = "verification evidence"
RESULT_NOUN = "succeeded review result"


def _review_source(
        action_id: str, prior_values: tuple[object, ...],
        what: str) -> Any | None:
    """The review request a record belongs to, or None for a KNOWN other one.

    WHICH chain a record belongs to is read from the authorizing request's own
    capability, and never from whether an artifact happens to stand for it. That
    difference is the whole of the two rules below. Keyed on the artifact, they
    switched THEMSELVES off in exactly the journals that needed them -- one that
    had not published a document yet, and one whose document had been deleted --
    because in both the artifact they looked for was not there to be found, and
    absence was read as "this is a dispatch, leave it alone".

    Three answers, and the third used to be silently the second:

    - a REVIEW request: the rules below judge the record;
    - a KNOWN request that is not a review. Its verification digests the CHANGE
      it made, a fact with no document behind it, so a rule demanding an
      artifact of it would refuse every honest dispatch in the product;
    - NO request at all, which is a broken relation and raises. It was left
      unjudged, on the reasoning that nothing here could judge a chain whose
      authorizing request is absent and that such a row could never be named by
      a result anyway. Both halves were wrong. A verification row is a claim
      that some action was verified, and an action nothing requested was never
      AUTHORIZED -- so the row is a claim about work no Human confirmed,
      standing in an immutable journal that replays as sound.

      And the shape is not one an honest run can leave. A crash truncates a
      journal's TAIL; it does not remove a record from the middle. The request
      is appended before the attempt that produces the evidence, so every prefix
      holding the evidence holds the request too.
    """
    source = action_request_for(prior_values, action_id)
    if source is None:
        raise ContractError(f"{what} names unknown action {action_id!r}")
    return source if source.capability == REVIEW_CAPABILITY else None


def _produced_by(
        action_id: str,
        prior_values: tuple[object, ...]) -> list[ArtifactDocument]:
    """Every artifact already standing for one action, in append order."""
    return [
        prior for prior in prior_values
        if isinstance(prior, ArtifactDocument)
        and prior.source_action_id == action_id]


def _verification_ids(
        action_id: str, prior_values: tuple[object, ...]) -> tuple[str, ...]:
    """Every verification evidence id already standing for one action."""
    return tuple(
        prior.evidence_id for prior in prior_values
        if _verified_action(prior) == action_id)


def validate_review_evidence(
        evidence: Any, prior_values: tuple[object, ...]) -> None:
    """A review's verification FOLLOWS one artifact of its own, and digests it.

    The writer already refuses each of these, and the writer is not the subject:
    a journal is bytes on a disk, and replay is where a build decides whether to
    believe them.

    Three relations, and only the last of them stood here before:

    - the review has published exactly one artifact, and it is ALREADY standing.
      A verification of a document nobody has published is a claim about
      nothing, and it used to replay as sound because the missing document was
      read as this being a dispatch;
    - no verification for this action stands yet. Two verified rows for one
      review are two answers to one question, and nothing in the journal says
      which one a result rests on;
    - the digest is THAT artifact's. Without it a raw journal could carry a real
      artifact, a verification pointing at a different digest, and a succeeded
      result -- and the run replayed as verified work nobody could reproduce.

    The plural side of the first relation is also held by
    `validate_artifact_source`, which refuses a second artifact for one action.
    It is written as one predicate rather than as a guard of its own precisely
    so it cannot become an unreachable branch: what this rule needs to say is
    "exactly one", and the reachable failure is zero.

    A KNOWN action that is not a review is left alone, and one nothing ever
    requested is refused outright; `_review_source` has all three readings.
    """
    action_id = _verified_action(evidence)
    if action_id is None:
        return
    if _review_source(action_id, prior_values, EVIDENCE_NOUN) is None:
        return
    produced = _produced_by(action_id, prior_values)
    if len(produced) != 1:
        raise ContractError(
            f"verification evidence for review action {action_id!r} stands on "
            f"{len(produced)} artifacts of that action rather than on one")
    if _verification_ids(action_id, prior_values):
        raise ContractError(
            f"review action {action_id!r} already carries verification evidence")
    if evidence.digest != produced[0].digest():
        raise ContractError(
            f"verification evidence for action {action_id!r} does not digest "
            f"the artifact that action produced")


def validate_review_result(
        result: Any, prior_values: tuple[object, ...]) -> None:
    """A succeeded review names the ONE verification evidence recorded for it.

    The last link, and it used to be the weakest. It was asked only when an
    artifact was found, so a succeeded review whose document was never written
    -- or was deleted out of the journal along with its verification -- was read
    as a dispatch and admitted with nothing behind it at all. Where it did run,
    it asked only that the result's references INTERSECT the verifications this
    run holds, which is weaker than the single chain production writes.

    Three relations, every one of them reached through the capability:

    - the review published exactly one artifact;
    - exactly one verification stands for it. `validate_review_evidence` refuses
      a second, so this is a second reader of that invariant on the plural side;
      the reachable failure is ZERO, a journal whose verification row is gone;
    - the result names exactly that evidence and nothing else. Given the two
      above, `attempt_replay` refuses every OTHER id a result could name, so the
      two spellings agree on any whole journal today -- this one says what
      production writes without borrowing that, and is held directly where a
      raw journal cannot reach it.

    A crash prefix is not a broken chain. An artifact with no verification yet,
    and an artifact and its verification with no terminal result yet, both
    replay: only a result that CLAIMS success is asked to account for itself.
    """
    if result.outcome != "succeeded":
        return
    if _review_source(result.action_id, prior_values, RESULT_NOUN) is None:
        return
    produced = _produced_by(result.action_id, prior_values)
    if len(produced) != 1:
        raise ContractError(
            f"succeeded review {result.action_id!r} stands on {len(produced)} "
            "artifacts of its own rather than on one")
    evidence_ids = _verification_ids(result.action_id, prior_values)
    if len(evidence_ids) != 1:
        raise ContractError(
            f"succeeded review {result.action_id!r} carries "
            f"{len(evidence_ids)} verification evidence rows rather than one")
    if tuple(result.evidence_refs) != evidence_ids:
        raise ContractError(
            f"succeeded review {result.action_id!r} does not name exactly the "
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
