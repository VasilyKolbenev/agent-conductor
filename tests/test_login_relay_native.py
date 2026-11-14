"""The files the relay copy writes carry the DACL of the folder they are written into, and no other.

A relay home is a folder the runner prepared for one attempt: its entries come from the relay
folder above it (protected, SYSTEM and the owner) and, once the attempt starts, the loan to the
attempt's container. A credential file with a DACL of its own would not follow either: it could be
open to someone the folder is closed to, or closed to the container the folder is lent to. A file
written elsewhere and moved in keeps the entries of the folder it was written in, which is the
same fault by the other road. So the file is created in place, plainly, and given no security.

This is read from the operating system with the stock `icacls`, on a real folder. The folder is
narrowed to SYSTEM and the current user first (the shape of the relay folder), and its own entries
are counted before the copy: the file must then carry exactly those two and mark them inherited,
which neither an explicit entry nor an entry kept from another folder can do.
"""
from __future__ import annotations

import os
import subprocess
from datetime import timedelta

import pytest

from conductor.command.adapters.claude_relay import CLAUDE_RELAY
from conductor.command.adapters.codex_relay import CODEX_RELAY
from conductor.command.adapters.login_relay import Ready, Ticket, copy_in, ready
from tests import relay_credentials as fake

pytestmark = pytest.mark.skipif(os.name != "nt", reason="DACLs are a Windows fact")


def entries(path):
    """The access entries `icacls` prints for a path, as lines of bytes."""
    done = subprocess.run(["icacls", str(path)], capture_output=True, check=True)
    return [row for row in done.stdout.splitlines() if b":(" in row]


def narrow_to_system_and_me(folder):
    """Protect a folder with SYSTEM and the current user as its only entries, handed down.

    The SID comes from the suite's own helper, which takes `whoami`'s bytes and decodes them in the
    OEM code page, tolerantly (a SID is ASCII). `whoami` prints the account name in the console's
    code page, and a name in Cyrillic is not UTF-8 there whatever `PYTHONUTF8` says: decoding it
    as text in the locale's encoding made this test depend on the console it was started from.
    """
    from tests.os_boundary_windows import current_user_sid
    sid = current_user_sid()
    subprocess.run(["icacls", str(folder), "/inheritance:r", "/grant:r",
                    "*S-1-5-18:(OI)(CI)F", f"*{sid}:(OI)(CI)F"], capture_output=True, check=True)


@pytest.mark.parametrize("spec,home", [
    pytest.param(CLAUDE_RELAY, fake.claude_home, id="claude"),
    pytest.param(CODEX_RELAY, fake.codex_home, id="codex")])
def test_every_file_of_the_copy_has_exactly_the_entries_of_its_folder_inherited(
        tmp_path, spec, home):
    real, relay = home(tmp_path), fake.relay_home(tmp_path)
    found = ready(real, spec, fake.NOW, timedelta(minutes=40))
    assert isinstance(found, Ready), found
    narrow_to_system_and_me(relay)
    assert len(entries(relay)) == 2, "the folder was not narrowed, so the check proves nothing"

    assert isinstance(copy_in(real, relay, spec, found.digest), Ticket)

    for name in spec.files:
        written = entries(relay / name)
        assert len(written) == 2 and all(b"(I)" in row for row in written), (name, written)
