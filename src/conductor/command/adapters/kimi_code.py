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
workspace evidence.

The home matters more here than the vendor's own default suggests. Because
``KIMI_CODE_HOME`` relocates "the config file, sessions, logs, OAuth credentials,
and all other data", a fresh one per attempt means this build never reads, keeps,
or hands onward a session or a credential the tool wrote -- and it also means the
tool starts each attempt with no operator session at all. A dispatch therefore
depends on the ``KIMI_MODEL_*`` channel the operator allowed by NAME, which is
the only credential road the vendor documents as reading the shell.
"""
from __future__ import annotations

import hashlib
import json
from . import login_home
from .jsonl_completion import decode_line
from .quota_connection import NativeQuotaDeferred, NativeQuotaReader, NativeQuotaReadError
from .subscription_quota import _Turn, _clean

from .quota_contracts import (
    NativeQuotaReading, NativeQuotaWindow, QuotaError, QuotaPolicy,
    quota_object, quota_percentage,
)

from collections.abc import Callable
from pathlib import Path

from .deep_contracts import DeepProtocol
from .artifact_transport import ArtifactAwareTransport
from .harness_workspace import INSTRUCTION_DIR, WORK_DIR
from .headless_cli import (
    DISPATCH_CAPABILITY,
    ExecutablePin,
    HarnessProfile,
    HeadlessCliError,
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
    home_env=KIMI_HOME_ENV,
    forced_env=((KIMI_TELEMETRY_ENV, TELEMETRY_DISABLED),),
    version_argv=VERSION_ARGV,
    home_id_kind="kimi-home",
    login_argv=("acp",), login_command=("login",),
    login_credentials=(), login_expected=("config.toml", "credentials", "server.token", "region"),
    login_scratch=("logs", "sessions", "server", "cache", "data", "device_id", "migrations-effort.json", "workspaces.json"),
    login_forbidden=("hooks", "plugins", "skills", "mcp.json", "agents"),
    exit_codes_published=False, capability=DISPATCH_CAPABILITY,
    output_limit=KIMI_OUTPUT_LIMIT,
    version_timeout_seconds=VERSION_TIMEOUT_SECONDS)


class KimiCodeError(HeadlessCliError):
    """Kimi Code cannot be driven without breaking one of this adapter's rules."""


def kimi_pin(executable: str, env_allow: tuple[str, ...] = (), *,
             auth: str = "api_key", auth_home: str = "") -> ExecutablePin:
    """Kimi Code's pin: ONE absolute path, and Kimi Code's own refusal type.

    One, not two: Kimi Code installs as a native binary and runs no interpreter,
    so there is no second half for this build to guess at. A provider whose pin
    shape is wrong is a provider that would need a path invented for it, and
    inventing one is the discovery this factory exists to refuse.
    """
    return ExecutablePin(
        executable=executable, error=KimiCodeError, env_allow=env_allow,
        auth=auth, auth_home=auth_home)


class KimiCodeAdapter(ArtifactAwareTransport):
    """Run one Kimi Code prompt per authorized action, and prove nothing more."""

    profile = KIMI_PROFILE
    error = KimiCodeError

    def __init__(
            self, pin: ExecutablePin, runner: ProcessRunner, *,
            root: str | Path,
            clock: Callable[[], str], ids: Callable[[str], str],
            adapter_id: str = KIMI_PROVIDER_ID) -> None:
        if type(pin) is not ExecutablePin or pin.error is not KimiCodeError:
            # The class alone binds nothing now that every single-binary provider
            # shares it, so the pin's own refusal type is checked too: a pin
            # built for another provider would refuse as that provider, and a
            # caller catching this one's error would never see it.
            raise KimiCodeError(
                "this adapter requires a single-executable pin of its own")
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

    def _login(self):
        return self._pin.auth, self._pin.auth_home

    def _login_home_grants(self, home):
        blocked = super()._login_home_grants(home)
        if not _managed_profile(login_home.profile_document(home, "config.toml")):
            blocked += ("config.toml",)
        selected = self._runner.capture_environment(self._env_allow())
        if any(name.startswith("KIMI_") and name not in (KIMI_HOME_ENV, KIMI_TELEMETRY_ENV)
               and selected.native_value(name) is not None for name in self._env_allow()):
            blocked += ("environment",)
        return blocked

    def _login_secrets(self):
        home = self._signed_in_road()
        config = login_home.profile_document(home, "config.toml") if home else None
        key = _managed_profile(config)
        if not key:
            return ()
        return login_home.nested_credentials(home, "credentials", (key.removeprefix("oauth/")+".json",))

    def _attempt_login_status(self, request):
        return self._attempt(("acp",), WORK_DIR,
            timeout=min(self.profile.version_timeout_seconds, request.timeout_seconds),
            stdin_bytes=KIMI_AUTH_INPUT, separate_stderr=True, stdin_completion_id=2)

    def _login_method_admitted(self, output):
        try:
            rows = [decode_line(line) for line in output.splitlines()]
            if len(rows) != 2 or {row.get("id") for row in rows} != {1, 2}:
                return False
            if any(type(row.get("id")) is not int or "method" in row or "error" in row
                   or type(row.get("result")) is not dict for row in rows):
                return False
            replies = {row["id"]: row["result"] for row in rows}
            return replies[1].get("protocolVersion") == 1 and replies[2] == {}
        except (ValueError, UnicodeError, RecursionError, TypeError):
            return False

    def quota_connection(self):
        if not self._signed_in_road():
            return NativeQuotaReader(LIVE_QUOTA_POLICY, self.profile.reviewed_version,
                                     reason="not_supported", transport="loopback")
        def read(wait, fetch, choose_port):
            try:
                return _read_local_usage(self, wait, fetch, choose_port)
            except (NativeQuotaReadError, NativeQuotaDeferred):
                raise
            except Exception:
                raise NativeQuotaReadError() from None
        return NativeQuotaReader(LIVE_QUOTA_POLICY, self.profile.reviewed_version,
                                 read, transport="loopback")




def _native_quota(payload):
    """The complete local /api/v1/oauth/usage response envelope."""
    body = quota_object(payload)
    if type(body.get("code")) is not int:
        raise QuotaError("missing Kimi response code")
    if body["code"] != 0:
        return NativeQuotaReading(error=True, policy=QUOTA_POLICY)
    data = quota_object(body.get("data"))
    if data.get("kind") == "error":
        return NativeQuotaReading(error=True, policy=QUOTA_POLICY)
    if data.get("kind") != "ok":
        raise QuotaError("unknown Kimi usage response kind")
    windows = []
    quota = data.get("quota")
    usages = None if quota is None else quota_object(quota).get("usages")
    if usages is None:
        return NativeQuotaReading(policy=QUOTA_POLICY)
    usages = quota_object(usages)
    for name, duration in (("limit5h", 300), ("limit7d", 10080),
                           ("monthTotal", None), ("monthCode", None)):
        raw = usages.get(name)
        if raw is None:
            continue
        row = quota_object(raw)
        ratio = row.get("usedRatio")
        if ratio is not None:
            ratio = quota_percentage(ratio)
            if ratio > 1:
                raise QuotaError("invalid Kimi usage ratio")
        windows.append(NativeQuotaWindow("kimi-subscription", name,
            None if ratio is None else ratio * 100, row.get("resetAt"), duration))
    return NativeQuotaReading(tuple(windows), policy=QUOTA_POLICY)


QUOTA_POLICY = QuotaPolicy("moonshot", "kimi-oauth-userinfo", "kimi-local-server",
                           "quota", "rfc3339", _native_quota)


KIMI_LOGIN_ARGV = ("login",)
KIMI_AUTH_INPUT = (b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
    b'{"protocolVersion":1,"clientCapabilities":{}}}\n'
    b'{"jsonrpc":"2.0","id":2,"method":"authenticate","params":{"methodId":"login"}}\n')
_KIMI_REGIONS = {"https://api.kimi.com/coding/v1": "https://auth.kimi.com",
                 "https://api.kimi.ai/coding/v1": "https://auth.kimi.ai"}


def _managed_profile(config):
    """Accept native managed login configuration, not a user API-key provider."""
    if type(config) is not dict or set(config) - {
            "providers", "models", "default_model", "default_provider", "thinking", "services"}:
        return None
    providers = config.get("providers")
    if type(providers) is not dict or set(providers) != {"managed:kimi-code"}:
        return None
    provider = providers["managed:kimi-code"]
    if type(provider) is not dict or set(provider) != {"type", "base_url", "api_key", "oauth"}:
        return None
    if provider["type"] != "kimi" or provider["api_key"] != "":
        return None
    base = provider["base_url"]
    if type(base) is not str or base not in _KIMI_REGIONS:
        return None
    oauth = provider["oauth"]
    host = _KIMI_REGIONS[base]
    key = "oauth/kimi-code" if host.endswith(".com") else "oauth/kimi-code-env-" + hashlib.sha256(
        json.dumps({"oauthHost": host, "baseUrl": base}, separators=(",", ":")).encode()).hexdigest()[:16]
    allowed = {"storage": "file", "key": key}
    if type(oauth) is not dict or oauth not in (allowed, {**allowed, "oauth_host": host}):
        return None
    models = config.get("models")
    default = config.get("default_model")
    if type(models) is not dict or type(default) is not str or default not in models:
        return None
    if config.get("default_provider", "managed:kimi-code") != "managed:kimi-code":
        return None
    for name, model in models.items():
        if (type(name) is not str or not name.startswith("kimi-code/") or type(model) is not dict
                or model.get("provider") != "managed:kimi-code" or set(model) - {
                    "provider", "model", "max_context_size", "capabilities", "display_name",
                    "protocol", "beta_api", "adaptive_thinking", "support_efforts", "default_effort"}):
            return None
    services = config.get("services", {})
    if type(services) is not dict or set(services) - {"moonshot_search", "moonshot_fetch"}:
        return None
    for name, row in services.items():
        if row != {"base_url": base + ("/search" if name == "moonshot_search" else "/fetch"),
                   "api_key": "", "oauth": oauth}:
            return None
    return key


def _read_local_usage(adapter, wait, fetch, choose_port):
    with _Turn(adapter):
        adapter._begin_road()
        try:
            home = adapter._signed_in_road()
            blocked = adapter._login_home_grants(home) if home else ("home",)
            if blocked == ("config.toml",) and login_home.profile_absent(home, "config.toml"):
                # The vendor's own login writes config.toml, so its absence is a sign-in still owed,
                # not an unsupported source (measured 23.09: a signed-out home read `not_supported`).
                raise NativeQuotaReadError("not_authenticated")
            if blocked:
                raise NativeQuotaReadError("not_supported")
            if adapter._workspace.sweep_homes():
                raise NativeQuotaReadError()
            adapter._workspace.work_root()
            version = adapter._attempt(VERSION_ARGV, WORK_DIR, timeout=10)
            _clean(adapter, version)
            if not adapter._version_matches(version.output):
                raise NativeQuotaReadError("not_supported")
            port = choose_port()
            if type(port) is not int or not 1 <= port <= 65535:
                raise NativeQuotaReadError()
            result = []
            def read(pid):
                auth = []
                def ready():
                    bearer = login_home.native_server_token(home, "server.token")
                    if bearer is None:
                        return None
                    try:
                        value = fetch(port=port, path="/api/v1/auth", bearer=bearer, timeout=.25)
                    except Exception:
                        return None
                    auth.append(value)
                    return port, bearer
                _, bearer = wait(ready, timeout=10)
                value = auth[-1]
                data = value.get("data") if type(value) is dict and type(value.get("code")) is int and value["code"] == 0 else None
                if (type(data) is not dict or data.get("ready") is not True
                        or type(data.get("providers_count")) is not int or data["providers_count"] != 1
                        or data.get("managed_provider") != {
                            "name": "managed:kimi-code", "status": "authenticated"}):
                    raise NativeQuotaReadError("not_authenticated")
                result.append(fetch(port=port, path="/api/v1/oauth/usage", bearer=bearer, timeout=10))
            outcome = adapter._attempt(("web", "--no-open", "--host", "127.0.0.1", "--port", str(port)),
                WORK_DIR, timeout=30, separate_stderr=True, server_read=read)
            if (outcome.status != "stopped" or outcome.output_truncated or outcome.output_contains_env_value
                    or adapter._login_echo or adapter._retained or adapter._login_residue or len(result) != 1):
                raise NativeQuotaReadError()
            return result[0]
        finally:
            adapter._forget_login_sample()


def _local_usage(payload):
    body = quota_object(payload)
    if type(body.get("code")) is not int:
        raise QuotaError("missing native response code")
    data = quota_object(body.get("data"))
    if body["code"] != 0 or data.get("kind") == "error":
        return NativeQuotaReading(error=True, policy=LIVE_QUOTA_POLICY)
    if data.get("kind") != "ok" or type(data.get("limits")) is not list or len(data["limits"]) > 64:
        raise QuotaError("invalid native usage response")
    rows = [("summary", data["summary"])] if data.get("summary") is not None else []
    rows += [("limit-"+str(index), row) for index, row in enumerate(data["limits"])]
    windows = []
    for identity, raw in rows:
        row = quota_object(raw)
        used, limit = row.get("used"), row.get("limit")
        if any(type(value) is not int or not 0 <= value <= 2**53-1 for value in (used, limit)):
            raise QuotaError("invalid native usage counts")
        minutes = None
        window = row.get("window")
        if window is not None:
            window = quota_object(window)
            unit, count = window.get("unit"), window.get("duration")
            factors = {"minute": 1, "hour": 60, "day": 1440, "week": 10080}
            if type(unit) is not str or unit not in factors or type(count) is not int or count <= 0:
                raise QuotaError("invalid native usage window")
            minutes = count * factors[unit]
        windows.append(NativeQuotaWindow("kimi-subscription", identity,
            None if limit == 0 else used / limit * 100, row.get("reset_at"), minutes))
    return NativeQuotaReading(tuple(windows), policy=LIVE_QUOTA_POLICY)


LIVE_QUOTA_POLICY = QuotaPolicy("moonshot", "kimi-oauth-userinfo", "kimi-local-server",
                               "quota", "rfc3339", _local_usage)
