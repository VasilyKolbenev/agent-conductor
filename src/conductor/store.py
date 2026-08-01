"""Tolerant reading of a project's conductor/ directory. The ONLY file-reading
surface shared by validate, prompt and the server. Strict writers, tolerant
readers (PROTOCOL.md: tolerant reader, strict writer): a torn or malformed lane
becomes a broken-lane entry, a malformed event line is skipped and counted, a
broken map.toml is reported in `map_error` — nothing short of a missing
conductor/ directory raises."""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from conductor import schema

AUTHOR_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")


class StoreError(Exception):
    """The project root has no conductor/ directory (fail-closed startup)."""


@dataclass
class Loaded:
    """Everything read from one conductor/ directory, broken pieces included.

    Each entry in `lanes` is `{"author": str, "data": dict | None,
    "error": str | None}`: `data is None` exactly when the lane is broken,
    and `error is None` exactly when it is live. This is the shape
    `merge._lane_view` consumes.
    """

    map_data: dict | None
    map_error: str | None
    warnings: list[str] = field(default_factory=list)   # schema-version etc. (§5)
    lanes: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    skipped_events: int = 0


def conductor_dir(root: Path | str) -> Path:
    """Resolve the conductor/ directory under a project root.

    Args:
        root: The project root (the directory that contains `conductor/`).

    Returns:
        The path to the existing `conductor/` directory.

    Raises:
        StoreError: If `root` has no `conductor/` directory — startup is
            fail-closed; everything after this point is tolerant.
    """
    path = Path(root) / "conductor"
    if not path.is_dir():
        raise StoreError(f"no conductor/ directory under {root} — run `conduct init`")
    return path


def _load_map(cdir: Path, out: Loaded) -> None:
    """Read and validate map.toml into `out` (map_data/map_error/warnings)."""
    map_path = cdir / "map.toml"
    if not map_path.is_file():
        out.map_error = "map.toml is missing"
        return
    try:
        data = tomllib.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # TOMLDecodeError and UnicodeDecodeError are ValueErrors
        out.map_error = f"map.toml unreadable: {e}"
        return
    errors, warnings = schema.validate_map(data)
    out.warnings.extend(warnings)
    if errors:
        out.map_error = "; ".join(errors)
    else:
        out.map_data = data


def _load_lanes(cdir: Path, out: Loaded) -> None:
    """Read lanes/*.json into `out.lanes`; malformed files become broken entries."""
    lanes_dir = cdir / "lanes"
    if not lanes_dir.is_dir():
        return
    for path in sorted(lanes_dir.glob("*.json")):
        stem = path.stem
        if not AUTHOR_RE.fullmatch(stem):
            out.lanes.append({"author": stem, "data": None,
                              "error": f"lane {stem}: invalid author filename {stem!r}"})
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:  # JSONDecodeError/UnicodeDecodeError are ValueErrors
            out.lanes.append({"author": stem, "data": None, "error": f"lane {stem}: {e}"})
            continue
        errors, warnings = schema.validate_lane(data, filename_stem=stem)
        out.warnings.extend(warnings)     # §5: schema-version warnings surface
        if errors:
            out.lanes.append({"author": stem, "data": None,
                              "error": "; ".join(errors)})
        else:
            out.lanes.append({"author": stem, "data": data, "error": None})


def _load_events(cdir: Path, out: Loaded) -> None:
    """Read events.jsonl into `out.events`; bad lines increment `skipped_events`."""
    events_path = cdir / "events.jsonl"
    if not events_path.is_file():
        return
    try:
        text = events_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        out.warnings.append(f"events.jsonl unreadable: {e}")
        return
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out.skipped_events += 1
            continue
        if schema.validate_event(obj):
            out.skipped_events += 1
        else:
            out.events.append(obj)


def load(root: Path | str) -> Loaded:
    """Load everything under `root`/conductor/ tolerantly.

    Broken pieces are reported, never raised: an invalid or unreadable
    `map.toml` sets `map_error`; a malformed or misattributed lane file
    becomes a `{"author", "data": None, "error"}` entry; malformed or
    invalid event lines are skipped and counted in `skipped_events`, and
    an unreadable `events.jsonl` surfaces as a warning. Unknown
    `schema_version` values are accepted with a warning, never guessed
    (spec §5). Lanes are ordered by filename.

    Args:
        root: The project root (the directory that contains `conductor/`).

    Returns:
        A `Loaded` snapshot of the map, lanes, events, warnings and the
        skipped-event count.

    Raises:
        StoreError: If `root` has no `conductor/` directory.
    """
    cdir = conductor_dir(root)
    out = Loaded(map_data=None, map_error=None)
    _load_map(cdir, out)
    _load_lanes(cdir, out)
    _load_events(cdir, out)
    return out
