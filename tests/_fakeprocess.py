"""Windows pytest launch seam for exact fake files created by ``_fakeexe.build``.

The registry is test-local authority, not a product fallback or a Windows trust rule.
Native CLI and unregistered commands retain their original launch path. A registered
file that changes must fail before Popen; it must never fall through to native execution.
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

MODULES = frozenset({"_fakeclaude", "_fakecodex", "_fakegrok", "_fakekimi", "_fakegh",
                     "_fakepolicy", "_fakepin"})


@dataclass(frozen=True)
class FakePin:
    module: str
    digest: bytes


_PINS: dict[str, FakePin] = {}


def _key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).digest()


def register_built(path, module):
    """Called only after the builder wrote its reviewed fixture body."""
    if module not in MODULES or not Path(path).is_absolute():
        raise ValueError("only an absolute built fake with a known module may be registered")
    _PINS[_key(path)] = FakePin(module, _digest(path))


def register_copy(source, target):
    """An explicitly copied fixture keeps the source's reviewed module and digest."""
    pin = _PINS[_key(source)]
    if (not Path(target).is_absolute()
            or _digest(source) != pin.digest or _digest(target) != pin.digest):
        raise ValueError("fake copy differs from the registered source")
    _PINS[_key(target)] = pin


def clear():
    _PINS.clear()


def _launch_args(args, positional, options):
    if not isinstance(args, (list, tuple)) or not args:
        return args
    executable = args[0]
    if not isinstance(executable, (str, os.PathLike)):
        return args
    path = Path(executable)
    lookup = path if path.is_absolute() else Path(options.get("cwd") or Path.cwd()) / path
    pin = _PINS.get(_key(lookup))
    if pin is None:
        return args
    if (not path.is_absolute() or positional
            or options.get("shell") or options.get("executable")):
        raise ValueError("registered fake needs absolute argv, keyword options and no shell")
    try:
        unchanged = _digest(path) == pin.digest
    except OSError:
        unchanged = False
    if not unchanged:
        raise ValueError("registered fake changed or disappeared; native fallback is forbidden")
    # Python's zip importer accepts this PE-prefixed archive; measured on this Windows runtime.
    # It sets sys.argv[0] to the original fixture, so fakegh's adjacent files and argv survive.
    return [sys.executable, *args]


def popen_for(original, *, windows):
    """Wrap Popen only for the Windows fixture road; all other processes stay real."""
    if not windows:
        return original

    class RegisteredFakePopen(original):
        def __init__(self, args, *positional, **options):
            super().__init__(_launch_args(args, positional, options), *positional, **options)

    return RegisteredFakePopen
