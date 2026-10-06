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
import threading
import time
from collections.abc import Callable, Collection, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from conductor.hub import job, refusals

if TYPE_CHECKING:
    from conductor.hub import operations, registry, supervisor

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


class OwnerOps:
    """The recoveries the hub runs, as operations of the shared ledger (spec 4.1.8, ADR-8).

    Every operation is one row of `operations.Operations` and one daemon thread. The commands are
    the ones a person types; the hub never ends one (not even at its own exit: one that began is
    left to finish), never prepares a restart, and learns what a recovery did from the ownership
    head the supervisor reads, never from what the command printed.
    """

    def __init__(self, home: Path | str, ledger: operations.Operations,
                 sup: supervisor.Supervisor, *,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 policy: Callable[[], str] | None = None, head: Sequence[str] = HEAD) -> None:
        self._home, self._ledger, self._sup = Path(home), ledger, sup
        self._popen, self._policy, self._head = popen, policy, tuple(head)
        self._lock = threading.Lock()
        self._closing = threading.Event()

    def require_free(self, project_id: str) -> None:
        """Refuse `project_busy` while an operation of this project runs."""
        if self._ledger.running_for(project_id) is not None:
            raise refusals.HubRefusal("project_busy", {"project_id": project_id})

    def close(self) -> None:
        """Seal at the hub's exit: nothing new starts, and no command that began is ended."""
        with self._lock:
            self._closing.set()

    def recover(self, project: registry.Project) -> str:
        """Open the `recover` operation of a project and run `conduct ownership recover`.

        Raises:
            HubRefusal: `project_busy` when an operation of the project runs, or the hub is
                closing.
        """
        self._require_open("project_busy", project.project_id)
        ident = self._ledger.open_project_row("recover", project.project_id, "recover")
        self._thread(self._recover, ident, project)
        return ident

    def _recover(self, ident: str, project: registry.Project) -> None:
        ran = self._command(("ownership", "recover", "--dir", project.root))
        if ran.code == 0 and recovered_head(ran.out):
            self._sup.recovered(project.project_id)
            self._ledger.update_row(ident, state="succeeded")
        else:
            self._fail(ident, ran, "recover")

    def _require_open(self, code: str, project_id: str | None = None) -> None:
        if self._closing.is_set():
            raise refusals.HubRefusal(code, {} if project_id is None else {
                "project_id": project_id})

    def _thread(self, body: Callable[..., None], ident: str, *args: Any) -> None:
        def run() -> None:
            try:
                body(ident, *args)
            except Exception:  # an operation must end in its closed vocabulary
                self._ended_by_a_fault(ident)

        thread = threading.Thread(target=run, name=f"hub-owner-{ident[-8:]}", daemon=True)
        try:
            thread.start()
        except RuntimeError:       # no thread could be made: the row must not stay running
            self._ended_by_a_fault(ident)

    def _ended_by_a_fault(self, ident: str) -> None:
        """End a row that is still running as `subprocess_failed`; a row that left is not read."""
        with suppress(refusals.HubRefusal, KeyError):
            if self._ledger.get(ident)["state"] == "running":
                self._ledger.update_row(ident, state="failed", code="subprocess_failed",
                                        detail=None)

    def _command(self, args: Sequence[str]) -> Ran:
        return run_command(args, home=self._home, popen=self._launch, policy=self._policy,
                           head=self._head)

    def _launch(self, argv: list[str], **kwargs: Any) -> subprocess.Popen:
        """Start a command unless the hub is closing: the gate and the start are one step."""
        with self._lock:
            if self._closing.is_set():
                raise OSError("the hub is closing")
            return self._popen(argv, **kwargs)

    def _fail(self, ident: str, ran: Ran, step: str) -> None:
        """End a row `failed` with the code the command printed when the step lists it.

        The row also carries the one closed reason the first line gives: which action a recovery
        that needs a restart or a preparation wants (`restart_reason`), or the recovery a profile
        copy needs first (`recovery_reason`). Nothing else the command printed is kept.
        """
        allowed = refusals.OPERATION_CODES_BY_STEP[step]
        code = refusal_code(ran.error, allowed)
        word = restart_reason(ran.error, step)
        if word is None and code == "subprocess_failed":
            word = recovery_reason(ran.error, allowed)
        self._ledger.update_row(ident, state="failed", code=code,
                                detail=None if word is None else {"reason": word})
