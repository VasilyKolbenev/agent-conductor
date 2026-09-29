"""The hub flags of `conduct up` (spec 4.1.4) and the closed list of refused starts (4.1.5).

Everything here is judged BEFORE any IO: `settle` reads the parsed arguments and
either returns an `UpPlan` or raises `UpRefusal(code, detail)`. The order in which
several faults are named is fixed, because the spec lists the codes and not their
priority: the value of `--mode`, then whether the flags that belong together are
all there, then each value in the order of the table. A refusal is printed as ONE
line, `conduct up: refused <code>: <detail>`; the caller writes the status file.
"""
from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from conductor.hub import home

#: The refusals a plain reading of the flags can produce.
FLAG_CODES = frozenset({
    "hub_flags_incomplete", "project_id_invalid", "hub_origin_invalid",
    "status_file_invalid", "stdin_is_terminal", "mode_invalid"})
#: Every code of the child rows of 4.1.5: a closed list, because the hub reads it.
START_CODES = FLAG_CODES | frozenset({
    "project_identity_changed", "hub_in_kill_on_close_job", "owner_busy",
    "recovery_required", "ownership_lost", "transition_conflict", "ownership_unavailable",
    "store_error", "providers_invalid", "bind_failed", "start_failed"})
#: The codes an ownership refusal may keep; any other one is `start_failed`.
OWNER_CODES = frozenset({"owner_busy", "recovery_required", "ownership_lost",
                         "transition_conflict", "ownership_unavailable"})
MODES = ("active", "view")

_PROJECT_ID = re.compile(r"[0-9a-f]{32}")
#: The one spelling of the hub's origin (4.5.1, 4.6.2): read by this module for the flag
#: and by `http_framing` for the frame policy, so there is no second grammar.
HUB_ORIGIN = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_TRANSITION = re.compile(_UUID)
_AUTO_CONTINUE = re.compile(_UUID + r"@[1-9][0-9]{0,8}")


class UpRefusal(Exception):
    """A start that must not go on: a code of the closed list and one line of detail."""

    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class UpPlan:
    """What the flags of one `conduct up` settled to."""

    project_id: str | None
    mode: str
    hub_origin: str | None
    status_file: Path | None
    stop_on_stdin_eof: bool
    transition: str | None
    auto_continue: str | None
    demo: bool = False

    @property
    def hub(self) -> bool:
        """Whether a hub started this process (the three hub flags are present)."""
        return self.hub_origin is not None


STANDALONE = UpPlan(None, "active", None, None, False, None, None)
#: `conduct demo`: no hub flags, and the plan says it is the demo (4.5.1).
DEMO = UpPlan(None, "active", None, None, False, None, None, demo=True)


def refusal_line(code: str, detail: str) -> str:
    """The one stderr line of a refused start; a detail never adds a second line."""
    return f"conduct up: refused {code}: {' '.join(str(detail).split())}"


def _stdin_is_terminal() -> bool:
    try:
        return bool(sys.stdin is not None and sys.stdin.isatty())
    except ValueError:                      # a closed stdin is not a terminal
        return False


def settle(args, *, stdin_isatty: Callable[[], bool] = _stdin_is_terminal) -> UpPlan:
    """Turn the parsed flags of `conduct up` into a plan, or refuse.

    Args:
        args: The parsed namespace of the `up` subcommand.
        stdin_isatty: Whether stdin is a terminal; a parameter so a test can say.

    Returns:
        The plan: every value validated, `mode` defaulted to `active`.

    Raises:
        UpRefusal: A flag is missing a partner or has a value the table refuses.
    """
    mode = _mode(args.mode)
    _completeness(args, mode)
    project_id = _project_id(args.project_id)
    hub_origin = status_file = None
    if _hub_flags_given(args):
        hub_origin = _hub_origin(args.hub_origin)
        status_file = _status_file(args.status_file, project_id)
        if stdin_isatty():
            raise UpRefusal("stdin_is_terminal",
                            "--stop-on-stdin-eof needs stdin to be a pipe from the hub")
    return UpPlan(project_id, mode, hub_origin, status_file, bool(args.stop_on_stdin_eof),
                  _formatted(args.transition, _TRANSITION, "--transition", "a uuid"),
                  _formatted(args.auto_continue, _AUTO_CONTINUE, "--auto-continue",
                             "<flag_id>@<revision>"))


def usable_status_path(args) -> Path | None:
    """The status file a refusal may be written to; None when `--status-file` is not usable.

    A refusal caused by some OTHER flag still reaches the hub through its own
    status file, as long as that file's path passes the same rule.
    """
    if args.status_file is None:
        return None
    try:
        return _status_file(args.status_file, _project_id(args.project_id))
    except UpRefusal:
        return None


def _hub_flags_given(args) -> bool:
    return (args.hub_origin is not None or args.status_file is not None
            or bool(args.stop_on_stdin_eof))


def _mode(values: list[str] | None) -> str:
    if values is None:
        return "active"
    if len(values) != 1 or values[0] not in MODES:
        raise UpRefusal("mode_invalid", "--mode takes exactly one of: active, view")
    return values[0]


def _completeness(args, mode: str) -> None:
    hub = _hub_flags_given(args)
    together = ("--hub-origin, --status-file and --stop-on-stdin-eof go together, "
                "and only with --project-id")
    if hub and (args.hub_origin is None or args.status_file is None
                or not args.stop_on_stdin_eof or args.project_id is None):
        raise UpRefusal("hub_flags_incomplete", together)
    if mode == "view" and not hub:
        raise UpRefusal("hub_flags_incomplete", "--mode view needs the hub flags")
    if args.transition is not None and not (hub and mode == "active"):
        raise UpRefusal("hub_flags_incomplete",
                        "--transition needs the hub flags and --mode active")
    if args.auto_continue is not None and args.transition is None:
        raise UpRefusal("hub_flags_incomplete", "--auto-continue needs --transition")


def _project_id(value: str | None) -> str | None:
    if value is not None and not _PROJECT_ID.fullmatch(value):
        raise UpRefusal("project_id_invalid",
                        "--project-id must be 32 lowercase hex characters")
    return value


def is_hub_origin(value: object) -> bool:
    """Whether `value` is exactly `http://127.0.0.1:<port>` with a port from 1 to 65535."""
    found = HUB_ORIGIN.fullmatch(value) if isinstance(value, str) else None
    return found is not None and int(found.group(1)) <= 65535


def _hub_origin(value: str) -> str:
    if not is_hub_origin(value):
        raise UpRefusal("hub_origin_invalid",
                        "--hub-origin must be http://127.0.0.1:<port> with a port up to 65535")
    return value


def _status_file(value: str, project_id: str | None) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise UpRefusal("status_file_invalid", "--status-file must be an absolute path")
    if project_id is None or path.name != f"{project_id}.json":
        raise UpRefusal("status_file_invalid", "--status-file must be named <project-id>.json")
    try:
        run_folder = home.conduct_home_path() / "run"
    except home.ConductHomeInvalid as error:
        raise UpRefusal("status_file_invalid", str(error)) from error
    if _resolved(path.parent) != _resolved(run_folder):
        raise UpRefusal("status_file_invalid",
                        "--status-file must be directly inside <conduct-home>/run")
    return path


def _resolved(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _formatted(value: str | None, grammar: re.Pattern[str], flag: str, form: str) -> str | None:
    if value is not None and not grammar.fullmatch(value):
        raise UpRefusal("hub_flags_incomplete", f"{flag} must be {form}")
    return value
