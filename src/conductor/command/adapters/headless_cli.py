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

So it lives here once, and a provider is a PROFILE plus two small methods. WHICH
two is decided by the profile's ``task_channel``, a closed choice of ``argv`` or
``stdin``, and that is structural rather than advisory:

- ``_argv_prefix`` -- what the operator's pin contributes to argv, on either
  channel;
- on the ``argv`` channel, ``_task_argv(task_text)`` -- where the vendor's flags
  put the prompt;
- on the ``stdin`` channel, ``_stdin_argv(home, model)`` and
  ``_task_stdin(task_text)``. The argv builder there takes NO task argument,
  which is the whole guarantee that no byte of an operator's instruction can
  reach a command line any process lister on the machine can read. An earlier
  version tried to CHECK that instead, by calling one builder twice with probe
  texts and comparing; a review probe defeated it in one line. Two observations
  are not independence, and an absent parameter is.

  The two things it IS handed are the attempt home minted for the spawn it is
  building -- a vendor may be asked to write an artefact into its own profile
  home, and nobody but the transport knows where that home is -- and the model
  the run's frozen configuration pinned for the instance, which is a deployment
  fact this module never learns the value of;
- ``_read_attempt_home(home)``, where a provider that asked for such an artefact
  reads it, after the spawn and before the home is discarded. The base names no
  artefact and reads nothing.

MODEL ROUTING lives next door in ``headless_routing``, mixed in below. This
module carries the routed value from ``PreparedAction`` to the argv builder and
learns nothing about it on the way.

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
authorized subtree. This base still mints no evidence and cannot answer
``verified``. ``ArtifactAwareTransport`` is the explicit outer seam that may
append a durable EvidenceRef; what changes a terminal state is that EVIDENCE,
never the exit code.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from ..contracts import ActionRequest, ActionResultReceipt
from .harness_profile import (
    DISPATCH_CAPABILITY,
    LOGIN_RESIDUE_DETAIL,
    OUTPUT_LIMIT,
    PREFLIGHT_LOGIN_RESIDUE_DETAIL,
    PREFLIGHT_RESIDUE_DETAIL,
    TASK_CHANNEL_STDIN,
    VERSION_TIMEOUT_SECONDS,
    ExecutablePin,
    HarnessProfile,
    HeadlessCliError,
    bounded_output,
    is_absolute,
    residue_detail,
    reviewed_env_allow,
    reviewed_pin_path,
    uncontained_detail,
)
from .base import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
    UnsupportedCapability,
)
from .deep_commands import OUTPUT_LIMIT_BYTES, DeepDispatchArgs
from .harness_workspace import (
    WORK_DIR,
    HarnessWorkspace,
    WorkspaceNotContained,
)
from . import login_home
from .headless_login import LoginRoad
from .headless_receipts import ReceiptWriting
from .headless_routing import ModelRouting
from .task_binding import (
    InstructionBinding, InstructionChanged, composed_task_text, promised_bytes)
from .headless_values import (
    ArgvSource,
    _Attempt,
    _changed,
    _version_token,
    attempt_relation,
)
from .process import (
    CommandSpec,
    ProcessOutcome,
    ProcessRunner,
    ProcessRunnerError,
)


class HeadlessCliTransport(
        ReceiptWriting, ModelRouting, LoginRoad, InstructionBinding):
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
        if profile.task_channel == TASK_CHANNEL_STDIN:
            # A profile can DECLARE the stdin channel; only the class can honour
            # it. Refusing here rather than at the first dispatch is the same
            # rule the profile itself follows: a code-owned mistake is caught
            # before an operator's run is standing on it.
            kind = type(self)
            for seam in ("_stdin_argv", "_task_stdin"):
                if getattr(kind, seam) is getattr(HeadlessCliTransport, seam):
                    raise self.error(
                        f"this provider's task travels by stdin, so it owes its "
                        f"own {seam}")
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
        #: Filed under the FULL attempt relation, never under an action id
        #: alone: one adapter serves every worker bound to its root, and an
        #: action id repeats across runs. See `attempt_relation`.
        self._attempts: dict[tuple[str, str, str, str], _Attempt] = {}
        #: How many homes this dispatch could not discard. A COUNT, never a
        #: name: the number is what a receipt may say, the name is operator
        #: state. It is re-derived per dispatch, because the standing residue
        #: itself is what the next sweep reads.
        self._retained = 0
        #: How many spawns left a name in a PERSISTENT login directory that no
        #: declaration accounts for. A count for the same reason: the names are
        #: an operator's own state, and one of them is a credential.
        self._login_residue = 0
        #: The three login facts one road carries; see `LoginRoad` for each.
        self._login_echo = False
        self._login_history: dict[tuple[str, str, str, str], tuple[bytes, ...]] = {}
        self._login_seen: tuple[bytes, ...] = ()

    # -- what a provider brings ------------------------------------------------

    def _argv_prefix(self) -> tuple[str, ...]:
        """What the operator's pin contributes to argv, before any code-owned flag."""
        raise NotImplementedError

    def _task_argv(self, task_text: str) -> tuple[str, ...]:
        """Where this vendor's flags put the one prompt, all tokens code-owned."""
        raise NotImplementedError

    def _stdin_argv(self, home: Path, model: str | None) -> tuple[str, ...]:
        """The code-owned flags of a provider whose task travels by STDIN.

        It takes NO task argument, and that is the entire guarantee. Not a
        promise the author kept, not a check the transport runs afterwards: an
        argv builder on this channel cannot put an instruction in the command
        line because it is never handed one, and a build that tried would fail
        to call this at all.

        What replaced: a version of this seam asked ``_task_argv`` twice with
        probe texts and compared the answers. A review probe defeated it in one
        line -- return a constant for both probes, embed the real instruction
        for anything else -- and the guard reported the argv safe while the
        operator's task rode it. Two observations were never independence.

        ``home`` is the attempt home minted for the spawn being built. A
        provider whose vendor writes an artefact into its own profile home has
        to name that path on the command line, and the path does not exist until
        ``_attempt`` mints it. It is not a road back to the task and cannot
        become one: ``_task_command`` returns this method UNCALLED, so no caller
        can curry a task into it, and ``_spawn`` -- its one call site -- passes
        the value ``_mint_home`` returned, which is a project subtree named by a
        freshly minted id and has never been near an instruction. A provider
        that needs nothing from the home ignores it, as Claude Code does.

        ``model`` is the id the run's frozen configuration pinned for the
        instance this action names, or None. It is a PARAMETER for the same
        reason the task is absent: one adapter instance serves every worker
        bound to its root, so a field remembering the attempt in flight is a
        field the next attempt can read, and a value that arrives through the
        call cannot outlive it. A provider turns it into tokens with
        ``_model_argv`` and decides WHERE they stand, because that is a fact
        about its vendor's command line and not about this transport.
        """
        raise NotImplementedError

    def _task_stdin(self, task_text: str) -> bytes:
        """The bytes a STDIN-channel provider hands the child, and its whole task.

        Only ever called for ``task_channel == "stdin"``. A provider on the argv
        channel never reaches here and never opens a pipe: its spawn is the
        DEVNULL spawn it had before either seam existed.
        """
        raise NotImplementedError

    def _read_attempt_home(self, home: Path) -> None:
        """Read whatever this provider asked its vendor to write into the home.

        Called after the spawn returned and before the home is discarded, and
        that placement is the whole reason the seam exists rather than being
        something a provider could do for itself. The home is deleted the
        instant ``_attempt`` returns -- that is the retention promise -- so a
        provider that put an output path inside it has exactly this window.

        The base names no artefact, knows of none, and reads nothing; a provider
        that asked for none never notices this. Nothing is returned, because a
        return value would have to travel back through code that must not learn
        what it is: an implementation keeps its own reading, in its own closed
        vocabulary, in its own module.

        An implementation must not RAISE. This runs on the road out of a spawn
        that already happened, so an exception here would replace what the child
        did with a reading error -- the same reason ``_discard`` counts its
        failures instead of raising them. What could not be established is
        reported by the provider as its own answer, not as an exception.
        """

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
        """The composed task: `task_binding` owns how those bytes are made."""
        return composed_task_text(
            args, instruction, self.profile.tool_noun, self.error)

    def _dispatch_task(
            self, request: ActionRequest, args: DeepDispatchArgs,
            instruction: str) -> str:
        """Materialize one dispatch task; subclasses may add durable inputs."""
        return self._task_text(args, instruction)

    def _instruction_text(
            self, request: ActionRequest, args: DeepDispatchArgs) -> str:
        """The instruction the child is asked to do: this base reads the file.

        One contained name under the workspace's instruction directory, or the
        refusal that reaches no child. A subclass with a durable road answers
        from the run's own journal first and falls back to exactly this.

        A proposal that promised these bytes gets them read as they stand; one
        that promised nothing gets the reading it has always had. The promise is
        what makes the difference, so the promise is what asks for it.
        """
        del request
        return self._workspace.read_instruction(
            args.instruction_ref, exact=promised_bytes(args))

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
        unroutable = self._unroutable(request, prepared.model)
        if unroutable is not None:
            return unroutable
        with self._workspace.owned():
            failed = False
            try:
                return self._dispatch(request, args, prepared.model)
            except InstructionChanged as changed:
                return self._receipt(request, "failed", None, str(changed))
            except WorkspaceNotContained:  # noqa: BLE001 -- carry no path onward
                failed = True
            finally:
                # Inside the turn, so a sibling road's own sample is never the
                # one dropped. What an attempt was given it keeps: this releases
                # the road's working set, not the attempt's.
                self._forget_login_sample()
            if failed:
                return self._receipt(
                    request, "failed", None,
                    uncontained_detail(self.profile.tool_noun))
        raise self.error("unreachable")

    def _already_claimed(self, request: ActionRequest):
        """A marker already claims this action, so nothing is spawned for it.

        An earlier attempt reached the spawn. Whether it finished is genuinely
        unknown, and guessing would be worse than saying so -- but running the
        task twice is not an option, so this answers `unknown` and stops.
        """
        if not self._workspace.is_claimed(request.run_id, request.action_id):
            return None
        return self._receipt(
            request, "unknown", None,
            "a marker from an earlier attempt already claims this action; "
            f"the {self.profile.task_noun} is never repeated after a crash")

    def _dispatch(
            self, request: ActionRequest, args: DeepDispatchArgs,
            model: str | None = None) -> ActionResultReceipt:
        """Claim-check, materialize, sweep, preflight, then spawn exactly once.
        The sweep guards state this dispatch INHERITED; the check after the
        preflight guards state this dispatch just made. Both are the same rule:
        a task never runs over a home that outlived its spawn, whether somebody
        else left it or the version probe did.
        """
        self._begin_road()
        claimed = self._already_claimed(request)
        if claimed is not None:
            return claimed
        instruction = self._bound_instruction(request, args)
        # A home a crashed attempt left behind is model text this build promised
        # not to retain, so it goes before this attempt mints its own. What the
        # sweep could NOT take is the whole reason this dispatch stops: state of
        # unknown ownership under the home root is either somebody else's or the
        # residue of a cleanup that failed, and running a task over either would
        # be building on a promise this build has already broken once.
        if self._workspace.sweep_homes():
            return self._receipt(
                request, "failed", None, residue_detail(self.profile.tool_noun))
        refused = self._preflight(request) or self._preflight_residue(request)
        if refused is not None:
            return refused
        task_text = self._dispatch_task(request, args, instruction)
        work = self._workspace.work_dir(args.work_item_id)
        before = self._workspace.digest_work_tree()
        self._workspace.claim(request.run_id, request.action_id)
        argv, payload = self._task_command(task_text)
        outcome = self._attempt(
            argv, f"{WORK_DIR}/{args.work_item_id}",
            timeout=request.timeout_seconds, stdin_bytes=payload, model=model,
            output_limit=OUTPUT_LIMIT_BYTES[args.output_limit_profile])
        self._attempts[attempt_relation(request)] = _Attempt(
            work_dir=work, before=before, after=self._evidence(),
            retained=bool(self._retained))
        self._keep_login_values(attempt_relation(request))
        if self._login_residue:
            # A task that ran and left state nobody declared in a directory this
            # build cannot clean has not met the promise it makes about that
            # directory. Reporting it as succeeded with a sentence appended
            # would leave the run's own record saying the opposite of the
            # sentence; the outcome is the answer, and this is not a success.
            return self._receipt(
                request, "failed", outcome.exit_code, LOGIN_RESIDUE_DETAIL)
        return self._observed(request, outcome)

    def _preflight_residue(
            self, request: ActionRequest) -> ActionResultReceipt | None:
        """What a preflight left behind in either directory, before a task runs.

        Counting it in the receipt was never enough. The promise is broken NOW,
        inside this dispatch, and the task is the one thing that must not be
        built on top of it: nothing is claimed and nothing is spawned. Two
        directories, two sentences, because a reader has to know which promise
        this dispatch could not keep.
        """
        if self._retained:
            return self._receipt(
                request, "failed", None, PREFLIGHT_RESIDUE_DETAIL)
        if self._login_residue:
            return self._receipt(
                request, "failed", None, PREFLIGHT_LOGIN_RESIDUE_DETAIL)
        return None

    def _task_command(self, task_text: str) -> tuple[ArgvSource, bytes | None]:
        """The argv SOURCE and the payload for this provider's channel, and only those.

        The channel is CLOSED and the profile already refused a third value, so
        these are the only two roads. Each builds its argv with exactly the
        arguments its own promise allows: on the stdin road the argv builder is
        never handed the task, which is what makes "no byte of an instruction
        reaches the command line" a fact about the signature rather than a
        property someone has to keep remembering.

        On that road the builder is handed over UNCALLED, and that is load
        bearing rather than a convenience: this method is the one place holding
        both the task and the builder, so calling it here -- even to pass
        nothing -- would be the one frame where a task could be curried in. It
        is called instead by ``_spawn``, which holds the minted home and has
        never seen ``task_text`` at all.
        """
        if self.profile.task_channel == TASK_CHANNEL_STDIN:
            return self._stdin_argv, self._task_stdin(task_text)
        return self._task_argv(task_text), None

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
        # BEFORE the version probe, not after it. Every spawn on this road --
        # the probe included -- is pointed at the login directory, and the
        # reviewed Codex writes into its home on every run, so a check that ran
        # after the probe would already have started a vendor inside a directory
        # this build had decided it may not point a spawn at.
        carried = self._login_home_refusal(request)
        if carried is not None:
            return carried
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
        return self._login_preflight(request)

    def _attempt(
            self, argv: ArgvSource, cwd: str, *,
            timeout: int | float,
            stdin_bytes: bytes | None = None,
            separate_stderr: bool = False,
            model: str | None = None,
            output_limit: int | None = None) -> ProcessOutcome:
        """One spawn inside one FRESH home, and the home goes when the spawn does.

        This is the whole of the retention promise: a real harness may write
        prompt, session, tool output and model text under its home, and nothing
        here ever reads a byte of it, so the honest lifetime of that state is
        exactly the lifetime of the spawn. The discard runs on every road out,
        including a raise. A home this door may NOT delete -- one holding a name
        whose kind it cannot establish -- is left standing rather than guessed
        at, and the next dispatch's sweep refuses over it rather than deleting
        through it.

        The ONE reading of that home a provider gets stands between the spawn
        and the discard, because after the discard there is nothing to read.
        """
        home = self._mint_home()
        # ONE source for "is there a login directory in play", so the before and
        # after measurements and the cleanup can never disagree about it.
        auth_home = self._signed_in_road()
        before = login_home.measure(auth_home, self.profile.login_scratch)
        self._login_echo = False
        self._remember_login_values()
        try:
            outcome = self._spawn(
                argv, home, cwd, timeout=timeout, stdin_bytes=stdin_bytes,
                separate_stderr=separate_stderr, model=model,
                output_limit=output_limit)
            self._read_attempt_home(home)
            # AFTER the spawn, and that is the whole point: a vendor refreshes
            # its own credential while it runs, so the values this build scanned
            # for before the spawn are not necessarily the ones the child could
            # have echoed. The runner's own flag answers for the first set; this
            # answers for the set the spawn left behind.
            self._login_echo = self._echoed_login(outcome.output)
            # AFTER as well as before: what the spawn left in the credential
            # file is what the NEXT reader would scan for, and what stood before
            # it is what this spawn could have written into a file.
            self._remember_login_values()
            return outcome
        finally:
            if auth_home:
                self._take_back_login(auth_home, before)
            self._discard(home)

    def _release_attempt(self, relation: tuple[str, str, str, str]) -> None:
        """Drop what ONE finished attempt left on this transport."""
        self._attempts.pop(relation, None)
        self._login_history.pop(relation, None)

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

    @staticmethod
    def _tokens(
            argv: ArgvSource, home: Path, model: str | None) -> tuple[str, ...]:
        """The child's own tokens: a ready argv, or the one its builder makes.

        The ONE place a stdin-channel builder is ever called, and it is called
        with the minted home, the routed model, and nothing else. There is no
        ``task_text`` in this frame to pass even by mistake.

        A READY tuple never sees the model, and that is the honest shape rather
        than an omission: the version preflight hands one, and a preflight that
        carried `--model` would be asking a build to load a model in order to
        print its own version.
        """
        return argv if type(argv) is tuple else argv(home, model)

    def _spawn(
            self, argv: ArgvSource, home: Path, cwd: str, *,
            timeout: int | float,
            stdin_bytes: bytes | None = None,
            separate_stderr: bool = False,
            model: str | None = None,
            output_limit: int | None = None) -> ProcessOutcome:
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
                argv=(*self._argv_prefix(),
                      *self._tokens(argv, home, model)), cwd=cwd,
                env_allow=self._env_allow(),
                # The minted home is written LAST so it cannot be
                # displaced. A `forced_env` pair naming `home_env`
                # would otherwise relocate the child's home and
                # defeat the whole retention promise; the profile
                # refuses that collision at construction, and this
                # ordering means the promise holds even if it did not.
                env={**dict(profile.forced_env),
                     profile.home_env: self._home_value(home)},
                output_limit=bounded_output(profile, output_limit),
                timeout_seconds=timeout,
                stdin_bytes=stdin_bytes, separate_stderr=separate_stderr,
                # The one road a value -- never a name -- crosses this seam: a
                # vendor login lives in a file, so the runner cannot derive it
                # from the environment the way it derives every other credential
                # this build hands a child.
                sensitive_extra=self._login_secrets())
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
        relation = attempt_relation(request)
        try:
            if not isinstance(request, ActionRequest) or not isinstance(
                    result, ActionResultReceipt):
                raise self.error("verify needs a validated request and result")
            attempt = self._attempts.get(relation)
            if attempt is None:
                return self._verification(
                    request, "error", (),
                    "this adapter holds no pre-task snapshot for the action, so "
                    "there is no independent evidence to read; absence of proof "
                    "is not absence of a verifier and is never an observed success")
            if attempt.after is None:
                return self._verification(
                    request, "error", (),
                    "the authorized work tree does not stand on a contained route, "
                    "so no independent evidence could be read from it")
            return self._read_change(request, attempt, attempt.after)
        finally:
            # EVERY road out, the raise included, and HERE rather than only in
            # the artifact-aware subclass: an adapter instance lives as long as
            # the server, so what one attempt leaves is a rate and not a bound,
            # and a promise that holds by inheritance holds until somebody
            # declines the inheritance. The login values go the same way for a
            # sharper reason -- they are credential bytes.
            self._release_attempt(relation)

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
