"""Kimi Code, driven headlessly: one pinned binary, one prompt, one attempt.

The vendor contract this adapter is written against was read from Moonshot AI's
own published pages on 2026-08-21 and is recorded here so a later reader can
re-check it rather than trust this prose:

- the one-shot transport is ``--prompt <prompt>``, which "Run[s] a single prompt
  non-interactively and stream[s] the Assistant output to stdout. This mode does
  not open the TUI"; ``--output-format`` takes ``text`` or ``stream-json`` and
  "Can only be used with ``--prompt``; defaults to ``text``"; ``-V``/
  ``--version`` "Print[s] the version number and exit[s]"
  (moonshotai.github.io/kimi-code/en/reference/kimi-command.html);
- ``KIMI_CODE_HOME`` "Overrides the data root directory; the default is
  ``~/.kimi-code``. Once set, the config file, sessions, logs, OAuth credentials,
  and all other data land under the new path", and ``KIMI_DISABLE_TELEMETRY``
  is "Set to ``1`` to turn off anonymous telemetry reporting"
  (moonshotai.github.io/kimi-code/en/configuration/env-vars.html);
- credential variables such as ``KIMI_API_KEY`` are "not read automatically from
  shell environment variables", and the ONE exception is the ``KIMI_MODEL_*``
  family, "an explicit channel that does read credentials from the shell", where
  ``KIMI_MODEL_NAME`` is the enable switch and ``KIMI_MODEL_API_KEY`` is
  required alongside it (same page). That is exactly the shape this build's
  provider door already uses: names pinned in operator config, values read at
  spawn and never written down by this build;
- the latest published release is ``0.38.0`` (2026-08-20)
  (moonshotai.github.io/kimi-code/en/release-notes/changelog.html);
- the binary installs by script and needs no Node.js, so it pins no interpreter
  entrypoint -- unlike dsh, the operator pins ONE absolute path.

Two things the audit did NOT find, and both bound what this adapter may claim
rather than being papered over:

**No exit-code contract is published for ``--prompt``.** Exit codes are
documented for ``kimi login``, ``kimi doctor`` and the legacy ``kimi server``,
and for nothing else. So this provider's profile declares
``exit_codes_published=False`` and every receipt says so: a zero is read as the
process having ended and as nothing else. Under this build's law that is where a
zero stops anyway -- an exit code buys ``execution_observed`` and never
success -- so the weaker reading costs no capability, and stating it is the
difference between an honest observation and a borrowed one.

**The exact format of the version print is not published**, only that a version
number is printed. The comparison below is EXACT against ``0.38.0``, so a build
that prints its version with a prefix refuses the preflight instead of running a
task. That is the safe direction of a wrong guess -- a false refusal, never a
false spawn -- and the opt-in real smoke is what settles the format against a
real install. When it does, what changes is this constant, in review.

The pin is exact and this build discovers nothing: no ``PATH`` search, no home
scan, no installer, no "latest", and never ``shell=True``. Everything after the
pin is the shared headless transport in ``headless_cli`` -- a fresh
``KIMI_CODE_HOME`` per attempt that is discarded when the spawn returns, an
exact version preflight before any prompt is spawned, code-owned argv down to
the last token, bounded and drained output that reaches no receipt, journal,
API, SSE frame, evidence or exception message, a marker that stops a crashed
prompt from being run twice, and verification that reads only independent
workspace evidence and never answers ``verified`` while this build writes no
durable evidence record.

The home matters more here than the vendor's own default suggests. Because
``KIMI_CODE_HOME`` relocates "the config file, sessions, logs, OAuth credentials,
and all other data", a fresh one per attempt means this build never reads, keeps,
or hands onward a session or a credential the tool wrote -- and it also means the
tool starts each attempt with no operator session at all. A dispatch therefore
depends on the ``KIMI_MODEL_*`` channel the operator allowed by NAME, which is
the only credential road the vendor documents as reading the shell.
"""
from __future__ import annotations

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
)
from .process import ProcessRunner

#: The graph node this provider binds to. ``conductor.harnesses`` registers the
#: id ``kimi-code``, so a role that names it draws a real badge rather than the
#: neutral fallback an unregistered string gets.
KIMI_PROVIDER_ID = "kimi-code"
#: The exact published version this build was reviewed against, read from the
#: vendor's changelog on 2026-08-21. A preflight that reads anything else
#: refuses: the product ships several releases a week, and "close enough" is not
#: a safe reading of a version string for a tool whose flags may move with them.
REVIEWED_KIMI_VERSION = "0.38.0"
#: The protocol token an operator pins to select this adapter.
KIMI_PROTOCOL = DeepProtocol.KIMI_HEADLESS_V1.value
#: Experimental is said in the one field the Cockpit projection actually carries.
KIMI_DISPLAY_NAME = "Kimi Code (headless, experimental)"
#: Observation, and the one control this adapter really implements. stop, retry
#: and switch stay ABSENT, because none of them is implemented and the
#: registration door refuses a control an adapter cannot back.
KIMI_CAPABILITIES = ("observe", DISPATCH_CAPABILITY)
#: The one control binds the one reviewed deep argument schema.
KIMI_SCHEMA_PAIRS = ((DISPATCH_CAPABILITY, "deep-arguments-v1"),)
#: The four seams the registration door requires of every provider.
KIMI_LIFECYCLE = ("execute", "observe", "prepare", "verify")
#: The environment NAMES this adapter owns. Only names live in durable config;
#: the home's VALUE is minted per attempt and never written to any config.
KIMI_HOME_ENV = "KIMI_CODE_HOME"
KIMI_TELEMETRY_ENV = "KIMI_DISABLE_TELEMETRY"
#: The vendor documents ``1`` as the value that turns telemetry off.
TELEMETRY_DISABLED = "1"
#: The code-owned flags. No caller ever contributes one, and the prompt stands
#: LAST: ``--output-format`` is documented as usable only alongside ``--prompt``,
#: and putting the pair first leaves no token after the prompt that a parser
#: could take for a flag of its own.
OUTPUT_FORMAT_ARGV = ("--output-format", "text")
PROMPT_FLAG = "--prompt"
VERSION_ARGV = ("--version",)
#: Capture ceiling for either spawn; the pump drains past it and drops the rest.
KIMI_OUTPUT_LIMIT = 16 * 1024
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: The two subtrees THIS provider owns beneath the project root, named here in
#: the provider's own module: the workspace door bounds every delete on the home
#: name it is handed, so a second harness naming this one would take this
#: provider's attempts for its own.
HOME_DIR = ".kimi-home"
MARKER_DIR = ".kimi-marker"

__all__ = [
    "HOME_DIR", "INSTRUCTION_DIR", "KIMI_CAPABILITIES", "KIMI_DISPLAY_NAME",
    "KIMI_LIFECYCLE", "KIMI_PROTOCOL", "KIMI_PROVIDER_ID", "KIMI_SCHEMA_PAIRS",
    "MARKER_DIR", "REVIEWED_KIMI_VERSION", "WORK_DIR",
    "KimiCodeAdapter", "KimiCodeError", "kimi_pin",
]

#: Every vendor fact above, gathered where the shared transport reads them.
KIMI_PROFILE = HarnessProfile(
    tool_noun="Kimi Code", task_noun="Kimi Code prompt",
    display_name=KIMI_DISPLAY_NAME, vendor="Moonshot AI",
    docs_url="https://moonshotai.github.io/kimi-code/",
    reviewed_version=REVIEWED_KIMI_VERSION,
    home_dir=HOME_DIR, marker_dir=MARKER_DIR,
    home_env=KIMI_HOME_ENV, telemetry_env=KIMI_TELEMETRY_ENV,
    telemetry_disabled=TELEMETRY_DISABLED, version_argv=VERSION_ARGV,
    home_id_kind="kimi-home",
    exit_codes_published=False, capability=DISPATCH_CAPABILITY,
    output_limit=KIMI_OUTPUT_LIMIT,
    version_timeout_seconds=VERSION_TIMEOUT_SECONDS)


class KimiCodeError(HeadlessCliError):
    """Kimi Code cannot be driven without breaking one of this adapter's rules."""


def kimi_pin(executable: str, env_allow: tuple[str, ...] = ()) -> ExecutablePin:
    """Kimi Code's pin: ONE absolute path, and Kimi Code's own refusal type.

    One, not two: Kimi Code installs as a native binary and runs no interpreter,
    so there is no second half for this build to guess at. A provider whose pin
    shape is wrong is a provider that would need a path invented for it, and
    inventing one is the discovery this factory exists to refuse.
    """
    return ExecutablePin(
        executable=executable, env_allow=env_allow, error=KimiCodeError)


class KimiCodeAdapter(HeadlessCliTransport):
    """Run one Kimi Code prompt per authorized action, and prove nothing more."""

    profile = KIMI_PROFILE
    error = KimiCodeError

    def __init__(
            self, pin: ExecutablePin, runner: ProcessRunner, *,
            root: str | Path,
            clock: Callable[[], str], ids: Callable[[str], str],
            adapter_id: str = KIMI_PROVIDER_ID) -> None:
        if type(pin) is not ExecutablePin:
            raise KimiCodeError(
                "this adapter requires an exact single-executable pin")
        self._pin = pin
        super().__init__(
            runner, root=root, clock=clock, ids=ids, adapter_id=adapter_id)

    def _argv_prefix(self) -> tuple[str, ...]:
        """One native binary, and nothing in front of it."""
        return (self._pin.executable,)

    def _task_argv(self, task_text: str) -> tuple[str, ...]:
        """``--output-format text --prompt <task>``: the prompt is an option VALUE.

        A parser that expects a value after ``--prompt`` is a smaller injection
        surface than one that takes the first free token, but it is not zero --
        a parser could still read a leading dash as the next flag -- so the
        shared transport proves the token flagless before it gets here.
        """
        return (*OUTPUT_FORMAT_ARGV, PROMPT_FLAG, task_text)

    def _env_allow(self) -> tuple[str, ...]:
        return self._pin.env_allow
