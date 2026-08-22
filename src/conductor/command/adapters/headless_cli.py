"""One headless CLI task per authorized action, for any vendor's one-shot tool.

Five products in the December Command roster expose the same shape: a binary
that takes one prompt, runs it without a TUI, streams to stdout and exits. What
differs between them is a handful of vendor FACTS -- the flag that starts a
one-shot run, the environment name that relocates a profile home, the switch
that turns telemetry off, the version the build was reviewed against -- and one
structural fact, whether the operator pins one executable or an interpreter and
the entrypoint it runs.

Everything else is identical, and it is the part that is dangerous: minting a
fresh home per spawn and taking it back, claiming an action before the child
exists so a crash cannot run the work twice, proving the pinned build's exact
version before any task is spawned, bounding and draining raw child output so it
reaches no receipt, journal, API or evidence, and reading verification from
independent workspace evidence rather than from what the child said. Copied per
provider, a fix to any of those is a fix that has to be made five times and will
eventually be made four.

So it lives here once, and a provider is a PROFILE plus two small methods:

- ``_argv_prefix`` -- what the operator's pin contributes to argv;
- ``_task_argv`` -- where the vendor's flags put the prompt.

This module is PROVIDER-NEUTRAL and names no product. It compares no provider
id, so the identity gate has nothing to permit here; each concrete adapter is a
subclass in its own module, which is what makes ``adapter_class.__module__``
still name one provider's own file.

What the base refuses to decide for a provider is as important as what it does
decide. It will not guess a version, invent a flag, or read an exit code as more
than an observation that a process ended -- and where a vendor publishes no exit
code contract at all, the profile says so and every receipt says so with it.
Exit zero buys ``execution_observed`` and never success; verification is a
separate seam that reads only files that actually changed under the action's own
authorized subtree, and it never answers ``verified`` while this build writes no
durable evidence record. The day an evidence writer lands, what changes a
terminal state is the EVIDENCE; it is never the exit code.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..contracts import ActionRequest, ActionResultReceipt
from .harness_profile import (
    DISPATCH_CAPABILITY,
    OUTPUT_LIMIT,
    VERSION_TIMEOUT_SECONDS,
    ExecutablePin,
    HarnessProfile,
    HeadlessCliError,
    is_absolute,
    reviewed_env_allow,
    reviewed_pin_path,
)
from .base import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
    UnsupportedCapability,
)
from .deep_commands import DeepDispatchArgs
from .harness_workspace import (
    WORK_DIR,
    HarnessWorkspace,
    WorkspaceNotContained,
)
from .process import (
    STDIN_INCOMPLETE,
    CommandSpec,
    ProcessOutcome,
    ProcessRunner,
    ProcessRunnerError,
)


#: Every sentence below names the product, so each is built from the profile's
#: nouns rather than written twice. The WORDING is the approved wording: a
#: refactor may move a promise, and may not reword one.


def uncontained_detail(tool: str) -> str:
    """A refused route, carrying no path and no child detail.

    The route is operator state, and naming it here would put it in a receipt,
    the journal and the API at once.
    """
    return (f"a name on the {tool} workspace's own writable route is not locally "
            "contained, so nothing was minted, claimed or spawned")


def residue_detail(tool: str) -> str:
    """The home root holds state this build did not mint and may not delete.

    It carries no name and no count: the residue is operator state, and the
    operator reads it from the disk, not from a receipt.
    """
    return (f"the {tool} home root holds state this build did not mint and may "
            "not delete, so nothing was preflighted, claimed or spawned; a "
            "dispatch runs again once an operator has cleared it")


#: The PREFLIGHT's own home outlived the version spawn. The version answered,
#: but the retention promise is already broken inside this dispatch, so the task
#: never starts on top of it. Product-neutral as written, so it stays a constant.
PREFLIGHT_RESIDUE_DETAIL = (
    "the version preflight could not take back the home it minted, so this "
    "dispatch stopped before claiming or spawning the task")


def retained_detail(tool: str) -> str:
    """Appended to whatever a receipt already says when a home outlived its spawn.

    It never replaces the observed outcome it accompanies: a cleanup that did
    not happen is a second fact about the attempt, not a different result.
    """
    return (" an attempt home could not be discarded and was left standing, so "
            "the next dispatch is blocked until an operator has cleared the "
            f"{tool} home root")


def flagless(
        token: str, what: str, launcher_noun: str,
        error: type[HeadlessCliError]) -> str:
    """Prove one argv token cannot be read by a launcher as its own flag.

    A launcher parses the flags it owns and treats an unrecognized token as the
    start of what it passes through. A token that begins with ``-`` is therefore
    the whole injection surface: a flag in a task position would be consumed by
    the launcher rather than passed through as text. Contract identifiers cannot
    begin with ``-`` by their own grammar; this proves it at the argv boundary
    anyway, because that is where the consequence lives.
    """
    if type(token) is not str or not token.strip():
        raise error(f"{what} must be a non-empty task token")
    if "\x00" in token:
        raise error(f"{what} must not contain NUL")
    if token.startswith("-"):
        raise error(
            f"{what} would be read by the {launcher_noun} as one of its own flags")
    return token


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
    """The evidence PAIR one execute read, so verify judges values, not the tree.

    Both snapshots are taken inside the workspace turn, around the spawn. That is
    the whole reason ``after`` is carried here instead of being re-read later: the
    turn is the only window in which the shared work tree is this dispatch's
    alone, and a verification that re-read the tree afterwards would be judging a
    tree a neighbouring provider may have changed in the meantime. What is judged
    must be what was read.

    ``after`` is None when the tree could not be read on a contained route at
    all. That is told apart from an empty reading, because "nothing changed" and
    "the route refused" are different answers.
    """

    work_dir: Path
    before: Mapping[str, str]
    after: Mapping[str, str] | None


class HeadlessCliTransport:
    """Run one headless task per authorized action, and prove nothing more.

    A concrete provider subclasses this in its OWN module, sets ``profile``, and
    implements the two methods that carry its vendor's argv shape. Everything
    below is the part that must not differ between providers.
    """

    #: Set by each concrete provider module.
    profile: HarnessProfile
    #: The provider's own refusal type. A provider that did not set one would
    #: refuse as the base class, and every caller naming its specific error
    #: would stop catching it -- so the default is the base only for a
    #: transport nobody has specialized yet.
    error: type[HeadlessCliError] = HeadlessCliError
    #: Derived from that profile below, and derived rather than declared on
    #: purpose. The registration door re-reads this mapping FROM THE CLASS and
    #: compares it as a whole against the catalog entry's declared relation, so
    #: a class free to spell it itself is a class free to bind a schema to a
    #: control its own profile does not carry. One source, one capability.
    argument_schemas: dict[str, str] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        profile = cls.__dict__.get("profile")
        if isinstance(profile, HarnessProfile):
            cls.argument_schemas = {profile.capability: "deep-arguments-v1"}

    def __init__(
            self, runner: ProcessRunner, *, root: str | Path,
            clock: Callable[[], str], ids: Callable[[str], str],
            adapter_id: str) -> None:
        if not isinstance(runner, ProcessRunner):
            raise self.error(
                "a headless transport spawns only through an owned runner")
        profile = self.profile
        self.manifest = AdapterManifest(
            adapter_id=adapter_id, display_name=profile.display_name,
            vendor=profile.vendor, version=profile.reviewed_version,
            capabilities=("observe", profile.capability),
            docs_url=profile.docs_url)
        self._runner = runner
        self._workspace = HarnessWorkspace.at(
            root, home_dir=profile.home_dir, marker_dir=profile.marker_dir)
        self._root = self._workspace.root
        self._clock = clock
        self._ids = ids
        self._attempts: dict[str, _Attempt] = {}
        #: How many homes this dispatch could not discard. A COUNT, never a
        #: name: the number is what a receipt may say, the name is operator
        #: state. It is re-derived per dispatch, because the standing residue
        #: itself is what the next sweep reads.
        self._retained = 0

    # -- what a provider brings ------------------------------------------------

    def _argv_prefix(self) -> tuple[str, ...]:
        """What the operator's pin contributes to argv, before any code-owned flag."""
        raise NotImplementedError

    def _task_argv(self, task_text: str) -> tuple[str, ...]:
        """Where this vendor's flags put the one prompt, all tokens code-owned."""
        raise NotImplementedError

    # -- observation: no probe, no spawn, no claim ------------------------------

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation:
        return AdapterObservation(
            adapter_id=self.manifest.adapter_id, instance_id=instance_id,
            run_id=run_id, observed_at=self._clock(), health="unknown",
            available_capabilities=(),
            detail=f"the {self.profile.tool_noun} harness adapter never probes "
                   "the machine; whether the pinned build answers is unknown "
                   "until a dispatch preflights it")

    # -- preparation: read the closed body, mint no command yet -----------------

    def prepare(self, request: ActionRequest) -> PreparedAction:
        if not isinstance(request, ActionRequest):
            raise self.error("request must be a validated ActionRequest")
        capability = self.profile.capability
        if request.capability != capability:
            raise UnsupportedCapability(
                f"the {self.profile.tool_noun} harness adapter only prepares "
                f"{capability!r}, not {request.capability!r}")
        args = self._dispatch_args(request.arguments)
        # The payload echoes the validated identifiers ONLY. No argv, no cwd, no
        # env value and no pinned path is carried here, so nothing downstream can
        # rewrite the command by rewriting the payload.
        return PreparedAction(
            adapter_id=self.manifest.adapter_id, request=request,
            adapter_payload=args.as_dict())

    def _dispatch_args(self, arguments: object) -> DeepDispatchArgs:
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
            raise self.error(
                "dispatch arguments do not match the closed deep dispatch schema")
        assert args is not None
        return args

    def _task_text(self, args: DeepDispatchArgs, instruction: str) -> str:
        """A code-owned frame, then the MATERIALIZED instruction the user asked for.

        The frame is written here from identifiers the request validated, and it
        stands FIRST so that no byte of the instruction can occupy a launcher's
        flag position; ``flagless`` proves that at the argv boundary anyway. The
        instruction itself is the task, read by the workspace door from one
        contained file -- a dispatch that could not read it never reaches this
        method, because a sentence built from the reference alone is not the
        user's task and dispatching it would be a lie about what the child was
        asked to do.
        """
        refs = " ".join(args.artifact_refs) or "none"
        return flagless(
            f"conduct work item {args.work_item_id} under the {args.profile} "
            f"profile over artifacts {refs}. instruction "
            f"{args.instruction_ref} reads:\n{instruction}",
            "task text", f"{self.profile.tool_noun} launcher", self.error)

    # -- execution: preflight, mark, spawn once ---------------------------------

    def execute(self, prepared: PreparedAction) -> ActionResultReceipt:
        """Dispatch one task, or refuse; an uncontained route reaches no child.

        Every workspace road below can refuse, and a refusal is reported as this
        transport's own fixed sentence rather than as the door's: the door's
        message names the exact path it refused, which is operator state and has
        no business in a receipt, the journal or the API.

        The dispatch runs while this adapter OWNS its workspace root. One
        adapter serves every worker bound to it, so without that turn two
        dispatches share one tree and one ``_retained`` count: a neighbour's
        fresh dispatch resets the record of a cleanup this one could not do, and
        this one then spawns its task over the home it was told about and no
        longer remembers.
        """
        if not isinstance(prepared, PreparedAction):
            raise self.error("execute requires a validated PreparedAction")
        request = prepared.request
        args = self._dispatch_args(prepared.adapter_payload)
        with self._workspace.owned():
            failed = False
            try:
                return self._dispatch(request, args)
            except WorkspaceNotContained:  # noqa: BLE001 -- carry no path onward
                failed = True
            if failed:
                return self._receipt(
                    request, "failed", None,
                    uncontained_detail(self.profile.tool_noun))
        raise self.error("unreachable")

    def _dispatch(
            self, request: ActionRequest,
            args: DeepDispatchArgs) -> ActionResultReceipt:
        """Claim-check, materialize, sweep, preflight, then spawn exactly once.

        The sweep guards state this dispatch INHERITED; the check after the
        preflight guards state this dispatch just made. Both are the same rule:
        a task never runs over a home that outlived its spawn, whether somebody
        else left it or the version probe did.
        """
        self._retained = 0
        if self._workspace.is_claimed(request.action_id):
            # A marker already claims this action: an earlier attempt reached the
            # spawn. Whether it finished is genuinely unknown, and guessing would
            # be worse than saying so -- but running the task twice is not an
            # option, so this returns without spawning anything.
            return self._receipt(
                request, "unknown", None,
                "a marker from an earlier attempt already claims this action; "
                f"the {self.profile.task_noun} is never repeated after a crash")
        instruction = self._workspace.read_instruction(args.instruction_ref)
        # A home a crashed attempt left behind is model text this build promised
        # not to retain, so it goes before this attempt mints its own. What the
        # sweep could NOT take is the whole reason this dispatch stops: state of
        # unknown ownership under the home root is either somebody else's or the
        # residue of a cleanup that failed, and running a task over either would
        # be building on a promise this build has already broken once.
        if self._workspace.sweep_homes():
            return self._receipt(
                request, "failed", None, residue_detail(self.profile.tool_noun))
        preflight = self._preflight(request)
        if preflight is not None:
            return preflight
        if self._retained:
            # The version answered, and then its own home would not go. Counting
            # that in the receipt was never enough: the promise is broken NOW,
            # inside this dispatch, and the task is the one thing that must not
            # be built on top of it. Nothing is claimed and nothing is spawned.
            return self._receipt(
                request, "failed", None, PREFLIGHT_RESIDUE_DETAIL)
        work = self._workspace.work_dir(args.work_item_id)
        before = self._workspace.digest_work_tree()
        self._workspace.claim(request.action_id)
        outcome = self._attempt(
            self._task_argv(self._task_text(args, instruction)),
            f"{WORK_DIR}/{args.work_item_id}", timeout=request.timeout_seconds)
        self._attempts[request.action_id] = _Attempt(
            work_dir=work, before=before, after=self._evidence())
        return self._observed(request, outcome)

    def _evidence(self) -> Mapping[str, str] | None:
        """One reading of the authorized work tree, or None if it refused.

        Called while the dispatch still HOLDS its workspace turn, and that
        placement is the whole point. The turn is the only window in which this
        dispatch owns the shared work tree: the runtime serializes on
        ``(run_id, action_id)``, so a neighbouring provider's entire dispatch can
        land between ``execute`` returning and ``verify`` being called. A
        verification that re-read the tree then charged this child with a change
        outside its own subtree that another provider had made.

        A refusal here must not rewrite what the spawn did: the dispatch already
        happened and its observed outcome is a fact. So the refusal is carried
        as an absent reading and reported by ``verify``, which is the seam whose
        job is to say what evidence there is.
        """
        try:
            return self._workspace.digest_work_tree()
        except WorkspaceNotContained:  # noqa: BLE001 -- carry no path onward
            return None

    def _preflight(self, request: ActionRequest) -> ActionResultReceipt | None:
        """Prove the pinned build's EXACT version, or refuse before any task runs."""
        profile = self.profile
        self._workspace.work_root()
        outcome = self._attempt(
            profile.version_argv, WORK_DIR,
            timeout=min(profile.version_timeout_seconds, request.timeout_seconds))
        if outcome.status != "completed" or outcome.exit_code != 0:
            return self._receipt(
                request, "failed", None,
                f"the pinned {profile.tool_noun} build did not answer a "
                "version preflight, so no task was spawned")
        if not self._version_matches(outcome.output):
            # The observed token is NOT reported: it is raw child output, and a
            # hostile build could put a secret where a version belongs.
            return self._receipt(
                request, "failed", None,
                f"the pinned {profile.tool_noun} build is not the reviewed "
                f"{profile.reviewed_version} this adapter was written against, "
                f"so no task was spawned")
        return None

    def _attempt(
            self, argv: tuple[str, ...], cwd: str, *,
            timeout: int | float) -> ProcessOutcome:
        """One spawn inside one FRESH home, and the home goes when the spawn does.

        This is the whole of the retention promise: a real harness may write
        prompt, session, tool output and model text under its home, and nothing
        here ever reads a byte of it, so the honest lifetime of that state is
        exactly the lifetime of the spawn. The discard runs on every road out,
        including a raise. A home this door may NOT delete -- one holding a name
        whose kind it cannot establish -- is left standing rather than guessed
        at, and the next dispatch's sweep refuses over it rather than deleting
        through it.
        """
        home = self._mint_home()
        try:
            return self._spawn(argv, home, cwd, timeout=timeout)
        finally:
            self._discard(home)

    def _discard(self, home: Path) -> None:
        """Discard one attempt home, or COUNT the failure; never raise, never hide.

        This runs in a ``finally``, so raising here would replace whatever the
        spawn did with a cleanup error. Swallowing the refusal is worse: the home
        survives, the next dispatch runs anyway, and the retention promise is
        silently broken. The refusal is counted instead, so every receipt this
        dispatch goes on to build states it alongside its own outcome, and the
        standing home stops the next dispatch at the sweep.
        """
        try:
            self._workspace.discard_home(home)
        except (WorkspaceNotContained, OSError):  # noqa: BLE001 -- no path onward
            self._retained += 1

    def _spawn(
            self, argv: tuple[str, ...], home: Path, cwd: str, *,
            timeout: int | float) -> ProcessOutcome:
        """The ONE place a child is started; argv, env and bounds are code-owned.

        ``cwd`` is a route RELATIVE to the project root, so the runner's own
        containment walk -- which refuses a symlink, a junction, a ``..`` segment
        or anything not strictly beneath the root -- is what decides where the
        child may stand. No transport here ever hands it an absolute path.
        """
        profile = self.profile
        failed = False
        try:
            # Building the spec is part of the spawn: a pin that cannot become a
            # valid argv must refuse with the SAME fixed sentence as a spawn that
            # cannot start, so no runner message and no path leaks through here.
            spec = CommandSpec(
                argv=(*self._argv_prefix(), *argv), cwd=cwd,
                env_allow=self._env_allow(),
                # The minted home is written LAST so it cannot be
                # displaced. A `forced_env` pair naming `home_env`
                # would otherwise relocate the child's home and
                # defeat the whole retention promise; the profile
                # refuses that collision at construction, and this
                # ordering means the promise holds even if it did not.
                env={**dict(profile.forced_env),
                     profile.home_env: str(home)},
                output_limit=profile.output_limit, timeout_seconds=timeout)
            return self._runner.run(spec)
        except ProcessRunnerError:  # noqa: BLE001 -- carry no child detail onward
            failed = True
        if failed:
            raise self.error(
                f"the {self.profile.tool_noun} harness could not start the "
                "pinned build") from None
        raise self.error("unreachable")

    def _env_allow(self) -> tuple[str, ...]:
        """The operator's environment allowlist, from this provider's own pin."""
        raise NotImplementedError

    def _version_matches(self, output: bytes) -> bool:
        """Whether the pinned build's version print IS the reviewed version.

        A BOOLEAN, and deliberately: the observed bytes are raw child output, so
        nothing derived from them may be returned to a caller or reach a receipt.
        A hostile build could put a secret where a version belongs.

        The default is an exact compare of the whole first non-empty line, which
        is right for a tool that prints the number and nothing else. A vendor that
        prints a richer form overrides this and PARSES it -- see
        ``grok_build.py``, where the published form carries the program name and a
        short commit ALWAYS and a channel label often, and none of the three may
        ever be read as a version. Which parts of such a form are optional is a
        fact about the vendor's entry point, so an override that guesses at it
        either refuses every real install or admits an executable that is none.
        """
        return _version_token(output) == self.profile.reviewed_version

    def _observed(
            self, request: ActionRequest,
            outcome: ProcessOutcome) -> ActionResultReceipt:
        """Report what was OBSERVED. Exit zero is an observation, not a success."""
        noun = self.profile.task_noun
        if outcome.status == "timed_out":
            return self._receipt(
                request, "failed", None,
                f"the {noun} exceeded its timeout and was terminated")
        if outcome.status == "stopped":
            return self._receipt(
                request, "cancelled", None,
                f"the {noun} was stopped by the runner")
        if outcome.stdin_state == STDIN_INCOMPLETE:
            # The mirror image of the capture bound below, and the earlier of the
            # two failures: there the answer was not read whole, here the QUESTION
            # was not delivered whole. A provider that takes its task on stdin and
            # exits zero without having received it has reported honestly about
            # something else, and no exit code can repair that. Checked before the
            # capture bound because a task never posed makes the answer moot.
            return self._receipt(
                request, "failed", None,
                f"the {noun} was never handed its whole instruction, so nothing "
                "it did can be read as an attempt at the one that was asked")
        if outcome.output_truncated:
            # The headless transport answers on stdout. A stream that overran the
            # capture bound was not read to its end, so whatever the exit code
            # says, this build did not see the answer -- and a bounded reader that
            # called that success would be lying about what it observed.
            return self._receipt(
                request, "failed", None,
                f"the {noun} wrote past the capture bound, so its result was "
                "never read whole and no success can be claimed for it")
        if outcome.exit_code == 0:
            return self._receipt(request, "succeeded", 0, self._zero_detail())
        return self._receipt(
            request, "failed", outcome.exit_code,
            f"the {noun} was observed to exit non-zero")

    def _zero_detail(self) -> str:
        """What an exit of zero is allowed to mean, given what the vendor published.

        Both readings end in the same place -- an observation of the process and
        never a verification of the work -- but they do not start in the same
        place, and a receipt that flattened them would overstate the weaker one.
        A vendor that documents no exit-code contract for its one-shot mode has
        not told this build what a zero means at all.
        """
        noun = self.profile.task_noun
        if self.profile.exit_codes_published:
            return (
                f"the {noun} was observed to exit zero; that is an observation "
                "of the process only, it is not a verification of the work, and "
                "this build cannot turn it into one")
        return (
            f"the {noun} was observed to exit zero; the vendor publishes no "
            "exit-code contract for this mode, so the code is read as the "
            "process having ended and as nothing else. It is not a verification "
            "of the work, and this build cannot turn it into one")

    def _receipt(
            self, request: ActionRequest, observed: str, exit_code: int | None,
            detail: str) -> ActionResultReceipt:
        """The one receipt funnel, so an undiscarded home cannot escape unsaid."""
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome=observed,
            observed_at=self._clock(),
            detail=(detail + retained_detail(self.profile.tool_noun)
                    if self._retained else detail),
            exit_code=exit_code)

    # -- verification: independent workspace evidence only ----------------------

    def verify(
            self, request: ActionRequest, result: ActionResultReceipt,
    ) -> AdapterVerification:
        """Judge the evidence pair the dispatch read, and claim nothing beyond it.

        This seam does NOT read the filesystem. Both snapshots were taken inside
        the dispatch's workspace turn, and re-reading the tree here would judge a
        tree a neighbouring provider may have changed since -- which is exactly
        the defect that made this a correction. What is judged is what was read.

        ``unavailable`` is never returned from here: that token says an adapter
        exposes NO verifier, and this one HAS one. Both answers land on
        ``verification_failed``, so borrowing it would buy nothing and would
        still misreport which of the two happened. Absence of proof is ``error``.
        """
        if not isinstance(request, ActionRequest) or not isinstance(
                result, ActionResultReceipt):
            raise self.error("verify needs a validated request and result")
        attempt = self._attempts.get(request.action_id)
        if attempt is None:
            return self._verification(
                request, "error", (),
                "this adapter holds no pre-task snapshot for the action, so there "
                "is no independent evidence to read; absence of proof is not "
                "absence of a verifier and is never an observed success")
        if attempt.after is None:
            return self._verification(
                request, "error", (),
                "the authorized work tree does not stand on a contained route, so "
                "no independent evidence could be read from it")
        return self._read_change(request, attempt, attempt.after)

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
                f"the {self.profile.task_noun} changed nothing under the "
                "authorized work tree, so there is no independent evidence that "
                "it did the work")
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
            state=state, observed_at=self._clock(), detail=detail,
            evidence_refs=refs)

    # -- the owned subtrees -----------------------------------------------------

    def _mint_home(self) -> Path:
        """A FRESH home per spawn, named by a freshly minted causal id.

        The id KIND comes from the provider. The extraction briefly made it the
        neutral ``harness-home`` for everyone, which silently renamed dsh's
        on-disk attempt directories -- a change of an observable, in a commit
        whose whole claim was that no observable changed. It is also worth more
        than tidiness: an operator reading the home root sees which provider left
        an attempt behind, and one shared kind would have told them nothing.
        """
        return self._workspace.mint_home(self._ids(self.profile.home_id_kind))
