"""The login road: which directory a child is pointed at, and what it may leave.

Split out of ``headless_cli`` when that module crossed the 800-line cap, on the
same kind of seam the three earlier splits found rather than as a place to put
spare lines. ``harness_profile`` holds what a provider DECLARES about its login;
``login_home`` holds the measurement of a directory; this holds the one circuit
that decides, per spawn, WHICH directory the child is told about and what is
taken back afterwards.

There are two roads and the difference between them is the whole contract.

On the API-key road the child is pointed at a directory this build minted for
one spawn and destroys when it returns, so whatever the vendor wrote under it
has a lifetime of one attempt. The credential comes from the environment by a
name the operator allowed, and no login is asked about because there is none.

On the subscription road the child is pointed at the directory the OPERATOR
pinned, where the vendor's own login command wrote its credential. That
directory cannot be deleted -- a login copied into a fresh one could not be
refreshed, and one deleted afterwards would have to be performed again before
every run -- so the retention promise is kept by NAMING what may appear there,
taking back the per-run names, and reporting anything else. And because a login
can be absent or expired, it is proved before a task is spawned, by the vendor's
own status command -- read for the METHOD it names, because both vendors answer
an API key with the same exit code they answer a subscription with.

What a mixin needs from the class it is mixed into is stated rather than
assumed: ``profile``, ``_attempt``, ``_receipt`` and ``_login_residue``, all of
them ``HeadlessCliTransport``'s.
"""
from __future__ import annotations

from pathlib import Path

from ..contracts import ActionRequest, ActionResultReceipt
from . import login_home
from .harness_workspace import WORK_DIR

#: The mode a login directory is read on. Spelled here rather than imported from
#: the config door, because this module is the transport's own reader of a pin
#: and must not depend on the surface that admits one.
SUBSCRIPTION = "subscription"


class LoginRoad:
    """Which login a transport was pinned to, and everything that follows."""

    def _login(self) -> tuple[str, str]:
        """The login this provider was pinned to, and where it is kept.

        The base answers with the road that shipped, so a provider that has
        never been given a vendor login behaves exactly as it did. A provider
        whose transport drives a real login overrides this from its own pin.
        """
        return "api_key", ""

    def _signed_in_road(self) -> str:
        """The pinned login directory, or empty on the road that has none."""
        auth, auth_home = self._login()
        return auth_home if auth == SUBSCRIPTION else ""

    def _home_value(self, home: Path) -> str:
        """What the child's home environment variable is set to for this spawn.

        The minted, doomed directory on the API-key road; the operator's pinned
        login directory on the subscription one. It is the same variable either
        way -- no new name is invented for a login -- and it is the only value
        this road changes about a spawn.
        """
        return self._signed_in_road() or str(home)

    def _login_preflight(
            self, request: ActionRequest) -> ActionResultReceipt | None:
        """Prove the pinned login is really a SUBSCRIPTION, or refuse before a task.

        Only on the subscription road: the API-key road has no login to ask
        about, and a build that asked there would be inventing a second thing
        that can fail.

        An exit code is not enough, and the first version of this seam believed
        it was. MEASURED on the reviewed builds: a directory holding nothing but
        an API key answers `codex login status` with "Logged in using an API
        key" and exit 0, and `claude auth status --json` answers an API key in
        the environment with `authMethod: "api_key"` and exit 0. Both bill an
        API account -- the exact silent fallback a subscription pin exists to
        refuse -- and a Codex directory holding a subscription AND a key answers
        with the key, so the key wins where nobody asked it to.

        So the METHOD is established positively, by the provider's own reader of
        its own status answer, and anything else refuses. What is read is a
        closed vocabulary; no account name, plan, key fragment or raw status
        byte reaches the receipt.
        """
        profile = self.profile
        if not self._signed_in_road():
            return None
        if not profile.login_argv:
            # The config door admits `subscription` for a protocol whose
            # transport drives a login; a profile that declares no status
            # question has no way to establish one, and a road that quietly
            # skipped the check would be the loudest of the defects this seam
            # exists to close, in silence.
            return self._receipt(
                request, "failed", None,
                f"this build cannot establish a subscription login for the "
                f"pinned {profile.tool_noun} build, so no task was spawned")
        outcome = self._attempt_login_status(request)
        answered = (outcome.status == "completed" and outcome.exit_code == 0
                    and not outcome.output_truncated)
        if answered and self._login_method_admitted(outcome.output):
            return None
        return self._receipt(
            request, "failed", None,
            f"the pinned {profile.tool_noun} build reports no subscription "
            f"login in the directory this provider pins -- an absent login, an "
            f"API key or a method this build does not accept -- so no task was "
            f"spawned; sign in yourself with {profile.home_env} set to that "
            f"directory and run {self._login_command_line()} -- this build "
            "never runs a login")

    def _attempt_login_status(self, request: ActionRequest):
        """Ask the vendor's status question, bounded like every other preflight."""
        profile = self.profile
        return self._attempt(
            self._login_status_argv(), WORK_DIR,
            timeout=min(profile.version_timeout_seconds, request.timeout_seconds))

    def _login_method_admitted(self, output: bytes) -> bool:
        """Whether the vendor's status answer names a login this road may use.

        Refuses by KNOWLEDGE rather than accepting by it: the values that mean
        "no login" and "an API key" are measured on the reviewed build, and the
        token a real subscription answers with is not -- nobody has signed in on
        this machine. A rule written the other way round would have to guess
        that token, and a wrong guess refuses every real subscription.

        The base REFUSES rather than raising. A provider that declared a status
        question and no reader for its answer is a programming fault, and the
        two ways of reporting one are not equal: an exception out of a preflight
        becomes an unknown attempt, while a refusal is a run that did not start.
        """
        return False

    def _login_home_refusal(
            self, request: ActionRequest) -> ActionResultReceipt | None:
        """Refuse a login directory that also carries CONFIGURATION.

        The API-key road mints an empty directory per spawn, and an empty one is
        the whole reason a harness does not trust the work tree it is standing
        in. Pointing the same variable at a directory that survives gives that
        reason away: MEASURED on Codex 0.112.0, a `config.toml` in the login
        directory naming the work tree as a trusted project makes the vendor
        read the work tree's own `.codex/config.toml`, which the empty directory
        had excluded. The names that can carry configuration or trust are
        therefore declared per provider and refused here, before the spawn that
        would read them.
        """
        profile = self.profile
        if not self._signed_in_road() or not profile.login_forbidden:
            return None
        if not self._login_home_grants(self._signed_in_road()):
            return None
        return self._receipt(
            request, "failed", None,
            f"the login directory this provider pins also holds {profile.tool_noun} "
            "configuration, which a spawn would read from a directory this build "
            "cannot vouch for, so no task was spawned; point this provider at a "
            "directory used for its login and nothing else")

    def _login_home_grants(self, home: str) -> tuple[str, ...]:
        """What a login directory gives away, by NAME unless a provider says more.

        The default is the strict reading: a declared name standing there is a
        grant, because for most of these files anything at all in them is
        customization this build cannot vouch for. A provider whose vendor
        writes its own file beside its own login overrides this and reads the
        file, so a directory the vendor itself produced is not refused for
        existing.

        A directory this build could not read answers with the whole list: a
        directory whose contents cannot be established is not one it can say is
        harmless.
        """
        held = login_home.entries(home)
        if held is None:
            return self.profile.login_forbidden
        return tuple(name for name in self.profile.login_forbidden if name in held)

    def _login_command_line(self) -> str:
        """The vendor's own login command, as a person would type it."""
        return " ".join(self.profile.login_command)

    def _login_secrets(self) -> tuple[bytes, ...]:
        """The values a child of THIS spawn must never be seen echoing back.

        Empty on the API-key road, where the credential arrives by an allowed
        environment name and the runner already scans for it. On the
        subscription road it is the vendor's own login file, read bounded and
        held only as bytes to compare the child's output against.
        """
        auth_home = self._signed_in_road()
        if not auth_home:
            return ()
        return login_home.credential_values(
            auth_home, self.profile.login_credentials)

    def _begin_road(self) -> None:
        """Re-derive everything one ROAD may report, before it reports any of it.

        An adapter instance serves every action of its provider. A count or a
        credential value left standing by a dispatch would be reported on a
        review whose own spawns produced neither -- and a login value borrowed
        from another action would have this one scanning new material against a
        secret that was never in it.
        """
        self._retained = 0
        self._login_residue = 0
        self._login_seen = ()

    def _remember_login_values(self) -> None:
        """Add the login as it stands NOW to what this road has seen.

        Called on both sides of every spawn. A credential refreshed mid-run
        leaves two values in play: the one a child could have written into a
        file before the refresh, and the one standing after it. A scan built
        from either alone looks for the wrong secret in material that carries
        the other.
        """
        self._login_seen = tuple(dict.fromkeys(
            (*self._login_seen, *self._login_secrets())))

    def _keep_login_values(self, relation) -> None:
        """Hand what this road has seen to the attempt it belongs to."""
        if self._login_seen:
            self._login_history[relation] = self._login_seen

    def _echoed_login(self, output: bytes) -> bool:
        """Whether this output carries a login value as it stands AFTER the spawn.

        The runner scans against the values read before the child started, which
        is the only set it can have. A vendor that refreshes its credential mid
        run leaves a DIFFERENT secret behind, and a child that echoed the new one
        would pass a scan built entirely from the old. So the file is read again
        here, and the same output is judged against what it now holds.

        The old values are not dropped: the runner's flag still answers for
        them, and both answers are consulted before anything is published.
        """
        if not output or not self._signed_in_road():
            return False
        return any(value in output for value in self._login_secrets())

    def _login_status_argv(self) -> tuple[str, ...]:
        """The status question as it is really asked, with this road's own bounds.

        A provider whose isolation is a FLAG has to send it here too. Asking the
        vendor's status question is a full startup of that CLI -- it opens a
        connection and writes its own profile -- and a startup standing in the
        run's work root would read whatever settings a previous task left there.
        The version probe is the one spawn that needs no flag, because printing
        a version is not a startup.
        """
        return self.profile.login_argv

    def _take_back_login(
            self, auth_home: str, before: frozenset[str] | None) -> None:
        """Take back what this spawn left in the login directory, and COUNT the rest.

        The mirror of ``_discard`` for the road that cannot delete its
        directory. It runs in the same ``finally``, for the same reason: a spawn
        that raised left state behind exactly as one that returned did -- and,
        for the same reason, it may not raise: an exception here would skip the
        attempt home's own discard and replace the outcome of the spawn.

        Only what APPEARED is judged, and only what appeared is taken back.
        Whatever the operator's own login put there before this build ever ran
        is theirs, and a product that refused over it -- or deleted it -- would
        be acting on the credential it was pointed at.

        A measurement this build could not take counts as residue rather than as
        a clean directory: a promise that could not be checked was not kept.
        """
        profile = self.profile
        declared = (*profile.login_scratch, *profile.login_expected)
        added = login_home.appeared(
            before, login_home.measure(auth_home, profile.login_scratch))
        left = login_home.take_back(auth_home, profile.login_scratch, added)
        if added is None or left or login_home.unexpected(added, declared):
            # The NAMES are not carried onward: this counter is read by the
            # receipt builder, which says that the promise did not hold and
            # never what was found. A cleanup that could not finish counts the
            # same as state nobody declared: in both cases what this attempt
            # left behind is not accounted for.
            self._login_residue += 1
