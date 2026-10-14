"""Trusted native policy, supplied by an owned attempt, never by HTTP arguments.

These values do not create a profile or grant access. The attempt must own those
resources before it can request this launch. Vendor integration remains separate.
"""
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class WindowsContainer:
    sid: str
    internet_client: bool = False
    #: The install folder loaned to this attempt (`process_loans`), absolute; None for an attempt
    #: that loans none. A spawn on a container that names one starts a program standing in it.
    install: str | None = None

    def __post_init__(self):
        if (type(self.sid) is not str
                or re.fullmatch(r"S-1-15-2(?:-[0-9]{1,10}){7}", self.sid) is None
                or any(int(value) > 0xFFFFFFFF for value in self.sid.split("-")[4:])):
            raise ValueError("a full AppContainer profile SID is required")
        if type(self.internet_client) is not bool:
            raise ValueError("internet_client must be a boolean")
        if self.install is not None and (type(self.install) is not str or not self.install
                                         or not Path(self.install).is_absolute()):
            raise ValueError("install must be an absolute folder, or None")


_DRIVE = re.compile(r"[A-Za-z]:")


def _route(name: str, value: object) -> None:
    """A route written as a string, relative to the project root, with no way out of it."""
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError(f"{name} must be a route written as a string")
    if (value[0] in "\\/" or _DRIVE.match(value) is not None
            or any(part in ("", ".", "..") for part in re.split(r"[\\/]", value))):
        raise ValueError(f"{name} must be a route beneath the project root")


@dataclass(frozen=True)
class AttemptFolders:
    """The existing folders an attempt works on, which the runner loans to its AppContainer.

    `work` and `home` are routes relative to the project root (`work/<id>`, the per-spawn home);
    `home` is None on the login road. `install` is the ABSOLUTE folder that holds the pinned
    executable and what it loads. Nothing here grants anything: the runner checks each folder and
    its journal grants and returns it (`process_loans`).
    """

    work: str
    home: str | None
    install: str

    def __post_init__(self):
        _route("work", self.work)
        if self.home is not None:
            _route("home", self.home)
        if (type(self.install) is not str or "\x00" in self.install
                or not Path(self.install).is_absolute()):
            raise ValueError("install must be the absolute folder of the pinned executable")
