"""What a project's child is, in the words of 4.6.4, and what the hub does about it (4.1.5, 4.1.7).

Three pure functions, no IO:

- `derive` turns a status record, the liveness of the process it names and what the hub itself
  knows into the pair `(state, state_code)`: the table of 4.1.5 and the state rows of 4.1.10.
  The `state` is one of the eleven words of 4.6.4; `state_code` is one of the codes of the start
  table plus the two the hub adds, and is set only where the row says so.
- `restart_action` is the restart table of 4.1.7: what the hub does at its own start with a
  project whose file and process are as given: `start`, `wait` or `offer_recover`.
- `working_of` is the order of 4.1.10: `active`, then `view`, then `queued`, then `stopped`.

A process whose liveness is `unproven` (something runs at the pid and the record cannot say
whether it is the same) is taken as alive wherever a wrong guess would start a second child.
"""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace

from conductor import up_flags, up_status

STATES = ("stopped", "starting", "running", "stopping", "stop_overdue", "stop_uncertain",
          "failed", "busy_elsewhere", "recovery_required", "identity_mismatch", "missing")
#: The codes the hub itself adds to those of the start table (4.1.5).
HUB_CODES = frozenset({"start_timeout", "active_not_closed"})
STATE_CODES = frozenset(up_flags.START_CODES) | HUB_CODES
_FAILED_CODES = STATE_CODES - {"project_identity_changed", "owner_busy", "recovery_required",
                               "ownership_lost"} - HUB_CODES
_STARTED = ("starting", "serving", "stopping", "stop_overdue")


@dataclass(frozen=True)
class Lifecycle:
    """The state of a project's child and, for a failure, the code that says which."""

    state: str
    state_code: str | None = None


def derive(record: up_status.StatusRecord | None, liveness: str, *, pending: str | None = None,
           head_phase: str | None = None, prior_alive: bool = False,
           hub_code: str | None = None) -> Lifecycle:
    """The lifecycle of one project.

    Args:
        record: The status file, or `None` when there is none (or it is an older child's).
        liveness: `alive`, `dead` or `unproven`, for the process the record names.
        pending: The hub's own child that has not reported: `alive` while it runs, `exited`
            once it has left without a record; `None` when the hub has none.
        head_phase: The phase of the ownership head, for a process that died in its work.
        prior_alive: Whether the hub's own earlier child of this project is still alive (an
            `owner_busy` refusal then means it is still stopping).
        hub_code: A code the hub put on the project (`start_timeout`, `active_not_closed`).

    Raises:
        ValueError: `hub_code` is not one of the hub's codes.
    """
    if hub_code is not None and hub_code not in HUB_CODES:
        raise ValueError(f"hub_code must be one of {', '.join(sorted(HUB_CODES))}")
    if hub_code == "start_timeout":
        return Lifecycle("failed", "start_timeout")
    base = _from_record(record, liveness, pending, head_phase, prior_alive)
    return replace(base, state_code=hub_code) if hub_code is not None else base


def _from_record(record: up_status.StatusRecord | None, liveness: str, pending: str | None,
                 head_phase: str | None, prior_alive: bool) -> Lifecycle:
    if record is None:
        return {None: Lifecycle("stopped"), "alive": Lifecycle("starting"),
                "exited": Lifecycle("failed", "start_failed")}[pending]
    alive = liveness != "dead"
    if record.state == "refused":
        return _refused(record.code, prior_alive)
    if record.state == "starting":
        return Lifecycle("starting") if alive else Lifecycle("failed", "start_failed")
    if record.state in ("serving", "stopping", "stop_overdue"):
        if alive:
            return Lifecycle({"serving": "running"}.get(record.state, record.state))
        return Lifecycle("recovery_required" if head_phase == "opened" else "stopped")
    if record.state == "stop_uncertain":
        return Lifecycle("stop_uncertain")
    return Lifecycle("stopped")


def _refused(code: str | None, prior_alive: bool) -> Lifecycle:
    if code == "owner_busy":
        return Lifecycle("stopping" if prior_alive else "busy_elsewhere")
    mapped = {"project_identity_changed": "identity_mismatch",
              "recovery_required": "recovery_required", "ownership_lost": "missing"}
    if code in mapped:
        return Lifecycle(mapped[code])
    return Lifecycle("failed", code if code in _FAILED_CODES else "start_failed")


def restart_action(record: up_status.StatusRecord | None, liveness: str) -> str:
    """What the hub does at its own start with this project (the table of 4.1.7).

    Returns:
        `start`, `wait` (a process of the project is still there: poll it once a second and
        start after it leaves) or `offer_recover` (the stop was not confirmed and the process
        is dead: the person must recover, after an OS restart).

    The rows the table does not give: a `starting` file with a dead process reads as `serving`
    with one (start); `stop_uncertain` with a live process is about to leave (wait); a `stopped`
    or `refused` file starts whatever the process does, as the table says.
    """
    if record is None or record.state in ("stopped", "refused"):
        return "start"
    alive = liveness != "dead"
    if record.state == "stop_uncertain":
        return "wait" if alive else "offer_recover"
    return "wait" if alive else "start"


def working_of(project_id: str, *, active: str | None, queue: Collection[str],
               viewing: Collection[str]) -> str:
    """`active`, `view`, `queued` or `stopped`, by the order of 4.1.10."""
    if project_id == active:
        return "active"
    if project_id in viewing:
        return "view"
    return "queued" if project_id in queue else "stopped"
