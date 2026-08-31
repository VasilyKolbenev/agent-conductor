"""What an authorization and an attempt ARE, with no behaviour attached.

Split out of ``runtime`` when that module reached its line cap, along the seam
this package already draws between a value and the machine that moves it --
``contract_values`` stands in the same relation to ``contracts``. Everything
here validates itself on construction and does nothing else: no store, no
adapter, no clock, no lock. So a reader asking what a confirmation must carry
reads one short file, and a reader asking what happens to it never walks past
these definitions to find out.

The states are the reason the split is worth drawing at all. Absence is never
one of the others here: ``unknown`` is not a failure, a rejected process is not
a success, and nothing in this file can promote anything to ``succeeded``,
because nothing in this file decides anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import (
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    ControlMode,
    EvidenceRef,
    _digest,
    _id,
    _mode,
    _scope,
    _timestamp,
)


class AuthorizationError(RuntimeError):
    """A confirmation fact is changed or stale; the action is refused before preparation."""


class RunAlreadyTerminal(AuthorizationError):
    """The run recorded that its plan ended; nothing further may be authorized.

    A SUBCLASS, deliberately, and the two halves of that matter separately.
    Every `except AuthorizationError` handler in the product keeps working, so
    adding this cannot make a road that used to refuse start admitting. And the
    HTTP boundary can still tell it apart by type, which is the only way it may:
    the runtime cannot raise an `ApiRefusal` -- `api_contracts` imports from
    `runtime`, so the reverse would be a cycle -- and reading a message to
    choose a wire word is exactly what the translation layer's own docstring
    forbids.
    """


class ExecutionError(RuntimeError):
    """The runtime cannot drive a request the store never authorized or cannot bind."""


class AttemptState(str, Enum):
    """The seven states A/RT-1 keeps distinct; absence is never one of the others.

    ``accepted`` and ``started`` are pre-terminal machine states; the remaining
    five are the terminal outcomes the durable result receipt records. None is
    ever inferred from the absence of another, and ``unknown`` is never promoted
    to ``succeeded``.
    """

    ACCEPTED = "accepted"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    VERIFICATION_FAILED = "verification_failed"


#: A raw execute-reported outcome that is not ``succeeded`` maps here without ever
#: touching ``succeeded``: an unknown process stays unknown, a rejected one is not
#: a success, and a self-declared verification_failed is honoured as such.
NON_SUCCESS: dict[str, AttemptState] = {
    "failed": AttemptState.FAILED,
    "cancelled": AttemptState.CANCELLED,
    "unknown": AttemptState.UNKNOWN,
    "rejected": AttemptState.FAILED,
}


@dataclass(frozen=True)
class Confirmation:
    """A fresh Human confirmation authorizing one exact stored proposal to execute.

    It restates, in the human's own words, every fact authorization holds against
    the run's durable state: which proposal, the preview digest they saw, the
    scope and capability they approved, and the frozen configuration they approved
    under. ``confirmed_at`` is the freshness instant, ``mode`` is always Confirm --
    Policy authorization is a separate, later seam this class does not express.
    """

    confirmation_id: str
    run_id: str
    proposal_id: str
    preview_digest: str
    capability: str
    scope: tuple[str, ...]
    config_digest: str
    confirmed_by: str
    confirmed_at: str
    mode: ControlMode | str = ControlMode.CONFIRM

    def __post_init__(self) -> None:
        for name in ("confirmation_id", "run_id", "proposal_id", "capability",
                     "confirmed_by"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "preview_digest", _digest("preview_digest", self.preview_digest))
        object.__setattr__(self, "config_digest", _digest("config_digest", self.config_digest))
        object.__setattr__(self, "scope", _scope(self.scope))
        object.__setattr__(self, "confirmed_at", _timestamp("confirmed_at", self.confirmed_at))
        mode = _mode(self.mode)
        if mode is not ControlMode.CONFIRM:
            raise ContractError("a Human confirmation must carry mode 'confirm'")
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True)
class Budget:
    """The action and time budgets an authorization is held within.

    ``max_actions`` caps how many action requests one run may authorize;
    ``max_action_seconds`` caps a single action's declared timeout; and
    ``max_confirmation_age_seconds`` is the freshness window a confirmation must
    fall inside. All three refuse before preparation when exceeded.
    """

    max_actions: int
    max_action_seconds: int
    max_confirmation_age_seconds: int

    def __post_init__(self) -> None:
        for name in ("max_actions", "max_action_seconds", "max_confirmation_age_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError(f"{name} must be an integer >= 1, got {value!r}")


@dataclass(frozen=True)
class Authorization:
    """A cleared confirmation and whether this call created its durable request.

    ``record_created`` is a response disposition, not execution authority.  It is
    true only for the runtime call that appended the request; an exact immutable
    retry returns the same request with it false.
    """

    request: ActionRequest
    state: AttemptState = AttemptState.ACCEPTED
    record_created: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.request, ActionRequest):
            raise ContractError("Authorization.request must be an ActionRequest")
        object.__setattr__(
            self, "request", ActionRequest.from_dict(self.request.as_dict()))
        if self.state is not AttemptState.ACCEPTED:
            raise ContractError("Authorization starts in accepted state")
        if type(self.record_created) is not bool:
            raise ContractError("Authorization.record_created must be a boolean")


@dataclass(frozen=True)
class Attempt:
    """One executed attempt: its terminal state, the state path it took, and receipt.

    ``history`` records states supported by this process or durable attempt facts.
    A live execute and a replay carrying an effect lease include ``started``;
    prepare refusal and legacy result replay do not. ``receipt`` is the immutable
    terminal record. Verification evidence is returned only when it follows a
    durable observation and is bound to the frozen adapter by the store relation.
    """

    request: ActionRequest
    state: AttemptState
    receipt: ActionResultReceipt
    history: tuple[AttemptState, ...]
    verification_evidence: tuple[EvidenceRef, ...] = ()
