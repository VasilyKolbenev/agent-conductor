"""One spawn inside one fresh home: the attempt, and the road out of it.

Split out of ``headless_cli`` when that module reached its line cap, on the same kind of seam as
``headless_login``: that module holds WHICH directory a child is told about, this holds the one
circuit that starts the child and takes its state back. What a mixin needs from the class it is
mixed into is stated rather than assumed: ``profile``, ``error``, ``_runner``, ``_workspace``,
``_ids``, ``_argv_prefix``, ``_signed_in_road`` and the login-road methods, all of them
``HeadlessCliTransport``'s.

An attempt is either a TASK attempt (it carries a ``mode``, ``dispatch`` or ``review``) or a
preflight (it carries none: a version print, a login status, a quota read). Only a task attempt
reaches the execution boundary (R5, spec 10.6), because only a task attempt is handed a project
folder to change; the others get none, so they stay on the plain runner path.

A transport is CONFINED by ``confine``, once, by the door that builds it, and there is no way
back. From then on a task attempt starts only inside ``ProcessRunner.container_profile``, and
there is no second road: when the boundary is not provided the attempt is refused before the
home is minted, a login is borrowed or anything is created, and it never falls back to the plain
launch. The provider door confines every adapter it builds, for the host platform unless it is
told another (``providers.resolve_providers``), so a production harness is never started outside
the boundary. A transport built without that door, or by a door told ``confine_platform=None``,
launches as it did before R5: that is the harness fakes' launch, and the doors tell any plan
that this harness has no boundary (``AdapterRegistry.execution_boundary``). Its subscription
spawns, a task attempt included, stand on the real login directory, as they did before the relay.

A confined task attempt of a harness that has a relay (``HarnessProfile.login_relay``) is the
RELAYED attempt (``_relayed``): its home is a fresh relay home outside the project, and its
order is the one of ``relay_attempt``: lease, copy, boundary entered, claim, run. The claim is
therefore a CALLBACK of ``_attempt``, taken by the attempt itself at that moment; on every other
road ``_attempt`` takes it first, which is the order that existed before the relay.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ...ownership_errors import OwnerRefused
from ..boundary_entry import entry_call, entry_lends_relay_homes, entry_takes_the_call
from ..execution_boundary import (
    ATTEMPT_MODES, BoundaryUnavailable, boundary_provided, require_boundary)
from . import login_home
from .harness_profile import boundary_detail, subscription_boundary_detail
from .harness_workspace import WorkspaceNotContained
from .headless_spec import attempt_spec
from .headless_values import ArgvSource
from .login_lifetime import owned_login_attempt
from .process import CommandSpec, ProcessOutcome, ProcessRunnerError
from .process_boundary import WindowsContainer
from .process_profile import ProfileRefused
from .relay_attempt import CLAIM_REFUSALS, CarriedError, LaunchLost, NotStarted

#: The environment names a confined child cannot do without: the container cannot read the
#: user's profile, so each points at the attempt's own fresh ``runtime`` folder (H contract, 6).
RUNTIME_ENV = ("LOCALAPPDATA", "TEMP", "TMP")
#: What entering or leaving the boundary can raise that is not a ``ProcessRunnerError`` (H
#: contract, section 4). All of them become the transport's one fixed "could not start" error,
#: and none is ``BoundaryUnavailable``, which is judged earlier and separately.
LAUNCH_REFUSALS = (ProcessRunnerError, OSError, OwnerRefused, ProfileRefused)


@dataclass(frozen=True)
class AttemptFolders:
    """The product-owned folders one boundaried attempt may touch (H contract, section 3.2).

    The shape is H's; it stands here until the runner's own ``AttemptFolders`` merges, and then
    this class is replaced by that import. Nothing else about the call changes.

    Attributes:
        work: The route, relative to the project root, of the attempt's work folder.
        home: The route, relative to the project root, of its per-spawn home, or None. For a
            RELAYED attempt (``AttemptLaunch._relayed``) it is instead the ABSOLUTE path of its
            relay home, as text, and the runner judges it as one (``relay_home``).
        install: The ABSOLUTE folder that holds the pinned executable and what it loads.
    """

    work: str
    home: str | None
    install: str


#: The folder under which the owner's installs live, one folder per harness and one per version
#: beneath it: ``harnesses/<name>/<version>`` (H contract, section 5).
INSTALL_TREE = "harnesses"


def find_install_folder(pinned_file: str) -> str | None:
    """The version folder a pinned file is installed in: ``harnesses/<name>/<version>``, or None.

    That folder, and not the one the file sits in, is what the boundary must be able to read: for
    a native binary it is the same folder, but one build keeps its file deep in a vendor tree
    beside what it loads, and another keeps its dependencies in sibling folders of the one that
    holds the entry (measured, H probe of 14.10). The nearest folder that is a version folder of
    the install tree is taken, so the grant is the narrowest that follows the rule.

    A pure fact of the pin's path, so the doors read it before any claim: a file installed
    outside the tree has no install folder, and a guess would grant too little or too much.

    Args:
        pinned_file: The absolute file the child starts from.
    """
    for folder in Path(pinned_file).parents:
        if folder.parent.parent.name.casefold() == INSTALL_TREE:
            return str(folder)
    return None


def install_folder(pinned_file: str) -> str:
    """``find_install_folder``, for the call that cannot go on without one.

    Raises:
        ProcessRunnerError: The file is not installed under the tree.
    """
    found = find_install_folder(pinned_file)
    if found is None:
        raise ProcessRunnerError(
            f"the pinned build is not installed under {INSTALL_TREE}/<name>/<version>")
    return found


def confined_spec(
        spec: CommandSpec, boundary: WindowsContainer, paths, *,
        plain: tuple[str, ...], prefix: tuple[str, ...]) -> CommandSpec:
    """The attempt's spec with the boundary, the runtime variables and the boundary argv prefix.

    ``prefix`` replaces ``plain``, what the operator's pin contributed to the front of the argv;
    the task tokens behind it are untouched.
    """
    runtime = str(paths["runtime"])
    return replace(
        spec, boundary=boundary, argv=(*prefix, *spec.argv[len(plain):]),
        env={**spec.env, **dict.fromkeys(RUNTIME_ENV, runtime)})


class AttemptLaunch:
    """Start one attempt in a fresh home, inside the boundary when confined, then take it back."""

    #: Set once by ``confine``; the class default is the launch that existed before R5.
    _confine = False
    _boundary_platform = ""

    def confine(self, platform: str) -> None:
        """Launch every later task attempt inside the execution boundary. There is no way back.

        Args:
            platform: The ``sys.platform`` value the boundary is judged for. It is passed in, never
                read here, so a test names the platform it asks about.
        """
        if type(platform) is not str or not platform:
            raise self.error("a confined transport needs the platform its boundary is judged for")
        self._confine = True
        self._boundary_platform = platform

    def boundary_provided(self, mode: str) -> bool:
        """Whether a task attempt of this mode would be launched inside the boundary.

        False for a transport never confined, false on the subscription road of a harness that
        has no relay (``_login_road_covered``), false when the runner this transport holds has no
        entry that takes the call it would make or, on a relay road, does not lend a relay home
        (``boundary_entry``), and false when the pinned build's install folder cannot be named
        from its path (``find_install_folder``): such an attempt is refused, never run without
        the boundary and never sent on to fail after the attempt was claimed. Each of these is a
        fact the transport holds before any claim, so the doors and the transport answer alike.

        Raises:
            ValueError: ``mode`` is not an attempt mode, confined or not, on any platform.
        """
        provided = boundary_provided(self._boundary_platform, mode)
        return self._confine and provided and self._road_covers(mode)

    def _road_covers(self, mode: str) -> bool:
        """Whether the road this transport holds can carry a confined attempt of this mode.

        Apart from the platform: the login it holds (``_login_road_covered``) and the launch
        (``_launch_covers``).
        """
        return self._login_road_covered() and self._launch_covers(mode)

    def _login_road_covered(self) -> bool:
        """Whether the login this transport holds may start a task inside the boundary.

        The API-key road may. The subscription road may where the harness has a relay
        (``HarnessProfile.login_relay``): its task runs on a relay home that holds a copy of the
        access token and no refresh token, and the real login home is never loaned (the decision
        of 23.10.2026, H5-SUB-R5). Where it has none the road may not: the owner's decision H5-V1
        of 21.10.2026 (``docs/recovery/2026-10-20/OPEN-DECISIONS.md``) stands, because its child
        would need rights on the operator's login home, where the vendor keeps executable
        configuration that runs again outside the boundary, and no attempt is given any.

        This is the ONE answer for that road: the doors (``boundary_provided``), the refusal
        before the claim (``_boundary_refusal``), the spawn (``_hold_boundary``) and the checker
        all reach it through ``_road_covers``. ``process_boundary.LOGIN_LOAN_OPEN`` is not part
        of it: that is the runner's own gate on a login home, and no transport names one
        (``AttemptFolders`` has no such field), so opening it opens nothing here.
        """
        return not self._signed_in_road() or self.profile.login_relay is not None

    def _relay_road(self) -> bool:
        """Whether this transport signs in by subscription AND its harness has a relay."""
        return bool(self._signed_in_road()) and self.profile.login_relay is not None

    def _relayed(self, mode: str | None) -> bool:
        """Whether an attempt of this mode is a TASK attempt that works on a relay home.

        A confined transport, a task attempt (``dispatch`` or ``review``) and a relay road. A
        transport never confined is not relayed whatever its login: that is the launch of the
        harness fakes, which stands on the real login directory (the launch before R5).
        """
        return self._confine and mode in ATTEMPT_MODES and self._relay_road()

    def _launch_covers(self, mode: str) -> bool:
        """A runner whose entry takes the call (and, on a relay road, lends a relay home), and a
        pinned build whose install folder the boundary can be asked to grant."""
        return (entry_takes_the_call(self._runner, mode)
                and (not self._relay_road() or entry_lends_relay_homes(self._runner))
                and find_install_folder(self._argv_prefix()[-1]) is not None)

    def _confined_attempt(self, mode: str | None) -> bool:
        """Whether an attempt of this mode is a TASK attempt that must start inside the boundary."""
        return mode is not None and self._confine

    def _launch_prefix(self, mode: str | None) -> tuple[str, ...]:
        """What the pin contributes to the argv a spawn of this mode will really run.

        The boundaried prefix for a confined task attempt, which can be longer than the pin
        (``_boundary_prefix``), and the pin as written for every other spawn. A size check made
        before the claim measures THIS, never the pin alone.
        """
        return self._boundary_prefix() if self._confined_attempt(mode) else self._argv_prefix()

    def _boundary_refusal(self, request, mode: str):
        """A failed receipt when a confined transport cannot cover this task, else None.

        Asked at the top of every road that starts a task, BEFORE its version preflight, so a
        refusal spawns nothing, borrows no login and creates no folder, home or marker. Where
        the login is the one fact missing (the platform has the boundary and the launch is
        covered), the receipt names it (H5-V1); otherwise it names no cause.
        """
        if not self._confine or self.boundary_provided(mode):
            return None
        tool = self.profile.tool_noun
        login_only = (not self._login_road_covered() and self._launch_covers(mode)
                      and boundary_provided(self._boundary_platform, mode))
        detail = subscription_boundary_detail(tool) if login_only else boundary_detail(tool)
        return self._receipt(request, "failed", None, detail)

    def _hold_boundary(self, mode: str | None) -> None:
        """Refuse a confined task attempt the boundary cannot cover, before it creates anything.

        The same question as ``_boundary_refusal``, asked once more at the spawn itself: a road
        that forgot to ask first still cannot start a child outside the boundary.
        """
        if not self._confined_attempt(mode):
            return
        require_boundary(self._boundary_platform, mode)
        if not self._road_covers(mode):
            raise BoundaryUnavailable(self._boundary_platform, mode)

    def _attempt(
            self, argv: ArgvSource, cwd: str, *, mode: str | None = None, claim=None,
            **options) -> ProcessOutcome:
        """One spawn inside one FRESH home, and the home goes when the spawn does.

        ``mode`` marks a TASK attempt (``dispatch`` or ``review``). On a confined transport such
        an attempt is refused here if the boundary is not provided, BEFORE the login write guard
        is entered, a home is minted or any folder is touched. ``options`` are the spawn's own
        bounds (``timeout``, ``stdin_bytes``, ``model`` and the rest); ``_owned_attempt`` names
        them and is where the spawn happens.

        ``claim`` is the ``Claim`` of the action, or None. An attempt that is not relayed takes it
        first, before the boundary is judged, as every road did before the relay. A RELAYED
        attempt hands it to ``_relay_attempt``, which takes it after the boundary was entered.
        That method stands under the login lease, so what it refuses it returns as a value, and
        this one, which stands outside the lease, raises it (``RelayNotStarted``, before any
        claim) or turns a lost launch into the error the runtime records as ``unknown``
        (``_relay_outcome``). So does a question put to the real login home of a relay road
        (``_asks_the_real_login``): the version print and the login status are spawns under the
        same lease.

        Raises:
            RelayNotStarted: A relayed attempt was refused before its claim.
        """
        if not self._relayed(mode):
            if claim is not None:
                claim()
            self._hold_boundary(mode)
            return self._relay_outcome(self._owned_attempt(argv, cwd, mode=mode, **options))
        self._hold_boundary(mode)
        return self._relay_outcome(
            self._relay_attempt(argv, cwd, mode=mode, claim=claim, **options))

    def _asks_the_real_login(self, mode: str | None) -> bool:
        """Whether this spawn is a question put to the real login home of a relay road.

        A version print, a login status, a quota read: no task attempt, and so no mode. They stand
        under the shared login lease, and an exception leaving it makes the lease uncertain until
        the OS restarts, so what these refuse before a child exists is a value (``LaunchLost``,
        ``CarriedError``) that ``_attempt`` raises again outside the lease.
        """
        return mode is None and self._relay_road()

    @owned_login_attempt
    def _owned_attempt(
            self, argv: ArgvSource, cwd: str, *,
            timeout: int | float,
            stdin_bytes: bytes | None = None,
            stdin_completion_id: int | None = None,
            separate_stderr: bool = False,
            model: str | None = None,
            output_limit: int | None = None, server_read=None,
            unset_env: tuple[str, ...] = (),
            mode: str | None = None) -> ProcessOutcome:
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

        A question put to the real login home of a relay road (``_asks_the_real_login``) that
        cannot start returns a value, not an exception: this method stands under the login lease.
        """
        try:
            home = self._mint_home()
        except (WorkspaceNotContained, OSError) as refused:
            if not self._asks_the_real_login(mode):
                raise
            return CarriedError(refused)
        # ONE source for "is there a login directory in play", so the before and
        # after measurements and the cleanup can never disagree about it.
        auth_home = self._signed_in_road()
        before = login_home.measure(auth_home, self.profile.login_scratch)
        self._login_echo = False
        self._remember_login_values()
        try:
            outcome = self._spawn(
                argv, home, cwd, timeout=timeout, stdin_bytes=stdin_bytes,
                stdin_completion_id=stdin_completion_id,
                separate_stderr=separate_stderr, model=model,
                output_limit=output_limit, unset_env=unset_env, mode=mode,
                **({} if server_read is None else {"server_read": server_read}))
            if isinstance(outcome, LaunchLost):
                return outcome
            self._read_attempt_result(home, outcome)
            return outcome
        finally:
            if auth_home:
                self._take_back_login(auth_home, before)
            self._discard(home)

    def _read_attempt_result(self, home, outcome):
        """Measure the completed spawn while its temporary home still exists."""
        self._read_attempt_home(home)
        # A vendor can refresh credentials while running. Scan the resulting
        # values as well as those the runner already checked before spawning.
        self._login_echo = self._echoed_login(outcome.output)
        self._remember_login_values()

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
            stdin_completion_id: int | None = None,
            separate_stderr: bool = False,
            model: str | None = None,
            output_limit: int | None = None, server_read=None,
            unset_env: tuple[str, ...] = (),
            mode: str | None = None) -> ProcessOutcome | LaunchLost:
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
            spec = attempt_spec(self, argv, home, cwd, timeout=timeout,
                stdin_bytes=stdin_bytes, stdin_completion_id=stdin_completion_id,
                separate_stderr=separate_stderr, model=model, output_limit=output_limit,
                unset_env=unset_env, mode=mode)
            if self._confined_attempt(mode):
                return self._run_confined(spec, home, cwd, mode)
            if server_read is not None:
                owned = self._runner.start(spec)
                try:
                    server_read(owned.pid)
                finally:
                    outcome = self._runner.stop(owned.token)
                return outcome
            return self._runner.run(spec)
        except ProcessRunnerError:  # noqa: BLE001 -- carry no child detail onward
            failed = True
        if failed and self._asks_the_real_login(mode):
            return LaunchLost()  # the same error, raised by `_attempt` once the lease has closed
        if failed:
            raise self.error(
                f"the {profile.tool_noun} harness could not start the "
                "pinned build") from None
        raise self.error("unreachable")

    def _run_confined(self, spec: CommandSpec, home: Path, cwd: str, mode: str) -> ProcessOutcome:
        """Run a task attempt inside the boundary entry, or refuse; never run it without one.

        The block ends only after the child's tree is gone and the entry has restored what it
        granted. Leaving it can still raise; the outcome already held is then real but its
        folders are not proven released, so the error propagates and the attempt is ``unknown``,
        never ``succeeded``. Every refusal of entering or leaving becomes the one fixed error.
        """
        plain = self._argv_prefix()
        try:
            folders = self._attempt_folders(cwd, home, mode)
            with self._runner.container_profile(**entry_call(mode, folders)) as (boundary, paths):
                return self._runner.run(confined_spec(
                    spec, boundary, paths, plain=plain, prefix=self._boundary_prefix()))
        except LAUNCH_REFUSALS:
            raise ProcessRunnerError("the boundaried launch was refused") from None

    def _attempt_folders(self, cwd: str, home: Path, mode: str) -> AttemptFolders:
        """The folders a confined attempt asks the boundary entry for: the one place they are named.

        The home of a RELAYED attempt is its relay home, written as the absolute path text the
        runner judges as one; any other is a route beneath the project root.
        """
        return AttemptFolders(
            work=cwd,
            home=str(home) if self._relayed(mode) else home.relative_to(
                self._workspace.root).as_posix(),
            install=install_folder(self._argv_prefix()[-1]))

    def _run_relayed(self, spec: CommandSpec, home: Path, cwd: str, mode: str, claim):
        """Enter the boundary, claim, run, leave: what is refused BEFORE the child is a value.

        Called under the login lease, so no expected failure may leave it as an exception. The
        action is claimed only once the block is entered, so a boundary that refuses its entry
        leaves no marker and nothing started (``NotStarted``). From the moment the run begins the
        child may have worked: a refusal to run or to leave after that is ``LaunchLost``, which
        the caller makes the error the runtime records as ``unknown``. A claim that cannot be taken
        starts nothing either. What is neither of these (a bug, an interrupt) is not caught.

        Returns:
            The outcome, a ``NotStarted`` or a ``LaunchLost``.
        """
        ran = False
        try:
            folders = self._attempt_folders(cwd, home, mode)
            with self._runner.container_profile(**entry_call(mode, folders)) as (boundary, paths):
                ready = self._ready_to_run(spec, boundary, paths, claim)
                if isinstance(ready, NotStarted):
                    return ready
                ran = True
                return self._runner.run(ready)
        except LAUNCH_REFUSALS:
            return LaunchLost() if ran else NotStarted("enter")

    def _ready_to_run(self, spec: CommandSpec, boundary: WindowsContainer, paths, claim):
        """The spec the child runs with, once the action is claimed; or why nothing may start.

        The entry of the boundary has given what the spec needs of it, so everything that can be
        refused is refused now, in this order, and the claim is the last of it: the spec is built
        (``NotStarted("spec")``), then the claim is taken. A claim that cannot be taken starts
        nothing, and says whether its marker stands anyway (``NotStarted("claim_standing")``): a
        write that failed half way leaves the action claimed, and a repeat of it is ``unknown``.
        """
        try:
            final = confined_spec(spec, boundary, paths, plain=self._argv_prefix(),
                                  prefix=self._boundary_prefix())
        except ProcessRunnerError:
            return NotStarted("spec")
        if claim is not None:
            try:
                claim()
            except CLAIM_REFUSALS:  # noqa: BLE001 -- no path onward
                return NotStarted("claim_standing" if claim.stands() else "claim")
        return final

    def _boundary_prefix(self) -> tuple[str, ...]:
        """What the pin contributes to the front of a boundaried argv.

        The pin as the operator wrote it, unless the build cannot start from it inside the
        container: a harness that needs more says so by overriding this.
        """
        return self._argv_prefix()

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
