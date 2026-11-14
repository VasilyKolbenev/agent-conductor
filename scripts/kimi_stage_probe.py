"""Windows release witness for a synthetic Kimi profile. No provider or model is started.

Run with the checkout's Python, e.g. `python scripts/kimi_stage_probe.py run <32 hex>`.
An interrupted case uses the same ID for `recover`. Each ID is confined to its own newly
created fixture under the owner's temporary directory. A completed lab keeps its nonsecret
ownership record for inspection.
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from conductor import ownership_native
from _kimi_stage_lab import exercise
from _kimi_stage_native import StageRefused
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_profile import ProfileRefused


def _await_observer():
    print(json.dumps({"status": "held"}), flush=True)
    if sys.stdin.buffer.readline(9) != b"release\n":
        raise StageRefused("observation incomplete")


def run(case, lab_id):
    if os.name != "nt" or not re.fullmatch("[0-9a-f]{32}", lab_id):
        raise StageRefused("invalid lab id or platform")
    lab = Path(tempfile.gettempdir()) / ("dc-kimi-stage-" + lab_id)
    top = lab / "DecemberCommand"
    relay = top / "relay"
    login = top / "logins" / "synthetic"
    with ExitStack() as hold:
        if case != "recover":
            lab.mkdir()
        hold.callback(ownership_native.NativeHold(lab, directory=True).close)
        if case != "recover":
            top.mkdir()
        hold.callback(ownership_native.NativeHold(top, directory=True).close)
        if case != "recover":
            login.parent.mkdir()
            login.mkdir()
            ProcessRunner.ensure_relay_root(login)
        root = ownership_native.NativeHold(relay, directory=True)
        hold.callback(root.close)
        # Confirm the actual protected DACL while the specific root cannot be exchanged.
        if ProcessRunner.ensure_relay_root(login) != relay:
            raise StageRefused("private relay mismatch")
        return exercise(root, case, handover=_await_observer if case == "hold" else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=["run", "hold", "interrupt", "interrupt-partial", "interrupt-gap", "interrupt-delete", "recover"])
    parser.add_argument("lab_id", help="32 lowercase hexadecimal digits; not a path")
    args = parser.parse_args()
    try:
        result = run(args.case, args.lab_id)
    except (StageRefused, ProfileRefused, OSError):
        print(json.dumps({"status": "refused"}))
        return 3
    print(json.dumps(result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
