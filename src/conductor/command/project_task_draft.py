"""Finite, volatile editor state, owned by one project server's command session."""
from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass
from threading import Lock

from .api_refusals import ApiRefusal

_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
_KEY = re.compile(r"[0-9a-f]{32}\Z")
_TASK = re.compile(r"task-[a-z0-9]{8,24}\Z")
_DOC = re.compile(r"d-[0-9a-f]{32}\Z")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_TTL = 1800
_CAPACITY = 16
_BYTES = 32768


def require(ok):
    if not ok:
        raise ApiRefusal.fixed("contract_invalid")


def fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names.split()))


def matches(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def validate_answers(answers):
    fields(answers, "title brief hint titleEdited guided withoutGit includeInstructions "
           "items cycleId owner instructions models")
    for key in ("title", "brief", "hint"):
        require(isinstance(answers[key], str))
    for key in ("titleEdited", "guided", "withoutGit"):
        require(type(answers[key]) is bool)
    require(answers["includeInstructions"] is None or type(answers["includeInstructions"]) is bool)
    require(answers["cycleId"] is None or matches(answers["cycleId"], _ID))
    require(isinstance(answers["items"], list) and len(answers["items"]) <= 64)
    for item in answers["items"]:
        require(isinstance(item, dict))
        if item.get("kind") == "project_doc":
            fields(item, "kind docId gitOid mode edits")
            require(matches(item["docId"], _DOC) and matches(item["gitOid"], _OID))
            require(item["mode"] in ("link", "copy") and isinstance(item["edits"], list))
            for edit in item["edits"]:
                fields(edit, "start remove insert")
                require(all(type(edit[k]) is int and 0 <= edit[k] <= 2**31
                            for k in ("start", "remove")))
                require(isinstance(edit["insert"], str))
        else:
            fields(item, "kind title content")
            require(item["kind"] in ("note", "scheme", "plan", "ideas"))
            require(isinstance(item["content"], str) and isinstance(item["title"], str))
    for key in ("owner", "instructions", "models"):
        mapping = answers[key]
        require(isinstance(mapping, dict) and all(matches(role, _ID) for role in mapping))
        for value in mapping.values():
            if key == "owner":
                require(matches(value, _ID))
            elif key == "models":
                fields(value, "provider text")
                require(matches(value["provider"], _ID) and isinstance(value["text"], str)
                        and len(value["text"]) <= 128)
            else:
                fields(value, "source like text back" if isinstance(value, dict) and "back" in value
                       else "source like text")
                require(value["source"] in ("task", "own", "like")
                        and value.get("back", "own") in ("task", "own"))
                require(value["like"] is None or matches(value["like"], _ID))
                require(isinstance(value["text"], str))
    try:
        encoded = json.dumps(answers, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()
    except UnicodeEncodeError:
        raise ApiRefusal.fixed("contract_invalid") from None
    require(len(encoded) <= _BYTES)
    return encoded


@dataclass
class _Draft:
    project: str
    task: str
    expires: float
    revision: int = 0
    answers: bytes | None = None
    last_edit: str | None = None


class TaskDrafts:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = Lock()
        self.rows = {}

    def apply(self, project, body):
        if not project or body.get("project") != project:
            raise ApiRefusal.fixed("project_mismatch")
        op = body.get("op")
        require(op in ("open", "read", "save", "discard"))
        fields(body, {"open": "op project task", "save": "op project key base edit answers",
                      "discard": "op project key base edit"}.get(op, "op project key"))
        if op == "open":
            require(matches(body["task"], _TASK))
        else:
            require(matches(body["key"], _KEY))
        if op in ("save", "discard"):
            require(type(body["base"]) is int and 0 <= body["base"] < 2**53)
            require(matches(body["edit"], _KEY) or (op == "discard" and body["edit"] is None))
        if op == "save":
            encoded = validate_answers(body["answers"])
        with self.lock:
            now = self.clock()
            self.rows = {key: row for key, row in self.rows.items() if row.expires > now}
            if op == "open":
                if len(self.rows) >= _CAPACITY:
                    raise ApiRefusal.fixed("service_refused")
                key = secrets.token_hex(16)
                self.rows[key] = _Draft(project, body["task"], now + _TTL)
                return 201, {"key": key, "revision": 0}
            row = self.rows.get(body["key"])
            if row is None or row.project != project:
                if op == "discard":
                    return 200, {"discarded": True}
                raise ApiRefusal.fixed("route_not_found")
            if op == "discard":
                own_pending = (row.revision == body["base"] + 1 and body["edit"] is not None
                               and row.last_edit == body["edit"])
                if row.revision != body["base"] and not own_pending:
                    raise ApiRefusal.fixed("draft_conflict")
                del self.rows[body["key"]]
                return 200, {"discarded": True}
            if op == "read":
                return 200, {"task": row.task, "revision": row.revision,
                             "answers": None if row.answers is None else json.loads(row.answers)}
            if body["base"] == row.revision:
                row.answers = encoded
                row.last_edit = body["edit"]
                row.expires = now + _TTL
                row.revision += 1
            elif (body["base"] != row.revision - 1 or body["edit"] != row.last_edit
                  or encoded != row.answers):
                raise ApiRefusal.fixed("draft_conflict")
            return 200, {"revision": row.revision}
