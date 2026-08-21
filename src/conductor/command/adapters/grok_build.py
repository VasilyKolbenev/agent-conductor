"""Grok Build, driven headlessly: one pinned binary, one prompt, one attempt.

Every vendor fact below was read from xAI's own published sources and is pinned
to a PERMALINK, so a later reader re-checks the exact bytes this module was
written against rather than whatever the page says today. Every repository path
cited below is pinned at ONE commit, written out once so each citation stays
short enough to read and exact enough to fetch::

    PINNED_COMMIT = 19d42e35c07a9c9244f03f6df0c4c353f970d4f9   (2026-08-19)
    https://github.com/xai-org/grok-build/blob/<PINNED_COMMIT>/<path>

The two docs-site pages carry no version at all, which is exactly why their
wording is QUOTED here rather than merely cited: a page that can change under a
citation is re-checkable only if the words it said are written down.

- **The one-shot transport** is ``-p, --single <PROMPT>`` -- "Send one prompt" --
  and ``--output-format`` takes "``plain``, ``json``, or ``streaming-json``".
  Background update checks are skipped by passing ``--no-auto-update``: "pass
  ``--no-auto-update`` (e.g. ``grok --no-auto-update -p "..."``) to skip
  background update checks."
  (docs.x.ai/build/cli/headless-scripting)
- **The version print** comes from ``grok --version``, which the README
  recommends, and from the ``grok version`` subcommand, which the CLI reference
  documents as "Print version information"
  (github.com/xai-org/grok-build#installing-the-released-binary;
  docs.x.ai/build/cli/reference).
- **The FORM of that print** is source-backed, and it is the reason this module
  overrides the shared exact-string compare. Reading only the version CRATE is
  what made the first version of this adapter unable to dispatch at all, so the
  whole line is traced here, from the entry point outward:

  * ``crates/codegen/xai-grok-pager-bin/src/main.rs`` builds it as
    ``format!("grok {}\\n", display_version_with_commit(full_version(),
    channel_label))`` -- so **the program name is part of the printed line**;
  * the same ``main`` calls ``set_full_version(env!("VERSION_WITH_COMMIT"))``
    unconditionally, so a release binary ALWAYS carries a commit;
  * ``crates/codegen/xai-grok-pager-bin/build.rs`` sets that variable from
    ``git rev-parse --short HEAD`` as ``"{version} ({commit})"``, falling back
    to the literal ``unknown`` when git is unavailable -- so ``(unknown)`` is a
    published form, and the abbreviation length is the builder's ``core.abbrev``
    rather than anything this module may assume;
  * ``crates/codegen/xai-grok-version/src/lib.rs`` appends the channel with
    ``format!("{}{}", version_with_commit, channel_label)``, and
    ``crates/codegen/xai-grok-update/src/version.rs``'s ``channel_label()``
    returns exactly ``" [alpha]"``, ``" [stable]"`` or ``""`` -- bracketed, with
    a leading space.

  So the real first line is ``grok 1.0.5 (abc1234) [stable]``, and the parser
  below reads that. An earlier version of this module modelled the crate alone,
  refused every string a real install prints, and would have made this provider
  advertise itself available while failing every preflight forever.
- **The reviewed version is 1.0.5**, the latest stable release of 2026-08-15
  (x.ai/build/changelog).
- **The home** relocates with ``GROK_HOME``: "Override config directory
  (default: ``~/.grok``)".
- **Four switches** are documented, and all four are turned off here:
  ``GROK_TELEMETRY_ENABLED`` "Enable/disable telemetry",
  ``GROK_TELEMETRY_TRACE_UPLOAD`` "Enable/disable session trace upload",
  ``GROK_TELEMETRY_MIXPANEL_ENABLED`` "Enable/disable Mixpanel specifically",
  and ``GROK_FEEDBACK_ENABLED`` "Enable/disable feedback system"
  (``crates/codegen/xai-grok-pager/docs/user-guide/05-configuration.md`` at
  PINNED_COMMIT), which is also where ``GROK_HOME`` is described.
- **Credentials** come from the shell as ``XAI_API_KEY``, or from a prior
  ``grok login``: "The example below assumes ``grok`` is already authenticated
  locally, or ``XAI_API_KEY`` is set" (headless-scripting). Env NAMES are pinned
  in operator config and values are read at spawn, never written down here.
- Grok Build installs as a native binary, so the operator pins ONE absolute
  path and this module puts nothing in front of it.

Three things the sources do NOT settle, and each bounds what may be claimed:

**No exit-code contract is published** for the one-shot mode, so the profile
declares ``exit_codes_published=False`` and every receipt says a zero is the
process having ended and nothing else. Under this build's law that is where a
zero stops anyway, so the weaker reading costs no capability.

**The literal form of a boolean environment value is not documented.** The
configuration guide describes the four switches as "Enable/disable" without
stating which strings count, and the only demonstrated forms anywhere near them
are ``GROK_MEMORY=1`` to enable and ``GROK_WORKFLOWS=0`` to disable. ``0`` is
therefore the demonstrated disable form and the one sent, and this paragraph is
here so a reader knows it is a demonstrated form rather than a stated rule. The
opt-in real smoke against a real install is what would show a switch not taking.

**The channel is parsed and then discarded.** ``channel_label()`` is quoted
above, so its spelling is a citation rather than the guess an earlier draft of
this docstring called it. What remains a RULING rather than a fact is that only
the semver decides: ``1.0.5 [alpha]`` is accepted as the reviewed version,
because the owner's rule for this provider is that the commit and the channel
never become the version. If an alpha build should instead be refused as a
different build line, that is a change of admission policy and belongs in review,
not in a quiet edit here.

**The pinned commit is one patch AHEAD of the reviewed version.**
``crates/codegen/xai-grok-pager-bin/Cargo.toml`` reads ``version = "1.0.6"`` at
PINNED_COMMIT, while the reviewed release is 1.0.5. Every fact above is a fact
about the printed FORM, which that tree pins exactly; none of them is the version
number itself, which comes from the published changelog. Said out loud because a
module whose method is "pin the exact bytes" owes a reader the version those
bytes came from.

Everything after the pin is the shared headless transport in ``headless_cli``:
one fresh ``GROK_HOME`` per attempt discarded when the spawn returns, an exact
version preflight before any prompt, code-owned argv down to the last token,
bounded and drained output that reaches no receipt, journal, API, SSE frame,
evidence or exception message, a marker that stops a crashed prompt from running
twice, and verification that reads only independent workspace evidence.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from .deep_contracts import DeepProtocol
from .harness_workspace import INSTRUCTION_DIR, WORK_DIR
from .headless_cli import (
    DISPATCH_CAPABILITY,
    ExecutablePin,
    HarnessProfile,
    HeadlessCliError,
    HeadlessCliTransport,
    _version_token,
)
from .process import ProcessRunner

#: The graph node this provider binds to; ``conductor.harnesses`` registers it.
GROK_PROVIDER_ID = "grok-build"
#: The exact published version this build was reviewed against: the latest
#: stable release, 2026-08-15. A preflight reading anything else refuses.
REVIEWED_GROK_VERSION = "1.0.5"
#: The protocol token an operator pins to select this adapter.
GROK_PROTOCOL = DeepProtocol.GROK_HEADLESS_V1.value
#: Experimental is said in the one field the Cockpit projection carries.
GROK_DISPLAY_NAME = "Grok Build (headless, experimental)"
#: Observation, and the one control this adapter really implements.
GROK_CAPABILITIES = ("observe", DISPATCH_CAPABILITY)
GROK_SCHEMA_PAIRS = ((DISPATCH_CAPABILITY, "deep-arguments-v1"),)
#: The four seams the registration door requires of every provider.
GROK_LIFECYCLE = ("execute", "observe", "prepare", "verify")
#: The environment NAME whose VALUE is minted fresh per attempt.
GROK_HOME_ENV = "GROK_HOME"
#: The four documented switches, and the value that turns each off. ``0`` is the
#: demonstrated disable form; see the module docstring on why it is demonstrated
#: rather than stated.
GROK_TELEMETRY_ENV = "GROK_TELEMETRY_ENABLED"
GROK_TRACE_UPLOAD_ENV = "GROK_TELEMETRY_TRACE_UPLOAD"
GROK_MIXPANEL_ENV = "GROK_TELEMETRY_MIXPANEL_ENABLED"
GROK_FEEDBACK_ENV = "GROK_FEEDBACK_ENABLED"
SWITCHED_OFF = "0"
GROK_FORCED_ENV = (
    (GROK_TELEMETRY_ENV, SWITCHED_OFF),
    (GROK_TRACE_UPLOAD_ENV, SWITCHED_OFF),
    (GROK_MIXPANEL_ENV, SWITCHED_OFF),
    (GROK_FEEDBACK_ENV, SWITCHED_OFF),
)
#: The code-owned flags. No caller contributes one, and the prompt stands LAST so
#: no token after it could be taken for a flag. ``--no-auto-update`` stands
#: FIRST: a background update check during a dispatch would change the very
#: build the preflight just proved.
NO_AUTO_UPDATE_ARGV = ("--no-auto-update",)
OUTPUT_FORMAT_ARGV = ("--output-format", "plain")
#: ``-p`` and ``--single`` are one flag; the long spelling is used so a reader of
#: the argv cannot mistake it for anything else.
PROMPT_FLAG = "--single"
VERSION_ARGV = ("--version",)
#: Capture ceiling for either spawn; the pump drains past it and drops the rest.
GROK_OUTPUT_LIMIT = 16 * 1024
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: The two subtrees THIS provider owns beneath the project root.
HOME_DIR = ".grok-home"
MARKER_DIR = ".grok-marker"
#: The ONE closed form this module will read a version out of. It is the form the
#: CLI really prints, which is NOT the one the version crate builds -- see the
#: module docstring: the entry point wraps that string as ``"grok {}\n"``, and a
#: release binary always carries a commit because ``set_full_version`` is called
#: unconditionally. So the program name is part of the line.
#:
#: The commit is any parenthesised run of non-space, non-paren characters rather
#: than a hex hash of a chosen length. Two published forms demanded that: the
#: build script falls back to the literal ``unknown`` when git is unavailable,
#: and ``git rev-parse --short`` honours ``core.abbrev``, so the length is the
#: builder's setting and never a fact this module may assume.
#:
#: Still anchored at both ends. What the anchors buy is unchanged: an unanchored
#: pattern finds ``1.0.5`` inside a warning line or inside a commit hash and
#: calls that the version. What they must not do is refuse the real thing, which
#: is exactly what they did while the ``grok `` prefix was missing from here.
_VERSION_FORM = re.compile(
    r"\A(?:grok )?"
    r"(?P<semver>\d+\.\d+\.\d+)"
    r"(?: \((?P<commit>[^()\s]+)\))?"
    r"(?: \[(?P<channel>stable|alpha)\])?\Z")

__all__ = [
    "GROK_CAPABILITIES", "GROK_DISPLAY_NAME", "GROK_FORCED_ENV", "GROK_HOME_ENV",
    "GROK_LIFECYCLE", "GROK_PROTOCOL", "GROK_PROVIDER_ID", "GROK_SCHEMA_PAIRS",
    "HOME_DIR", "INSTRUCTION_DIR", "MARKER_DIR", "REVIEWED_GROK_VERSION",
    "WORK_DIR",
    "GrokBuildAdapter", "GrokBuildError", "grok_pin",
]

#: Every vendor fact above, gathered where the shared transport reads them.
GROK_PROFILE = HarnessProfile(
    tool_noun="Grok Build", task_noun="Grok Build prompt",
    display_name=GROK_DISPLAY_NAME, vendor="xAI",
    docs_url="https://docs.x.ai/build/overview",
    reviewed_version=REVIEWED_GROK_VERSION,
    home_dir=HOME_DIR, marker_dir=MARKER_DIR,
    home_env=GROK_HOME_ENV, forced_env=GROK_FORCED_ENV,
    version_argv=VERSION_ARGV, exit_codes_published=False,
    capability=DISPATCH_CAPABILITY, output_limit=GROK_OUTPUT_LIMIT,
    version_timeout_seconds=VERSION_TIMEOUT_SECONDS,
    home_id_kind="grok-home")


class GrokBuildError(HeadlessCliError):
    """Grok Build cannot be driven without breaking one of this adapter's rules."""


def grok_pin(executable: str, env_allow: tuple[str, ...] = ()) -> ExecutablePin:
    """Grok Build's pin: ONE absolute path, and Grok Build's own refusal type.

    One, not two: Grok Build installs as a native binary and runs no
    interpreter, so there is no second half for this build to guess at.
    """
    return ExecutablePin(
        executable=executable, error=GrokBuildError, env_allow=env_allow)


class GrokBuildAdapter(HeadlessCliTransport):
    """Run one Grok Build prompt per authorized action, and prove nothing more."""

    profile = GROK_PROFILE
    error = GrokBuildError

    def __init__(
            self, pin: ExecutablePin, runner: ProcessRunner, *,
            root: str | Path, clock: Callable[[], str],
            ids: Callable[[str], str],
            adapter_id: str = GROK_PROVIDER_ID) -> None:
        if type(pin) is not ExecutablePin or pin.error is not GrokBuildError:
            raise GrokBuildError(
                "this adapter requires a single-executable pin of its own")
        self._pin = pin
        super().__init__(
            runner, root=root, clock=clock, ids=ids, adapter_id=adapter_id)

    def _argv_prefix(self) -> tuple[str, ...]:
        """One native binary, and nothing in front of it."""
        return (self._pin.executable,)

    def _task_argv(self, task_text: str) -> tuple[str, ...]:
        """``--no-auto-update --output-format plain --single <task>``."""
        return (*NO_AUTO_UPDATE_ARGV, *OUTPUT_FORMAT_ARGV, PROMPT_FLAG, task_text)

    def _env_allow(self) -> tuple[str, ...]:
        return self._pin.env_allow

    def _version_matches(self, output: bytes) -> bool:
        """PARSE the published form, and compare only its semver.

        The shared default compares the whole first line, which would refuse
        every real Grok Build that prints its commit or its channel. So this
        reads the closed form the vendor's own version module builds and takes
        the semver out of it -- and the short commit and the channel label are
        never allowed to become a version, which is the point of a closed
        pattern anchored at both ends rather than a search.

        Still a BOOLEAN. Nothing derived from the child's bytes leaves this
        method, because a hostile build could put a secret where a version
        belongs and every road out of here reaches a receipt.
        """
        found = _VERSION_FORM.match(_version_token(output))
        if found is None:
            return False
        return found.group("semver") == self.profile.reviewed_version
