"""A scripted stand-in for the pinned `gh`, built as a REAL executable (spec 9.12).

The product runs the pinned `gh` through its process runner, and `tool_env` hands a child no
variable of the test's own, so neither the scenario nor the record of what happened can travel
by environment. Both are FILES beside the executable instead:

- `gh-script.json` maps a command (its first two arguments: `repo view`, `pr list`,
  `pr create`) to a list of replies, taken in order, the last one repeating. A reply is
  `{"exit": 0, "stdout": "...", "sleep": 0}`; a command with no entry exits 1;
- `gh-log.jsonl` gets one JSON line per call: the arguments, what arrived on stdin, the NAMES
  of the environment variables (never their values: a token set by a test must not be copied
  into a second place), and the `PATH` value, which the pinned-path witness needs.

`--version` answers the first line a pin reads and is not logged. Importing this module runs
nothing; the child body is `main`.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SCRIPT_NAME = "gh-script.json"
LOG_NAME = "gh-log.jsonl"
VERSION_LINE = "gh version 2.50.0 (2026-01-01)\n"
REPO = "o/r"


def build_executable(directory):
    """A real single-file executable named `gh` in `directory`, or None on a host with no stub."""
    from tests import _fakeexe
    return _fakeexe.build(directory, "gh", "_fakegh")


def script(directory, replies):
    """Write the scenario beside the executable: `{"pr list": [reply, ...], ...}`."""
    Path(directory, SCRIPT_NAME).write_text(json.dumps(replies), encoding="utf-8")


def calls(directory):
    """Every call recorded so far, oldest first; a missing log means no call."""
    try:
        text = Path(directory, LOG_NAME).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def said(stdout="", exit=0, sleep=0):
    """One reply: what the command prints, its exit code, and seconds to wait first."""
    return {"exit": exit, "stdout": stdout, "sleep": sleep}


def repo_view(name=REPO, permission="WRITE", archived=False, default="main"):
    """The reply of `gh repo view --json nameWithOwner,defaultBranchRef,viewerPermission,...`."""
    return said(json.dumps({
        "nameWithOwner": name, "defaultBranchRef": {"name": default},
        "viewerPermission": permission, "isArchived": archived}))


def pr_row(number, head_oid, *, repo=REPO, base="main", head="conduct/run-001", cross=False,
           state="OPEN", draft=False):
    """One row of `gh pr list --json ...`."""
    return {"number": number, "url": f"https://github.com/{repo}/pull/{number}", "state": state,
            "headRefName": head, "headRefOid": head_oid, "baseRefName": base,
            "isCrossRepository": cross, "isDraft": draft}


def pr_list(*rows):
    """The reply of `gh pr list`: a JSON array of rows."""
    return said(json.dumps(list(rows)))


def created(number, repo=REPO):
    """The reply of `gh pr create`: the address of the pull request on its own line."""
    return said(f"https://github.com/{repo}/pull/{number}\n")


def _pick(replies, key, before):
    chosen = replies.get(key) or [said(exit=1)]
    return chosen[min(before, len(chosen) - 1)]


def main():
    arguments = sys.argv[1:]
    if arguments == ["--version"]:
        sys.stdout.buffer.write(VERSION_LINE.encode("ascii"))
        return 0
    here = Path(sys.argv[0]).resolve().parent
    stdin = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    key = " ".join(arguments[:2])
    log = here / LOG_NAME
    before = len([row for row in calls(here) if row["key"] == key])
    with log.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({
            "key": key, "argv": arguments, "stdin": stdin, "env_names": sorted(os.environ),
            "path": os.environ.get("PATH", ""), "cwd": os.getcwd()}) + "\n")
    try:
        replies = json.loads((here / SCRIPT_NAME).read_text(encoding="utf-8"))
    except OSError:
        replies = {}
    answer = _pick(replies, key, before)
    time.sleep(answer.get("sleep", 0))
    sys.stdout.buffer.write(answer.get("stdout", "").encode("utf-8"))   # bytes: no CRLF on Windows
    sys.stdout.buffer.flush()
    return answer.get("exit", 0)
