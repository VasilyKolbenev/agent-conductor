"""Read GitHub identity and repository choices through the owner's pinned gh.

No credentials or arbitrary URLs cross this boundary. The common tool environment
excludes token/host overrides; gh uses its own separately authenticated profile.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from conductor import tool_env, tool_pins
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.hub.refusals import HubRefusal

FIELDS = "nameWithOwner,description,visibility,updatedAt,isArchived,isFork"
LOGIN_COMMAND = "gh auth login --hostname github.com --web"
OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}\Z")
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}\Z")
LIMIT = 1024 * 1024


class Github:
    def __init__(self, home: Path, *, run=None, verify=None, source=None):
        self.home = Path(home)
        self.source = dict(os.environ if source is None else source)
        self.run = run or ProcessRunner(self.home.parent).run
        self.verify = verify or tool_pins.verify_pin
        self._pin = None
        self._lock = threading.Lock()

    def _read(self, arguments):
        try:
            pins = tool_pins.load_pins(self.home)
            if pins.gh is None:
                raise HubRefusal("gh_not_pinned")
            with self._lock:
                if pins.gh != self._pin:
                    self._pin = self.verify("gh", folder=self.home, source=self.source)
                pin = self._pin
            env = tool_env.tool_env(self.source, pins, self.home)
            result = self.run(CommandSpec((pin.path, *arguments), str(self.home),
                env=env, output_limit=LIMIT, timeout_seconds=15, separate_stderr=True))
        except tool_pins.ToolPinError as error:
            code = error.code if error.code in {"gh_not_pinned", "gh_changed"} else "gh_failed"
            raise HubRefusal(code) from error
        except OSError as error:
            raise HubRefusal("gh_failed") from error
        if result.status in {"timed_out", "stopped"}:
            raise HubRefusal("gh_unreachable")
        if result.exit_code == 4:
            raise HubRefusal("gh_not_logged_in")
        if (result.status != "completed" or result.exit_code != 0 or result.output_truncated
                or len(result.output) > LIMIT or result.output_contains_env_value):
            raise HubRefusal("gh_failed")
        try:
            return result.output.decode("utf-8")
        except UnicodeError as error:
            raise HubRefusal("gh_failed") from error

    def status(self):
        try:
            login = self._read(("api", "user", "--jq", ".login")).rstrip("\r\n")
            if OWNER.fullmatch(login) is None:
                raise HubRefusal("gh_failed")
            return {"state": "ok", "login": login, "login_command": None}
        except HubRefusal as error:
            return {"state": error.code.removeprefix("gh_"), "login": None,
                    "login_command": LOGIN_COMMAND if error.code == "gh_not_logged_in" else None}

    def repositories(self, owner=None):
        if owner is not None and (type(owner) is not str or OWNER.fullmatch(owner) is None):
            raise HubRefusal("contract_invalid")
        argv = ("repo", "list", "--limit", "200", "--json", FIELDS)
        if owner is not None:
            argv += ("--", owner)
        try:
            rows = json.loads(self._read(argv))
            if not isinstance(rows, list) or len(rows) > 200:
                raise ValueError("repository list")
            repos = [repository(row) for row in rows]
        except (ValueError, TypeError, KeyError) as error:
            raise HubRefusal("gh_failed") from error
        return {"owner": owner, "repos": repos, "truncated": len(rows) == 200}


def repository(row):
    if (not isinstance(row, dict) or set(row) != set(FIELDS.split(","))
            or type(row["nameWithOwner"]) is not str or REPO.fullmatch(row["nameWithOwner"]) is None
            or row["visibility"] not in {"PUBLIC", "PRIVATE", "INTERNAL"}
            or type(row["isArchived"]) is not bool or type(row["isFork"]) is not bool
            or type(row["updatedAt"]) is not str
            or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["updatedAt"])
            or row["description"] is not None and type(row["description"]) is not str):
        raise ValueError("repository facts")
    return {"full_name": row["nameWithOwner"],
            "description": None if row["description"] is None else row["description"][:200],
            "visibility": row["visibility"].lower(), "updated_at": row["updatedAt"],
            "archived": row["isArchived"], "fork": row["isFork"]}
