"""Durable storage for reusable plans: one file per template REVISION, forever.

A run's journal is the wrong home for a template, and the reason is what a
template is FOR. `RunStore` is rooted at one run and every record in it belongs
to that run; a template is meant to outlive the run that first used it and to
be materialized again somewhere else. Storing one inside a run would make the
second run's plan depend on the first run's directory still existing.

So templates get their own root, and the shape follows the contract rather than
the other way round. `graph_template` already says that editing a template does
not edit anything a run followed -- a change makes a NEW revision, a different
identity -- so a revision is written EXCLUSIVELY and never rewritten. That is
not a policy this module adds on top; it is the only storage that can keep the
promise the contract already makes, because a revision whose bytes could change
would make every run that materialized from it replay against a plan nobody
can reconstruct.

Writing the same revision twice is therefore two different events wearing one
name, and they get two different answers: identical bytes are an honest retry
and succeed, and different bytes are a `RevisionConflict`. The graph route
already answers a repeated write that way, and a store that answered a retry
with a conflict would punish a client whose reply was lost.

Beside the revisions, one DRAFT: the document a person is still editing. It
lives in the same directory and under the same route gate -- ownership is a
house rule, not a per-file choice -- and it is written the opposite way, by
atomic replace rather than exclusive create, because saving it again is the
whole point of it. The two can never be confused for one another: `revisions`
counts `<digits>.json` and a draft is not a number, and `revision_path` builds
its name from an `int` and so can never land on `draft.json`. Neither rule has
to know about the other.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple

from .containment import (
    RouteViolation,
    RouteViolationCode,
    first_directory_violation,
    portal_violation,
    _optional_lstat,
)
from .contracts import ContractError, _id, canonical_json
from .graph_template import GraphTemplate, TemplateError
from .run_store import (
    _canonical_bytes,
    _exclusive_bytes,
    _fsync_dir,
    _replace_bytes,
)
from .store_errors import RecordConflict, StoreError
from .workflow_draft import WorkflowDraft

#: One fixed sentence per structural reason a route is not this store's to use,
#: and not one of them names a path. `containment` reports typed FACTS exactly
#: so a caller need not parse a rendering -- and its own renderer puts the path
#: in the message, which is this server's directory layout handed to whoever
#: asked for a template. The kind is what a caller can act on; the location is
#: what the operator already knows and an attacker does not.
_ROUTE_REFUSAL = MappingProxyType({
    RouteViolationCode.SYMLINK:
        "a component of the template store is a symbolic link",
    RouteViolationCode.JUNCTION:
        "a component of the template store is a directory junction",
    RouteViolationCode.REPARSE_POINT:
        "a component of the template store is a reparse point",
    RouteViolationCode.HARD_LINK:
        "a stored revision carries more than one name",
    RouteViolationCode.IRREGULAR_FILE:
        "a stored revision is not a regular file",
    RouteViolationCode.NOT_DIRECTORY:
        "a component of the template store is not a directory",
    RouteViolationCode.UNREADABLE:
        "a component of the template store cannot be read",
    RouteViolationCode.MISSING:
        "a component of the template store cannot be read",
})


def _leaf_violation(path: Path) -> RouteViolation | None:
    """Judge one revision file as regular, local, and singly named.

    Absent is admissible: this store may own its creation. Present and anything
    other than a lone regular file is not, and each reason is its own typed
    fact rather than one flat "bad path".
    """
    found, failure = _optional_lstat(path)
    if failure is not None:
        return failure
    if found is None:
        return None
    portal = portal_violation(path, found)
    if portal is not None:
        return portal
    if not stat.S_ISREG(found.st_mode):
        return RouteViolation(RouteViolationCode.IRREGULAR_FILE, path)
    if found.st_nlink != 1:
        return RouteViolation(
            RouteViolationCode.HARD_LINK, path, link_count=found.st_nlink)
    return None


#: The one file name a workflow directory holds that is not a revision. It is
#: spelled here rather than at each use so the two halves of the rule -- what
#: `save_draft` writes at, and what `revisions` refuses to count -- read off one
#: constant and cannot come apart.
DRAFT_NAME = "draft.json"


class Published(NamedTuple):
    """Where a revision stands, and whether THIS call is what put it there.

    The caller cannot work `created` out for itself. Reading the directory
    first and comparing is a race that two identical publishes both win, and
    both would then claim to have created the same file. The exclusive create
    is the one thing that knows, so it is the one thing that says.
    """

    path: Path
    created: bool


class RouteNotOwned(StoreError):
    """The route to a revision reaches state this store cannot account for."""


class DraftSaved(NamedTuple):
    """Where a draft stands, and whether THIS call is what first put one there.

    ``created`` distinguishes the first draft of a workflow from every later
    save of it. A caller cannot work it out: a draft is mutable, so reading the
    directory first and comparing is exactly the race the answer is about.
    """

    path: Path
    created: bool


class RevisionConflict(RecordConflict):
    """A revision was written twice with different facts under one identity."""


class TemplateStore:
    """Single-writer store rooted at one project's `conductor/templates`.

    Reads touch no durable byte and take no lock: a revision that exists is
    final, so there is no half-written state a reader could observe and no
    repair for a reader to race with.
    """

    def __init__(self, project_root: str | os.PathLike[str]) -> None:
        self.project_root = Path(project_root).resolve()
        self.templates_root = self.project_root / "conductor" / "templates"

    def revision_path(self, template_id: str, revision: int) -> Path:
        """Where one revision lives, with both halves of the name validated.

        `template_id` goes through the contract's own id rule rather than a
        path check of this module's invention, so the set of names a store
        accepts is the set the contract accepts -- and a caller cannot reach a
        directory by naming one.
        """
        try:
            safe = _id("template_id", template_id)
        except ContractError as error:
            raise StoreError(str(error)) from None
        if type(revision) is not int or revision < 1:
            raise StoreError("a template revision starts at 1 and only goes up")
        return self.templates_root / safe / f"{revision}.json"

    def draft_path(self, template_id: str) -> Path:
        """Where one workflow's single editable document lives.

        Beside its revisions, under a name that is not a number. That is not a
        convenience: ``revisions`` counts ``<digits>.json`` and nothing else, so
        a draft cannot be listed as a revision, and ``revision_path`` builds its
        name from an ``int``, so a publish cannot land on the draft. Neither
        half needs to know about the other for the partition to hold.
        """
        return self._workflow_dir(template_id) / DRAFT_NAME

    def _workflow_dir(self, template_id: str) -> Path:
        try:
            safe = _id("template_id", template_id)
        except ContractError as error:
            raise StoreError(str(error)) from None
        return self.templates_root / safe

    @staticmethod
    def _refuse(violation: RouteViolation) -> None:
        raise RouteNotOwned(_ROUTE_REFUSAL[violation.code])

    def _owned(self, path: Path) -> None:
        """Refuse a route that reaches bytes this store cannot account for.

        Every directory this store writes THROUGH is walked, and the leaf it
        writes AT is judged separately, because the two fail differently. A
        portal anywhere on the route means the name is here and the content is
        somewhere else, so a write lands outside the tree the operator pointed
        at. A second hard link on the leaf means the same bytes already stand
        under another name, so publishing at ours changes only one view of
        state nobody accounted for -- which is the failure `os.link` alone
        cannot see, since it arbitrates the NAME and says nothing about how
        many names the bytes behind it already have.

        The check runs on the way IN and on the way OUT. A route that grew a
        portal after a revision was written would otherwise be read back
        happily, and a reader trusting bytes from somewhere else is the same
        defect as a writer sending bytes there.
        """
        violation = first_directory_violation((
            self.project_root / "conductor", self.templates_root, path.parent,
        )) or _leaf_violation(path)
        if violation is not None:
            self._refuse(violation)

    def save(self, template: GraphTemplate) -> Published:
        """Publish one revision, or agree that it is already published.

        Exclusive, because a revision is an identity: `os.link` refuses a name
        that is claimed, so two writers racing for one revision cannot both
        believe they wrote it. What the loser does next depends on WHAT is
        already there -- the same document is the request already satisfied,
        and a different one is two plans wearing one name.
        """
        if type(template) is not GraphTemplate:
            raise StoreError("save takes exactly a GraphTemplate")
        document = template.as_dict()
        path = self.revision_path(template.template_id, template.revision)
        self._owned(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._owned(path)
        try:
            _exclusive_bytes(path, _canonical_bytes(document))
        except FileExistsError:
            self._agrees(path, template, document)
            return Published(path, created=False)
        except OSError as error:
            raise StoreError(
                f"cannot publish template {template.template_id!r} "
                f"revision {template.revision}: {error.strerror}") from None
        _fsync_dir(path.parent)
        return Published(path, created=True)

    def _agrees(self, path: Path, template: GraphTemplate,
                document: dict) -> None:
        """Refuse a second revision that says something else under one name."""
        if canonical_json(self._document(path, template.template_id,
                                         template.revision)) != canonical_json(document):
            raise RevisionConflict(
                f"template {template.template_id!r} revision {template.revision} "
                "already records different facts; an edit is a new revision")

    def load(self, template_id: str, revision: int) -> GraphTemplate:
        """Read one revision back through the contract's own door.

        `from_dict`, exactly as an operator's file goes through, so a stored
        document is held to the contract rather than trusted for having been
        written by us -- and a revision written by an older build that this one
        no longer speaks is refused rather than half-read.
        """
        path = self.revision_path(template_id, revision)
        self._owned(path)
        return GraphTemplate.from_dict(
            self._document(path, template_id, revision))

    @staticmethod
    def _document(path: Path, template_id: str, revision: int) -> dict:
        """One stored revision as data, refused without naming this disk.

        The path is not in the message and the `OSError` is not chained: its
        `str` carries the full name it failed on, which is this server's
        directory layout under any traceback. The two facts the caller already
        supplied are the whole of what the refusal owes them.
        """
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            raise TemplateError(
                f"no stored template {template_id!r} at revision {revision}"
            ) from None
        except json.JSONDecodeError as error:
            raise TemplateError(
                f"stored template {template_id!r} revision {revision} is not "
                f"JSON: {error}") from None

    def revisions(self, template_id: str) -> tuple[int, ...]:
        """Every revision stored for one template, ascending; empty if none.

        Read off the directory rather than a written-down index, for
        `graph_definition`'s reason: an index of oneself can come to disagree
        with oneself, and here the files ARE the record.
        """
        try:
            safe = _id("template_id", template_id)
        except ContractError as error:
            raise StoreError(str(error)) from None
        found = []
        try:
            for entry in (self.templates_root / safe).iterdir():
                # `isdigit` is what keeps `draft.json` out of this answer, and
                # it is DELIBERATE rather than incidental: a draft is the one
                # file beside a workflow's revisions, and a listing that counted
                # it would offer an unfinished document as a published one.
                if entry.suffix == ".json" and entry.stem.isdigit():
                    found.append(int(entry.stem))
        except OSError:
            return ()
        return tuple(sorted(found))

    def workflows(self) -> tuple[str, ...]:
        """Every workflow this store holds a directory for, ascending.

        Read off the directory for `revisions`' reason -- the files ARE the
        record -- and gated on the way out for `_owned`'s reason. A name whose
        content lives somewhere else is refused rather than skipped: a listing
        that quietly omitted it would answer "this workflow does not exist"
        about a name every other call on this store refuses to touch.
        """
        violation = first_directory_violation(
            (self.project_root / "conductor", self.templates_root))
        if violation is not None:
            self._refuse(violation)
        try:
            entries = sorted(self.templates_root.iterdir())
        except FileNotFoundError:
            return ()
        except OSError:
            self._refuse(RouteViolation(
                RouteViolationCode.UNREADABLE, self.templates_root))
        found: list[str] = []
        for entry in entries:
            state, failure = _optional_lstat(entry)
            if failure is not None:
                self._refuse(failure)
            if state is None:
                continue
            portal = portal_violation(entry, state)
            if portal is not None:
                self._refuse(portal)
            if not stat.S_ISDIR(state.st_mode):
                continue
            try:
                found.append(_id("template_id", entry.name))
            except ContractError:
                # A directory whose name is not an id names no workflow this
                # store could ever address, so it is not one.
                continue
        return tuple(found)

    def has_draft(self, template_id: str) -> bool:
        """Whether one workflow holds an editable document, route gate included."""
        path = self.draft_path(template_id)
        self._owned(path)
        return path.exists()

    def save_draft(self, draft: WorkflowDraft) -> DraftSaved:
        """Replace one workflow's editable document, all or nothing.

        An atomic REPLACE, never the exclusive `os.link` a revision gets, and
        the difference is what the two things are. A revision is an identity: it
        is written once and a second write under that name is either the same
        request or two plans wearing one name. A draft is the opposite by
        definition -- saving it again with different words is the whole point --
        so exclusivity would refuse every save after the first.

        What it keeps from the revision road is the staging: the bytes are
        written and fsynced under a private name before `os.replace` publishes
        them, so a crash leaves the previous draft whole rather than a truncated
        one. Identical bytes write nothing at all, so a client whose reply was
        lost does not disturb the file it already saved.
        """
        if type(draft) is not WorkflowDraft:
            raise StoreError("save_draft takes exactly a WorkflowDraft")
        path = self.draft_path(draft.workflow_id)
        self._owned(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._owned(path)
        payload = _canonical_bytes(draft.as_dict())
        try:
            standing = path.read_bytes() if path.exists() else None
            if standing == payload:
                return DraftSaved(path, created=False)
            _replace_bytes(path, payload)
        except OSError as error:
            raise StoreError(
                f"cannot save the draft for workflow {draft.workflow_id!r}: "
                f"{error.strerror}") from None
        _fsync_dir(path.parent)
        return DraftSaved(path, created=standing is None)

    def load_draft(self, template_id: str) -> WorkflowDraft | None:
        """Read one workflow's editable document back, or None if it holds none.

        Through `WorkflowDraft.from_dict`, exactly as `load` goes through
        `GraphTemplate.from_dict`: a file written by an older build that this
        one no longer speaks is refused rather than half-read. A refusal here is
        a STORE fault and says so -- the caller supplied a workflow id and a
        durable file contradicted it, which is not the caller's contract error.
        """
        path = self.draft_path(template_id)
        self._owned(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            raise StoreError(
                f"the draft for workflow {template_id!r} cannot be read") from None
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise StoreError(
                f"the stored draft for workflow {template_id!r} is not JSON: "
                f"{error}") from None
        try:
            draft = WorkflowDraft.from_dict(document)
        except ContractError as error:
            raise StoreError(
                f"the stored draft for workflow {template_id!r} is not a draft "
                f"this build can read: {error}") from None
        if draft.workflow_id != self._workflow_dir(template_id).name:
            raise StoreError(
                f"the draft stored for workflow {template_id!r} answers for "
                f"{draft.workflow_id!r} instead")
        return draft

    def discard_draft(self, template_id: str) -> bool:
        """Remove one workflow's editable document; False if there was none.

        This is the only delete this store has, and it is a delete of the one
        thing that was never durable history. No revision is removable by any
        call here, and none ever will be.
        """
        path = self.draft_path(template_id)
        self._owned(path)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise StoreError(
                f"cannot discard the draft for workflow {template_id!r}: "
                f"{error.strerror}") from None
        _fsync_dir(path.parent)
        return True
