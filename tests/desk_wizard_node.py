"""Run the real wizard modules under Node and read what they answer back as JSON.

The wizard's model is pure: state in, state out, asks as values. So its tests
import the packaged module itself with `node --input-type=module`, hand it JSON
as data and print the answer as JSON -- the pattern `tests/test_studio_automation.py`
uses for the automation model. The script goes in on stdin, not on the command
line, because a flow fixture is several kilobytes and a Windows command line is
not.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODEL = "desk-wizard-model.js"


def fixture(*parts: str) -> Any:
    """One JSON fixture under `tests/fixtures/`, parsed."""
    return json.loads(FIXTURES.joinpath(*parts).read_text(encoding="utf-8"))


def run_js(body: str, data: Any = None, modules: dict[str, str] | None = None) -> Any:
    """Evaluate `body` next to the wizard's modules and return its printed JSON.

    Args:
        body: JavaScript that prints one JSON value with `console.log`.
        data: A JSON-serializable value, visible to `body` as the constant `d`.
        modules: Alias to packaged file name; defaults to `wiz` for the model.

    Returns:
        The parsed JSON the script printed.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to run the real wizard modules")
    wanted = modules or {"wiz": MODEL}
    imports = "\n".join(f"import * as {alias} from {json.dumps((PANEL / name).as_uri())};"
                        for alias, name in wanted.items())
    source = f"{imports}\nconst d = {json.dumps(data)};\n{body}\n"
    result = subprocess.run([node, "--input-type=module"], input=source, capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
