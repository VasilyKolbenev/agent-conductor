"""The short lived, UI-triggered native folder chooser for the hub."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def _tkinter() -> dict:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(parent=root, mustexist=True)
    finally:
        root.destroy()
    return {"path": path} if path else {"cancelled": True}


def _command(argv: list[str], *, mac: bool = False) -> dict:
    completed = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                               timeout=590, check=False)
    if completed.returncode == 0:
        path = completed.stdout.decode("utf-8").strip()
        return {"path": path} if path else {"cancelled": True}
    if mac:
        return {"cancelled": True} if b"-128" in completed.stderr else {"unavailable": True}
    return {"cancelled": True} if completed.returncode == 1 else {"unavailable": True}


def choose(backend: str) -> dict:
    if backend == "windows":
        return _tkinter()
    if backend == "mac":
        return _command(["/usr/bin/osascript", "-e", "POSIX path of (choose folder)"], mac=True)
    if backend == "linux":
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return {"unavailable": True}
        for executable, args in (("/usr/bin/zenity", ["--file-selection", "--directory"]),
                                 ("/usr/bin/kdialog", ["--getexistingdirectory"])):
            if os.path.isfile(executable) and os.access(executable, os.X_OK):
                answer = _command([executable, *args])
                if "unavailable" not in answer:
                    return answer
        return _tkinter()
    return {"unavailable": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("windows", "mac", "linux"), required=True)
    args = parser.parse_args(argv)
    try:
        answer = choose(args.backend)
    except (OSError, ImportError, RuntimeError, subprocess.TimeoutExpired):
        answer = {"unavailable": True}
    print(json.dumps(answer, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
