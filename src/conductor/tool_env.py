"""The one environment git and gh run in (spec 8.9): a list of names, never a copy.

`tool_env(source, pins, conduct_home)` is the only builder of the environment of a
git or gh process in this product; the hub (clone), `projects add` and a child (git,
push, pull request) all take it from here. It is a pure function of what it is
handed: it reads no process state, so a token or a `GIT_*` variable of the owner
cannot arrive by accident, and a test can hand it any owner.

What passes is the allowlist `TRANSFERRED`, by name, from `source`. What never passes
is everything else, and `NEVER_TRANSFERRED` names the ones that matter (gh tokens, its
host override, the askpass programs, and every `GIT_*` of the owner) so a guard can
read the list. Then the literals of 8.9 are laid over it, and `PATH` is rebuilt from
the pinned directories alone. Hooks are silenced here and nowhere else: `GIT_CONFIG_*`
points `core.hooksPath` at `<conduct-home>/git/hooks-empty`, so there is no `-c` for
hooks in the product.
"""
from __future__ import annotations

import ntpath
import posixpath
import sys
from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Protocol

#: Taken from the owner's environment by name, when present, in this spelling.
TRANSFERRED = (
    "SystemRoot", "WINDIR", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA",
    "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
    "TMP", "TEMP", "TMPDIR", "LANG", "SSH_AUTH_SOCK", "GH_CONFIG_DIR",
    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy")
#: Never taken, in any spelling; every other `GIT_*` of the owner is refused as well.
NEVER_TRANSFERRED = (
    "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_HOST",
    "GIT_ASKPASS", "SSH_ASKPASS")

_LITERALS = {
    "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1",
    "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
    "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C",
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_KEY_0": "core.hooksPath",
    "GIT_CONFIG_KEY_1": "core.fsmonitor", "GIT_CONFIG_VALUE_1": "false",
}
_DARWIN_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
_LINUX_DIRS = ("/usr/bin", "/bin")


class _Pinned(Protocol):
    path: str


class _Pins(Protocol):
    git: _Pinned | None
    gh: _Pinned | None


def hooks_folder(conduct_home: object, *, platform: str | None = None) -> str:
    """`<conduct-home>/git/hooks-empty`, spelled with forward slashes as git reads it."""
    pure = PureWindowsPath if _windows(platform) else PurePosixPath
    return (pure(str(conduct_home)) / "git" / "hooks-empty").as_posix()


def tool_env(source: Mapping[str, str], pins: _Pins, conduct_home: object, *,
             platform: str | None = None) -> dict[str, str]:
    """Build the environment of one git or gh process.

    Args:
        source: The owner's environment to take the allowlisted names from.
        pins: The pinned tools (`tool_pins.ToolPins`): only the directories of
            `pins.git.path` and `pins.gh.path` are used, and a `None` adds none.
        conduct_home: The hub's folder; the hooks folder lies beneath it.
        platform: `sys.platform` unless a test says another: it decides how names
            match (case-insensitively on Windows), the `PATH` separator and the
            system directories.

    Returns:
        A new dict of strings: the allowlisted names, then the literals, then `PATH`.
    """
    windows = _windows(platform)
    env: dict[str, str] = {}
    taken: set[str] = set()
    for name in TRANSFERRED:
        key = name.upper() if windows else name
        value = _lookup(source, name, windows)
        if value is not None and key not in taken:
            env[name] = value
            taken.add(key)
    env.update(_LITERALS)
    env["GIT_CONFIG_VALUE_0"] = hooks_folder(conduct_home, platform=platform)
    env["PATH"] = _path(source, pins, platform, windows)
    return env


def _windows(platform: str | None) -> bool:
    return (sys.platform if platform is None else platform) == "win32"


def _lookup(source: Mapping[str, str], name: str, windows: bool) -> str | None:
    """The value of one name: exact first, then any spelling on Windows; text without NUL only."""
    value = source.get(name)
    if value is None and windows:
        folded = name.upper()
        value = next((held for key, held in source.items() if key.upper() == folded), None)
    return value if isinstance(value, str) and "\0" not in value else None


def _path(source: Mapping[str, str], pins: _Pins, platform: str | None, windows: bool) -> str:
    """Pinned git directory, pinned gh directory, then the system directories, each once."""
    dirname = ntpath.dirname if windows else posixpath.dirname
    listed = [dirname(pinned.path) for pinned in (pins.git, pins.gh) if pinned is not None]
    listed += _system_dirs(source, platform, windows)
    unique: list[str] = []
    seen: set[str] = set()
    for folder in listed:
        key = folder.upper() if windows else folder
        if folder and key not in seen:
            seen.add(key)
            unique.append(folder)
    return (";" if windows else ":").join(unique)


def _system_dirs(source: Mapping[str, str], platform: str | None, windows: bool) -> list[str]:
    if windows:
        root = _lookup(source, "SystemRoot", True)
        if root is None:                    # invented paths would be worse than none
            return []
        return [ntpath.join(root, "System32"), root, ntpath.join(root, "System32", "Wbem")]
    return list(_DARWIN_DIRS if (sys.platform if platform is None else platform) == "darwin"
                else _LINUX_DIRS)
