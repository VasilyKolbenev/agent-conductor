"""Detached process environment values; no filesystem or process authority."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def literal_environment(value: object, error: type[Exception]) -> Mapping[str, str]:
    """The historical CommandSpec literal map validation, with its error type."""
    if not isinstance(value, Mapping):
        raise error("env must map variable names to string values")
    out: dict[str, str] = {}
    for name, item in value.items():
        if not isinstance(name, str) or ENV_NAME.fullmatch(name) is None:
            raise error(f"env names an invalid variable: {name!r}")
        if not isinstance(item, str) or "\x00" in item:
            raise error(f"env[{name!r}] must be a string without NUL")
        out[name] = item
    return MappingProxyType(out)


def select_environment(source, names, overrides) -> dict[str, str]:
    """Exact allowlist lookup first; code-owned literal overrides last."""
    return {**{name: source[name] for name in names if name in source}, **overrides}


class EnvironmentSelectionError(ValueError):
    """A captured value has no unambiguous native interpretation."""


@dataclass(frozen=True)
class EnvironmentValues:
    """Private memory only, after the runner selected the actual child values."""
    values: Mapping[str, str] = field(repr=False)
    windows: bool = False

    def __post_init__(self) -> None:
        if type(self.windows) is not bool:
            raise EnvironmentSelectionError("invalid platform interpretation")
        try:
            copied = literal_environment(self.values, EnvironmentSelectionError)
        except Exception:
            raise EnvironmentSelectionError("invalid captured environment") from None
        object.__setattr__(self, "values", copied)

    def native_value(self, name: str) -> str | None:
        """Interpret names only after exact allowlist selection, as the OS does."""
        if type(name) is not str or ENV_NAME.fullmatch(name) is None:
            raise EnvironmentSelectionError("invalid environment reference")
        wanted = name.upper() if self.windows else name
        matches = [value for key, value in self.values.items()
                   if (key.upper() if self.windows else key) == wanted]
        if len(matches) > 1:
            raise EnvironmentSelectionError("ambiguous native environment name")
        return matches[0] if matches else None
