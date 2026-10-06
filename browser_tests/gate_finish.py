"""The browser gate's mark that a module's pytest process ended through pytest.

The gate loads this plugin with ``-p`` into every module process and names, in
the environment, a mark file and a nonce of its own for that one run.
``pytest_unconfigure`` runs after the session has finished and its fixtures
were torn down; there the plugin writes the nonce and pytest's final exit
status, through a partial file and one rename, so a reader finds the whole
mark or none. Other unconfigure hooks and the release of the configuration may
still run after it.

A process that left by ``os._exit``, a crash or a kill never reaches that hook
and leaves no mark: its return code, even 0 or 1, says nothing about how it
ended. The mark says the session and its fixtures ended through pytest; it
does not prove that every process the module started is gone.

Not a test module (no ``test_`` prefix), and inert outside the gate: without
the two environment names it writes nothing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

MARK_ENV = "CONDUCT_GATE_FINISH"
NONCE_ENV = "CONDUCT_GATE_NONCE"
_STATUS = pytest.StashKey[int]()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session) -> None:
    """Keep the status the process will end with, after every other plugin's say."""
    session.config.stash[_STATUS] = int(session.exitstatus)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Write the mark once the session has finished and its fixtures were torn down."""
    path, nonce = os.environ.get(MARK_ENV), os.environ.get(NONCE_ENV)
    if not path or not nonce or _STATUS not in config.stash:
        return
    mark = Path(path)
    partial = mark.with_name(mark.name + ".partial")
    partial.write_text(json.dumps({"nonce": nonce, "exitstatus": config.stash[_STATUS],
                                   "pid": os.getpid()}), encoding="utf-8")
    os.replace(partial, mark)
