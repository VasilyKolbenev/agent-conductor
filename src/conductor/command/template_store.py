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
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import MappingProxyType

from .containment import (
    RouteViolation,
    RouteViolationCode,
    first_directory_violation,
    portal_violation,
    _optional_lstat,
)
from .contracts import ContractError, _id, canonical_json
from .graph_template import GraphTemplate, TemplateError
from .run_store import _canonical_bytes, _exclusive_bytes, _fsync_dir
from .store_errors import RecordConflict, StoreError

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


class RouteNotOwned(StoreError):
    """The route to a revision reaches state this store cannot account for."""


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
            raise RouteNotOwned(_ROUTE_REFUSAL[violation.code])

    def save(self, template: GraphTemplate) -> Path:
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
            return path
        except OSError as error:
            raise StoreError(
                f"cannot publish template {template.template_id!r} "
                f"revision {template.revision}: {error.strerror}") from None
        _fsync_dir(path.parent)
        return path

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
                if entry.suffix == ".json" and entry.stem.isdigit():
                    found.append(int(entry.stem))
        except OSError:
            return ()
        return tuple(sorted(found))
