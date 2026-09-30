"""The run reads the desk's feed and summary models are tested against, derived and not typed.

Nothing in `tests/fixtures/desk/feed_reads.json` is written by hand. The server's own answers
are taken from the project of `tests/desk_progress_seed.py` (four tasks, three runs at three
places) and from the repository's independent-check rig (the run whose check did not pass and
which recorded typed findings), through the production `CommandApi` with a fixed clock, and
`tests/test_desk_feed_model.py` re-derives them and compares, so a server that changes the shape
of a read reds there and not in a browser.

Run `python -m tests.desk_feed_reads` from the repository root to write the file again.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore
from tests.desk_progress_seed import TASKS, seed_project
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, get_headers, ids
from tests.test_policy_feedback import first_rejection, fixture
from tests.test_store import good_lane, write_project

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "desk" / "feed_reads.json"
RUNS = tuple(run for _task, _title, run in TASKS if run is not None)


def _answer(api: CommandApi, route: str) -> Any:
    response = api.handle("GET", route, get_headers())
    assert response.status == 200, (route, response.payload)
    return json.loads(json.dumps(response.payload))


def _seeded(base: Path) -> dict[str, Any]:
    root = write_project(base, lanes={"claude": good_lane()})
    seed_project(root)
    api = CommandApi(RunStore(root), AdapterRegistry([FakeAdapter()]),
                     session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
                     clock=lambda: NOW, ids=ids(), publish_run=lambda run: None)
    return {
        "tasks": _answer(api, "/command/tasks"), "runs": _answer(api, "/command/runs"),
        "automation": {run: _answer(api, f"/command/runs/{run}/automation") for run in RUNS},
        "reads": {run: _answer(api, f"/command/runs/{run}") for run in RUNS},
    }


def _rejected(base: Path) -> Any:
    """The rig's run after its first independent rejection: typed findings on record."""
    with pytest.MonkeyPatch.context() as patch:
        rig = fixture(base, patch)
        first_rejection(rig)
        api = CommandApi(rig.store, rig.registry, session=CommandSession(PORT, TOKEN),
                         budget=rig.policy.budget, clock=rig.policy.clock, ids=rig.runtime._ids,
                         publish_run=lambda run: None)
        return _answer(api, "/command/runs/run")


def derive() -> dict[str, Any]:
    """Every frozen read, taken from servers built in a scratch directory."""
    with tempfile.TemporaryDirectory(prefix="desk-feed-reads-") as scratch:
        base = Path(scratch)
        (base / "seeded").mkdir()
        (base / "rig").mkdir()
        return {"_comment": (
            "Derived by tests/desk_feed_reads.py from the production CommandApi; do not edit. "
            "`seeded` is the project of tests/desk_progress_seed.py, `rejected` the read of "
            "the independent-check rig after its first rejection."),
            "seeded": _seeded(base / "seeded"), "rejected": _rejected(base / "rig")}


def write_all() -> None:
    FIXTURE.write_text(json.dumps(derive(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")


if __name__ == "__main__":  # pragma: no cover -- derivation entry
    write_all()
