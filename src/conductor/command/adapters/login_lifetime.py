"""Keep the declared login resource through the existing attempt and cleanup."""
from __future__ import annotations

from .login_refusal import ids_of, sentence
from .process import OwnershipError, ProcessRunner


class LoginLeaseRefused(OwnershipError):
    """The login guard refused at its entry, so the attempt never began and nothing ran.

    It keeps two closed ids (`login_refusal`) and nothing the owner wrote: the owner's sentence
    names state of the operator's machine, and stays in `__cause__` for a log, never in a receipt.
    """

    def __init__(self, code: str, reader: str | None = None) -> None:
        super().__init__(sentence(code, reader))
        self.code, self.reader = code, reader


class _Entry:
    """A guard whose refusal at ENTRY, and only there, is made the typed refusal.

    A refusal raised when the guard closes comes after the task ran: its result is lost, which
    is not "no task was spawned", so it is passed on as it is.
    """

    def __init__(self, guard):
        self._guard = guard

    def __enter__(self):
        try:
            return self._guard.__enter__()
        except Exception as refused:
            ids = ids_of(refused)
            if ids is None:
                raise
            raise LoginLeaseRefused(*ids) from refused

    def __exit__(self, kind, error, traceback):
        return self._guard.__exit__(kind, error, traceback)


def owned_login_attempt(method):
    def guarded(self, *args, **kwargs):
        with _Entry(ProcessRunner.login_write_guard(self._workspace.root, self._signed_in_road())):
            return method(self, *args, **kwargs)
    guarded.__name__ = method.__name__
    guarded.__doc__ = method.__doc__
    guarded.__wrapped__ = method
    return guarded
