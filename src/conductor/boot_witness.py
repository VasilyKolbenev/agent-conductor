"""The boot witness: one closed text format and the one comparison that proves a restart.

Three kinds of witness text exist. `counter` is the Windows scheme, an environment GUID and a
strictly increasing boot counter. `unique` is a random per-boot id (`linux:<uuid>`,
`darwin:<uuid>`): only its difference proves a restart. `legacy` is the old Windows string
(`windows:<uuid>`): it can be read, but it never proves anything, because it holds no counter; a
record that holds only it is recovered through an explicit preparation.

Nothing here touches the OS; the readers live in `boot_kuser` and `ownership_native`.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

COUNTER_SCHEME = "windows-bootid.v1"
#: The largest counter a witness may hold. 0xFFFFFFFF is refused: nothing could exceed it later.
MAX_COUNTER = 0xFFFFFFFE

#: Every reason a boot witness is refused: the comparison first, then the readers.
CODES = frozenset({
    "same_boot", "counter_decreased", "counter_overflow", "other_scope", "other_scheme",
    "legacy_value", "unknown_format", "preparation_unneeded",
    "unsupported_platform", "native_unavailable", "layout_unknown", "partial_read",
    "value_empty"})

_UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
_UUID_ONLY = re.compile(_UUID)
_COUNTER = re.compile(rf"{re.escape(COUNTER_SCHEME)}:({_UUID}):([0-9]{{1,20}})")
_PER_BOOT = re.compile(rf"(linux|darwin):({_UUID})")
_LEGACY = re.compile(rf"(windows):({_UUID})")


class BootRefused(RuntimeError):
    """A boot witness was refused, with a closed code and a sentence a person can act on."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in CODES:
            raise ValueError(f"code must be one of {', '.join(sorted(CODES))}")
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class Witness:
    """A parsed witness: `kind`, `scheme`, `scope` (GUID or uuid) and, for a counter, its value."""

    text: str
    kind: str
    scheme: str
    scope: str
    counter: int | None = None


def counter_text(scope: str, counter: int) -> str:
    """Build the text of a counter witness.

    Args:
        scope: The environment GUID, lowercase 8-4-4-4-12.
        counter: The boot counter, 1 up to `MAX_COUNTER`.

    Raises:
        BootRefused: `value_empty` for 0, `counter_overflow` above `MAX_COUNTER`,
            `unknown_format` for anything that is not a GUID and a plain integer.
    """
    if type(scope) is not str or _UUID_ONLY.fullmatch(scope) is None:
        raise BootRefused("unknown_format", "the boot environment is not a lowercase GUID")
    if type(counter) is not int or counter < 0:
        raise BootRefused("unknown_format", "the boot counter is not a non-negative integer")
    if counter == 0:
        raise BootRefused("value_empty", "the boot counter is 0, which names no boot")
    if counter > MAX_COUNTER:
        raise BootRefused("counter_overflow", _no_room(counter))
    return f"{COUNTER_SCHEME}:{scope}:{counter}"


def parse(text: object) -> Witness:
    """Parse one witness text.

    Raises:
        BootRefused: `unknown_format` unless the text is exactly one of the three closed forms;
            `counter_overflow` for a counter above `MAX_COUNTER`.
    """
    if type(text) is not str:
        raise BootRefused("unknown_format", "a boot witness is a text")
    found = _COUNTER.fullmatch(text)
    if found is not None:
        digits = found[2]
        if digits[0] == "0":
            raise BootRefused("unknown_format", "a boot counter has no leading zero and is not 0")
        return Witness(text, "counter", COUNTER_SCHEME, found[1], _checked(int(digits)))
    found = _PER_BOOT.fullmatch(text)
    if found is not None:
        return Witness(text, "unique", found[1], found[2])
    found = _LEGACY.fullmatch(text)
    if found is not None:
        return Witness(text, "legacy", found[1], found[2])
    raise BootRefused("unknown_format", "the text is none of the closed boot witness forms")


def _checked(value: int) -> int:
    if value > MAX_COUNTER:
        raise BootRefused("counter_overflow", _no_room(value))
    return value


def _no_room(value: int) -> str:
    return f"the boot counter {value} leaves no room for a later boot to exceed it"


def is_counter(text: object) -> bool:
    """True when `text` is a well-formed counter witness."""
    try:
        return parse(text).kind == "counter"
    except BootRefused:
        return False


def is_legacy(text: object) -> bool:
    """True when `text` is the old `windows:<uuid>` string, which proves no restart."""
    try:
        return parse(text).kind == "legacy"
    except BootRefused:
        return False


def _side(text: object, name: str) -> Witness:
    try:
        return parse(text)
    except BootRefused as error:
        detail = f"the {name} boot witness is refused: {error.detail}"
        raise BootRefused(error.code, detail) from error


def prove_restart(recorded: str, current: str) -> Witness:
    """Prove that the OS restarted between two measurements, or refuse with the reason.

    The same scheme and scope are required. A counter must be strictly greater. A per-boot id
    must differ. A legacy value on either side never proves anything.

    Args:
        recorded: The witness stored when the owner wrote its record.
        current: The witness measured now.

    Returns:
        The parsed current witness.

    Raises:
        BootRefused: with the code that names why no restart is proven.
    """
    before, after = _side(recorded, "recorded"), _side(current, "current")
    if "legacy" in (before.kind, after.kind):
        raise BootRefused("legacy_value", (
            "a legacy boot value cannot prove a restart, whatever the other side holds; "
            "prepare the record first (--prepare-restart), restart the OS, then recover"))
    if before.scheme != after.scheme:
        raise BootRefused("other_scheme", (
            f"the recorded boot scheme {before.scheme} is not the current {after.scheme}; "
            "different schemes are never compared"))
    if before.kind == "unique":
        return _unique(before, after)
    return _counter(before, after)


def _unique(before: Witness, after: Witness) -> Witness:
    if before.scope == after.scope:
        raise _same_boot()
    return after


def _counter(before: Witness, after: Witness) -> Witness:
    if before.scope != after.scope:
        raise BootRefused("other_scope", (
            f"the recorded boot environment {before.scope} is not the current {after.scope}; "
            "counters of different environments are not comparable"))
    if after.counter == before.counter:
        raise _same_boot()
    if after.counter < before.counter:
        raise BootRefused("counter_decreased", (
            f"the current boot counter {after.counter} is lower than the recorded "
            f"{before.counter}; a lower counter proves no restart"))
    return after


def _same_boot() -> BootRefused:
    return BootRefused("same_boot", (
        "the boot has not changed since the record was written, so the OS has not restarted; "
        "restart the OS (do a full Restart, not a shutdown) and try again"))


def preparation_needed(recorded: str, current: str, *, prepared: bool) -> bool:
    """Decide whether a NEW preparation may be written, or the standing one is the answer.

    A preparation records the measurement a later recovery must be newer than. Only a counter of
    the same boot environment can be exceeded, so a measurement from another environment is the
    one case where a record, or an earlier preparation, needs a new baseline. Nothing here
    permits a recovery: a preparation grants nothing, and a restart inside the new environment is
    still required.

    Args:
        recorded: What a recovery would compare with: the measurement of the latest preparation
            when `prepared`, else the boot the record itself holds.
        current: The measurement taken now.
        prepared: Whether `recorded` is the measurement of a preparation.

    Returns:
        True to write a new preparation, False when the standing preparation stands (a repeat
        in the same environment never moves its baseline, whatever the counter now reads).

    Raises:
        BootRefused: `unknown_format` or `counter_overflow` for a side that is not a witness;
            `other_scheme` when `current` is not a counter; `preparation_unneeded` for a per-boot
            id record or a record whose restart is already proven; `same_boot` or
            `counter_decreased` for a counter of this environment with no preparation. A lower
            counter, an overflow and an unreadable measurement are never a way to prepare again.
    """
    before, after = _side(recorded, "recorded"), _side(current, "current")
    if before.kind == "unique":
        raise BootRefused("preparation_unneeded", (
            "this record holds a per-boot id, which a later id proves a restart with; "
            "nothing can be prepared"))
    if after.kind != "counter":
        raise BootRefused("other_scheme", (
            "the current boot measurement is not a counter witness, so no restart can be "
            "prepared with it"))
    if before.kind == "legacy" or before.scope != after.scope:
        return True
    if prepared:
        return False
    prove_restart(recorded, current)
    raise BootRefused("preparation_unneeded", (
        "a restart is already proven for this record by the counter now read"))


def preparation_refusal(error: BootRefused, command: str) -> str:
    """The sentence for a preparation that was refused, naming the recovery command to use.

    Args:
        error: What `preparation_needed` raised, or the reader's own refusal.
        command: The recovery command this refusal belongs to, such as `ownership recover`.
    """
    if error.code == "same_boot":
        return ("no preparation is needed: the record already holds a comparable boot and the "
                "OS has not restarted since it was written; do a full Restart (not a shutdown), "
                f"then run `{command}`")
    if error.code == "preparation_unneeded":
        return f"no preparation is needed: {error.detail}; run `{command}`"
    if error.code == "other_scheme":
        return "this OS gives no boot counter to prepare a restart with"
    if error.code == "counter_decreased":
        return f"nothing can be prepared: {error.detail}"
    return f"the OS boot cannot be measured, so no restart can be prepared: {error}"


def other_environment_advice(error: BootRefused, command: str) -> str:
    """What to do when the recorded boot environment is not the current one.

    A second Restart cannot make the old environment the current one, so the only exit is an
    explicit new preparation in the current environment, followed by a Restart inside it.
    """
    return (f"no restart is proven: {error.detail}. Another Restart does not make the old "
            f"environment the current one: run `{command} --prepare-restart` to prepare in the "
            f"current boot environment, do a full Restart, then run `{command}` again")
