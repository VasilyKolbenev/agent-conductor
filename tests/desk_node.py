"""Run the desk's pure JavaScript modules under Node and read what they answer as JSON.

The desk's catalogue and its status rules are values in, values out, so their tests import
the packaged module itself with `node --input-type=module`, hand it JSON as data and print
the answer as JSON. The script goes in on stdin: a table of cases is longer than a Windows
command line allows.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"


def run_js(body: str, modules: dict[str, str], data: Any = None) -> Any:
    """Evaluate `body` next to the named packaged modules and return its printed JSON.

    Args:
        body: JavaScript that prints one JSON value with `console.log`.
        modules: Alias to packaged file name; each is imported as `import * as <alias>`.
        data: A JSON-serializable value, visible to `body` as the constant `d`.

    Returns:
        The parsed JSON the script printed.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to run the real desk modules")
    imports = "\n".join(f"import * as {alias} from {json.dumps((PANEL / name).as_uri())};"
                        for alias, name in modules.items())
    source = f"{imports}\nconst d = {json.dumps(data)};\n{body}\n"
    result = subprocess.run([node, "--input-type=module"], input=source, capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
