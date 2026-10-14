"""The reader the product hands the command API, answering from a table without a process.

For the faults a process cannot show without waiting: a call that timed out, output that was cut,
output that carries a value of the environment. Each call takes the next answer and is recorded,
arguments, stdin and timeout together. `tests/_fakegh.py` is the other kind of witness, a real
executable that is asked through the real runner.
"""
from __future__ import annotations

from conductor.command.accept_gh import GhAnswer


class ScriptGh:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, args, *, stdin=None, timeout=None, output_limit=None):
        self.calls.append({"argv": list(args), "stdin": stdin, "timeout": timeout})
        return self.answers.pop(0)


def answer(output=b"", code=0, **flags):
    """One `GhAnswer`; a str output is encoded."""
    data = output.encode("utf-8") if isinstance(output, str) else output
    return GhAnswer(exit_code=code, output=data, **flags)
