"""What a Studio client may say: one publish request, and one new run.

Split out of ``api_contracts`` when that module reached its line cap, along the
seam the two already had. Everything here validates a body the STUDIO sends and
settles it into a value; the module next door holds the refusal vocabulary, the
transport translation and the contracts every other route speaks. Nothing here
touches a store, a clock, a registry or a path.

The shape of :class:`RunInput` is the whole authority argument of this surface,
so it is worth saying plainly. A browser names an instance, a configured
provider, and at most a model. There is nowhere in that vocabulary for an
adapter binding of the caller's own, a filesystem path, an argv, an environment
value or a credential -- not because those are screened out afterwards, but
because the words do not exist. The frozen configuration a run replays against
is assembled by the server from the three facts above and from nothing else.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .api_contracts import ApiRefusal, _closed, _contract, _json_array, parse_document
from .contracts import ControlMode, RunEnvelope, _id
from .graph_template import RunBinding
from .run_store import snapshot_digest

#: What a publish asks for: the revision it expects to create, and OPTIONALLY
#: the document to create it from. Omitting the document means "publish the
#: draft you are holding" -- one durable source, read once by the route, and
#: never a second body that could disagree with the draft the screen showed.
_REVISION_REQUIRED = frozenset({"revision"})
_REVISION_FIELDS = _REVISION_REQUIRED | {"document"}
#: What a run-creation request supplies. Every key is REQUIRED and the two that
#: may be empty are spelled `null`, because a browser that omits a key and a
#: browser that says "no workflow" must not be the same request.
_RUN_FIELDS = frozenset({
    "run_id", "cycle_id", "mode", "participants", "workflow_id", "revision",
    "assignments"})
#: One participant: who they are in this run, which configured provider carries
#: them, and which model if this build pins one.
_PARTICIPANT_FIELDS = frozenset({"instance_id", "provider_id", "model"})
#: The closed authority ladder, read OFF the contract's own enum so a mode this
#: API accepts is a mode the run envelope can hold.
CONTROL_MODES = frozenset(mode.value for mode in ControlMode)
#: A run binds at most this many participants. `graph_template.MAX_ROLES` bounds
#: the other side of the same join, and a run with more instances than a
#: template can have roles is a request nothing could materialize.
MAX_RUN_PARTICIPANTS = 64


@dataclass(frozen=True)
class RevisionInput:
    """One publish request: the revision asked for, and what to build it from.

    ``document`` is ``None`` when the caller named none, which is the request to
    publish the workflow's stored draft. It is deliberately not defaulted to the
    draft here: reading a durable source is the route's business, and it must be
    read exactly once so that what is judged is what is written.
    """

    revision: int
    document: Mapping[str, Any] | None


@dataclass(frozen=True)
class Participant:
    """One instance a run binds, and the configured provider that carries it."""

    instance_id: str
    provider_id: str
    model: str | None


@dataclass(frozen=True)
class RunInput:
    """One validated request to open a run; time and ids are the server's.

    What is NOT settled here is whether those providers exist, whether this
    build can reach them, whether the revision is stored, or whether the bound
    adapters can serve the plan. Those are facts about a build and a machine and
    only a run about to be WRITTEN is worth asking them for.
    """

    run_id: str
    cycle_id: str
    mode: str
    participants: tuple[Participant, ...]
    workflow_id: str | None
    revision: int | None
    binding: RunBinding

    def snapshot(self) -> dict[str, Any]:
        """The frozen configuration THIS SERVER writes for those participants.

        The instances are sorted by id so two requests that name the same
        participants in different orders produce the same bytes, and therefore
        the same digest and the same idempotent answer.

        ``workflow`` is where this run records WHICH plan it followed, and it is
        in the frozen configuration rather than beside it for three reasons that
        are really one: the snapshot is the document `config_digest` is taken
        over. Being inside it means the identity is re-verified on every replay
        (`RunStore.read` re-digests the config and refuses a mismatch), that a
        second open naming a different revision is a `RecordConflict` rather
        than a silent adoption (`_repeats_the_standing_run` compares the whole
        config), and that no later edit can reach it -- a published revision 3
        cannot change what a run that started on revision 1 is following,
        because nothing rewrites a frozen config and the digest would refuse it
        if anything tried.

        It is OMITTED, never null, when this run follows no workflow. A run
        opened without one freezes exactly the bytes it always did, so no
        existing digest moves and no stored run has to be migrated.
        """
        instances = []
        for row in sorted(self.participants, key=lambda value: value.instance_id):
            entry = {"id": row.instance_id, "adapter": row.provider_id}
            # Omitted rather than null: `frozen_config_models` reads absence as
            # "this build pinned none" and refuses an explicit null, because a
            # configuration that chose a value chose one that is not a model id.
            if row.model is not None:
                entry["model"] = row.model
            instances.append(entry)
        snapshot: dict[str, Any] = {
            "cycle": {"id": self.cycle_id}, "instances": instances}
        if self.workflow_id is not None:
            snapshot["workflow"] = {"id": self.workflow_id,
                                    "revision": self.revision}
        return snapshot

    def build(self, snapshot: Mapping[str, Any], created_at: str) -> RunEnvelope:
        """One envelope over a snapshot the caller already has in hand.

        The snapshot is passed IN rather than rebuilt here, so the digest this
        envelope carries is of the bytes that are about to be written and not of
        a second construction that could differ from them.
        """
        return RunEnvelope(
            run_id=self.run_id, cycle_id=self.cycle_id, created_at=created_at,
            config_digest=snapshot_digest(snapshot), mode=self.mode)


def _exact_revision(value: object) -> int:
    """A revision is an ``int``; a numeral that looks like one is not one."""
    if type(value) is not int or isinstance(value, bool) or value < 1:
        raise ApiRefusal.fixed("contract_invalid")
    return value


def parse_workflow_revision(body: object) -> RevisionInput:
    """Validate a publish: the expected revision, and an optional document.

    The expected number is what stops two editors from silently overwriting each
    other's intent. It is not a hint: the route compares it against what the
    store already holds, and the store's own exclusive create arbitrates the
    race that remains.
    """
    if not isinstance(body, Mapping) or any(not isinstance(key, str) for key in body):
        raise ApiRefusal.fixed("contract_invalid")
    supplied = set(body)
    if not _REVISION_REQUIRED <= supplied <= _REVISION_FIELDS:
        raise ApiRefusal.fixed("contract_invalid")
    document = None
    if "document" in supplied:
        document = _contract(parse_document, body["document"])
    return RevisionInput(
        revision=_exact_revision(body["revision"]), document=document)


def _participant(row: object) -> Participant:
    values = _closed(row, _PARTICIPANT_FIELDS)
    model = values["model"]
    if model is not None:
        model = _contract(_id, "model", model)
    return Participant(
        instance_id=_contract(_id, "instance_id", values["instance_id"]),
        provider_id=_contract(_id, "provider_id", values["provider_id"]),
        model=model)


def parse_run(body: object) -> RunInput:
    """Validate exactly the seven caller-owned facts of one new run.

    ``mode`` comes from the closed :data:`CONTROL_MODES` vocabulary, so there is
    no spelling of authority a browser can reach that the durable envelope
    cannot hold. ``workflow_id`` and ``revision`` are both present or both
    ``null``: half of a reference names a workflow with no revision or a
    revision of nothing, and either would be a request nothing could serve.
    """
    values = _closed(body, _RUN_FIELDS)
    mode = values["mode"]
    if not isinstance(mode, str) or mode not in CONTROL_MODES:
        raise ApiRefusal.fixed("contract_invalid")
    rows = _json_array(values, "participants")
    if not rows or len(rows) > MAX_RUN_PARTICIPANTS:
        raise ApiRefusal.fixed("contract_invalid")
    participants = tuple(_participant(row) for row in rows)
    if len({row.instance_id for row in participants}) != len(participants):
        raise ApiRefusal.fixed("contract_invalid")
    workflow_id, revision = values["workflow_id"], values["revision"]
    if (workflow_id is None) != (revision is None):
        raise ApiRefusal.fixed("contract_invalid")
    if workflow_id is not None:
        workflow_id = _contract(_id, "template_id", workflow_id)
        revision = _exact_revision(revision)
    binding = _contract(RunBinding.from_dict, {"assignments": values["assignments"]})
    # Assignments answer for a workflow's roles. Without one there are no roles,
    # so a non-empty mapping is a binding for a template that was never named.
    if workflow_id is None and binding.bound():
        raise ApiRefusal.fixed("contract_invalid")
    return RunInput(
        run_id=_contract(_id, "run_id", values["run_id"]),
        cycle_id=_contract(_id, "cycle_id", values["cycle_id"]),
        mode=mode, participants=participants, workflow_id=workflow_id,
        revision=revision, binding=binding)
