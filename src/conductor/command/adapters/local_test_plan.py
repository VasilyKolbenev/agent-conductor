"""The owner-bound opt-in local-test policy and its bounded, plain runtime inventory."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from time import monotonic

from ..containment import first_directory_violation, portal_violation
from .codex_patch import PatchRefused, validate_path

TEST_MARKER = "\n\nconduct.test-plan.v1\n"
SOURCE_MARKER = "\n\nconduct.patch-sources.v1\n"
_HEX = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PLAN_KEYS = {"runner", "toolchain", "start", "pattern", "timeout_seconds"}
MAX_RUNTIME_ENTRIES = 16384
MAX_RUNTIME_BYTES = 512 * 1024 * 1024
MAX_RUNTIME_FILE = 64 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def _bad():
    return PatchRefused("invalid initial test plan")


def _unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise _bad()
    return result


@dataclass(frozen=True)
class TestPlan:
    install: str
    runtime_digest: str
    start: str
    pattern: str
    timeout_seconds: int
    runner: str = "python-unittest-v1"
    entry: str = "python.exe"

    def as_dict(self):
        return {"runner": self.runner, "toolchain": self.toolchain(), "start": self.start,
                "pattern": self.pattern, "timeout_seconds": self.timeout_seconds}

    def toolchain(self):
        return {"install": self.install, "entry": self.entry,
                "runtime_digest": self.runtime_digest}

    @property
    def digest(self):
        return digest(self.as_dict())

    @property
    def toolchain_digest(self):
        return digest(self.toolchain())


def read_plan(value):
    """Validate closed JSON data without opening or executing the selected toolchain."""
    if type(value) is not dict or set(value) != _PLAN_KEYS:
        raise _bad()
    tool = value["toolchain"]
    if (value["runner"] != "python-unittest-v1" or type(tool) is not dict
            or set(tool) != {"install", "entry", "runtime_digest"}
            or tool["entry"] != "python.exe" or type(tool["install"]) is not str
            or not tool["install"] or len(tool["install"]) > 1024
            or "\0" in tool["install"] or not Path(tool["install"]).is_absolute()
            or type(tool["runtime_digest"]) is not str
            or _HEX.fullmatch(tool["runtime_digest"]) is None):
        raise _bad()
    install = Path(tool["install"])
    parts = tool["install"].replace("\\", "/").split("/")
    if (install.parent.parent.name.casefold() != "harnesses"
            or any(part in (".", "..") for part in parts)):
        raise _bad()
    start, pattern, timeout = (value[k] for k in ("start", "pattern", "timeout_seconds"))
    if (type(start) is not str or len(start) > 320
            or type(pattern) is not str or not pattern or len(pattern) > 160
            or any(c in pattern for c in ("/", "\\", ":", "\0", "\r", "\n"))
            or pattern in (".", "..") or type(timeout) is not int or not 1 <= timeout <= 86400):
        raise _bad()
    try:
        validate_path(start)
    except PatchRefused:
        raise _bad() from None
    if any(part.startswith(".") for part in start.split("/")):
        raise _bad()
    return TestPlan(str(install), tool["runtime_digest"], start, pattern, timeout)


def plan_for(bound_document, instruction=None):
    """Only an initial bound instruction may opt in; malformed markers never mean legacy."""
    if isinstance(bound_document, Mapping):
        content = bound_document.get("content", "")
        source_action = bound_document.get("source_action_id")
    else:
        content = getattr(bound_document, "content", "")
        source_action = getattr(bound_document, "source_action_id", None)
    text = instruction if instruction is not None else content
    if type(text) is not str:
        raise _bad()
    if "conduct.test-plan.v1" not in text:
        return None
    if (bound_document is None or source_action is not None
            or content != text or text.count(TEST_MARKER) != 1
            or text.count("conduct.test-plan.v1") != 1
            or text.count(SOURCE_MARKER) > 1):
        raise _bad()
    before, _, encoded = text.partition(TEST_MARKER)
    if SOURCE_MARKER in before:
        raise _bad()
    encoded, _source, _names = encoded.partition(SOURCE_MARKER)
    try:
        value = json.loads(encoded, object_pairs_hook=_unique)
        return read_plan(value)
    except (ValueError, TypeError, RecursionError):
        raise _bad() from None


def inventory_digest(install, *, deadline=None):
    """Hash every regular singly named file and directory; follow no portals or links."""
    root = Path(install)
    if (not root.is_absolute() or not root.is_dir()
            or first_directory_violation((*reversed(root.parents), root))):
        raise PatchRefused("test runtime is not a plain installation")
    pending, rows, seen, total = [root], [], set(), 0
    while pending:
        folder = pending.pop()
        with os.scandir(folder) as children:
            entries = sorted(children, key=lambda row: row.name.casefold())
        for entry in entries:
            if deadline is not None and monotonic() >= deadline:
                raise PatchRefused("the Do time limit expired")
            path = Path(entry.path)
            found = os.lstat(path)
            name = path.relative_to(root).as_posix()
            key = name.casefold()
            if (key in seen or len(rows) >= MAX_RUNTIME_ENTRIES
                    or portal_violation(path, found)):
                raise PatchRefused("test runtime inventory is not plain and bounded")
            seen.add(key)
            if stat.S_ISDIR(found.st_mode):
                rows.append({"path": name, "directory": True})
                pending.append(path)
                continue
            if (not stat.S_ISREG(found.st_mode) or found.st_nlink != 1
                    or found.st_size > MAX_RUNTIME_FILE
                    or total + found.st_size > MAX_RUNTIME_BYTES):
                raise PatchRefused("test runtime inventory is not plain and bounded")
            image = hashlib.sha256()
            length = 0
            with path.open("rb") as stream:
                held = os.fstat(stream.fileno())
                if ((held.st_dev, held.st_ino) != (found.st_dev, found.st_ino)
                        or held.st_size != found.st_size or held.st_nlink != 1):
                    raise PatchRefused("test runtime changed during inventory")
                while data := stream.read(1024 * 1024):
                    length += len(data)
                    if length > found.st_size or deadline is not None and monotonic() >= deadline:
                        raise PatchRefused("test runtime inventory exceeded its bound")
                    image.update(data)
            after = os.lstat(path)
            if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                    != (found.st_dev, found.st_ino, found.st_size, found.st_mtime_ns)
                    or length != found.st_size):
                raise PatchRefused("test runtime changed during inventory")
            total += length
            rows.append({"path": name, "length": length, "sha256": image.hexdigest()})
    return digest(sorted(rows, key=lambda row: row["path"]))


def vet_runtime(plan, *, deadline=None):
    entry = os.lstat(Path(plan.install) / plan.entry)
    if (not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1
            or inventory_digest(plan.install, deadline=deadline) != plan.runtime_digest):
        raise PatchRefused("test runtime pin mismatch")
