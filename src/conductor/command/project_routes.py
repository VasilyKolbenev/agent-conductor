"""The routes of a project's documents and of a run's materials (spec 6.2, 9.1.6, 9.5).

Three handlers, each answering with what the door needs and knowing nothing of how a response is
shaped on the wire (the boundary owns that, as for every other route module):

- `read_documents` and `read_document` answer `GET /command/project/documents` and
  `.../documents/<doc_id>` from HEAD through the reader of the project's git;
- `materials_document` turns the body of `POST /command/runs/<run_id>/materials` into the one
  document `artifact-materials`, which the boundary then appends through the door the artifacts
  route uses, so the write, the refusal of an ended run and the exact retry are that door's.

Git is only ever asked through `api._project_git`, and never in `view` (spec 9.1.6): a server that
was started to view the project creates no child process, so a route that needs git refuses
`project_not_active` before the reader is touched. What needs git is a document list, a document
text, a copy of a project document (its path comes from HEAD) and a link judged against the
seed's base tree. What does not is a plan, an idea, a scheme or a note, and a link when the task
has no seed with a base at all (`seed_missing`, decided from the record on disk).

A link is judged against what the seed really copied: a document the base tree holds but the
seed left out is `doc_not_seeded`, said here before the composer can call the same path
`doc_unknown`, because only the seed's own record knows why a file is missing. A copy is the
owner's text and is judged against nothing of the seed.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeVar

from . import project_documents
from .api_contracts import ApiRefusal, ArtifactInput
from .materials import MAX_MATERIALS, PROJECT_DOC, BaseFile, MaterialsRefused, compose_materials
from .plan_admission import _task
from .project_git import GitReadFailed
from .seed_record import read_seed

if TYPE_CHECKING:  # pragma: no cover - the boundary this module is called by, never built here
    from .http_api import CommandApi

ARTIFACT_REF = "artifact-materials"
MEDIA_TYPE = "text/markdown"
_BODY_KEYS = frozenset({"lang", "items"})
_Reply = tuple[int, dict[str, Any]]
_T = TypeVar("_T")


def read_documents(api: CommandApi) -> _Reply:
    """`GET /command/project/documents`: the tracked documents of HEAD, at most 500.

    A server that has no git reader (a demo, an embedder) offers no documents and says so the
    way a project with no commit does: no base and an empty list.

    Raises:
        ApiRefusal: `project_not_active` in `view`; `store_error` when git itself failed.
    """
    return 200, _listing(api).as_dict()


def read_document(api: CommandApi, doc_id: str) -> _Reply:
    """`GET /command/project/documents/<doc_id>`: `{doc_id, path, git_oid, content}` of HEAD.

    Raises:
        ApiRefusal: `project_not_active` in `view`; `materials_refused` with `doc_unknown` for an
            id HEAD does not list and `document_not_text` for a blob that is not UTF-8 text;
            `store_error` when git itself failed.
    """
    _hold_git_allowed(api)
    if api._project_git is None:
        raise ApiRefusal.materials_refused("doc_unknown")
    try:
        return 200, _git_read(lambda: project_documents.read_document(
            api._store.project_root, api._project_git, doc_id))
    except project_documents.DocumentRefused as refused:
        raise ApiRefusal.materials_refused(refused.reason) from None


def materials_document(api: CommandApi, run_id: str, body: object) -> ArtifactInput:
    """The document `artifact-materials` a materials body makes for this run.

    Args:
        api: The boundary, for the store, the identity and the git reader.
        run_id: The run the materials are for.
        body: `{"lang": "ru"|"en", "items": [...]}`, closed to exactly those two keys.

    Returns:
        The document, its id derived from the run and the composed bytes, so a request repeated
        after a lost answer finds the document already standing.

    Raises:
        ApiRefusal: `contract_invalid` for a body of other keys; `materials_refused` with a reason
            of `MATERIALS_REASONS`; `project_not_active` in `view` when the items need git;
            `store_error` when git itself failed.
        ContractError: An item or the language is not in the closed shape.
    """
    lang, items = _parse(body)
    api._hold_route(run_id)
    config = api._store.read(run_id).config
    base, documents = _sources(api, config, items)
    try:
        content = compose_materials(items, lang, base, documents)
    except MaterialsRefused as refused:
        raise ApiRefusal.materials_refused(refused.reason) from None
    return ArtifactInput(document_id(run_id, ARTIFACT_REF, MEDIA_TYPE, content),
                         ARTIFACT_REF, MEDIA_TYPE, content)


def document_id(run_id: str, ref: str, media_type: str, content: str) -> str:
    """`doc-` and 32 hex of the SHA-256 of the four facts joined by NUL (spec 6.4.1)."""
    joined = "\0".join((run_id, ref, media_type, content))
    return "doc-" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def _parse(body: object) -> tuple[Any, Any]:
    if not isinstance(body, Mapping) or set(body) != _BODY_KEYS:
        raise ApiRefusal.fixed("contract_invalid")
    return body["lang"], body["items"]


def _hold_git_allowed(api: CommandApi) -> None:
    """A server started to view the project asks git nothing (spec 9.1.6)."""
    if api._identity.mode == "view":
        raise ApiRefusal.fixed("project_not_active")


def _git_read(call: Callable[[], _T]) -> _T:
    try:
        return call()
    except GitReadFailed:
        raise ApiRefusal.fixed("store_error") from None


def _listing(api: CommandApi) -> project_documents.Listing:
    _hold_git_allowed(api)
    if api._project_git is None:
        return project_documents.EMPTY
    return _git_read(lambda: project_documents.list_documents(
        api._store.project_root, api._project_git))


def _asked(items: object) -> tuple[list[str], list[str]]:
    """The ids of the links and of the copies the items ask for, from the items well formed
    enough to be asked; anything else is left for the composer to refuse."""
    links: list[str] = []
    copies: list[str] = []
    for item in items if isinstance(items, (list, tuple)) else ():
        if not (isinstance(item, Mapping) and item.get("kind") == PROJECT_DOC
                and isinstance(item.get("doc_id"), str)):
            continue
        if item.get("mode") == "link":
            links.append(item["doc_id"])
        elif item.get("mode") == "copy":
            copies.append(item["doc_id"])
    return links, copies


def _sources(api: CommandApi, config: Mapping[str, Any],
             items: object) -> tuple[dict[str, BaseFile] | None, dict[str, str]]:
    """What the composer judges the items against: the seed's base and HEAD's documents.

    Git is asked only when an item needs it, and not at all for a list the composer will refuse
    for its length.
    """
    links, copies = _asked(items)
    if not (links or copies) or len(items) > MAX_MATERIALS:  # type: ignore[arg-type]
        return None, {}
    documents = {row.doc_id: row.path for row in _listing(api).documents} if copies else {}
    return (_seeded_base(api, config, links) if links else None), documents


def _seeded_base(api: CommandApi, config: Mapping[str, Any],
                 links: Sequence[str]) -> dict[str, BaseFile] | None:
    """The documents of the task's base tree, by document id, or None when it has no base.

    A link to one the seed left out is refused here, so the composer only ever sees a link to a
    file the seed copied, and says `doc_unknown` for what the base tree never held.

    Raises:
        ApiRefusal: `materials_refused` with `doc_not_seeded` for a link to a document the base
            tree holds and the seed left out; `project_not_active` in `view`.
    """
    binding = _task(config)
    seed = None if binding is None else read_seed(api._store.project_root, binding.task_id)
    if seed is None or seed.base_tree is None:
        return None
    _hold_git_allowed(api)
    if api._project_git is None:
        raise ApiRefusal.fixed("store_error")
    held = _git_read(lambda: project_documents.base_documents(
        api._store.project_root, api._project_git, seed.base_tree))
    left_out = seed.not_copied()
    if any(doc_id in held and held[doc_id].path in left_out for doc_id in links):
        raise ApiRefusal.materials_refused("doc_not_seeded")
    return {doc_id: BaseFile(row.path, row.git_oid) for doc_id, row in held.items()}
