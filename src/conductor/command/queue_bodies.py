"""The closed bodies of the queue routes (spec 4.4.5).

`POST /command/queue` carries a `run_id` and exactly one of `start` (the body of an authorize) or
`resume` (the body of a control, without its action). Every field is closed: a body that names
anything else, and above all a `root`, a `path` or a `dir`, is refused `contract_invalid` before
the queue is asked a thing, and `{}` is refused too. The body is judged against ITSELF here (the
digest it names is the digest of the terms it carries) so that the checks of the service, which
need the run, the clock and the owner, only ever see a well-formed ask.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .authorization_terms import closed_fields
from .contract_values import ContractError, _id
from .flag_control_id import refuse_flag_control_id
from .path_admission import admit_name
from .policy_preview import PREVIEW_FIELDS
from .policy_service import AUTHORIZE_FIELDS, CONTROL_FIELDS, PolicyService
from .queue_store import ResumePreauth, StartPreauth

#: The body of a `resume`: a control's body without the action, which the queue always means.
RESUME_FIELDS = frozenset(CONTROL_FIELDS - {"action"})
_WRITE_KEYS = ("start", "resume")
_ORDER_FIELDS = frozenset({"expected_revision", "run_ids"})


@dataclass(frozen=True)
class Ask:
    """One `POST /command/queue`, judged for shape: the run, the kind, the permission, the body.

    `body` is the authorize body (for a start) or the control body (for a resume) exactly as it
    was sent: the service needs it to ask the preview cache and to build the candidate grant.
    """

    run_id: str
    kind: str
    preauth: StartPreauth | ResumePreauth
    body: dict[str, Any]


def parse_write(body: object, now: str) -> Ask:
    """A closed `QueueWrite`, or `ContractError` (and `WindowsNameError` for a record id that
    names a device): nothing is read, written or started here.

    Args:
        body: The decoded JSON object of the request.
        now: The server clock; it is the moment of the preauthorization.
    """
    if type(body) is not dict or "run_id" not in body:
        raise ContractError("a queue write names a run and one of start or resume")
    kinds = [key for key in _WRITE_KEYS if key in body]
    if len(kinds) != 1 or set(body) != {"run_id", kinds[0]}:
        raise ContractError("a queue write carries exactly a run_id and one of start or resume")
    run_id, kind = _id("run_id", body["run_id"]), kinds[0]
    if kind == "start":
        fields = closed_fields(body["start"], AUTHORIZE_FIELDS, "queue start")
        return Ask(run_id, kind, _start(fields, now), fields)
    fields = closed_fields(body["resume"], RESUME_FIELDS, "queue resume")
    control_id = _id("control_id", fields["control_id"])
    admit_name(control_id, "control_id")
    refuse_flag_control_id(control_id)      # the name of the flag's own resume (spec 4.3.4)
    preauth = ResumePreauth(fields["control_id"], fields["authorization_id"],
                            fields["authorization_digest"], fields["expected_control_id"],
                            fields["actor"], now)
    return Ask(run_id, kind, preauth, fields)


def _start(fields: dict[str, Any], now: str) -> StartPreauth:
    PolicyService._hold_to_its_own_terms(fields)
    terms = fields["terms"]
    admit_name(_id("authorization_id", fields["authorization_id"]), "authorization_id")
    if "source_prefix_digest" not in terms:
        raise ContractError("the terms name no source prefix")
    return StartPreauth(fields["authorization_id"], fields["preview_digest"],
                        terms["source_prefix_digest"], {key: terms.get(key) for key in
                                                        PREVIEW_FIELDS},
                        fields["supersedes"], fields["authorized_by"], now)


def parse_order(body: object) -> tuple[int, tuple[str, ...]]:
    """`{"expected_revision": int, "run_ids": [...]}`: a revision and a list of distinct ids."""
    data = closed_fields(body, _ORDER_FIELDS, "queue order")
    revision, run_ids = data["expected_revision"], data["run_ids"]
    if type(revision) is not int or revision < 0:
        raise ContractError("expected_revision must be a non-negative integer")
    if type(run_ids) is not list:
        raise ContractError("run_ids must be a list")
    ids = tuple(_id("run_id", run_id) for run_id in run_ids)
    if len(set(ids)) != len(ids):
        raise ContractError("run_ids must not repeat a run")
    return revision, ids


def parse_withdraw(body: object) -> None:
    """A withdraw takes the empty object and nothing else."""
    if type(body) is not dict or body:
        raise ContractError("a withdraw carries no fields")
