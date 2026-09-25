"""Creation admission; durable value grammar and historical reads stay separate.

No filesystem access. Windows names are rejected portably, not normalized.
The Windows budgets cover this build's actual new paths; they are deliberately
not a claim that every Windows API shares a limit or that arbitrary child files
will fit. Existing records are read before callers use this admission door.
"""
from __future__ import annotations

from pathlib import PurePath, PureWindowsPath

from .contracts import ContractError


class WindowsNameError(ContractError):
    """A new filesystem identity is not a portable Windows name."""


class WindowsPathError(ContractError):
    """A new operation exceeds this build's supported Windows path budget."""


_DEVICES = frozenset({'CON', 'PRN', 'AUX', 'NUL'} | {
    prefix + number for prefix in ('COM', 'LPT')
    for number in ('1', '2', '3', '4', '5', '6', '7', '8', '9', '¹', '²', '³')})


def admit_name(name: str, label: str) -> None:
    """Called only after the caller's existing identifier grammar."""
    if name.endswith(('.', ' ')):
        raise WindowsNameError(f'{label} must not end with a dot or space')
    if name.split('.', 1)[0].upper() in _DEVICES:
        raise WindowsNameError(f'{label} is a reserved Windows basename')


def _windows_budget(path: PurePath, limit: int, label: str) -> None:
    if isinstance(path, PureWindowsPath):
        units = len(str(path).encode('utf-16-le', errors='surrogatepass')) // 2
        if units > limit:
            raise WindowsPathError(f'{label} exceeds the Windows path budget; '
                        'shorten the identifier or move the project to a shorter path')


def admit_work_path(path: PurePath, item: str, scope: str | None) -> None:
    """No work mkdir, home sweep, version check or child may precede this."""
    admit_name(item, 'work_item_id')
    if scope is not None:
        admit_name(scope, 'work_scope')
    # SetCurrentDirectory requires room for the trailing separator and NUL;
    # its documentation explicitly warns that an overlong cwd breaks spawning.
    _windows_budget(path, 258, 'working directory')


def admit_file(path: PurePath, label: str) -> None:
    """Budget both final file and the private tempfile used by run_files."""
    _windows_budget(path.parent, 247, label)
    _windows_budget(path, 259, label)
    _windows_budget(path.with_name('.' + path.name + '.xxxxxxxx.tmp'), 259, label)


def admit_directory(parent: PurePath, name: str, leaves: tuple[str, ...],
                    label: str, *,
                    directories: tuple[str, ...] = ()) -> None:
    """Directory publication stages under .<id>.<eight tempfile characters>."""
    admit_name(name, label)
    for directory in (parent / name, parent / ('.' + name + '.xxxxxxxx')):
        _windows_budget(directory, 247, label)
        for child in directories:
            _windows_budget(directory / child, 247, label)
        for leaf in leaves:
            admit_file(directory / leaf, label)
