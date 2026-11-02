"""Read only the DACL and identities of Kimi's two fixed source names on Windows."""
from __future__ import annotations

import os

from .process_loans import _refused
from .relay_home import ace_refusal, relay_root_for

# Kimi 0.38.0's two reviewed regions. The selected model, TOML and token bytes are irrelevant
# to Windows access: a child can open either file by its literal name.
LEAVES = ("kimi-code.json", "kimi-code-env-0e4f99c69cc27850.json")


def inspect_sources(native, homes, stack, hold_factory):
    """Pin existing objects, refuse open DACLs, and remember missing and present identities.

    All names are fixed relative to the configured home. Only a missing final component below
    a pinned parent is absent. An access failure, reparse object or additional file link refuses.
    """
    facts = {}
    for home in homes:
        if not home.is_absolute() or os.pardir in home.parts:
            raise _refused("a configured Kimi source has an indirect or relative path")
        try:
            _source(native, home, stack, hold_factory, facts)
        except OSError as error:
            raise _refused("a configured Kimi source cannot be safely checked") from error
    return facts


def _source(native, home, stack, hold_factory, facts):
    # Pin the written chain, including dedicated homes outside the managed layout. Only the
    # managed logins parent has a DACL contract of its own. No ancestor's contents are listed.
    managed = relay_root_for(home) is not None
    for path in reversed(home.parents):
        if not _inspect(native, path, True, stack, hold_factory, facts,
                        check_acl=managed and path == home.parent):
            return
    for path in (home, home / "credentials"):
        if not _inspect(native, path, True, stack, hold_factory, facts):
            return
    for name in LEAVES:
        _inspect(native, home / "credentials" / name, False, stack, hold_factory, facts)


def _inspect(native, path, directory, stack, hold_factory, facts, *, check_acl=True):
    # lstat distinguishes an absent name from a dangling reparse object. The following
    # no-follow hold identifies the actual object and denies replacement until stack.close().
    try:
        os.lstat(path)
    except FileNotFoundError:
        if path.parent == path:
            raise
        facts[str(path)] = None
        return False
    hold = hold_factory(path, directory=directory)
    stack.callback(hold.close)
    if check_acl:
        refusal = ace_refusal(native.acl_snapshot(hold)[0])
        if refusal:
            raise _refused(f"the configured Kimi source {refusal}")
    # WindowsPath equality folds case, including on NTFS directories configured to distinguish it.
    facts[str(path)] = hold.identity
    return True
