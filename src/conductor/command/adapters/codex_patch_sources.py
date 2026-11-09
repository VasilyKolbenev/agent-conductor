"""Supply only the task files declared in the reviewed, bound patch instruction."""
import hashlib
import json

from . import codex_patch
from .harness_workspace import WorkspaceNotContained
from .independent_check import CheckFrameError, scan_material
from .process import STDIN_LIMIT


_HEADER = ("\n\nTASK SOURCE FILES\nCurrent contents for the following task-relative paths. "
           "Use them as source data. No shell read of these files is needed.\n")
SOURCE_MARKER = "\n\nconduct.patch-sources.v1\n"


def _names(instruction):
    if instruction is None or instruction.source_action_id is not None:
        return ()
    _, marker, encoded = instruction.content.partition(SOURCE_MARKER)
    if not marker:
        return ()
    try:
        names = json.loads(encoded)
        if (type(names) is not list or len(names) > codex_patch.MAX_FILES
                or any(type(name) is not str for name in names)):
            raise ValueError
        for name in names:
            codex_patch.validate_path(name)
            if any(part.startswith(".") for part in name.split("/")):
                raise ValueError
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError
    except (ValueError, RecursionError):
        raise codex_patch.PatchRefused("invalid patch source list") from None
    return names


def source_section(workspace, args, work, before, instruction, sensitive_values):
    names = _names(instruction)
    if not names:
        return ""
    prefix = workspace.subtree(work)
    sensitive = sensitive_values()
    lines, size = [], len(_HEADER)
    for name in names:
        try:
            _, image = codex_patch.file_image(workspace, args, name)
        except (WorkspaceNotContained, codex_patch.PatchRefused, OSError):
            raise codex_patch.PatchRefused("named patch source cannot be read safely") from None
        digest = hashlib.sha256(image[1]).hexdigest() if image is not None else None
        if digest != before.get(prefix + name):
            raise codex_patch.PatchRefused("named patch source changed before preparation")
        row = {"path": name, "state": "absent"}
        try:
            if image is not None:
                text = image[1].decode("utf-8")
                if "\0" in text:
                    raise codex_patch.PatchRefused("named patch source cannot be sent as text")
                row = {"path": name, "sha256": digest, "content": text}
            scan_material(row, sensitive)
        except (UnicodeError, CheckFrameError):
            raise codex_patch.PatchRefused("named patch source cannot be sent as text") from None
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        size += len(line.encode("utf-8")) + 1
        if size > STDIN_LIMIT:
            raise codex_patch.PatchRefused("named patch sources exceed the task channel")
        lines.append(line)
    return _HEADER + "\n".join(lines)
