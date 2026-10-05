"""The boot witness: one closed text format and the one comparison that proves a restart.

Three kinds of witness text exist. `counter` is the Windows scheme, an environment GUID and a
strictly increasing boot counter. `unique` is a random per-boot id (`linux:<uuid>`,
`darwin:<uuid>`): only its difference proves a restart. `legacy` is the old Windows string
(`windows:<uuid>`): it can be read, but it never proves anything, because the id it holds does not
change with a boot.

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
    "legacy_value", "unknown_format",
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
        "restart the OS (a full Restart: sleep, hibernate and a Fast Startup shutdown keep the "
        "same boot) and try again"))
