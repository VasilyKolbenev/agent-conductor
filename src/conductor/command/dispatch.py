"""Pure validation for the public, durable ``dispatch`` argument shape."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_FIELDS = frozenset({"argv", "cwd", "env_allow", "output_limit"})


class DispatchArgumentError(ValueError):
    """Dispatch arguments would persist an unsafe or ambiguous command shape."""


def validate_dispatch_arguments(arguments: Mapping[str, object]) -> None:
    """Fail closed before proposal append; resolve no environment value here."""
    if not isinstance(arguments, Mapping):
        raise DispatchArgumentError("dispatch arguments must be a JSON object")
    if "env" in arguments:
        raise DispatchArgumentError(
            "dispatch arguments must reference environment names through env_allow; "
            "literal env values are not durable request data")
    unknown = sorted(set(arguments) - _FIELDS)
    if unknown:
        raise DispatchArgumentError(
            f"dispatch arguments contain unsupported fields: {unknown!r}")
    argv = arguments.get("argv")
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence) or not argv:
        raise DispatchArgumentError("argv must be a non-empty list of strings")
    if any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise DispatchArgumentError("argv must contain only NUL-free strings")
    cwd = arguments.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise DispatchArgumentError("cwd must be a non-empty path string")
    env_allow = arguments.get("env_allow", ())
    if isinstance(env_allow, (str, bytes)) or not isinstance(env_allow, Sequence):
        raise DispatchArgumentError("env_allow must be a list of environment names")
    names = tuple(env_allow)
    if any(not isinstance(name, str) or _ENV_NAME.fullmatch(name) is None
           for name in names):
        raise DispatchArgumentError("env_allow contains an invalid environment name")
    if len(names) != len(set(names)):
        raise DispatchArgumentError("env_allow must not repeat a name")
    limit = arguments.get("output_limit", 64 * 1024)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise DispatchArgumentError("output_limit must be a positive integer")
