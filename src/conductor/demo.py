"""The bundled demo fixture — a fictional release-gate scenario.

The packaged `_demo/conductor/` tree plays out the moment a plain web
project's release smoke gate went red: three blocker findings, a reviewer
who confirms two and partially disputes the third (one computed
disagreement), and one genuine ops decision sitting in the human queue.
`conduct demo` copies the tree into a throwaway directory and serves it
with the regular panel server, so nothing ever mutates the packaged
fixture.

That tree is Protocol v1 and NOTHING ELSE, and for a while that was the whole
demo -- which meant the front door showed none of it. `GET /` serves the
Workflow Studio; the Studio reads the command surface and holds no opinion
about a Protocol v1 map, so it opened on an empty Overview, an empty workflow
list and an empty run list while the findings and the feed sat on `/state.json`
behind a link only the classic panel followed.

So a demo is two halves and `conduct demo` writes both: `materialize` for the
v1 fixture the classic panel reads, and `populate` for the workflow, revision
and run the Studio reads. They are separate functions because they are separate
stories with separate readers, and because most callers of the first want
exactly the first. `conduct demo` calls both, and a test drives the real
command to prove it.
"""
from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path
from typing import Any


def materialize(target_dir: Path | str) -> Path:
    """Copy the packaged demo fixture tree into `target_dir`.

    Args:
        target_dir: Directory to receive the fixture (may already exist).
            After the call, `target_dir/conductor/` holds map.toml, lanes/
            and events.jsonl. Existing files with the same names are
            overwritten.

    Returns:
        `target_dir` as a `Path`, ready to use as a project root (for
        `store.load`, `server.build`, or `conduct validate --dir`).
    """
    target = Path(target_dir)
    source = importlib.resources.files("conductor") / "_demo"
    # as_file yields a real directory for copytree — a no-op wrapper for
    # normal installs. (Extracting a whole directory from a zipped package
    # needs Python 3.12+; not an install mode this package ships in.)
    with importlib.resources.as_file(source) as src:
        shutil.copytree(src, target, dirs_exist_ok=True)
    return target


def populate(project_root: Path | str) -> dict[str, Any]:
    """Write the command-side story the Workflow Studio reads.

    One workflow with one published revision, one run frozen against that exact
    revision, one step carried through all five durable timeline records, one
    gate a person already answered and one still waiting for them -- all of it
    through the production writers, which is what makes it a demonstration of
    this product rather than a picture of it.

    Deferred import: `conductor.command` is the heavier half of this package and
    nothing on the classic panel's road needs it, so a caller that only wants
    the v1 fixture never pays for it.

    Args:
        project_root: A directory that already holds `conductor/` -- normally
            the one `materialize` just wrote.

    Returns:
        The identities the story uses, so a caller can name them to a person.

    Raises:
        StoreError: A durable relation refused one of the records. It is not
            caught: a demo the product's own rules no longer admit must fail
            loudly rather than serve a front door that is quietly empty again.
    """
    from conductor.command import demo_scenario

    return dict(demo_scenario.build(Path(project_root)))
