"""Grok Build, driven headlessly: one pinned binary, one prompt, one attempt.

The active V1 task is read-only review over --prompt-file in a fresh attempt home, with an
access-only subscription relay. Grok returns a JSON terminal response. Only its successful
text may become the review artifact. Dispatch argv below is dormant test coverage; historical
--single documentation describes the earlier transport, not the active task channel.

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
  whole line is traced here from the ENTRY POINT this adapter actually drives --
  the top-level ``--version`` flag -- outward:

  * ``crates/codegen/xai-grok-pager-bin/src/main.rs`` answers that flag in
    ``dispatch_version_if_requested``, which calls ``write_version``, whose
    ``version_text`` builds the line as ``format!("grok {}\\n",
    display_version_with_commit(full_version(), channel_label))`` -- so **the
    program name is part of the printed line**, and it is not optional. The
    ``version`` subcommand's non-JSON arm calls the same ``write_version``;
  * ``set_full_version(env!("VERSION_WITH_COMMIT"))`` is the FIRST statement of
    that ``main``, ahead of ``PagerArgs::parse_cli()`` and therefore ahead of
    the dispatch above -- so **a commit is already set before anything prints**.
    Not usually: on every road through the binary;
  * ``crates/codegen/xai-grok-pager-bin/build.rs`` sets that variable as
    ``"{version} ({commit})"`` -- the parentheses live in the format string, so
    they stand on EVERY path -- from ``git rev-parse --short HEAD``, trimmed,
    falling back to the literal ``unknown`` when git is unavailable. So the
    commit is lowercase hex or that one word, and its LENGTH runs 4 to 40:
    ``core.abbrev`` chooses it, but git refuses a setting below 4 outright and
    clamps one above the object name, which is 40 digits in this SHA-1 tree;
  * ``crates/codegen/xai-grok-version/src/lib.rs`` appends the channel with
    ``format!("{}{}", version_with_commit, channel_label)``, and
    ``crates/codegen/xai-grok-update/src/version.rs``'s ``channel_label()``
    returns exactly ``" [alpha]"``, ``" [stable]"`` or ``""`` -- bracketed, with
    a leading space. The channel, alone of the three, really is optional.

  So the real first line is ``grok 1.0.5 (abc1234) [stable]``, and the parser
  below reads that. An earlier version of this module modelled the crate alone,
  refused every string a real install prints, and would have made this provider
  advertise itself available while failing every preflight forever.

  **The one fallback that is not a published form.** ``full_version()`` reads
  ``FULL_VERSION.get().copied().unwrap_or(VERSION)``, so the CRATE can yield a
  bare semver carrying no commit, and ``display_version_with_commit`` can be
  called directly without the wrapper. The correction of the defect above read
  those two facts as licence to make the ``grok `` prefix and the commit
  optional, and that was the more expensive error of the two: neither is
  reachable from the binary, because ``set_full_version`` runs before argument
  parsing and ``--version`` has exactly one handler. What it bought instead was
  that any executable printing the five bytes ``1.0.5`` cleared the one
  preflight standing between an operator's pin and a real prompt. **A form the
  crate can build is not a form the program prints**, and only the second is
  this preflight's subject.
- The current Windows pin prints ``grok 1.0.13 (5e9a58528b76)``. The older
  1.0.5 release described below returned HTTP 426 on the subscription service.
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
the semver decides: a reviewed semver with the alpha suffix is accepted,
because the owner's rule for this provider is that the commit and the channel
never become the version. If an alpha build should instead be refused as a
different build line, that is a change of admission policy and belongs in review,
not in a quiet edit here.

**Source history for the original version parser.**
``crates/codegen/xai-grok-pager-bin/Cargo.toml`` reads ``version = "1.0.6"`` at
PINNED_COMMIT, while the originally reviewed release was 1.0.5. Every fact above is a fact
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

from . import login_home, task_file
from ..artifacts import ARTIFACT_CONTENT_LIMIT
from .quota_connection import NativeQuotaReadError
from .service_metadata import ServiceMetadata
from .jsonl_completion import decode_line
from .deep_commands import GROK_PROVIDER_ID, GROK_SESSION_PHASE
from .grok_stream import STREAM_OUTPUT_LIMIT, decode_stream
from .subscription_quota import SubscriptionRpc, native_subscription_connection
from .grok_relay import GROK_AUTH_FIELDS, GROK_AUTH_CREDENTIALS, GROK_RELAY
from .relay_env import GROK_COMPAT_ENV, GROK_ROUTE_ENV

from .quota_contracts import NativeQuotaReading, NativeQuotaWindow, QuotaError, QuotaPolicy, quota_object

import json
import re
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType

from .deep_contracts import DeepProtocol
from .artifact_transport import ArtifactAwareTransport, REVIEW_CAPABILITY
from .harness_workspace import INSTRUCTION_DIR, WORK_DIR
from .headless_cli import (
    TASK_CHANNEL_FILE,
    DISPATCH_CAPABILITY,
    ExecutablePin,
    HarnessProfile,
    HeadlessCliError,
    _version_token,
)
from .process import ProcessRunner

#: The graph node this provider binds to; ``conductor.harnesses`` registers it.
#: The exact published version this build was reviewed against: the latest
#: stable release, 2026-08-15. A preflight reading anything else refuses.
REVIEWED_GROK_VERSION = "1.0.13"
#: The protocol token an operator pins to select this adapter.
GROK_PROTOCOL = DeepProtocol.GROK_HEADLESS_V1.value
#: Experimental is said in the one field the Cockpit projection carries.
GROK_DISPLAY_NAME = "Grok Build (headless, experimental)"
#: The shared dispatch schema remains declared, but task_modes refuses that road in V1.
GROK_CAPABILITIES = ("observe", DISPATCH_CAPABILITY, REVIEW_CAPABILITY)
GROK_SCHEMA_PAIRS = ((DISPATCH_CAPABILITY, "deep-arguments-v1"),
                     (REVIEW_CAPABILITY, "deep-arguments-v1"))
#: The four seams the registration door requires of every provider.
GROK_LIFECYCLE = ("execute", "observe", "prepare", "verify")
#: The environment NAME whose VALUE is minted fresh per attempt.
GROK_HOME_ENV = "GROK_HOME"
GROK_LOGIN_ARGV = ("--no-auto-update", "login")
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
    # G0b / H5-GROK-DIAGNOSE addendum 1: metadata children run outside the task boundary too.
    # Disable imports from personal profiles on every child; operator values cannot enable them.
    *GROK_COMPAT_ENV,
)
#: The code-owned flags. The task travels only in a fresh attempt-home file; the
#: command line names it and carries no task text. Disable update checks on every task.
NO_AUTO_UPDATE_ARGV = ("--no-auto-update",)
OUTPUT_FORMAT_ARGV = ("--output-format", "plain")
#: What a DISPATCH may do that headless mode forbids by default (spec 10.2, review ruling of
#: 28.09.2026). A headless run without auto-approval denies the Edit and Write tools -- measured
#: live, a dispatch ended "no changed file" -- and the pinned headless guide documents ``--allow``
#: as repeatable. The tool names are case-sensitive at PINNED_COMMIT
#: (``xai-grok-workspace/src/permission/rules.rs``), and Bash is a separate rule that stays
#: gated. These two pairs stand in the dormant dispatch argv ONLY. Active review instead
#: permits Read/Grep/Glob and explicitly denies edit, shell, web and MCP tools below.
ALLOW_FLAG = "--allow"
DISPATCH_ALLOWED_TOOLS = ("Edit", "Write")
DISPATCH_PERMISSION_ARGV = tuple(
    token for tool in DISPATCH_ALLOWED_TOOLS for token in (ALLOW_FLAG, tool))
#: Review may read, never edit or run a shell/web/MCP tool. OS review rights remain authoritative.
REVIEW_PERMISSION_ARGV = ("--allow", "Read", "--allow", "Grep", "--allow", "Glob",
                          "--deny", "Edit", "--deny", "Bash", "--deny", "WebFetch",
                          "--deny", "WebSearch", "--deny", "MCPTool")
VERSION_ARGV = ("--version",)
#: Preserve the existing metadata and marked diagnostic stream budget.
GROK_OUTPUT_LIMIT = STREAM_OUTPUT_LIMIT
#: A JSON string may encode one UTF-8 byte as six ASCII bytes (\uXXXX).
#: The separate 256 KiB metadata allowance is a code-owned budget, not a measured reply size.
GROK_JSON_WIRE_LIMIT = 6 * ARTIFACT_CONTENT_LIMIT + 256 * 1024
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: The two subtrees THIS provider owns beneath the project root.
HOME_DIR = ".grok-home"
MARKER_DIR = ".grok-marker"
#: The ONE closed form this module will read a version out of, closed on three
#: sides. It is the form the CLI really prints, which is NOT the one the version
#: crate builds -- see the module docstring, which traces every part of it to the
#: statement that writes it.
#:
#: ``grok `` and the parenthesised commit are REQUIRED, because every road
#: through the binary produces both: the entry point wraps the line as
#: ``"grok {}\n"``, and ``set_full_version`` is ``main``'s first statement, so
#: it has run before the flag is even parsed. Only the channel is optional,
#: because only ``channel_label()`` genuinely returns ``""``.
#:
#: The commit is lowercase hex of 4 to 40 digits, OR the literal ``unknown``.
#: That is the whole set the build script can emit: ``git rev-parse --short
#: HEAD`` writes the hex, and its one fallback writes that one word.
#:
#: Both bounds are MEASURED, not assumed, and an earlier draft left the length
#: open precisely because it looked unmeasurable -- ``core.abbrev`` chooses it,
#: so a bound seemed to be this module assuming a builder's setting. It is not,
#: because git refuses the settings outside the range rather than honouring them
#: (checked against git 2.52.0):
#:
#: * below 4, ``git rev-parse`` FAILS -- "abbrev length out of range" -- and the
#:   build script's fallback turns that whole branch into ``unknown``. So a
#:   one-, two- or three-digit commit is not rare, it is unreachable;
#: * above the object name's length it is clamped to the object name, and the
#:   pinned tree is SHA-1: PINNED_COMMIT is itself 40 hex digits. So 40 is the
#:   ceiling for THIS repository, and the day xAI moves it to SHA-256 that
#:   ceiling becomes 64 -- the one fact that would reopen this bound.
#:
#: An unbounded run of hex is not a weaker version of this rule; it is a
#: different rule, and it admitted a one-character and a 200-character commit
#: from a binary that is not Grok Build.
#:
#: Still anchored at both ends, and now closed at the front as well. What the
#: anchors buy is unchanged: an unanchored pattern finds ``1.0.5`` inside a
#: warning line or inside a commit hash and calls that the version. The two
#: errors this pattern has already made are opposite, and both are refusals to
#: read the source: too narrow refused every real install, while an optional
#: prefix and an optional commit admitted a bare ``1.0.5`` from any executable
#: whatsoever -- and only the second one still looked green.
_VERSION_FORM = re.compile(
    r"\Agrok "
    r"(?P<semver>\d+\.\d+\.\d+)"
    r" \((?P<commit>[0-9a-f]{4,40}|unknown)\)"
    r"(?: \[(?P<channel>stable|alpha)\])?\Z")

__all__ = [
    "GROK_CAPABILITIES", "GROK_DISPLAY_NAME", "GROK_FORCED_ENV", "GROK_HOME_ENV",
    "GROK_LIFECYCLE", "GROK_PROTOCOL", "GROK_PROVIDER_ID", "GROK_SCHEMA_PAIRS",
    "HOME_DIR", "INSTRUCTION_DIR", "MARKER_DIR", "REVIEWED_GROK_VERSION",
    "WORK_DIR",
    "GrokBuildAdapter", "GrokBuildError", "grok_pin",
]

GROK_PROFILE = HarnessProfile(
    tool_noun="Grok Build", task_noun="Grok Build prompt",
    display_name=GROK_DISPLAY_NAME, vendor="xAI",
    docs_url="https://docs.x.ai/build/overview",
    reviewed_version=REVIEWED_GROK_VERSION,
    home_dir=HOME_DIR, marker_dir=MARKER_DIR,
    home_env=GROK_HOME_ENV, forced_env=GROK_FORCED_ENV,
    version_argv=VERSION_ARGV, exit_codes_published=False,
    login_argv=("--no-auto-update", "agent", "stdio"), login_command=GROK_LOGIN_ARGV,
    login_credentials=("auth.json",),
    login_scratch=("logs", "sessions", "active_sessions.json", "active_sessions.lock",
                   ".config-init.lock", "managed_config.lock",
                   # MEASURED (1.0.5, 28.10.2026): a spawn that starts the agent writes these two.
                   # Their `-wal` and `-shm` are not declared: one that appears is a residue.
                   "models_cache.json", "worktrees.db"),
    login_expected=("auth.json", "config.toml", ".metadata_version", "agent_id", "docs", "README.md"),
    login_forbidden=("mcp_credentials.json", "mcp.json", "hooks", "plugins", "skills", "lsp.json"),
    capability=DISPATCH_CAPABILITY, output_limit=GROK_JSON_WIRE_LIMIT,
    task_channel=TASK_CHANNEL_FILE, login_relay=GROK_RELAY,
    version_timeout_seconds=VERSION_TIMEOUT_SECONDS,
    home_id_kind="grok-home")


class GrokBuildError(HeadlessCliError):
    """Grok Build cannot be driven without breaking one of this adapter's rules."""


def grok_pin(executable: str, env_allow: tuple[str, ...] = (), *,
             auth: str = "api_key", auth_home: str = "") -> ExecutablePin:
    """Grok Build's pin: ONE absolute path, and Grok Build's own refusal type.

    One, not two: Grok Build installs as a native binary and runs no
    interpreter, so there is no second half for this build to guess at.
    """
    return ExecutablePin(
        executable=executable, error=GrokBuildError, env_allow=env_allow,
        auth=auth, auth_home=auth_home)


class GrokBuildAdapter(ServiceMetadata, ArtifactAwareTransport):
    """Run one read-only Grok review; dispatch and independent checking remain closed."""

    profile = GROK_PROFILE
    error = GrokBuildError
    review_enabled = True
    review_output_format = "json"
    serves_checks = False
    task_modes = ("review",)

    def __init__(
            self, pin: ExecutablePin, runner: ProcessRunner, *,
            root: str | Path, clock: Callable[[], str],
            ids: Callable[[str], str],
            adapter_id: str = GROK_PROVIDER_ID) -> None:
        if type(pin) is not ExecutablePin or pin.error is not GrokBuildError:
            raise GrokBuildError(
                "this adapter requires a single-executable pin of its own")
        self._pin = pin
        self.review_diagnostic_version = GROK_SESSION_PHASE if (
            pin.auth == "subscription" and adapter_id == GROK_PROVIDER_ID) else None
        super().__init__(
            runner, root=root, clock=clock, ids=ids, adapter_id=adapter_id)

    def _argv_prefix(self) -> tuple[str, ...]:
        """One native binary, and nothing in front of it."""
        return (self._pin.executable,)

    def _stdin_argv(self, home: Path, model: str | None) -> tuple[str, ...]:
        """Dormant dispatch builder, exercised only by an explicitly enabled test subclass."""
        return (*NO_AUTO_UPDATE_ARGV, *OUTPUT_FORMAT_ARGV, *DISPATCH_PERMISSION_ARGV,
                "--prompt-file", task_file.path_in(home))

    def _review_argv(self, home: Path, model: str | None) -> tuple[str, ...]:
        return self._review_format_argv(home, self.review_output_format)

    def _review_command(self, request):
        if request.arguments.get("grok_diagnostic") == GROK_SESSION_PHASE:
            return lambda home, model: self._review_format_argv(home, "streaming-messages-json")
        return self._review_argv

    def _review_output_limit(self, request):
        return (GROK_OUTPUT_LIMIT if request.arguments.get("grok_diagnostic") == GROK_SESSION_PHASE
                else GROK_JSON_WIRE_LIMIT)

    def _attempt(self, argv, cwd, **options):
        # Only an explicitly budgeted review may use the larger JSON wire ceiling.
        asked = options.get("output_limit")
        if asked is None:
            asked = GROK_OUTPUT_LIMIT
        if options.get("mode") != "review":
            asked = min(asked, GROK_OUTPUT_LIMIT)
        options["output_limit"] = asked
        return super()._attempt(argv, cwd, **options)

    @staticmethod
    def _review_format_argv(home, output_format):
        return (*NO_AUTO_UPDATE_ARGV, "--output-format", output_format,
                *REVIEW_PERMISSION_ARGV,
                "--prompt-file", task_file.path_in(home))

    def _review_response(self, request, outcome, relation):
        receipt = self._observed(request, outcome)
        if outcome.status != "completed" or outcome.output_truncated:
            return b"", receipt
        if self._review_attempt_carries(outcome):
            return b"", self._receipt(request, "failed", None,
                                      "the review contained sensitive output")
        if request.arguments.get("grok_diagnostic") == GROK_SESSION_PHASE:
            content, reason = decode_stream(outcome.output, outcome.exit_code)
            if reason is not None:
                return b"", self._receipt(request, "failed", outcome.exit_code or None, reason)
            if any(value and value in content for value in self._sensitive_values(relation)):
                return b"", self._receipt(request, "failed", None,
                                          "the review contained sensitive output")
            return content, receipt
        try:
            doc = decode_line(outcome.output)
            if outcome.exit_code != 0:
                if doc.get("type") == "error" and isinstance(doc.get("message"), str):
                    reason = _grok_error_reason(doc)
                    receipt = self._receipt(request, "failed", outcome.exit_code, reason)
                return b"", receipt
            if "type" in doc or "message" in doc or doc.get("stopReason") != "end_turn":
                raise ValueError
            text = doc.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError
            content = text.encode("utf-8")
            if any(value and value in content for value in self._sensitive_values(relation)):
                return b"", self._receipt(request, "failed", None,
                                          "the review contained sensitive output")
            if len(content) > ARTIFACT_CONTENT_LIMIT:
                return b"", self._receipt(request, "failed", None,
                    "the review result exceeded the artifact byte limit")
            return content, receipt
        except (ValueError, UnicodeError, RecursionError):
            if outcome.exit_code == 0:
                receipt = self._receipt(request, "failed", None,
                                        "the review returned an invalid terminal response")
            return b"", receipt

    def _task_stdin(self, task_text: str) -> bytes:
        return task_text.encode("utf-8")

    def _env_allow(self) -> tuple[str, ...]:
        return self._pin.env_allow

    def _login(self) -> tuple[str, str]:
        return self._pin.auth, self._pin.auth_home

    def _login_home_grants(self, home: str) -> tuple[str, ...]:
        blocked = tuple(name for name in super()._login_home_grants(home) if name != "config.toml")
        if not login_home.plain_config(home, "config.toml", LOGIN_CONFIG_FORMS):
            blocked += ("config.toml",)
        selected = self._runner.capture_environment(self._env_allow())
        if any(selected.native_value(name) is not None for name in GROK_LOGIN_OVERRIDES):
            blocked += ("environment",)
        return blocked

    def _attempt_login_status(self, request):
        return self._attempt(GROK_AUTH_RPC.argv, WORK_DIR,
            timeout=min(self.profile.version_timeout_seconds, request.timeout_seconds),
            stdin_bytes=GROK_AUTH_RPC.payload, separate_stderr=True, stdin_completion_id=2)

    def _login_method_admitted(self, output: bytes) -> bool:
        try:
            return GROK_AUTH_RPC.decode(output).get("methodId") == "cached_token"
        except NativeQuotaReadError:
            return False

    def quota_connection(self):
        return native_subscription_connection(self, QUOTA_POLICY, GROK_QUOTA_RPC)

    def _service_for(self, argv, stdin_bytes: bytes | None) -> SubscriptionRpc | None:
        return _SERVICE_BY_PAYLOAD.get(stdin_bytes) if argv == _RPC_ARGV else None

    def _reply_metadata(self) -> dict[str, frozenset[bytes]]:
        home = self._signed_in_road()
        if not home:
            return {}
        (name,) = self.profile.login_credentials
        return _reply_metadata(login_home.credential_document(home, name))

    def _masked_reply(self, output: bytes, service: SubscriptionRpc,
                      own_fields: dict[str, frozenset[bytes]]) -> bytes:
        return _masked_reply(output, service, own_fields)

    def _parsed_version(self, output: bytes) -> str | None:
        r"""The semver this parser reads out of a version print, or ``None``.

        Separate from the yes/no answer, and the separation is what makes the
        opt-in smoke able to tell two opposite findings apart. A BOOLEAN cannot:
        ``False`` means either "a different build", which the adapter is right
        to refuse, or "this parser could not read the published form at all",
        which no refusal repairs -- and a parser accepting NOTHING refuses
        everything, which looks exactly like working correctly.

        That is not hypothetical here. Replacing this module's pattern with one
        that matches nothing, against a valid published form at an unreviewed
        version, passed the smoke and every refusal test in the suite.

        **What may be done with the answer.** It is a substring of child output,
        so it stays inside this class and inside tests: no production path puts
        it in a receipt, a journal record, an API response or an exception
        message. What makes that bearable rather than merely promised is the
        pattern -- the group is ``\d+\.\d+\.\d+`` and can carry digits and dots
        and nothing else, so unlike a whole line it cannot hold a secret a
        hostile build planted where a version belongs. The commit and the
        channel are read and DISCARDED here, and never returned.
        """
        found = _VERSION_FORM.match(_version_token(output))
        return None if found is None else found.group("semver")

    def _version_matches(self, output: bytes) -> bool:
        """Whether the pinned build's print IS the reviewed version.

        The shared default compares the whole first line, which would refuse
        every real Grok Build, because a real one always prints its commit and
        usually its channel. So the reading is delegated to ``_parsed_version``
        -- which reads the closed form the vendor's ENTRY POINT prints, not the
        one its version module builds -- and this method only compares. The
        short commit and the channel label are never allowed to become a
        version, which is the point of a closed pattern anchored at both ends
        rather than a search.
        """
        return self._parsed_version(output) == self.profile.reviewed_version




# These are emitter signatures. An unwrapped ACP error can quote the same text.
_STARTUP_REASONS = {
    "Couldn't start session": "the harness reported an embedded agent startup failure",
    "Couldn't initialize": "the harness reported an agent initialization failure",
    "Couldn't create session": "the harness reported a task session opening failure",
}


def _grok_error_reason(doc):
    """Only product-owned categories may leave this module."""
    message = doc["message"]
    text = message.casefold().strip().removesuffix(".")
    prefix, _, detail = message.partition(": ")
    phase = _STARTUP_REASONS.get(prefix) if detail.strip() else None
    normalized_prefix = text.partition(":")[0]
    if phase is None and any(label.casefold() == normalized_prefix for label in _STARTUP_REASONS):
        phase = "the harness reported a session startup failure"
    elif message == "Connection closed unexpectedly":
        phase = "the harness reported that its local prompt channel closed"
    if phase is not None:
        # Prompt errors can carry spending fields along with arbitrary text.
        if "usage" in doc or "usage_is_incomplete" in doc:
            return _unclassified_grok_error(doc)
        return phase
    if text.startswith("not signed in"):
        return "the harness reported that sign-in is required"
    if "rate limit" in text or "quota exceeded" in text or "too many requests" in text:
        return "the harness reported a subscription usage limit"
    if "subscription required" in text or "requires a subscription" in text:
        return "the harness reported that a subscription is required for this task"
    if "model" in text and any(word in text for word in ("unsupported", "not supported", "not found")):
        return "the harness reported that the requested model is unavailable"
    if text == "max turns reached":
        return "the harness reported that the turn limit was reached"
    if (text == "grok build is not yet available for this account"
            or any(word in text for word in ("permission denied", "forbidden", "unauthorized"))):
        return "the harness reported an access refusal"
    if (text == "connection closed unexpectedly"
            or any(word in text for word in ("connection refused", "connection reset", "dns error"))):
        return "the harness reported a connection failure"
    return _unclassified_grok_error(doc)


def _unclassified_grok_error(doc):
    usage = doc.get("usage")
    total = usage.get("total_tokens") if isinstance(usage, dict) else None
    if type(total) is int and total > 0:
        return "the harness reported an unclassified service error with recorded token usage"
    if doc.get("usage_is_incomplete") is True:
        return "the harness reported an unclassified service error with incomplete usage data"
    return "the harness reported an unclassified service error"


def _native_quota(payload):
    """ACP x.ai/billing percentage schema; legacy monetary budgets stay separate."""
    body = quota_object(payload)
    windows = []
    raw = body.get("config")
    if raw is not None:
        config = quota_object(raw)
        period = config.get("currentPeriod")
        start = reset = duration = None
        name = "current"
        if period is not None:
            period = quota_object(period)
            kind = period.get("type")
            periods = {"USAGE_PERIOD_TYPE_WEEKLY": ("weekly", 10080),
                       "USAGE_PERIOD_TYPE_MONTHLY": ("monthly", None)}
            if kind is not None:
                if type(kind) is not str or kind not in periods:
                    raise QuotaError("unknown Grok usage period")
                name, duration = periods[kind]
            start, reset = period.get("start"), period.get("end")
        windows.append(NativeQuotaWindow("grok-subscription", name,
            config.get("creditUsagePercent"), reset, duration, start))
    return NativeQuotaReading(tuple(windows), policy=QUOTA_POLICY)


QUOTA_POLICY = QuotaPolicy("xai", "grok-account", "grok-acp", "quota", "rfc3339", _native_quota)

#: The bootstrap configuration a dedicated login profile may hold, compared as decoded values.
#: MEASURED on a real subscription login (1.0.5, 28.09.2026): the vendor's own login registers its
#: official marketplace as a source. A source installs nothing by itself; installed skills,
#: plugins, hooks and MCP stay forbidden in the login home (`login_forbidden`), so this exact
#: official form is admitted -- another source, or another address, is not.
LOGIN_CONFIG_FORMS = ({}, {"marketplace": {"default_skills_installs_purged": True}}, {
    "marketplace": {"default_skills_installs_purged": True,
                    "official_marketplace_auto_installed": True,
                    "sources": [{"name": "xAI Official",
                                 "git": "https://github.com/xai-org/plugin-marketplace.git"}]}})

# Native 1.0.5 ACP calibration: these metadata requests do not create a session
# or send a model prompt. Billing requires the native xAI session auth gate.
GROK_LOGIN_OVERRIDES = GROK_ROUTE_ENV
_RPC_ARGV = ("--no-auto-update", "agent", "stdio")
_RPC_INIT = (b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
             b'{"protocolVersion":1,"clientCapabilities":{},'
             b'"clientInfo":{"name":"conduct-quota","version":"1"}}}\n')
_RPC_INFO = b'{"jsonrpc":"2.0","id":2,"method":"_x.ai/auth/info","params":{}}\n'
_RPC_NOTIFICATIONS = ("_x.ai/mcp/servers_updated", "_x.ai/settings/update",
                      "_x.ai/announcements/update")
GROK_AUTH_RPC = SubscriptionRpc(_RPC_ARGV, _RPC_INIT+_RPC_INFO, (1, 2),
    ("_meta", "defaultAuthMethodId"), "cached_token", _RPC_NOTIFICATIONS)
GROK_QUOTA_RPC = SubscriptionRpc(_RPC_ARGV, _RPC_INIT+_RPC_INFO+
    b'{"jsonrpc":"2.0","id":3,"method":"_x.ai/billing","params":{}}\n',
    (1, 2, 3), ("methodId",), "cached_token", _RPC_NOTIFICATIONS)
_SERVICE_BY_PAYLOAD = MappingProxyType({GROK_AUTH_RPC.payload: GROK_AUTH_RPC,
                                        GROK_QUOTA_RPC.payload: GROK_QUOTA_RPC})
#: The id of the auth/info reply in both exchanges above.
_RPC_INFO_ID = 2

#: GROK_AUTH_FIELDS and GROK_AUTH_CREDENTIALS are reexported from the relay value module.
#: auth/info reply field -> the login field whose value it repeats. The first four are MEASURED
#: on a real subscription login (1.0.5, 28.09.2026, names only): the image URL carries the asset
#: id inside it, and (28.10.2026) the principal id inside the image URL. That the principal id
#: stands inside the asset id itself is read from the source (`handle_info`: the address is the
#: asset id, or `grok-asset:///` and it), not measured; the live read will confirm it. The nine
#: after them are the rest of what `handle_info` passes through from the login record (SOURCE,
#: `handle_info` in extensions/auth.rs at PINNED_COMMIT; not measured): each repeats its own
#: login field whole, so it is read at exact equality and nowhere else.
GROK_REPLY_METADATA = MappingProxyType({
    "email": "email", "teamId": "team_id", "principalId": "principal_id",
    "profileImageUrl": "profile_image_asset_id",
    "firstName": "first_name", "lastName": "last_name", "teamName": "team_name",
    "teamRole": "team_role", "organizationId": "organization_id",
    "organizationName": "organization_name", "organizationRole": "organization_role",
    "principalType": "principal_type", "userBlockedReason": "user_blocked_reason"})
#: The leak scan's own floor for a login value (`login_home.credential_values`).
_SECRET_FLOOR = 12


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [row for item in value.values() for row in _strings(item)]
    if isinstance(value, list):
        return [row for item in value for row in _strings(item)]
    return []


def _reply_metadata(document: object) -> dict[str, frozenset[bytes]]:
    """The login values a verified reply may repeat, by login field.

    A value that equals, holds or sits inside a credential -- or a value of a
    field the vendor's schema does not name -- is never admitted: the key wins.
    A file of any other shape admits nothing.
    """
    records = list(document.values()) if type(document) is dict else []
    if not records or any(type(record) is not dict for record in records):
        return {}
    keys = [value.encode("utf-8") for record in records for name, item in record.items()
            if name in GROK_AUTH_CREDENTIALS or name not in GROK_AUTH_FIELDS
            for value in _strings(item) if len(value) >= _SECRET_FLOOR]
    admitted: dict[str, set[bytes]] = {}
    for record in records:
        for field in GROK_REPLY_METADATA.values():
            value = record.get(field)
            if type(value) is not str or len(value) < _SECRET_FLOOR:
                continue
            raw = value.encode("utf-8")
            if not any(raw in key or key in raw for key in keys):
                admitted.setdefault(field, set()).add(raw)
    return {field: frozenset(values) for field, values in admitted.items()}


def _masked_reply(output: bytes, service: SubscriptionRpc,
                  metadata: dict[str, frozenset[bytes]]) -> bytes:
    """The output with admitted metadata blanked in its own auth/info fields -- if verified.

    A transcript the exchange's own decoder refuses is returned whole, so nothing
    in it is admitted. Only the named reply fields are blanked, and only when they
    carry their own login field's value; an unknown field or a nested one stays.
    """
    try:
        service.decode(output)
    except NativeQuotaReadError:
        return output
    rows = []
    for line in output.splitlines():
        row = json.loads(line)
        result = row.get("result") if row.get("id") == _RPC_INFO_ID else None
        if type(result) is dict:
            result = {name: _mask_value(name, value, metadata)
                      for name, value in result.items()}
            line = json.dumps({**row, "result": result}, ensure_ascii=False).encode("utf-8")
        rows.append(line)
    return b"\n".join(rows)


def _mask_value(name: str, value: object, metadata: dict[str, frozenset[bytes]]) -> object:
    field = GROK_REPLY_METADATA.get(name)
    if field is None or type(value) is not str:
        return value
    raw = value.encode("utf-8")
    for known in metadata.get(field, ()):
        if raw == known:
            return ""
        if name == "profileImageUrl" and known in raw:
            return value.replace(known.decode("utf-8"), "", 1)
    return value
