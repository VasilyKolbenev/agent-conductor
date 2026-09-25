"""Optional in-memory attempt serialization; no authority or execution door.

Registrations carry values and bound callbacks, not factories to be called while
discovering an adapter. The resource remains strongly referenced and is compared
by identity only. A descriptor says which cooperating resource a transport holds;
it does not prove filesystem ownership or constrain arbitrary plugin code.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MemberDescriptorType


class AttemptScopeError(ValueError):
    """An explicitly supplied attempt scope is not the value this SDK accepts."""


@dataclass(frozen=True, eq=False)
class AttemptScope:
    resource: object = field(repr=False, compare=False)
    acquire: Callable[[], bool] = field(repr=False, compare=False)
    release: Callable[[], object] = field(repr=False, compare=False)

    def __post_init__(self):
        if self.resource is None or not callable(self.acquire) or not callable(self.release):
            raise AttemptScopeError(
                "attempt scope requires a resource and acquire/release callbacks")

    def copied(self):
        return AttemptScope(self.resource, self.acquire, self.release)


def registered_attempt_scope(adapter) -> AttemptScope | None:
    """Read an explicit value/slot without invoking discovery or a descriptor getter."""
    try:
        values = object.__getattribute__(adapter, "__dict__")
    except AttributeError:
        values = {}
    if "attempt_scope" in values:
        claimed = values["attempt_scope"]
    else:
        claimed = None
        for owner in type(adapter).__mro__:
            if "attempt_scope" not in vars(owner):
                continue
            declared = vars(owner)["attempt_scope"]
            if isinstance(declared, MemberDescriptorType):
                try:
                    claimed = declared.__get__(adapter, type(adapter))
                except AttributeError:
                    raise AttemptScopeError(
                        "declared attempt scope slot is uninitialized") from None
            else:
                claimed = declared
            break
    if claimed is None:
        return None
    if type(claimed) is not AttemptScope:
        raise AttemptScopeError("attempt_scope must be an explicit AttemptScope value or None")
    return claimed.copied()
