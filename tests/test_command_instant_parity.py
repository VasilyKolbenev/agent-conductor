"""The durable contract answers the shared UTC-instant corpus, on any Python.

Two of the corpus's four bindings live here, in the fast suite, so a divergence
between the store and the Cockpit can never hide behind the separately-run
browser gate: whatever ``instantIsValid`` decides in a browser, these two say
what ``ActionRequest.requested_at`` and ``DecisionReceipt.decided_at`` decide,
and the browser bindings assert the same rows.

The blocker these close (Codex P1): ``_timestamp`` used to delegate its meaning
to ``datetime.fromisoformat``, whose accepted set *changes across the Pythons
this package supports*. ``2026-08-17T24:00:00Z`` is refused on 3.11 and 3.12 and
accepted on 3.14; a space separator, a basic or week date, a comma fraction and
``-00:00`` are accepted by 3.11/3.12 too and refused by the browser. So the same
December Command build held different valid facts on different interpreters, and
the Human Gate held a third set. The grammar is frozen instead, and the accept
path never calls a version-variant parser at all — pinned below, because with a
single interpreter on the machine no test could observe that by running.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from conductor.command import contracts
from conductor.command.contracts import ActionRequest, ContractError, DecisionReceipt

from tests.utc_instant_corpus import CASES, IDS, PARAMS


DIGEST = "sha256:" + "a" * 64
PREVIEW = "sha256:" + "b" * 64
#: The classes Codex named, each of which must stay in the corpus with this
#: verdict. A row may be added freely; silently dropping one of these, or
#: flipping it back, reds here rather than quietly shrinking the guard.
REQUIRED = {
    "end-of-day-24": False,
    "end-of-day-24-second-set": False,
    "space-separator-utc-offset": False,
    "basic-date": False,
    "week-date": False,
    "comma-fraction": False,
    "negative-zero-offset": False,
    "lowercase-t-separator": False,
    "non-utc-offset-ahead": False,
    "month-13": False,
    "day-32": False,
    "feb-29-non-leap": False,
    "hour-25": False,
    "minute-60": False,
    "second-60": False,
    "prose": False,
    "empty": False,
    "trailing-z": True,
    "explicit-utc-offset": True,
    "fraction-six-digits": True,
    "leap-day": True,
    "year-lower-bound": True,
    "year-upper-bound": True,
}


def an_action(requested_at: str) -> dict[str, object]:
    """One otherwise-valid ActionRequest document, varying only its instant."""
    return {
        "schema_version": 2, "action_id": "action-001", "run_id": "run-001",
        "attempt_id": "attempt-001", "instance_id": "claude-dev",
        "capability": "dispatch", "arguments": {"handoff": "packet-001"},
        "scope": ["src"], "requested_by": "owner", "requested_at": requested_at,
        "idempotency_key": "dispatch-proposal-001", "timeout_seconds": 900,
        "preview_digest": PREVIEW, "mode": "confirm",
    }


def a_decision(decided_at: str) -> dict[str, object]:
    """One otherwise-valid DecisionReceipt document, varying only its instant."""
    return {
        "schema_version": 2, "receipt_id": "decision-001", "run_id": "run-001",
        "gate_id": "release", "action": "approve", "actor": "release-owner",
        "decided_at": decided_at, "reason": "Reviewed the attached evidence.",
        "scope_refs": ["release"], "config_digest": DIGEST,
        "evidence_refs": [], "supersedes": None,
    }


@pytest.mark.parametrize("value,accepted", PARAMS, ids=IDS)
def test_the_durable_action_request_answers_the_corpus_for_requested_at(
        value: str, accepted: bool) -> None:
    """Binding one of four: what the store will hold as a request's instant."""
    if accepted:
        assert ActionRequest.from_dict(an_action(value)).requested_at == value
        return
    with pytest.raises(ContractError, match="requested_at"):
        ActionRequest.from_dict(an_action(value))


@pytest.mark.parametrize("value,accepted", PARAMS, ids=IDS)
def test_the_durable_decision_receipt_answers_the_corpus_for_decided_at(
        value: str, accepted: bool) -> None:
    """Binding two of four: what the store will hold as a Human decision's instant."""
    if accepted:
        assert DecisionReceipt.from_dict(a_decision(value)).decided_at == value
        return
    with pytest.raises(ContractError, match="decided_at"):
        DecisionReceipt.from_dict(a_decision(value))


def test_the_corpus_still_carries_every_class_the_parity_blocker_named() -> None:
    """The corpus may grow; it may not quietly lose the cases that closed the P1."""
    verdicts = {case.name: case.accepted for case in CASES}
    assert {name: verdicts.get(name) for name in REQUIRED} == REQUIRED


def test_the_accept_path_never_consults_a_version_variant_parser() -> None:
    """Version independence by construction, which no run on one Python can show.

    Only 3.14 exists on this machine, so a claim about 3.11 and 3.12 cannot be
    made by executing anything here. It is made structurally instead, over the
    parsed function rather than its prose: the accept path calls no parser whose
    accepted set moves between versions, and takes calendar truth from a single
    six-field ``datetime`` construction, whose meaning does not move. Restoring
    such a call reds here as well as in the corpus above.
    """
    body = ast.parse(inspect.getsource(contracts._timestamp))
    called = {node.func.attr for node in ast.walk(body)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not called & {"fromisoformat", "strptime", "fromtimestamp", "isoparse"}
    built = [node for node in ast.walk(body) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "datetime"]
    assert len(built) == 1 and len(built[0].args) == 6 and not built[0].keywords
