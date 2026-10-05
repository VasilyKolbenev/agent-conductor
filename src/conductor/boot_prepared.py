"""Immutable restart preparations for journals whose records name the boot they were written in.

Two journals keep one boot text per record: the container attempt loans of a project
(`command/adapters/process_acl.py`) and the clone attempts of the hub (`hub/clone.py`). A record
from before the boot counter holds the old string, which proves nothing, and a counter record can
meet another boot environment, where its counter is not comparable. For both the way out is the
same one the project and the login have: an explicit preparation, written only by a person's
command, then a restart that the counter proves inside the environment the preparation was made in.

A preparation is one canonical JSON file next to its record, `<record stem>.prepared-<k>.json`,
made exclusively and never rewritten. It binds the record (the digest of everything but its
phase), the boot the record holds, the identities of the objects the cleanup acts on, the previous
preparation (its digest) and the measurement it was made at. It grants nothing: a recovery stands
on the newest preparation, and only a restart measured after it counts. Reading is strict: every
file is held natively before it is read, a gap or a stray name refuses, and a forged, damaged or
foreign file grants nothing and is kept as it is.

The comparison and the sentences for a refused or needless preparation are `boot_witness`'s; nothing
here reads the OS.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat

from . import boot_witness
from .boot_witness import BootRefused
from .ownership_native import NativeHold
from .ownership_records import canonical, digest, exclusive

PROTOCOL = "conduct.boot-preparation.v1"
_FIELDS = frozenset({"protocol", "kind", "subject", "sequence", "previous_digest",
                     "record_digest", "record_boot", "held", "prepared_boot"})
_LIMIT = 4096


class PreparationInvalid(RuntimeError):
    """A preparation exists but does not stand: it grants nothing and is never overwritten."""


@dataclass(frozen=True)
class Standing:
    """What the preparations of one record say.

    Attributes:
        chain: The preparations in order; empty when there is none or none of them stands.
        reason: None when a restart is proven; else the sentence that names the next action.
    """

    chain: tuple
    reason: str | None


def record_digest(record: dict) -> str:
    """The digest of the facts of a journal record that never change: all but its phase.

    A phase moves on while a record is worked on (a clean-up that fails marks its record), so a
    preparation bound to the phase would be lost by the first failed attempt.
    """
    return digest(canonical({key: value for key, value in record.items() if key != "phase"}))


def facts(kind: str, subject: str, record: dict) -> dict:
    """The facts every preparation of `record` binds: kind, subject, digest, the boot it holds."""
    return {"kind": kind, "subject": subject, "record_digest": record_digest(record),
            "record_boot": record["boot"]}


def schema_fits(schema: object, boot: object) -> bool:
    """Whether a journal record's schema and boot text agree.

    Schema 1 holds the historical boot texts (the old string, a per-boot id); schema 2 holds a
    counter witness. A counter in schema 1, or anything else in schema 2, is not a record this
    build wrote.
    """
    if schema not in (1, 2) or type(schema) is not int:
        return False
    try:
        kind = boot_witness.parse(boot).kind
    except BootRefused:
        return False
    return kind == "counter" if schema == 2 else kind != "counter"


def baseline(record_boot: str, chain) -> str:
    """What a recovery compares with: the newest preparation's measurement, else the record's."""
    return chain[-1]["prepared_boot"] if chain else record_boot


def _invalid(detail: str) -> PreparationInvalid:
    return PreparationInvalid(detail)


def names(directory: Path, stem: str) -> list[Path]:
    """The preparations of the record `stem` in order; a gap or a stray name refuses.

    Raises:
        PreparationInvalid: A name that starts like a preparation of this record but is none, or a
            numbering that is not the whole run 0..n.
    """
    prefix = stem + ".prepared"
    shape = re.compile(re.escape(stem) + r"\.prepared-(0|[1-9][0-9]*)\.json")
    found: dict[int, Path] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.name.startswith(prefix):
                continue
            match = shape.fullmatch(entry.name)
            if match is None:
                raise _invalid("the journal holds a file of this record that is no restart "
                               f"preparation ({entry.name})")
            found[int(match[1])] = Path(entry.path)
    if sorted(found) != list(range(len(found))):
        raise _invalid("the restart preparations of this record are not a whole sequence")
    return [found[number] for number in range(len(found))]


def _hold(files: ExitStack, path: Path) -> None:
    try:
        hold = NativeHold(path)
    except OSError as error:
        raise _invalid(f"a restart preparation cannot be held ({error})") from error
    files.callback(hold.close)


def _read(path: Path) -> dict:
    found = os.lstat(path)
    if (not stat.S_ISREG(found.st_mode) or getattr(found, "st_reparse_tag", 0)
            or found.st_nlink != 1):
        raise _invalid("a restart preparation is not a plain file with one name")
    with open(path, "rb") as stream:
        raw = stream.read(_LIMIT + 1)
    if len(raw) > _LIMIT:
        raise _invalid("a restart preparation exceeds its size bound")
    try:
        value = json.loads(raw)
        again = canonical(value)
    except (ValueError, TypeError, RecursionError) as error:
        raise _invalid("a restart preparation is malformed") from error
    if type(value) is not dict or again != raw:
        raise _invalid("a restart preparation is not a canonical closed record")
    return value


def _pair(value: object) -> bool:
    return (type(value) is list and len(value) == 2
            and all(type(part) is int and part >= 0 for part in value))


def _held_ok(held: object, expected: dict) -> bool:
    if type(held) is not dict or set(held) != set(expected):
        return False
    return all(value is None or (_pair(value) and value == expected[key])
               for key, value in held.items())


def _checked(value: dict, index: int, earlier: list, expected: dict, expected_held: dict) -> dict:
    if set(value) != _FIELDS or value["protocol"] != PROTOCOL:
        raise _invalid("the restart preparation has another shape")
    for key, wanted in expected.items():
        if value[key] != wanted:
            raise _invalid(f"the restart preparation does not belong to this record ({key})")
    previous = digest(canonical(earlier[-1])) if earlier else None
    if (type(value["sequence"]) is not int or value["sequence"] != index
            or value["previous_digest"] != previous):
        raise _invalid("the restart preparation does not follow the one before it")
    if not boot_witness.is_counter(value["prepared_boot"]):
        raise _invalid("the restart preparation holds no counter")
    if not _held_ok(value["held"], expected_held):
        raise _invalid("the restart preparation holds other objects than the record names (held)")
    standing = boot_witness.parse(baseline(expected["record_boot"], earlier))
    if (standing.kind == "counter"
            and standing.scope == boot_witness.parse(value["prepared_boot"]).scope):
        raise _invalid("the restart preparation stands in the environment that already stands")
    return value


def read_chain(files: ExitStack, directory: Path, stem: str, expected: dict,
               expected_held: dict) -> tuple:
    """The preparations of a record in order, each held natively and checked; `()` when none.

    A record that holds a per-boot id (Linux, macOS) needs none and is never asked for any. For the
    others every file is held before it is read, and a damaged, partial, foreign, misnumbered or
    unlinked one refuses.

    Args:
        files: The stack that keeps the holds open until the caller is done acting on the record.
        directory: The journal directory.
        stem: The record's file stem, such as `acl-<attempt>`.
        expected: The facts the record binds (`facts`).
        expected_held: The identities the record names, by object key; each preparation holds
            exactly these or, for an object that was absent when it was made, `None`.

    Raises:
        PreparationInvalid: A preparation does not stand.
    """
    if boot_witness.parse(expected["record_boot"]).kind == "unique":
        return ()
    chain: list[dict] = []
    for index, path in enumerate(names(directory, stem)):
        _hold(files, path)
        chain.append(_checked(_read(path), index, chain, expected, expected_held))
    return tuple(chain)


def unproven_advice(error: BootRefused, command: str) -> str:
    """The sentence that says what to do when no restart is proven for a record."""
    if error.code == "same_boot":
        return "restart the OS (do a full Restart, not a shutdown), then recover again"
    if error.code == "other_scope":
        return boot_witness.other_environment_advice(error, command)
    if error.code == "legacy_value":
        return ("this record predates the boot counter and cannot prove a restart; run "
                f"`{command} --prepare-restart`, restart the OS (a full Restart, not a shutdown), "
                f"then run `{command}` again")
    return f"no restart is proven: {error.detail}"


def standing(files: ExitStack, directory: Path, stem: str, expected: dict, expected_held: dict,
             current: str, command: str) -> Standing:
    """Whether the boot measured now proves a restart for the record, and what to do if not.

    Args:
        current: The boot measurement now.
        command: The recovery command the sentences name, such as `ownership recover-clones`.
    """
    try:
        chain = read_chain(files, directory, stem, expected, expected_held)
    except PreparationInvalid as error:
        return Standing((), "the restart preparations of this record do not stand: "
                            f"{error}; they are kept as they are, nothing is deleted")
    try:
        boot_witness.prove_restart(baseline(expected["record_boot"], chain), current)
    except BootRefused as error:
        return Standing(chain, unproven_advice(error, command))
    return Standing(chain, None)


def decide(record_boot: str, chain, current: str) -> bool:
    """Whether a NEW preparation may be written now (`boot_witness.preparation_needed`).

    Returns:
        True to write one, False when the newest one stands.

    Raises:
        BootRefused: No preparation is needed or possible; the code says why.
    """
    return boot_witness.preparation_needed(baseline(record_boot, chain), current,
                                           prepared=bool(chain))


def appeared(chain, expected_held: dict, present) -> tuple[str, ...]:
    """The objects that exist now but were not held when the newest preparation was made."""
    if not chain:
        return ()
    held = chain[-1]["held"]
    return tuple(key for key in present if held.get(key) != expected_held[key])


def write_next(files: ExitStack, directory: Path, stem: str, expected: dict, held: dict,
               chain, current: str) -> dict:
    """Create the next preparation exclusively; an existing name is never overwritten.

    Raises:
        FileExistsError: The numbered name is taken.
        PreparationInvalid: The file read back is not the one written.
    """
    index = len(chain)
    row = {"protocol": PROTOCOL, **expected, "sequence": index,
           "previous_digest": digest(canonical(chain[-1])) if chain else None,
           "held": held, "prepared_boot": current}
    path = directory / f"{stem}.prepared-{index}.json"
    exclusive(path, canonical(row))
    _hold(files, path)
    if path.read_bytes() != canonical(row):
        raise _invalid("the created restart preparation was replaced")
    return row
