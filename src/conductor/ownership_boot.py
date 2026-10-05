"""The one place that answers "what is the boot measurement now" for ownership.

On Windows it is the counter witness (`boot_kuser`); on Linux and macOS it is the per-boot id
`ownership_native.boot_identity` reads. Project and login records, and every recovery, ask here and
nowhere else, so a test can stand in for a restart at a single seam and the product has a single
place to refuse when the boot cannot be measured.

`ownership_native.boot_identity` keeps answering the old class-90 string for the callers that
compare it outside project and login ownership.
"""
from __future__ import annotations

import os

from . import boot_kuser
from .boot_witness import BootRefused
from .ownership_errors import OwnerRefused


def current_boot() -> str:
    """The witness text of the current boot.

    Raises:
        BootRefused: on Windows, when the counter cannot be read as the documented layout.
        OSError: elsewhere, when the OS does not answer.
    """
    if os.name == "nt":
        return boot_kuser.current_witness()
    from . import ownership_native
    return ownership_native.boot_identity()


def measured(what: str) -> str:
    """The current boot, for a record that will be written.

    Args:
        what: What would be opened ("owner session", "shared login lease"), for the message.

    Raises:
        OwnerRefused: `ownership_unavailable` when the boot cannot be measured: a record whose
            boot is unknown could never be recovered after a crash, so none is written.
    """
    try:
        return current_boot()
    except BootRefused as error:
        raise OwnerRefused("ownership_unavailable",
                           f"the OS boot cannot be measured, so no {what} is opened: {error}"
                           ) from error
