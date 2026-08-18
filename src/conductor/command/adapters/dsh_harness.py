"""The DeepSeek Harness (dsh) headless adapter: one pinned interpreter, one task.

The vendor contract this adapter is written against was read from the project's
own published sources on 2026-08-17 and is recorded here so a later reader can
re-check it rather than trust this prose:

- the CLI ships as the npm package ``@deepseek-ai/dsh``, whose ``bin`` maps the
  name ``dsh`` to ``lib/bin.js`` -- a Node script, never a native executable and
  never a Windows ``.cmd`` shim;
- the one-shot, non-interactive transport is the ``headless`` profile bundle,
  described by its own package as "a direct core Agent/Session runner over
  dsh-base with no Host, HTTP, or browser layer", invoked as
  ``dsh --profile headless "task"``: one task, no follow-up, no listening port,
  exit 0 when the turn ended and 1 when it did not;
- ``-V``/``--version`` is handled by the launcher's own argument adapter, which
  prints and exits;
- ``DSH_HOME`` is read by the harness's shared path helper (an empty or
  whitespace-only value counts as unset, and the default is ``~/.dsh``), and
  ``DSH_TELEMETRY_DISABLED`` is read by the CLI's profile boot, where ANY
  non-empty value disables telemetry;
- the ``headless`` profile is a built-in template that auto-initializes on first
  use, which is the only reason a FRESH, isolated ``DSH_HOME`` can boot it.

What this module refuses is as much of the contract as what it uses. It runs
ONLY an operator-pinned absolute Node executable against an operator-pinned
absolute entrypoint: no ``npx``, no ``npm`` shim, no ``PATH`` search, no home
scan, no "latest", no install, and never ``shell=True``. It mints a fresh
``DSH_HOME`` per attempt and never reuses one, so two attempts share no profile
state. It proves the pinned build's version EXACTLY before a task is spawned, so
a mismatched install spawns the task zero times. Its argv is code-owned down to
the last token: the authorized capability body is a closed set of contract
identifiers, and no value from it can be read by the launcher as one of its own
flags. Raw child output is bounded, drained, and discarded -- it never reaches a
receipt, the journal, the API, an SSE frame, evidence, or an exception message.

Exit 0 means the process was OBSERVED to end, never that the work is right, and
in this build it can never mean more than that. Verification is a separate seam
and reads only INDEPENDENT workspace evidence: files that actually changed under
the action's own authorized subtree. This build writes NO durable evidence
record, so the seam never answers ``verified`` and never mints an evidence
identifier it cannot back -- absence of proof is reported as ``error``, which
the runtime resolves to ``verification_failed``, and a change outside the
authorized subtree is ``mismatch``. ``unavailable`` is never used at all: the
runtime reserves that token for an adapter that exposes no verifier, and reading
absence of proof as absence of a verifier is how exit zero became success. The
day a durable evidence-writer lands, what changes a terminal state is the
EVIDENCE; it is never the exit code.

The prompt is held to the same standard. A task sentence naming only an
instruction REFERENCE would send the real dsh something that is not the user's
task, so the instruction TEXT is materialized through the workspace door from
one contained file, and a dispatch that cannot materialize it refuses before any
child exists rather than dispatching a vague prompt.

Every name this adapter writes through -- the per-attempt home, the marker, the
work subtree and the instruction -- is proved contained by the workspace door
before the write, with the typed lstat-only relation the preview's route gate
and the owned runner's cwd walk already use. And a task is never run twice: a
marker written before the spawn survives a crash, so a restart that finds it
reports an honest ``unknown`` instead of repeating the work.

DSH_HOME retention is stated, not implied. A real harness may write prompt,
session, tool output and model text into its home, so the home is minted fresh
per SPAWN, is never read by anything here, and is discarded when the spawn
returns; a home a crash left behind is swept at the next dispatch. Nothing from
it reaches a receipt, the journal, evidence, the API or an exception message, and
no dsh home is ever a durable record of model text.

That promise is kept against a HOSTILE child too, which is what it was missing.
A child can replace the home directory this process minted with a portal; the
entry is still one this process created and remembers, so it is removed by its
own entry and the tree it named keeps every byte. When a discard genuinely
cannot happen, the failure is COUNTED rather than swallowed: every receipt the
dispatch goes on to build states it beside -- never instead of -- what the spawn
did. And the standing home is not merely reported at the next dispatch, it stops
it: a sweep that cannot take everything under the home root refuses the whole
dispatch, spawning nothing at all, until an operator has cleared it.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from ..contracts import ActionRequest, ActionResultReceipt
from .base import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
    UnsupportedCapability,
)
from .deep_commands import DeepDispatchArgs
from .deep_contracts import DeepProtocol
from .dsh_workspace import (
    HOME_DIR,
    INSTRUCTION_DIR,
    MARKER_DIR,
    WORK_DIR,
    DshWorkspace,
    WorkspaceNotContained,
)
from .process import CommandSpec, ProcessOutcome, ProcessRunner, ProcessRunnerError

#: The exact published version this build was reviewed against. A preflight that
#: reads anything else refuses; the harness is a developer preview whose own
#: README promises compatibility-breaking changes, so "close enough" is not a
#: safe reading of a version string.
REVIEWED_DSH_VERSION = "0.1.0-rc.7"
#: The protocol token an operator pins to select this adapter.
DSH_PROTOCOL = DeepProtocol.DSH_HEADLESS_V1.value
#: The environment NAMES this adapter owns. Only names live in durable config;
#: the home's VALUE is minted per attempt and never written to any config.
DSH_HOME_ENV = "DSH_HOME"
DSH_TELEMETRY_DISABLED_ENV = "DSH_TELEMETRY_DISABLED"
#: Any non-empty value disables vendor telemetry; "1" is the one this build sends.
TELEMETRY_DISABLED = "1"
#: The code-owned launcher flags. No caller ever contributes a flag.
HEADLESS_ARGV = ("--profile", "headless")
VERSION_ARGV = ("--version",)
#: Capture ceiling for either spawn; the pump drains past it and drops the rest.
DSH_OUTPUT_LIMIT = 16 * 1024
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: The one control this adapter carries. stop, retry and switch stay ABSENT.
DSH_CAPABILITY = "dispatch"
#: Re-exported from the workspace door so a reader of this module can see the
#: subtrees it owns without following an import.
__all__ = [
    "DSH_PROTOCOL", "HOME_DIR", "INSTRUCTION_DIR", "MARKER_DIR",
    "REVIEWED_DSH_VERSION", "WORK_DIR",
    "DshHarnessAdapter", "DshHarnessError", "DshPin",
]
#: What a refused workspace route reports. It carries no path and no child
#: detail: the route is operator state, and naming it here would put it in a
#: receipt, the journal and the API at once.
UNCONTAINED_DETAIL = (
    "a name on the dsh workspace's own writable route is not locally contained, "
    "so nothing was minted, claimed or spawned")
#: What a dispatch reports when the home root holds state this build did not
#: mint and may not delete. It carries no name and no count: the residue is
#: operator state, and the operator reads it from the disk, not from a receipt.
RESIDUE_DETAIL = (
    "the dsh home root holds state this build did not mint and may not delete, "
    "so nothing was preflighted, claimed or spawned; a dispatch runs again once "
    "an operator has cleared it")
#: Appended to whatever a receipt already says when an attempt home outlived its
#: spawn. It never replaces the observed outcome it accompanies: a cleanup that
#: did not happen is a second fact about the attempt, not a different result.
RETAINED_DETAIL = (
    " an attempt home could not be discarded and was left standing, so the next "
    "dispatch is blocked until an operator has cleared the dsh home root")


class DshHarnessError(AdapterContractError):
    """The harness cannot honour the request without breaking one of its rules."""


def _is_absolute(path: str) -> bool:
    return PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()


@dataclass(frozen=True)
class DshPin:
    """Both operator pins, re-proved absolute before either reaches an argv."""

    node_executable: str
    entrypoint: str
    env_allow: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("node_executable", "entrypoint"):
            value = getattr(self, name)
            if type(value) is not str or not value or "\x00" in value:
                raise DshHarnessError(f"{name} must be a NUL-free non-empty path")
            if not _is_absolute(value):
                raise DshHarnessError(f"{name} must be an absolute operator pin")
        names = tuple(self.env_allow)
        if any(type(row) is not str for row in names):
            raise DshHarnessError("env_allow must contain environment NAMES only")
        object.__setattr__(self, "env_allow", names)


def _flagless(token: str, what: str) -> str:
    """Prove one argv token cannot be read by the dsh launcher as its own flag.

    The launcher parses only the flags it owns and treats the first UNRECOGNIZED
    token as the start of the inner arguments. A token that begins with ``-`` is
    therefore the whole injection surface: ``--patch`` in a task position would be
    consumed by the launcher, not passed through as text. Contract identifiers
    cannot begin with ``-`` by their own grammar; this proves it at the argv
    boundary anyway, because that is where the consequence lives.
    """
    if type(token) is not str or not token.strip():
        raise DshHarnessError(f"{what} must be a non-empty task token")
    if "\x00" in token:
        raise DshHarnessError(f"{what} must not contain NUL")
    if token.startswith("-"):
        raise DshHarnessError(
            f"{what} would be read by the dsh launcher as one of its own flags")
    return token


def _task_text(args: DeepDispatchArgs, instruction: str) -> str:
    """A code-owned frame, then the MATERIALIZED instruction the user asked for.

    The frame is written here from identifiers the request validated, and it
    stands FIRST so that no byte of the instruction can occupy the launcher's
    flag position; `_flagless` proves that at the argv boundary anyway. The
    instruction itself is the task, read by the workspace door from one contained
    file -- a dispatch that could not read it never reaches this function,
    because a sentence built from the reference alone is not the user's task and
    dispatching it would be a lie about what the child was asked to do.
    """
    refs = " ".join(args.artifact_refs) or "none"
    return _flagless(
        f"conduct work item {args.work_item_id} under the {args.profile} profile "
        f"over artifacts {refs}. instruction {args.instruction_ref} reads:\n"
        f"{instruction}",
        "task text")


def _changed(before: Mapping[str, str], after: Mapping[str, str]) -> tuple[str, ...]:
    """Every path whose content appeared, vanished, or moved between snapshots."""
    return tuple(sorted(
        name for name in set(before) | set(after)
        if before.get(name) != after.get(name)))


def _version_token(output: bytes) -> str:
    """The first non-empty line of a version print, as an exact token.

    The bytes are the child's raw output, so nothing derived from them is ever
    returned to a caller: this token is only ever COMPARED against the reviewed
    constant, and the comparison's answer is a boolean.
    """
    text = output.decode("utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


@dataclass(frozen=True)
class _Attempt:
    """What one execute minted, kept so verify can read evidence, not output."""

    work_dir: Path
    before: Mapping[str, str]


class DshHarnessAdapter:
    """Run one dsh headless task per authorized action, and prove nothing more.

    The manifest holds exactly two entries: ``observe``, which reports honest
    ignorance without touching the machine, and ``dispatch``, which runs one
    task. ``stop``, ``retry`` and ``switch`` are ABSENT rather than present and
    empty, because this adapter implements none of them and the provider door
    refuses a control an adapter cannot back.
    """

    argument_schemas = {DSH_CAPABILITY: "deep-arguments-v1"}

    def __init__(
            self, pin: DshPin, runner: ProcessRunner, *, root: str | Path,
            clock: Callable[[], str], ids: Callable[[str], str],
            adapter_id: str = "deepseek-harness") -> None:
        if type(pin) is not DshPin:
            raise DshHarnessError("the harness requires an exact DshPin")
        if not isinstance(runner, ProcessRunner):
            raise DshHarnessError("the harness spawns only through an owned runner")
        self.manifest = AdapterManifest(
            adapter_id=adapter_id, display_name="DeepSeek Harness (dsh, headless)",
            vendor="DeepSeek", version=REVIEWED_DSH_VERSION,
            capabilities=("observe", DSH_CAPABILITY),
            docs_url="https://github.com/deepseek-ai/deepseek-harness")
        self._pin = pin
        self._runner = runner
        self._workspace = DshWorkspace.at(root)
        self._root = self._workspace.root
        self._clock = clock
        self._ids = ids
        self._attempts: dict[str, _Attempt] = {}
        #: How many homes this dispatch could not discard. A COUNT, never a
        #: name: the number is what a receipt may say, the name is operator
        #: state. It is re-derived per dispatch, because the standing residue
        #: itself is what the next sweep reads.
        self._retained = 0

    # -- observation: no probe, no spawn, no claim ------------------------------

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation:
        return AdapterObservation(
            adapter_id=self.manifest.adapter_id, instance_id=instance_id,
            run_id=run_id, observed_at=self._clock(), health="unknown",
            available_capabilities=(),
            detail="the dsh harness adapter never probes the machine; whether the "
                   "pinned build answers is unknown until a dispatch preflights it")

    # -- preparation: read the closed body, mint no command yet -----------------

    def prepare(self, request: ActionRequest) -> PreparedAction:
        if not isinstance(request, ActionRequest):
            raise DshHarnessError("request must be a validated ActionRequest")
        if request.capability != DSH_CAPABILITY:
            raise UnsupportedCapability(
                f"the dsh harness adapter only prepares {DSH_CAPABILITY!r}, "
                f"not {request.capability!r}")
        args = self._dispatch_args(request.arguments)
        # The payload echoes the validated identifiers ONLY. No argv, no cwd, no
        # env value and no pinned path is carried here, so nothing downstream can
        # rewrite the command by rewriting the payload.
        return PreparedAction(
            adapter_id=self.manifest.adapter_id, request=request,
            adapter_payload=args.as_dict())

    @staticmethod
    def _dispatch_args(arguments: object) -> DeepDispatchArgs:
        plain = {
            key: list(value) if type(value) is tuple else value
            for key, value in dict(arguments).items()} if isinstance(
                arguments, Mapping) else arguments
        failed = False
        try:
            args = DeepDispatchArgs.from_dict(plain)
        except Exception:  # noqa: BLE001 -- the body is untrusted; keep no graph
            failed = True
            args = None
        if failed:
            raise DshHarnessError(
                "dispatch arguments do not match the closed deep dispatch schema")
        assert args is not None
        return args

    # -- execution: preflight, mark, spawn once ---------------------------------

    def execute(self, prepared: PreparedAction) -> ActionResultReceipt:
        """Dispatch one task, or refuse; an uncontained route reaches no child.

        Every workspace road below can refuse, and a refusal is reported as this
        adapter's own fixed sentence rather than as the door's: the door's
        message names the exact path it refused, which is operator state and has
        no business in a receipt, the journal or the API.
        """
        if not isinstance(prepared, PreparedAction):
            raise DshHarnessError("execute requires a validated PreparedAction")
        request = prepared.request
        args = self._dispatch_args(prepared.adapter_payload)
        failed = False
        try:
            return self._dispatch(request, args)
        except WorkspaceNotContained:  # noqa: BLE001 -- carry no path onward
            failed = True
        if failed:
            return self._receipt(request, "failed", None, UNCONTAINED_DETAIL)
        raise DshHarnessError("unreachable")

    def _dispatch(
            self, request: ActionRequest, args: DeepDispatchArgs) -> ActionResultReceipt:
        """Claim-check, materialize, sweep, preflight, then spawn exactly once."""
        self._retained = 0
        if self._workspace.is_claimed(request.action_id):
            # A marker already claims this action: an earlier attempt reached the
            # spawn. Whether it finished is genuinely unknown, and guessing would
            # be worse than saying so -- but running the task twice is not an
            # option, so this returns without spawning anything.
            return self._receipt(
                request, "unknown", None,
                "a marker from an earlier attempt already claims this action; the "
                "dsh task is never repeated after a crash")
        instruction = self._workspace.read_instruction(args.instruction_ref)
        # A home a crashed attempt left behind is model text this build promised
        # not to retain, so it goes before this attempt mints its own. What the
        # sweep could NOT take is the whole reason this dispatch stops: state of
        # unknown ownership under the home root is either somebody else's or the
        # residue of a cleanup that failed, and running a task over either would
        # be building on a promise this build has already broken once.
        if self._workspace.sweep_homes():
            return self._receipt(request, "failed", None, RESIDUE_DETAIL)
        preflight = self._preflight(request)
        if preflight is not None:
            return preflight
        work = self._workspace.work_dir(args.work_item_id)
        before = self._workspace.digest_work_tree()
        self._workspace.claim(request.action_id)
        outcome = self._attempt(
            (*HEADLESS_ARGV, _task_text(args, instruction)),
            f"{WORK_DIR}/{args.work_item_id}", timeout=request.timeout_seconds)
        self._attempts[request.action_id] = _Attempt(work_dir=work, before=before)
        return self._observed(request, outcome)

    def _preflight(self, request: ActionRequest) -> ActionResultReceipt | None:
        """Prove the pinned build's EXACT version, or refuse before any task runs."""
        self._workspace.work_root()
        outcome = self._attempt(
            VERSION_ARGV, WORK_DIR,
            timeout=min(VERSION_TIMEOUT_SECONDS, request.timeout_seconds))
        if outcome.status != "completed" or outcome.exit_code != 0:
            return self._receipt(
                request, "failed", None,
                "the pinned dsh build did not answer a version preflight, so no "
                "task was spawned")
        if _version_token(outcome.output) != REVIEWED_DSH_VERSION:
            # The observed token is NOT reported: it is raw child output, and a
            # hostile build could put a secret where a version belongs.
            return self._receipt(
                request, "failed", None,
                f"the pinned dsh build is not the reviewed "
                f"{REVIEWED_DSH_VERSION} this adapter was written against, so no "
                f"task was spawned")
        return None

    def _attempt(
            self, argv: tuple[str, ...], cwd: str, *,
            timeout: int | float) -> ProcessOutcome:
        """One spawn inside one FRESH home, and the home goes when the spawn does.

        This is the whole of the retention promise: a real dsh may write prompt,
        session, tool output and model text under DSH_HOME, and nothing here ever
        reads a byte of it, so the honest lifetime of that state is exactly the
        lifetime of the spawn. The discard runs on every road out, including a
        raise. A home this door may NOT delete -- one holding a name whose kind
        it cannot establish -- is left standing rather than guessed at, and the
        next dispatch's sweep refuses over it rather than deleting through it.
        """
        home = self._mint_home()
        try:
            return self._spawn(argv, home, cwd, timeout=timeout)
        finally:
            self._discard(home)

    def _discard(self, home: Path) -> None:
        """Discard one attempt home, or COUNT the failure; never raise, never hide.

        This runs in a ``finally``, so raising here would replace whatever the
        spawn did with a cleanup error -- which is why the old body swallowed the
        refusal. Swallowing it was worse: the home survived, the next dispatch
        ran anyway, and the retention promise was silently broken. The refusal is
        counted instead, so every receipt this dispatch goes on to build states
        it alongside its own outcome, and the standing home stops the next
        dispatch at the sweep.
        """
        try:
            self._workspace.discard_home(home)
        except (WorkspaceNotContained, OSError):  # noqa: BLE001 -- carry no path onward
            self._retained += 1

    def _spawn(
            self, argv: tuple[str, ...], home: Path, cwd: str, *,
            timeout: int | float) -> ProcessOutcome:
        """The ONE place a child is started; argv, env and bounds are all code-owned.

        ``cwd`` is a route RELATIVE to the project root, so the runner's own
        containment walk -- which refuses a symlink, a junction, a ``..`` segment
        or anything not strictly beneath the root -- is what decides where the
        child may stand. This adapter never hands it an absolute path.
        """
        failed = False
        try:
            # Building the spec is part of the spawn: a pin that cannot become a
            # valid argv must refuse with the SAME fixed sentence as a spawn that
            # cannot start, so no runner message and no path leaks through here.
            spec = CommandSpec(
                argv=(self._pin.node_executable, self._pin.entrypoint, *argv),
                cwd=cwd, env_allow=self._pin.env_allow,
                env={
                    DSH_HOME_ENV: str(home),
                    DSH_TELEMETRY_DISABLED_ENV: TELEMETRY_DISABLED},
                output_limit=DSH_OUTPUT_LIMIT, timeout_seconds=timeout)
            return self._runner.run(spec)
        except ProcessRunnerError:  # noqa: BLE001 -- carry no child detail onward
            failed = True
        if failed:
            raise DshHarnessError(
                "the dsh harness could not start the pinned build") from None
        raise DshHarnessError("unreachable")

    def _observed(
            self, request: ActionRequest, outcome: ProcessOutcome) -> ActionResultReceipt:
        """Report what was OBSERVED. Exit zero is an observation, not a success."""
        if outcome.status == "timed_out":
            return self._receipt(
                request, "failed", None,
                "the dsh task exceeded its timeout and was terminated")
        if outcome.status == "stopped":
            return self._receipt(
                request, "cancelled", None, "the dsh task was stopped by the runner")
        if outcome.output_truncated:
            # The headless transport answers on stdout. A stream that overran the
            # capture bound was not read to its end, so whatever the exit code
            # says, this build did not see the answer -- and a bounded reader that
            # called that success would be lying about what it observed.
            return self._receipt(
                request, "failed", None,
                "the dsh task wrote past the capture bound, so its result was "
                "never read whole and no success can be claimed for it")
        if outcome.exit_code == 0:
            return self._receipt(
                request, "succeeded", 0,
                "the dsh task was observed to exit zero; that is an observation of "
                "the process only, it is not a verification of the work, and this "
                "build cannot turn it into one")
        return self._receipt(
            request, "failed", outcome.exit_code,
            "the dsh task was observed to exit non-zero")

    def _receipt(
            self, request: ActionRequest, observed: str, exit_code: int | None,
            detail: str) -> ActionResultReceipt:
        """The one receipt funnel, so an undiscarded home cannot escape unsaid."""
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome=observed,
            observed_at=self._clock(),
            detail=detail + RETAINED_DETAIL if self._retained else detail,
            exit_code=exit_code)

    # -- verification: independent workspace evidence only ----------------------

    def verify(
            self, request: ActionRequest, result: ActionResultReceipt,
    ) -> AdapterVerification:
        """Read independent workspace evidence, and claim nothing it cannot back.

        ``unavailable`` is never returned from here: that token says an adapter
        exposes NO verifier, and this one HAS one. Both answers now land on
        ``verification_failed``, so borrowing it would buy nothing and would
        still misreport which of the two happened. Absence of proof is
        ``error``.
        """
        if not isinstance(request, ActionRequest) or not isinstance(
                result, ActionResultReceipt):
            raise DshHarnessError("verify needs a validated request and result")
        attempt = self._attempts.get(request.action_id)
        if attempt is None:
            return self._verification(
                request, "error", (),
                "this adapter holds no pre-task snapshot for the action, so there "
                "is no independent evidence to read; absence of proof is not "
                "absence of a verifier and is never an observed success")
        failed = False
        try:
            after = self._workspace.digest_work_tree()
        except WorkspaceNotContained:  # noqa: BLE001 -- carry no path onward
            failed = True
            after = {}
        if failed:
            return self._verification(
                request, "error", (),
                "the authorized work tree does not stand on a contained route, so "
                "no independent evidence could be read from it")
        return self._read_change(request, attempt, after)

    def _read_change(
            self, request: ActionRequest, attempt: "_Attempt",
            after: Mapping[str, str]) -> AdapterVerification:
        """Judge the snapshot difference. No ``verified``, and no minted id.

        This build writes no durable ``EvidenceRef``, and an evidence identifier
        with no durable record behind it is a claim about evidence that does not
        exist -- which is why none is minted here rather than minted and then
        rejected downstream.
        """
        changed = _changed(attempt.before, after)
        if not changed:
            return self._verification(
                request, "error", (),
                "the dsh task changed nothing under the authorized work tree, so "
                "there is no independent evidence that it did the work")
        scope = f"{attempt.work_dir.name}/"
        outside = [name for name in changed if not name.startswith(scope)]
        if outside:
            return self._verification(
                request, "mismatch", (),
                f"{len(outside)} changed path(s) lie outside the action's "
                f"authorized work subtree")
        return self._verification(
            request, "error", (),
            f"{len(changed)} file(s) changed inside the action's authorized work "
            f"subtree, but this build writes no durable evidence record for them, "
            f"so no verified success may be claimed on their account")

    def _verification(
            self, request: ActionRequest, state: str, refs: tuple[str, ...],
            detail: str) -> AdapterVerification:
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state=state, observed_at=self._clock(), detail=detail, evidence_refs=refs)

    # -- the owned subtrees -----------------------------------------------------

    def _mint_home(self) -> Path:
        """A FRESH home per spawn, named by a freshly minted causal id."""
        return self._workspace.mint_home(self._ids("dsh-home"))
