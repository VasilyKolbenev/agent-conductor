"""Injected owner callbacks; no acquisition, filesystem or process door."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProcessLease:
    handles: tuple[int, ...]
    retire: Callable[[bool], None]

    def __post_init__(self):
        if type(self.handles) is not tuple or not self.handles or any(
                type(handle) is not int or handle < 0 for handle in self.handles):
            raise ValueError("process owner loan requires explicit native handles")
        if not callable(self.retire):
            raise ValueError("process owner loan requires its retirement callback")


@dataclass(frozen=True)
class ProcessOwnership:
    check: Callable[[], None]
    claim: Callable[[], ProcessLease]
    borrow: Callable[[], object]
    resource: Callable[[str], object]

    def __post_init__(self):
        if not callable(self.check) or not callable(self.claim) or not callable(self.borrow) or not callable(self.resource):
            raise ValueError("process ownership requires declared callbacks")


class OwnershipScopes:
    """Synchronization is injected by the existing process execution door."""

    def __init__(self, guard):
        self.guard, self.entries = guard, {}

    def install(self, root, scope):
        if type(scope) is not ProcessOwnership:
            raise ValueError("a process owner scope must use the closed callback value")
        with self.guard:
            if root in self.entries:
                raise ValueError("a process owner scope is already installed")
            self.entries[root] = scope

    def remove(self, root, scope):
        with self.guard:
            if self.entries.get(root) is not scope:
                raise ValueError("only the standing process owner can remove its scope")
            del self.entries[root]

    def find(self, root):
        with self.guard:
            return self.entries.get(root)


class LoginBorrow:
    """Compose only injected contexts; the API-key road enters neither one."""
    def __init__(self, project_context, scope_of, auth_home):
        self.project, self.scope_of, self.auth_home = project_context, scope_of, auth_home
        self.entered, self.resource = False, None

    def __enter__(self):
        if not self.auth_home:
            return self
        self.project.__enter__()
        self.entered = True
        try:
            scope = self.scope_of()
            if scope is not None:
                resource = scope.resource(self.auth_home)
                resource.__enter__()
                self.resource = resource
            return self
        except BaseException as error:
            self.project.__exit__(type(error), error, error.__traceback__)
            self.entered = False
            raise

    def __exit__(self, kind, error, traceback):
        try:
            if self.resource is not None:
                return self.resource.__exit__(kind, error, traceback)
        finally:
            if self.entered:
                self.project.__exit__(kind, error, traceback)
