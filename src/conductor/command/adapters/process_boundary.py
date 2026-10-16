"""Trusted native policy, supplied by an owned attempt, never by HTTP arguments.

These values do not create a profile or grant access. The attempt must own those
resources before it can request this launch. Vendor integration remains separate.
"""
from dataclasses import dataclass
from pathlib import Path, PurePath
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
#: The product keeps one login home per harness in `<anything>/DecemberCommand/logins/<name>`, case
#: folded. The boundary grants a login home of this shape and no other folder.
LOGIN_PARENTS = ("decembercommand", "logins")
LOGIN_SHAPE = "DecemberCommand/logins/<name>"
#: Whether the runner loans a leased login home to a confined attempt at all. It does not, as
#: shipped. The rights of a credential refresh let the attempt create files in that home and
#: overwrite every file beneath it, and the vendor's executable configuration (hooks, tool servers,
#: user instructions, a notify command) lives there and is run again with the person's rights by
#: spawns that stand outside the boundary: a status read, a quota read, a sign-in. A review ruling
#: on which objects of the home the attempt may write opens this, and nothing else does.
LOGIN_LOAN_OPEN = False


def login_loan_provided() -> bool:
    """Whether the runner loans a leased login home today: the fact a door asks before a claim.

    Only the boolean True counts as open. The runner refuses a login home with this answer `False`
    (`ProfileRefused`, before any profile, journal record or change exists), so a door that
    reads it and a spawn that is judged by it can never disagree.
    """
    return LOGIN_LOAN_OPEN is True


def login_home_named(path: object) -> bool:
    """Whether `path` is written as a login home of the product (`DecemberCommand/logins/<name>`).

    A fact about the written place only (its names, case folded), so a door can ask it before an
    attempt is claimed. It does not say that the folder exists or that the attempt holds the lease
    on it: the runner checks both before it grants anything.

    Args:
        path: A path string or path-like; anything else is not a login home.
    """
    text = str(path) if isinstance(path, PurePath) else path
    if type(text) is not str or "\x00" in text:
        return False
    parts = [part for part in re.split(r"[\\/]+", text) if part]
    return (len(parts) >= 3 and not any(part in (".", "..") for part in parts)
            and tuple(part.casefold() for part in parts[-3:-1]) == LOGIN_PARENTS)


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
    executable and what it loads. `login` is the ABSOLUTE login home the attempt holds under the
    shared login lease (the subscription road), and None on the API-key road. Nothing here grants
    anything: the runner checks each folder, takes the login home only if the attempt's own lease
    names it, and its journal grants and returns it (`process_loans`). A `login` is refused while
    `login_loan_provided()` is False, and it is, as shipped.
    """

    work: str
    home: str | None
    install: str
    login: str | None = None

    def __post_init__(self):
        _route("work", self.work)
        if self.home is not None:
            _route("home", self.home)
        if (type(self.install) is not str or "\x00" in self.install
                or not Path(self.install).is_absolute()):
            raise ValueError("install must be the absolute folder of the pinned executable")
        if self.login is not None and (type(self.login) is not str or "\x00" in self.login
                                       or not Path(self.login).is_absolute()):
            raise ValueError("login must be the absolute login home the attempt's lease names")
        if self.login is not None and self.home is not None:
            raise ValueError("a per-spawn home and a login home are never both loaned")
