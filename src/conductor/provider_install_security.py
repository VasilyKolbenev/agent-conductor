"""Read-only Windows checks before handing a pinned subscription login to the owner."""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .command.adapters.process_loans import _fields, _split
from .command.adapters.process_profile import ProfileRefused
from .command.adapters.relay_home import LOGIN_ENTRIES, _acl_of
from .ownership_native import NativeHold
from .ownership_records import plain

# H5 manual preflight's masks. Creating a sibling high up on a volume cannot
# replace the user's profile. DELETE_CHILD, WRITE_DAC and ownership there can.
WRITE = 0xD0156 | 0x50000000
REPLACE = 0xD0040 | 0x50000000
_RIGHTS = {
    "FA": 0x1F01FF, "FR": 0x120089, "FX": 0x1200A0, "FW": 0x120116,
    "GA": 0x10000000, "GR": 0x80000000, "GX": 0x20000000, "GW": 0x40000000,
    "RC": 0x20000, "SD": 0x10000, "WD": 0x40000, "WO": 0x80000,
    "CC": 1, "DC": 2, "LC": 4, "SW": 8, "RP": 16, "WP": 32,
    "DT": 64, "LO": 128, "CR": 256,
}


def _rights(text):
    if text.startswith("0x"):
        return int(text, 16)
    if not text or len(text) % 2:
        raise ValueError("unrecognized permission")
    mask = 0
    for i in range(0, len(text), 2):
        mask |= _RIGHTS[text[i:i+2]]
    return mask


def acl_allows(facts, allowed, *, ancestor=False, private=False):
    if facts is None:
        return False
    sddl, _, owner = facts
    if not ancestor and owner not in allowed:
        return False
    try:
        _, aces = _split(sddl)
        if not aces:
            return False
        for ace in aces:
            parts = _fields(ace)
            if len(parts) != 6 or parts[0] not in {"A", "D", "OA", "OD"}:
                return False
            if (parts[0] in {"D", "OD"} or parts[5] in allowed
                    or (parts[5] == "OW" and owner in allowed)):
                continue
            if not private and "IO" in parts[1]:
                continue
            if private or _rights(parts[2]) & (REPLACE if ancestor else WRITE):
                return False
    except (KeyError, ValueError, ProfileRefused):
        return False
    return True


def _external_codex():
    import winreg
    program_data = Path(os.environ.get("ProgramData", ""))
    if not program_data.is_absolute():
        raise OSError("The machine's ProgramData directory could not be established.")
    for name in ("config.toml", "requirements.toml"):
        try:
            (program_data / "OpenAI" / "Codex" / name).lstat()
        except FileNotFoundError:
            continue
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\OpenAI\Codex",
                            access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            return True
    except FileNotFoundError:
        return False


def _allowed(native):
    return {native.current_user_sid(), "SY", "BA", "S-1-5-18", "S-1-5-32-544"}


def verify_login_directory(home):
    from .command.adapters import _winlaunch
    allowed = _allowed(_winlaunch)
    for path in (home.parent, home):
        facts = _acl_of(_winlaunch, NativeHold, path)
        if not acl_allows(facts, allowed, private=True):
            raise OSError("The dedicated login folder has unverified ownership or access.")
    with os.scandir(home) as entries:
        for count, entry in enumerate(entries, 1):
            if count > LOGIN_ENTRIES:
                raise OSError("Too many entries in the dedicated login.")
            path = Path(entry.path)
            folder = stat.S_ISDIR(path.lstat().st_mode)
            plain(path, directory=folder)
            facts = _acl_of(_winlaunch, NativeHold, path, directory=folder)
            if not acl_allows(facts, allowed, private=True):
                raise OSError("An entry in the dedicated login has unverified ownership or access.")


def verify_install(product, install, kind):
    from .command.adapters import _winlaunch
    allowed = _allowed(_winlaunch)
    protected = False
    for directory in (*reversed(install.parents), install):
        facts = _acl_of(_winlaunch, NativeHold, directory)
        ancestor = directory in product.parent.parents
        if not acl_allows(facts, allowed, ancestor=ancestor):
            raise OSError("Unverified ownership or write access in the installation path.")
        if directory in (product, product / "harnesses"):
            protected |= facts[1]
    if not protected:
        raise OSError("The product or harnesses root needs a protected access list.")
    pending, seen = [install], 0
    while pending:
        with os.scandir(pending.pop()) as children:
            for child in children:
                seen += 1
                if seen > 256:
                    raise OSError("The harness installation exceeds its reviewed size.")
                path = Path(child.path)
                folder = stat.S_ISDIR(path.lstat().st_mode)
                plain(path, directory=folder)
                facts = _acl_of(_winlaunch, NativeHold, path, directory=folder)
                if not acl_allows(facts, allowed):
                    raise OSError("Unverified ownership or write access inside the installation.")
                if folder:
                    pending.append(path)
    if kind == "codex" and _external_codex():
        raise OSError("External Codex machine configuration is present.")
