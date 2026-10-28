"""What a transport does, around the boundary entry, to run a task on a RELAY home (I2b).

A subscription harness that has a relay (`HarnessProfile.login_relay`) is never started on the real
login home. Its task attempt works on a fresh relay home that holds a copy of the access token and
no refresh token (`login_relay`, `relay_home`), and the order is the Codex ruling of 23.10.2026
(C2): the lease of the login is taken, the copy is made, the boundary is ENTERED, and only then
is the action claimed and the child started. Everything that can be refused before that is a
refusal before the claim: it leaves no marker, no child and no home, and the lease closes clean.

**The shared login lease is poisoned by an exception raised inside it** (design F3): any exception
leaving the guard marks the lease uncertain, and an uncertain lease refuses the login until the OS
restarts. So everything this road expects to fail inside the lease fails as a VALUE (ruling C3):
`NotStarted` (no child, no marker) and `LaunchLost` (the child may have run, and what became of it
is not known), and `AttemptLaunch._attempt`, which stands OUTSIDE the lease, turns them into the
refusal a receipt can say (`RelayNotStarted`) or the error the runtime records as `unknown`. What
this road does NOT expect (a fault of the code, an interrupt, a loan the runner could not prove
retired) still raises and still leaves the lease uncertain, as before.

What the road holds, by moment:

- the START of a road (`_relay_start`), before the version question: the relay folder is made and
  proved (outside the lease: its refusal is an exception of the runner), and what an earlier attempt
  left in it is swept; a home that cannot be removed stops the road like a home of the project does;
- the ENVIRONMENT (`_route_selected`), first of all, before any question is put to the real login
  home: a name that replaces the login or reroutes its traffic, judged by the values the runner
  really selects (`HeadlessCliTransport._preflight`, a quota read);
- the READINESS (`_relay_preflight`), as the LAST step of the preflight, after the login status
  question, which is the last use of the real home by anything that could change it: the DACLs, the
  environment again, and the login itself for an attempt of this one length. It is asked again for
  every attempt and kept for none; a login that is not fresh enough is refused with a request to
  sign in again, and no refresh is attempted outside the boundary in this version;
- the ATTEMPT (`_relay_attempt`), under the lease: the lease must name this login, the home is made,
  the copy is written, the boundary is entered, the command is built, the action is claimed, the
  child runs. The home is read back before it goes, so a token the vendor renewed in it joins what
  is scanned for, and it goes on every road out; one that cannot be removed is counted, and the next
  road is stopped by it.

A question put to the real login home (a version print, a login status, a quota read) stands under
the same lease and fails the same way (`AttemptLaunch._asks_the_real_login`): a runner that refuses
before a child exists is `LaunchLost`, a project home that cannot be made is `CarriedError`, both
values, raised again by `_attempt` outside the lease.

Nothing here copies a byte back to the real login home, and nothing here names a path or a value in
a sentence: the words a refusal carries are a closed table (`refusal_sentence`), and the runtime
answers them with words of its own (`failure_reasons`).

What a mixin needs from the class it is mixed into is stated rather than assumed: `profile`,
`error`, `_runner`, `_workspace`, `_clock`, `_receipt`, `_retained`, `_login_seen`, `_login_echo`,
`_signed_in_road`, `_login_command_line`, `_env_allow`, `_confine`, `_relay_road`, `_relayed`,
`_run_relayed`, `_tokens`, `_read_attempt_home` and `_echoed_login`, all of them
`HeadlessCliTransport`'s.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ...ownership_errors import OwnerRefused
from ..contracts import ActionRequest, ActionResultReceipt
from . import login_relay, relay_home
from .harness_profile import residue_detail
from .harness_workspace import WorkspaceNotContained
from .headless_spec import attempt_spec
from .relay_env import access_only_switch
from .login_lifetime import owned_login_attempt
from .process import ProcessOutcome, ProcessRunnerError
from .process_profile import ProfileRefused

#: What taking the claim of an action can refuse with: a value under the lease, never an exception.
CLAIM_REFUSALS = (WorkspaceNotContained, OSError, OwnerRefused, ProcessRunnerError)
#: The refusals of this road that are not a refusal of the login itself (`login_relay.REFUSALS`),
#: each with the words a sentence says it in. A word names no path and no value.
OWN_PHRASES = MappingProxyType({
    "root": "the relay folder of the login is not usable",
    "acl": "a folder of the login or of its relay is open to an isolated child",
    "env": "the environment of the attempt carries a name that replaces the login or "
           "reroutes its traffic",
    "ready": "the login was not proved ready for this attempt",
    "lease": "the login lease of the attempt does not name this login",
    "mint": "the relay home of the attempt could not be made",
    "spec": "the command of the attempt could not be built for its relay home",
    "enter": "the execution boundary refused the relay home of the attempt",
    "claim": "the action could not be claimed for the attempt",
    "claim_standing": "the claim of the action could not be completed but its marker stands, and "
                      "a repeat of the action is unknown",
})
#: The refusals only a new sign-in repairs: their sentence says which command to run.
SIGN_IN_AGAIN = frozenset({"expiry_short", "expiry_unknown"})
#: The refusals that say nothing against the login: the relay home, the command, the boundary or
#: the claim of the attempt failed, and the attempt could not start in isolation. Every other
#: refusal is about the login or the folders it stands in, and says the login is not ready.
NOT_THE_LOGIN = frozenset({"mint", "spec", "enter", "claim", "claim_standing"})


def refusal_prefix(tool: str, code: str | None = None) -> str:
    """The words a refusal begins with: of the login, or (for `NOT_THE_LOGIN`) of the start.

    Without a code it is the opening of every refusal about the login, which is what a preflight
    can answer (`RelayAttempt._relay_refused`).
    """
    if code in NOT_THE_LOGIN:
        return f"the {tool} attempt could not start in isolation: "
    return f"the {tool} login is not ready for an isolated attempt: "


def refusal_sentence(tool: str, code: str, sign_in: str | None = None, home_env: str = "") -> str:
    """The one sentence a refused relay attempt writes: no path, no value, nothing a child said.

    Args:
        tool: The harness's noun (`HarnessProfile.tool_noun`).
        code: A code of `login_relay.REFUSALS` or `OWN_PHRASES`.
        sign_in: The vendor's own login command as a person types it; said where only a new
            sign-in repairs the refusal (`SIGN_IN_AGAIN`).
        home_env: The name of the variable that points the vendor at its login folder, said with
            the command: without it the person would sign in to the vendor's own global profile,
            not to the folder this provider pins. The folder itself is a path and is not said.

    Raises:
        KeyError: `code` is no refusal of this road.
    """
    phrase = login_relay.REFUSALS[code] if code in login_relay.REFUSALS else OWN_PHRASES[code]
    again = ""
    if code in SIGN_IN_AGAIN and sign_in:
        where = ""
        if home_env:
            where = f"{home_env} set to the login directory this provider pins and run "
        again = f"; sign in again with {where}{sign_in}"
    return f"{refusal_prefix(tool, code)}{phrase}, so no task was spawned{again}"


@dataclass(frozen=True)
class NotStarted:
    """An attempt that never began: no child was started, no action was claimed.

    A value, so that what is refused under the lease is refused as a value and the lease closes
    clean. `code` is a code of `login_relay.REFUSALS` or `OWN_PHRASES`.
    """

    code: str

    def __post_init__(self) -> None:
        if self.code not in login_relay.REFUSALS and self.code not in OWN_PHRASES:
            raise ValueError("an attempt that did not begin says one of the closed codes")


@dataclass(frozen=True)
class LaunchLost:
    """The child may have run, and its outcome is lost: the action was claimed, so it is `unknown`.

    Leaving the boundary failed after the work, or the runner refused the run itself after the
    claim. It is never a success and never "not started", and the work is never repeated. It is
    also what a question put to the real login home (a version print, a login status) becomes when
    the runner cannot start it: nothing was claimed there, and `_attempt` raises the transport's
    one fixed "could not start" error, as it always did, once the lease has closed clean.
    """


@dataclass(frozen=True)
class CarriedError:
    """An exception a question to the real login home met under the lease, carried out of it.

    The project's home for the question could not be made. The lease must not see an exception for
    that: it is a fact of the project and says nothing against the login, and an exception leaving
    the guard marks the lease uncertain. `_attempt` raises `error` again, unchanged, once the lease
    has closed, so the receipt the road builds from it is the one it always built.
    """

    error: Exception


@dataclass(frozen=True)
class Claim:
    """The claim of one action as an attempt takes it, and the means to see whether it stands.

    Calling it takes the claim. `stands` looks at the marker afterwards: a claim that fails after
    its marker was written leaves the action claimed, and a receipt must not say otherwise.
    """

    take: Callable[[], None]
    look: Callable[[], bool]

    def __call__(self) -> None:
        self.take()

    def stands(self) -> bool:
        """Whether the marker is there; a marker that cannot be looked at counts as there."""
        try:
            return bool(self.look())
        except CLAIM_REFUSALS:
            return True


class RelayNotStarted(Exception):
    """A relay attempt was refused before its claim; `str()` is the one closed sentence.

    Raised by `AttemptLaunch._attempt`, which stands outside the login lease: the lease it was
    refused under has closed clean by then. The roads that start a task turn it into a `failed`
    receipt (or, for the checker, a closed reason).
    """

    def __init__(self, code: str, sentence: str) -> None:
        super().__init__(sentence)
        self.code = code


class RelayAttempt:
    """The relay road of a transport: its start, its readiness and its attempt."""

    #: What `_relay_preflight` proved for the attempt that comes next, or None: held between the
    #: preflight and the attempt of ONE road and consumed by the attempt.
    _relay_ready: login_relay.Ready | None = None

    # -- the start of a road ----------------------------------------------------------------

    def _relay_start(self, mode: str | None) -> str | None:
        """The relay folder is proved and swept; the code of a refusal, or None.

        `root` for a relay folder the runner cannot prove (it raises, so it is asked here, outside
        any lease) and `homes` for a home an earlier attempt left that could not be removed.
        """
        if not self._relayed(mode):
            return None
        spec = self.profile.login_relay
        try:
            root = self._runner.ensure_relay_root(self._signed_in_road())
            key = relay_home.project_key(self._workspace.root)
        except (ProfileRefused, ProcessRunnerError, OSError):
            return "root"
        return "homes" if login_relay.sweep(root, key, spec.kind, spec.files) else None

    def _claim_of(self, request: ActionRequest, *, verification: bool = False) -> Claim:
        """The claim of this request's action, or of its independent check, for one attempt."""
        workspace, run, action = self._workspace, request.run_id, request.action_id
        if verification:
            return Claim(lambda: workspace.claim_verification(run, action),
                         lambda: workspace.is_verification_claimed(run, action))
        return Claim(lambda: workspace.claim(run, action),
                     lambda: workspace.is_claimed(run, action))

    def _homes_refusal(self, request: ActionRequest, mode: str) -> ActionResultReceipt | None:
        """A failed receipt when the homes of the project or the relay homes hold a leftover.

        What is left in either place is state this build may not delete, and the road stops
        before it asks anything, claims anything or starts anything.
        """
        code = "homes" if self._workspace.sweep_homes() else self._relay_start(mode)
        if code is None:
            return None
        detail = (residue_detail(self.profile.tool_noun) if code == "homes"
                  else self._refusal_detail(code))
        return self._receipt(request, "failed", None, detail)

    def _refusal_detail(self, code: str) -> str:
        return refusal_sentence(
            self.profile.tool_noun, code, self._login_command_line(), self.profile.home_env)

    # -- the environment, before the real login home is asked anything ---------------------------

    def _route_selected(self) -> bool:
        """Whether the environment the spawns really get carries a name that replaces the login.

        Operator selection is checked BEFORE code-owned overrides, even when the operator's
        value equals the code's. A name absent from the selected environment is not forwarded.
        Only the exact access-only switch declared by Codex's profile is exempt among forced
        values; preflights on the real login never receive it (`headless_spec`). Asked before
        the version, login status and quota reads. False off the confined relay road.
        """
        if not (self._confine and self._relay_road()):
            return False
        spec = self.profile.login_relay
        chosen = self._runner.capture_environment(self._env_allow())
        if any(spec.forbids(name) for name in chosen.values):
            return True
        return any(spec.forbids(name) and not access_only_switch(self.profile, name, value)
                   for name, value in self.profile.forced_env)

    # -- the readiness of the login, as the last step of the preflight ---------------------------

    def _relay_preflight(self, request: ActionRequest) -> ActionResultReceipt | None:
        """Prove the login ready for THIS attempt, or refuse before anything is claimed.

        Asked by every road that starts a task attempt (a dispatch, a review, a checker), which
        is the question whether the transport is confined on a relay road: both attempt modes are
        relayed alike. The folders first, then the environment the attempt will really get (once
        more: `_route_selected` was asked before the first question), then the login for an
        attempt of the timeout of this request. What is proved is held for the attempt that
        follows and for nothing else.
        """
        self._relay_ready = None
        if not (self._confine and self._relay_road()):
            return None
        spec, auth_home = self.profile.login_relay, self._signed_in_road()
        if self._runner.relay_acl_refusal(auth_home) is not None:
            return self._unready(request, "acl")
        if self._route_selected():
            return self._unready(request, "env")
        ready = login_relay.ready_for(auth_home, spec, self._clock(), request.timeout_seconds)
        if isinstance(ready, login_relay.Refused):
            return self._unready(request, ready.code)
        self._relay_ready = ready
        return None

    def _unready(self, request: ActionRequest, code: str) -> ActionResultReceipt:
        return self._receipt(request, "failed", None, self._refusal_detail(code))

    def _relay_refused(self, receipt: ActionResultReceipt | None) -> bool:
        """Whether a preflight's refusal is the relay's (a login not ready), not a build refused."""
        return receipt is not None and receipt.detail.startswith(
            refusal_prefix(self.profile.tool_noun))

    # -- the attempt, under the lease ----------------------------------------------------------

    def _relay_outcome(
            self, value: "ProcessOutcome | NotStarted | LaunchLost | CarriedError"
    ) -> ProcessOutcome:
        """What `_attempt`, outside the lease, makes of what the attempt returned under it."""
        if isinstance(value, NotStarted):
            raise RelayNotStarted(value.code, self._refusal_detail(value.code))
        if isinstance(value, LaunchLost):
            raise self.error(
                f"the {self.profile.tool_noun} harness could not start the pinned build") from None
        if isinstance(value, CarriedError):
            raise value.error
        return value

    @owned_login_attempt
    def _relay_attempt(self, argv, cwd: str, *, timeout, mode: str, claim=None, **options):
        """One task attempt on a relay home, under the lease. Expected failures are values.

        The lease must name this very login before anything is made. The home is removed on every
        road out of this method, a raise included; a home that stays is counted. The readiness
        this attempt rests on was proved by the preflight and is consumed here.
        """
        spec, auth_home = self.profile.login_relay, self._signed_in_road()
        root = self._workspace.root
        ready, self._relay_ready = self._relay_ready, None
        if not relay_home.lease_names(root, auth_home):
            return NotStarted("lease")
        if not isinstance(ready, login_relay.Ready):
            return NotStarted("ready")
        home = relay_home.mint_home(auth_home, root, spec.kind)
        if home is None:
            return NotStarted("mint")
        self._login_echo = False
        try:
            return self._relay_in(home, ready, argv, cwd, timeout=timeout, mode=mode,
                                  claim=claim, **options)
        finally:
            if not login_relay.discard(home, spec.files):
                self._retained += 1

    def _relay_in(self, home: Path, ready: login_relay.Ready, argv, cwd: str, *, timeout,
                  mode: str, claim, **options):
        """The copy, the entry and the run on a home that was just made; then the read-back."""
        spec, auth_home = self.profile.login_relay, self._signed_in_road()
        if self._runner.relay_acl_refusal(auth_home, home) is not None:
            return NotStarted("acl")
        ticket = login_relay.copy_in(auth_home, home, spec, ready.digest)
        if isinstance(ticket, login_relay.Refused):
            return NotStarted(ticket.code)
        values = (*ready.secrets, *ticket.secrets)
        self._remember_relay_values(values)
        built = self._relay_spec(argv, home, cwd, values, timeout=timeout, mode=mode, **options)
        if isinstance(built, NotStarted):
            return built
        outcome = self._run_relayed(built, home, cwd, mode, claim)
        if isinstance(outcome, ProcessOutcome):
            self._read_relay_home(home, outcome, ticket)
        return outcome

    def _relay_spec(self, argv, home: Path, cwd: str, values: tuple[bytes, ...], *, timeout,
                    mode: str, stdin_bytes=None, stdin_completion_id=None,
                    separate_stderr=False, model=None, output_limit=None, server_read=None,
                    unset_env=()):
        """The command of the attempt, or `NotStarted`: a pin that cannot become a valid argv."""
        if server_read is not None:
            return NotStarted("spec")
        try:
            return attempt_spec(
                self, argv, home, cwd, timeout=timeout, stdin_bytes=stdin_bytes,
                stdin_completion_id=stdin_completion_id, separate_stderr=separate_stderr,
                model=model, output_limit=output_limit, unset_env=unset_env, mode=mode,
                extra=values)
        except ProcessRunnerError:
            return NotStarted("spec")

    # -- what the attempt left in the home ---------------------------------------------------------

    def _remember_relay_values(self, values: tuple[bytes, ...]) -> None:
        """Add secret values of the relay to what this road has seen, for every later scan."""
        self._login_seen = tuple(dict.fromkeys((*self._login_seen, *values)))

    def _read_relay_home(self, home: Path, outcome: ProcessOutcome,
                         ticket: login_relay.Ticket) -> None:
        """Read what the child left, while the home still stands, and judge the output by it.

        The vendor's own artefact first (Codex's final message file), then the credential of the
        home again: a token the child renewed there is a value the copy did not hold. A credential
        that cannot be read, or is no longer in the shape the relay admits, is taken as echoed,
        which a REVIEW honours (it is not published): what the file holds is not known. A dispatch
        and a checker read no such flag on any road; for them the protection is the values: those
        of a document that parses but has left its shape are ALL its texts, not only the named
        fields, and those of one that cannot be read are none, since there is nothing to read.
        """
        spec = self.profile.login_relay
        self._read_attempt_home(home)
        leaf = login_relay.read_leaf(ticket.leaf)
        unreadable = isinstance(leaf, login_relay.Refused) or spec.admit(leaf.doc) is not None
        values = ()
        if not isinstance(leaf, login_relay.Refused):
            values = (login_relay.every_text(leaf.doc) if unreadable
                      else login_relay.secret_values(leaf.doc, spec.secret_fields))
        self._remember_relay_values(values)
        self._login_echo = (unreadable or self._echoed_login(outcome.output)
                            or any(value in outcome.output for value in values))
        self._remember_login_values()

    def _home_leaf_kind(self, home: Path, name: str) -> str:
        """What stands at one name in an attempt home: of the project, or a relay home outside."""
        if Path(home).parent == self._workspace.homes_root():
            return self._workspace.home_leaf_kind(home, name)
        return relay_home.leaf_kind(home, name)
