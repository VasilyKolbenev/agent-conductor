"""What `conduct validate` computes, separated from what it prints.

One function, `check`, returning `(errors, warnings)` as data. It exists so
that more than one caller can ask the same question without one of them having
to import the CLI: `conduct validate` renders the answer, and `conduct init`
uses it to check the scaffold it has just written. Both therefore judge a
project by the identical computation, and neither can drift from the other.

The split also makes `init`'s report honest. Exit code 0 covers both "clean"
and "valid, with warnings", so a caller that only sees the code cannot tell
them apart — and `init` says which one it found.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from conductor import merge, store

Result = tuple[list[str], list[str]]  # (errors, warnings), as in schema.py


def merged_state(loaded: store.Loaded) -> dict:
    """Merge a `Loaded` snapshot into a state dict at the current time.

    Args:
        loaded: A snapshot from `store.load`.

    Returns:
        The `state.json` dict `merge.merge` computes, loader-level warnings
        passed through so nothing they carry is silently dropped.
    """
    return merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                       loaded.events, loaded.skipped_events,
                       datetime.now(timezone.utc),
                       extra_warnings=loaded.warnings)


def check(root: Path | str) -> Result:
    """Validate one project root: schema errors first, merge warnings after.

    Args:
        root: The project root — the directory holding `conductor/`.

    Returns:
        `(errors, warnings)`. Errors are schema failures, already prefixed
        with their source (`map...`, `lane <stem>: ...`), and mean the project
        is invalid. Warnings are informational — referential drift, an
        unrecognized `schema_version` — and never block. Errors short-circuit
        the merge, so the two are never both populated: an invalid map makes
        every warning computed from it meaningless.

    Raises:
        store.StoreError: If `root` has no `conductor/` directory. That is the
            command failing to run, not a finding about the project, and the
            caller reports it as such.
    """
    loaded = store.load(root)
    errors = [entry["error"] for entry in loaded.lanes if entry["error"] is not None]
    if loaded.map_error is not None:
        errors.insert(0, loaded.map_error)
    if errors:
        return errors, []
    return [], merged_state(loaded)["warnings"]
