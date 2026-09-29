"""The printing bodies of the hub-side commands of `conduct` (spec 4.1.12).

`conduct tools pin` is here today; `hub` and `projects add` come later. Each body turns what
a library decided into the stream contract of the CLI: a result on stdout, or ONE refusal
line on stderr, and an exit code. The libraries (`tool_pins`, ...) raise and never print.
"""
from __future__ import annotations

import json
import sys

from conductor import tool_pins
from conductor.hub import home


def tools_pin(tool: str, path: str) -> int:
    """`conduct tools pin <tool> --path <abs>`: one JSON line on stdout, or one refusal line.

    Args:
        tool: `git` or `gh`.
        path: The absolute path of the executable to pin.

    Returns:
        0 after a pin was written, 1 for any refusal.
    """
    try:
        pin = tool_pins.pin_tool(tool, path)
    except tool_pins.ToolPinError as error:
        return _refused("tools pin", error.code, error.detail)
    except home.ConductHomeInvalid as error:
        return _refused("tools pin", error.code, str(error))
    print(json.dumps({"tool": pin.tool, "path": pin.path, "version": pin.version},
                     sort_keys=True, ensure_ascii=False))
    return 0


def _refused(command: str, code: str, detail: str) -> int:
    print(f"conduct {command}: refused {code}: {' '.join(str(detail).split())}", file=sys.stderr)
    return 1
