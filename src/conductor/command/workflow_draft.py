"""The editable half of a workflow: a document on its way to being a revision.

``graph_template`` owns a published revision. It is finished by construction --
a ``GraphTemplate`` that exists is one that materializes -- which is exactly
right for something that must never change, and exactly wrong for something a
person is still drawing. A workflow under an editor's hand has a dangling edge,
a loop that points at a step nobody has added yet, a gate that guards nothing.
None of that is a template, and all of it is a draft.

So this module owns the other half, and it draws ONE line:

- a draft may be **INCOMPLETE**. No edge has to land, no gate has to stand in
  front of the work it guards, no loop has to reopen a step that exists, and a
  draft with no nodes at all is where every new workflow starts.
- a draft may never be **FOREIGN**. Everything it carries has to be something a
  ``GraphTemplate`` could carry: the same closed key set, the same node and edge
  contracts, the same ids. A key a template does not name is refused here for
  the same reason it is refused there.

The consequence is that the two documents cannot drift, because the topology
rules are never restated. What a draft is missing is discovered by asking the
real constructor and translating what it says -- ``draft_diagnostics`` and
``publish_candidate`` are the same call, one swallowing the refusal and one
raising it. One judge, two callers.

Two words are deliberately absent from a draft document. ``template_id`` is the
workflow's identity and comes from the route that addressed it; ``revision`` is
the number a publish is asking for. A draft that carried either could disagree
with the caller about which workflow it is or which revision it would become,
and a stored draft could then be mistaken for a stored revision. It cannot be:
the two words it would need are not in its vocabulary.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .contracts import (
    ContractError, _content_digest, _freeze_json, _id, _text, _timestamp,
    canonical_json)
from .graph_definition import GraphEdge, _exact, _json_list, _json_object
from .graph_template import (
    SCHEMA_VERSION,
    TEMPLATE_DIR,
    GraphTemplate,
    TemplateError,
    TemplateNode,
    load_template,
)

if TYPE_CHECKING:  # pragma: no cover - the store imports THIS module
    from .template_store import TemplateStore

#: The schema of the stored draft ENVELOPE -- the file, not the workflow inside
#: it. It is held exactly, for `graph_template`'s reason: the envelope is closed
#: at every level, so it cannot honestly read a revision of itself it has never
#: seen.
DRAFT_SCHEMA_VERSION = 1
#: The two words a draft has not got yet. Named here so the vocabulary below is
#: derived from the template's own rather than spelled a second time.
NOT_YET_FIELDS = frozenset({"template_id", "revision"})
#: What a draft document may carry: exactly a template's fields less the two a
#: draft does not have. Read OFF the contract, exactly as
#: ``api_contracts._TEMPLATE_FIELDS`` is, so a field added to ``GraphTemplate``
#: cannot become a field a draft silently refuses.
DRAFT_FIELDS = frozenset(GraphTemplate._FIELDS) - NOT_YET_FIELDS
#: The stored file's own shape.
ENVELOPE_FIELDS = frozenset({
    "schema_version", "workflow_id", "saved_at", "document"})
#: Bounds on a draft's size. The 64 KiB command-body ceiling already stops a
#: document far smaller than these, so what they add is a CONTRACT answer for an
#: oversized draft rather than a transport one -- and a bound that a stored
#: draft is held to on the way out as well as in.
MAX_DRAFT_NODES = 256
MAX_DRAFT_EDGES = 1024
#: Every code a diagnostic row may carry, derived from the exception TYPE the
#: real constructor raised and from nothing else. The prose is never parsed:
#: reading a message to decide what it meant is how two judges are born.
DIAGNOSTIC_CODES = frozenset({"template_refused", "contract_refused"})


class WorkflowDraftError(ContractError):
    """A draft document or envelope is not something a template could carry."""


class DraftRefused(ContractError):
    """A draft is well formed and does not yet construct a workflow revision.

    It carries the structured rows rather than only a sentence, because the
    difference between this and :class:`WorkflowDraftError` is the whole design:
    a foreign document is refused, and an incomplete one is EXPLAINED.
    """

    def __init__(self, diagnostics: tuple[Mapping[str, Any], ...]) -> None:
        self.diagnostics = tuple(dict(row) for row in diagnostics)
        super().__init__("this draft does not yet construct a workflow revision")


def _row(error: ContractError) -> dict[str, Any]:
    """One diagnostic, coded by the exception's TYPE and never by its words.

    ``node_id`` and ``field`` are present and ``null``. They are the shape a
    reader can rely on, and this build fills neither: the one judge is handed
    the whole document, so the only honest way to attribute its answer to a node
    would be to parse the sentence it wrote -- which is a second judge that can
    disagree with the first. A build that attributes will do it by handing the
    constructor a smaller value, not by reading its prose.
    """
    return {
        "code": ("template_refused" if isinstance(error, TemplateError)
                 else "contract_refused"),
        "message": str(error),
        "node_id": None,
        "field": None,
    }


def parse_document(value: object) -> dict[str, Any]:
    """Admit one draft document and hand back this module's own copy of it.

    Every node goes through ``TemplateNode.from_dict`` and every edge through
    ``GraphEdge.from_dict`` -- the same doors a published revision goes through,
    so a key, an id, a payload or a loop a template could not carry is refused
    here too. What is NOT asked is anything that needs the document as a WHOLE:
    whether an edge lands, whether ids repeat, whether the thing is acyclic,
    whether an effecting step stands behind a gate. Those are the questions
    ``draft_diagnostics`` puts to the real constructor.

    Returns:
        A fresh canonical document, rebuilt from the values this function
        settled rather than from the caller's own objects.

    Raises:
        WorkflowDraftError: The key set is not the draft vocabulary, the schema
            is not the one this build speaks, or a size bound is exceeded.
        ContractError: A node or an edge is not one a template could carry.
    """
    data = dict(_json_object("workflow draft document", value))
    supplied = set(data)
    if supplied != DRAFT_FIELDS:
        unknown = sorted(supplied - DRAFT_FIELDS)
        missing = sorted(DRAFT_FIELDS - supplied)
        raise WorkflowDraftError(
            f"a workflow draft document carries exactly {sorted(DRAFT_FIELDS)!r}; "
            f"unsupported {unknown!r}, missing {missing!r}")
    version = _exact("workflow draft schema_version", data["schema_version"], int)
    if version != SCHEMA_VERSION:
        raise WorkflowDraftError(
            f"this build speaks workflow schema_version {SCHEMA_VERSION} and this "
            f"draft claims {version}")
    title = _text("workflow draft title", data["title"])
    rows = _json_list("workflow draft nodes", data["nodes"])
    if len(rows) > MAX_DRAFT_NODES:
        raise WorkflowDraftError(
            f"a workflow draft carries at most {MAX_DRAFT_NODES} nodes")
    wires = _json_list("workflow draft edges", data["edges"])
    if len(wires) > MAX_DRAFT_EDGES:
        raise WorkflowDraftError(
            f"a workflow draft carries at most {MAX_DRAFT_EDGES} edges")
    nodes = tuple(TemplateNode.from_dict(row) for row in rows)
    edges = tuple(GraphEdge.from_dict(row) for row in wires)
    return {
        "schema_version": version,
        "title": title,
        "nodes": [node.as_dict() for node in nodes],
        "edges": [edge.as_dict() for edge in edges],
    }


def publish_candidate(
        document: Mapping[str, Any], *, workflow_id: str,
        revision: int) -> GraphTemplate:
    """Build the revision this draft WOULD be, or say what stops it.

    The identity and the number are supplied by the caller because a draft holds
    neither. Everything else is the draft's, and it is handed to the production
    constructor whole: this function adds no rule, restates no rule, and knows
    nothing about topology.

    Raises:
        DraftRefused: The document is well formed and does not construct.
    """
    candidate = dict(document)
    candidate["template_id"] = workflow_id
    candidate["revision"] = revision
    try:
        return GraphTemplate.from_dict(candidate)
    except ContractError as error:
        raise DraftRefused((_row(error),)) from None


def draft_digest(document: Mapping[str, Any]) -> str:
    """The identity of one draft document, in the store's own digest grammar.

    Over the CANONICAL bytes, so two documents that say the same thing in a
    different key order have one identity, and a document that differs by a
    single character has another. It names a DOCUMENT and never a moment: a
    draft saved twice with identical content keeps its digest, which is what
    makes a review of it survive an idempotent re-save.
    """
    return _content_digest(dict(document))


def unchanged_from_published(
        draft: Mapping[str, Any] | None, published: Mapping[str, Any] | None,
        *, workflow_id: str, revision: int) -> bool:
    """Would publishing this draft create a revision that says nothing new?

    Compared as the CANDIDATE would be built rather than as the draft is
    stored, because the two documents differ in exactly the two fields a draft
    never carries: `template_id` and `revision`. Comparing the stored shapes
    would call every draft different from every revision, and comparing them
    with the numbers stripped would call a draft equal to a revision it is not
    actually a copy of. So the draft is turned into the candidate it would
    publish AS, and both sides are canonicalised by the contract that owns
    them.

    A workflow with nothing published yet answers False: its first revision
    always says something new, even when the drawing is empty.

    Args:
        draft: The stored draft document, or None when there is none.
        published: The latest published revision as stored, or None.
        workflow_id: The identity the candidate would carry.
        revision: The number the candidate would carry.

    Returns:
        True only when a publish would write a document identical, field for
        field, to the one already standing at the latest revision.
    """
    if draft is None or published is None:
        return False
    try:
        candidate = publish_candidate(
            draft, workflow_id=workflow_id, revision=revision).as_dict()
    except DraftRefused:
        # A draft that will not construct is not "unchanged"; it is refused,
        # and the diagnostics say so. Answering True here would hide a broken
        # draft behind a reassuring word.
        return False
    standing = dict(published)
    candidate.pop("revision", None)
    standing.pop("revision", None)
    return canonical_json(candidate) == canonical_json(standing)


def draft_diagnostics(
        document: Mapping[str, Any], *, workflow_id: str,
        revision: int) -> tuple[dict[str, Any], ...]:
    """What stops this draft from being a revision; empty when nothing does.

    The same call as :func:`publish_candidate`, with the refusal swallowed.
    Asking the question twice through two code paths is how a screen comes to
    say ``publishable`` about a document the publish route then refuses.
    """
    try:
        publish_candidate(document, workflow_id=workflow_id, revision=revision)
    except DraftRefused as refused:
        return refused.diagnostics
    return ()


@dataclass(frozen=True)
class WorkflowDraft:
    """One stored draft: whose it is, when it was saved, and what it says."""

    workflow_id: str
    saved_at: str
    document: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "workflow_id", _id("workflow_id", self.workflow_id))
        object.__setattr__(
            self, "saved_at", _timestamp("saved_at", self.saved_at))
        settled = parse_document(self.document)
        object.__setattr__(self, "document", _freeze_json(settled))
        # The snapshot-and-witness this package uses everywhere a contract must
        # answer for what it settled rather than for what it currently holds.
        object.__setattr__(self, "_document_text", canonical_json(settled))
        object.__setattr__(self, "_document_witness", self.document)

    def settled(self) -> dict[str, Any]:
        """The document this contract admitted, rebuilt from its own record.

        Caught by IDENTITY first, which reads nothing: a mapping put here after
        validation would otherwise answer ``items`` however it liked and this
        contract would have reported the answer as the draft.
        """
        if self.document is not self._document_witness:
            raise WorkflowDraftError(
                f"draft {self.workflow_id!r} had its document replaced after it "
                "was validated; this contract answers only for what it settled"
            ) from None
        return json.loads(self._document_text)

    def as_dict(self) -> dict[str, Any]:
        """The stored envelope: self-describing, so a file can be judged alone."""
        return {
            "schema_version": DRAFT_SCHEMA_VERSION,
            "workflow_id": self.workflow_id,
            "saved_at": self.saved_at,
            "document": self.settled(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "WorkflowDraft":
        data = dict(_json_object("workflow draft", value))
        if set(data) != ENVELOPE_FIELDS:
            raise WorkflowDraftError(
                f"a stored workflow draft carries exactly {sorted(ENVELOPE_FIELDS)!r}")
        version = _exact("draft schema_version", data["schema_version"], int)
        if version != DRAFT_SCHEMA_VERSION:
            raise WorkflowDraftError(
                f"this build speaks draft schema_version {DRAFT_SCHEMA_VERSION} "
                f"and this file claims {version}")
        return cls(workflow_id=data["workflow_id"], saved_at=data["saved_at"],
                   document=data["document"])


# -- what a screen is shown about a workflow -------------------------------
#
# These read a `TemplateStore` and compute; they store nothing and they are the
# only place the draft, the revisions and the diagnostics are joined. They live
# beside the draft contract rather than on the HTTP boundary because the join is
# the draft's own question -- "what would this become, and what stops it" -- and
# because two routes answer with it and must answer identically.


def starters() -> list[dict[str, Any]]:
    """The workflow documents this BUILD ships, as starting points.

    Read through ``load_template``, the one door this product already uses for a
    bundled file, and enumerated from the directory the wheel actually carries
    rather than from a list written down beside it -- so a bundled revision
    added or removed moves this answer by itself.

    A starter is not a revision of anybody's workflow. It carries the bundled
    ``template_id`` and ``revision`` because that is what the shipped document
    says; a client saves it as a DRAFT under a workflow id its user chooses, and
    publishing that draft creates revision 1 of THAT workflow. Nothing here
    writes, and no route makes the bundled ids reachable as a workflow to
    publish into: they live inside the installed package and a project's store
    is rooted at its own ``conductor/templates``.

    The whole document travels rather than a name to fetch it by. The bundled
    set is code-owned -- an operator cannot add to it -- and is two files of
    about 3 KB each, so a second round trip per starter would buy nothing and a
    conditional payload shape would cost every client a second code path.
    """
    rows = []
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        template = load_template(path.stem)
        rows.append({"starter_id": path.stem, "title": template.title,
                     "revision": template.revision,
                     "caveats": starter_caveats(template),
                     "document": template.as_dict()})
    return rows


def starter_caveats(template) -> list[str]:
    """What somebody should know before starting from this document.

    Both shipped starters are titled `Dalio five-step cycle` and differ in one
    revision number and four arguments, so a picker showing titles offered two
    rows nobody could tell apart -- and they are not equivalent choices. In
    `dalio-v1` no review step names a `result_artifact_ref`, and
    `artifact_transport._review` refuses exactly that: "this review names no
    result artifact, so nothing it produced could be published; no task was
    spawned". Four of its steps cannot succeed.

    DERIVED, never written down beside the files. A sentence typed here would
    be a second description of a document, free to go stale the moment somebody
    edits the JSON; this reads the same relation the runtime enforces, so a
    starter that gains its missing argument loses its caveat by itself. It is
    also why nothing in the shipped documents moved: their bytes are untouched
    and both revision digests are exactly what they were.
    """
    from .artifacts import REVIEW_CAPABILITY

    unpublishable = sorted(
        node.node_id for node in template.nodes
        if node.capability == REVIEW_CAPABILITY
        and not node.payload().get("result_artifact_ref"))
    if not unpublishable:
        return []
    return [f"{len(unpublishable)} review step(s) name no result artifact, so "
            f"each of them fails without spawning anything: "
            f"{', '.join(unpublishable)}. A later starter may fix this."]


#: The one warning this build emits, word for word. "MAY", not "will": whether
#: a step is reached on every pass depends on the conditions its roads carry,
#: and a branch can end a run before the bounded step is asked for again. A
#: stronger claim is only true where the step lies on EVERY path from the loop's
#: `back_to` to the loop and no edge on any of them carries a condition --
#: recorded here so a later build can add the strong form without re-deriving
#: it, and deliberately not emitted by this one.
BOUND_WARNING = "Attempt bound may be exhausted before the loop's final pass."


def publish_warnings(
        document: Mapping[str, Any], *, workflow_id: str,
        revision: int) -> list[str]:
    """What a person should know about a candidate that is nonetheless publishable.

    A warning is NOT a diagnostic and must never become one. `DIAGNOSTIC_CODES`
    stays what it was, `publishable` does not consult this, and nothing here can
    refuse a publish -- because what it describes is not an error. The document
    is legal, the run it produces may simply be unable to finish, and that is a
    judgement for whoever drew it.

    The interaction it names is real and is invisible from either field alone.
    `attempt_bound` is spent per step across the WHOLE run -- every
    `action_request` naming that step, never reset per lap -- while a loop asks
    the step to settle once per lap. So an effecting step with a bound below its
    loop's bound can settle fewer times than the loop needs, and the last lap
    can never complete: the run stalls. Neither number is wrong on its own,
    which is why nothing refuses them.

    DERIVED, never written beside the files, for `starter_caveats`' reason one
    function over: a sentence typed next to a document is a second description
    free to go stale the moment somebody edits the JSON.
    """
    from .graph_definition import EFFECTING_CAPABILITIES
    from .graph_schedule import loop_body

    try:
        candidate = publish_candidate(
            document, workflow_id=workflow_id, revision=revision)
    except DraftRefused:
        # A document that does not construct has no bodies to walk. Its
        # diagnostics are the answer, and a warning beside them would be
        # advice about a revision that cannot exist.
        return []
    nodes, edges = candidate.settled()
    bounded = {node.node_id: node for node in nodes
               if node.capability in EFFECTING_CAPABILITIES
               and node.attempt_bound is not None}
    for loop in nodes:
        if loop.loop is None:
            continue
        for node_id in loop_body(nodes, edges, loop):
            node = bounded.get(node_id)
            if node is not None and node.attempt_bound < loop.loop.bound:
                return [BOUND_WARNING]
    return []


def _latest_published(templates, workflow_id: str, latest: int | None):
    """The latest revision as stored, and the numbers that would not read.

    ContractError, not TemplateError. The store raises the narrow one for bytes
    it cannot open, but the CONTRACT raises the base class for a document that
    opens and is not a template -- a missing `template_id`, an array where an
    object belongs. Catching only the narrow one let that escape as
    `contract_invalid`, which blames the caller for a well-formed request and
    makes one damaged file answer for the whole workflow.
    """
    if latest is None:
        return None, []
    try:
        return templates.load(workflow_id, latest).as_dict(), []
    except ContractError:
        return None, [latest]


def _draft_row(draft) -> dict[str, Any] | None:
    """One stored draft as a screen reads it: what it says, when, and which one.

    The digest travels WITH the document so a client can echo back which draft
    it reviewed without hashing anything itself; `publish_revision` refuses when
    that echo does not match the draft it is about to write.
    """
    if draft is None:
        return None
    document = draft.settled()
    return {"document": document, "saved_at": draft.saved_at,
            "digest": draft_digest(document)}


def _warnings_for(draft, workflow_id: str, revision: int) -> list[str]:
    """Beside the diagnostics and nothing like them.

    A diagnostic stops a publish and a warning never does. `publishable` does
    not read this, and a workflow with no draft has no candidate to warn about.
    """
    if draft is None:
        return []
    return publish_warnings(
        draft.settled(), workflow_id=workflow_id, revision=revision)


def workflow_state(
        templates: "TemplateStore", workflow_id: str) -> dict[str, Any]:
    """Everything the Studio needs about one workflow, published and unsaved.

    A workflow nothing is stored for is not a refusal: it is the state every
    workflow starts in, and answering it as one is what lets a client open a
    name its user just invented and begin drawing.

    ``published`` is the latest revision as stored. A revision this build cannot
    read through the contract is NOT silently dropped -- its number appears in
    ``unreadable_revisions``, because a revision you cannot read is a fact and a
    revision you cannot see is a lie.
    """
    revisions = templates.revisions(workflow_id)
    latest = revisions[-1] if revisions else None
    published, unreadable = _latest_published(templates, workflow_id, latest)
    next_revision = 1 if latest is None else latest + 1
    draft = templates.load_draft(workflow_id)
    diagnostics = () if draft is None else draft_diagnostics(
        draft.settled(), workflow_id=workflow_id, revision=next_revision)
    unchanged = unchanged_from_published(
        None if draft is None else draft.settled(), published,
        workflow_id=workflow_id, revision=next_revision)
    return {
        "workflow_id": workflow_id,
        "revisions": list(revisions),
        "latest_revision": latest,
        "unreadable_revisions": unreadable,
        "published": published,
        # The digest travels WITH the document a screen is about to show, so a
        # client can echo back which draft it reviewed without hashing anything
        # itself. `publish_revision` refuses when the echo does not match the
        # draft it is about to publish -- which is the whole of the fix for a
        # review that confirmed one document and wrote another.
        "draft": _draft_row(draft),
        "diagnostics": [dict(row) for row in diagnostics],
        "warnings": _warnings_for(draft, workflow_id, next_revision),
        # True only when there IS a draft and nothing stops it. A workflow with
        # no draft has nothing to publish, which is a different thing from a
        # draft that would be refused, and the two must not share a word.
        # True only when there IS a draft, nothing stops it, AND it would say
        # something the standing revision does not. Publishing a draft nobody
        # has changed used to create a second revision carrying the same
        # document under a new number -- a durable record of an edit that never
        # happened, and one no reader could tell from a real one afterwards.
        "publishable": (draft is not None and not diagnostics
                        and not unchanged),
        "unchanged": unchanged,
        "next_revision": next_revision,
    }


def workflow_rows(templates: "TemplateStore") -> list[dict[str, Any]]:
    """One row per workflow this store holds, cheapest first.

    The draft is not opened here: whether a workflow HAS one is a fact about the
    directory, and reading every draft in the project to render a list would
    make one unreadable file refuse the whole list.
    """
    rows = []
    for workflow_id in templates.workflows():
        revisions = templates.revisions(workflow_id)
        latest = revisions[-1] if revisions else None
        title, unreadable = None, False
        if latest is not None:
            try:
                title = templates.load(workflow_id, latest).title
            except ContractError:
                # See `workflow_state`: the base class, or one damaged revision
                # file hides every workflow in the project behind a 422.
                unreadable = True
        rows.append({
            "workflow_id": workflow_id,
            "title": title,
            "latest_revision": latest,
            "revisions": list(revisions),
            "has_draft": templates.has_draft(workflow_id),
            "unreadable": unreadable,
        })
    return rows


def saved_draft(
        templates: "TemplateStore", workflow_id: str,
        document: Mapping[str, Any], clock) -> bool:
    """Store one draft, keeping the moment it was saved when nothing changed.

    Idempotence here is about the DOCUMENT and not about the file: a client
    whose reply was lost re-sends the same drawing, and stamping it with a new
    clock would rewrite the file, move the timestamp a screen is showing, and
    make an identical request a change. So the stored draft is read first, its
    ``saved_at`` is reused when the document is the same one, and the store then
    finds bytes it already holds and writes nothing at all.

    Read and write are one transaction. The read decides what the write will
    say, so two clients saving at once could otherwise both read the same
    standing draft and the later write would carry a `saved_at` chosen for the
    document the earlier one replaced.

    Returns:
        True when this call is what first gave the workflow a draft.
    """
    with templates.transaction(workflow_id):
        standing = templates.load_draft(workflow_id)
        saved_at = (standing.saved_at
                    if standing is not None and standing.settled() == document
                    else clock())
        return templates.save_draft(WorkflowDraft(
            workflow_id=workflow_id, saved_at=saved_at, document=document)).created
