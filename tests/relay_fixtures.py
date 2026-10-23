"""Relay-home layouts and fake natives for the unit tests of the relay layer.

Real folders under a pytest tmp path, in the shape the product keeps them in
(`DecemberCommand/logins/<name>`, `DecemberCommand/relay/<key>/<name>`), and DACLs held as text by
a fake native, the way `tests/test_process_loans.py` holds them. Nothing here is the operator's
folder: every path is under the tmp path the caller passes.
"""
from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from conductor.command.adapters.relay_home import relay_home_shape, relay_key, relay_root_sddl
from conductor.ownership_native import NativeOwnershipError, identity

HEX = "0123456789abcdef"
OWNER = "S-1-5-21-1"
#: What a folder made under the protected relay folder inherits, as the OS reads it back.
INHERITED = (f"O:{OWNER}D:AI(A;OICIID;FA;;;SY)(A;OICIID;FA;;;{OWNER})")
#: A login home as the operator has it: inherited from the user's folder, no container named.
LOGIN_DACL = (f"O:{OWNER}D:AI(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)(A;OICIID;FA;;;{OWNER})"
              "(A;OICIID;0x1200a9;;;BU)")


def link(path: Path, target: Path) -> None:
    """A directory link at `path` to `target`: a junction on Windows (no privilege), else a link."""
    if os.name == "nt":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(target)],
                              capture_output=True)
        assert done.returncode == 0, done.stderr
    else:
        os.symlink(target, path, target_is_directory=True)


def layout(base: Path, *, kind: str = "c") -> SimpleNamespace:
    """A project, an install folder, one login home and the relay home of the project's attempt."""
    root = (base / "project").resolve()
    work = root / "work" / "t1"
    work.mkdir(parents=True)
    install = (base / "harnesses" / "kit" / "1.0").resolve()
    install.mkdir(parents=True)
    top = (base / "DecemberCommand").resolve()
    login = top / "logins" / "claude-code"
    login.mkdir(parents=True)
    ident = tuple(identity(root))
    key = top / "relay" / relay_key(ident)
    home = key / f"{kind}-{HEX}"
    home.mkdir(parents=True)
    return SimpleNamespace(root=root, ident=ident, work=work, install=install, top=top,
                           login=login, relay=top / "relay", key=key, home=home)


def shape(found: SimpleNamespace, **changes) -> str | None:
    """`relay_home_shape` for a layout; `changes` replace any one of its arguments."""
    arguments = {"auth_homes": (found.login,), "root": found.root, "root_identity": found.ident,
                 "path": found.home, "work": found.work, "install": found.install}
    arguments.update(changes)
    return relay_home_shape(**arguments)


class ReadHold:
    """A held folder or file without the OS: identity from the file system, as the real hold reads
    it. It refuses a link and an object of the other kind, as the real hold does."""

    def __init__(self, path, *, directory, grants=False):
        self.path, self.identity = Path(path), identity(path)
        if self.path.is_dir() != directory:
            raise NativeOwnershipError("ownership object has the wrong kind")

    def check(self):
        assert identity(self.path) == self.identity

    def close(self):
        pass


def fake_native(state: dict, events: list | None = None) -> SimpleNamespace:
    """Natives over a dict of `path -> (DACL text, protected, owner)`, which a folder made after
    the dict was filled gets `INHERITED` for, unprotected, as a new folder under a parent does.

    A DACL belongs to the folder and not to its name: one that was set is found again by the
    folder's identity under any name it is renamed to, as the OS reads it."""
    log, by_identity = [] if events is None else events, {}

    def snapshot(hold):
        hold.check()
        return state.setdefault(str(hold.path),
                                by_identity.get(hold.identity, (INHERITED, False, OWNER)))

    def set_acl(hold, sddl, *, protected):
        hold.check()
        log.append(("set", str(hold.path), sddl, protected))
        state[str(hold.path)] = by_identity[hold.identity] = (sddl, protected, OWNER)

    @contextmanager
    def exclusive(hold):
        hold.check()
        log.append(("enter", str(hold.path)))
        yield False
        log.append(("exit", str(hold.path)))

    return SimpleNamespace(acl_snapshot=snapshot, acl_set=set_acl,
                           acl_equal=lambda a, b: a == b, acl_exclusive=exclusive)


def sealed(found: SimpleNamespace, state: dict) -> None:
    """Fill `state` with what a good relay layout reads back: the exact relay folder, the key
    folder and the relay home inheriting it, the login home and its parent as the operator has."""
    state[str(found.relay)] = (relay_root_sddl(OWNER), True, OWNER)
    for path in (found.key, found.home):
        state[str(path)] = (INHERITED, False, OWNER)
    for path in (found.login, found.login.parent):
        state[str(path)] = (LOGIN_DACL, False, OWNER)
