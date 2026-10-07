"""Trusted native policy, supplied by an owned attempt, never by HTTP arguments.

This value does not create a profile or grant access. The attempt must own those
resources before it can request this launch. Vendor integration remains separate.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class WindowsContainer:
    sid: str
    internet_client: bool = False

    def __post_init__(self):
        if (type(self.sid) is not str
                or re.fullmatch(r"S-1-15-2(?:-[0-9]{1,10}){7}", self.sid) is None
                or any(int(value) > 0xFFFFFFFF for value in self.sid.split("-")[4:])):
            raise ValueError("a full AppContainer profile SID is required")
        if type(self.internet_client) is not bool:
            raise ValueError("internet_client must be a boolean")
