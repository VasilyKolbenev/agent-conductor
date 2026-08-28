"""What a map says this project is CALLED, and when that is not a name.

One question, asked in one place, because three different things all mean "this
build has no project name to show" and every surface that shows one has to tell
them apart the same way:

- the map never carried a ``project`` key, which is every project scaffolded
  before `conduct init` wrote one on all of its roads;
- the value is not a string, which `schema.validate_map` reports as an error
  while still leaving the document readable;
- the value is the placeholder every template ships with. This is the one worth
  spelling out: `templates.UNNAMED` is what a map carries until somebody
  chooses, so a surface that treated it as a name would tell a reader their
  project is called "your-project", in the largest type on the screen. A
  placeholder shown as a fact is worse than an absence shown as an absence.

Kept out of `server.py` so the rule has one home rather than one per reader,
and out of `conductor.command` entirely: that package holds no opinion about
Protocol v1 documents and imports nothing that reads one. The command boundary
is handed a name or ``None`` and never the map.
"""
from __future__ import annotations

from collections.abc import Mapping

from conductor import templates


def project_name(map_data: Mapping[str, object] | None) -> str | None:
    """The project's own name, or ``None`` when there is none to show.

    Args:
        map_data: A parsed ``map.toml`` document, or ``None`` when no map has
            been read. ``None`` is an ordinary input, not an error: a server
            answering before its first read has no name yet either.

    Returns:
        The name with surrounding whitespace removed, or ``None`` when the
        document carries no name, carries something that is not a string, or
        carries the placeholder a template ships with.
    """
    name = (map_data or {}).get("project")
    if not isinstance(name, str):
        return None
    settled = name.strip()
    if not settled or settled == templates.UNNAMED:
        return None
    return settled
