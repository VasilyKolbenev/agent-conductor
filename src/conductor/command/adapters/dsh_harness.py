"""The DeepSeek Harness (dsh) headless adapter: one pinned interpreter, one task.

The vendor contract this adapter is written against was read from the project's
own published sources on 2026-08-17 and is recorded here so a later reader can
re-check it rather than trust this prose:

- the CLI ships as the npm package ``@deepseek-ai/dsh``, whose ``bin`` maps the
  name ``dsh`` to ``lib/bin.js`` -- a Node script, never a native executable and
  never a Windows ``.cmd`` shim;
- the one-shot, non-interactive transport is the ``headless`` profile bundle,
  described by its own package as "a direct core Agent/Session runner over
  dsh-base with no Host, HTTP, or browser layer", invoked as
  ``dsh --profile headless "task"``: one task, no follow-up, no listening port,
  exit 0 when the turn ended and 1 when it did not;
- ``-V``/``--version`` is handled by the launcher's own argument adapter, which
  prints and exits;
- ``DSH_HOME`` is read by the harness's shared path helper (an empty or
  whitespace-only value counts as unset, and the default is ``~/.dsh``), and
  ``DSH_TELEMETRY_DISABLED`` is read by the CLI's profile boot, where ANY
  non-empty value disables telemetry;
- the ``headless`` profile is a built-in template that auto-initializes on first
  use, which is the only reason a FRESH, isolated ``DSH_HOME`` can boot it.

Because dsh publishes what its one-shot exit codes MEAN, this provider's profile
says so, and its receipts read a zero the documented way. That reading is still
only an observation of the process; it is the weaker, undocumented reading that
another provider's profile has to declare instead.

What this module refuses is as much of the contract as what it uses. It runs
ONLY an operator-pinned absolute Node executable against an operator-pinned
absolute entrypoint: no ``npx``, no ``npm`` shim, no ``PATH`` search, no home
scan, no "latest", no install, and never ``shell=True``. Everything after that
is the shared headless transport in ``headless_cli``: a fresh ``DSH_HOME`` per
attempt, an exact version preflight before any task is spawned, code-owned argv
down to the last token, bounded and drained output that reaches no receipt,
journal, API, SSE frame, evidence or exception message, a marker that stops a
crashed task from being run twice, and verification that reads only independent
workspace evidence.

Those guarantees are documented where they are implemented rather than restated
here, because a copy of a promise is a promise that can drift from the code that
keeps it. What stays HERE is what is true of dsh and of nothing else: the vendor
contract above, the two absolute pins, and where the launcher wants its flags.
"""
from __future__ import annotations

from .quota_contracts import NativeBalanceAmount, NativeQuotaReading, QuotaError, QuotaPolicy, quota_object

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .deep_contracts import DeepProtocol
from .artifact_transport import ArtifactAwareTransport
from .harness_workspace import INSTRUCTION_DIR, WORK_DIR
from .headless_cli import (
    DISPATCH_CAPABILITY,
    HarnessProfile,
    HeadlessCliError,
    reviewed_env_allow,
    reviewed_pin_path,
)
from .process import ProcessRunner
from .environment_values import EnvironmentSelectionError
from .quota_connection import NativeQuotaConnection

#: The exact published version this build was reviewed against. A preflight that
#: reads anything else refuses; the harness is a developer preview whose own
#: README promises compatibility-breaking changes, so "close enough" is not a
#: safe reading of a version string.
REVIEWED_DSH_VERSION = "0.1.0-rc.7"
#: Fixed direct API policy. A gateway is never silently mapped to this source.
BALANCE_ENDPOINT = "https://api.deepseek.com/user/balance"
BALANCE_SOURCE_VERSION = "user-balance-v1"
PUBLIC_API_ORIGIN = "https://api.deepseek.com"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
API_ORIGIN_ENV = "DEEPSEEK_BASE_URL"
#: The protocol token an operator pins to select this adapter.
DSH_PROTOCOL = DeepProtocol.DSH_HEADLESS_V1.value
#: The environment NAMES this adapter owns. Only names live in durable config;
#: the home's VALUE is minted per attempt and never written to any config.
DSH_HOME_ENV = "DSH_HOME"
DSH_TELEMETRY_DISABLED_ENV = "DSH_TELEMETRY_DISABLED"
#: Any non-empty value disables vendor telemetry; "1" is the one this build sends.
TELEMETRY_DISABLED = "1"
#: The code-owned launcher flags. No caller ever contributes a flag.
HEADLESS_ARGV = ("--profile", "headless")
VERSION_ARGV = ("--version",)
#: Capture ceiling for either spawn; the pump drains past it and drops the rest.
DSH_OUTPUT_LIMIT = 16 * 1024
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: The one control this adapter carries. stop, retry and switch stay ABSENT.
DSH_CAPABILITY = DISPATCH_CAPABILITY
#: The two subtrees THIS provider owns beneath the project root. They are named
#: here, in the provider's own module, rather than in the shared workspace door:
#: the door serializes and bounds every delete on the home name it is handed, so
#: a second harness naming the same home would take this one's attempts for its
#: own. One provider, one home name, declared where the provider is.
HOME_DIR = ".dsh-home"
MARKER_DIR = ".dsh-marker"
#: ``WORK_DIR`` and ``INSTRUCTION_DIR`` are re-exported from the workspace door,
#: and ``HOME_DIR`` and ``MARKER_DIR`` are this module's own, so a reader of this
#: module sees all four subtrees a dispatch touches without following an import.
__all__ = [
    "DSH_PROTOCOL", "HOME_DIR", "INSTRUCTION_DIR", "MARKER_DIR",
    "REVIEWED_DSH_VERSION", "WORK_DIR",
    "DshHarnessAdapter", "DshHarnessError", "DshPin",
]

#: Every vendor fact above, gathered where the shared transport reads them.
DSH_PROFILE = HarnessProfile(
    tool_noun="dsh", task_noun="dsh task",
    display_name="DeepSeek Harness (dsh, headless)", vendor="DeepSeek",
    docs_url="https://github.com/deepseek-ai/deepseek-harness",
    reviewed_version=REVIEWED_DSH_VERSION,
    home_dir=HOME_DIR, marker_dir=MARKER_DIR,
    home_env=DSH_HOME_ENV,
    forced_env=((DSH_TELEMETRY_DISABLED_ENV, TELEMETRY_DISABLED),),
    version_argv=VERSION_ARGV,
    home_id_kind="dsh-home",
    exit_codes_published=True, capability=DSH_CAPABILITY,
    output_limit=DSH_OUTPUT_LIMIT,
    version_timeout_seconds=VERSION_TIMEOUT_SECONDS)


class DshHarnessError(HeadlessCliError):
    """The harness cannot honour the request without breaking one of its rules."""


@dataclass(frozen=True)
class DshPin:
    """Both operator pins, re-proved absolute before either reaches an argv."""

    node_executable: str
    entrypoint: str
    env_allow: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("node_executable", "entrypoint"):
            reviewed_pin_path(getattr(self, name), name, DshHarnessError)
        object.__setattr__(
            self, "env_allow",
            reviewed_env_allow(self.env_allow, DshHarnessError))


class DshHarnessAdapter(ArtifactAwareTransport):
    """Run one dsh headless task per authorized action, and prove nothing more.

    The manifest holds exactly two entries: ``observe``, which reports honest
    ignorance without touching the machine, and ``dispatch``, which runs one
    task. ``stop``, ``retry`` and ``switch`` are ABSENT rather than present and
    empty, because this adapter implements none of them and the provider door
    refuses a control an adapter cannot back.
    """

    profile = DSH_PROFILE
    error = DshHarnessError

    def __init__(
            self, pin: DshPin, runner: ProcessRunner, *, root: str | Path,
            clock: Callable[[], str], ids: Callable[[str], str],
            adapter_id: str = "deepseek-harness") -> None:
        if type(pin) is not DshPin:
            raise DshHarnessError("the harness requires an exact DshPin")
        self._pin = pin
        super().__init__(
            runner, root=root, clock=clock, ids=ids, adapter_id=adapter_id)

    def _argv_prefix(self) -> tuple[str, ...]:
        """An interpreter and the entrypoint it runs: dsh is a Node script."""
        return (self._pin.node_executable, self._pin.entrypoint)

    def _task_argv(self, task_text: str) -> tuple[str, ...]:
        """``--profile headless <task>``: the task is the first free token."""
        return (*HEADLESS_ARGV, task_text)

    def _env_allow(self) -> tuple[str, ...]:
        return self._pin.env_allow

    def quota_connection(self) -> NativeQuotaConnection:
        """Capture direct API auth only; no native home scan, spawn or network.

        Dispatch creates a fresh home after these literals, so inherited home
        settings cannot select another credential. File-only keys can still
        dispatch, but this initial capture does not discover them.
        """
        reason = "source_error"
        try:
            captured = self._runner.capture_environment(
                self._env_allow(), overrides=dict(self.profile.forced_env))
            key = captured.native_value(DEFAULT_API_KEY_ENV)
            origin = captured.native_value(API_ORIGIN_ENV)
            # Windows aliases can survive an exact uppercase override. Until
            # that shape is proved natively, do not claim the fresh-home rule.
            home_alias = captured.windows and any(
                name.upper() == DSH_HOME_ENV and name != DSH_HOME_ENV
                for name in captured.values)
            if home_alias or (origin is not None and origin != PUBLIC_API_ORIGIN):
                reason = "not_supported"
            elif key is None or key == "":
                reason = "no_data"
            else:
                return NativeQuotaConnection(
                    QUOTA_POLICY, BALANCE_SOURCE_VERSION, BALANCE_ENDPOINT, key)
        except EnvironmentSelectionError:
            reason = "not_supported"
        except Exception:
            # Native errors may contain credentials. Only this closed reason
            # crosses to provider resolution; never retain the exception.
            reason = "source_error"
        return NativeQuotaConnection(
            QUOTA_POLICY, BALANCE_SOURCE_VERSION, BALANCE_ENDPOINT, reason=reason)

def _native_quota(payload):
    """GET /user/balance reports money and a native availability boolean."""
    body = quota_object(payload)
    available = body.get("is_available")
    if type(available) is not bool:
        raise QuotaError("missing native balance availability")
    rows = body.get("balance_infos")
    if type(rows) is not list or not rows or len(rows) > 2:
        raise QuotaError("missing native balance amounts")
    amounts = []
    for raw in rows:
        row = quota_object(raw)
        amounts.append(NativeBalanceAmount(row.get("currency"), row.get("total_balance"),
                                            row.get("granted_balance"), row.get("topped_up_balance")))
    return NativeQuotaReading(balances=tuple(amounts), is_available=available, policy=QUOTA_POLICY)


QUOTA_POLICY = QuotaPolicy("deepseek", "deepseek-account", "deepseek-api",
                           "balance", "none", _native_quota, ("CNY", "USD"))
