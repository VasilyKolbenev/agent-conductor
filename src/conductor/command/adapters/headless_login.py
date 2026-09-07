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
own status command, read for its exit code alone.

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
        """Prove the pinned SUBSCRIPTION login answers, or refuse before a task.

        Only on the subscription road: the API-key road has no login to ask
        about, and a build that asked there would be inventing a second thing
        that can fail. The vendor's own status command is asked, and only its
        EXIT CODE is read -- the answer is a fact about an account, and a
        product that parsed and reported it would be repeating somebody's
        account state into a durable receipt.

        Measured on the reviewed builds: with no login, Claude Code's
        ``auth status --json`` exits 1 and Codex's ``login status`` exits 1, and
        neither needs a credential to answer. The refusal therefore says what is
        missing and how a PERSON fixes it, and quotes no child output at all.
        """
        profile = self.profile
        if not self._signed_in_road() or not profile.login_argv:
            return None
        outcome = self._attempt(
            self._login_status_argv(), WORK_DIR,
            timeout=min(profile.version_timeout_seconds, request.timeout_seconds))
        if outcome.status == "completed" and outcome.exit_code == 0:
            return None
        return self._receipt(
            request, "failed", None,
            f"the pinned {profile.tool_noun} build has no usable subscription "
            f"login in the directory this provider pins, so no task was "
            f"spawned; sign in yourself with {profile.home_env} set to that "
            f"directory and run {' '.join(profile.login_command)} -- this build "
            "never runs a login")

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
        added = login_home.appeared(before, login_home.entries(auth_home))
        if added is None or login_home.unexpected(added, declared):
            # The NAMES are not carried onward: this counter is read by the
            # receipt builder, which says that the promise did not hold and
            # never what was found.
            self._login_residue += 1
        login_home.take_back(auth_home, profile.login_scratch, added)
