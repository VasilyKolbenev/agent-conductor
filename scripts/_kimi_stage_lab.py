"""One fixed synthetic preparation and retirement under a caller-proven private Windows root.

This is the release probe's operation, not the consumer of a person's credentials. Its
caller must hold and verify the root before entering. A future real grant must prove its
own handover, scratch rights and cleanup before it can use the native primitives.
"""
from contextlib import ExitStack
import json
import os

from _kimi_stage_native import HeldObject, StageRefused


# Children are acquired in order and retired in reverse. Parents use their slot, never a path.
TREE = (("attempt", None), ("credentials", 0), ("kimi-code.json", 1), ("config.toml", 0))
RECORD = "stage-record.jsonl"
_CREDENTIAL = b'{"access_token":"synthetic-stage-access","refresh_token":""}\n'
_CONFIG = b'[providers."managed:kimi-code".oauth]\nstorage = "file"\nkey = "oauth/kimi-code"\n'


def _wire(row):
    return json.dumps(row, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"


def _read_record(handle, root):
    data = handle.read()
    if not data.endswith(b"\n"):
        raise StageRefused("partial ownership record")
    try:
        rows = [json.loads(line) for line in data.splitlines()]
        if not rows or data != b"".join(_wire(row) for row in rows):
            raise ValueError
        if _wire(rows[0]) != _wire([1, "root", *root.identity]):
            raise ValueError
    except (ValueError, RecursionError):
        raise StageRefused("invalid ownership record") from None
    made, removing, closed = [], [], False
    for row in rows[1:]:
        if closed or type(row) is not list:
            raise StageRefused("invalid ownership sequence")
        if len(row) == 4 and row[0] == "made":
            index, volume, file = row[1:]
            if (removing or len(made) == len(TREE) or type(index) is not int or index != len(made)
                    or type(volume) is not int or type(file) is not int
                    or not 0 <= volume < 2**64 or not 0 < file < 2**128
                    or (volume, file) in made or (volume, file) == root.identity):
                raise StageRefused("invalid created identity")
            made.append((volume, file))
        elif len(row) == 2 and row[0] == "removing":
            expected = len(made) - len(removing) - 1
            if expected < 0 or type(row[1]) is not int or row[1] != expected:
                raise StageRefused("invalid removal sequence")
            removing.append(expected)
        elif row == ["retired"] and len(removing) == len(made):
            closed = True
        else:
            raise StageRefused("unrecognized ownership record")
    return made, removing, closed


def _children(path):
    with os.scandir(path) as rows:
        names = set()
        for item in rows:
            names.add(item.name)
            if len(names) > len(TREE) + 1:
                raise StageRefused("unexpected children")
        return names


def _paths(root):
    paths = []
    for name, parent in TREE:
        paths.append((root.path if parent is None else paths[parent]) / name)
    return paths


def _check_tree(root, opened):
    root.check()
    paths = _paths(root)
    if _children(root.path) != ({RECORD, "attempt"} if 0 in opened else {RECORD}):
        raise StageRefused("unexpected root content")
    for directory in (0, 1):
        if directory in opened:
            expected = {name for i, (name, parent) in enumerate(TREE)
                        if parent == directory and i in opened}
            if _children(paths[directory]) != expected:
                raise StageRefused("unowned object in staged directory")
    for item in opened.values():
        item.check()


def _retire(root, ledger, *, interrupt_delete=False):
    made, removing, closed = _read_record(ledger, root)
    opened = {}
    with ExitStack() as held:
        for index, expected in enumerate(made):
            name, parent = TREE[index]
            holder = root if parent is None else opened.get(parent)
            if holder is not None:
                try:
                    child = HeldObject(holder, name, create=False)
                except FileNotFoundError:
                    child = None
                if child is not None:
                    held.callback(child.close)
                    if child.identity != expected:
                        raise StageRefused("owned object was replaced")
                    opened[index] = child
                    continue
            if index not in removing:
                raise StageRefused("owned object missing without retirement")
        # Validate the ENTIRE remaining tree before starting a single deletion.
        _check_tree(root, opened)
        if closed:
            if opened:
                raise StageRefused("retired record has live objects")
            return
        for index in reversed(range(len(made))):
            if index not in removing:
                ledger.append(_wire(["removing", index]))
            if index in opened:
                opened[index].delete()
                if interrupt_delete:
                    os._exit(75)
        if _children(root.path) != {RECORD}:
            raise StageRefused("retirement still pending")
        ledger.append(_wire(["retired"]))


def _inspect(root, handles):
    """A held consumer must see the exact test payload, and rename must be refused."""
    if handles[2].read() != _CREDENTIAL or handles[3].read() != _CONFIG:
        raise StageRefused("synthetic payload mismatch")
    for path in _paths(root):
        try:
            path.rename(path.with_name("unpermitted-move"))
        except PermissionError:
            continue
        raise StageRefused("a held object moved")


def exercise(root, case, *, handover=None):
    """Run a fixed non-networked fixture. Never accepts source bytes, a command or child names."""
    if case not in ("run", "hold", "interrupt", "interrupt-partial", "interrupt-gap", "interrupt-delete", "recover"):
        raise StageRefused("unknown case")
    if (handover is not None) != (case == "hold"):
        raise StageRefused("invalid handover")
    create = case != "recover"
    if create and _children(root.path):
        raise StageRefused("lab root not empty")
    with ExitStack() as outer:
        ledger = HeldObject(root, RECORD, create=create)
        outer.callback(ledger.close)
        if create:
            ledger.append(_wire([1, "root", *root.identity]))
            handles = []
            with ExitStack() as live:
                for index, (name, parent) in enumerate(TREE):
                    source = root if parent is None else handles[parent]
                    child = HeldObject(source, name, create=True)
                    live.callback(child.close)
                    if case == "interrupt-gap" and index == 2:
                        os._exit(75)  # no data was written; recovery cannot claim this new object
                    ledger.append(_wire(["made", index, *child.identity]))
                    handles.append(child)
                    if case == "interrupt-partial" and index == 1:
                        os._exit(75)
                _check_tree(root, dict(enumerate(handles)))
                handles[2].append(_CREDENTIAL)
                handles[3].append(_CONFIG)
                _check_tree(root, dict(enumerate(handles)))
                _inspect(root, handles)
                if handover is not None:
                    handover()
                if case == "interrupt":
                    os._exit(75)
        _retire(root, ledger, interrupt_delete=case == "interrupt-delete")
    return {"status": "retired", "checked": create}
