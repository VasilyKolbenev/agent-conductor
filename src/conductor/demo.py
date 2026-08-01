"""The bundled demo fixture — a sanitized real release-gate case.

The packaged `_demo/conductor/` tree replays the moment a desktop voice
app's offline smoke gate went red: three blocker findings, a reviewer who
confirms two and partially disputes the third (one computed disagreement),
and one genuine product decision sitting in the human queue. `conduct demo`
copies the tree into a throwaway directory and serves it with the regular
panel server, so nothing ever mutates the packaged fixture.
"""
from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path


def materialize(target_dir: Path | str) -> Path:
    """Copy the packaged demo fixture tree into `target_dir`.

    Args:
        target_dir: Directory to receive the fixture (may already exist).
            After the call, `target_dir/conductor/` holds map.toml, lanes/
            and events.jsonl.

    Returns:
        `target_dir` as a `Path`, ready to use as a project root (for
        `store.load`, `server.build`, or `conduct validate --dir`).
    """
    target = Path(target_dir)
    source = importlib.resources.files("conductor") / "_demo"
    # as_file keeps this importlib-pure: it yields a real filesystem path
    # even for exotic loaders, and is a no-op wrapper for normal installs.
    with importlib.resources.as_file(source) as src:
        shutil.copytree(src, target, dirs_exist_ok=True)
    return target
