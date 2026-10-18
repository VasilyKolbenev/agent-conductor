"""The refusals of the owned-process runner: the family every transport already catches.

`ProcessRunnerError` is the family. `LaunchRefused` is its narrow member for ONE known fact: a
confined launch the runner refused or could not apply the container policy to, with the child
ended before it ran any code and reaped. It is deliberately not the place for anything else. An
outcome that is unknown after the child may have run, and a cleanup that did not finish, are not
a refusal, and keep the error they had.
"""
from __future__ import annotations


class ProcessRunnerError(RuntimeError):
    """The runner cannot safely honour the request as stated."""


class CommandSpecError(ProcessRunnerError):
    """A command is not structured argv, or its environment names are malformed."""


class ContainmentError(ProcessRunnerError):
    """The requested cwd is not strictly, locally beneath the project root."""


class OwnershipError(ProcessRunnerError):
    """A stop names no child this runner started and still holds."""


#: The closed vocabulary of a launch refusal: the code, and the one sentence it shows.
LAUNCH_SENTENCES = {
    "launch_failed": "the confined child could not be created",
    "policy_not_applied": "the container policy was not shown on the child, which was ended "
                          "before it ran",
}


class LaunchRefused(ProcessRunnerError):
    """A confined launch refused before any child code ran, with nothing left running.

    Raised for the OS refusing to create the confined child, and for the policy check on the still
    suspended child failing when the child was ended and reaped. Never raised once the child may
    have run, and never when ending the child failed: those keep their own errors.

    It carries a closed `code` and the number of the OS error, and nothing of the original error's
    text, which can name a path or a value of the child's environment. The original error is not
    chained either.
    """

    def __init__(self, code: str, os_error: int | None = None) -> None:
        if code not in LAUNCH_SENTENCES:
            raise ValueError("unknown launch refusal")
        super().__init__(LAUNCH_SENTENCES[code])
        self.code, self.os_error = code, os_error
