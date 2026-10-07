"""The run write host under Node: the harness `desk_run_write_host.mjs` is part of the suite.

The host holds the decisions, the drafts and the write locks of the run the desk shows, and its
rules are values in and calls out, so they are run from the real module with `node --test`. This
file runs the harness and says what it printed when it fails, as the other desk modules' tests
do through `tests/desk_node.py`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent / "desk_run_write_host.mjs"


def test_every_test_of_the_run_write_host_harness_passes_under_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to run the real desk modules")
    done = subprocess.run([node, "--test", "--test-reporter=tap", str(HARNESS)],
                          capture_output=True, text=True, encoding="utf-8", timeout=120,
                          check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "# fail 0" in done.stdout and "# tests 7" in done.stdout, done.stdout
