"""One pass of the queue pump (spec 4.4.4): start, at most, one admitted entry.

The pump runs in the driver's thread when nothing is active and nothing is in flight, under the
root gate, in steps: the owner; the reconciliation and the clean-up; the first admitted entry whose
terms still hold. It is not a second authorization road: it writes a grant or a control only for an
entry a human confirmed in THIS process (or, for the continue-after flag, in a child that consumed
it), only when the driver's own `hold_activation` says the slot is free (the very check a direct
authorize makes), and only after the preview, asked again, gives the digest the human confirmed.

Three writes start a run, in this order: the receipt, the journal record, then the activation; the
entry is removed last. A crash between any two leaves a state the NEXT pass reconciles before it
builds any preview: the journal is the only source of the fact that a grant or a control was
accepted, so a receipt with no record is replaced on retry, a record with its receipt is recognised
and never written again (and never activated by the pass that finds it: a recorded, unactivated
start waits for an explicit resume), and a receipt that disagrees with the journal blocks its entry.
"""
from __future__ import annotations

import copy
from typing import Any

from .authorization_history import validate_authorization_history
from .contract_values import ContractError
from .policy_preview import build_preview, from_terms
from . import queue_flag
from .queue_reading import Facts, pairing_of, record_digest, resume_refusal
from .queue_store import Dropped, QueueEntry, Receipt
from .run_authorization import RunAuthorizationControl
from .store_errors import StoreError

#: A pass that finds no owner waits this long before it asks again (spec 4.4.4 step 1).
OWNER_RETRY_SECONDS = 5


def run_pass(svc: Any) -> bool:
    """One pass; True when a run was started or resumed, False when nothing was.

    Args:
        svc: The `QueueService` (its policy, store, admission and clock).
    """
    policy = svc.policy
    if policy.driver is None or svc.monotonic() < svc.owner_retry_at:
        return False
    try:
        policy.owner_check()
    except Exception:       # whatever the refusal, there is no owner this pass: keep everything
        svc.owner_retry_at = svc.monotonic() + OWNER_RETRY_SECONDS
        return False
    try:
        with svc.store.transaction():
            return _pass(svc)
    except StoreError:
        return False        # the preauthorizations stay; the next pass begins by reconciling


def _pass(svc: Any) -> bool:
    now = svc.policy.clock()
    file = svc.store.read()
    facts = svc.facts(file)
    done = svc.processed(facts, now)
    if done:
        svc.commit([row for row in file.entries if row.run_id not in done], list(done))
    if queue_flag.consume_once(svc):
        facts = svc.facts(svc.store.read())     # the admission the flag gave is part of the facts
    carried = queue_flag.resume_next(svc, now)
    if carried != "none":
        return carried == "started"
    for item in facts:
        if item.entry.run_id in done or not _eligible(item):
            continue
        outcome = _attempt(svc, item, now)
        if outcome == "started":
            return True
        if outcome == "slot":
            return False
    return False


def _eligible(item: Facts) -> bool:
    """An entry the pump may act on: readable, confirmed, admitted here, and not in conflict."""
    return (item.recovered is not None and item.entry.preauthorization is not None
            and item.admitted and pairing_of(item) != "conflict")


def _attempt(svc: Any, item: Facts, now: str) -> str:
    """`started`, `dropped` (its permission was withdrawn, try the next) or `slot` (stop)."""
    try:
        svc.policy.driver.hold_activation(item.entry.run_id)
    except ContractError:   # SlotBusy, NewWorkHeld, a driver that is not running: nothing starts
        return "slot"
    if item.entry.kind == "start":
        return _start(svc, item, now)
    return _resume(svc, item, now)


def _start(svc: Any, item: Facts, now: str) -> str:
    policy, pre, run = svc.policy, item.entry.preauthorization, item.recovered
    reason, grant = None, None
    try:
        fresh = build_preview(run, copy.deepcopy(pre.asked), budget=policy.budget,
                              registry=policy.registry, provider_digest=policy.provider_digest,
                              clock=lambda: now, provider_facts=policy.provider_facts)
        if fresh["preview_digest"] != pre.preview_digest:
            reason = "terms_changed"
        else:
            grant = from_terms(fresh["terms"], authorization_id=pre.authorization_id,
                               authorized_by=pre.authorized_by, authorized_at=now,
                               supersedes=pre.supersedes)
            validate_authorization_history(run, grant)
    except ContractError:
        reason = "preview_refused"
    if reason is not None:
        return _drop(svc, item, reason, now)
    receipt = Receipt(item.entry.run_id, "run_authorization", pre.authorization_id,
                      pre.authorized_by, pre.preauthorized_at, pre.preview_digest,
                      grant.authorization_digest, now, "confirmation")
    return _carry_out(svc, item, receipt, grant, grant.authorization_id)


def _resume(svc: Any, item: Facts, now: str) -> str:
    pre, run = item.entry.preauthorization, item.recovered
    reason = _resume_refusal(pre, run, now)
    control = None
    if reason is None:
        control = RunAuthorizationControl(
            control_id=pre.control_id, run_id=item.entry.run_id,
            authorization_id=pre.authorization_id, authorization_digest=pre.authorization_digest,
            action="resume", actor=pre.actor, recorded_at=now,
            expected_control_id=pre.expected_control_id)
        try:
            validate_authorization_history(run, control)
        except ContractError:
            reason = "preview_refused"
    if reason is not None:
        return _drop(svc, item, reason, now)
    receipt = Receipt(item.entry.run_id, "run_authorization_control", pre.control_id, pre.actor,
                      pre.preauthorized_at, pre.authorization_digest, record_digest(control), now,
                      "confirmation")
    return _carry_out(svc, item, receipt, control, pre.authorization_id)


def _resume_refusal(pre: Any, run: Any, now: str) -> str | None:
    return resume_refusal(pre.authorization_id, pre.authorization_digest,
                          pre.expected_control_id, run, now)


def _carry_out(svc: Any, item: Facts, receipt: Receipt, record: Any, grant_id: str) -> str:
    """Receipt, journal record, activation, removal, frame: in that order, each one recoverable."""
    run_id = item.entry.run_id
    svc.store.put_receipt(receipt)
    svc.policy.store.append(record)
    svc.policy.driver.activate(run_id, grant_id)
    _remove(svc, item.entry)
    svc.policy.notify(run_id)
    return "started"


def _remove(svc: Any, entry: QueueEntry) -> None:
    """Take the started entry out; a failure here never undoes the start (spec 4.4.4 step 4)."""
    try:
        file = svc.store.read()
        svc.commit([row for row in file.entries if row.run_id != entry.run_id], [entry.run_id])
    except StoreError:
        return              # the read hides it and the next pass removes it


def _drop(svc: Any, item: Facts, reason: str, now: str) -> str:
    """Withdraw a preauthorization: the entry keeps its place and says why and when."""
    entry = item.entry
    dropped = QueueEntry(entry.run_id, entry.kind, entry.enqueued_at, entry.enqueued_by, None,
                         Dropped(reason, now))
    file = svc.store.read()
    svc.commit([dropped if row.run_id == entry.run_id else row for row in file.entries],
               [entry.run_id])
    return "dropped"
