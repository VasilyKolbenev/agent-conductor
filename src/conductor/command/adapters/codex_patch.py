"""Validate a bounded Codex patch and apply it to scratch files in an offline AppContainer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import stat
import time

from ..accept_manifest import SnapshotRefused, result_path
from ..containment import portal_violation
from ..long_path import extended
from ..work_layout import work_parts
from .deep_commands import OUTPUT_LIMIT_BYTES
from .harness_attempt import AttemptFolders, install_folder
from .harness_workspace import FILE_BUDGET, _read_work_file
from .process import STDIN_DELIVERED

MAX_FILES = 32
MAX_PATCH = OUTPUT_LIMIT_BYTES["normal"]
KINDS = ("Add", "Update", "Delete")


class PatchRefused(ValueError):
    """A fixed reason, with no proposal, path or other model text."""


@dataclass(frozen=True)
class Operation:
    kind: str
    name: str
    body: tuple[str, ...]

    def for_stage(self, path: Path) -> str:
        return "\n".join((f"*** {self.kind} File: {path.as_posix()}", *self.body))


def parse_patch(raw: bytes) -> list[Operation]:
    if not raw or len(raw) > MAX_PATCH or b"\x00" in raw:
        raise PatchRefused("invalid patch size or content")
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n").removesuffix("\n")
    except UnicodeError:
        raise PatchRefused("patch is not UTF-8") from None
    lines = text.split("\n")
    if ("\r" in text or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch"
            or len(lines) < 3):
        raise PatchRefused("expected a complete patch without surrounding text")
    ops, seen, index = [], set(), 1
    while index < len(lines) - 1:
        header = lines[index]
        kind = next((k for k in KINDS if header.startswith(f"*** {k} File: ")), None)
        if kind is None or len(ops) >= MAX_FILES:
            raise PatchRefused("unexpected patch operation")
        name = header[len(f"*** {kind} File: "):]
        try:
            result_path(name)
        except SnapshotRefused:
            raise PatchRefused("patch names an inadmissible task path") from None
        if name != name.strip() or name.casefold() in seen:
            raise PatchRefused("ambiguous patch path")
        seen.add(name.casefold())
        index += 1
        start = index
        while index < len(lines) - 1 and not lines[index].startswith("*** "):
            index += 1
        body = lines[start:index]
        if kind == "Update" and lines[index] == "*** End of File":
            body.append(lines[index])
            index += 1
        if (any(s.lstrip().startswith("*** ") and s != "*** End of File" for s in body)
                or (kind == "Delete" and body)
                or (kind == "Add" and not all(s.startswith("+") for s in body))
                or (kind == "Update" and (not body or not all(
                    s.startswith((" ", "+", "-", "@@ ")) or s in ("@@", "*** End of File")
                    for s in body)))):
            raise PatchRefused("invalid patch section")
        ops.append(Operation(kind, name, tuple(body)))
    return ops


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise PatchRefused("the Do time limit expired")
    return seconds


def file_image(workspace, args, name):
    parts = work_parts(args.work_item_id, args.task_scope)
    path, found = workspace._file_route(*parts, *name.split("/"))
    if found is None:
        return path, None
    if found.st_size > FILE_BUDGET:
        raise PatchRefused("patch target exceeds the file bound")
    _, data = _read_work_file(path, found, True, FILE_BUDGET)
    if data is None:
        raise PatchRefused("patch target could not be read in full")
    return path, (stat.S_IMODE(found.st_mode), data)


def render_patch(transport, args, cwd, ops, originals, deadline):
    """Only numbered scratch files are writable by the fixed native patcher."""
    exe, = transport._argv_prefix()
    folders = AttemptFolders(work=cwd, home=None, install=install_folder(exe))
    with transport._runner.container_profile(
            mode="review", folders=folders, internet_client=False) as (boundary, paths):
        scratch = Path(paths["runtime"])
        targets = [scratch / f"edit-{i}" for i in range(len(ops))]
        for op, target in zip(ops, targets, strict=True):
            image = originals[op.name]
            if (image is None) != (op.kind == "Add"):
                raise PatchRefused("patch does not match the existing files")
            if image is not None:
                target.write_bytes(image[1])
        sections = [op.for_stage(target) for op, target in zip(ops, targets, strict=True)]
        payload = "\n".join(("*** Begin Patch", *sections, "*** End Patch", "")).encode()
        result = transport._apply_codex_patch(
            cwd, scratch, boundary, payload, timeout=remaining(deadline), output_limit=MAX_PATCH)
        if (result.status != "completed" or result.exit_code != 0
                or result.stdin_state != STDIN_DELIVERED or result.output_truncated):
            raise PatchRefused("patch did not apply to the original contents")
        proposed = {}
        for op, target in zip(ops, targets, strict=True):
            if op.kind == "Delete":
                if os.path.lexists(target):
                    raise PatchRefused("deletion was not established")
                proposed[op.name] = None
                continue
            found = os.lstat(extended(target))
            if (portal_violation(target, found) or not stat.S_ISREG(found.st_mode)
                    or found.st_nlink != 1
                    or found.st_size > FILE_BUDGET):
                raise PatchRefused("inadmissible staged file")
            _, data = _read_work_file(target, found, True, FILE_BUDGET)
            if data is None:
                raise PatchRefused("staged file could not be read in full")
            default_mode = stat.S_IMODE(found.st_mode) if os.name == "nt" else 0o644
            mode = originals[op.name][0] if originals[op.name] else default_mode
            proposed[op.name] = (mode, data)
        return proposed
