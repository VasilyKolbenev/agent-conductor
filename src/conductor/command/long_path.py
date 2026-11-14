"""How a path that may be deeper than the classic limit is named to the operating system.

Windows without `LongPathsEnabled` answers "not found" to any name of 260 characters or more in its
plain form, and a child inside the boundary can make such a name (its TEMP, a vendor's project
folders). A walk or a removal given the plain name then lists nothing, reads nothing or refuses a
tree that is there. The extended-length form (`\\\\?\\` and the absolute path) names it.

This is the one place that decides it: every walk and removal of a tree a child writes in passes
its path through `extended`, and what it hands back is then used as it is.
"""
from __future__ import annotations

import os


def extended(path: str | os.PathLike) -> str:
    """The absolute extended-length form on Windows (so a deep path has a name), else absolute.

    The name is made absolute and cleaned first (`.`, `..`, `/`), because the prefix passes it to
    the system as written. A name that already has the prefix is returned as it is, before any
    cleaning: it is the name a listing gave, and cleaning it again would name another entry
    (`foo ` and `foo.` are `foo` to a plain name, `...` is the folder above). A device name
    (`\\\\.\\X`) is no network path (`\\\\?\\UNC\\.\\X` is a share called `.`): the system reads it
    itself, so it is returned with no prefix, as `abspath` makes it.

    Args:
        path: A path, deep or not; it need not exist.
    """
    text = os.fspath(path)
    if os.name == "nt" and text.startswith("\\\\?\\"):
        return text
    absolute = os.path.abspath(text)
    if os.name != "nt" or absolute.startswith(("\\\\?\\", "\\\\.\\")):  # also `//?/` and `//./`
        return absolute
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute
