"""Where the hub's folder is: `<conduct-home>` (spec 4.1.2).

Only the path is here. The folder is `~/.december-command` on every OS, and
`CONDUCT_HOME` may replace it with an ABSOLUTE path; a relative or empty
override is refused instead of being resolved against the working folder of
whichever process reads it. Computing the path creates nothing, so a child can
judge `--status-file` against it before it does any IO.
"""
from __future__ import annotations

import os
from pathlib import Path

HOME_FOLDER = ".december-command"
OVERRIDE = "CONDUCT_HOME"


class ConductHomeInvalid(ValueError):
    """`CONDUCT_HOME` is set and is not an absolute path."""

    code = "conduct_home_invalid"


def conduct_home_path() -> Path:
    """The folder the hub keeps its files in, without creating it.

    Returns:
        `CONDUCT_HOME` when it names an absolute path, else `~/.december-command`.

    Raises:
        ConductHomeInvalid: `CONDUCT_HOME` is set to a relative or empty path.
    """
    override = os.environ.get(OVERRIDE)
    if override is None:
        return Path.home() / HOME_FOLDER
    if not override or not os.path.isabs(override):
        raise ConductHomeInvalid(f"{OVERRIDE} must be an absolute path, not {override!r}")
    return Path(override)
