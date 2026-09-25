"""Keep the declared login resource through the existing attempt and cleanup."""
from .process import ProcessRunner


def owned_login_attempt(method):
    def guarded(self, *args, **kwargs):
        with ProcessRunner.login_write_guard(self._workspace.root, self._signed_in_road()):
            return method(self, *args, **kwargs)
    guarded.__name__ = method.__name__
    guarded.__doc__ = method.__doc__
    guarded.__wrapped__ = method
    return guarded
