"""Closed deep-adapter arguments and code-owned process specifications."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from .deep_contracts import (
    OMITTED,
    DeepAdapterConfig,
    DeepContractError,
    DeepProtocol,
    _closed_id,
    _enum,
    _env_names,
    _exact,
    _ids,
    _Omitted,
    settle_instruction_digest,
    settle_step_purpose,
)

if TYPE_CHECKING:
    from .process import CommandSpec


DEEP_PROTOCOL_FLAGS = MappingProxyType({
    DeepProtocol.FAKE_CLAUDE_V1.value: "--fake-claude-jsonl-v1",
    DeepProtocol.FAKE_CODEX_V1.value: "--fake-codex-jsonl-v1",
})
DEEP_WORKING_DIRECTORY = "work"
DEEP_OUTPUT_PROFILE = "bounded-jsonl-v1"
DEEP_OUTPUT_LIMIT = 16 * 1024
DISPATCH_PROFILES = frozenset({"implement", "review"})
#: What each output-limit profile MEANS, in bytes a child may write.
#:
#: The profile has been a validated word with no consequence: every dispatch
#: carried one, the closed schema refused any other value, every shipped starter
#: names `normal` -- and the byte count handed to the runner was a constant, so
#: naming `small` bought a step nothing. That is the exact shape the release
#: verdict rejects, and it was the example it named.
#:
#: A CEILING, never a raise. `_spawn` takes the smaller of this and the
#: provider's own `HarnessProfile.output_limit`, so a plan may ask a step to
#: write less and can never ask a provider to tolerate more than its own
#: transport was reviewed for -- the same rule `timeout_seconds` already
#: follows. `normal` is deliberately the standing default, so no step that
#: names it changes behaviour and no shipped document moves.
OUTPUT_LIMIT_BYTES = MappingProxyType({"small": 4 * 1024, "normal": 16 * 1024})
#: Derived from the table above rather than written twice: a profile that has
#: no byte count is a word the schema would admit and the spawn could not honour.
OUTPUT_LIMIT_PROFILES = frozenset(OUTPUT_LIMIT_BYTES)
REVIEW_PROFILES = frozenset({"quality", "security", "spec"})
#: UNREACHABLE IN THIS RELEASE, and said here rather than discovered later.
#:
#: This and the three below belong to the `evidence`, `stop`, `retry` and
#: `switch` capabilities of the deep protocol. Every provider in
#: `providers.PROVIDER_CATALOG` declares only `observe`, `dispatch` and
#: `review`, so no run this build can open will ever compose an argument these
#: vocabularies judge. They are exercised by the deep contract tests and by the
#: fake harness, and by nothing a person can reach.
#:
#: They are kept, and kept HERE, on purpose. The argument dataclasses beside
#: them are the reviewed schema for those capabilities; a vocabulary moved away
#: from the validator that spends it is a vocabulary free to drift from it, and
#: deleting the pair would mean re-deriving both the day a provider declares one.
#: What the comment buys is that nobody reads this as shipped surface: a
#: capability with no provider is not a feature, and this file must not imply
#: otherwise.
REQUESTED_EVIDENCE_KINDS = frozenset({"result", "diff", "tests", "status"})
STOP_REASONS = frozenset({"user", "timeout", "switch"})
RETRY_REASONS = frozenset({
    "failed", "unknown", "verification_failed", "user"})


class _StrictArguments:
    _FIELDS: ClassVar[frozenset[str]]
    _ARRAY_FIELDS: ClassVar[frozenset[str]] = frozenset()
    #: Fields a payload MAY omit. Everything else in `_FIELDS` is required, so
    #: the default of nothing keeps every existing argument type exactly as
    #: strict as it was.
    #:
    #: It exists because a frozen artefact and a new field cannot both be right
    #: otherwise. `result_artifact_ref` is what makes a review's output
    #: publishable, and revision 1 of the Dalio template -- along with the
    #: ALPHA-3 definition and the cockpit boundary fixtures frozen beside it --
    #: was written before it existed. Rewriting those bytes to fit a new field
    #: would destroy the historical witnesses; requiring the field would make
    #: them unreadable. So the CONTRACT reads both shapes and the TRANSPORT
    #: refuses to run a review that names no output, which is where the
    #: consequence actually lives.
    _OPTIONAL_FIELDS: ClassVar[frozenset[str]] = frozenset()

    def as_dict(self) -> dict[str, Any]:
        if type(self) not in DEEP_ARGUMENT_TYPES.values():
            raise DeepContractError("deep arguments must remain canonical")
        failed = False
        try:
            canonical = type(self)(**{
                name: getattr(self, name) for name in self._FIELDS})
        except Exception:  # noqa: BLE001 -- a mutated value remains untrusted
            failed = True
            canonical = None
        if failed:
            raise DeepContractError("deep arguments must remain canonical") from None
        assert canonical is not None
        return {
            name: list(value) if type(value) is tuple else value
            for name in canonical._FIELDS
            if (value := getattr(canonical, name)) is not OMITTED
        }

    @property
    def task_scope(self) -> str | None:
        """The task whose directory this work lives in, or None for a task-less run."""
        scope = getattr(self, "work_scope", OMITTED)
        return None if scope is OMITTED else scope

    @classmethod
    def from_dict(cls, value: object):
        if cls not in DEEP_ARGUMENT_TYPES.values():
            raise DeepContractError("argument reconstruction requires an exact base type")
        data = _exact(
            value, cls._FIELDS, cls.__name__, optional=cls._OPTIONAL_FIELDS)
        if any(type(data[name]) is not list for name in cls._ARRAY_FIELDS):
            raise DeepContractError("argument array fields must be JSON arrays")
        return cls(**data)


@dataclass(frozen=True)
class DeepDispatchArgs(_StrictArguments):
    work_item_id: str
    instruction_ref: str
    profile: str
    artifact_refs: tuple[str, ...] | list[str]
    output_limit_profile: str
    #: Why the PLAN says this step exists, materialized into the payload by
    #: `graph_template._dispatch_payload`. Omittable, so every document written
    #: before it existed still reads and no frozen revision moves; and never
    #: composed by hand, because `graph_causality` refuses any request whose
    #: arguments are not byte-identical to the plan node's.
    step_purpose: "str | _Omitted" = OMITTED
    #: The digest of the instruction BYTES this step was previewed with, when
    #: the proposal promised them. A reference names a place and a place can be
    #: rewritten -- the file road reads the instruction from disk at dispatch --
    #: so only the bytes can say the child is being asked what the person
    #: approved. Omittable, and its absence is the road exactly as it was: a
    #: proposal written before this field promised nothing about these bytes,
    #: and a door added today may not re-judge what passed before it existed.
    #: Carried, never computed here: a value this build derived itself would be
    #: checking its own reading against itself.
    instruction_digest: "str | _Omitted" = OMITTED
    #: The run's TASK, when it has one: which task directory the work item lives
    #: in (`harness_workspace.work_parts`). A plan's steps carry it materialized
    #: from the run's frozen task binding; a proposal on a run with no plan carries
    #: what its caller wrote. Either way it is judged against that binding
    #: (`task_contracts.work_scope_disagreement`) at every door that admits work:
    #: the plan doors, the proposal door and the authority to execute.
    #: Omittable, and its absence is the task-less road exactly as it was, so no
    #: standing plan's directory moves.
    work_scope: "str | _Omitted" = OMITTED
    _FIELDS = frozenset({
        "work_item_id", "instruction_ref", "profile", "artifact_refs",
        "output_limit_profile", "step_purpose", "instruction_digest", "work_scope"})
    _OPTIONAL_FIELDS = frozenset({"step_purpose", "instruction_digest", "work_scope"})
    _ARRAY_FIELDS = frozenset({"artifact_refs"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_item_id", _closed_id(
            "work_item_id", self.work_item_id))
        object.__setattr__(self, "instruction_ref", _closed_id(
            "instruction_ref", self.instruction_ref))
        object.__setattr__(self, "profile", _enum(
            "profile", self.profile, DISPATCH_PROFILES))
        object.__setattr__(self, "artifact_refs", _ids(
            "artifact_refs", self.artifact_refs, empty=True))
        object.__setattr__(self, "output_limit_profile", _enum(
            "output_limit_profile", self.output_limit_profile,
            OUTPUT_LIMIT_PROFILES))
        settle_step_purpose(self)
        settle_instruction_digest(self)
        _settle_work_scope(self)


def _settle_work_scope(args) -> None:
    """A carried task scope is an id of the contract's grammar, or it is refused."""
    if args.work_scope is not OMITTED:
        object.__setattr__(args, "work_scope", _closed_id("work_scope", args.work_scope))


@dataclass(frozen=True)
class DeepReviewArgs(_StrictArguments):
    work_item_id: str
    target_artifact_refs: tuple[str, ...] | list[str]
    #: Where this review's own output is published. Omittable in a PAYLOAD and
    #: REQUIRED to run: revision 1 of the Dalio template was written before the
    #: field existed, and it is a frozen historical witness. A review that names
    #: no result artifact is refused by the transport, with a receipt saying so,
    #: rather than by a parser that would make the frozen bytes unreadable.
    #:
    #: It carries NO dataclass default, and keeps its place in the order. A
    #: default would have to move it last, and every construction of this type
    #: passes four positional strings -- so the move would have slid a profile
    #: into a reference and back, silently, at eight call sites. `from_dict`
    #: always passes the key, `OMITTED` when the payload left it out.
    #:
    #: `OMITTED` and `None` are NOT the same answer. A payload that carries an
    #: explicit `null` chose a value, and that value is refused here like any
    #: other wrong one; only a payload that says nothing is admitted.
    result_artifact_ref: "str | _Omitted"
    review_profile: str
    #: The same plan-authored context a dispatch carries; see `DeepDispatchArgs`.
    step_purpose: "str | _Omitted" = OMITTED
    #: The run's task, exactly as on `DeepDispatchArgs`: a review stands in the
    #: same directory the work it reviews was written to.
    work_scope: "str | _Omitted" = OMITTED
    _FIELDS = frozenset({
        "work_item_id", "target_artifact_refs", "result_artifact_ref",
        "review_profile", "step_purpose", "work_scope"})
    _OPTIONAL_FIELDS = frozenset({"result_artifact_ref", "step_purpose", "work_scope"})
    _ARRAY_FIELDS = frozenset({"target_artifact_refs"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_item_id", _closed_id(
            "work_item_id", self.work_item_id))
        object.__setattr__(self, "target_artifact_refs", _ids(
            "target_artifact_refs", self.target_artifact_refs))
        if self.result_artifact_ref is not OMITTED:
            object.__setattr__(self, "result_artifact_ref", _closed_id(
                "result_artifact_ref", self.result_artifact_ref))
        object.__setattr__(self, "review_profile", _enum(
            "review_profile", self.review_profile,
            REVIEW_PROFILES))
        settle_step_purpose(self)
        _settle_work_scope(self)


@dataclass(frozen=True)
class DeepEvidenceArgs(_StrictArguments):
    target_action_id: str
    kinds: tuple[str, ...] | list[str]
    _FIELDS = frozenset({"target_action_id", "kinds"})
    _ARRAY_FIELDS = frozenset({"kinds"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_action_id", _closed_id(
            "target_action_id", self.target_action_id))
        if type(self.kinds) not in (list, tuple):
            raise DeepContractError("kinds must be a list")
        kinds = tuple(self.kinds)
        if not kinds or any(
                type(row) is not str or row not in REQUESTED_EVIDENCE_KINDS
                for row in kinds):
            raise DeepContractError("kinds contains an unsupported evidence kind")
        if len(kinds) != len(set(kinds)):
            raise DeepContractError("kinds must not repeat a value")
        object.__setattr__(self, "kinds", kinds)


@dataclass(frozen=True)
class DeepStopArgs(_StrictArguments):
    target_attempt_id: str
    reason: str
    _FIELDS = frozenset({"target_attempt_id", "reason"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_attempt_id", _closed_id(
            "target_attempt_id", self.target_attempt_id))
        object.__setattr__(self, "reason", _enum(
            "reason", self.reason, STOP_REASONS))


@dataclass(frozen=True)
class DeepRetryArgs(_StrictArguments):
    prior_action_id: str
    reason: str
    _FIELDS = frozenset({"prior_action_id", "reason"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "prior_action_id", _closed_id(
            "prior_action_id", self.prior_action_id))
        object.__setattr__(self, "reason", _enum(
            "reason", self.reason, RETRY_REASONS))


@dataclass(frozen=True)
class DeepSwitchArgs(_StrictArguments):
    prior_action_id: str
    target_instance_id: str
    handoff_ref: str
    _FIELDS = frozenset({"prior_action_id", "target_instance_id", "handoff_ref"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "prior_action_id", _closed_id(
            "prior_action_id", self.prior_action_id))
        object.__setattr__(self, "target_instance_id", _closed_id(
            "target_instance_id", self.target_instance_id))
        object.__setattr__(self, "handoff_ref", _closed_id(
            "handoff_ref", self.handoff_ref))


DEEP_ARGUMENT_TYPES = MappingProxyType({
    "dispatch": DeepDispatchArgs,
    "review": DeepReviewArgs,
    "evidence": DeepEvidenceArgs,
    "stop": DeepStopArgs,
    "retry": DeepRetryArgs,
    "switch": DeepSwitchArgs,
})


@dataclass(frozen=True)
class DeepCommandSpec:
    """One structural invocation, re-derived from config before runner use."""

    argv: tuple[str, ...]
    cwd: str
    env_allow: tuple[str, ...]
    output_profile: str
    timeout_seconds: int

    def __post_init__(self) -> None:
        if (type(self.argv) is not tuple or len(self.argv) != 2
                or any(type(row) is not str or not row or "\x00" in row
                       for row in self.argv)):
            raise DeepContractError("argv must be the exact reviewed two-value tuple")
        executable, flag = self.argv
        if not (PurePosixPath(executable).is_absolute()
                or PureWindowsPath(executable).is_absolute()):
            raise DeepContractError("argv executable must be an absolute configured path")
        if flag not in DEEP_PROTOCOL_FLAGS.values():
            raise DeepContractError("argv protocol flag is not reviewed")
        if type(self.cwd) is not str or self.cwd != DEEP_WORKING_DIRECTORY:
            raise DeepContractError("cwd must equal the reviewed strict descendant")
        object.__setattr__(self, "env_allow", _env_names(self.env_allow))
        if (type(self.output_profile) is not str
                or self.output_profile != DEEP_OUTPUT_PROFILE):
            raise DeepContractError("output profile is not reviewed")
        if type(self.timeout_seconds) is not int or self.timeout_seconds < 1:
            raise DeepContractError("timeout_seconds must be a positive integer")

    @classmethod
    def from_config(
            cls, config: DeepAdapterConfig, *, timeout_seconds: int) -> "DeepCommandSpec":
        if cls is not DeepCommandSpec:
            raise DeepContractError("from_config requires the exact spec base type")
        if type(config) is not DeepAdapterConfig:
            raise DeepContractError("from_config requires a DeepAdapterConfig")
        if type(timeout_seconds) is not int or timeout_seconds < 1:
            raise DeepContractError("timeout_seconds must be a positive integer")
        failed = False
        try:
            canonical = DeepAdapterConfig(
                config.executable, config.protocol, config.env_allow, config.real_mode)
        except Exception:  # noqa: BLE001 -- a mutated config remains untrusted
            failed = True
            canonical = None
        if failed:
            raise DeepContractError(
                "from_config requires a canonical DeepAdapterConfig") from None
        assert canonical is not None
        return DeepCommandSpec(
            (canonical.executable, DEEP_PROTOCOL_FLAGS[canonical.protocol.value]),
            DEEP_WORKING_DIRECTORY, canonical.env_allow, DEEP_OUTPUT_PROFILE,
            timeout_seconds)

    def to_runner_spec(self, config: DeepAdapterConfig) -> CommandSpec:
        """Re-derive authority and return the sole ProcessRunner input form."""
        from .process import CommandSpec

        if type(self) is not DeepCommandSpec:
            raise DeepContractError("runner conversion requires the exact spec base type")
        if type(config) is not DeepAdapterConfig:
            raise DeepContractError("from_config requires a DeepAdapterConfig")
        if (type(self.argv) is not tuple
                or type(self.env_allow) not in (list, tuple)
                or type(config.env_allow) not in (list, tuple)):
            raise DeepContractError("command spec must remain canonical")
        failed = False
        try:
            candidate = DeepCommandSpec(
                self.argv, self.cwd, self.env_allow, self.output_profile,
                self.timeout_seconds)
            reviewed_config = DeepAdapterConfig(
                config.executable, config.protocol, config.env_allow, config.real_mode)
            canonical = DeepCommandSpec.from_config(
                reviewed_config, timeout_seconds=candidate.timeout_seconds)
        except Exception:  # noqa: BLE001 -- a mutated value remains untrusted
            failed = True
            candidate = canonical = None
        if failed:
            raise DeepContractError(
                "command spec does not equal its frozen config") from None
        assert candidate is not None and canonical is not None
        if candidate != canonical:
            raise DeepContractError("command spec does not equal its frozen config")
        return CommandSpec(
            argv=canonical.argv, cwd=canonical.cwd,
            env_allow=canonical.env_allow, output_limit=DEEP_OUTPUT_LIMIT,
            timeout_seconds=canonical.timeout_seconds)
