"""Detached process environment values; no filesystem or process authority."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
#: The variable of ADR-7e: git does not search upward past the directories it names.
GIT_CEILING = "GIT_CEILING_DIRECTORIES"


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


def git_ceiling_environment(env: Mapping[str, str], root: Path, work: Path, cwd: Path, *,
                            windows: bool) -> dict[str, str]:
    """ADR-7e: tell git it must not search upward from the work tree into the owner's repository.

    A child standing in the work folder or beneath it, where every harness stands, gets
    `GIT_CEILING_DIRECTORIES=<root>`, last, replacing any spelling of the name a caller or the
    parent environment supplied (on Windows names fold case, so every spelling is one variable).
    A child standing elsewhere is left as it is: `conduct projects add` reads a candidate folder
    through a runner rooted at the candidate's PARENT, and a ceiling there would hide the
    repository that encloses a subfolder.

    This is extra protection, not the boundary: an explicit `git -C`, `--git-dir` and a plain file
    write are not stopped by it (spec 10.6). The value is one path, so a root whose name holds the
    platform's path-list separator names something else to git; that limit is stated, not handled.

    Args:
        env: The environment selected for the child.
        root: The runner's resolved project root; the value of the variable.
        work: The project's work folder (`<root>/work`).
        cwd: The child's working folder, already walked from `root`.
        windows: Whether environment names match without regard to case.

    Returns:
        A new mapping; `env` is never changed.
    """
    folder = Path(cwd)
    if folder != Path(work) and Path(work) not in folder.parents:
        return dict(env)
    kept = {name: value for name, value in env.items()
            if (name.upper() if windows else name) != GIT_CEILING}
    return {**kept, GIT_CEILING: str(root)}


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
