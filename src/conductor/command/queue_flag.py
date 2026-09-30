"""Executing the continue-after flag in the pump (spec 4.3.4, 4.4.4 step 3).

The flag is the owner's advance permission, written in the desk of a project and read by the hub
when it decides the next project. Only the child a hub started for a PLANNED transition executes
it: `--mode active --transition <id> --auto-continue <flag_id>@<revision>`. A standalone `up`, a
process opened for viewing, a hub restart, a start after "Recover": none of them is handed the
three, and none of them consumes anything. A crash or an uncertain stop never restores permission.

On its first pass, after the owner check and before its first continuation, the child consumes the
flag with lane H's one conditional write (`auto_continue.consume`): the file is rewritten off, with
`consumed`, only if it still holds exactly the `flag_id@revision` the hub handed over. A flag taken
down or replaced after the hub read it is not executed at all, and the newer flag of the owner
survives for the next activation.

What was consumed is kept in this process alone: the runs the owner listed, each bound to the grant
(`authorization_id`, `authorization_digest`) and the last control he was looking at, and whether
the task queue may start. The runs are resumed in the order of the list, one per free slot, by a
control of the flag's actor, and only while the run still stands on that binding; its
`expected_control_id` is the stored one, not the current one. A run that moved on (a new grant, a
pause, a revoke, an open action, an expired grant) is struck from the list and waits for a human.
"""
from __future__ import annotations

import hashlib
from typing import Any

from . import auto_continue
from .authorization_history import validate_authorization_history
from .contract_values import ContractError
from .queue_reading import record_digest, resume_refusal
from .queue_store import JOURNAL_KIND, Receipt
from .run_authorization import RunAuthorizationControl


def consume_once(svc: Any) -> bool:
    """On the first pass of a planned transition, consume the flag the hub handed this child.

    Returns True when this call consumed a flag (the admission it gives changes the facts).

    A `StoreError` of the write itself is not an answer (the pass ends and the next one tries
    again); a record that is not a flag, a hand-over that is not the shape of one, and a flag that
    is no longer the standing one are answers, and the flag is then not executed.
    """
    if svc.flag_tried or not svc.hands_over_a_flag():
        return False
    flag_id, _, revision = svc.auto_continue.partition("@")
    try:
        record = auto_continue.consume(
            svc.flags, expected_flag_id=flag_id, expected_revision=int(revision),
            transition_id=svc.transition_id, activation_nonce=svc.project_id,
            clock=svc.policy.clock)
    except (ContractError, ValueError, auto_continue.CorruptFlag):
        svc.flag_tried = True
        return False
    svc.flag_tried = True
    if record is None:
        return False
    svc.flag_record, svc.flag_runs = record, list(record.resume_runs)
    if record.start_task_queue:
        svc.admit_all_on_file()
    return True


def control_id_of(flag_id: str, run_id: str) -> str:
    """One name per (flag, run), so a retry after a fault finds what a first try left.

    The name is `flag-` and 32 hex digits: a control of this shape in a run's journal is a resume
    the flag wrote (the control has no field for it), and a test holds the shape for the readers
    that rely on it.
    """
    return "flag-" + hashlib.sha256(f"{flag_id}/{run_id}".encode("utf-8")).hexdigest()[:32]


def resume_next(svc: Any, now: str) -> str:
    """Resume the next listed run that still stands on its binding: `started`, `slot` or `none`.

    `slot` means the driver's own `hold_activation` refused (the slot is taken, a drain is on, it
    is not running): nothing more starts this pass, and the run stays on the list for the next.
    """
    policy = svc.policy
    while svc.flag_runs:
        bound = svc.flag_runs[0]
        recovered = svc.recovered(bound.run_id)
        if recovered is None or resume_refusal(
                bound.authorization_id, bound.authorization_digest, bound.last_control_id,
                recovered, now) is not None:
            svc.flag_runs.pop(0)                 # it waits for a human, as any run does
            continue
        try:
            policy.driver.hold_activation(bound.run_id)
        except ContractError:
            return "slot"
        if _carry_out(svc, bound, recovered, now):
            return "started"
    return "none"


def _carry_out(svc: Any, bound: Any, recovered: Any, now: str) -> bool:
    """Receipt, control, activation, frame; False when the run was struck instead.

    A retry after a fault never writes a second control: once the control is in the journal the
    last control of the grant is no longer the one the flag recorded, so the run is struck. So is
    a run whose receipt the store refuses to create (a path over the Windows budget, judged before
    any effect): it can never be written, and left first in the list it would stop the queue.
    """
    flag, policy = svc.flag_record, svc.policy
    control_id = control_id_of(flag.flag_id, bound.run_id)
    control = RunAuthorizationControl(
        control_id=control_id, run_id=bound.run_id, authorization_id=bound.authorization_id,
        authorization_digest=bound.authorization_digest, action="resume", actor=flag.actor,
        recorded_at=now, expected_control_id=bound.last_control_id)
    try:
        validate_authorization_history(recovered, control)
    except ContractError:
        svc.flag_runs.pop(0)
        return False
    receipt = Receipt(bound.run_id, JOURNAL_KIND["resume"], control_id, flag.actor, flag.set_at,
                      bound.authorization_digest, record_digest(control), now, "auto_continue",
                      flag.flag_id, svc.transition_id)
    try:
        svc.store.put_receipt(receipt)
    except ContractError:
        svc.flag_runs.pop(0)
        return False
    policy.store.append(control)
    policy.driver.activate(bound.run_id, bound.authorization_id)
    svc.flag_runs.pop(0)
    policy.notify(bound.run_id)
    return True
