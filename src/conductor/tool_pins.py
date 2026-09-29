"""The pins of git and gh: `<conduct-home>/tools.json` (spec 8.8).

A pin is a path and a `major.minor.patch` version. Nothing searches PATH: a child
runs the pinned path or does not run the tool at all, so this file is read strictly
(exactly the schema, nothing tolerated), written whole and canonical through
`atomic_replace`, and never overwritten when it is not the schema, because then it is
the owner's to fix. The version of a tool is read by running it in the environment
`tool_env` builds, so the owner's `GIT_*` and tokens never reach even that probe.

Lane L reads pins with `read_pin(tool)`. `pin_tool` is what `conduct tools pin` (and,
later, the hub's pin route) calls; `verify_pin` is the check a hub makes at start and a
child once per process. Every refusal is a `ToolPinError` whose `code` is a code the spec
names (`SPEC_CODES`) or one of the two proposals (`PROPOSED_CODES`); no other can be built.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from conductor import atomic_replace, tool_env
from conductor.hub import home
from conductor.ownership_native import NativeHold

TOOLS = ("git", "gh")
FILE_NAME = "tools.json"
LOCK_NAME = "tools.lock"
#: Tries of the non-blocking lock, and the pause between two: about two seconds, as 4.1.3.
LOCK_ATTEMPTS = 100
LOCK_PAUSE_SECONDS = 0.02
SCHEMA_VERSION = 1
#: Below this git has no `GIT_CONFIG_COUNT`, which is how `tool_env` silences hooks.
MIN_GIT = (2, 31)
VERSION_TIMEOUT_SECONDS = 10

_VERSION = re.compile(r"\d+\.\d+\.\d+")
_FIRST_LINE = re.compile(r"(git|gh) version (\d+)\.(\d+)\.(\d+)")

#: Runs `argv` in `env` and returns its standard output; raises `OSError` or
#: `subprocess.SubprocessError` when it cannot.
Runner = Callable[[list[str], Mapping[str, str]], str]


#: The codes this library raises that the spec already names (8.8, 4.6.3, 4.6.5).
SPEC_CODES = frozenset({"git_not_pinned", "gh_not_pinned", "git_changed", "gh_changed",
                        "git_too_old", "tool_version_unreadable"})
#: Proposals: the spec has no name for a `tools.json` that is not the schema, nor for one that
#: cannot be written (the lock that is not taken counts as that). `registry_invalid` and
#: `profile_invalid` are the analogues for other files. They stay until the tech lead rules.
PROPOSED_CODES = frozenset({"tools_file_invalid", "tools_file_unwritable"})


class ToolPinError(Exception):
    """A pin that cannot be read, made or trusted: a code and one line of detail.

    Raises:
        ValueError: `code` is neither in `SPEC_CODES` nor in `PROPOSED_CODES`; a new code is
            a decision for the spec, not something a raise site may introduce.
    """

    def __init__(self, code: str, detail: str) -> None:
        if code not in SPEC_CODES | PROPOSED_CODES:
            raise ValueError(f"{code!r} is neither a code of the spec nor a proposed one")
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ToolPin:
    """One pinned tool: where it is and the version it said when it was pinned."""

    tool: str
    path: str
    version: str


@dataclass(frozen=True)
class ToolPins:
    """The content of `tools.json`: a pin or `None` for each tool."""

    git: ToolPin | None = None
    gh: ToolPin | None = None

    def get(self, tool: str) -> ToolPin | None:
        """The pin of `tool`, or `None` when it is not pinned."""
        return getattr(self, _checked(tool))

    def with_pin(self, pin: ToolPin) -> ToolPins:
        """These pins with one tool's pin replaced; the other tool is untouched."""
        return replace(self, **{_checked(pin.tool): pin})


def _checked(tool: str) -> str:
    if tool not in TOOLS:
        raise ValueError(f"no such tool {tool!r}; the tools are {', '.join(TOOLS)}")
    return tool


def _folder(folder: Path | str | None) -> Path:
    return home.conduct_home_path() if folder is None else Path(folder)


def tools_file(folder: Path | str | None = None) -> Path:
    """`<conduct-home>/tools.json`, or the same name in `folder`."""
    return _folder(folder) / FILE_NAME


# -- reading: strict about the schema, not about the bytes ---------------------------


def load_pins(folder: Path | str | None = None) -> ToolPins:
    """Read `tools.json`; a missing file is no pins at all.

    Raises:
        ToolPinError: `tools_file_invalid`: the file exists and is not the schema.
    """
    path = tools_file(folder)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return ToolPins()
    except OSError as error:
        raise ToolPinError("tools_file_invalid", f"{path.name} cannot be read: {error}") from error
    try:
        return _pins_from(_strict_json(raw.decode("utf-8")))
    except ValueError as error:                       # incl. JSON and UTF-8 decode errors
        raise ToolPinError("tools_file_invalid", f"{path.name}: {error}") from error


def read_pin(tool: str, folder: Path | str | None = None) -> ToolPin | None:
    """The pin of one tool, or `None` when it is not pinned (no file, or a `null` entry).

    Raises:
        ToolPinError: `tools_file_invalid`, see `load_pins`.
        ValueError: `tool` is not `git` or `gh`.
    """
    return load_pins(folder).get(tool)


def _strict_json(text: str) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key appears twice")
        return dict(pairs)

    def refuse(constant: str) -> object:
        raise ValueError(f"{constant} is not JSON")

    return json.loads(text, object_pairs_hook=unique, parse_constant=refuse)


def _pins_from(document: object) -> ToolPins:
    if not isinstance(document, dict) or set(document) != {"schema_version", *TOOLS}:
        raise ValueError("expected exactly the keys schema_version, git and gh")
    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be the number {SCHEMA_VERSION}")
    return ToolPins(**{tool: _entry(tool, document[tool]) for tool in TOOLS})


def _entry(tool: str, value: object) -> ToolPin | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"path", "version"}:
        raise ValueError(f"{tool} must be null or exactly path and version")
    path, version = value["path"], value["version"]
    if not (isinstance(path, str) and path and "\0" not in path and os.path.isabs(path)):
        raise ValueError(f"{tool}.path must be an absolute path")
    if not (isinstance(version, str) and _VERSION.fullmatch(version)):
        raise ValueError(f"{tool}.version must be major.minor.patch")
    return ToolPin(tool, path, version)


# -- writing: canonical, whole, atomic ------------------------------------------------


def _canonical(pins: ToolPins) -> bytes:
    document: dict[str, object] = {"schema_version": SCHEMA_VERSION}
    for tool in TOOLS:
        pin = pins.get(tool)
        document[tool] = None if pin is None else {"path": pin.path, "version": pin.version}
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return (text + "\n").encode("utf-8")


def _store(pins: ToolPins, folder: Path) -> None:
    target = tools_file(folder)
    try:
        atomic_replace.replace_bytes(target, _canonical(pins))
    except OSError as error:
        raise ToolPinError("tools_file_unwritable",
                           f"{target.name} could not be written: {error}") from error


# -- the lock: a pin reads, changes and writes the file, so two pins take turns ------


@contextmanager
def _locked(folder: Path) -> Iterator[None]:
    """Hold `tools.lock` exclusively for the read-modify-write of `tools.json`.

    The lock is the registry's kind (4.1.3): the file is created when it is absent, taken
    without waiting, retried a bounded number of times, and freed by the OS if its holder
    dies. Readers take no lock: the file is swapped whole.

    Raises:
        ToolPinError: `tools_file_unwritable`: the folder or the lock file cannot be made,
            or another pin held the lock for every try.
    """
    lock = folder / LOCK_NAME
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            pass
    except OSError as error:
        raise ToolPinError("tools_file_unwritable",
                           f"{LOCK_NAME} could not be made: {error}") from error
    hold = _take(lock)
    try:
        yield
    finally:
        hold.close()


def _take(lock: Path) -> NativeHold:
    refused: OSError | None = None
    for attempt in range(LOCK_ATTEMPTS):
        try:
            return NativeHold(lock, exclusive=True)
        except OSError as error:
            refused = error
            if attempt < LOCK_ATTEMPTS - 1:
                time.sleep(LOCK_PAUSE_SECONDS)
    raise ToolPinError("tools_file_unwritable",
                       f"{LOCK_NAME} is held by another pin: {refused}") from refused


# -- versions: run the tool in the built environment ---------------------------------


def parse_version(tool: str, output: str) -> str:
    """`major.minor.patch` from the first line of `<tool> --version`.

    Raises:
        ToolPinError: `tool_version_unreadable`: the first line is not `<tool> version X.Y.Z`.
    """
    lines = output.splitlines()
    found = _FIRST_LINE.match(lines[0]) if lines else None
    if found is None or found.group(1) != _checked(tool):
        raise ToolPinError("tool_version_unreadable",
                           f"the first line of `{tool} --version` is not `{tool} version X.Y.Z`")
    return ".".join(found.group(2, 3, 4))


def _run_version(argv: list[str], env: Mapping[str, str]) -> str:
    done = subprocess.run(argv, env=dict(env), stdin=subprocess.DEVNULL, capture_output=True,
                          encoding="utf-8", errors="replace", check=True,
                          timeout=VERSION_TIMEOUT_SECONDS)
    return done.stdout


def _read_version(tool: str, path: str, where: Path, source: Mapping[str, str] | None,
                  run: Runner | None) -> str:
    # Only the directory of the stand-in is read by the builder, never its version.
    stand_in = ToolPins(**{tool: ToolPin(tool, path, "0.0.0")})
    env = tool_env.tool_env(os.environ if source is None else source, stand_in, where)
    try:
        output = (run or _run_version)([path, "--version"], env)
    except (OSError, subprocess.SubprocessError) as error:
        raise ToolPinError("tool_version_unreadable",
                           f"`{tool} --version` could not be run: {error}") from error
    return parse_version(tool, output)


def _too_old(version: str) -> bool:
    major, minor, _ = (int(part) for part in version.split("."))
    return (major, minor) < MIN_GIT


# -- the operations ------------------------------------------------------------------


def pin_tool(tool: str, path: str, *, folder: Path | str | None = None,
             run: Runner | None = None, source: Mapping[str, str] | None = None) -> ToolPin:
    """Pin `tool` at `path`: read its version, refuse a git that is too old, write the file.

    Args:
        tool: `git` or `gh`.
        path: The absolute path of the executable.
        folder: `<conduct-home>` unless a test says another.
        run: Runs `[path, "--version"]`; the real process unless a test stands in.
        source: The owner's environment for `tool_env`; `os.environ` by default.

    Raises:
        ToolPinError: `tool_version_unreadable` (also for a relative path), `tools_file_invalid`
            (the file is left as it is), `git_too_old`, `tools_file_unwritable`.
    """
    _checked(tool)
    if not (isinstance(path, str) and path and os.path.isabs(path)):
        raise ToolPinError("tool_version_unreadable",
                           "the path of the tool must be absolute, so no version can be read")
    where = _folder(folder)
    load_pins(where)              # an invalid file refuses before anything runs; read again below
    version = _read_version(tool, path, where, source, run)
    if tool == "git" and _too_old(version):
        raise ToolPinError("git_too_old", f"git {version} is older than "
                           f"{MIN_GIT[0]}.{MIN_GIT[1]}, which the hooks-off environment needs")
    pin = ToolPin(tool, path, version)
    # The probe ran outside the lock (it may take seconds). The read that counts is this one:
    # a pin of the other tool, or an edit of the owner, may have landed meanwhile.
    with _locked(where):
        _store(load_pins(where).with_pin(pin), where)
    return pin


def verify_pin(tool: str, *, folder: Path | str | None = None, run: Runner | None = None,
               source: Mapping[str, str] | None = None) -> ToolPin:
    """Check that the pinned tool still says the version it was pinned at.

    Raises:
        ToolPinError: `<tool>_not_pinned`, `tool_version_unreadable`, `<tool>_changed`
            (pin it again to confirm), or `tools_file_invalid`.
    """
    where = _folder(folder)
    pin = load_pins(where).get(tool)
    if pin is None:
        raise ToolPinError(f"{tool}_not_pinned", f"no {tool} is pinned; run "
                           f"`conduct tools pin {tool} --path <absolute path>`")
    version = _read_version(tool, pin.path, where, source, run)
    if version != pin.version:
        raise ToolPinError(f"{tool}_changed", f"{tool} at the pinned path now says {version}, "
                           f"and {pin.version} was pinned; pin it again to confirm")
    return pin
