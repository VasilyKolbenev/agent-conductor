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
launch. A transport never confined launches as it always did; the doors tell a plan that demands
the boundary from such a harness that it has none (``AdapterRegistry.execution_boundary``).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ...ownership_errors import OwnerRefused
from ..execution_boundary import BoundaryUnavailable, boundary_provided, require_boundary
from . import login_home
from .harness_profile import boundary_detail
from .harness_workspace import WorkspaceNotContained
from .headless_spec import attempt_spec
from .headless_values import ArgvSource
from .login_lifetime import owned_login_attempt
from .process import CommandSpec, ProcessOutcome, ProcessRunnerError
from .process_boundary import WindowsContainer
from .process_profile import ProfileRefused

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
        home: The route, relative to the project root, of its per-spawn home, or None.
        install: The ABSOLUTE folder that holds the pinned executable and what it loads.
    """

    work: str
    home: str | None
    install: str


def confined_spec(spec: CommandSpec, boundary: WindowsContainer, paths) -> CommandSpec:
    """The attempt's spec with the boundary and the runtime variables, and nothing else changed."""
    runtime = str(paths["runtime"])
    return replace(spec, boundary=boundary, env={**spec.env, **dict.fromkeys(RUNTIME_ENV, runtime)})


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

        False for a transport never confined, and false on the subscription road, whose leased
        login directory the boundary does not grant (H contract, section 5): such an attempt is
        refused, never run without the boundary.

        Raises:
            ValueError: ``mode`` is not an attempt mode, confined or not, on any platform.
        """
        provided = boundary_provided(self._boundary_platform, mode)
        return self._confine and provided and not self._signed_in_road()

    def _boundary_refusal(self, request, mode: str):
        """A failed receipt when a confined transport cannot cover this task, else None.

        Asked at the top of every road that starts a task, BEFORE its version preflight, so a
        refusal spawns nothing, borrows no login and creates no folder, home or marker.
        """
        if not self._confine or self.boundary_provided(mode):
            return None
        return self._receipt(request, "failed", None, boundary_detail(self.profile.tool_noun))

    def _hold_boundary(self, mode: str | None) -> None:
        """Refuse a confined task attempt the boundary cannot cover, before it creates anything.

        The same question as ``_boundary_refusal``, asked once more at the spawn itself: a road
        that forgot to ask first still cannot start a child outside the boundary.
        """
        if mode is None or not self._confine:
            return
        require_boundary(self._boundary_platform, mode)
        if self._signed_in_road():
            raise BoundaryUnavailable(self._boundary_platform, mode)

    def _attempt(
            self, argv: ArgvSource, cwd: str, *, mode: str | None = None,
            **options) -> ProcessOutcome:
        """One spawn inside one FRESH home, and the home goes when the spawn does.

        ``mode`` marks a TASK attempt (``dispatch`` or ``review``). On a confined transport such
        an attempt is refused here if the boundary is not provided, BEFORE the login write guard
        is entered, a home is minted or any folder is touched. ``options`` are the spawn's own
        bounds (``timeout``, ``stdin_bytes``, ``model`` and the rest); ``_owned_attempt`` names
        them and is where the spawn happens.
        """
        self._hold_boundary(mode)
        return self._owned_attempt(argv, cwd, mode=mode, **options)

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
                stdin_completion_id=stdin_completion_id,
                separate_stderr=separate_stderr, model=model,
                output_limit=output_limit, unset_env=unset_env, mode=mode,
                **({} if server_read is None else {"server_read": server_read}))
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
            mode: str | None = None) -> ProcessOutcome:
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
                unset_env=unset_env)
            if mode is not None and self._confine:
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
        folders = AttemptFolders(
            work=cwd, home=home.relative_to(self._workspace.root).as_posix(),
            install=self._install_folder())
        try:
            with self._runner.container_profile(
                    mode=mode, internet_client=True, folders=folders) as (boundary, paths):
                return self._runner.run(confined_spec(spec, boundary, paths))
        except LAUNCH_REFUSALS:
            raise ProcessRunnerError("the boundaried launch was refused") from None

    def _install_folder(self) -> str:
        """The folder that holds the pinned file the child starts from, as an absolute path.

        The folder of the last element of the operator's pin: the executable of a native binary,
        the entrypoint of an interpreter. What else the build loads beside it is measured by the
        host's probe and is not guessed here.
        """
        return str(Path(self._argv_prefix()[-1]).parent)

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
