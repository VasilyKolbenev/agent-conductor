"""Stand-ins shared by the tests of the two journals that name a boot in every record.

The journals are the attempt ACL loans of a project and the clone attempts of the hub. A record of
either one is written with the boot measurement of its time; a record from before the boot counter
holds the old `windows:<uuid>` string, which proves nothing. Every restart in these tests is a
model: the one seam is `ownership_boot.current_boot` (`tests/_boot_world.measure`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from conductor import ownership_records as records
from tests._boot_world import GUID, OTHER_GUID, counter

#: The old class-90 string of the same machine and one that no reader of this host would give.
LEGACY_SAME_MACHINE = f"windows:{GUID}"
LEGACY_OTHER = f"windows:{OTHER_GUID}"
THIRD_GUID = "22222222-3333-4444-8555-666666666666"
LEGACY_TEXTS = (LEGACY_SAME_MACHINE, LEGACY_OTHER)


def tree(root: Path, skip: tuple[str, ...] = ()) -> dict[str, bytes | None]:
    """Every file below `root` as {relative path: bytes}, and every directory as {path: None}.

    A name in `skip` is listed but not read (a file another process holds exclusively).
    """
    found: dict[str, bytes | None] = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        found[key] = path.read_bytes() if path.is_file() and key not in skip else None
    return found


def rewrite(path: Path, change) -> None:
    """Read a canonical JSON file, let `change` edit the dict, write it back canonically."""
    row = json.loads(path.read_bytes())
    change(row)
    path.write_bytes(records.canonical(row))


def read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def first_held_key(row: dict) -> str:
    return next(iter(row["held"]))


def _digest_of_nothing(row):
    row["record_digest"] = "sha256:" + "0" * 64


def _other_record_boot(row):
    row["record_boot"] = LEGACY_OTHER if row["record_boot"] != LEGACY_OTHER else LEGACY_SAME_MACHINE


def _foreign_identity(row):
    row["held"][first_held_key(row)] = [9, 9]


def _missing_key(row):
    del row["held"][first_held_key(row)]


def _object_not_held(row):
    row["held"][first_held_key(row)] = None


#: Every field of a preparation, forged once; each yields a file the checker must refuse.
FORGERIES = {
    "another record digest": _digest_of_nothing,
    "another recorded boot": _other_record_boot,
    "another subject": lambda row: row.update(subject="somebody-else"),
    "another kind": lambda row: row.update(kind="login-lease"),
    "a wrong sequence number": lambda row: row.update(sequence=1),
    "a previous digest on the first": lambda row: row.update(previous_digest="sha256:" + "1" * 64),
    "a legacy boot as the preparation": lambda row: row.update(prepared_boot=LEGACY_OTHER),
    "a per-boot id as the preparation": lambda row: row.update(
        prepared_boot="linux:00000000-1111-4222-8333-444444444444"),
    "an identity that is not the record's": _foreign_identity,
    "a held object missing": _missing_key,
    "an extra field": lambda row: row.update(extra=1),
    "another protocol": lambda row: row.update(protocol="conduct.boot-preparation.v2"),
    "a preparation that holds a counter of the standing environment": lambda row: row.update(
        prepared_boot=counter(99, GUID)),
}

#: Forgeries that only a counter record can have: its own environment is the standing one.
STANDING_ENVIRONMENT = "a preparation that holds a counter of the standing environment"


def damage(path: Path, how: str) -> None:
    """Break a preparation file in a way no field edit can: bytes, form, size, links."""
    good = path.read_bytes()
    if how == "truncated":
        path.write_bytes(good[: len(good) // 2])
    elif how == "empty":
        path.write_bytes(b"")
    elif how == "pretty-printed":
        path.write_bytes(json.dumps(json.loads(good), indent=2).encode("utf-8"))
    elif how == "oversize":
        path.write_bytes(good + b" " * 5000)
    elif how == "not json":
        path.write_bytes(b"\xff\xfe not a record")
    elif how == "a second name":
        os.link(path, path.with_name("alias.json"))
    else:
        raise ValueError(how)


DAMAGE = ("truncated", "empty", "pretty-printed", "oversize", "not json", "a second name")
