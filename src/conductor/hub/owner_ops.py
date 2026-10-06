"""The short ownership commands the hub runs for a person's click (spec 4.1.8, 8.7; ADR-6, ADR-8).

`conduct ownership recover`, `recover-login` and `providers --from-profile` are the commands a
person would type; the hub starts the same ones, in a session or process group of its own and in
no Job (so the death of the hub does not end one mid-`acquire_owner`), with `CONDUCT_HOME` set to
its own folder, and never ends one itself. What a command printed is believed only in two ways:
the one JSON object a success prints, and the code on the FIRST error line when the step's own
list holds it. Anything else is `subprocess_failed`. The first line is also read for one closed
reason that tells the person which action to take (`recovery_reason`, `restart_reason`); the
reason changes no state and grants nothing, and no text of the command is kept.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Collection, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from conductor.hub import job, refusals

OUTPUT_BOUND = 65536
POLL_SECONDS = 0.05
#: The command every owner operation is started with; a test may give another head.
HEAD = (sys.executable, "-m", "conductor")
_REFUSAL = re.compile(r"([a-z][a-z0-9_]*): \S")
#: The two job policies under which a command may start (`kill_on_close` ends it with the hub).
_RUNNABLE = ("none", "breakaway")


@dataclass(frozen=True)
class Ran:
    """What a finished command left: its exit code and its stdout and stderr text.

    Each text is read to `OUTPUT_BOUND`; over the bound the text is dropped, never trusted. Only
    the FIRST line of `error` is ever looked at, and only by the parsers of this module.
    """

    code: int
    out: str
    error: str


def run_command(args: Sequence[str], *, home: Path,
                popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                policy: Callable[[], str] | None = None, head: Sequence[str] = HEAD) -> Ran:
    """Run `head + args` to its end and collect what it said; never raises for its failure.

    Args:
        args: The arguments after the head (`ownership recover --dir <root>`).
        home: The hub's folder: the working folder, `CONDUCT_HOME`, and where the two scratch
            files of the command's output live while it runs (both are removed at the end).
        popen: `subprocess.Popen` unless a test stands in.
        policy: The word for the hub's own Windows job (`job.own_policy` by default).
        head: The command before the arguments.

    Returns:
        The collected result; `Ran(1, "", "")` when the command could not be started: the job
        would end it with the hub, or the OS refused to start it.
    """
    word = (policy or job.own_policy)()
    if word not in _RUNNABLE:
        return Ran(1, "", "")
    isolated = _isolation(word)
    paths: list[Path] = []
    try:
        for prefix in ("hub-owner-out-", "hub-owner-err-"):
            handle, name = tempfile.mkstemp(prefix=prefix, dir=home)
            os.close(handle)
            paths.append(Path(name))
        return _run([*head, *args], home, popen, isolated, *paths)
    except OSError:
        return Ran(1, "", "")
    finally:
        for path in paths:
            with suppress(OSError):
                path.unlink()


def _isolation(policy: str) -> dict:
    """A group (Windows) or a session (POSIX) of its own, and no console window."""
    if os.name != "nt":
        return {"start_new_session": True}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    if policy == "breakaway":
        flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    return {"creationflags": flags}


def _run(argv: list[str], home: Path, popen: Callable[..., subprocess.Popen], isolated: dict,
         out_path: Path, error_path: Path) -> Ran:
    env = {**os.environ, "CONDUCT_HOME": str(home), "PYTHONIOENCODING": "utf-8"}
    with open(out_path, "wb") as out, open(error_path, "wb") as error:
        process = popen(argv, cwd=home, stdin=subprocess.DEVNULL, env=env, stdout=out,
                        stderr=error, **isolated)
    while process.poll() is None:
        time.sleep(POLL_SECONDS)
    return Ran(process.returncode, _collect(out_path), _collect(error_path))


def _collect(path: Path) -> str:
    with open(path, "rb") as handle:
        data = handle.read(OUTPUT_BOUND + 1)
    return "" if len(data) > OUTPUT_BOUND else data.decode("utf-8", errors="replace")


def _first_line(error_text: str) -> tuple[str, str] | None:
    """`(code, rest)` of the FIRST line when it is `<code>: <text>`, else `None`."""
    lines = error_text.splitlines()
    found = _REFUSAL.match(lines[0]) if lines else None
    return None if found is None else (found[1], lines[0][found.end(1) + 2:])


def refusal_code(error_text: str, allowed: Collection[str]) -> str:
    """The code on the first line of a refusal when the step lists it, else `subprocess_failed`.

    Nothing else of the text is used: no other line, no word after the code.
    """
    first = _first_line(error_text)
    return first[0] if first is not None and first[0] in allowed else "subprocess_failed"


def recovery_reason(error_text: str, allowed: Collection[str]) -> str | None:
    """The typed recovery reason behind a `subprocess_failed`, or `None`.

    It is the FIRST line's code, when that word is a reason that may stand beside
    `subprocess_failed` and the step does not already list it as its own code (the step then
    says it in its top code). Nothing else of what a command printed is kept.
    """
    first = _first_line(error_text)
    word = None if first is None else first[0]
    beside = refusals.OPERATION_DETAIL_REASONS.get(word, ())
    return word if "subprocess_failed" in beside and word not in allowed else None


#: The two steps whose OWN code is the restart-family code, and the sentence stems that tell
#: four situations apart, most specific first. A stem is a lower-cased fragment of what the
#: project and login recoveries and `boot_witness.other_environment_advice` print; the tests pin
#: this table against those sentence builders, so a rewording cannot silently turn an
#: instruction to prepare into advice to restart.
_RESTART_CODE = {"recover": "recovery_required", "recover_login": "login_recovery_required"}
_RESTART_STEMS = (
    ("another restart does not make the old environment the current one", "other_environment"),
    ("predates the boot counter", "prepare_needed"))
_RESTART_FIRST = "restart the os before recovering"


def restart_reason(error_text: str, step: str) -> str | None:
    """The closed reason behind a recovery that refused with its restart-family code, or `None`.

    `None` unless the FIRST line's code is the restart-family code of `step`. Then one of
    `other_environment`, `prepare_needed`, `restart_needed` or `not_proven`; a sentence the table
    does not know is `not_proven`, never restart advice. Nothing else the command printed is kept.
    """
    first = _first_line(error_text)
    code = _RESTART_CODE.get(step)
    if code is None or first is None or first[0] != code:
        return None
    detail = first[1].lower()
    for stem, word in _RESTART_STEMS:
        if stem in detail:
            return word
    return "restart_needed" if detail.startswith(_RESTART_FIRST) else "not_proven"


def _one_object(out: str) -> dict | None:
    try:
        value = json.loads(out)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def recovered_head(out: str) -> bool:
    """Whether stdout is the one JSON object a successful recovery prints: `phase: recovered`."""
    found = _one_object(out)
    return found is not None and found.get("phase") == "recovered"


def recovered_login(out: str) -> bool:
    """Whether stdout is the one JSON object a successful login recovery prints."""
    found = _one_object(out)
    return found is not None and found.get("state") == "recovered"
